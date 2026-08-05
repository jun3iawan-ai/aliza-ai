"""
AlizaAI Telegram Bot — command handlers.
Semua command utama: start, help, market, radar, radarpro, setfutures, entry, close,
portfolio, predict, quant, marketstate, status, testalert, marketdebug.
"""

import os
import sys
import asyncio
import logging
import threading
import time as time_module
from datetime import datetime, time, timedelta, timezone
from typing import Any

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None  # type: ignore[misc, assignment]

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.environment import load_project_dotenv
from core.graceful_shutdown import GracefulShutdownController

load_project_dotenv()

from telegram import Bot, BotCommand, Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    ApplicationHandlerStop,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    TypeHandler,
    filters,
)

# Snapshot & market
from engine.market.market_snapshot_engine import (
    get_market_snapshot,
    get_snapshot_timestamp_str,
    is_snapshot_valid,
    update_market_snapshot,
)
from engine.market.global_market_cache import get_global_market_data
from engine.market.breakout_detector import run_breakout_check, format_breakout_alert_message
from engine.market.volume_spike_detector import (
    run_volume_spike_check,
    format_volume_spike_alert_message,
)
from engine.market.funding_rate_monitor import (
    format_funding_section_for_brief,
    check_funding_extremes,
    format_funding_alert_message,
    format_funding_table_for_command,
    get_all_funding_data,
)
from engine.market.macro_monitor import (
    format_macro_section_for_brief,
    check_new_macro_release,
    format_macro_alert_message,
    initialize_macro_seen_dates,
    build_macro_check_command_text,
    get_macro_data,
)
from engine.market.economic_calendar import (
    get_upcoming_events,
    get_events_tomorrow,
    get_events_next_hour,
)
from engine.market import institutional_data as inst_data
from engine.market.market_context_engine import calculate_market_score, format_context_for_brief
import engine.market.market_snapshot_engine as snapshot_state
from engine.market.market_intelligence import analyze_market_environment
from engine.market.market_report_formatter import format_market_report
from engine.market.market_radar_pro_analyzer import (
    generate_radar_pro,
    format_radar_pro_report,
)
from engine.market.market_universe import MAJOR_COINS
# Trading
from engine.trading.opportunity_scanner import (
    scan_opportunities,
    scan_opportunities_from_data,
    format_opportunities_message,
)
from engine.trading.signal_engine import (
    scan_for_signals,
    format_signal_message,
)
from engine.trading.signal_tracker import (
    init_signal_tracking_db,
    record_signal,
    check_open_signals,
    get_signal_stats,
)
from engine.shadow.e3_shadow import (
    collect_shadow_signals,
    dispatch_enabled as shadow_dispatch_enabled,
    dispatch_cooldown_sec as shadow_dispatch_cooldown_sec,
    format_shadow_message,
)
from engine.shadow.promotion_criteria import (
    evaluate_promotion_criteria,
    format_promotion_check_message,
)
from engine.signal_engine import (
    SIGNAL_TYPE_INFORMATIONAL,
    attach_strategy_source,
    process_signal,
)
try:
    from engine.alerts.auto_alert_engine import process_auto_alerts
except ImportError:
    process_auto_alerts = None
from engine.trading.trade_manager import (
    init_trade_db,
    create_trade,
    get_active_trades,
    close_trade,
    trade_direction,
)
try:
    from engine.portfolio.portfolio_ai_engine import evaluate_trade as portfolio_evaluate_trade
except ImportError:
    portfolio_evaluate_trade = None

try:
    from engine.portfolio.drawdown_protector import check_drawdown
except ImportError:
    check_drawdown = None

try:
    from engine.learning.trade_history_tracker import get_closed_history
    from engine.analytics.performance_analyzer import analyze_performance
except ImportError:
    get_closed_history = None
    analyze_performance = None

# Intelligence
from engine.intelligence.market_state_engine import (
    calculate_market_state,
    format_market_state_report,
)

try:
    from engine.market.dynamic_universe import get_tradable_coins
except ImportError:
    get_tradable_coins = None

try:
    from engine.intelligence.predictive_market_ai import predict_market, format_prediction_report
except ImportError:
    predict_market = None
    format_prediction_report = None

try:
    from engine.prediction.prediction_engine import generate_market_prediction
except ImportError:
    generate_market_prediction = None

try:
    from engine.intelligence.quant_market_model import calculate_market_score as _quant_market_score, format_quant_report as _quant_format_report
except ImportError:
    _quant_market_score = None
    format_quant_report = None

try:
    from engine.prediction.bias_score_engine import calculate_market_bias
except ImportError:
    calculate_market_bias = None

from engine.intelligence.whale_flow_analyzer import analyze_whale_flow
from engine.detectors.whale_accumulation_detector import detect_whale_accumulation

try:
    from engine.market_signal import generate_signal as marketdebug_signal
except ImportError:
    marketdebug_signal = None

try:
    from engine.explain.explain_engine import explain_trade_decision
except ImportError:
    explain_trade_decision = None
try:
    from engine.reasoning.why_reason_engine import generate_trade_reasoning
except ImportError:
    generate_trade_reasoning = None

try:
    from engine.alerts.btc_smart_alert import analyze_btc_signal, should_alert_btc
except ImportError:
    analyze_btc_signal = None
    should_alert_btc = None

try:
    from engine.alerts.alert_manager import should_send_alert
except ImportError:
    should_send_alert = None

from engine.alerts import notification_governor as ngov
from engine.monitoring.system_monitor import check_system_health

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
IS_PRIMARY_DISPATCHER = os.getenv("IS_PRIMARY_DISPATCHER", "true").strip().lower() == "true"
DEFAULT_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
_bot_instance = None
_dispatch_semaphore = asyncio.Semaphore(5)
_calendar_reminder_last_sent: dict[str, datetime] = {}
# NOTE: cooldown state for near_support/near_resistance/rsi/big_move/whale/
# volume_spike/breakout/funding used to live in plain in-memory dicts here
# (and in their respective detector modules) — wiped on every process
# restart, which is the root cause documented in NOTIFIKASI_MITIGASI_REPORT.md.
# They are now persisted via engine.alerts.notification_governor (ngov);
# only the cooldown *durations* remain as module constants below.
_WHALE_ALERT_COOLDOWN_SEC = 4 * 3600
_WHALE_MONITOR_COINS = ("BTC", "ETH", "BNB", "SOL", "XRP")
_SNAPSHOT_ALERT_COOLDOWN_SEC = 4 * 3600
ALERT_COIN_BLACKLIST: set[str] = {
    "WLFI",
    "SKY",
    "PIXEL",
}

# Production logging: file + console, avoid duplicate handlers on reload
LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "aliza.log")
os.makedirs(LOG_DIR, exist_ok=True)
SNAPSHOT_MAX_AGE_SEC = int(os.getenv("SNAPSHOT_MAX_AGE_SEC", "300"))

logger = logging.getLogger()
logger.setLevel(logging.INFO)
formatter = logging.Formatter(
    "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
if not logger.handlers:
    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

# Suppress httpx URL logging (mencegah token Telegram muncul di log)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.WARNING)

ALLOWED_COINS = get_tradable_coins() if get_tradable_coins else list(MAJOR_COINS)

# Persistent cache — menyimpan nilai terakhir yang berhasil di-fetch (brief header)
_BRIEF_DATA_CACHE: dict[str, Any] = {
    "cross_asset": None,
    "stablecoin": None,
    "deribit": None,
    "coinbase_premium": None,
    "institutional": None,
    "last_updated": None,
    "last_full_update": None,
}

# Persistent fallback — nilai cross-asset terakhir yang valid
_CROSS_ASSET_LAST_VALID: dict[str, Any] = {}
_BRIEF_DATA_CACHE_LOCK = threading.Lock()
# Timestamp UTC per section saat nilai valid terakhir disimpan (untuk label staleness)
_BRIEF_SECTION_UPDATED_AT: dict[str, datetime | None] = {
    "cross_asset": None,
    "stablecoin": None,
    "deribit": None,
    "coinbase_premium": None,
    "institutional": None,
}


def get_bot() -> Bot:
    global _bot_instance
    if _bot_instance is None:
        if not BOT_TOKEN:
            raise RuntimeError("TELEGRAM_BOT_TOKEN not set")
        _bot_instance = Bot(token=BOT_TOKEN)
    return _bot_instance


async def dispatch_alert_message(message: str, chat_id: int | str | None = None, force: bool = False) -> bool:
    """Centralized Telegram dispatcher (single source of truth)."""
    if not IS_PRIMARY_DISPATCHER:
        logging.info("ALERT DISPATCH SKIPPED (NON-PRIMARY INSTANCE)")
        return False
    with snapshot_state._snapshot_lock:
        cb_active = snapshot_state.CIRCUIT_BREAKER_ACTIVE
    if cb_active and not force:
        logging.critical("ALERT BLOCKED: CIRCUIT BREAKER ACTIVE")
        return False

    bot = get_bot()
    target_chat_id = chat_id or DEFAULT_CHAT_ID
    if not target_chat_id:
        raise RuntimeError("CHAT_ID NOT SET")

    await bot.send_message(chat_id=target_chat_id, text=message)
    logging.info("ALERT DISPATCHED via CENTRAL GATEWAY")
    return True


async def safe_dispatch(message: str, chat_id: int | str | None = None, force: bool = False) -> bool:
    async with _dispatch_semaphore:
        return await dispatch_alert_message(message, chat_id, force=force)


async def _error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logging.error("Telegram error: %s", context.error, exc_info=context.error)
    if update and isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text("Terjadi kesalahan internal. Coba lagi atau cek log.")
        except Exception:
            pass


# ========== START / HELP ==========

def _main_menu_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["📊 Market", "💹 Trading", "📈 Analisis"],
            ["🌍 Makro & Sentimen", "⚙️ Sistem"],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("COMMAND RECEIVED: /start")
    msg = update.effective_message
    if not msg:
        return
    if not _authorized_chat(update):
        await msg.reply_text("⛔ Unauthorized.")
        return
    try:
        if update.effective_chat:
            chat_id = update.effective_chat.id
            # simpan single user (simple mode)
            context.bot_data["chat_id"] = chat_id
            # (OPSIONAL — future multi-user) sederhana: simpan subscriber set
            context.bot_data.setdefault("subscribers", set()).add(chat_id)
        message = (
            "🤖 ALIZA AI TRADING TERMINAL\n"
            "Asisten AI untuk analisis dan trading crypto market.\n"
            "━━━━━━━━━━━━━━\n"
            "📊 Market • 💹 Trading • 📈 Analisis\n"
            "🌍 Makro & Sentimen • ⚙️ Sistem\n"
            "Gunakan tombol menu untuk navigasi."
        )
        await msg.reply_text(message, reply_markup=_main_menu_keyboard())
    except Exception as e:
        logging.error("START ERROR: %s", e)
        await msg.reply_text("Terjadi kesalahan.")


def _market_submenu_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["🌅 Ringkasan Pagi", "🌙 Ringkasan Malam"],
            ["📡 Radar Market", "📡 Radar Pro"],
            ["🌐 Kondisi Global"],
            ["🔔 Monitor Pasar"],
            ["⬅ Kembali"],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def _spot_trading_submenu_keyboard():
    return _trading_submenu_keyboard()


def _futures_trading_submenu_keyboard():
    return _trading_submenu_keyboard()


def _trading_submenu_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["📈 Saran Spot", "🟢 Peluang Spot"],
            ["🔎 Scan Futures", "🔍 Analisis Coin"],
            ["📂 Posisi Aktif", "📈 Buka Posisi"],
            ["📉 Tutup Posisi"],
            ["⬅ Kembali"],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def _analysis_submenu_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["🎯 Konteks Market", "🔮 Prediksi Market"],
            ["📊 Skor Quant", "🔎 Penjelasan AI"],
            ["📊 Performance"],
            ["⬅ Kembali"],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def _macro_submenu_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["🌐 Data Makro", "🔄 Funding Rate & OI"],
            ["📊 CFRA", "📅 Kalender Ekonomi"],
            ["🐋 Monitor Whale"],
            ["⬅ Kembali"],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def _market_monitor_submenu_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["🚨 Cek Breakout", "📊 Cek Volume Spike"],
            ["📍 Levels (S/R)"],
            ["💥 Cek Big Move (snapshot)", "🔵 Cek RSI Ekstrem (snapshot)"],
            ["📌 Snapshot Market"],
            ["⬅ Kembali"],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def _performance_submenu_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["📊 Akurasi Sinyal", "📈 Kinerja Trade (RR/PF)"],
            ["📅 Ringkasan Mingguan", "🧪 Riset Shadow E3"],
            ["⬅ Kembali"],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def _system_submenu_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["⚙️ Status Sistem", "🏥 Health Sistem"],
            ["📊 Alert Stats", "🧪 Test Alert"],
            ["🛠 Debug Market", "🧪 Cek Promosi Shadow"],
            ["⬅ Kembali"],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def _set_menu_parent(context: ContextTypes.DEFAULT_TYPE, parent: str | None) -> None:
    """Remember the active reply-keyboard level so Back can return one level."""
    user_data = getattr(context, "user_data", None)
    if not isinstance(user_data, dict):
        return
    if parent is None:
        user_data.pop("reply_menu_parent", None)
    else:
        user_data["reply_menu_parent"] = parent


def _get_menu_parent(context: ContextTypes.DEFAULT_TYPE) -> str | None:
    user_data = getattr(context, "user_data", None)
    if not isinstance(user_data, dict):
        return None
    value = user_data.get("reply_menu_parent")
    return value if isinstance(value, str) else None


def _build_coin_selector(prefix, coins):
    """Build inline keyboard for coin selection (2 kolom). prefix e.g. 'market', 'entry', 'scan', 'why', 'spot'."""
    buttons = []
    row = []
    for coin in coins:
        row.append(InlineKeyboardButton(coin, callback_data=f"{prefix}_{coin}"))
        if len(row) >= 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)


def _reply_target(update: Update):
    """Pesan yang dipakai untuk reply: dari callback atau dari command."""
    if getattr(update, "callback_query", None) and getattr(update.callback_query, "message", None):
        return update.callback_query.message
    return getattr(update, "message", None)


async def menu_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk tombol menu keyboard; menampilkan submenu atau menjalankan command."""
    if not update.message or not update.message.text:
        return
    text = update.message.text.strip()

    # ⬅ Kembali (legacy: ⬅ Back) → satu level di atas untuk submenu bertingkat.
    if text in ("⬅ Kembali", "⬅ Back"):
        parent = _get_menu_parent(context)
        if parent == "market_monitor":
            _set_menu_parent(context, "market")
            await update.message.reply_text(
                "📊 MARKET",
                reply_markup=_market_submenu_keyboard(),
            )
            return
        if parent == "performance":
            _set_menu_parent(context, "analysis")
            await update.message.reply_text(
                "📈 ANALISIS",
                reply_markup=_analysis_submenu_keyboard(),
            )
            return
        _set_menu_parent(context, None)
        await update.message.reply_text(
            "Pilih menu di bawah.",
            reply_markup=_main_menu_keyboard(),
        )
        return

    # 📊 Market
    if text == "📊 Market":
        _set_menu_parent(context, "market")
        await update.message.reply_text(
            "📊 MARKET\n\n"
            "🌅 Ringkasan Pagi — Ringkasan harian\n"
            "🌙 Ringkasan Malam — Ringkasan sore\n"
            "📡 Radar Market — Trend semua coin\n"
            "📡 Radar Pro — Radar dengan label AI\n"
            "🌐 Kondisi Global — Kondisi market global",
            reply_markup=_market_submenu_keyboard(),
        )
        return
    if text == "🔔 Monitor Pasar":
        _set_menu_parent(context, "market_monitor")
        await update.message.reply_text(
            "🔔 MONITOR PASAR\n\n"
            "Levels, momentum snapshot, breakout, volume spike, dan snapshot market.",
            reply_markup=_market_monitor_submenu_keyboard(),
        )
        return
    if text == "🌅 Ringkasan Pagi":
        await morning_brief_command(update, context)
        return
    if text == "🌙 Ringkasan Malam":
        await evening_summary_command(update, context)
        return
    if text == "📡 Radar Market":
        await radar(update, context)
        return
    if text == "📡 Radar Pro":
        await radarpro_command(update, context)
        return
    if text == "🌐 Kondisi Global":
        await marketstate_command(update, context)
        return
    if text == "📍 Levels (S/R)":
        await levels_command(update, context)
        return
    if text == "💥 Cek Big Move (snapshot)":
        await check_big_move_command(update, context)
        return
    if text == "🔵 Cek RSI Ekstrem (snapshot)":
        await check_rsi_extreme_command(update, context)
        return
    if text == "🚨 Cek Breakout":
        await check_breakout_command(update, context)
        return
    if text == "📊 Cek Volume Spike":
        await check_volume_spike_command(update, context)
        return
    if text == "📌 Snapshot Market":
        await snapshot_command(update, context)
        return

    # 💹 Trading (baru — gabungan Spot + Futures)
    if text == "💹 Trading":
        await update.message.reply_text(
            "💹 TRADING\n\n"
            "📈 Saran Spot — saran swing entry 21 coin (3x/hari)\n"
            "🟢 Peluang Spot — daftar coin BUY\n"
            "🔎 Scan Futures — scan peluang futures\n"
            "🔍 Analisis Coin — analisa per coin\n"
            "📂 Posisi Aktif — posisi terbuka",
            reply_markup=_trading_submenu_keyboard(),
        )
        return
    # Fallback cache lama — redirect ke Trading baru
    if text in ("🟢 Spot Trading", "📊 Futures Trading"):
        await update.message.reply_text(
            "Menu sudah digabung ke 💹 Trading.",
            reply_markup=_trading_submenu_keyboard(),
        )
        return
    # Keyboard cache lama
    if text == "🎯 Sinyal & Trading":
        await update.message.reply_text(
            "Menu dipisah: pilih 💹 Trading di menu utama.",
            reply_markup=_main_menu_keyboard(),
        )
        return
    if text == "📂 Posisi Aktif":
        await portfolio(update, context)
        return
    if text == "🔎 Scan Futures":
        kb = _build_coin_selector("scan", MAJOR_COINS)
        await update.message.reply_text(
            "🔎 SCAN FUTURES\n\nPilih coin untuk melihat peluang futures.",
            reply_markup=kb,
        )
        return
    if text == "🔎 Scan Peluang":
        kb = _build_coin_selector("scan", MAJOR_COINS)
        await update.message.reply_text(
            "🔎 SCAN PELUANG\n\nPilih coin untuk melihat peluang trading.",
            reply_markup=kb,
        )
        return
    if text == "🟢 Peluang Spot":
        await spot_command(update, context)
        return
    if text == "🔍 Analisis Coin":
        kb = _build_coin_selector("spot", MAJOR_COINS)
        await update.message.reply_text(
            "🔍 ANALISIS COIN\n\nPilih coin untuk analisa spot.",
            reply_markup=kb,
        )
        return
    if text == "📈 Buka Posisi":
        kb = _build_coin_selector("entry", ALLOWED_COINS)
        await update.message.reply_text("Pilih coin untuk buka posisi:", reply_markup=kb)
        return
    if text == "📉 Tutup Posisi":
        trades = get_active_trades()
        coins = [t[0] for t in trades] if trades else []
        if not coins:
            await update.message.reply_text("Belum ada posisi aktif.")
            return
        kb = _build_coin_selector("close", coins)
        await update.message.reply_text("Pilih posisi yang akan ditutup:", reply_markup=kb)
        return
    if text == "📂 Portofolio":
        await portfolio(update, context)
        return

    # 📈 Analisis (baru) + fallback cache lama
    if text == "📈 Analisis":
        _set_menu_parent(context, "analysis")
        await update.message.reply_text(
            "📈 ANALISIS\n\n"
            "🎯 Konteks Market — skor kondisi market\n"
            "🔮 Prediksi Market — probabilitas bullish/bearish\n"
            "📊 Skor Quant — market strength score\n"
            "🔎 Penjelasan AI — analisa AI per coin\n"
            "📊 Performance — akurasi sinyal dan kinerja trade",
            reply_markup=_analysis_submenu_keyboard(),
        )
        return
    if text == "📈 Analisis & Skor":
        if update.message:
            await update.message.reply_text(
                "📈 ANALISIS",
                reply_markup=_analysis_submenu_keyboard(),
            )
        return
    if text == "🎯 Konteks Market":
        await market_context_command(update, context)
        return
    if text == "🔮 Prediksi Market":
        await predict(update, context)
        return
    if text == "📊 Skor Quant":
        await quant_command(update, context)
        return
    if text == "🔎 Penjelasan AI":
        kb = _build_coin_selector("why", MAJOR_COINS)
        await update.message.reply_text(
            "🔎 PENJELASAN AI\n\nPilih coin untuk melihat analisa AI.",
            reply_markup=kb,
        )
        return
    if text == "📊 Performance":
        _set_menu_parent(context, "performance")
        await update.message.reply_text(
            "📊 PERFORMANCE\n\n"
            "Akurasi sinyal produksi, kinerja trade, ringkasan mingguan, dan riset Shadow E3.",
            reply_markup=_performance_submenu_keyboard(),
        )
        return
    if text == "📊 Akurasi Sinyal":
        await signal_stats_command(update, context)
        return
    if text == "📈 Kinerja Trade (RR/PF)":
        await performance_command(update, context)
        return
    if text == "📅 Ringkasan Mingguan":
        await weekly_winrate_summary_command(update, context)
        return
    if text == "🧪 Riset Shadow E3":
        await shadow_stats_command(update, context)
        return
    # Label Performance lama untuk keyboard client yang masih ter-cache.
    if text == "📊 Performa Sinyal":
        await signal_stats_command(update, context)
        return
    if text == "📊 Performa Trading":
        await performance_command(update, context)
        return
    if text == "📈 Saran Spot":
        await spot_signal_command(update, context)
        return

    # 🌍 Makro & Sentimen
    if text == "🌍 Makro & Sentimen":
        await update.message.reply_text(
            "🌍 MAKRO & SENTIMEN\n\n"
            "Data makro, funding, kalender ekonomi, dan whale monitor.",
            reply_markup=_macro_submenu_keyboard(),
        )
        return
    if text == "🌐 Data Makro":
        await check_macro_command(update, context)
        return
    if text == "🔄 Funding Rate & OI":
        await check_funding_command(update, context)
        return
    if text == "📊 CFRA":
        await cfra_command(update, context)
        return
    if text == "📅 Kalender Ekonomi":
        await check_calendar_command(update, context)
        return
    if text == "🐋 Monitor Whale":
        await check_whale_command(update, context)
        return

    # ⚙️ Sistem
    if text == "⚙️ Sistem":
        _set_menu_parent(context, "system")
        await update.message.reply_text(
            "⚙️ SISTEM\n\n"
            "Status, health, observability alert, test, debug, dan administrasi riset.",
            reply_markup=_system_submenu_keyboard(),
        )
        return
    if text == "⚙️ Status Sistem":
        await status(update, context)
        return
    if text == "🧪 Test Alert":
        await testalert(update, context)
        return
    if text == "🏥 Health Sistem":
        await health_command(update, context)
        return
    if text == "📊 Alert Stats":
        await alert_stats_command(update, context)
        return
    if text == "🛠 Debug Market":
        await marketdebug(update, context)
        return
    if text == "🧪 Cek Promosi Shadow":
        await shadow_promotion_check_command(update, context)
        return

    # Tombol Sistem lama (keyboard cache) — tetap kompatibel, tetapi tidak lagi aktif.
    if text == "📉 Near Support":
        await check_near_support_command(update, context)
        return
    if text == "📈 Near Resistance":
        await check_near_resistance_command(update, context)
        return
    if text == "🔵 RSI Extreme":
        await check_rsi_extreme_command(update, context)
        return
    if text == "💥 Big Move":
        await check_big_move_command(update, context)
        return

    # Tombol lama (keyboard cache) — tetap dirutekan ke handler yang sama
    if text == "📊 Market Coin":
        kb = _build_coin_selector("market", ALLOWED_COINS)
        await update.message.reply_text("Pilih coin untuk melihat market:", reply_markup=kb)
        return
    if text == "📡 Radar":
        await radar(update, context)
        return
    if text == "🌐 Market State":
        await marketstate_command(update, context)
        return
    if text == "🎯 Trading":
        await update.message.reply_text(
            "🎯 TRADING\n\n"
            "Menu ini sudah dipisah: 🟢 Spot Trading • 📊 Futures Trading",
            reply_markup=_main_menu_keyboard(),
        )
        return
    if text == "🔎 Scan Opportunities":
        kb = _build_coin_selector("scan", MAJOR_COINS)
        await update.message.reply_text(
            "🔎 SCAN PELUANG\n\nPilih coin untuk melihat peluang trading.",
            reply_markup=kb,
        )
        return
    if text == "📈 Open Position":
        kb = _build_coin_selector("entry", ALLOWED_COINS)
        await update.message.reply_text("Pilih coin untuk buka posisi:", reply_markup=kb)
        return
    if text == "📉 Close Position":
        trades = get_active_trades()
        coins = [t[0] for t in trades] if trades else []
        if not coins:
            await update.message.reply_text("Belum ada posisi aktif.")
            return
        kb = _build_coin_selector("close", coins)
        await update.message.reply_text("Pilih posisi yang akan ditutup:", reply_markup=kb)
        return
    if text == "📂 Portfolio":
        await portfolio(update, context)
        return
    if text == "🧠 AI Intelligence":
        await update.message.reply_text(
            "📈 ANALISIS & SKOR\n\n"
            "Menu ini sudah dipindah ke: 📈 Analisis & Skor",
            reply_markup=_analysis_submenu_keyboard(),
        )
        return
    if text == "🔮 Market Prediction":
        await predict(update, context)
        return
    if text == "📊 Quant Score":
        await quant_command(update, context)
        return
    if text == "🔎 Trade Explanation":
        kb = _build_coin_selector("why", MAJOR_COINS)
        await update.message.reply_text(
            "🔎 PENJELASAN AI\n\nPilih coin untuk melihat analisa AI.",
            reply_markup=kb,
        )
        return
    if text == "📈 Analytics":
        await update.message.reply_text(
            "📈 ANALISIS & SKOR\n\n"
            "Menu ini sudah dipindah ke: 📈 Analisis & Skor",
            reply_markup=_analysis_submenu_keyboard(),
        )
        return
    if text == "📊 Trading Performance":
        await performance_command(update, context)
        return
    if text == "⚙️ System":
        await update.message.reply_text(
            "⚙️ SISTEM\n\n"
            "Menu ini sudah dipindah ke: ⚙️ Sistem",
            reply_markup=_system_submenu_keyboard(),
        )
        return
    if text == "⚙️ System Status":
        await status(update, context)
        return
    if text == "🛠 Market Debug":
        await marketdebug(update, context)
        return
    if text == "📊 Spot Opportunities":
        await spot_command(update, context)
        return
    if text == "🔍 Analyze Coin":
        kb = _build_coin_selector("spot", MAJOR_COINS)
        await update.message.reply_text(
            "🔍 ANALISIS COIN\n\nPilih coin untuk analisa spot.",
            reply_markup=kb,
        )
        return


async def coin_selector_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline coin selector: market, entry, close, scan, why, spot."""
    if not update.callback_query or not update.callback_query.data:
        return
    if not _authorized_chat(update):
        await update.callback_query.answer(
            "⛔ Unauthorized.",
            show_alert=True,
        )
        return
    try:
        await update.callback_query.answer()
        data = update.callback_query.data.strip()
        if "_" not in data:
            return
        prefix, symbol = data.split("_", 1)
        symbol = symbol.upper()
        msg = update.callback_query.message

        if prefix == "market":
            text, err = _get_market_report_text(symbol)
            if err:
                await msg.reply_text(err)
            else:
                await msg.reply_text(text)
        elif prefix == "entry":
            context.args = [symbol]
            await entry(update, context)
        elif prefix == "close":
            context.args = [symbol]
            await close(update, context)
        elif prefix == "scan":
            snapshot = get_market_snapshot()
            market_data = snapshot.get("data") or {}
            single = {symbol: market_data[symbol]} if symbol in market_data else {}
            opportunities = scan_opportunities_from_data(single)
            context.bot_data["last_opportunities"] = opportunities
            if not opportunities:
                await msg.reply_text(
                    f"Tidak ada peluang trading untuk {symbol} saat ini.\n\n"
                    f"🕒 Market Snapshot : {get_snapshot_timestamp_str()}"
                )
            else:
                text_msg = format_opportunities_message(opportunities, max_items=5)
                text_msg += f"\n\n🕒 Market Snapshot : {get_snapshot_timestamp_str()}"
                await msg.reply_text(text_msg)
        elif prefix == "why":
            context.args = [symbol]
            await why_command(update, context)
        elif prefix == "spot":
            context.args = [symbol]
            await spot_command(update, context)
    except Exception as e:
        logging.error("Coin selector callback error: %s", e)
        if update.callback_query and update.callback_query.message:
            await update.callback_query.message.reply_text("Terjadi kesalahan.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("COMMAND RECEIVED: /help")
    try:
        msg = (
            "📘 ALIZA COMMAND GUIDE\n\n"
            "📊 Market\n"
            "/market [COIN]\n"
            "Melihat kondisi market coin\n\n"
            "/radar\n"
            "Radar trend semua coin\n\n"
            "/radarpro\n"
            "Radar dengan AI intelligence label\n\n"
            "/marketstate\n"
            "Kondisi global market\n\n"
            "🟢 Spot Trading • 📊 Futures Trading (menu)\n"
            "/setfutures\n"
            "Menampilkan peluang trading terbaik\n\n"
            "/entry\n"
            "Membuka posisi\n\n"
            "/close\n"
            "Menutup posisi\n\n"
            "/portfolio\n"
            "Melihat posisi aktif\n\n"
            "💰 Portfolio & Risk\n"
            "/set_balance <jumlah>\n"
            "Set modal akun (USDT) untuk position sizing\n\n"
            "/balance\n"
            "Lihat ringkasan akun, posisi aktif, dan risk\n\n"
            "🧠 AI Intelligence\n"
            "/predict\n"
            "Prediksi arah market\n\n"
            "/quant\n"
            "Skor kekuatan market\n\n"
            "/why\n"
            "Penjelasan keputusan AI trading\n\n"
            "/spot [COIN]\n"
            "Peluang spot BUY (akumulasi/pullback)\n\n"
            "/btc\n"
            "BTC smart signal (STRONG BUY, ACCUMULATE, HOLD, TAKE PROFIT, RISK ALERT, CRASH WARNING)\n\n"
            "📈 Analytics\n"
            "/performance\n"
            "Kinerja trade (RR/PF)\n\n"
            "/signal_stats\n"
            "Akurasi sinyal produksi (alias: /stats)\n\n"
            "⚙️ System\n"
            "/status\n"
            "Status sistem Aliza\n\n"
            "/testalert\n"
            "Test notifikasi\n\n"
            "/marketdebug\n"
            "Debug data market\n\n"
            "/alert_stats\n"
            "Statistik alert (terkirim/digest/skip/rate-limit)\n\n"
            "/levels [toleransi%]\n"
            "Cek coin dekat support/resistance (default 1%)"
        )
        await update.message.reply_text(msg)
    except Exception as e:
        logging.error("HELP ERROR: %s", e)
        await update.message.reply_text("Terjadi kesalahan.")


# ========== SPOT (Spot opportunity) ==========

async def spot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Daftar peluang spot BUY atau detail per coin. /spot atau /spot BTC."""
    logging.info("COMMAND RECEIVED: /spot")
    target = _reply_target(update)
    if not target:
        return
    try:
        snapshot = get_market_snapshot()
        data = snapshot.get("data") or {}
        symbol_arg = (context.args[0].upper().strip() if context.args else "").strip()

        if symbol_arg:
            # Detail view: /spot BTC
            symbol = symbol_arg
            if symbol not in data:
                await target.reply_text(f"Data tidak tersedia untuk {symbol}.")
                return
            md = data[symbol]
            spot = md.get("spot_signal")
            if not spot or not isinstance(spot, dict):
                msg = (
                    f"🟢 SPOT ANALYSIS\n\n{symbol}\n\n"
                    "Signal     : WAIT\n"
                    "Type       : —\n"
                    "Confidence : 0\n\n"
                    "Reason:\nBelum ada sinyal spot."
                )
            else:
                sig = spot.get("signal", "WAIT")
                typ = spot.get("type") or "—"
                conf = spot.get("confidence", 0)
                reason = spot.get("reason", "—")

                price = md.get("price")
                rsi = md.get("rsi")
                trend = md.get("trend") or "—"
                support = md.get("support")
                resistance = md.get("resistance")

                def _fmt(v, prefix="$"):
                    if v is None:
                        return "—"
                    try:
                        f = float(v)
                        if f == 0:
                            return f"{prefix}0"
                        abs_f = abs(f)
                        if abs_f >= 1000:
                            return f"{prefix}{f:,.2f}"
                        elif abs_f >= 1:
                            return f"{prefix}{f:,.4f}"
                        elif abs_f >= 0.01:
                            return f"{prefix}{f:.4f}"
                        elif abs_f >= 0.000001:
                            return f"{prefix}{f:.8f}"
                        else:
                            return f"{prefix}{f:.10f}"
                    except (TypeError, ValueError):
                        return "—"

                entry_str = _fmt(support) if support else "—"
                sl_val = round(support * 0.96, 8) if support else None
                sl_str = _fmt(sl_val)
                sl_pct = "4.0%" if support else "—"
                target_str = _fmt(resistance) if resistance else "—"

                if support and sl_val and resistance:
                    try:
                        rr = (resistance - support) / (support - sl_val)
                        rr_str = f"{rr:.1f}x"
                    except ZeroDivisionError:
                        rr_str = "—"
                else:
                    rr_str = "—"

                rsi_str = f"{float(rsi):.1f}" if rsi is not None else "—"
                price_str = _fmt(price)

                msg = (
                    f"🟢 SPOT ANALYSIS — {symbol}\n"
                    f"Signal     : {sig} ({typ})\n"
                    f"Confidence : {conf}/100\n\n"
                    f"Harga      : {price_str}\n"
                    f"RSI        : {rsi_str} | Trend: {trend}\n"
                    f"Support    : {_fmt(support)} | Resistance: {_fmt(resistance)}\n\n"
                    f"Entry ideal: {entry_str} (di support)\n"
                    f"SL         : {sl_str} ({sl_pct} dari entry)\n"
                    f"Target     : {target_str} (resistance)\n"
                    f"RR         : {rr_str}\n\n"
                    f"Reason: {reason}"
                )
            msg += f"\n\n🕒 Market Snapshot : {get_snapshot_timestamp_str()}"
            await target.reply_text(msg)
            return

        # List view: hanya coin dengan signal BUY + inline selector untuk detail
        buy_list = []
        for sym, md in data.items():
            spot = md.get("spot_signal") if isinstance(md, dict) else None
            if spot and isinstance(spot, dict) and spot.get("signal") == "BUY":
                typ = spot.get("type") or "BUY"
                buy_list.append((sym, typ))
        if not buy_list:
            await target.reply_text("Tidak ada peluang spot saat ini.")
            return
        lines = ["🟢 ALIZA SPOT OPPORTUNITIES\n"]
        for sym, typ in buy_list:
            lines.append(f"{sym} → BUY ({typ})")
        lines.append(f"\n🕒 Market Snapshot : {get_snapshot_timestamp_str()}")
        lines.append("\nPilih coin untuk melihat detail 👇")
        buy_coins = [sym for sym, _ in buy_list]
        kb = _build_coin_selector("spot", buy_coins)
        await target.reply_text("\n".join(lines), reply_markup=kb)
    except Exception as e:
        logging.error("SPOT ERROR: %s", e)
        if target:
            await target.reply_text("Terjadi kesalahan.")


# ========== WHY (Trade decision explanation) ==========

async def why_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Explain why Aliza did or did not give a trade for the coin."""
    logging.info("COMMAND RECEIVED: /why")
    target = _reply_target(update)
    if not target:
        return
    try:
        symbol = (context.args[0].upper() if context.args else "BTC").strip()
        snapshot = get_market_snapshot()
        data = snapshot.get("data") or {}
        if symbol not in data:
            await target.reply_text("Market data tidak tersedia untuk coin ini.")
            return
        market_data = data[symbol]
        trade_setup = market_data.get("trade_setup") or {}

        if generate_trade_reasoning is not None:
            reason = generate_trade_reasoning(market_data, trade_setup)
        else:
            reason = None

        if explain_trade_decision is not None:
            out = explain_trade_decision(symbol, snapshot)
        else:
            out = None
        if not out and reason is None:
            await target.reply_text("Market data tidak tersedia untuk coin ini.")
            return

        def _fmt(v):
            if v is None:
                return "—"
            if isinstance(v, float):
                return round(v, 2) if v == v else "—"
            return str(v)

        trend_str = _fmt(out.get("trend")) if out else _fmt(market_data.get("trend"))
        rsi_str = _fmt(out.get("rsi")) if out else _fmt(market_data.get("rsi"))
        alignment_str = _fmt(out.get("alignment")) if out else _fmt(market_data.get("trend_alignment"))
        setup_raw = out.get("setup") if out else trade_setup.get("setup")
        setup_display = "NONE" if (not setup_raw or str(setup_raw).strip().upper() in ("NO SETUP", "NO DATA", "")) else str(setup_raw).strip().upper()

        message = (
            "🔎 ALIZA TRADE ANALYSIS\n\n"
            f"{out.get('symbol', symbol) if out else symbol}\n\n"
            f"Trend        : {trend_str}\n"
            f"RSI          : {rsi_str}\n"
            f"Alignment    : {alignment_str}\n\n"
            f"Setup        : {setup_display}\n\n"
        )

        if reason is not None:
            is_valid = reason.get("decision") == "TAKE"
            if is_valid:
                message += "✅ Entry Valid\n\n"
            else:
                message += "❌ Entry Tidak Valid\n\n"
            message += "Alasan:\n"
            for r in reason.get("reasons") or []:
                if isinstance(r, dict):
                    level = r.get("level", "")
                    text = r.get("text", "")
                    icon = "🔴" if level == "CRITICAL" else "🟡"
                    message += f"{icon} {text}\n"
                else:
                    message += f"• {r}\n"
            message += f"\n📊 Market Context : {reason.get('context', '—')}\n"
            message += f"📊 Confidence     : {reason.get('confidence_zone', '—')}\n\n"
            message += f"📊 Insight:\n{reason.get('insight', '—')}\n\n"
            triggers = reason.get("triggers") or []
            message += "📍 Trigger berikutnya:\n"
            for t in triggers:
                message += f"• {t}\n"
            message += f"\n📌 Saran:\n{reason.get('suggestion', '—')}\n\n"
        else:
            decision = "SKIPPED" if (setup_display == "NONE") else "TRADE AVAILABLE"
            message += f"Decision     : {decision}\n"
            message += f"Reason       : {out.get('reason', '—') if out else '—'}\n\n"

        message += f"🕒 Market Snapshot : {get_snapshot_timestamp_str()}"
        await target.reply_text(message)
    except Exception as e:
        logging.error("WHY ERROR: %s", e)
        if target:
            await target.reply_text("Terjadi kesalahan.")


# ========== MARKET ==========

def _get_market_report_text(symbol):
    """Return (message_text, None) or (None, error_message) for market report."""
    snapshot = get_market_snapshot()
    data = snapshot.get("data") or {}
    if not data:
        return None, "Market snapshot belum tersedia. Tunggu beberapa saat."
    symbol = (symbol or "BTC").upper()
    if symbol not in ALLOWED_COINS:
        return None, "Coin tidak tersedia."
    if symbol not in data:
        return None, f"Market data tidak tersedia untuk {symbol}."
    market = data[symbol]
    price = market.get("price")
    trend = market.get("trend")
    rsi = market.get("rsi")
    support = market.get("support")
    resistance = market.get("resistance")
    trend_4h = market.get("trend_4h")
    trend_1d = market.get("trend_1d")
    alignment = market.get("trend_alignment")

    def _fmt(v):
        if v is None:
            return "—"
        if isinstance(v, float):
            return round(v, 2) if v == v else "—"
        return str(v)

    message = (
        f"📊 {symbol} MARKET STATUS\n\n"
        f"Price      : {_fmt(price)}\n"
        f"Trend      : {_fmt(trend)}\n"
        f"RSI        : {_fmt(rsi)}\n\n"
        f"4H Trend   : {_fmt(trend_4h)}\n"
        f"1D Trend   : {_fmt(trend_1d)}\n"
        f"Alignment  : {_fmt(alignment)}\n\n"
        f"Support    : {_fmt(support)}\n"
        f"Resistance : {_fmt(resistance)}\n\n"
        f"🕒 Market Snapshot : {get_snapshot_timestamp_str()}"
    )
    return message, None


async def market(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("COMMAND RECEIVED: /market")
    try:
        symbol = (context.args[0].upper() if context.args else "BTC")
        msg, err = _get_market_report_text(symbol)
        if err:
            await update.message.reply_text(err)
            return
        await update.message.reply_text(msg)
    except Exception as e:
        logging.error("MARKET ERROR: %s", e)
        await update.message.reply_text("Terjadi kesalahan membaca market.")


# ========== RADAR ==========

def _format_alignment_label(alignment):
    """Map trend_alignment to display label for /radar."""
    a = (alignment or "UNKNOWN").upper().strip()
    if a == "STRONG_BULLISH":
        return "STRONG_BULLISH 🔥"
    if a == "STRONG_BEARISH":
        return "STRONG_BEARISH ❄️"
    if a == "BULLISH":
        return "BULLISH ↑"
    if a == "BEARISH":
        return "BEARISH ↓"
    if a == "MIXED":
        return "MIXED ⚠️"
    if a == "PARTIAL":
        return "PARTIAL"
    return "UNKNOWN"


async def radar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("COMMAND RECEIVED: /radar")
    try:
        radar_data = generate_radar_pro()
        if not radar_data:
            await update.message.reply_text("Radar market tidak tersedia.")
            return
        lines = ["📡 ALIZA MARKET RADAR\n"]
        for item in radar_data:
            coin = item.get("coin", "")
            alignment = item.get("trend_alignment", "UNKNOWN")
            label = _format_alignment_label(alignment)
            lines.append(f"{coin} → {label}")
        lines.append(f"\n🕒 Market Snapshot : {get_snapshot_timestamp_str()}")
        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        logging.error("RADAR ERROR: %s", e)
        await update.message.reply_text("Terjadi kesalahan scan market.")


async def radarpro_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("COMMAND RECEIVED: /radarpro")
    try:
        radar = generate_radar_pro()
        message = format_radar_pro_report(radar)
        await update.message.reply_text(message)
    except Exception as e:
        logging.error("RADARPRO ERROR: %s", e)
        await update.message.reply_text("Terjadi kesalahan memuat radar pro.")


# ========== SETFUTURES ==========

async def setfutures(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("COMMAND RECEIVED: /setfutures")
    try:
        opportunities = scan_opportunities()
        context.bot_data["last_opportunities"] = opportunities
        message = format_opportunities_message(opportunities, max_items=3)
        message += f"\n\n🕒 Market Snapshot : {get_snapshot_timestamp_str()}"
        await update.message.reply_text(message)
    except Exception as e:
        logging.error("SETFUTURES ERROR: %s", e)
        await update.message.reply_text("Terjadi kesalahan futures scanner.")


# ========== ENTRY ==========

async def entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("COMMAND RECEIVED: /entry")
    msg = update.effective_message
    if not msg:
        return
    if not _authorized_chat(update):
        await msg.reply_text("⛔ Unauthorized.")
        return
    try:
        if not context.args:
            await msg.reply_text("Gunakan: /entry BNB atau /entry 1")
            return
        arg = context.args[0].strip()
        last_opportunities = context.bot_data.get("last_opportunities") or []
        if arg.isdigit():
            n = int(arg)
            if n < 1 or n > len(last_opportunities):
                await msg.reply_text("Nomor tidak valid. Jalankan /setfutures dulu.")
                return
            opp = last_opportunities[n - 1]
            coin = (opp.get("coin") or "").upper()
        else:
            coin = arg.upper()
        if coin not in ALLOWED_COINS:
            await msg.reply_text("Coin tidak tersedia.")
            return
        setup = entry_price = sl = tp1 = tp2 = None
        for opp in last_opportunities:
            if (opp.get("coin") or "").upper() == coin:
                setup = opp.get("setup")
                entry_price = opp.get("entry")
                sl = opp.get("sl")
                tp1 = opp.get("tp1")
                tp2 = opp.get("tp2")
                break
        if setup is None or entry_price is None:
            snapshot = get_market_snapshot()
            data = (snapshot.get("data") or {}).get(coin)
            if not data or data.get("error"):
                await msg.reply_text("Data market tidak tersedia.")
                return
            trade_setup = data.get("trade_setup")
            if not trade_setup or trade_setup.get("setup") in (None, "NO SETUP", "NO DATA"):
                await msg.reply_text("Tidak ada setup untuk coin ini. Jalankan /setfutures dulu.")
                return
            setup = trade_setup.get("setup")
            entry_price = trade_setup.get("entry")
            sl = trade_setup.get("sl")
            tp1 = trade_setup.get("tp1")
            tp2 = trade_setup.get("tp2")
        if not setup or entry_price is None:
            await msg.reply_text("Tidak ada setup. Jalankan /setfutures dulu.")
            return
        if portfolio_evaluate_trade is not None:
            eval_setup = {"entry": entry_price, "sl": sl}
            eval_result = portfolio_evaluate_trade(eval_setup)
            if not eval_result.get("allowed", True):
                await msg.reply_text(
                    f"Trade ditolak: {eval_result.get('reason', 'Portfolio AI')}"
                )
                return
            position_size = eval_result.get("position_size")
        else:
            position_size = None

        quantity = None
        position_value_usdt = None
        risk_usdt_val = None
        try:
            from engine.position_sizer import (
                calculate_position_size,
                get_account_balance,
                get_current_open_risk,
            )

            bal = get_account_balance()
            if bal > 0 and entry_price is not None and sl is not None:
                active_tr = get_active_trades() or []
                cur_risk = get_current_open_risk(active_tr, bal)
                sr = calculate_position_size(
                    entry_price=float(entry_price),
                    stop_loss=float(sl),
                    account_balance=bal,
                    current_open_risk_usdt=cur_risk,
                )
                if sr is not None:
                    quantity = float(sr.size_units)
                    position_value_usdt = float(sr.size_usdt)
                    risk_usdt_val = float(sr.risk_amount_usdt)
        except Exception as e:
            logging.debug("entry position sizing: %s", e)

        create_trade(
            coin,
            setup,
            entry_price,
            sl,
            tp1,
            tp2,
            quantity=quantity,
            position_value_usdt=position_value_usdt,
            risk_usdt=risk_usdt_val,
        )
        message = (
            f"TRADE DITAMBAHKAN\n\n{coin} {setup}\n"
            f"Entry : {entry_price}\nSL : {sl}\nTP1 : {tp1}\nTP2 : {tp2}"
        )
        if quantity is not None and quantity > 0:
            message += (
                f"\n\nUkuran posisi (estimasi): {quantity:.6f} "
                f"(~{position_value_usdt:,.0f} USDT, risk ~{risk_usdt_val:,.0f} USDT)"
            )
        elif position_size is not None and position_size > 0:
            message += f"\n\nUkuran posisi (saran portfolio): {round(position_size, 6)}"
        await msg.reply_text(message)
    except Exception as e:
        logging.error("ENTRY ERROR: %s", e)
        await msg.reply_text("Terjadi kesalahan saat membuka posisi.")


def _authorized_chat(update: Update) -> bool:
    """
    Fail closed jika TELEGRAM_CHAT_ID tidak tersedia; bila tersedia, hanya izinkan
    chat_id yang cocok.
    """
    allowed = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    if not allowed:
        logging.error("TELEGRAM_CHAT_ID is not configured; denying request.")
        return False
    chat_id = update.effective_chat.id if update.effective_chat else None
    return str(chat_id) == str(allowed)


async def _authorization_gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Stop unauthorized incoming Telegram updates before business handlers run."""
    try:
        authorized = update.effective_chat is not None and _authorized_chat(update)
    except Exception:
        logging.exception("Telegram authorization check failed; denying request.")
        authorized = False

    if authorized:
        return

    try:
        if update.callback_query is not None:
            await update.callback_query.answer(
                "⛔ Unauthorized.",
                show_alert=True,
            )
        elif update.effective_message is not None:
            await update.effective_message.reply_text("⛔ Unauthorized.")
    finally:
        raise ApplicationHandlerStop


async def cmd_set_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /set_balance — Set account balance atau mode Binance auto-sync.
    """
    logging.info("COMMAND RECEIVED: /set_balance")
    msg = update.effective_message
    if not msg:
        return
    if not _authorized_chat(update):
        await msg.reply_text("⛔ Unauthorized.")
        return

    try:
        from engine.user_config import (
            get_balance,
            get_balance_source_label,
            is_auto_balance_enabled,
            set_config,
        )
        from engine.position_sizer import DEFAULT_RISK_PER_TRADE, DEFAULT_MAX_TOTAL_RISK
    except Exception as e:
        logging.error("set_balance import: %s", e)
        await msg.reply_text("Konfigurasi balance tidak tersedia.")
        return

    if not context.args:
        current = get_balance()
        label = get_balance_source_label()
        auto_on = is_auto_balance_enabled()
        await msg.reply_text(
            f"💰 Balance: {current:,.0f} USDT\n"
            f"Sumber: {label}\n"
            f"Auto-sync Binance: {'ON' if auto_on else 'OFF'}\n\n"
            f"Opsi:\n"
            f"/set_balance <jumlah> — set manual (nonaktifkan auto)\n"
            f"/set_balance auto — aktifkan Binance sync\n"
            f"/set_balance auto off — matikan auto, pakai manual / .env"
        )
        return

    if context.args[0].lower() == "auto":
        if len(context.args) > 1 and context.args[1].lower() == "off":
            set_config("auto_balance", "false")
            await msg.reply_text(
                "🔒 Auto-sync OFF. Pakai balance manual (DB) atau .env."
            )
            return
        set_config("auto_balance", "true")
        set_config("account_balance", "0")
        try:
            from engine.binance_balance import fetch_spot_balance

            bal = fetch_spot_balance("USDT")
            if bal > 0:
                await msg.reply_text(
                    f"🔄 Auto-sync ON — Binance balance: {bal:,.0f} USDT\n"
                    f"Cache sinkron ~{int(os.getenv('BINANCE_BALANCE_CACHE_SEC', '300'))} detik."
                )
            else:
                await msg.reply_text(
                    "🔄 Auto-sync ON — Binance = 0 USDT atau API key tidak diset.\n"
                    "Isi BINANCE_API_KEY / BINANCE_API_SECRET (permission: Enable Reading)."
                )
        except Exception as e:
            logging.warning("set_balance auto: %s", e)
            await msg.reply_text(
                "🔄 Auto-sync ON tetapi gagal fetch Binance — cek .env dan log server."
            )
        return

    raw = context.args[0].replace(",", "")
    try:
        amount = float(raw)
    except ValueError:
        await msg.reply_text("❌ Format salah. Contoh: /set_balance 10000")
        return

    if amount <= 0:
        await msg.reply_text("❌ Balance harus lebih dari 0.")
        return

    if amount > 10_000_000:
        await msg.reply_text(
            "⚠️ Angka terlalu besar. Yakin? Gunakan nilai lebih kecil atau set via .env."
        )
        return

    try:
        set_config("auto_balance", "false")
        success = set_config("account_balance", str(amount))
    except Exception as e:
        logging.error("set_balance: %s", e)
        success = False

    if success:
        risk_per_trade = amount * DEFAULT_RISK_PER_TRADE
        max_total_risk = amount * DEFAULT_MAX_TOTAL_RISK
        await msg.reply_text(
            f"✅ Balance manual: {amount:,.0f} USDT (auto-sync OFF)\n\n"
            f"📊 Risk parameters:\n"
            f"• Risk per trade: {risk_per_trade:,.0f} USDT ({DEFAULT_RISK_PER_TRADE*100:.0f}%)\n"
            f"• Max total risk: {max_total_risk:,.0f} USDT ({DEFAULT_MAX_TOTAL_RISK*100:.0f}%)\n\n"
            f"Sinyal berikutnya akan menyertakan position sizing."
        )
    else:
        await msg.reply_text("❌ Gagal menyimpan. Cek log server.")


async def cmd_get_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/balance — Lihat balance dan risk summary."""
    logging.info("COMMAND RECEIVED: /balance")
    msg = update.effective_message
    if not msg:
        return
    if not _authorized_chat(update):
        await msg.reply_text("⛔ Unauthorized.")
        return

    try:
        from engine.user_config import get_balance, get_balance_source_label
        from engine.position_sizer import (
            DEFAULT_RISK_PER_TRADE,
            DEFAULT_MAX_TOTAL_RISK,
            get_current_open_risk,
        )

        balance = get_balance()
        src = get_balance_source_label()
    except Exception as e:
        logging.error("get_balance: %s", e)
        await msg.reply_text("Tidak bisa membaca balance.")
        return

    if balance <= 0:
        await msg.reply_text(
            "💰 Balance belum di-set.\n"
            "Set manual: /set_balance <jumlah> atau /set_balance auto (Binance)."
        )
        return

    active = get_active_trades() or []
    current_risk = get_current_open_risk(active, balance)
    max_risk = balance * DEFAULT_MAX_TOTAL_RISK
    remaining = max_risk - current_risk

    await msg.reply_text(
        f"💰 Account Summary\n"
        f"{'─' * 25}\n"
        f"Balance: {balance:,.0f} USDT\n"
        f"Sumber: {src}\n"
        f"Posisi aktif: {len(active)}/3\n"
        f"Risk terpakai: {current_risk:,.0f} / {max_risk:,.0f} USDT\n"
        f"Risk tersisa: {remaining:,.0f} USDT\n"
        f"{'─' * 25}\n"
        f"Risk/trade: {DEFAULT_RISK_PER_TRADE*100:.0f}% | "
        f"Max risk: {DEFAULT_MAX_TOTAL_RISK*100:.0f}%"
    )


# ========== CLOSE ==========

async def close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("COMMAND RECEIVED: /close")
    msg = update.effective_message
    if not msg:
        return
    if not _authorized_chat(update):
        await msg.reply_text("⛔ Unauthorized.")
        return
    try:
        if not context.args:
            await msg.reply_text("Gunakan: /close BNB")
            return
        coin = context.args[0].upper()
        closed = close_trade(coin)
        if closed:
            await msg.reply_text(f"📤 POSISI DITUTUP\n\n{coin} telah ditutup.")
        else:
            await msg.reply_text(f"Tidak ada posisi terbuka untuk {coin}.")
    except Exception as e:
        logging.error("CLOSE ERROR: %s", e)
        await msg.reply_text("Terjadi kesalahan saat menutup posisi.")


# ========== PORTFOLIO ==========

async def portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("COMMAND RECEIVED: /portfolio")
    try:
        trades = get_active_trades()
        if not trades:
            await update.message.reply_text("Belum ada posisi aktif.")
            return
        snapshot = get_market_snapshot()
        data_map = snapshot.get("data") or {}
        lines = ["💼 PORTFOLIO AKTIF\n"]
        for t in trades:
            coin = t[0]
            direction = trade_direction(t)
            setup = t[2]
            entry = t[3]
            sl = t[4]
            tp1 = t[5]
            tp2 = t[6]
            price = None
            if isinstance(data_map.get(coin), dict):
                price = data_map.get(coin).get("price")
            pnl = None
            if price is not None and entry and entry != 0:
                if direction == "LONG":
                    pnl = ((price - entry) / entry) * 100
                else:
                    pnl = ((entry - price) / entry) * 100
            pnl_s = f"{round(pnl, 2)}%" if pnl is not None else "—"
            lines.append(f"{coin} {direction} | Entry {entry} | Price {price} | PnL {pnl_s}")
            lines.append(f"  SL {sl} | TP1 {tp1} | TP2 {tp2}\n")
        lines.append(f"🕒 Market Snapshot : {get_snapshot_timestamp_str()}")
        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        logging.error("PORTFOLIO ERROR: %s", e)
        await update.message.reply_text("Terjadi kesalahan memuat portfolio.")


# ========== PERFORMANCE ==========

async def performance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("COMMAND RECEIVED: /performance")
    try:
        if get_closed_history is None or analyze_performance is None:
            await update.message.reply_text("Modul analytics belum tersedia.")
            return
        closed = get_closed_history()
        perf = analyze_performance(closed)
        total = perf.get("total_trades", 0)
        wins = perf.get("wins", 0)
        losses = perf.get("losses", 0)
        winrate = perf.get("winrate", 0.0)
        avg_rr = perf.get("avg_rr", 0.0)
        pf = perf.get("profit_factor", 0.0)
        winrate_pct = f"{winrate * 100:.1f}%" if total > 0 else "0%"
        message = (
            "📊 ALIZA PERFORMANCE REPORT\n\n"
            f"Total Trades : {total}\n"
            f"Wins : {wins}\n"
            f"Losses : {losses}\n\n"
            f"Winrate : {winrate_pct}\n"
            f"Average RR : {avg_rr}\n"
            f"Profit Factor : {pf}"
        )
        await update.message.reply_text(message)
    except Exception as e:
        logging.error("PERFORMANCE ERROR: %s", e)
        await update.message.reply_text("Terjadi kesalahan memuat performance report.")


# ========== PREDICT ==========

async def predict(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("COMMAND RECEIVED: /predict")
    try:
        snapshot = get_market_snapshot()
        if generate_market_prediction is not None:
            prediction = generate_market_prediction(snapshot)
            bull_p = prediction.get("bullish_probability", 50)
            bear_p = prediction.get("bearish_probability", 50)
            bias = prediction.get("bias", "NEUTRAL")
            confidence = prediction.get("confidence", "LOW")
            message = (
                "🧠 ALIZA MARKET PREDICTION\n\n"
                f"Bullish Probability : {bull_p}%\n"
                f"Bearish Probability : {bear_p}%\n\n"
                f"Short-term Bias : {bias}\n"
                f"Confidence : {confidence}"
            )
        elif predict_market and format_prediction_report:
            btc = (snapshot.get("data") or {}).get("BTC")
            pred = predict_market(btc)
            message = format_prediction_report(pred)
        else:
            await update.message.reply_text("Modul prediksi belum tersedia.")
            return
        message += f"\n\n🕒 Market Snapshot : {get_snapshot_timestamp_str()}"
        await update.message.reply_text(message)
    except Exception as e:
        logging.error("PREDICT ERROR: %s", e)
        await update.message.reply_text("Terjadi kesalahan memuat prediksi.")


# ========== QUANT ==========

async def quant_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("COMMAND RECEIVED: /quant")
    try:
        if calculate_market_bias is None:
            if _quant_market_score and format_quant_report:
                snapshot = get_market_snapshot()
                btc = (snapshot.get("data") or {}).get("BTC")
                result = _quant_market_score(btc_data=btc)
                message = format_quant_report(result)
                message += f"\n\n🕒 Market Snapshot : {get_snapshot_timestamp_str()}"
                await update.message.reply_text(message)
                return
            await update.message.reply_text("Modul quant belum tersedia.")
            return
        snapshot = get_market_snapshot()
        scores = calculate_market_bias(snapshot)
        bullish_score = scores.get("bullish_score", 0)
        bearish_score = scores.get("bearish_score", 0)
        bias = "BULLISH" if bullish_score > bearish_score else "BEARISH"
        total = bullish_score + bearish_score
        if total == 0:
            strength = "WEAK"
        else:
            ratio = bullish_score / total
            if ratio > 0.7:
                strength = "STRONG"
            elif ratio > 0.55:
                strength = "MEDIUM"
            else:
                strength = "WEAK"
        mi = snapshot.get("market_intelligence") or {}
        market_regime = mi.get("market_regime") or "—"
        whale_pressure = mi.get("whale_pressure") or "—"
        altseason_probability = mi.get("altseason_probability")
        alt_pct = f"{altseason_probability}%" if altseason_probability is not None else "—"
        btc_data = (snapshot.get("data") or {}).get("BTC") or {}
        trend = btc_data.get("trend") or "—"
        rsi = btc_data.get("rsi")
        rsi_str = str(int(rsi)) if rsi is not None else "—"
        message = (
            "🧠 ALIZA QUANT MARKET SCORE\n\n"
            f"Bullish Score : {bullish_score}\n"
            f"Bearish Score : {bearish_score}\n\n"
            f"Market Bias : {bias}\n"
            f"Market Strength : {strength}\n\n"
            "Signals\n"
            f"Trend : {trend}\n"
            f"RSI : {rsi_str}\n"
            f"Market Regime : {market_regime}\n"
            f"Whale Pressure : {whale_pressure}\n"
            f"Altseason Prob : {alt_pct}"
        )
        message += f"\n\n🕒 Market Snapshot : {get_snapshot_timestamp_str()}"
        await update.message.reply_text(message)
    except Exception as e:
        logging.error("QUANT ERROR: %s", e)
        await update.message.reply_text("Terjadi kesalahan memuat quant model.")


# ========== MARKETSTATE ==========

async def marketstate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("COMMAND RECEIVED: /marketstate")
    try:
        snapshot = get_market_snapshot()
        intel = analyze_market_environment(snapshot)
        phase = intel.get("market_phase")
        trend = intel.get("btc_trend")
        rsi = intel.get("btc_rsi")
        crash = intel.get("crash_warning")

        def _v(v):
            return v if v is not None else "—"

        message = (
            "🧠 ALIZA MARKET STATE\n\n"
            f"BTC Trend      : {_v(trend)}\n"
            f"BTC RSI        : {_v(rsi)}\n\n"
            f"Market Phase   : {_v(phase)}\n"
            f"Crash Warning  : {'YES' if crash else 'NO'}"
        )
        await update.message.reply_text(message)
    except Exception as e:
        logging.error("MARKETSTATE ERROR: %s", e)
        await update.message.reply_text("Terjadi kesalahan memuat market state.")


# ========== STATUS ==========

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("COMMAND RECEIVED: /status")
    try:
        trades = get_active_trades()
        n_trades = len(trades)
        n_coins = len(ALLOWED_COINS)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        msg = (
            "⚙️ ALIZA SYSTEM STATUS\n\n"
            "Engine    : AKTIF\n"
            "Bot       : AKTIF\n\n"
            f"Posisi aktif : {n_trades}\n"
            f"Coins pantau : {n_coins}\n\n"
            f"Server time  : {now}"
        )
        await update.message.reply_text(msg)
    except Exception as e:
        logging.error("STATUS ERROR: %s", e)
        await update.message.reply_text("Gagal memuat status.")


# ========== ALERT STATS ==========

async def alert_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Observability untuk mitigasi spam notifikasi: alert terkirim/di-digest/
    di-skip(stale)/kena rate-limit per jenis, sejak proses ini terakhir start."""
    logging.info("COMMAND RECEIVED: /alert_stats")
    try:
        stats = ngov.get_stats_snapshot()
        rl = stats.pop("_rate_limit", {})
        lines = ["📊 ALERT STATS (sejak proses terakhir start)", ""]
        if not stats:
            lines.append("Belum ada alert yang diproses pada proses ini.")
        else:
            for alert_type in sorted(stats.keys()):
                s = stats[alert_type]
                sent_individual = s.get("sent_individual", 0)
                sent_digested = s.get("sent_digested", 0)
                skipped_stale = s.get("skipped_stale", 0)
                lines.append(
                    f"• {alert_type}: terkirim={sent_individual} | "
                    f"di-digest={sent_digested} | skip(stale)={skipped_stale}"
                )
        lines.append("")
        lines.append(
            f"⏳ Rate limit jam ini: {rl.get('sent_this_hour', 0)}/{rl.get('max_per_hour', ngov.MAX_ALERTS_PER_HOUR)} "
            f"terkirim, {rl.get('suppressed_this_hour', 0)} tersaring"
        )
        lines.append(f"🔢 Pending di buffer digest: {ngov.pending_count()}")
        lines.append(
            f"⚙️ Threshold digest: {ngov.ALERT_DIGEST_THRESHOLD} | "
            f"Cooldown big move: {ngov.BIG_MOVE_COOLDOWN_SEC}s | "
            f"Snapshot max age: {ngov.SNAPSHOT_MAX_AGE_SEC}s"
        )
        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        logging.error("ALERT_STATS ERROR: %s", e, exc_info=True)
        await update.message.reply_text("Gagal memuat alert stats.")


# ========== TESTALERT ==========

async def testalert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("COMMAND RECEIVED: /testalert")
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await update.message.reply_text(
            "🚨 TEST ALERT\n\nNotifikasi berfungsi.\n\n" + f"Server time: {now}"
        )
    except Exception as e:
        logging.error("TESTALERT ERROR: %s", e)
        await update.message.reply_text("Gagal mengirim test alert.")


# ========== MARKETDEBUG ==========

async def marketdebug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("COMMAND RECEIVED: /marketdebug")
    try:
        if marketdebug_signal:
            data = marketdebug_signal("BTC")
        else:
            snapshot = get_market_snapshot()
            data = (snapshot.get("data") or {}).get("BTC") or {}
        if not data:
            await update.message.reply_text("Market data tidak tersedia.")
            return
        def _f(v):
            if v is None:
                return "—"
            if isinstance(v, float):
                return round(v, 2)
            return str(v)
        msg = (
            "📊 MARKET DEBUG (BTC)\n\n"
            f"Price : {_f(data.get('price'))}\n"
            f"Trend : {_f(data.get('trend'))}\n"
            f"RSI   : {_f(data.get('rsi'))}\n"
            f"Support : {_f(data.get('support'))}\n"
            f"Resistance : {_f(data.get('resistance'))}\n"
            f"Market Risk : {_f(data.get('market_risk_score'))}"
        )
        await update.message.reply_text(msg)
    except Exception as e:
        logging.error("MARKETDEBUG ERROR: %s", e)
        await update.message.reply_text("Market debug error: " + str(e))


async def market_context_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("COMMAND RECEIVED: /market_context")
    target = update.effective_message
    if not target:
        return
    try:
        result = calculate_market_score()
        c = result.get("components", {})
        fg = c.get("fear_greed") or {}
        dom = c.get("btc_dominance") or {}
        fr = c.get("funding_rate") or {}
        macro = c.get("macro") or {}
        tech = c.get("technical") or {}

        fg_val = fg.get("value")
        dom_val = dom.get("value")
        fr_val = fr.get("avg_fr")
        cpi_change = macro.get("cpi_change")
        fed_rate = macro.get("fed_rate")
        has_signal = bool(tech.get("has_signal"))

        fg_label = "—" if fg_val is None else f"{float(fg_val):.1f}"
        dom_label = "—" if dom_val is None else f"{float(dom_val):.2f}%"
        fr_label = "—" if fr_val is None else f"{float(fr_val):+.4f}%"
        cpi_label = "—" if cpi_change is None else f"{float(cpi_change):+.2f}%"
        fed_label = "—" if fed_rate is None else f"{float(fed_rate):.2f}%"
        tech_label = "ada sinyal" if has_signal else "tidak ada sinyal"

        msg = (
            "🎯 Market Context Score\n\n"
            f"Total: {result.get('total_score', 50)}/100 — {result.get('label', 'Neutral')} {result.get('emoji', '⚪')}\n\n"
            "Breakdown:\n"
            f"• Fear & Greed: {fg.get('score', 0)}/20 (nilai: {fg_label})\n"
            f"• BTC Dominance: {dom.get('score', 0)}/15 (nilai: {dom_label})\n"
            f"• Funding Rate: {fr.get('score', 0)}/25 (avg FR: {fr_label})\n"
            f"• Makro: {macro.get('score', 0)}/25 (CPI: {cpi_label} | Fed: {fed_label})\n"
            f"• Teknikal: {tech.get('score', 0)}/15 ({tech_label})\n\n"
            f"{result.get('summary', 'Pasar sideways — tunggu breakout atau sinyal yang jelas.')}\n\n"
            f"⏰ {result.get('timestamp', '—')}"
        )
        await target.reply_text(msg)
    except Exception as e:
        logging.error("market_context_command: %s", e, exc_info=True)
        await target.reply_text("Terjadi kesalahan saat hitung market context.")


# ========== BTC SMART ALERT ==========

def _confidence_to_zone(conf: int | None) -> str:
    if conf is None:
        return "—"
    try:
        c = int(conf)
    except (TypeError, ValueError):
        return "—"
    if c >= 85:
        return "HIGH"
    if c >= 70:
        return "MEDIUM"
    if c > 0:
        return "LOW"
    return "LOW"


def _format_btc_smart_message(result: dict, btc_data: dict) -> str:
    def _fmt(v):
        if v is None:
            return "—"
        if isinstance(v, float):
            return round(v, 2) if v == v else "—"
        return str(v)

    conf = result.get("confidence", 0)
    zone = _confidence_to_zone(conf)
    return (
        "🧠 BTC SMART SIGNAL\n\n"
        f"Signal       : {result.get('signal', 'WAIT')}\n"
        f"Market Phase : {result.get('phase', '—')}\n"
        f"Confidence   : {zone}\n\n"
        f"📊 RSI        : {_fmt(btc_data.get('rsi'))}\n"
        f"📊 Trend      : {_fmt(btc_data.get('trend'))}\n\n"
        "📌 Recommendation:\n"
        f"{result.get('recommendation', '—')}"
    )


async def btc_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("COMMAND RECEIVED: /btc")
    target = _reply_target(update)
    if not target:
        return
    try:
        if analyze_btc_signal is None:
            await target.reply_text("Fitur btc smart alert tidak tersedia.")
            return
        snapshot = get_market_snapshot()
        data = snapshot.get("data") or {}
        btc_data = data.get("BTC") or {}
        if not btc_data:
            await target.reply_text("Market data BTC tidak tersedia.")
            return

        result = analyze_btc_signal(snapshot)
        await target.reply_text(_format_btc_smart_message(result, btc_data))
    except Exception as e:
        logging.error("BTC ERROR: %s", e)
        await target.reply_text("Terjadi kesalahan.")


# ========== SNAPSHOT ==========

async def snapshot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display current market snapshot (cached; no API calls)."""
    logging.info("COMMAND RECEIVED: /snapshot")
    try:
        snapshot = get_market_snapshot()
        data = snapshot.get("data", {})
        ts = snapshot.get("timestamp")

        num_coins = len(data)
        if num_coins == 0:
            await update.message.reply_text("Market snapshot kosong.")
            return

        age = 0
        if ts:
            try:
                age = int((datetime.utcnow() - ts).total_seconds())
            except (TypeError, ValueError, AttributeError):
                pass

        lines = [
            "📸 ALIZA SNAPSHOT\n",
            f"Coins : {num_coins}",
            f"Age   : {age}s\n",
        ]
        for symbol, market in list(data.items())[:10]:
            price = market.get("price")
            if price is not None:
                try:
                    p = float(price)
                    lines.append(f"{symbol} {p:.2f}")
                except (TypeError, ValueError):
                    lines.append(f"{symbol} —")
            else:
                lines.append(f"{symbol} —")
        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        logging.error("SNAPSHOT ERROR: %s", e)
        await update.message.reply_text("Terjadi kesalahan memuat snapshot.")


# ========== HEALTH ==========

async def health_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check Aliza system health from snapshot (read-only)."""
    logging.info("COMMAND RECEIVED: /health")
    try:
        snapshot = get_market_snapshot()
        data = snapshot.get("data", {})
        ts = snapshot.get("timestamp")

        num_coins = len(data)

        age = None
        if ts:
            try:
                age = int((datetime.utcnow() - ts).total_seconds())
            except (TypeError, ValueError, AttributeError):
                pass

        status = "OK"
        if num_coins < 5:
            status = "WARNING"
        if age is None or age > 300:
            status = "STALE"

        btc_present = "YES" if "BTC" in data and data.get("BTC") else "NO"
        age_str = f"{age}s" if age is not None else "—"

        msg = (
            "🏥 ALIZA SYSTEM HEALTH\n\n"
            f"Status          : {status}\n"
            f"Snapshot coins  : {num_coins}\n"
            f"Snapshot age    : {age_str}\n\n"
            f"BTC present     : {btc_present}"
        )
        await update.message.reply_text(msg)
    except Exception as e:
        logging.error("HEALTH ERROR: %s", e)
        await update.message.reply_text("Terjadi kesalahan cek health.")


def _brief_wib_date_header() -> str:
    """Hari dan tanggal untuk header brief (zona WIB)."""
    try:
        if ZoneInfo is not None:
            n = datetime.now(ZoneInfo("Asia/Jakarta"))
        else:
            n = datetime.utcnow() + timedelta(hours=7)
    except Exception:
        n = datetime.utcnow() + timedelta(hours=7)
    days = ("Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu")
    months = (
        "Januari",
        "Februari",
        "Maret",
        "April",
        "Mei",
        "Juni",
        "Juli",
        "Agustus",
        "September",
        "Oktober",
        "November",
        "Desember",
    )
    return f"{days[n.weekday()]}, {n.day} {months[n.month - 1]} {n.year}"


def _spot_signal_wib_header_line() -> str:
    """Hari, tanggal, dan jam saat ini untuk header saran spot (zona WIB)."""
    try:
        if ZoneInfo is not None:
            n = datetime.now(ZoneInfo("Asia/Jakarta"))
        else:
            n = datetime.utcnow() + timedelta(hours=7)
    except Exception:
        n = datetime.utcnow() + timedelta(hours=7)
    days = ("Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu")
    months = (
        "Januari",
        "Februari",
        "Maret",
        "April",
        "Mei",
        "Juni",
        "Juli",
        "Agustus",
        "September",
        "Oktober",
        "November",
        "Desember",
    )
    date_part = f"{days[n.weekday()]}, {n.day} {months[n.month - 1]} {n.year}"
    time_part = f"{n.strftime('%H:%M')} WIB"
    return f"{date_part} • {time_part}"


def _fear_greed_label(fg: float) -> str:
    """Label skala Fear & Greed (nilai 0–100)."""
    if fg <= 24:
        return "Extreme Fear"
    if fg <= 46:
        return "Fear"
    if fg <= 54:
        return "Neutral"
    if fg <= 74:
        return "Greed"
    return "Extreme Greed"


def _brief_fmt_price(p) -> str:
    if p is None:
        return "—"
    try:
        v = float(p)
        return f"${v:,.2f}"
    except (TypeError, ValueError):
        return "—"


def _brief_fmt_pct(ch) -> str:
    if ch is None:
        return "—"
    try:
        v = float(ch)
        return f"{v:+.2f}%"
    except (TypeError, ValueError):
        return "—"


try:
    from engine.brain.aliza_engine import ask_aliza
except ImportError:
    ask_aliza = None  # type: ignore[misc, assignment]


def _brief_fmt_vol(v) -> str:
    if v is None:
        return "—"
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "—"
    ax = abs(x)
    if ax >= 1e9:
        return f"{x / 1e9:.2f}B"
    if ax >= 1e6:
        return f"{x / 1e6:.2f}M"
    if ax >= 1e3:
        return f"{x / 1e3:.2f}K"
    return f"{x:.2f}"


def _top_coins_analysis_dict(data: dict) -> dict[str, dict[str, Any]]:
    """Ringkas snapshot ke dict untuk prompt analisis."""
    out: dict[str, dict[str, Any]] = {}
    if not data:
        return out
    for symbol in sorted(data.keys()):
        m = data.get(symbol) or {}
        pct = m.get("price_change_percentage_24h")
        if pct is None:
            pct = m.get("change_24h_pct")
        if pct is None:
            pct = m.get("price_change_24h")
        vol = m.get("volume_24h")
        if vol is None:
            vol = m.get("quote_volume_24h")
        if vol is None:
            vol = m.get("volume")
        out[symbol] = {
            "price": m.get("price"),
            "pct_24h": pct,
            "volume": vol,
        }
    return out


def _funding_rates_analysis_dict() -> dict[str, Any]:
    """Data funding per coin untuk prompt (tanpa API baru)."""
    try:
        raw = get_all_funding_data() or {}
        if not isinstance(raw, dict):
            return {}
        slim: dict[str, Any] = {}
        for sym, row in raw.items():
            if not isinstance(row, dict):
                continue
            slim[str(sym).upper()] = {
                "funding_rate": row.get("funding_rate"),
                "oi_usd": row.get("oi_usd"),
            }
        return slim
    except Exception as e:  # noqa: BLE001
        logging.warning("_funding_rates_analysis_dict: %s", e)
        return {}


def _macro_for_analysis_prompt() -> dict[str, Any]:
    """CPI YoY, Core PCE YoY, NFP mom, Fed latest — ringkas untuk prompt."""
    out: dict[str, Any] = {}
    try:
        cpi = get_macro_data("CPIAUCSL", "pct_change_yoy")
        if cpi:
            out["cpi_yoy_pct"] = cpi.get("value")
    except Exception:
        pass
    try:
        pce = get_macro_data("PCEPILFE", "pct_change_yoy")
        if pce:
            out["core_pce_yoy_pct"] = pce.get("value")
    except Exception:
        pass
    try:
        nfp = get_macro_data("PAYEMS", "mom_change")
        if nfp:
            out["nfp_change_k"] = nfp.get("value")
    except Exception:
        pass
    try:
        fed = get_macro_data("FEDFUNDS", "latest")
        if fed:
            out["fed_rate_pct"] = fed.get("value")
    except Exception:
        pass
    return out


def _avg_funding_fr_pct_and_bias(funding_rates: dict) -> tuple[str, str]:
    """Rata-rata FR dalam % dan label LONG/SHORT/SEIMBANG."""
    coins = ("BTC", "ETH", "BNB", "SOL", "XRP")
    rates: list[float] = []
    for c in coins:
        row = funding_rates.get(c) if isinstance(funding_rates, dict) else None
        if not isinstance(row, dict):
            continue
        fr = row.get("funding_rate")
        try:
            if fr is not None:
                rates.append(float(fr) * 100.0)
        except (TypeError, ValueError):
            continue
    if not rates:
        return "—", "tidak diketahui"
    avg = sum(rates) / len(rates)
    avg_s = f"{avg:+.4f}"
    if avg > 0.05:
        bias = "LONG dominan"
    elif avg < -0.05:
        bias = "SHORT dominan"
    else:
        bias = "SEIMBANG"
    return avg_s, bias


def _format_events_for_prompt(events: list | None) -> str:
    if not events:
        return "tidak ada"
    parts = []
    for e in events[:12]:
        if not isinstance(e, dict):
            continue
        nm = e.get("name", "—")
        t = e.get("datetime_wib") or e.get("datetime_utc") or "—"
        parts.append(f"{nm} ({t})")
    return "; ".join(parts) if parts else "tidak ada"



def _format_events_for_display(events):
    """Format event untuk display ke user — lebih manusiawi dari ISO timestamp."""
    if not events:
        return "tidak ada"
    from datetime import datetime as _dt
    HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
    BULAN = ["", "Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
             "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
    parts = []
    for e in events[:3]:
        if not isinstance(e, dict):
            continue
        nm = e.get("name", "-")
        t = e.get("datetime_wib") or e.get("datetime_utc") or ""
        impact = e.get("impact", "")
        icon = "🔴" if impact == "HIGH" else "🟡" if impact == "MEDIUM" else "⚪"
        try:
            dt = _dt.fromisoformat(str(t))
            hari = HARI[dt.weekday()]
            bln = BULAN[dt.month]
            tgl = dt.day
            jam = dt.strftime("%H:%M")
            t_str = f"{hari} {tgl} {bln} {jam} WIB"
        except Exception:
            t_str = str(t)
        parts.append(f"{icon} {nm} • {t_str}")
    return "\n".join(parts) if parts else "tidak ada"

def _format_top_coins_line(top_coins: dict) -> str:
    if not top_coins:
        return "tidak ada data"
    lines = []
    for sym in sorted(top_coins.keys())[:15]:
        row = top_coins.get(sym) or {}
        p = row.get("price")
        pct = row.get("pct_24h")
        try:
            p_s = f"{float(p):,.2f}" if p is not None else "—"
        except (TypeError, ValueError):
            p_s = "—"
        try:
            pct_s = f"{float(pct):+.2f}%" if pct is not None else "—"
        except (TypeError, ValueError):
            pct_s = str(pct) if pct is not None else "—"
        lines.append(f"{sym} {p_s} ({pct_s})")
    return " | ".join(lines)


def _get_cross_asset_data() -> dict:
    """Fetch SPX, VIX, Gold, Oil via Serper + FRED. Fallback None jika gagal."""
    import re as _re
    result = {"dxy": None, "gold": None, "oil": None, "sp500": None, "vix": None}
    try:
        import httpx as _httpx
        import os as _os
        serper_key = _os.getenv("SERPER_API_KEY", "")

        def _serper_search(query):
            try:
                r = _httpx.post(
                    "https://google.serper.dev/search",
                    headers={"X-API-KEY": serper_key, "Content-Type": "application/json"},
                    json={"q": query, "num": 3},
                    timeout=8,
                )
                if r.status_code == 200:
                    data = r.json()
                    # Coba answerBox dulu (lebih akurat untuk harga)
                    ab = data.get("answerBox", {})
                    if ab.get("answer"):
                        return str(ab.get("title", "")) + " " + str(ab.get("answer", ""))
                    # Coba answerBox snippet (gold pakai ini)
                    if ab.get("snippet"):
                        return str(ab.get("snippet", ""))
                    # Fallback ke organic snippet
                    for item in data.get("organic", []):
                        snippet = item.get("snippet", "")
                        if snippet:
                            return snippet
            except Exception:
                pass
            return ""

        def _parse_price(text):
            # Pattern 1: price dengan pct change "(+1.2%)"
            m = _re.search(r"([\d,]+\.?\d*)\s*[+\-][\d,]+\.?\d*\s*\(([+\-][\d.]+)%\)", text)
            if m:
                try:
                    return float(m.group(1).replace(",", "")), float(m.group(2))
                except ValueError:
                    pass
            # Pattern 2: "$4,791.00" format (answerBox gold)
            m2 = _re.search(r"\$([\d,]+\.\d+)", text)
            if m2:
                try:
                    return float(m2.group(1).replace(",", "")), 0.0
                except ValueError:
                    pass
            # Pattern 3: plain number dengan desimal
            m3 = _re.search(r"([\d,]+\.[\d]+)", text)
            if m3:
                try:
                    return float(m3.group(1).replace(",", "")), 0.0
                except ValueError:
                    pass
            return None, None

        try:
            _fred_key = _os.getenv("FRED_API_KEY", "")
            if _fred_key:
                _r = _httpx.get(
                    "https://api.stlouisfed.org/fred/series/observations",
                    params={
                        "series_id": "SP500",
                        "api_key": _fred_key,
                        "limit": 2,
                        "sort_order": "desc",
                        "file_type": "json",
                    },
                    timeout=8,
                )
                if _r.status_code == 200:
                    _obs = _r.json().get("observations") or []
                    if len(_obs) >= 2:
                        _v1 = _obs[0].get("value")
                        _v2 = _obs[1].get("value")
                        if _v1 not in ("", ".") and _v2 not in ("", "."):
                            _price = float(_v1)
                            _prev = float(_v2)
                            _pct = round((_price - _prev) / _prev * 100, 2) if _prev else 0.0
                            result["sp500"] = {"price": _price, "pct": _pct}
        except Exception:
            pass

        try:
            _fred_key = _os.getenv("FRED_API_KEY", "")
            if _fred_key:
                _r = _httpx.get(
                    "https://api.stlouisfed.org/fred/series/observations",
                    params={
                        "series_id": "VIXCLS",
                        "api_key": _fred_key,
                        "limit": 1,
                        "sort_order": "desc",
                        "file_type": "json",
                    },
                    timeout=8,
                )
                if _r.status_code == 200:
                    _obs = _r.json().get("observations") or []
                    if _obs and _obs[0].get("value") not in ("", "."):
                        result["vix"] = {"price": float(_obs[0]["value"]), "pct": 0.0}
        except Exception:
            pass

        try:
            _r = _httpx.get(
                "https://api.binance.com/api/v3/ticker/24hr",
                params={"symbol": "XAUTUSDT"},
                headers={"User-Agent": "AlizaAI"},
                timeout=8,
            )
            if _r.status_code == 200:
                _d = _r.json()
                _price = float(_d.get("lastPrice", 0))
                _pct = float(_d.get("priceChangePercent", 0))
                if 1500 < _price < 10000:
                    result["gold"] = {"price": _price, "pct": round(_pct, 2)}
        except Exception:
            pass

        try:
            _fred_key = _os.getenv("FRED_API_KEY", "")
            if _fred_key:
                _r = _httpx.get(
                    "https://api.stlouisfed.org/fred/series/observations",
                    params={
                        "series_id": "DTWEXBGS",
                        "api_key": _fred_key,
                        "limit": 1,
                        "sort_order": "desc",
                        "file_type": "json",
                    },
                    timeout=8,
                )
                if _r.status_code == 200:
                    _obs = _r.json().get("observations") or []
                    if _obs and _obs[0].get("value") not in ("", "."):
                        _val = float(_obs[0]["value"])
                        if 80 < _val < 200:
                            result["dxy"] = {"price": _val, "pct": 0.0}
        except Exception:
            pass

        fred_key = _os.getenv("FRED_API_KEY", "")
        if fred_key:
            try:
                r = _httpx.get(
                    "https://api.stlouisfed.org/fred/series/observations"
                    "?series_id=DCOILWTICO&api_key=" + fred_key + "&limit=2&sort_order=desc&file_type=json",
                    timeout=8,
                )
                if r.status_code == 200:
                    obs = r.json().get("observations", [])
                    if len(obs) >= 2:
                        v1, v2 = float(obs[0]["value"]), float(obs[1]["value"])
                        result["oil"] = {
                            "price": round(v1, 2),
                            "pct": round((v1-v2)/v2*100, 2) if v2 else 0,
                            "date": obs[0].get("date", ""),
                        }
                    elif len(obs) == 1:
                        result["oil"] = {
                            "price": round(float(obs[0]["value"]), 2),
                            "pct": 0,
                            "date": obs[0].get("date", ""),
                        }
            except Exception:
                pass
    except Exception:
        pass
    return result

def _brief_analysis_is_llm_failure(analysis: str) -> bool:
    """True jika _generate_brief_analysis mengembalikan fallback (timeout / error / AI off)."""
    if "Analisis AI sementara tidak tersedia (timeout atau error)" in analysis:
        return True
    if "Modul AI tidak tersedia — analisis otomatis dilewati" in analysis:
        return True
    if "Conviction: —/10 — Modul AI tidak tersedia" in analysis:
        return True
    return False



def _get_usd_idr_rate() -> float:
    """Ambil kurs USD/IDR real-time dari exchangerate-api (free, no key needed)."""
    try:
        import httpx as _httpx

        resp = _httpx.get(
            "https://api.exchangerate-api.com/v4/latest/USD",
            timeout=5,
        )
        if resp.status_code == 200:
            rate = resp.json().get("rates", {}).get("IDR")
            if rate:
                return float(rate)
    except Exception:
        pass
    return 16500.0  # fallback default


def _reorder_section_by_rr(section_text: str, is_spot: bool = False) -> str:
    """Urutkan entry coin berdasarkan RR tertinggi ke terendah, hitung ulang RR dari Entry/SL/Target."""
    import re as _re
    lines = section_text.split("\n")
    header_lines = []
    entries = []
    footer_lines = []
    current_entry = []
    in_entries = False
    for line in lines:
        if line.strip().startswith(("•", "-", "*", "·", "▪", "‣")):
            in_entries = True
            if current_entry:
                entries.append("\n".join(current_entry))
            current_entry = [line]
        elif in_entries:
            if line.strip().startswith("⚠️"):
                if current_entry:
                    entries.append("\n".join(current_entry))
                    current_entry = []
                footer_lines.append(line)
            else:
                current_entry.append(line)
        else:
            header_lines.append(line)
    if current_entry:
        entries.append("\n".join(current_entry))

    def parse_price(text, label):
        m = _re.search(label + r"[: ]*\$?([\d,]+\.?\d*)", text, _re.IGNORECASE)
        if m:
            try:
                return float(m.group(1).replace(",", ""))
            except ValueError:
                return None
        return None

    def parse_target_t1(text):
        t = parse_price(text, "Target 1")
        if t is not None:
            return t
        return parse_price(text, "Target")

    def parse_target_far(text):
        """Target yang RR-nya dihitung dari sini — final/"ambil sisa" target, BUKAN
        target pertama yang diambil profit-nya (partial). Sebelum enforce_target_order
        menjalankan urutan, "Target 2" adalah yang dimaksud (kalau ada); fallback ke
        "Target 1"/"Target" untuk teks legacy yang cuma punya satu target."""
        t = parse_price(text, "Target 2")
        if t is not None:
            return t
        t = parse_price(text, "Target 1")
        if t is not None:
            return t
        return parse_price(text, "Target")

    def parse_entry_any(text):
        if is_spot:
            for lab in ("Entry ideal", "Entry sekarang", "Entry"):
                v = parse_price(text, lab)
                if v is not None:
                    return v
            return None
        return parse_price(text, "Entry")

    def is_short_entry(entry_text):
        return bool(_re.search(r"SHORT", entry_text, _re.IGNORECASE)) and not is_spot

    MIN_RR = 2.0
    MIN_SL_PCT = 0.05  # 5% minimum SL
    MAX_SL_PCT = 0.08  # 8% maximum SL (cap agar tidak terlalu lebar)

    def enforce_sl_range(entry_text):
        """Pastikan SL berada di range 5-8% dari entry."""
        import re as _re2
        entry = parse_entry_any(entry_text)
        sl = parse_price(entry_text, "SL")
        if not entry or not sl or entry <= 0:
            return entry_text
        sl_pct = abs(entry - sl) / entry
        if MIN_SL_PCT <= sl_pct <= MAX_SL_PCT:
            return entry_text  # sudah dalam range
        # Adjust SL ke 6% (tengah range)
        if is_short_entry(entry_text):
            new_sl = round(entry * (1 + 0.06), 2)
        else:
            new_sl = round(entry * (1 - 0.06), 2)
        if entry > 1000:
            sl_str = f"{new_sl:,.2f}"
        elif entry > 10:
            sl_str = f"{new_sl:.2f}"
        else:
            sl_str = f"{new_sl:.4f}"
        result = _re2.sub(
            r"SL: *\$[\d,]+\.?\d*",
            "SL: $" + sl_str,
            entry_text
        )
        return result

    def fix_sl_percentage(entry_text):
        """Hitung ulang '(X% dari entry)' di baris SL dari Entry/SL yang benar-benar
        ditampilkan di pesan ini — jangan percaya angka persen yang ditulis LLM.
        enforce_sl_range() di atas cuma mengganti angka dolar SL kalau di luar
        rentang 5-8%; kalau SL sudah dalam rentang (atau setelah diganti), label
        persennya sendiri tidak pernah disentuh — itu sebabnya "(5% dari entry)"
        bisa nempel di teks padahal Entry/SL yang ditampilkan aslinya 6,00%."""
        entry = parse_entry_any(entry_text)
        sl = parse_price(entry_text, "SL")
        if not entry or not sl or entry <= 0:
            return entry_text
        correct_pct = round(abs(entry - sl) / entry * 100, 1)
        m = _re.search(r"(SL:\s*\$[\d,]+\.?\d*\s*\()([\d.]+)(%\s*dari entry\))", entry_text)
        if not m:
            return entry_text
        return entry_text[: m.start(2)] + f"{correct_pct:.1f}" + entry_text[m.end(2) :]

    def enforce_target_order(entry_text):
        """Pastikan Target 1 (label 'ambil 50%', diambil duluan) selalu LEBIH DEKAT
        ke entry daripada Target 2 (label 'ambil sisa', target akhir) — posisi
        harga yang menentukan urutan, bukan sekadar label bebas yang ditulis LLM.
        Root cause bug Target1/Target2 tertukar: enforce_min_rr (di bawah) dulu
        cuma menulis ulang "Target 1" untuk memenuhi RR minimum tanpa mengecek
        posisinya relatif ke Target 2 — kalau Target 1 asli LLM sudah dekat
        (RR rendah), dipaksa naik jadi lebih jauh dari Target 2, sehingga
        Target 1 > Target 2 padahal labelnya menyiratkan sebaliknya. Fungsi ini
        menukar NILAI (dolar) dua target itu kalau urutannya kebalik, sebelum
        enforce_min_rr/fix_target_percentages jalan — supaya keduanya selalu
        beroperasi pada target yang sudah benar posisinya."""
        entry = parse_entry_any(entry_text)
        t1 = parse_price(entry_text, "Target 1")
        t2 = parse_price(entry_text, "Target 2")
        if entry is None or t1 is None or t2 is None:
            return entry_text
        is_short = is_short_entry(entry_text)
        d1 = (entry - t1) if is_short else (t1 - entry)
        d2 = (entry - t2) if is_short else (t2 - entry)
        if d1 <= d2:
            return entry_text  # Target 1 sudah lebih dekat (atau sama) — urutan benar
        if max(t1, t2) > 1000:
            t1_str, t2_str = f"{t2:,.2f}", f"{t1:,.2f}"
        elif max(t1, t2) > 10:
            t1_str, t2_str = f"{t2:.2f}", f"{t1:.2f}"
        else:
            t1_str, t2_str = f"{t2:.4f}", f"{t1:.4f}"
        result = _re.sub(r"Target 1:\s*\$[\d,]+\.?\d*", "Target 1: $" + t1_str, entry_text)
        result = _re.sub(r"Target 2:\s*\$[\d,]+\.?\d*", "Target 2: $" + t2_str, result)
        return result

    def calc_rr(entry_text):
        """RR selalu dihitung dari target FINAL (Target 2 kalau ada, 'ambil sisa') —
        itu yang mendefinisikan R-multiple, bukan target partial pertama."""
        entry = parse_entry_any(entry_text)
        sl = parse_price(entry_text, "SL")
        target = parse_target_far(entry_text)
        if entry and sl and target and abs(entry - sl) > 0:
            sl_distance = abs(entry - sl)
            if is_short_entry(entry_text):
                return round((entry - target) / sl_distance, 1)
            return round((target - entry) / sl_distance, 1)
        return None

    def enforce_min_rr(entry_text, min_rr=MIN_RR):
        """Adjust target FINAL (Target 2, atau Target 1/Target legacy kalau tidak
        ada Target 2) agar RR minimal min_rr. Sengaja tidak menyentuh Target 1
        (partial) — itu dipertahankan sebagai target dekat, konsisten dengan
        enforce_target_order di atas."""
        entry = parse_entry_any(entry_text)
        sl = parse_price(entry_text, "SL")
        target = parse_target_far(entry_text)
        if not (entry and sl and target):
            return entry_text
        sl_distance = abs(entry - sl)
        if sl_distance == 0:
            return entry_text
        is_short = is_short_entry(entry_text)
        if is_short:
            current_rr = (entry - target) / sl_distance
        else:
            current_rr = (target - entry) / sl_distance
        if current_rr >= min_rr:
            return entry_text
        # Hitung target baru
        if is_short:
            new_target = round(entry - (sl_distance * min_rr), 2)
        else:
            new_target = round(entry + (sl_distance * min_rr), 2)
        # Format target sesuai skala harga
        if entry > 1000:
            target_str = f"{new_target:,.2f}"
        elif entry > 10:
            target_str = f"{new_target:.2f}"
        else:
            target_str = f"{new_target:.4f}"
        # Ganti Target 2 (spot/futures baru dengan dua target), atau Target 1 /
        # Target (legacy, cuma satu target)
        if parse_price(entry_text, "Target 2") is not None:
            result = _re.sub(
                r"Target 2:\s*\$[\d,]+\.?\d*",
                "Target 2: $" + target_str,
                entry_text,
            )
        elif parse_price(entry_text, "Target 1") is not None:
            result = _re.sub(
                r"Target 1:\s*\$[\d,]+\.?\d*",
                "Target 1: $" + target_str,
                entry_text,
            )
        else:
            result = _re.sub(
                r"Target:\s*\$[\d,]+\.?\d*",
                "Target: $" + target_str,
                entry_text,
            )
        return result

    def fix_target_percentages(entry_text):
        """Hitung ulang persentase Target 1 dan Target 2 dari entry — jangan percaya LLM."""
        import re as _re3
        entry = parse_entry_any(entry_text)
        if not entry or entry <= 0:
            return entry_text
        result = entry_text

        # Fix Target 1 percentage
        m1 = _re3.search(r"Target 1:\s*\$([\d,]+\.?\d*)\s*\(([+\-][\d.]+)%\)", result)
        if m1:
            try:
                t1 = float(m1.group(1).replace(",", ""))
                if is_short_entry(result):
                    correct_pct = round((entry - t1) / entry * 100, 1)
                else:
                    correct_pct = round((t1 - entry) / entry * 100, 1)
                result = result.replace(m1.group(0),
                    f"Target 1: ${m1.group(1)} ({correct_pct:+.1f}%)")
            except Exception:
                pass

        # Fix Target 2 percentage
        m2 = _re3.search(r"Target 2:\s*\$([\d,]+\.?\d*)\s*\(([+\-][\d.]+)%\)", result)
        if m2:
            try:
                t2 = float(m2.group(1).replace(",", ""))
                if is_short_entry(result):
                    correct_pct = round((entry - t2) / entry * 100, 1)
                else:
                    correct_pct = round((t2 - entry) / entry * 100, 1)
                result = result.replace(m2.group(0),
                    f"Target 2: ${m2.group(1)} ({correct_pct:+.1f}%)")
            except Exception:
                pass

        return result

    def fix_invalidation(entry_text):
        """Pastikan invalidasi level konsisten dengan SL — tidak lebih dari 2% di bawah SL."""
        import re as _re4
        sl = parse_price(entry_text, "SL")
        if not sl or sl <= 0:
            return entry_text
        is_short = is_short_entry(entry_text)
        if is_short:
            invalidation = round(sl * 1.005, 2)
        else:
            invalidation = round(sl * 0.995, 2)
        if sl > 1000:
            inv_str = f"{invalidation:,.2f}"
        elif sl > 10:
            inv_str = f"{invalidation:.2f}"
        else:
            inv_str = f"{invalidation:.4f}"
        side = "atas" if is_short else "bawah"
        result = _re4.sub(
            r"Invalidasi:.*",
            f"Invalidasi: Jika harga tutup di {side} ${inv_str}",
            entry_text
        )
        return result

    def fix_rr_in_entry(entry_text, rr_val):
        if rr_val is None:
            return entry_text
        return _re.sub(r"RR: *[\d.]+x?", "RR: " + str(rr_val) + "x", entry_text)

    usd_idr_rate = _get_usd_idr_rate() if is_spot else 0.0

    def _format_idr(v: float) -> str:
        n = int(round(v))
        return f"{n:,}".replace(",", ".")

    processed = []
    for e in entries:
        e = "\n".join(l.rstrip() for l in e.split("\n"))  # strip trailing spaces
        e = enforce_sl_range(e)
        e = fix_sl_percentage(e)
        e = enforce_target_order(e)
        e = enforce_min_rr(e)
        e = fix_target_percentages(e)
        e = fix_invalidation(e)
        rr = calc_rr(e)
        # Skip entry dengan RR terlalu rendah setelah semua enforce
        if rr is not None and rr < 1.5:
            continue
        e_fixed = fix_rr_in_entry(e, rr)
        if is_spot:
            entry_val = parse_entry_any(e_fixed)
            sl_val = parse_price(e_fixed, "SL")
            target_val = parse_target_t1(e_fixed)
            if (
                entry_val is not None
                and sl_val is not None
                and target_val is not None
            ):
                idr_line = (
                    f"  IDR  Entry: Rp{_format_idr(entry_val * usd_idr_rate)}"
                    f" | SL: Rp{_format_idr(sl_val * usd_idr_rate)}"
                    f" | Target 1: Rp{_format_idr(target_val * usd_idr_rate)}"
                )
                e_fixed += "\n" + idr_line
        processed.append((rr if rr is not None else 0.0, e_fixed))

    processed_sorted = sorted(processed, key=lambda x: x[0], reverse=True)
    entries_sorted = [e for _, e in processed_sorted]

    result_parts = []
    if header_lines:
        result_parts.append("\n".join(header_lines))
    if entries_sorted:
        result_parts.append("\n\n".join(entries_sorted))
    if footer_lines:
        result_parts.append("\n".join(footer_lines))
    result = "\n".join(result_parts)

    # Pastikan section ini SELALU eksplisit bilang Entry/SL/Target di dalamnya
    # estimasi AI (LLM), BUKAN sinyal yang sudah melalui backtest/validasi
    # winrate (beda dari TradingBrain/E3 shadow yang tervalidasi) — ditambahkan
    # di kode, tidak bergantung LLM menuliskannya sendiri di teks bebas, supaya
    # selalu muncul dan tidak cuma kadang-kadang tergantung LLM ikut instruksi
    # prompt atau tidak. Kalau section futures sudah punya baris peringatan
    # risiko dari LLM ("⚠️ Futures berisiko tinggi..."), gabungkan ke baris itu
    # alih-alih menambah baris disclaimer terpisah.
    _ai_estimate_note = (
        "Entry/SL/Target di atas estimasi AI (LLM), bukan sinyal yang sudah "
        "melalui backtest/validasi winrate — beda dari sinyal deterministik/E3 "
        "shadow yang tervalidasi. Gunakan sebagai referensi awal, selalu "
        "konfirmasi manual sebelum entry."
    )
    if result.strip() and _ai_estimate_note not in result:
        if not is_spot and "⚠️ Futures berisiko tinggi" in result:
            result = _re.sub(
                r"(⚠️ Futures berisiko tinggi\.[^\n]*)",
                lambda m: m.group(1) + " " + _ai_estimate_note,
                result,
                count=1,
            )
        else:
            result = result.rstrip() + "\n⚠️ " + _ai_estimate_note
    return result

def _extract_spot_section_from_brief_analysis(analysis: str) -> str:
    """Pisahkan spot/futures dari konten entry, bukan posisi header futures."""
    lines = analysis.split("\n")
    spot_start = next((i for i, l in enumerate(lines) if "SARAN SPOT" in l), None)
    if spot_start is None:
        return analysis.strip()
    section_lines = [l.rstrip() for l in lines[spot_start:]]
    try:
        entries: list[str] = []
        current: list[str] = []
        for line in section_lines:
            if line.strip().startswith(("•", "-", "*", "·", "▪", "‣")):
                if current:
                    entries.append("\n".join(current).strip())
                current = [line]
            elif current:
                current.append(line)
        if current:
            entries.append("\n".join(current).strip())

        spot_entries: list[str] = []
        futures_entries: list[str] = []
        for entry in entries:
            upper_entry = entry.upper()
            if "SKIP" in upper_entry:
                continue
            is_futures = (
                "LEVERAGE" in upper_entry
                or ": LONG" in upper_entry
                or ": SHORT" in upper_entry
            )
            if is_futures:
                futures_entries.append(entry)
            else:
                spot_entries.append(entry)

        result_sections: list[str] = []

        # Correlation risk warning — inject jika ada >=2 spot entries
        correlation_warning = ""
        if len(spot_entries) >= 2:
            correlation_warning = "\n⚠️ CORRELATION RISK: Semua coin crypto berkorelasi tinggi — jangan buka semua posisi sekaligus. Pilih maksimal 1-2 setup terbaik."

        if spot_entries:
            spot_text = "📈 SARAN SPOT TERBAIK\n" + "\n".join("\n".join(l.rstrip() for l in e.split("\n")) for e in spot_entries) + correlation_warning
            spot_section = _reorder_section_by_rr(spot_text, is_spot=True).strip()
            if spot_section:
                result_sections.append(spot_section)

        if futures_entries:
            futures_text = "📊 SARAN FUTURES\n" + "\n".join(futures_entries)
            futures_section = _reorder_section_by_rr(futures_text).strip()
            if futures_section:
                result_sections.append(futures_section)

        if result_sections:
            raw = "\n\n".join(result_sections).strip()
            # Strip duplikat header dan IDR yang salah posisi
            lines_out = raw.split("\n")
            cleaned = []
            seen_spot_header = False
            seen_futures_header = False
            in_futures = False
            for ln in lines_out:
                stripped = ln.strip()
                # Deduplicate spot header
                if "SARAN SPOT" in stripped:
                    if seen_spot_header:
                        continue
                    seen_spot_header = True
                # Deduplicate futures header
                if "SARAN FUTURES" in stripped:
                    if seen_futures_header:
                        continue
                    seen_futures_header = True
                    in_futures = True
                # Strip IDR baris yang muncul di futures section
                if in_futures and stripped.startswith("IDR "):
                    continue
                cleaned.append(ln)
            return "\n".join(cleaned).strip()
        return ""
    except Exception:
        return "\n".join(section_lines).strip()


def _format_cross_asset_strings(cross_asset: dict[str, Any]) -> dict[str, str]:
    """Bangun string satu baris per aset untuk prompt LLM."""
    sp500_str = (
        f"${cross_asset['sp500']['price']:,.0f} ({cross_asset['sp500']['pct']:+.1f}%)"
        if cross_asset.get("sp500")
        else "data tidak tersedia"
    )
    vix_str = (
        f"{cross_asset['vix']['price']:.1f} ({cross_asset['vix']['pct']:+.1f}%)"
        if cross_asset.get("vix")
        else "data tidak tersedia"
    )
    gold_str = (
        f"${cross_asset['gold']['price']:,.0f} ({cross_asset['gold']['pct']:+.1f}%)"
        if cross_asset.get("gold")
        else "data tidak tersedia"
    )
    if cross_asset.get("oil"):
        _oil = cross_asset["oil"]
        _oil_date = _oil.get("date", "")
        _oil_date_label = f" • per {_oil_date}" if _oil_date else ""
        oil_str = f"${_oil['price']:.1f} ({_oil['pct']:+.1f}%){_oil_date_label}"
    else:
        oil_str = "data tidak tersedia"
    dxy_str = (
        f"{cross_asset['dxy']['price']:.1f} ({cross_asset['dxy']['pct']:+.1f}%)"
        if cross_asset.get("dxy")
        else "data tidak tersedia"
    )
    return {
        "sp500_str": sp500_str,
        "vix_str": vix_str,
        "gold_str": gold_str,
        "oil_str": oil_str,
        "dxy_str": dxy_str,
    }


def _now_ts() -> float:
    return datetime.now(timezone.utc).timestamp()


SERPER_NEWS_URL = "https://google.serper.dev/news"

# Dedup judul berita yang sudah di-alert, 24 jam — persisted via
# notification_governor (ngov), namespace "news_title". Sebelumnya pakai dict
# in-memory (SENT_NEWS_TITLES) yang di-reset tiap restart proses, kelas bug
# yang sama dengan insiden 21 Juli (lihat NOTIFIKASI_MITIGASI_REPORT.md) —
# hanya belum pernah teramati aktif untuk job ini (lihat BERITA_MITIGASI_REPORT.md).
_NEWS_TITLE_DEDUP_SEC = 86400

BREAKING_KEYWORDS = [
    # Fed & rates
    "federal reserve",
    "fed rate cut",
    "fed rate hike",
    "fomc",
    "powell",
    "interest rate decision",
    "rate cut",
    "rate hike",
    "fed pivot",
    # Crypto regulasi
    "sec crypto",
    "etf approved",
    "etf rejected",
    "crypto ban",
    "crypto regulation",
    "bitcoin etf",
    "ethereum etf",
    # Exchange & hack
    "exchange hack",
    "exchange collapsed",
    "exchange bankrupt",
    "crypto hack",
    "exploit",
    "stolen crypto",
    "rug pull",
    "binance",
    "coinbase",
    "bybit",
    "okx",
    # Market events
    "liquidation cascade",
    "flash crash",
    "crypto crash",
    "all time high",
    "bitcoin ath",
    "ethereum ath",
    "short squeeze",
    "long squeeze",
    # Macro yang langsung impact crypto
    "cpi data",
    "inflation data",
    "jobs report",
    "nfp",
    "us sanctions",
    "crypto sanction",
    # Institutional
    "blackrock bitcoin",
    "fidelity bitcoin",
    "spot etf",
    "etf inflow",
    "etf outflow",
    "institutional bitcoin",
    # Geopolitical yang langsung impact
    "oil embargo",
    "iran war settlement",
    "iran ceasefire",
    "strait of hormuz",
    "etf launch",
    "etf listing",
    "stakes bitcoin",
    "stakes ethereum",
    "buys bitcoin",
    "buys ethereum",
    "million bitcoin",
    "million ethereum",
    "million in bitcoin",
    "million in ethereum",
    "billion bitcoin",
    "billion ethereum",
]

# Keyword yang TIDAK boleh trigger alert meski ada keyword di atas
BREAKING_BLACKLIST = [
    "mortgage",
    "real estate",
    "housing",
    "home price",
    "loan rate",
    "car loan",
    "student loan",
    "current price of",
    "price for april",
    "price for march",
    "how to buy",
    "what is bitcoin",
    "what is ethereum",
    "beginner guide",
    "spring 2026",
    "fall 2026",
]


def _prune_sent_news_titles() -> None:
    """Buang entri dedup berita yang lebih lama dari _NEWS_TITLE_DEDUP_SEC dari
    state persisten. Perlu dijalankan manual (beda dari cooldown per-coin di
    checker lain) karena key-nya per judul artikel — jumlahnya tidak terbatas
    seperti daftar coin, jadi kalau tidak di-prune, data/alert_cooldown_state.json
    tumbuh terus."""
    ngov.prune_cooldown_namespace("news_title", _NEWS_TITLE_DEDUP_SEC)


def _serper_news_fetch(query: str, num: int) -> list[dict[str, Any]]:
    key = os.getenv("SERPER_API_KEY", "")
    if not key:
        return []
    try:
        import httpx

        r = httpx.post(
            SERPER_NEWS_URL,
            headers={"X-API-KEY": key, "Content-Type": "application/json"},
            json={"q": query, "num": num, "tbs": "qdr:d"},
            timeout=8.0,
        )
        if r.status_code != 200:
            logging.warning("Serper news HTTP %s: %s", r.status_code, query[:40])
            return []
        data = r.json()
        if not isinstance(data, dict):
            return []
        raw = data.get("news") or data.get("organic") or []
        if not isinstance(raw, list):
            return []
        out: list[dict[str, Any]] = []
        for item in raw[:num]:
            if not isinstance(item, dict):
                continue
            src = item.get("source")
            if isinstance(src, dict):
                src = src.get("name", "") or ""
            out.append(
                {
                    "title": item.get("title", "") or "",
                    "snippet": item.get("snippet", "") or "",
                    "source": str(src or ""),
                    "link": item.get("link", "") or "",
                    "time": item.get("date", "") or item.get("time", "") or "",
                }
            )
        return out
    except Exception as e:  # noqa: BLE001
        logging.warning("_serper_news_fetch: %s", e)
        return []


def _fetch_crypto_news() -> list[dict[str, Any]]:
    key = os.getenv("NEWSAPI_KEY", "")
    if not key:
        logging.warning("_fetch_crypto_news: NEWSAPI_KEY tidak ada di env")
        return []
    try:
        import httpx

        _from_dt = (datetime.now(timezone.utc) - timedelta(hours=3)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        r = httpx.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": "bitcoin OR ethereum OR crypto",
                "sortBy": "publishedAt",
                "pageSize": 10,
                "language": "en",
                "from": _from_dt,
                "apiKey": key,
            },
            timeout=8.0,
        )
        if r.status_code != 200:
            logging.warning("NewsAPI crypto HTTP %s", r.status_code)
            return []
        articles = r.json().get("articles") or []
        logging.info("_fetch_crypto_news: %d artikel mentah dari NewsAPI", len(articles))
        out = []
        for item in articles[:10]:
            if not isinstance(item, dict):
                continue
            out.append({
                "title": item.get("title", "") or "",
                "snippet": item.get("description", "") or "",
                "source": (item.get("source") or {}).get("name", "") or "",
                "link": item.get("url", "") or "",
                "time": item.get("publishedAt", "") or "",
            })
        return out
    except Exception as e:  # noqa: BLE001
        logging.warning("_fetch_crypto_news: %s", e)
        return []


def _fetch_macro_news() -> list[dict[str, Any]]:
    key = os.getenv("NEWSAPI_KEY", "")
    if not key:
        logging.warning("_fetch_macro_news: NEWSAPI_KEY tidak ada di env")
        return []
    try:
        import httpx

        _from_dt = (datetime.now(timezone.utc) - timedelta(hours=3)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        r = httpx.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": "Federal Reserve OR interest rate OR inflation OR economy",
                "sortBy": "publishedAt",
                "pageSize": 5,
                "language": "en",
                "from": _from_dt,
                "apiKey": key,
            },
            timeout=8.0,
        )
        if r.status_code != 200:
            logging.warning("NewsAPI macro HTTP %s", r.status_code)
            return []
        articles = r.json().get("articles") or []
        logging.info("_fetch_macro_news: %d artikel mentah dari NewsAPI", len(articles))
        out = []
        for item in articles[:5]:
            if not isinstance(item, dict):
                continue
            out.append({
                "title": item.get("title", "") or "",
                "snippet": item.get("description", "") or "",
                "source": (item.get("source") or {}).get("name", "") or "",
                "link": item.get("url", "") or "",
                "time": item.get("publishedAt", "") or "",
            })
        return out
    except Exception as e:  # noqa: BLE001
        logging.warning("_fetch_macro_news: %s", e)
        return []


def _summarize_news_for_brief(news_items: list[dict]) -> str:
    import re as _re2
    if not news_items:
        return "Tidak ada berita terbaru yang tersedia."

    def _is_latin(text: str) -> bool:
        if not text:
            return True
        # Cek karakter non-Latin (Arab, Cina, Jepang, Korea, dll)
        non_latin = len(_re2.findall(r'[\u0600-\u06FF\u4E00-\u9FFF\u3040-\u309F\u30A0-\u30FF\uAC00-\uD7AF]', text))
        return non_latin / max(len(text), 1) < 0.1

    lines: list[str] = []
    for item in news_items[:10]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        snippet = str(item.get("snippet") or "").strip()
        source = str(item.get("source") or "").strip()
        if not _is_latin(title) or not _is_latin(snippet):
            continue
        snip = snippet[:100] + ("..." if len(snippet) > 100 else "")
        lines.append(f"- {title} ({source}): {snip}")
        if len(lines) >= 5:
            break
    if not lines:
        return "Tidak ada berita terbaru yang tersedia."
    return "\n".join(lines)
def _hits_breaking_blacklist(title: str, snippet: str) -> bool:
    blob = f"{title or ''} {snippet or ''}".lower()
    return any(bk in blob for bk in BREAKING_BLACKLIST)


def _hits_breaking_keyword(title: str, snippet: str) -> bool:
    blob = f"{title or ''} {snippet or ''}".lower()
    return any(kw in blob for kw in BREAKING_KEYWORDS)


def _is_breaking_news(title: str, snippet: str) -> bool:
    # Cek blacklist dulu — kalau ada blacklist keyword, langsung skip
    if _hits_breaking_blacklist(title, snippet):
        return False
    # Cek apakah ada breaking keyword
    return _hits_breaking_keyword(title, snippet)


def _translate_news_to_id(title: str, snippet: str) -> tuple[str, str]:
    """Translate judul dan snippet berita ke Bahasa Indonesia via LLM."""
    if ask_aliza is None:
        return title, snippet
    try:
        prompt = f"""Terjemahkan teks berita berikut ke Bahasa Indonesia yang natural dan ringkas.
Jaga nama proper (Bitcoin, Fed, SEC, dll) tetap dalam bentuk aslinya.
Jawab HANYA dengan format:
JUDUL: [terjemahan judul]
RINGKASAN: [terjemahan snippet, max 150 kata]

JUDUL ASLI: {title}
SNIPPET ASLI: {snippet[:300]}"""
        result = str(ask_aliza(prompt)).strip()
        title_id = title
        snippet_id = snippet
        for line in result.split("\n"):
            if line.startswith("JUDUL:"):
                title_id = line.replace("JUDUL:", "").strip()
            elif line.startswith("RINGKASAN:"):
                snippet_id = line.replace("RINGKASAN:", "").strip()
        return title_id, snippet_id
    except Exception:
        return title, snippet


async def breaking_news_job(context: ContextTypes.DEFAULT_TYPE):
    """Cek berita breaking ~1 jam; maks 3 alert per run; dedup 24h (persisted
    via notification_governor, namespace "news_title")."""
    logging.info("breaking_news_job: scan start")
    chat_id = None
    try:
        if context and getattr(context, "bot_data", None):
            chat_id = context.bot_data.get("chat_id")
    except Exception:
        chat_id = None
    if not chat_id:
        chat_id = DEFAULT_CHAT_ID
    if not chat_id:
        logging.warning("breaking_news_job: no chat_id")
        return

    _prune_sent_news_titles()

    crypto_news: list[dict[str, Any]] = []
    macro_news: list[dict[str, Any]] = []
    try:
        crypto_news = _fetch_crypto_news()
    except Exception as e:  # noqa: BLE001
        logging.warning("breaking_news_job crypto: %s", e)
    try:
        macro_news = _fetch_macro_news()
    except Exception as e:  # noqa: BLE001
        logging.warning("breaking_news_job macro: %s", e)

    combined = crypto_news + macro_news
    sent = 0
    n_total = len(combined)
    n_blacklisted = 0
    n_not_breaking = 0
    n_stale = 0
    n_dedup_skipped = 0
    n_dispatch_failed = 0
    for item in combined:
        if sent >= 3:
            break
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        snippet = str(item.get("snippet") or "").strip()
        if not title:
            continue
        if _hits_breaking_blacklist(title, snippet):
            n_blacklisted += 1
            continue
        if not _hits_breaking_keyword(title, snippet):
            n_not_breaking += 1
            continue
        # Skip berita lama (>3 jam)
        time_str = str(item.get("time") or "").lower()
        # Coba parse ISO timestamp (format NewsAPI: "2026-05-06T00:25:32Z")
        _news_skipped = False
        if "t" in time_str and ("z" in time_str or "+" in time_str):
            try:
                _pub = datetime.fromisoformat(
                    str(item.get("time") or "").replace("Z", "+00:00")
                )
                _age_hours = (datetime.now(timezone.utc) - _pub).total_seconds() / 3600
                if _age_hours > 3:
                    _news_skipped = True
            except Exception:  # noqa: BLE001
                pass
        if _news_skipped:
            n_stale += 1
            continue
        # Fallback: format lama "2 hours ago" dari Serper
        if "hour" in time_str:
            try:
                hours_ago = int(time_str.split()[0])
                if hours_ago > 3:
                    n_stale += 1
                    continue
            except Exception:
                pass
        if "day" in time_str or "week" in time_str:
            n_stale += 1
            continue
        key = title[:400]
        if not ngov.is_cooldown_allowed("news_title", key, _NEWS_TITLE_DEDUP_SEC):
            n_dedup_skipped += 1
            continue
        src = str(item.get("source") or "—")
        time_s = str(item.get("time") or "—")
        # Translate ke Bahasa Indonesia
        title_id, snip_id = _translate_news_to_id(title, snippet[:300])
        msg = (
            "🚨 BREAKING NEWS\n"
            f"{title_id}\n\n"
            f"{snip_id}\n\n"
            f"Sumber: {src} • {time_s}\n"
            "⚠️ Monitor dampak ke market crypto."
        )
        try:
            await safe_dispatch(msg, chat_id=chat_id, force=False)
            ngov.record_cooldown("news_title", key)
            sent += 1
        except Exception as e:  # noqa: BLE001
            n_dispatch_failed += 1
            logging.warning("breaking_news_job dispatch: %s", e)

    logging.info(
        "breaking_news_job: scan done, alerts_sent=%s "
        "(total=%s blacklisted=%s not_breaking=%s stale=%s dedup_skipped=%s dispatch_failed=%s)",
        sent,
        n_total,
        n_blacklisted,
        n_not_breaking,
        n_stale,
        n_dedup_skipped,
        n_dispatch_failed,
    )


def _funding_projection_block_from_coin_details(
    coin_details: dict[str, Any],
) -> tuple[dict[str, float | None], str]:
    funding_projection: dict[str, float | None] = {}
    for _fc in ("BTC", "ETH", "BNB", "SOL", "XRP"):
        _frd = coin_details.get(_fc, {}).get("funding_rate")
        if _frd is not None:
            try:
                funding_projection[_fc] = round(float(_frd) * 9 * 100, 4)
            except (TypeError, ValueError):
                funding_projection[_fc] = None
        else:
            funding_projection[_fc] = None

    def _fp_disp(_c: str) -> str:
        _v = funding_projection.get(_c)
        if _v is None:
            return "N/A"
        return f"{_v}%"

    block = (
        "FUNDING COST PROJECTION (hold 3 hari):\n"
        f"BTC: {_fp_disp('BTC')} | ETH: {_fp_disp('ETH')}\n"
        f"SOL: {_fp_disp('SOL')} | BNB: {_fp_disp('BNB')} | XRP: {_fp_disp('XRP')}"
    )
    return funding_projection, block


def _build_coin_details_for_brief(brief_data: dict) -> tuple[dict[str, Any], str]:
    """Snapshot + funding_map → coin_details dan detail_block (satu string)."""
    snapshot_data: dict[str, Any] = {}
    try:
        _snap = get_market_snapshot()
        snapshot_data = _snap.get("data") or {}
        if not isinstance(snapshot_data, dict):
            snapshot_data = {}
    except Exception as e:  # noqa: BLE001
        logging.warning("_build_coin_details_for_brief: snapshot: %s", e)
        snapshot_data = {}

    funding_map = brief_data.get("funding_rates") or {}
    if not isinstance(funding_map, dict):
        funding_map = {}

    coin_details: dict[str, Any] = {}
    detail_lines: list[str] = []
    for _coin in ("BTC", "ETH", "BNB", "SOL", "XRP"):
        _cd = snapshot_data.get(_coin, {})
        _fr_raw = None
        if isinstance(funding_map.get(_coin), dict):
            _fr_raw = (funding_map.get(_coin) or {}).get("funding_rate")

        if not isinstance(_cd, dict) or not _cd:
            coin_details[_coin] = {
                "price": None,
                "pct_24h": None,
                "rsi": None,
                "trend": None,
                "support": None,
                "resistance": None,
                "funding_rate": _fr_raw,
                "note": "data tidak tersedia",
            }
            detail_lines.append(f"{_coin} | data tidak tersedia")
            continue

        _p24 = _cd.get("price_change_percentage_24h")
        if _p24 is None:
            _p24 = _cd.get("change_24h_pct")
        if _p24 is None:
            _p24 = _cd.get("price_change_24h")

        coin_details[_coin] = {
            "price": _cd.get("price"),
            "pct_24h": _p24,
            "rsi": _cd.get("rsi"),
            "trend": _cd.get("trend"),
            "support": _cd.get("support"),
            "resistance": _cd.get("resistance"),
            "funding_rate": _fr_raw,
        }

        try:
            _pxs = f"{float(_cd.get('price')):,.2f}" if _cd.get("price") is not None else "—"
        except (TypeError, ValueError):
            _pxs = "—"
        try:
            _p24s = f"{float(_p24):+.2f}%" if _p24 is not None else "—"
        except (TypeError, ValueError):
            _p24s = "—"
        _rsi = _cd.get("rsi")
        try:
            _rsis = f"{float(_rsi):.1f}" if _rsi is not None else "—"
        except (TypeError, ValueError):
            _rsis = str(_rsi) if _rsi is not None else "—"
        _tr = _cd.get("trend") or "—"
        try:
            _sups = f"{float(_cd.get('support')):,.2f}" if _cd.get("support") is not None else "—"
        except (TypeError, ValueError):
            _sups = "—"
        try:
            _ress = f"{float(_cd.get('resistance')):,.2f}" if _cd.get("resistance") is not None else "—"
        except (TypeError, ValueError):
            _ress = "—"
        try:
            _frs = f"{float(_fr_raw) * 100:.4f}%" if _fr_raw is not None else "—"
        except (TypeError, ValueError):
            _frs = "—"

        detail_lines.append(
            f"{_coin} | Harga: {_pxs} | 24h: {_p24s} | RSI: {_rsis} | Trend: {_tr} | "
            f"Support: {_sups} | Resistance: {_ress} | FR: {_frs}"
        )

    detail_block = "\n".join(detail_lines) if detail_lines else "(tidak ada baris detail)"
    return coin_details, detail_block


async def _call_llm_async(prompt: str) -> str:
    """Panggil ask_aliza di executor; timeout 90s per call."""
    if ask_aliza is None:
        return ""

    def _call() -> str:
        # Prefix "CHAT:" memastikan detect_intent routing ke chat, bukan math
        # karena prompt LLM mengandung simbol +/-/* yang bisa trigger math intent
        prefixed = "CHAT_OVERRIDE: " + prompt
        return str(ask_aliza(prefixed))

    _prompt_tokens_est = len(prompt) // 4  # estimasi kasar
    if _prompt_tokens_est > 10000:
        logging.warning("_call_llm_async: prompt besar ~%d tokens", _prompt_tokens_est)

    try:
        loop = asyncio.get_running_loop()
        out = await asyncio.wait_for(loop.run_in_executor(None, _call), timeout=90.0)
        return str(out).strip()
    except asyncio.TimeoutError:
        logging.warning("_call_llm_async: timeout (90s)")
    except Exception as e:  # noqa: BLE001
        logging.warning("_call_llm_async: %s", e)
    return ""


async def _generate_spot_analysis(
    brief_data: dict,
    coin_details: dict[str, Any],
    *,
    _cross_bundle: dict[str, str] | None = None,
) -> str:
    """Satu pemanggilan LLM: hanya section 🟢 SARAN SPOT."""
    _lines: list[str] = []
    for _coin in ("BTC", "ETH", "BNB", "SOL", "XRP"):
        cd = coin_details.get(_coin) or {}
        if cd.get("note") == "data tidak tersedia":
            _lines.append(f"{_coin} | data tidak tersedia")
            continue
        try:
            _pxs = f"{float(cd.get('price')):,.2f}" if cd.get("price") is not None else "—"
        except (TypeError, ValueError):
            _pxs = "—"
        _p24 = cd.get("pct_24h")
        try:
            _p24s = f"{float(_p24):+.2f}%" if _p24 is not None else "—"
        except (TypeError, ValueError):
            _p24s = "—"
        _rsi = cd.get("rsi")
        try:
            _rsis = f"{float(_rsi):.1f}" if _rsi is not None else "—"
        except (TypeError, ValueError):
            _rsis = str(_rsi) if _rsi is not None else "—"
        _tr = cd.get("trend") or "—"
        try:
            _sups = f"{float(cd.get('support')):,.2f}" if cd.get("support") is not None else "—"
        except (TypeError, ValueError):
            _sups = "—"
        try:
            _ress = f"{float(cd.get('resistance')):,.2f}" if cd.get("resistance") is not None else "—"
        except (TypeError, ValueError):
            _ress = "—"
        _fr_raw = cd.get("funding_rate")
        try:
            _frs = f"{float(_fr_raw) * 100:.4f}%" if _fr_raw is not None else "—"
        except (TypeError, ValueError):
            _frs = "—"
        _lines.append(
            f"{_coin} | Harga: {_pxs} | 24h: {_p24s} | RSI: {_rsis} | Trend: {_tr} | "
            f"Support: {_sups} | Resistance: {_ress} | FR: {_frs}"
        )
    detail_block = "\n".join(_lines) if _lines else "(tidak ada baris detail)"

    if _cross_bundle is None:
        try:
            cross_asset = _get_cross_asset_data()
        except Exception:  # noqa: BLE001
            cross_asset = {"dxy": None, "gold": None, "oil": None, "sp500": None, "vix": None}
        cx = _format_cross_asset_strings(cross_asset)
    else:
        cx = _cross_bundle

    score = brief_data.get("market_score")
    label = brief_data.get("market_label") or "—"
    fg = brief_data.get("fear_greed")
    dom = brief_data.get("btc_dominance")
    fg_label = "—"
    try:
        if fg is not None:
            fg_label = _fear_greed_label(float(fg))
    except (TypeError, ValueError):
        pass
    fg_s = str(int(round(float(fg)))) if fg is not None else "—"
    dom_s = f"{float(dom):.2f}" if dom is not None else "—"

    funding_rates = brief_data.get("funding_rates") or {}
    avg_fr, fr_bias = _avg_funding_fr_pct_and_bias(
        funding_rates if isinstance(funding_rates, dict) else {}
    )

    macro = brief_data.get("macro") or {}
    if not isinstance(macro, dict):
        macro = {}
    cpi_s = f"{float(macro.get('cpi_yoy_pct')):.2f}" if macro.get("cpi_yoy_pct") is not None else "—"
    fed_s = f"{float(macro.get('fed_rate_pct')):.2f}" if macro.get("fed_rate_pct") is not None else "—"

    sig = brief_data.get("active_signal")
    if sig and isinstance(sig, dict):
        s_coin = sig.get("coin", "—")
        s_setup = sig.get("setup", "—")
        s_conf = sig.get("confidence")
        sig_txt = f"{s_coin} {s_setup} (conf {s_conf})"
    else:
        sig_txt = "tidak ada"

    events = brief_data.get("events_tomorrow")
    if not isinstance(events, list):
        events = []
    ev_txt = _format_events_for_prompt(events)
    ctx_sum = str(brief_data.get("context_summary") or "").strip() or "—"

    data_market_block = f"""Market Score: {score}/100 — {label}
Fear & Greed: {fg_s} ({fg_label})
BTC Dominance: {dom_s}%
Funding Rate avg: {avg_fr}% ({fr_bias})
CPI YoY: {cpi_s}% | Fed Rate: {fed_s}%
Sinyal aktif: {sig_txt}
Event besok: {ev_txt}
Konteks: {ctx_sum}

CROSS-ASSET:
S&P 500: {cx['sp500_str']}
VIX: {cx['vix_str']}
Gold: {cx['gold_str']}
Oil WTI: {cx['oil_str']}
DXY: {cx['dxy_str']}"""

    # Pre-compute action berdasarkan data
    _score = score if score is not None else 50
    _fg = float(fg) if fg is not None else 50
    if _score < 40 or _fg < 25:
        _action_constraint = "TAHAN — JANGAN rekomendasikan entry baru. Tulis: Tidak ada setup spot yang layak — tunggu pullback ke support."
    elif _score < 50 or _fg < 35:
        _action_constraint = "SELEKTIF — hanya rekomendasikan entry jika harga sudah di level support, bukan entry sekarang."
    else:
        _action_constraint = "NORMAL — rekomendasikan setup terbaik sesuai kondisi teknikal."

    prompt = f"""---
Kamu adalah Aliza, AI trading assistant untuk swing trading (1-7 hari).
Berikan HANYA saran spot trading dalam Bahasa Indonesia.

DATA MARKET:
{data_market_block}

KEPUTUSAN HARI INI (WAJIB DIIKUTI):
{_action_constraint}

DETAIL PER COIN:
{detail_block}

VALIDATION RULES:
RULE 1: Jika market_score < 40 ATAU fear_greed < 25: entry HANYA di support, bukan harga sekarang
RULE 2: Jika sinyal aktif = tidak ada: tulis "Entry HANYA jika pullback ke [support]"
RULE 3: SL wajib 5-8% dari entry
RULE 4: RR minimum 2.0x
RULE 5: Jika >=2 coin: tambahkan correlation warning

OUTPUT FORMAT (HANYA section ini, tidak ada section lain):
🟢 SARAN SPOT (Swing 1-7 hari)
[Jika tidak ada setup: "Tidak ada setup spot yang layak — tunggu pullback ke support."]
[Jika ada setup, maksimal 3 coin terbaik:]

• [COIN] [LABEL]
  Entry ideal: $[support] — tunggu harga ke sini
  Entry sekarang: $[harga] [LAYAK/KURANG IDEAL/TIDAK DISARANKAN]
  SL: $[level] ([X]% dari entry)
  Target 1: $[level] (+[X]%) — ambil 50%
  Target 2: $[level] (+[X]%) — ambil sisa
  RR: [hitung: (T1-Entry)/(Entry-SL)]
  Timeframe: [estimasi hari]
  Invalidasi: [kondisi yang membatalkan]

Hanya gunakan coin spot (BTC, ETH, BNB, SOL, XRP). Jangan tulis section futures.
Jawab HANYA dengan section 🟢 SARAN SPOT di atas, tanpa pembuka, tanpa penutup.
---"""

    if ask_aliza is None:
        return (
            "🟢 SARAN SPOT (Swing 1-7 hari)\n"
            "Tidak ada setup spot yang layak — tunggu pullback ke support.\n"
            "(Modul AI tidak tersedia — analisis otomatis dilewati.)"
        )

    out = await _call_llm_async(prompt)
    if out:
        return out
    return (
        "🟢 SARAN SPOT (Swing 1-7 hari)\n"
        "Tidak ada setup spot yang layak — tunggu pullback ke support. (LLM timeout/error)"
    )


async def _generate_futures_analysis(
    brief_data: dict,
    coin_details: dict[str, Any],
    *,
    _cross_bundle: dict[str, str] | None = None,
) -> str:
    """Satu pemanggilan LLM: hanya section 📊 SARAN FUTURES."""
    _lines: list[str] = []
    for _coin in ("BTC", "ETH", "BNB", "SOL", "XRP"):
        cd = coin_details.get(_coin) or {}
        if cd.get("note") == "data tidak tersedia":
            _lines.append(f"{_coin} | data tidak tersedia")
            continue
        try:
            _pxs = f"{float(cd.get('price')):,.2f}" if cd.get("price") is not None else "—"
        except (TypeError, ValueError):
            _pxs = "—"
        _p24 = cd.get("pct_24h")
        try:
            _p24s = f"{float(_p24):+.2f}%" if _p24 is not None else "—"
        except (TypeError, ValueError):
            _p24s = "—"
        _rsi = cd.get("rsi")
        try:
            _rsis = f"{float(_rsi):.1f}" if _rsi is not None else "—"
        except (TypeError, ValueError):
            _rsis = str(_rsi) if _rsi is not None else "—"
        _tr = cd.get("trend") or "—"
        try:
            _sups = f"{float(cd.get('support')):,.2f}" if cd.get("support") is not None else "—"
        except (TypeError, ValueError):
            _sups = "—"
        try:
            _ress = f"{float(cd.get('resistance')):,.2f}" if cd.get("resistance") is not None else "—"
        except (TypeError, ValueError):
            _ress = "—"
        _fr_raw = cd.get("funding_rate")
        try:
            _frs = f"{float(_fr_raw) * 100:.4f}%" if _fr_raw is not None else "—"
        except (TypeError, ValueError):
            _frs = "—"
        _lines.append(
            f"{_coin} | Harga: {_pxs} | 24h: {_p24s} | RSI: {_rsis} | Trend: {_tr} | "
            f"Support: {_sups} | Resistance: {_ress} | FR: {_frs}"
        )
    detail_block = "\n".join(_lines) if _lines else "(tidak ada baris detail)"

    if _cross_bundle is None:
        try:
            cross_asset = _get_cross_asset_data()
        except Exception:  # noqa: BLE001
            cross_asset = {"dxy": None, "gold": None, "oil": None, "sp500": None, "vix": None}
        cx = _format_cross_asset_strings(cross_asset)
    else:
        cx = _cross_bundle

    _, funding_proj_block = _funding_projection_block_from_coin_details(coin_details)

    score = brief_data.get("market_score")
    label = brief_data.get("market_label") or "—"
    fg = brief_data.get("fear_greed")
    dom = brief_data.get("btc_dominance")
    fg_label = "—"
    try:
        if fg is not None:
            fg_label = _fear_greed_label(float(fg))
    except (TypeError, ValueError):
        pass
    fg_s = str(int(round(float(fg)))) if fg is not None else "—"
    dom_s = f"{float(dom):.2f}" if dom is not None else "—"

    funding_rates = brief_data.get("funding_rates") or {}
    avg_fr, fr_bias = _avg_funding_fr_pct_and_bias(
        funding_rates if isinstance(funding_rates, dict) else {}
    )

    macro = brief_data.get("macro") or {}
    if not isinstance(macro, dict):
        macro = {}
    cpi_s = f"{float(macro.get('cpi_yoy_pct')):.2f}" if macro.get("cpi_yoy_pct") is not None else "—"
    fed_s = f"{float(macro.get('fed_rate_pct')):.2f}" if macro.get("fed_rate_pct") is not None else "—"

    sig = brief_data.get("active_signal")
    if sig and isinstance(sig, dict):
        s_coin = sig.get("coin", "—")
        s_setup = sig.get("setup", "—")
        s_conf = sig.get("confidence")
        sig_txt = f"{s_coin} {s_setup} (conf {s_conf})"
    else:
        sig_txt = "tidak ada"

    events = brief_data.get("events_tomorrow")
    if not isinstance(events, list):
        events = []
    ev_txt = _format_events_for_prompt(events)
    ctx_sum = str(brief_data.get("context_summary") or "").strip() or "—"

    data_market_block = f"""Market Score: {score}/100 — {label}
Fear & Greed: {fg_s} ({fg_label})
BTC Dominance: {dom_s}%
Funding Rate avg: {avg_fr}% ({fr_bias})
CPI YoY: {cpi_s}% | Fed Rate: {fed_s}%
Sinyal aktif: {sig_txt}
Event besok: {ev_txt}
Konteks: {ctx_sum}

CROSS-ASSET:
S&P 500: {cx['sp500_str']}
VIX: {cx['vix_str']}
Gold: {cx['gold_str']}
Oil WTI: {cx['oil_str']}
DXY: {cx['dxy_str']}"""

    # Pre-compute action berdasarkan data
    _score = score if score is not None else 50
    _fg = float(fg) if fg is not None else 50
    if _score < 40 or _fg < 25:
        _action_constraint = "TAHAN — JANGAN rekomendasikan futures. Tulis: Kondisi tidak mendukung futures saat ini."
    elif _score < 50 or _fg < 35:
        _action_constraint = "SELEKTIF — hanya SHORT jika trend jelas bearish, atau tidak ada rekomendasi."
    else:
        _action_constraint = "NORMAL — rekomendasikan setup futures terbaik sesuai kondisi teknikal."

    prompt = f"""---
Kamu adalah Aliza, AI trading assistant untuk swing trading (1-7 hari).
Berikan HANYA saran futures trading dalam Bahasa Indonesia.

DATA MARKET:
{data_market_block}

KEPUTUSAN HARI INI (WAJIB DIIKUTI):
{_action_constraint}

DETAIL PER COIN:
{detail_block}

FUNDING COST PROJECTION (hold 3 hari):
{funding_proj_block}

VALIDATION RULES:
RULE 1: Jika market_score < 40 ATAU fear_greed < 25: tulis "Kondisi tidak mendukung futures saat ini"
RULE 2: SL wajib 5-8% dari entry
RULE 3: RR minimum 2.0x
RULE 4: Leverage maksimal 5x, rekomendasi 2-3x untuk swing
RULE 5: Sertakan estimasi funding cost 3 hari

OUTPUT FORMAT (HANYA section ini):
📊 SARAN FUTURES (Swing 1-7 hari)
[Jika kondisi tidak mendukung: "📊 SARAN FUTURES (Swing 1-7 hari)
Kondisi tidak mendukung futures saat ini."]
[Jika ada setup:]

• [COIN]: [LONG/SHORT]
  Entry: $[level] — konfirmasi dulu sebelum entry
  SL: $[level] ([X]% dari entry)
  Target 1: $[level] (+[X]%) — ambil 50%
  Target 2: $[level] (+[X]%) — ambil sisa
  Leverage: [2-5x]
  RR: [hitung: (T1-Entry)/(Entry-SL)]
  Funding est. 3 hari: [dari data yang diberikan]%
  Invalidasi: [kondisi yang membatalkan]

⚠️ Futures berisiko tinggi. Gunakan leverage rendah dan selalu pasang SL.

Hanya futures untuk BTC, ETH, BNB, SOL, XRP. Jangan campur saran spot.
Jawab HANYA dengan section 📊 SARAN FUTURES di atas, tanpa pembuka, tanpa penutup.
---"""

    if ask_aliza is None:
        return (
            "📊 SARAN FUTURES (Swing 1-7 hari)\n"
            "Kondisi tidak mendukung futures saat ini.\n\n"
            "⚠️ Futures berisiko tinggi. Gunakan leverage rendah dan selalu pasang SL.\n"
            "(Modul AI tidak tersedia — analisis otomatis dilewati.)"
        )

    out = await _call_llm_async(prompt)
    if out:
        return out
    return (
        "📊 SARAN FUTURES (Swing 1-7 hari)\n"
        "Kondisi tidak mendukung futures saat ini. (LLM timeout/error)\n\n"
        "⚠️ Futures berisiko tinggi. Gunakan leverage rendah dan selalu pasang SL."
    )


async def _generate_brief_analysis(brief_data: dict) -> str:
    """
    Bangun prompt dari brief_data: 6 section utama + spot + futures (3x LLM paralel).
    """
    coin_details, detail_block = _build_coin_details_for_brief(brief_data)
    brief_data["coin_details"] = coin_details

    try:
        cross_asset = _get_cross_asset_data()
    except Exception:  # noqa: BLE001
        cross_asset = {"dxy": None, "gold": None, "oil": None, "sp500": None, "vix": None}
    cross_bundle = _format_cross_asset_strings(cross_asset)

    if ask_aliza is None:
        return (
            "⚡ KEPUTUSAN HARI INI\n"
            "Regime: —\n"
            "Bias: —\n"
            "Conviction: —/10 — Modul AI tidak tersedia.\n"
            "Action: ⏸️ TAHAN\n"
            "Catalyst: —\n\n"
            "📊 KONTEKS MARKET\n"
            "Modul AI tidak tersedia — gunakan data di brief sebagai acuan.\n"
            "Cross-asset: data tidak tersedia (cek sumber eksternal).\n\n"
            "🎯 STRATEGI HARI INI\n"
            "Pantau harga dan manajemen risiko; tunggu konfirmasi sebelum menambah exposure.\n\n"
            "⚠️ YANG HARUS DIHINDARI\n"
            "Over-leverage tanpa konfirmasi.\n\n"
            "🚨 LEVEL & CATALYST PENTING\n"
            "Pantau level SL/TP dan rilis data makro sesuai kalender.\n\n"
            "🟢 SARAN SPOT (Swing 1-7 hari)\n"
            "Tidak ada setup spot yang layak — tunggu pullback ke support.\n\n"
            "📊 SARAN FUTURES (Swing 1-7 hari)\n"
            "Kondisi tidak mendukung futures saat ini.\n\n"
            "⚠️ DISCLAIMER\n"
            "Analisis teknikal swing trading dari sistem Aliza, bukan saran investasi.\n"
            "Selalu pasang SL dan gunakan sizing sesuai risk tolerance.\n"
            "(Modul AI tidak tersedia — analisis otomatis dilewati.)"
        )

    sp500_str = cross_bundle["sp500_str"]
    vix_str = cross_bundle["vix_str"]
    gold_str = cross_bundle["gold_str"]
    oil_str = cross_bundle["oil_str"]
    dxy_str = cross_bundle["dxy_str"]

    score = brief_data.get("market_score")
    label = brief_data.get("market_label") or "—"
    fg = brief_data.get("fear_greed")
    dom = brief_data.get("btc_dominance")
    fg_label = "—"
    try:
        if fg is not None:
            fg_label = _fear_greed_label(float(fg))
    except (TypeError, ValueError):
        pass
    fg_s = str(int(round(float(fg)))) if fg is not None else "—"
    dom_s = f"{float(dom):.2f}" if dom is not None else "—"

    funding_rates = brief_data.get("funding_rates") or {}
    avg_fr, fr_bias = _avg_funding_fr_pct_and_bias(
        funding_rates if isinstance(funding_rates, dict) else {}
    )

    macro = brief_data.get("macro") or {}
    if not isinstance(macro, dict):
        macro = {}
    cpi_s = f"{float(macro.get('cpi_yoy_pct')):.2f}" if macro.get("cpi_yoy_pct") is not None else "—"
    fed_s = f"{float(macro.get('fed_rate_pct')):.2f}" if macro.get("fed_rate_pct") is not None else "—"

    sig = brief_data.get("active_signal")
    if sig and isinstance(sig, dict):
        s_coin = sig.get("coin", "—")
        s_setup = sig.get("setup", "—")
        s_conf = sig.get("confidence")
        sig_txt = f"{s_coin} {s_setup} (conf {s_conf})"
    else:
        sig_txt = "tidak ada"

    events = brief_data.get("events_tomorrow")
    if not isinstance(events, list):
        events = []
    ev_txt = _format_events_for_prompt(events)
    ctx_sum = str(brief_data.get("context_summary") or "").strip() or "—"

    try:
        crypto_news = _fetch_crypto_news()
        macro_news = _fetch_macro_news()
        all_news = (crypto_news + macro_news)[:8]
        news_block = _summarize_news_for_brief(all_news)
    except Exception as e:  # noqa: BLE001
        logging.warning("_generate_brief_analysis news fetch: %s", e)
        news_block = "Data berita tidak tersedia saat ini."

    try:
        st_mi = _get_stablecoin_data()
        dr_mi = _get_deribit_options()
        cb_mi = _get_coinbase_premium()
    except Exception as e:  # noqa: BLE001
        logging.warning("_generate_brief_analysis market intelligence: %s", e)
        st_mi = {"interpretation": "Data tidak tersedia", "usdt_dominance": None}
        dr_mi = {
            "interpretation": "Data tidak tersedia",
            "put_call_ratio": None,
            "max_pain": None,
        }
        cb_mi = {"interpretation": "Data tidak tersedia", "premium_pct": None}

    _mi_usdt = st_mi.get("usdt_dominance")
    mi_usdt_s = f"{float(_mi_usdt):.2f}" if _mi_usdt is not None else "N/A"
    mi_st_int = str(st_mi.get("interpretation") or "—")
    _mi_ratio = dr_mi.get("put_call_ratio")
    mi_ratio_s = f"{float(_mi_ratio):.3f}" if _mi_ratio is not None else "N/A"
    _mi_mp = dr_mi.get("max_pain")
    mi_mp_s = f"{float(_mi_mp):,.0f}" if _mi_mp is not None else "N/A"
    _mi_ppc = cb_mi.get("premium_pct")
    mi_ppc_s = f"{float(_mi_ppc):.4f}" if _mi_ppc is not None else "N/A"
    mi_cb_int = str(cb_mi.get("interpretation") or "—")

    market_intel_prompt = (
        f"MARKET INTELLIGENCE:\n"
        f"Stablecoin USDT: {mi_usdt_s}% | {mi_st_int}\n"
        f"Options Put/Call: {mi_ratio_s} | Max Pain: ${mi_mp_s}\n"
        f"Coinbase Premium: {mi_ppc_s}% | {mi_cb_int}"
    )

    try:
        inst_mi = _get_institutional_data()
    except Exception as e:  # noqa: BLE001
        logging.warning("_generate_brief_analysis institutional: %s", e)
        inst_mi = {
            "etf_flow_usd_m": None,
            "etf_flow_7d_usd_m": None,
            "etf_sentiment": "Data ETF flow tidak tersedia hari ini",
            "netflow_btc": None,
            "netflow_sentiment": "Data netflow tidak tersedia",
            "liq_above": None,
            "liq_below": None,
        }
    _ief = inst_mi.get("etf_flow_usd_m")
    _ief7 = inst_mi.get("etf_flow_7d_usd_m")
    inst_etf_s = f"{float(_ief):.2f}" if _ief is not None else "N/A"
    inst_etf7_s = f"{float(_ief7):.2f}" if _ief7 is not None else "N/A"
    _inf = inst_mi.get("netflow_btc")
    inst_nf_s = f"{float(_inf):,.0f}" if _inf is not None else "N/A"
    _ila = inst_mi.get("liq_above")
    _ilb = inst_mi.get("liq_below")
    inst_la_s = f"{float(_ila):,.0f}" if _ila is not None else "N/A"
    inst_lb_s = f"{float(_ilb):,.0f}" if _ilb is not None else "N/A"
    institutional_prompt = (
        "INSTITUTIONAL DATA (estimasi):\n"
        f"ETF Flow hari ini: {inst_etf_s}M | 7 hari: {inst_etf7_s}M | "
        f"{inst_mi.get('etf_sentiment', '—')}\n"
        f"BTC Exchange Netflow: {inst_nf_s} BTC | "
        f"{inst_mi.get('netflow_sentiment', '—')}\n"
        f"Liquidation zones: atas ${inst_la_s} | bawah ${inst_lb_s}\n"
        "Gunakan data ini untuk memperkuat analisis sentimen institusional."
    )

    # Hitung conviction di kode — LLM wajib pakai nilai ini (prompt utama saja)
    try:
        _score = int(score) if score is not None else 50
        _fg = int(float(fg)) if fg is not None else 50
        _has_signal = bool(sig and isinstance(sig, dict))
        if _score >= 70:
            _conviction = 7
        elif _score >= 55:
            _conviction = 5
        elif _score >= 45:
            _conviction = 4
        elif _score >= 30:
            _conviction = 3
        else:
            _conviction = 2
        if _fg < 25:
            _conviction = max(1, _conviction - 2)
        elif _fg < 35:
            _conviction = max(1, _conviction - 1)
        if _has_signal:
            _conviction = min(9, _conviction + 1)
        conviction_preset = _conviction
    except Exception:
        conviction_preset = 4

    main_prompt = f"""---
Kamu adalah Aliza, AI trading assistant untuk swing trading (1-7 hari).
Berikan analisis dalam Bahasa Indonesia yang KONSISTEN INTERNAL.

DATA MARKET:
Market Score: {score}/100 — {label}
Fear & Greed: {fg_s} ({fg_label})
BTC Dominance: {dom_s}%
Funding Rate avg: {avg_fr}% ({fr_bias})
CPI YoY: {cpi_s}% | Fed Rate: {fed_s}%
Sinyal aktif: {sig_txt}
Event besok: {ev_txt}
Konteks: {ctx_sum}

BERITA TERBARU (24 jam):
{news_block}

Gunakan BERITA TERBARU untuk memperkuat analisis di KONTEKS MARKET dan LEVEL & CATALYST PENTING. Jika ada berita yang sangat relevan, sebutkan secara eksplisit.

CROSS-ASSET:
S&P 500: {sp500_str}
VIX: {vix_str}
Gold: {gold_str}
Oil WTI: {oil_str}
DXY: {dxy_str}

{market_intel_prompt}

{institutional_prompt}

DETAIL PER COIN:
{detail_block}

VALIDATION RULES — WAJIB DIIKUTI:
RULE 1: Jika market_score < 40 ATAU fear_greed < 25 ATAU label Bearish/Weak:
  → ACTION harus TAHAN atau KURANGI EXPOSURE
  → Conviction maksimal 4/10
  → Entry spot HANYA di level support, bukan harga sekarang

RULE 1A: Jika fear_greed < 25 (Extreme Fear):
  → WAJIB sebutkan implikasi kontrarian secara eksplisit sebelum menyimpulkan bias:
    fear ekstrem historis sering berada dekat area jenuh jual, namun tunggu konfirmasi reversal sebelum menaikkan keyakinan.
  → Rule ACTION defensif, Conviction maksimal 4/10, dan entry hanya di level support dari RULE 1 tetap berlaku.

RULE 1B: Jika fear_greed > 75 (Extreme Greed):
  → WAJIB sebutkan risiko euforia/blow-off top secara eksplisit sebelum menyimpulkan bias.
  → ACTION condong defensif untuk ENTRY BARU, bukan untuk profit-taking posisi existing.
  → Conviction untuk entry baru maksimal 4/10.

RULE 2: Jika ada rekomendasi BELI/LONG tapi sinyal aktif = tidak ada:
  → Wajib tulis "Entry HANYA jika harga pullback ke [support]"
  → JANGAN entry di harga sekarang jika jauh dari support >3%

RULE 3: market_score 40-60 (Neutral):
  → ACTION: SELEKTIF — hanya coin terbaik, sizing kecil
  → Conviction maksimal 6/10

RULE 4: Jika market_score > 60 (Bullish):
  → ACTION boleh BELI BERTAHAP
  → Conviction bisa sampai 8/10

RULE 5: Jika >2 rekomendasi LONG bersamaan:
  → Tambahkan: "⚠️ Korelasi tinggi — jangan buka semua sekaligus"

FORMAT OUTPUT (6 section saja — JANGAN tulis saran spot atau futures):

⚡ KEPUTUSAN HARI INI
Regime: [Trending Bullish / Ranging / Risk-Off Sideways / Trending Bearish]
Bias: [Bullish / Neutral-Bullish / Neutral / Neutral-Bearish / Bearish]
Conviction: {conviction_preset}/10 — [1 kalimat justifikasi, JANGAN ubah angka {conviction_preset}]
Action: [🟢 BELI BERTAHAP / 🟡 SELEKTIF / ⏸️ TAHAN / 🔴 KURANGI EXPOSURE]
Catalyst: [event terdekat dengan estimasi waktu]

📊 KONTEKS MARKET
[2-3 kalimat kondisi market]
Cross-asset: [ringkasan DXY/VIX/Gold/SPX — risk-on atau risk-off]

🎯 STRATEGI HARI INI
[1-2 kalimat, HARUS konsisten dengan Action di atas]

⚠️ YANG HARUS DIHINDARI
[1-2 kalimat, termasuk warning korelasi jika >2 LONG]

🚨 LEVEL & CATALYST PENTING
[Level kunci + event dengan jam rilis]


📋 SKENARIO MINGGU INI
Bull case (prob [X]%): [kondisi yang harus terjadi] → target [level]
Base case (prob [X]%): [kondisi paling mungkin] → ekspektasi [range]
Bear case (prob [X]%): [kondisi bearish] → risiko ke [level]
Invalidasi bull: [kondisi yang membatalkan skenario bull]

Jawab HANYA dengan 6 section (⚡ sampai 🚨), tanpa pembuka, tanpa penutup. Jangan saran spot/futures.
Total probabilitas Bull+Base+Bear harus = 100%.
---"""

    main_out = ""
    spot_raw = ""
    fut_raw = ""
    try:
        main_out, spot_raw, fut_raw = await asyncio.gather(
            _call_llm_async(main_prompt),
            _generate_spot_analysis(brief_data, coin_details, _cross_bundle=cross_bundle),
            _generate_futures_analysis(brief_data, coin_details, _cross_bundle=cross_bundle),
        )
    except Exception as e:  # noqa: BLE001
        logging.warning("_generate_brief_analysis: gather failed: %s", e)
        if not main_out:
            main_out = await _call_llm_async(main_prompt)
        if not spot_raw:
            spot_raw = await _generate_spot_analysis(
                brief_data, coin_details, _cross_bundle=cross_bundle
            )
        if not fut_raw:
            fut_raw = await _generate_futures_analysis(
                brief_data, coin_details, _cross_bundle=cross_bundle
            )

    if not main_out.strip():
        main_out = (
            "⚡ KEPUTUSAN HARI INI\n"
            "Regime: —\n"
            "Bias: —\n"
            "Conviction: —/10 — Analisis AI sementara tidak tersedia (timeout atau error).\n"
            "Action: ⏸️ TAHAN\n"
            "Catalyst: —\n\n"
            "📊 KONTEKS MARKET\n"
            "LLM tidak merespons — gunakan data di brief sebagai acuan; hindari over-leverage.\n"
            "Cross-asset: tinjau manual dari sumber eksternal jika diperlukan.\n\n"
            "🎯 STRATEGI HARI INI\n"
            "Review posisi, set alert harga, dan cek kalender makro sebelum menambah exposure.\n\n"
            "⚠️ YANG HARUS DIHINDARI\n"
            "Chasing tanpa konfirmasi volume/struktur.\n\n"
            "🚨 LEVEL & CATALYST PENTING\n"
            "Pantau level SL/TP dan event ekonomi besok."
        )

    spot_section = _reorder_section_by_rr(spot_raw, is_spot=True).strip()
    if not spot_section:
        spot_section = spot_raw.strip() if spot_raw.strip() else (
            "🟢 SARAN SPOT (Swing 1-7 hari)\n"
            "Tidak ada setup spot yang layak — tunggu pullback ke support."
        )

    # Dedup: kalau fut_raw sudah mengandung section futures, gunakan langsung
    futures_section = _reorder_section_by_rr(fut_raw).strip()
    if not futures_section:
        futures_section = fut_raw.strip() if fut_raw.strip() else (
            "📊 SARAN FUTURES (Swing 1-7 hari)\n"
            "Kondisi tidak mendukung futures saat ini.\n\n"
            "⚠️ Futures berisiko tinggi. Gunakan leverage rendah dan selalu pasang SL."
        )

    disclaimer = (
        "⚠️ DISCLAIMER\n"
        "Analisis teknikal swing trading dari sistem Aliza, bukan saran investasi.\n"
        "Selalu pasang SL dan gunakan sizing sesuai risk tolerance."
    )
    # Hapus duplikasi section futures di main_out
    for _marker in ("SARAN SPOT", "SARAN FUTURES", "DISCLAIMER"):
        if _marker in main_out:
            _lines = main_out.split("\n")
            _cut = next((i for i, l in enumerate(_lines) if _marker in l), None)
            if _cut is not None:
                main_out = "\n".join(_lines[:_cut]).strip()
                break
    # Fallback kedua: jika dedup membuat main_out kosong, gunakan fallback.
    # Catatan: ini HANYA soal main_out (section 6 KEPUTUSAN HARI INI) — spot_section
    # dan futures_section datang dari panggilan LLM terpisah (_generate_spot_analysis/
    # _generate_futures_analysis di atas, dijalankan paralel via asyncio.gather) dan
    # tetap dikirim apa adanya di bawah fallback ini kalau berhasil, karena
    # kegagalannya independen dari kegagalan main_out. Pesannya sengaja tidak
    # menyebut detail implementasi ("LLM tidak mengikuti format", dst) ke user.
    if not main_out.strip():
        logging.warning("_generate_brief_analysis: main_out kosong setelah dedup — pakai fallback")
        main_out = (
            "⚡ KEPUTUSAN HARI INI\n"
            "Regime: —\n"
            "Bias: —\n"
            f"Conviction: {conviction_preset}/10 — Analisis makro harian gagal diproses untuk sesi ini.\n"
            "Action: ⏸️ TAHAN\n"
            "Catalyst: Pantau event makro dan price action.\n\n"
            "📊 KONTEKS MARKET\n"
            "Ringkasan makro tidak tersedia untuk sesi ini — gunakan data snapshot di atas, "
            "serta SARAN SPOT/FUTURES di bawah, sebagai acuan.\n"
            "Cross-asset: tinjau manual dari data yang tersedia di brief.\n\n"
            "🎯 STRATEGI HARI INI\n"
            "Tahan posisi, set alert di level support/resistance, dan pantau kalender ekonomi.\n\n"
            "⚠️ YANG HARUS DIHINDARI\n"
            "Entry tanpa konfirmasi struktur dan volume.\n\n"
            "🚨 LEVEL & CATALYST PENTING\n"
            "Pantau level SL/TP aktif dan event besok."
        )
    # Dedup spot_section jika mengandung lebih dari satu header SARAN SPOT
    if spot_section.count("SARAN SPOT") > 1:
        _sp_lines = spot_section.split("\n")
        _second = next((i for i, l in enumerate(_sp_lines) if "SARAN SPOT" in l and i > 0), None)
        if _second:
            spot_section = "\n".join(_sp_lines[:_second]).strip()
    _output = "\n\n".join(
        [
            main_out.strip(),
            spot_section,
            futures_section,
            disclaimer,
        ]
    )
    # Final safety dedup: hapus blok SARAN SPOT duplikat di output gabungan
    _lines = _output.split("\n")
    _spot_headers = [i for i, l in enumerate(_lines) if l.strip().startswith("🟢 SARAN SPOT")]
    if len(_spot_headers) > 1:
        _second = _spot_headers[1]
        _next_section = next(
            (
                j
                for j in range(_second + 1, len(_lines))
                if _lines[j].strip() and _lines[j].strip()[0] in ("📊", "⚠️", "⚡", "🎯", "🚨", "📋", "☀️", "📈")
            ),
            None,
        )
        if _next_section is not None:
            _lines = _lines[:_second] + _lines[_next_section:]
        else:
            _lines = _lines[:_second]
        while _lines and not _lines[-1].strip():
            _lines.pop()
        _output = "\n".join(_lines)
    return _output



def _format_cross_asset_section() -> str:
    """Format cross-asset data untuk ditampilkan di brief header."""
    try:
        with _BRIEF_DATA_CACHE_LOCK:
            cached = _BRIEF_DATA_CACHE.get("cross_asset")
        ca: dict[str, Any] = {}
        if cached is None:
            fresh = _get_cross_asset_data()
            if any(v is not None for v in fresh.values()):
                with _BRIEF_DATA_CACHE_LOCK:
                    _BRIEF_DATA_CACHE["cross_asset"] = fresh
                now = datetime.now(timezone.utc)
                _BRIEF_SECTION_UPDATED_AT["cross_asset"] = now
                # Simpan nilai valid ke persistent fallback
                for k, v in fresh.items():
                    if v is not None:
                        _CROSS_ASSET_LAST_VALID[k] = v
                ca = fresh
            else:
                # Semua N/A — pakai nilai terakhir yang valid sebagai fallback
                ca = dict(fresh)
                for k, v in _CROSS_ASSET_LAST_VALID.items():
                    if ca.get(k) is None:
                        ca[k] = v
        else:
            ca = dict(cached)  # copy agar tidak mutate cache
            # Update persistent fallback dari cache
            for k, v in ca.items():
                if v is not None:
                    _CROSS_ASSET_LAST_VALID[k] = v
            # Fallback: isi None dari last valid
            for k, v in _CROSS_ASSET_LAST_VALID.items():
                if ca.get(k) is None:
                    ca[k] = v
        ts = _BRIEF_SECTION_UPDATED_AT.get("cross_asset")
        age_min = (
            int((datetime.now(timezone.utc) - ts).total_seconds() // 60) if ts else 0
        )
        # Cek apakah ada data yang berasal dari fallback (bukan live)
        has_fallback = any(
            ca.get(k) is not None and _BRIEF_DATA_CACHE.get("cross_asset", {}) and
            _BRIEF_DATA_CACHE.get("cross_asset", {}).get(k) is None
            for k in ("sp500", "vix", "gold", "dxy")
        )
        staleness = " *(cached)*" if (ts is not None and age_min > 30) else ""
        if has_fallback:
            staleness = " *(data kemarin)*"

        def fmt(key, prefix="", price_fmt=",.0f"):
            d = ca.get(key)
            if not d:
                return "N/A"
            arrow = "↑" if d["pct"] > 0 else "↓" if d["pct"] < 0 else "→"
            return f"{prefix}{d['price']:{price_fmt}} ({d['pct']:+.1f}%) {arrow}"

        lines = [
            f"🌍 CROSS-ASSET{staleness}",
            f"S&P 500 : {fmt('sp500', '$')}",
            f"VIX     : {fmt('vix', price_fmt='.1f')}",
            f"Gold    : {fmt('gold', '$')}",
            f"Oil WTI : {fmt('oil', '$', '.1f')}",
            f"DXY     : {fmt('dxy', price_fmt='.1f')}",
        ]
        return "\n".join(lines)
    except Exception:
        return "🌍 CROSS-ASSET\nData tidak tersedia"


def _get_stablecoin_data() -> dict[str, Any]:
    """CoinGecko global: dominasi stablecoin & interpretasi."""
    out: dict[str, Any] = {
        "usdt_dominance": None,
        "usdc_dominance": None,
        "total_stablecoin_pct": None,
        "total_mcap_usd": None,
        "interpretation": "Data tidak tersedia",
    }
    try:
        import httpx

        r = httpx.get("https://api.coingecko.com/api/v3/global", timeout=8.0)
        if r.status_code != 200:
            return out
        body = r.json()
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, dict):
            return out
        mcp = data.get("market_cap_percentage") or {}
        if not isinstance(mcp, dict):
            mcp = {}
        usdt = _safe_float_any(mcp.get("usdt"))
        usdc = _safe_float_any(mcp.get("usdc"))
        stable_keys = (
            "usdt",
            "usdc",
            "dai",
            "busd",
            "fdusd",
            "tusd",
            "pyusd",
            "usdd",
        )
        total_st = 0.0
        for k in stable_keys:
            v = _safe_float_any(mcp.get(k))
            if v is not None:
                total_st += v
        tmc = data.get("total_market_cap")
        mcap_usd = None
        if isinstance(tmc, dict):
            mcap_usd = _safe_float_any(tmc.get("usd"))
        out["usdt_dominance"] = usdt
        out["usdc_dominance"] = usdc
        out["total_stablecoin_pct"] = round(total_st, 2) if total_st > 0 else None
        out["total_mcap_usd"] = mcap_usd
        if usdt is None:
            out["interpretation"] = "Data tidak tersedia"
        elif usdt > 8:
            out["interpretation"] = "Stablecoin dominan tinggi → dry powder besar, potensi rally"
        elif usdt >= 6:
            out["interpretation"] = "Stablecoin normal → pasar seimbang"
        else:
            out["interpretation"] = "Stablecoin rendah → capital sudah deploy, less room to rally"
        return out
    except Exception as e:  # noqa: BLE001
        logging.warning("_get_stablecoin_data: %s", e)
        return out


def _safe_float_any(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _get_deribit_options() -> dict[str, Any]:
    """Deribit BTC options: put/call OI, max pain, avg IV (volume>0)."""
    out: dict[str, Any] = {
        "put_call_ratio": None,
        "max_pain": None,
        "avg_iv": None,
        "interpretation": "Data tidak tersedia",
    }
    try:
        import httpx

        r = httpx.get(
            "https://www.deribit.com/api/v2/public/get_book_summary_by_currency",
            params={"currency": "BTC", "kind": "option"},
            timeout=8.0,
        )
        if r.status_code != 200:
            return out
        body = r.json()
        rows = body.get("result") if isinstance(body, dict) else None
        if not isinstance(rows, list) or not rows:
            return out
        put_oi = 0.0
        call_oi = 0.0
        strike_oi: dict[float, float] = {}
        iv_sum = 0.0
        iv_n = 0
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get("instrument_name") or "")
            parts = name.split("-")
            if len(parts) < 4:
                continue
            cp = parts[-1].strip().upper()
            if cp not in ("C", "P"):
                continue
            try:
                strike = float(parts[-2])
            except (TypeError, ValueError):
                continue
            oi = _safe_float_any(row.get("open_interest"))
            if oi is None:
                oi = 0.0
            vol = _safe_float_any(row.get("volume")) or 0.0
            miv = _safe_float_any(row.get("mark_iv"))
            if cp == "P":
                put_oi += oi
            else:
                call_oi += oi
            strike_oi[strike] = strike_oi.get(strike, 0.0) + oi
            if vol > 0 and miv is not None:
                iv_sum += miv
                iv_n += 1
        if call_oi > 0:
            ratio = put_oi / call_oi
        elif put_oi > 0:
            ratio = float("inf")
        else:
            ratio = None
        out["put_call_ratio"] = round(ratio, 3) if ratio is not None and ratio != float("inf") else None
        if ratio == float("inf"):
            out["put_call_ratio"] = None
        if strike_oi:
            out["max_pain"] = float(max(strike_oi.keys(), key=lambda s: strike_oi[s]))
        if iv_n > 0:
            avg = iv_sum / iv_n
            # Deribit mark_iv biasanya desimal (0.55 = 55%)
            out["avg_iv"] = round(avg * 100.0, 2) if avg is not None and avg <= 2.0 else round(avg, 2)
        ratio_disp = out["put_call_ratio"]
        if ratio_disp is None:
            out["interpretation"] = "Data tidak tersedia"
        elif ratio_disp < 0.7:
            out["interpretation"] = f"Put/Call {ratio_disp} → bullish skew"
        elif ratio_disp <= 1.0:
            out["interpretation"] = f"Put/Call {ratio_disp} → netral"
        else:
            out["interpretation"] = f"Put/Call {ratio_disp} → bearish skew, hedging aktif"
        return out
    except Exception as e:  # noqa: BLE001
        logging.warning("_get_deribit_options: %s", e)
        return out


def _get_coinbase_premium() -> dict[str, Any]:
    """Coinbase vs Binance BTC — premium % dan interpretasi."""
    out: dict[str, Any] = {
        "coinbase_price": None,
        "binance_price": None,
        "premium_usd": None,
        "premium_pct": None,
        "interpretation": "Data tidak tersedia",
    }
    try:
        import httpx

        with httpx.Client(timeout=8.0) as client:
            rc = client.get("https://api.coinbase.com/v2/prices/BTC-USD/spot")
            rb = client.get(
                "https://api.binance.com/api/v3/ticker/price",
                params={"symbol": "BTCUSDT"},
            )
        if rc.status_code != 200 or rb.status_code != 200:
            return out
        cj = rc.json()
        bj = rb.json()
        amt = (cj.get("data") or {}).get("amount") if isinstance(cj, dict) else None
        bprice = bj.get("price") if isinstance(bj, dict) else None
        cb_p = _safe_float_any(amt)
        bn_p = _safe_float_any(bprice)
        if cb_p is None or bn_p is None or bn_p == 0:
            return out
        out["coinbase_price"] = cb_p
        out["binance_price"] = bn_p
        prem_usd = cb_p - bn_p
        prem_pct = (prem_usd / bn_p) * 100.0
        out["premium_usd"] = round(prem_usd, 2)
        out["premium_pct"] = round(prem_pct, 4)
        if prem_pct > 0.1:
            out["interpretation"] = f"CB premium +{prem_pct:.3f}% → US buyers agresif, bullish signal"
        elif prem_pct >= 0:
            out["interpretation"] = "CB premium netral"
        else:
            out["interpretation"] = f"CB discount {prem_pct:.3f}% → US sellers dominan, bearish signal"
        return out
    except Exception as e:  # noqa: BLE001
        logging.warning("_get_coinbase_premium: %s", e)
        return out


def _etf_flow_sentiment(flow_m: float | None) -> str:
    if flow_m is None:
        return "Data ETF flow tidak tersedia hari ini"
    if flow_m > 100:
        return "Inflow kuat → institusi akumulasi agresif 🟢"
    if flow_m > 0:
        return "Inflow moderat → institusi beli bertahap 🟡"
    if flow_m > -100:
        return "Outflow moderat → institusi jual sebagian 🟡"
    return "Outflow besar → institusi distribusi 🔴"


def _btc_netflow_sentiment(nf: float | None) -> str:
    if nf is None:
        return "Data netflow tidak tersedia"
    if nf < -1000:
        return "Outflow besar dari exchange → akumulasi 🟢"
    if nf < 0:
        return "Outflow moderat → slight bullish 🟡"
    if nf <= 1000:
        return "Inflow moderat → slight bearish 🟡"
    return "Inflow besar ke exchange → distribusi 🔴"


def _institutional_footer(inst: dict[str, Any]) -> str:
    """Footer section INSTITUTIONAL -- membedakan "beberapa metrik memang
    belum dikonfigurasi" (bukan kegagalan apa pun) dari "ada fetch yang
    benar-benar gagal" (network/API error saat fetch), lihat
    INSTITUTIONAL_DATA_REPORT.md. Dihitung dari status per-metrik langsung
    (bukan cuma bucket `data_quality` kasar) supaya ETF Flow yang statusnya
    "ok" tidak ikut membuat footer terkesan "ada yang gagal" padahal
    Netflow/Liquidation cuma belum diaktifkan."""
    statuses = (inst.get("etf_status"), inst.get("netflow_status"), inst.get("liq_status"))
    if any(s == "fetch_failed" for s in statuses):
        return "⚠️ Sebagian sumber gagal fetch — lihat pesan per baris di atas"
    if inst.get("data_quality") == "not_configured":
        return (
            "🔧 Belum aktif — daftar akun gratis di sosovalue.com/developer "
            "untuk ETF Flow (isi SOSOVALUE_API_KEY di .env). Liquidation 24h "
            "butuh CoinGlass berbayar (opsional, mulai $29/bln) — lihat "
            "INSTITUTIONAL_DATA_REPORT.md"
        )
    if all(s == "ok" for s in statuses):
        return "Sumber: SoSoValue (ETF flow, fallback Farside), CoinGlass (Liquidation)"
    labels = []
    if inst.get("etf_status") == "not_configured":
        labels.append("ETF Flow")
    if inst.get("netflow_status") == "not_configured":
        labels.append("BTC Netflow")
    if inst.get("liq_status") == "not_configured":
        labels.append("Liquidation 24h")
    return f"{' & '.join(labels)} belum aktif — lihat pesan di atas"


def _get_institutional_data() -> dict[str, Any]:
    """Data institusional (ETF flow, BTC exchange netflow, liquidation volume 24h)
    via engine.market.institutional_data (SoSoValue/Farside untuk ETF flow,
    CoinGlass berbayar-opsional untuk liquidation -- bukan lagi proxy
    Serper-news-snippet-parsing seperti sebelumnya -- lihat
    INSTITUTIONAL_DATA_REPORT.md)."""
    etf = inst_data.get_etf_flow_data()
    liq = inst_data.get_liquidation_volume_24h()
    nf = inst_data.get_btc_exchange_netflow()

    out: dict[str, Any] = {
        "etf_flow_usd_m": etf.get("flow_usd_today_m"),
        "etf_flow_7d_usd_m": etf.get("flow_usd_7d_m"),
        "etf_status": etf.get("status"),
        "etf_message": etf.get("message"),
        "netflow_btc": nf.get("netflow_btc"),
        "netflow_status": nf.get("status"),
        "netflow_message": nf.get("message"),
        "liq_long_usd_m": liq.get("long_usd_m"),
        "liq_short_usd_m": liq.get("short_usd_m"),
        "liq_status": liq.get("status"),
        "liq_message": liq.get("message"),
        # Dipertahankan None -- lihat INSTITUTIONAL_DATA_REPORT.md: price-level
        # liquidation zones (bukan volume agregat) butuh CoinGlass Professional+
        # (di atas plan Hobbyist berbayar $29/bln yang dipakai untuk volume
        # agregat), jadi tidak pernah diisi dari sumber manapun saat ini.
        "liq_above": None,
        "liq_below": None,
    }
    out["etf_sentiment"] = _etf_flow_sentiment(out["etf_flow_usd_m"])
    out["netflow_sentiment"] = _btc_netflow_sentiment(out["netflow_btc"])

    statuses = (out["etf_status"], out["netflow_status"], out["liq_status"])
    if all(s == "ok" for s in statuses):
        out["data_quality"] = "live"
    elif any(s == "ok" for s in statuses):
        out["data_quality"] = "partial"
    elif all(s == "not_configured" for s in statuses):
        out["data_quality"] = "not_configured"
    else:
        out["data_quality"] = "unavailable"
    return out


def _brief_cache_attempt() -> dict[str, bool]:
    """Satu siklus fetch semua data brief; update cache dan section timestamps."""
    results: dict[str, bool] = {}
    now = datetime.now(timezone.utc)

    try:
        data = _get_cross_asset_data()
        has_data = any(v is not None for v in data.values())
        if has_data:
            with _BRIEF_DATA_CACHE_LOCK:
                _BRIEF_DATA_CACHE["cross_asset"] = data
            _BRIEF_SECTION_UPDATED_AT["cross_asset"] = now
            results["cross_asset"] = True
        else:
            results["cross_asset"] = False
    except Exception:
        results["cross_asset"] = False

    try:
        data = _get_stablecoin_data()
        if data.get("usdt_dominance") is not None:
            with _BRIEF_DATA_CACHE_LOCK:
                _BRIEF_DATA_CACHE["stablecoin"] = data
            _BRIEF_SECTION_UPDATED_AT["stablecoin"] = now
            results["stablecoin"] = True
        else:
            results["stablecoin"] = False
    except Exception:
        results["stablecoin"] = False

    try:
        data = _get_deribit_options()
        if data.get("put_call_ratio") is not None:
            with _BRIEF_DATA_CACHE_LOCK:
                _BRIEF_DATA_CACHE["deribit"] = data
            _BRIEF_SECTION_UPDATED_AT["deribit"] = now
            results["deribit"] = True
        else:
            results["deribit"] = False
    except Exception:
        results["deribit"] = False

    try:
        data = _get_coinbase_premium()
        if data.get("premium_pct") is not None:
            with _BRIEF_DATA_CACHE_LOCK:
                _BRIEF_DATA_CACHE["coinbase_premium"] = data
            _BRIEF_SECTION_UPDATED_AT["coinbase_premium"] = now
            results["coinbase_premium"] = True
        else:
            results["coinbase_premium"] = False
    except Exception:
        results["coinbase_premium"] = False

    try:
        data = _get_institutional_data()
        if data.get("data_quality") != "unavailable":
            with _BRIEF_DATA_CACHE_LOCK:
                _BRIEF_DATA_CACHE["institutional"] = data
            _BRIEF_SECTION_UPDATED_AT["institutional"] = now
            results["institutional"] = True
        else:
            results["institutional"] = False
    except Exception:
        results["institutional"] = False

    with _BRIEF_DATA_CACHE_LOCK:
        _BRIEF_DATA_CACHE["last_updated"] = datetime.now(timezone.utc)
        if all(results.values()):
            _BRIEF_DATA_CACHE["last_full_update"] = datetime.now(timezone.utc)
    return results


def _update_brief_cache() -> dict[str, bool]:
    """
    Fetch semua data brief dan update _BRIEF_DATA_CACHE.
    Return dict: {data_name: True jika berhasil, False jika N/A}.
    Retry terbatas: satu percobaan ulang setelah jeda jika belum semua berhasil.
    """
    r1 = _brief_cache_attempt()
    if all(r1.values()):
        return r1
    time_module.sleep(2)
    r2 = _brief_cache_attempt()
    _keys = ("cross_asset", "stablecoin", "deribit", "coinbase_premium", "institutional")
    merged = {k: r1.get(k, False) or r2.get(k, False) for k in _keys}
    with _BRIEF_DATA_CACHE_LOCK:
        _BRIEF_DATA_CACHE["last_updated"] = datetime.now(timezone.utc)
        if all(merged.values()):
            _BRIEF_DATA_CACHE["last_full_update"] = datetime.now(timezone.utc)
    return merged


def _format_market_intelligence_section() -> str:
    """Blok teks 🧠 MARKET INTELLIGENCE untuk header brief."""
    try:
        now = datetime.now(timezone.utc)

        def _pick(ckey: str, fetch_fn, valid_fn) -> Any:
            with _BRIEF_DATA_CACHE_LOCK:
                c = _BRIEF_DATA_CACHE.get(ckey)
            if c is None:
                f = fetch_fn()
                if valid_fn(f):
                    with _BRIEF_DATA_CACHE_LOCK:
                        _BRIEF_DATA_CACHE[ckey] = f
                    _BRIEF_SECTION_UPDATED_AT[ckey] = now
                    return f
                return f
            return c

        st = _pick(
            "stablecoin",
            _get_stablecoin_data,
            lambda d: d.get("usdt_dominance") is not None,
        )
        dr = _pick(
            "deribit",
            _get_deribit_options,
            lambda d: d.get("put_call_ratio") is not None,
        )
        cb = _pick(
            "coinbase_premium",
            _get_coinbase_premium,
            lambda d: d.get("premium_pct") is not None,
        )
        inst = _pick(
            "institutional",
            _get_institutional_data,
            lambda d: d.get("data_quality") != "unavailable",
        )

        ts_keys = ("stablecoin", "deribit", "coinbase_premium", "institutional")
        ages: list[int] = []
        for k in ts_keys:
            t = _BRIEF_SECTION_UPDATED_AT.get(k)
            if t is not None:
                ages.append(int((now - t).total_seconds() // 60))
        age_min = max(ages) if ages else 0
        staleness = " *(cached)*" if age_min > 30 else ""

        usdt = st.get("usdt_dominance")
        usdc = st.get("usdc_dominance")
        tot = st.get("total_stablecoin_pct")
        usdt_s = f"{usdt:.2f}" if usdt is not None else "—"
        usdc_s = f"{usdc:.2f}" if usdc is not None else "—"
        tot_s = f"{tot:.2f}" if tot is not None else "—"
        st_int = str(st.get("interpretation") or "—")
        ratio = dr.get("put_call_ratio")
        mp = dr.get("max_pain")
        iv = dr.get("avg_iv")
        ratio_s = f"{ratio:.3f}" if ratio is not None else "—"
        mp_s = f"${mp:,.0f}" if mp is not None else "—"
        iv_s = f"{iv:.1f}" if iv is not None else "—"
        dr_int = str(dr.get("interpretation") or "—")
        prem_u = cb.get("premium_usd")
        prem_p = cb.get("premium_pct")
        prem_u_s = f"{prem_u:+.0f}" if prem_u is not None else "—"
        prem_p_s = f"{prem_p:+.3f}" if prem_p is not None else "—"
        cb_int = str(cb.get("interpretation") or "—")

        try:
            ef = inst.get("etf_flow_usd_m")
            ef7 = inst.get("etf_flow_7d_usd_m")
            etf_today_s = f"{float(ef):+.0f}M" if ef is not None else "N/A"
            etf_7d_s = f"{float(ef7):+.0f}M" if ef7 is not None else "N/A"
            etf_snt = (
                str(inst.get("etf_sentiment") or "—")
                if ef is not None
                else str(inst.get("etf_message") or "Data ETF flow tidak tersedia")
            )

            nf_btc = inst.get("netflow_btc")
            nf_s = f"{float(nf_btc):+,.0f} BTC" if nf_btc is not None else "N/A"
            nf_snt = (
                str(inst.get("netflow_sentiment") or "—")
                if nf_btc is not None
                else str(inst.get("netflow_message") or "Data netflow tidak tersedia")
            )

            # Liquidation 24h agregat long/short (BUKAN price-level "zones" --
            # itu butuh CoinGlass Professional+, di atas plan Hobbyist berbayar
            # yang dipakai di sini. Lihat INSTITUTIONAL_DATA_REPORT.md.)
            ll = inst.get("liq_long_usd_m")
            ls = inst.get("liq_short_usd_m")
            if ll is not None and ls is not None:
                liq_s = f"Long ${ll:,.0f}M | Short ${ls:,.0f}M"
                if ll > ls:
                    liq_note = "Long dominan → tekanan jual dari likuidasi long lebih besar"
                elif ls > ll:
                    liq_note = "Short dominan → tekanan beli dari short squeeze lebih besar"
                else:
                    liq_note = "Long/short seimbang"
            else:
                liq_s = "N/A"
                liq_note = str(inst.get("liq_message") or "Data liquidation tidak tersedia")

            inst_footer = _institutional_footer(inst)
            inst_block = (
                "\n\n🏦 INSTITUTIONAL\n"
                f"ETF Flow      : {etf_today_s} hari ini | {etf_7d_s} 7 hari\n"
                f"                {etf_snt}\n"
                f"BTC Netflow   : {nf_s}\n"
                f"                {nf_snt}\n"
                f"Liquidation 24h: {liq_s}\n"
                f"                {liq_note}\n"
                f"{inst_footer}"
            )
        except Exception as e:  # noqa: BLE001
            logging.warning("_format_market_intelligence_section institutional: %s", e)
            inst_block = (
                "\n\n🏦 INSTITUTIONAL\n"
                "ETF Flow      : N/A hari ini | N/A 7 hari\n"
                "                Data ETF flow tidak tersedia\n"
                "BTC Netflow   : N/A\n"
                "                Data netflow tidak tersedia\n"
                "Liquidation 24h: N/A\n"
                "                Data liquidation tidak tersedia\n"
                "🔧 Cek konfigurasi SOSOVALUE_API_KEY (ETF flow, gratis) / "
                "COINGLASS_API_KEY (Liquidation, berbayar) di .env"
            )
        return (
            f"🧠 MARKET INTELLIGENCE{staleness}\n"
            f"Stablecoin : USDT {usdt_s}% | USDC {usdc_s}% | Total {tot_s}%\n"
            f"             {st_int}\n"
            f"Options    : Put/Call {ratio_s} | Max Pain {mp_s} | IV {iv_s}%\n"
            f"             {dr_int}\n"
            f"CB Premium : {prem_u_s} USD ({prem_p_s}%)\n"
            f"             {cb_int}"
            + inst_block
        )
    except Exception as e:  # noqa: BLE001
        logging.warning("_format_market_intelligence_section: %s", e)
        return "🧠 MARKET INTELLIGENCE\nData tidak tersedia"


def _format_macro_section_for_brief_with_data_per() -> str:
    """
    Bungkus format_macro_section_for_brief: tambah 'per' sebelum tanggal observasi
    (tanggal rilis data FRED), tanpa mengubah fetch di macro_monitor.
    """
    raw = format_macro_section_for_brief()
    if not raw or "Data tidak tersedia" in raw:
        return raw
    prefixes = ("CPI (", "Core PCE (", "NFP:", "Fed Rate:")
    out_lines: list[str] = []
    for line in raw.split("\n"):
        if any(line.startswith(p) for p in prefixes) and " • " in line:
            left, right = line.rsplit(" • ", 1)
            r = right.strip()
            if not r or r in ("—", "None"):
                r = "N/A"
            out_lines.append(f"{left} • per {r}")
        else:
            out_lines.append(line)
    return "\n".join(out_lines)


async def pre_fetch_brief_data_job(_context: ContextTypes.DEFAULT_TYPE) -> None:
    """Pre-fetch semua data brief dan simpan ke cache. Jalan di window sebelum brief pagi/malam."""
    wib = datetime.now(timezone(timedelta(hours=7)))
    hour = wib.hour
    minute = wib.minute
    in_morning_window = (6, 0) <= (hour, minute) <= (7, 50)
    in_evening_window = (18, 0) <= (hour, minute) <= (19, 50)
    if not (in_morning_window or in_evening_window):
        return
    loop = asyncio.get_running_loop()
    try:
        results = await loop.run_in_executor(None, _update_brief_cache)
        missing = [k for k, v in results.items() if not v]
        if missing:
            logging.info("pre_fetch_brief_data: N/A untuk %s", missing)
        else:
            logging.info("pre_fetch_brief_data: semua data lengkap")
    except Exception as e:
        logging.warning("pre_fetch_brief_data_job: %s", e)


import re as _re_sig


def _parse_and_record_signals(text: str, market_score: int = 0) -> None:
    """Parse output saran spot/futures dan simpan ke signal_tracking."""
    try:
        coin_blocks = _re_sig.split(r'\n(?=•\s+\w)', text)
        for block in coin_blocks:
            coin_match = _re_sig.search(r'•\s+(\w+)', block)
            if not coin_match:
                continue
            coin = coin_match.group(1).upper()

            setup = "SPOT"
            if _re_sig.search(r'LONG', block, _re_sig.IGNORECASE):
                setup = "LONG"
            elif _re_sig.search(r'SHORT', block, _re_sig.IGNORECASE):
                setup = "SHORT"

            entry_match = _re_sig.search(r'Entry(?:\s+ideal)?[:\s]+\$?([\d,\.]+)', block)
            entry = float(entry_match.group(1).replace(',', '')) if entry_match else None

            sl_match = _re_sig.search(r'SL[:\s]+\$?([\d,\.]+)', block)
            sl = float(sl_match.group(1).replace(',', '')) if sl_match else None

            tp_match = _re_sig.search(r'Target\s+1[:\s]+\$?([\d,\.]+)', block)
            tp = float(tp_match.group(1).replace(',', '')) if tp_match else None

            rr_match = _re_sig.search(r'RR[:\s]+([\d\.]+)', block)
            rr = float(rr_match.group(1)) if rr_match else None

            if not entry or not sl or not tp:
                continue

            try:
                _snap = get_market_snapshot()
                _regime = ((_snap.get("market_intelligence") or {}).get("market_regime")) or "UNKNOWN"
            except Exception:
                _regime = "UNKNOWN"

            record_signal({
                "coin": coin,
                "setup": setup,
                "side": "SHORT" if setup == "SHORT" else "LONG",
                "source": "llm",
                "dispatch_status": "SENT",
                "entry": entry,
                "sl": sl,
                "tp": tp,
                "rr": rr,
                "market_score": market_score,
                "regime": _regime,
                "signal_time": _wib_now_label(),
            })
    except Exception as _e:
        logging.warning("_parse_and_record_signals: %s", _e)


async def morning_brief_job(context: ContextTypes.DEFAULT_TYPE):
    """Ringkasan market harian; kirim via safe_dispatch(force=True) agar lolos circuit breaker."""
    chat_id = None
    try:
        if context and getattr(context, "bot_data", None):
            chat_id = context.bot_data.get("chat_id")
    except Exception:
        chat_id = None
    if not chat_id:
        chat_id = DEFAULT_CHAT_ID
    if not chat_id:
        logging.warning("Morning brief skipped: no chat_id (set TELEGRAM_CHAT_ID or /start)")
        return

    partial = False
    data: dict = {}
    try:
        snapshot = get_market_snapshot()
        data = snapshot.get("data") or {}
        if not data:
            partial = True
    except Exception as e:
        logging.warning("morning_brief snapshot: %s", e)
        partial = True
        data = {}

    fg_val = None
    dom_val = None
    try:
        gd = get_global_market_data()
        fg_val = gd.get("fear_greed")
        dom_val = gd.get("btc_dominance")
    except Exception as e:
        logging.warning("morning_brief global cache: %s", e)

    try:
        funding_data = get_all_funding_data() or {}
        if not isinstance(funding_data, dict):
            funding_data = {}
    except Exception as e:
        logging.warning("morning_brief funding: %s", e)
        funding_data = {}

    try:
        result = calculate_market_score()
    except Exception as e:
        logging.warning("morning_brief calculate_market_score: %s", e)
        result = {}

    events_tm: list = []
    try:
        events_tm = get_events_tomorrow() or []
    except Exception as e:
        logging.warning("morning_brief events: %s", e)

    active_sig = None
    try:
        active_sig = scan_for_signals()
    except Exception as e:
        logging.warning("morning_brief scan_for_signals: %s", e)

    brief_data = {
        "market_score": result.get("total_score"),
        "market_label": result.get("label"),
        "fear_greed": fg_val,
        "btc_dominance": dom_val,
        "top_coins": _top_coins_analysis_dict(data),
        "funding_rates": funding_data,
        "macro": _macro_for_analysis_prompt(),
        "active_signal": active_sig,
        "events_tomorrow": events_tm,
        "context_summary": result.get("summary", ""),
    }

    ts = get_snapshot_timestamp_str() or "—"
    ev_preview = _format_events_for_display(events_tm)
    near_level_section = _format_near_levels_section(
        get_coins_near_levels(snapshot=snapshot),
        NEAR_LEVEL_DEFAULT_TOLERANCE_PCT,
    )

    # Weekend liquidity warning
    from datetime import datetime as _dt
    _wib_hour = _dt.utcnow().hour + 7
    _weekday = (_dt.utcnow().weekday() + (_wib_hour // 24)) % 7
    _is_weekend = _weekday >= 5  # 5=Sabtu, 6=Minggu
    weekend_warning = (
        "\n⚠️ WEEKEND LIQUIDITY WARNING\n"
        "Hari ini Sabtu/Minggu — likuiditas tipis, spread lebih lebar.\n"
        "Hindari entry besar. Waspadai volatilitas tak terduga di Asia session.\n"
    ) if _is_weekend else ""

    brief_header = (
        "☀️ MORNING BRIEF\n"
        f"🕒 Snapshot: {ts}\n"
        + ("⚠️ Data snapshot tidak lengkap.\n" if partial else "")
        + "\n"
        + format_context_for_brief()
        + "\n\n"
        + format_funding_section_for_brief()
        + "\n\n"
        + _format_macro_section_for_brief_with_data_per()
        + "\n\n" + _format_cross_asset_section()
        + "\n\n" + _format_market_intelligence_section()
        + "\n\n" + near_level_section
        + "\n\n📅 Event besok (ringkas): "
        + ev_preview
        + weekend_warning
    )

    try:
        await safe_dispatch(brief_header, chat_id=chat_id, force=True)
    except Exception as e:
        logging.error("morning_brief dispatch header: %s", e)

    try:
        analysis = await _generate_brief_analysis(brief_data)
    except Exception as e:
        logging.warning("morning_brief _generate_brief_analysis: %s", e)
        return

    if not analysis or not str(analysis).strip():
        logging.warning("morning_brief: analisis kosong")
        return

    analysis_sent = False
    try:
        analysis_sent = bool(
            await safe_dispatch(str(analysis).strip(), chat_id=chat_id, force=True)
        )
    except Exception as e:
        logging.error("morning_brief dispatch analysis: %s", e)
    if analysis_sent:
        try:
            _ms = result.get("total_score", 0) if result else 0
            _parse_and_record_signals(str(analysis), market_score=_ms)
        except Exception:
            pass


async def morning_brief_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("COMMAND RECEIVED: /morning_brief")
    await morning_brief_job(context)


async def evening_summary_job(context: ContextTypes.DEFAULT_TYPE):
    """Ringkasan sore; struktur sama dengan morning brief, label evening."""
    chat_id = None
    try:
        if context and getattr(context, "bot_data", None):
            chat_id = context.bot_data.get("chat_id")
    except Exception:
        chat_id = None
    if not chat_id:
        chat_id = DEFAULT_CHAT_ID
    if not chat_id:
        logging.warning("Evening summary skipped: no chat_id (set TELEGRAM_CHAT_ID or /start)")
        return

    partial = False
    data: dict = {}
    try:
        snapshot = get_market_snapshot()
        data = snapshot.get("data") or {}
        if not data:
            partial = True
    except Exception as e:
        logging.warning("evening_summary snapshot: %s", e)
        partial = True
        data = {}

    fg_val = None
    dom_val = None
    try:
        gd = get_global_market_data()
        fg_val = gd.get("fear_greed")
        dom_val = gd.get("btc_dominance")
    except Exception as e:
        logging.warning("evening_summary global cache: %s", e)

    try:
        funding_data = get_all_funding_data() or {}
        if not isinstance(funding_data, dict):
            funding_data = {}
    except Exception as e:
        logging.warning("evening_summary funding: %s", e)
        funding_data = {}

    try:
        result = calculate_market_score()
    except Exception as e:
        logging.warning("evening_summary calculate_market_score: %s", e)
        result = {}

    events_tm: list = []
    try:
        events_tm = get_events_tomorrow() or []
    except Exception as e:
        logging.warning("evening_summary events: %s", e)

    active_sig = None
    try:
        active_sig = scan_for_signals()
    except Exception as e:
        logging.warning("evening_summary scan_for_signals: %s", e)

    brief_data = {
        "market_score": result.get("total_score"),
        "market_label": result.get("label"),
        "fear_greed": fg_val,
        "btc_dominance": dom_val,
        "top_coins": _top_coins_analysis_dict(data),
        "funding_rates": funding_data,
        "macro": _macro_for_analysis_prompt(),
        "active_signal": active_sig,
        "events_tomorrow": events_tm,
        "context_summary": result.get("summary", ""),
    }

    ts = get_snapshot_timestamp_str() or "—"
    ev_preview = _format_events_for_display(events_tm)
    near_level_section = _format_near_levels_section(
        get_coins_near_levels(snapshot=snapshot),
        NEAR_LEVEL_DEFAULT_TOLERANCE_PCT,
    )
    brief_header = (
        "🌙 EVENING SUMMARY\n"
        f"🕒 Snapshot: {ts}\n"
        + ("⚠️ Data snapshot tidak lengkap.\n" if partial else "")
        + "\n"
        + format_context_for_brief()
        + "\n\n"
        + format_funding_section_for_brief()
        + "\n\n"
        + _format_macro_section_for_brief_with_data_per()
        + "\n\n" + _format_cross_asset_section()
        + "\n\n" + _format_market_intelligence_section()
        + "\n\n" + near_level_section
        + "\n\n📅 Event besok (ringkas): "
        + ev_preview
    )

    try:
        await safe_dispatch(brief_header, chat_id=chat_id, force=True)
    except Exception as e:
        logging.error("evening_summary dispatch header: %s", e)

    try:
        analysis = await _generate_brief_analysis(brief_data)
    except Exception as e:
        logging.warning("evening_summary _generate_brief_analysis: %s", e)
        return

    if not analysis or not str(analysis).strip():
        logging.warning("evening_summary: analisis kosong")
        return

    analysis_sent = False
    try:
        analysis_sent = bool(
            await safe_dispatch(str(analysis).strip(), chat_id=chat_id, force=True)
        )
    except Exception as e:
        logging.error("evening_summary dispatch analysis: %s", e)
    if analysis_sent:
        try:
            _ms = result.get("total_score", 0) if result else 0
            _parse_and_record_signals(str(analysis), market_score=_ms)
        except Exception:
            pass


async def evening_summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("COMMAND RECEIVED: /evening_summary")
    await evening_summary_job(context)


async def spot_signal_job(context: ContextTypes.DEFAULT_TYPE, _bypass_dedup: bool = False):
    """Kirim hanya section saran spot (5 coin) via LLM; terjadwal 3x/hari WIB."""
    chat_id = None
    try:
        if context and getattr(context, "bot_data", None):
            chat_id = context.bot_data.get("chat_id")
    except Exception:
        chat_id = None
    if not chat_id:
        chat_id = DEFAULT_CHAT_ID
    if not chat_id:
        logging.warning("spot_signal skipped: no chat_id (set TELEGRAM_CHAT_ID or /start)")
        return

    data: dict = {}
    try:
        snapshot = get_market_snapshot()
        data = snapshot.get("data") or {}
        if not isinstance(data, dict):
            data = {}
    except Exception as e:
        logging.warning("spot_signal snapshot: %s", e)
        return

    if not data:
        logging.warning("spot_signal skipped: snapshot kosong")
        return

    fg_val = None
    dom_val = None
    try:
        gd = get_global_market_data()
        fg_val = gd.get("fear_greed")
        dom_val = gd.get("btc_dominance")
    except Exception as e:
        logging.warning("spot_signal global cache: %s", e)

    try:
        funding_data = get_all_funding_data() or {}
        if not isinstance(funding_data, dict):
            funding_data = {}
    except Exception as e:
        logging.warning("spot_signal get_all_funding_data: %s", e)
        funding_data = {}

    try:
        result = calculate_market_score()
    except Exception as e:
        logging.warning("spot_signal calculate_market_score: %s", e)
        result = {}

    events_tm: list = []
    try:
        events_tm = get_events_tomorrow() or []
    except Exception as e:
        logging.warning("spot_signal events: %s", e)

    brief_data = {
        "market_score": result.get("total_score"),
        "market_label": result.get("label"),
        "fear_greed": fg_val,
        "btc_dominance": dom_val,
        "top_coins": _top_coins_analysis_dict(data),
        "funding_rates": funding_data,
        "macro": _macro_for_analysis_prompt(),
        "active_signal": None,
        "events_tomorrow": events_tm,
        "context_summary": result.get("summary", ""),
    }

    try:
        coin_details, _db = _build_coin_details_for_brief(brief_data)
        brief_data["coin_details"] = coin_details
        spot_raw, _fut_raw = await asyncio.gather(
            _generate_spot_analysis(brief_data, coin_details),
            _generate_futures_analysis(brief_data, coin_details),
        )
        spot_section = _reorder_section_by_rr(spot_raw, is_spot=True).strip()
        if not spot_section:
            spot_section = _extract_spot_section_from_brief_analysis(spot_raw)
    except Exception as e:
        logging.warning("spot_signal spot/futures LLM failed: %s", e)
        return

    if not spot_section or not str(spot_section).strip():
        logging.warning("spot_signal skipped: section spot kosong")
        return

    if _brief_analysis_is_llm_failure(spot_raw):
        logging.warning("spot_signal skipped: LLM tidak menghasilkan analisis (timeout/error/AI off)")
        return

    # Dedup: kalau isi section persis sama dengan pengiriman sebelumnya dalam
    # <2 jam (mis. beberapa run "Tidak ada setup spot yang layak" berturutan
    # akibat restart proses di antara dua jadwal resmi 06/12/21 WIB), jangan
    # kirim ulang — jadwal resminya sendiri TIDAK diubah oleh cek ini.
    now_ts = time_module.time()
    if not _bypass_dedup:
        last = ngov.get_value("spot_signal", "last_sent") or {}
        last_text = last.get("text")
        last_ts = last.get("ts")
        if last_text == spot_section and last_ts is not None and (now_ts - float(last_ts)) < 7200:
            logging.info("spot_signal skipped: konten identik dengan pengiriman <2 jam lalu")
            return
    ngov.set_value("spot_signal", "last_sent", {"text": spot_section, "ts": now_ts})

    msg = (
        "📈 SARAN SPOT TERBAIK\n"
        f"{_spot_signal_wib_header_line()}\n"
        "━━━━━━━━━━━━━━\n"
        f"{spot_section}"
    )
    try:
        await safe_dispatch(msg, chat_id=chat_id, force=False)
    except Exception as e:
        logging.error("spot_signal dispatch: %s", e)


async def spot_signal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("COMMAND RECEIVED: /spot_signal")
    await spot_signal_job(context, _bypass_dedup=True)


async def breakout_check_job(context: ContextTypes.DEFAULT_TYPE):
    """Cek breakout top 5 coin setiap 5 menit; kirim alert via safe_dispatch (hormati circuit breaker)."""
    try:
        breakouts = await run_breakout_check()
        chat_id = None
        if context and getattr(context, "bot_data", None):
            chat_id = context.bot_data.get("chat_id")
        if not chat_id:
            chat_id = DEFAULT_CHAT_ID
        if not chat_id:
            logging.warning("breakout_check_job: no chat_id")
            return
        for b in breakouts:
            msg = format_breakout_alert_message(b)
            coin = b.get("symbol", "")
            direction = b.get("direction", "")
            ngov.queue_alert("breakout", "BREAKOUT", f"{coin} {direction}", msg)
    except Exception as e:
        logging.error("breakout_check_job: %s", e, exc_info=True)


async def check_breakout_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("COMMAND RECEIVED: /check_breakout")
    target = update.effective_message
    if not target:
        return
    try:
        breakouts = await run_breakout_check()
        chat_id = None
        if context and getattr(context, "bot_data", None):
            chat_id = context.bot_data.get("chat_id")
        if not chat_id:
            chat_id = DEFAULT_CHAT_ID
        if breakouts:
            for b in breakouts:
                msg = format_breakout_alert_message(b)
                await safe_dispatch(msg, chat_id=chat_id, force=False)
            await target.reply_text(f"Breakout terdeteksi: {len(breakouts)} alert dikirim.")
        else:
            await target.reply_text(
                "Tidak ada breakout terdeteksi saat ini — semua coin dalam range support/resistance."
            )
    except Exception as e:
        logging.error("check_breakout_command: %s", e, exc_info=True)
        await target.reply_text("Terjadi kesalahan saat cek breakout.")


async def volume_spike_job(context: ContextTypes.DEFAULT_TYPE):
    """Cek volume spike top 5 coin setiap 5 menit; threshold & cooldown ditentukan
    tunggal di volume_spike_detector.py (SPIKE_MULTIPLIER, ALERT_COOLDOWN_SEC) —
    tidak ada gate kedua di sini lagi (lihat NOTIFIKASI_MITIGASI_REPORT.md item 6)."""
    try:
        spikes = await run_volume_spike_check()
        chat_id = None
        if context and getattr(context, "bot_data", None):
            chat_id = context.bot_data.get("chat_id")
        if not chat_id:
            chat_id = DEFAULT_CHAT_ID
        if not chat_id:
            logging.warning("volume_spike_job: no chat_id")
            return
        for s in spikes:
            coin = s.get("symbol", "")
            mult = s.get("multiplier", 0.0)
            msg = format_volume_spike_alert_message(s)
            ngov.queue_alert("volume_spike", "VOLUME SPIKE", f"{coin} {mult:.2f}x", msg)
    except Exception as e:
        logging.error("volume_spike_job: %s", e, exc_info=True)


async def check_volume_spike_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("COMMAND RECEIVED: /check_volume_spike")
    target = update.effective_message
    if not target:
        return
    try:
        spikes = await run_volume_spike_check()
        chat_id = None
        if context and getattr(context, "bot_data", None):
            chat_id = context.bot_data.get("chat_id")
        if not chat_id:
            chat_id = DEFAULT_CHAT_ID
        if spikes:
            for s in spikes:
                msg = format_volume_spike_alert_message(s)
                await safe_dispatch(msg, chat_id=chat_id, force=False)
            await target.reply_text(f"Volume spike terdeteksi: {len(spikes)} alert dikirim.")
        else:
            await target.reply_text(
                "Tidak ada volume spike terdeteksi saat ini — semua coin dalam range normal."
            )
    except Exception as e:
        logging.error("check_volume_spike_command: %s", e, exc_info=True)
        await target.reply_text("Terjadi kesalahan saat cek volume spike.")


async def funding_alert_job(context: ContextTypes.DEFAULT_TYPE):
    """Cek funding ekstrem setiap 5 menit; alert via safe_dispatch (hormati circuit breaker)."""
    try:
        alerts = check_funding_extremes()
        chat_id = None
        if context and getattr(context, "bot_data", None):
            chat_id = context.bot_data.get("chat_id")
        if not chat_id:
            chat_id = DEFAULT_CHAT_ID
        if not chat_id:
            logging.warning("funding_alert_job: no chat_id")
            return
        for item in alerts:
            msg = format_funding_alert_message(item)
            coin = item.get("symbol", "")
            condition = item.get("condition", "")
            ngov.queue_alert("funding", "FUNDING EXTREME", f"{coin} {condition}", msg)
    except Exception as e:
        logging.error("funding_alert_job: %s", e, exc_info=True)


async def check_funding_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("COMMAND RECEIVED: /check_funding")
    target = update.effective_message
    if not target:
        return
    try:
        table = format_funding_table_for_command()
        extremes = check_funding_extremes()
        chat_id = None
        if context and getattr(context, "bot_data", None):
            chat_id = context.bot_data.get("chat_id")
        if not chat_id:
            chat_id = DEFAULT_CHAT_ID
        for item in extremes:
            await safe_dispatch(format_funding_alert_message(item), chat_id=chat_id, force=False)
        if extremes:
            suffix = f"\n\n⚠️ Kondisi ekstrem: {len(extremes)} alert dikirim."
        else:
            suffix = "\n\n✅ Tidak ada kondisi ekstrem — |FR| tidak melebihi 0.1%."
        await target.reply_text(table + suffix)
    except Exception as e:
        logging.error("check_funding_command: %s", e, exc_info=True)
        await target.reply_text("Terjadi kesalahan saat cek funding.")


async def cfra_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """On-demand CFRA: tampilkan zona FR semua coin."""
    logging.info("COMMAND RECEIVED: /cfra")
    target = _reply_target(update)
    if not target:
        return
    try:
        from engine.market.funding_rate_monitor import get_cfra_analysis
        results = get_cfra_analysis()
        if not results:
            await target.reply_text("Data CFRA tidak tersedia saat ini.")
            return

        lines = ["📊 CONTRARIAN FUNDING RATE ANALYTICS (CFRA)\n"]
        squeeze_risk = []
        neutral = []
        for r in results:
            coin = r["coin"]
            label = r["label"]
            action = r["action"]
            next_f = r.get("next_funding") or "—"
            mins = r.get("minutes_to_funding")
            mins_str = f"{mins} mnt" if mins is not None else "—"
            zone = r.get("zone", "UNKNOWN")
            if zone in ("LONG_SQUEEZE_RISK", "SHORT_SQUEEZE_RISK"):
                squeeze_risk.append(
                    f"{r['emoji']} {coin}: {label}\n"
                    f"   → {action}\n"
                    f"   Next funding: {next_f} ({mins_str})"
                )
            else:
                neutral.append(f"⚪ {coin}: FR {r['fr_pct']:+.4f}%" if r['fr_pct'] is not None else f"⚪ {coin}: —")

        if squeeze_risk:
            lines.append("🚨 ZONA EKSTREM:")
            lines.extend(squeeze_risk)
            lines.append("")
        if neutral:
            lines.append("✅ ZONA NETRAL:")
            lines.append("\n".join(neutral))

        lines.append(f"\n⏰ {_wib_now_label()}")
        await target.reply_text("\n".join(lines))
    except Exception as e:
        logging.error("CFRA ERROR: %s", e)
        await target.reply_text("Terjadi kesalahan memuat data CFRA.")


async def cfra_alert_job(context: ContextTypes.DEFAULT_TYPE):
    """Alert CFRA: kirim notifikasi saat FR ekstrem + <90 menit ke funding window."""
    chat_id = context.bot_data.get("chat_id")
    if not chat_id:
        return
    try:
        from engine.market.funding_rate_monitor import get_cfra_analysis
        results = get_cfra_analysis()
        for r in results:
            zone = r.get("zone", "NEUTRAL")
            if zone not in ("LONG_SQUEEZE_RISK", "SHORT_SQUEEZE_RISK"):
                continue
            mins = r.get("minutes_to_funding")
            if mins is None or mins > 90 or mins < 0:
                continue
            coin = r["coin"]
            emoji = r["emoji"]
            label = r["label"]
            action = r["action"]
            next_f = r.get("next_funding") or "—"
            msg = (
                f"{emoji} CFRA ALERT — {coin}\n"
                f"{label}\n\n"
                f"⏳ Funding dalam {mins} menit ({next_f})\n"
                f"💡 {action}\n\n"
                f"——\nAliza CFRA • {_wib_now_label()}"
            )
            await safe_dispatch(msg, chat_id=chat_id, force=True)
    except Exception as e:
        logging.warning("cfra_alert_job: %s", e)


async def macro_check_job(context: ContextTypes.DEFAULT_TYPE):
    """Cek rilis data makro FRED per jam; alert via safe_dispatch (hormati circuit breaker)."""
    try:
        items = check_new_macro_release()
        chat_id = None
        if context and getattr(context, "bot_data", None):
            chat_id = context.bot_data.get("chat_id")
        if not chat_id:
            chat_id = DEFAULT_CHAT_ID
        if not chat_id:
            logging.warning("macro_check_job: no chat_id")
            return
        for item in items:
            msg = format_macro_alert_message(item)
            await safe_dispatch(msg, chat_id=chat_id, force=False)
    except Exception as e:
        logging.error("macro_check_job: %s", e, exc_info=True)


async def check_macro_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("COMMAND RECEIVED: /check_macro")
    target = update.effective_message
    if not target:
        return
    try:
        k = os.getenv("FRED_API_KEY")
        if not k or not str(k).strip():
            await target.reply_text("FRED_API_KEY belum dikonfigurasi di .env")
            return
        text = build_macro_check_command_text()
        if not text.strip():
            await target.reply_text("Data makro tidak tersedia (cek FRED atau koneksi).")
        else:
            await target.reply_text(text)
    except Exception as e:
        logging.error("check_macro_command: %s", e, exc_info=True)
        await target.reply_text("Terjadi kesalahan saat cek makro.")


def _calendar_impact_badge(impact: str) -> str:
    if (impact or "").upper() == "HIGH":
        return "🔴 HIGH"
    return "🟡 MEDIUM"


def _calendar_time_wib_label(event: dict) -> str:
    try:
        dt = datetime.fromisoformat(str(event.get("datetime_wib")))
        return dt.strftime("%H:%M")
    except Exception:
        return "—"


def _format_evening_calendar_alert(events: list[dict]) -> str:
    if not events:
        return ""
    date_label = "Besok"
    try:
        dt = datetime.fromisoformat(str(events[0].get("datetime_wib")))
        date_label = dt.strftime("%d-%m-%Y")
    except Exception:
        pass
    lines = [f"📅 Economic Calendar — Besok {date_label}", ""]
    for e in events:
        lines.append(f"[{_calendar_impact_badge(str(e.get('impact', 'MEDIUM')))}] {e.get('name', '—')}")
        lines.append(f"⏰ {_calendar_time_wib_label(e)} WIB")
        lines.append(f"Sebelumnya: {e.get('previous', '—')} | Forecast: {e.get('forecast', '—')}")
        lines.append("")
    lines.append("💡 Pertimbangkan kurangi posisi sebelum event High Impact.")
    lines.append("——")
    lines.append("Aliza Engine • Economic Calendar")
    return "\n".join(lines)


def _format_calendar_reminder_alert(event: dict) -> str:
    impact = str(event.get("impact", "MEDIUM")).upper()
    tip = (
        "Siapkan diri untuk volatilitas tinggi"
        if impact == "HIGH"
        else "Pantau reaksi market"
    )
    return (
        f"⏰ REMINDER: {event.get('name', 'Event')} dalam 1 jam!\n\n"
        f"Impact: [{_calendar_impact_badge(impact)}]\n"
        f"Jadwal: {_calendar_time_wib_label(event)} WIB\n"
        f"Sebelumnya: {event.get('previous', '—')} | Forecast: {event.get('forecast', '—')}\n\n"
        f"💡 {tip}\n"
        "——\n"
        "Aliza Engine • Economic Calendar"
    )


async def evening_calendar_job(context: ContextTypes.DEFAULT_TYPE):
    """Kirim ringkasan event ekonomi besok (daily 21:00 WIB)."""
    try:
        events = get_events_tomorrow()
        if not events:
            return
        chat_id = None
        if context and getattr(context, "bot_data", None):
            chat_id = context.bot_data.get("chat_id")
        if not chat_id:
            chat_id = DEFAULT_CHAT_ID
        if not chat_id:
            logging.warning("evening_calendar_job: no chat_id")
            return
        await safe_dispatch(_format_evening_calendar_alert(events), chat_id=chat_id, force=False)
    except Exception as e:
        logging.error("evening_calendar_job: %s", e, exc_info=True)


async def calendar_reminder_job(context: ContextTypes.DEFAULT_TYPE):
    """Reminder event H-1 jam dengan cooldown 2 jam per nama event."""
    try:
        events = get_events_next_hour()
        if not events:
            return
        chat_id = None
        if context and getattr(context, "bot_data", None):
            chat_id = context.bot_data.get("chat_id")
        if not chat_id:
            chat_id = DEFAULT_CHAT_ID
        if not chat_id:
            logging.warning("calendar_reminder_job: no chat_id")
            return
        now_utc = datetime.now(timezone.utc)
        for e in events:
            key = str(e.get("name", ""))
            if not key:
                continue
            last_sent = _calendar_reminder_last_sent.get(key)
            if last_sent and (now_utc - last_sent) < timedelta(hours=2):
                continue
            await safe_dispatch(_format_calendar_reminder_alert(e), chat_id=chat_id, force=False)
            _calendar_reminder_last_sent[key] = now_utc
    except Exception as e:
        logging.error("calendar_reminder_job: %s", e, exc_info=True)


async def check_calendar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("COMMAND RECEIVED: /check_calendar")
    target = update.effective_message
    if not target:
        return
    try:
        events = get_upcoming_events(days_ahead=2)
        if not events:
            await target.reply_text("Tidak ada event ekonomi High/Medium impact dalam 2 hari ke depan.")
            return

        grouped: dict[str, list[dict]] = {}
        for e in events:
            try:
                dt_wib = datetime.fromisoformat(str(e.get("datetime_wib")))
                day_key = dt_wib.strftime("%d-%m-%Y")
            except Exception:
                day_key = "Tanggal tidak diketahui"
            grouped.setdefault(day_key, []).append(e)

        lines = ["📅 Economic Calendar (2 hari ke depan)", ""]
        for day in sorted(grouped.keys()):
            lines.append(f"{day}:")
            for e in sorted(grouped[day], key=lambda x: str(x.get("datetime_wib", ""))):
                lines.append(
                    f"- {_calendar_time_wib_label(e)} WIB | {_calendar_impact_badge(str(e.get('impact', 'MEDIUM')))} | {e.get('name', '—')}"
                )
            lines.append("")
        await target.reply_text("\n".join(lines).strip())
    except Exception as e:
        logging.error("check_calendar_command: %s", e, exc_info=True)
        await target.reply_text("Terjadi kesalahan saat cek economic calendar.")


def _wib_now_label() -> str:
    try:
        if ZoneInfo is not None:
            now_wib = datetime.now(ZoneInfo("Asia/Jakarta"))
        else:
            now_wib = datetime.utcnow() + timedelta(hours=7)
    except Exception:
        now_wib = datetime.utcnow() + timedelta(hours=7)
    return now_wib.strftime("%Y-%m-%d %H:%M:%S WIB")


def _whale_alert_allowed(coin: str, condition: str, now_utc: datetime) -> bool:
    key = f"{coin}:{condition}"
    # now_utc is a naive datetime.utcnow() — .timestamp() on a naive datetime is
    # interpreted as LOCAL time, not UTC (Python stdlib behavior). This VPS runs
    # Asia/Jakarta (UTC+7), so a bare .timestamp() here silently stored cooldown
    # epochs 7h in the past. Elapsed-time comparisons still happened to cancel
    # out (same bias on write and read), but the stored absolute timestamps were
    # wrong — found while inspecting data/alert_cooldown_state.json during
    # restart verification (NOTIFIKASI_DEPLOY_VERIFIKASI_REPORT.md).
    now_ts = now_utc.replace(tzinfo=timezone.utc).timestamp()
    if not ngov.is_cooldown_allowed("whale_alert", key, _WHALE_ALERT_COOLDOWN_SEC, now=now_ts):
        return False
    ngov.record_cooldown("whale_alert", key, now=now_ts)
    return True


def _format_whale_buying_alert(coin: str, market_data: dict) -> str:
    return (
        "🐋 WHALE ALERT\n\n"
        f"🟢 {coin} — Tekanan BUYING terdeteksi\n"
        f"Whale Activity: {market_data.get('whale_activity') or '—'}\n"
        f"OI Level: {market_data.get('open_interest_level') or '—'}\n"
        f"Liquidation Risk: {market_data.get('liquidation_risk') or '—'}\n\n"
        "💡 Whale sedang akumulasi — potensi harga naik.\n"
        "Pantau price action dan konfirmasi volume.\n\n"
        f"⏰ {_wib_now_label()}\n"
        "——\n"
        "Aliza Engine • Whale Monitor"
    )


def _format_whale_selling_alert(coin: str, market_data: dict) -> str:
    return (
        "🐋 WHALE ALERT\n\n"
        f"🔴 {coin} — Tekanan SELLING terdeteksi\n"
        f"Whale Activity: {market_data.get('whale_activity') or '—'}\n"
        f"Liquidation Risk: {market_data.get('liquidation_risk') or '—'}\n\n"
        "💡 Tekanan jual dari whale — waspadai penurunan harga.\n"
        "Pertimbangkan kurangi atau tunda posisi long.\n\n"
        f"⏰ {_wib_now_label()}\n"
        "——\n"
        "Aliza Engine • Whale Monitor"
    )


def _format_whale_accumulation_alert(coin: str, market_data: dict, confidence: str) -> str:
    return (
        "🐋 WHALE ACCUMULATION\n\n"
        f"🟡 {coin} — Pola Akumulasi Terdeteksi\n"
        f"Trend: {market_data.get('trend') or '—'} | RSI: {market_data.get('rsi') or '—'} | "
        f"Whale Activity: {market_data.get('whale_activity') or '—'}\n"
        f"Confidence: {confidence}\n\n"
        "💡 Whale terlihat akumulasi sebelum potensi pump.\n"
        "Setup: sideways + RSI recovering + high whale activity.\n\n"
        f"⏰ {_wib_now_label()}\n"
        "——\n"
        "Aliza Engine • Whale Monitor"
    )


async def whale_alert_job(context: ContextTypes.DEFAULT_TYPE):
    """Cek whale pressure/accumulation tiap 10 menit dan kirim alert dengan cooldown."""
    try:
        snapshot = get_market_snapshot()
        data_map = snapshot.get("data") or {}
        if not data_map:
            logging.warning("whale_alert_job: empty snapshot")
            return

        chat_id = None
        if context and getattr(context, "bot_data", None):
            chat_id = context.bot_data.get("chat_id")
        if not chat_id:
            chat_id = DEFAULT_CHAT_ID
        if not chat_id:
            logging.warning("whale_alert_job: no chat_id")
            return

        now_utc = datetime.utcnow()
        for coin in _WHALE_MONITOR_COINS:
            coin_data = data_map.get(coin)
            if not isinstance(coin_data, dict):
                continue

            if not ngov.is_coin_snapshot_fresh(coin_data):
                logging.warning("whale_alert_job: skip %s — stale snapshot data", coin)
                ngov.record_skipped_stale("whale_alert")
                continue

            whale_result = analyze_whale_flow(coin_data) or {}
            whale_pressure = str(whale_result.get("whale_pressure", "NEUTRAL")).upper()
            accumulation_result = detect_whale_accumulation(coin, coin_data) or {}
            has_accum = bool(accumulation_result.get("whale_accumulation"))
            confidence = str(accumulation_result.get("confidence", "MEDIUM"))

            if whale_pressure == "BUYING" and _whale_alert_allowed(coin, "BUYING", now_utc):
                ngov.queue_alert(
                    "whale_alert", "WHALE BUYING", f"{coin} — tekanan BUYING",
                    _format_whale_buying_alert(coin, coin_data),
                )
            if whale_pressure == "SELLING" and _whale_alert_allowed(coin, "SELLING", now_utc):
                ngov.queue_alert(
                    "whale_alert", "WHALE SELLING", f"{coin} — tekanan SELLING",
                    _format_whale_selling_alert(coin, coin_data),
                )
            if has_accum and _whale_alert_allowed(coin, "ACCUMULATION", now_utc):
                ngov.queue_alert(
                    "whale_alert", "WHALE ACCUMULATION", f"{coin} — akumulasi ({confidence})",
                    _format_whale_accumulation_alert(coin, coin_data, confidence),
                )
    except Exception as e:
        logging.error("whale_alert_job: %s", e, exc_info=True)


async def check_whale_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("COMMAND RECEIVED: /check_whale")
    target = update.effective_message
    if not target:
        return
    try:
        snapshot = get_market_snapshot()
        data_map = snapshot.get("data") or {}
        lines = ["🐋 Whale Monitor", ""]
        for coin in _WHALE_MONITOR_COINS:
            coin_data = data_map.get(coin)
            if not isinstance(coin_data, dict):
                lines.append(f"{coin} Pressure: NEUTRAL | Accum: Tidak | RSI: — | Trend: —")
                continue
            whale_result = analyze_whale_flow(coin_data) or {}
            whale_pressure = str(whale_result.get("whale_pressure", "NEUTRAL")).upper()
            accumulation_result = detect_whale_accumulation(coin, coin_data) or {}
            accum_label = "Ya" if accumulation_result.get("whale_accumulation") else "Tidak"
            rsi = coin_data.get("rsi")
            trend = coin_data.get("trend") or "—"
            rsi_label = "—"
            if rsi is not None:
                try:
                    rsi_label = f"{float(rsi):.2f}"
                except (TypeError, ValueError):
                    rsi_label = str(rsi)
            lines.append(
                f"{coin} Pressure: {whale_pressure} | Accum: {accum_label} | RSI: {rsi_label} | Trend: {trend}"
            )
        lines.append("")
        lines.append(f"⏰ {_wib_now_label()}")
        await target.reply_text("\n".join(lines))
    except Exception as e:
        logging.error("check_whale_command: %s", e, exc_info=True)
        await target.reply_text("Terjadi kesalahan saat cek whale monitor.")


def _snapshot_alert_allowed(coin: str, condition: str, now_utc: datetime, pct: float | None = None) -> bool:
    """Persisted cooldown + identical-value dedup gate (survives process restart)."""
    key = f"{coin}:{condition}"
    # See _whale_alert_allowed for why .replace(tzinfo=timezone.utc) is required
    # here instead of a bare now_utc.timestamp() on this naive datetime.
    now_ts = now_utc.replace(tzinfo=timezone.utc).timestamp()
    if not ngov.is_cooldown_allowed("snapshot_alert", key, _SNAPSHOT_ALERT_COOLDOWN_SEC, now=now_ts):
        return False
    # Cek apakah nilai pct sama persis dengan yang terakhir dikirim (data stale/tidak berubah)
    if pct is not None and ngov.is_duplicate_value("snapshot_alert", key, pct):
        return False
    if pct is not None:
        ngov.record_value("snapshot_alert", key, pct)
    ngov.record_cooldown("snapshot_alert", key, now=now_ts)
    return True


def _snapshot_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _snapshot_big_move_pct(coin_data: dict) -> float | None:
    """Prefer price_change_1h; fallback ke perubahan jangka pendek yang ada di snapshot."""
    if not isinstance(coin_data, dict):
        return None
    for key in ("price_change_1h", "price_change_pct_1h", "price_change_1h_pct"):
        x = _snapshot_float(coin_data.get(key))
        if x is not None:
            return x
    for key in ("price_change_percentage_24h", "price_change_pct_24h", "price_change_24h"):
        x = _snapshot_float(coin_data.get(key))
        if x is not None:
            return x
    return None


def _fmt_snapshot_usd(v: float) -> str:
    if v is None:
        return "$—"
    try:
        f = float(v)
        if f == 0:
            return "$0"
        abs_f = abs(f)
        if abs_f >= 1000:
            return f"${f:,.2f}"
        elif abs_f >= 1:
            return f"${f:,.4f}"
        elif abs_f >= 0.01:
            return f"${f:.4f}"
        elif abs_f >= 0.000001:
            return f"${f:.8f}"
        else:
            return f"${f:.10f}"
    except (TypeError, ValueError):
        return "$—"


def _near_level_default_tolerance_pct() -> float:
    """Read the display/detection default without letting a bad env disable the command."""
    try:
        value = float(os.getenv("NEAR_LEVEL_DEFAULT_TOLERANCE_PCT", "1.0"))
        return value if value > 0 else 1.0
    except (TypeError, ValueError):
        return 1.0


NEAR_LEVEL_DEFAULT_TOLERANCE_PCT = _near_level_default_tolerance_pct()
NEAR_LEVEL_PUSH_ENABLED = os.getenv("NEAR_LEVEL_PUSH_ENABLED", "false").strip().lower() in {
    "1", "true", "yes", "on",
}


def get_coins_near_levels(tolerance_pct: float = NEAR_LEVEL_DEFAULT_TOLERANCE_PCT, snapshot: dict | None = None) -> list[dict]:
    """Return near support/resistance rows from one snapshot without dispatching.

    Passing ``snapshot`` makes this deterministic for callers/tests. The
    eligibility rules intentionally match the pre-existing push checkers.
    """
    try:
        tolerance_pct = float(tolerance_pct)
    except (TypeError, ValueError):
        return []
    if tolerance_pct <= 0:
        return []
    if snapshot is None:
        snapshot = get_market_snapshot()
    data_map = snapshot.get("data") if isinstance(snapshot, dict) else None
    if not isinstance(data_map, dict):
        return []

    tolerance = tolerance_pct / 100.0
    rows: list[dict] = []
    for coin in sorted(data_map):
        if coin in ALERT_COIN_BLACKLIST:
            continue
        coin_data = data_map.get(coin)
        if not isinstance(coin_data, dict):
            continue
        price = _snapshot_float(coin_data.get("price"))
        support = _snapshot_float(coin_data.get("support"))
        resistance = _snapshot_float(coin_data.get("resistance"))
        if price is None:
            continue
        if support is not None and support > 0 and resistance is not None and resistance > 0:
            if abs(resistance - support) / support < 0.02:
                continue
        if not ngov.is_coin_snapshot_fresh(coin_data):
            continue
        for side, level in (("support", support), ("resistance", resistance)):
            if level is None or level <= 0:
                continue
            rel = abs(price - level) / level
            if rel >= tolerance or rel < 0.0005:
                continue
            rows.append(
                {
                    "coin": coin,
                    "side": side,
                    "price": price,
                    "level": level,
                    "distance_pct": rel * 100.0,
                }
            )
    return rows


def _format_near_levels_section(levels: list[dict], tolerance_pct: float = NEAR_LEVEL_DEFAULT_TOLERANCE_PCT) -> str:
    """Compact reusable text for /levels and scheduled market reports."""
    support_rows = [row for row in levels if row.get("side") == "support"]
    resistance_rows = [row for row in levels if row.get("side") == "resistance"]
    lines = [f"📍 LEVEL TERDEKAT (toleransi ±{float(tolerance_pct):.2f}%)", "", "🔻 Dekat Support"]
    if support_rows:
        lines.extend(
            f"• {row['coin']} — Harga {_fmt_snapshot_usd(row['price'])} | Support {_fmt_snapshot_usd(row['level'])} | Jarak {row['distance_pct']:.2f}%"
            for row in support_rows
        )
    else:
        lines.append("• Tidak ada coin dekat support saat ini.")
    lines.extend(["", "🔺 Dekat Resistance"])
    if resistance_rows:
        lines.extend(
            f"• {row['coin']} — Harga {_fmt_snapshot_usd(row['price'])} | Resistance {_fmt_snapshot_usd(row['level'])} | Jarak {row['distance_pct']:.2f}%"
            for row in resistance_rows
        )
    else:
        lines.append("• Tidak ada coin dekat resistance saat ini.")
    if not levels:
        lines.extend(["", "Tidak ada coin dekat level saat ini."])
    return "\n".join(lines)


async def _near_level_push_checker(context: ContextTypes.DEFAULT_TYPE, side: str) -> None:
    """Keep the legacy scheduled detector, with individual push behind a flag."""
    levels = [row for row in get_coins_near_levels() if row["side"] == side]
    if not levels:
        return
    if not NEAR_LEVEL_PUSH_ENABLED:
        logging.info("near_level_push disabled: suppressed %d %s candidate(s)", len(levels), side)
        return

    chat_id = None
    if context and getattr(context, "bot_data", None):
        chat_id = context.bot_data.get("chat_id")
    if not chat_id:
        chat_id = DEFAULT_CHAT_ID
    if not chat_id:
        logging.warning("near_%s_checker: no chat_id", side)
        return

    now_utc = datetime.utcnow()
    condition = f"near_{side}"
    for row in levels:
        coin = row["coin"]
        if not _snapshot_alert_allowed(coin, condition, now_utc):
            continue
        if side == "support":
            msg = (
                "📉 NEAR SUPPORT ALERT\n\n"
                f"{coin} mendekati level support!\n"
                f"Harga: {_fmt_snapshot_usd(row['price'])} | Support: {_fmt_snapshot_usd(row['level'])}\n"
                f"Jarak: {row['distance_pct']:.2f}%\n"
                "💡 Potensi bounce — pantau konfirmasi bullish\n"
                "——\n"
                f"Aliza Engine • {_wib_now_label()}"
            )
            label = "NEAR SUPPORT"
        else:
            msg = (
                "📈 NEAR RESISTANCE ALERT\n\n"
                f"{coin} mendekati level resistance!\n"
                f"Harga: {_fmt_snapshot_usd(row['price'])} | Resistance {_fmt_snapshot_usd(row['level'])}\n"
                f"Jarak: {row['distance_pct']:.2f}%\n"
                "💡 Potensi reversal atau breakout — siap ambil profit atau entry short\n"
                "——\n"
                f"Aliza Engine • {_wib_now_label()}"
            )
            label = "NEAR RESISTANCE"
        ngov.queue_alert(condition, label, f"{coin} @ {_fmt_snapshot_usd(row['price'])} (jarak {row['distance_pct']:.2f}%)", msg)


async def near_support_checker(context: ContextTypes.DEFAULT_TYPE):
    """Legacy scheduled support push; disabled by default via NEAR_LEVEL_PUSH_ENABLED."""
    try:
        await _near_level_push_checker(context, "support")
    except Exception as e:
        logging.error("near_support_checker: %s", e, exc_info=True)


async def near_resistance_checker(context: ContextTypes.DEFAULT_TYPE):
    """Legacy scheduled resistance push; disabled by default via NEAR_LEVEL_PUSH_ENABLED."""
    try:
        await _near_level_push_checker(context, "resistance")
    except Exception as e:
        logging.error("near_resistance_checker: %s", e, exc_info=True)


async def rsi_extreme_checker(context: ContextTypes.DEFAULT_TYPE):
    """RSI < 30 atau > 75; cooldown terpisah per (coin, oversold|overbought)."""
    try:
        snapshot = get_market_snapshot()
        data_map = snapshot.get("data") or {}
        if not data_map:
            logging.warning("rsi_extreme_checker: empty snapshot")
            return
        chat_id = None
        if context and getattr(context, "bot_data", None):
            chat_id = context.bot_data.get("chat_id")
        if not chat_id:
            chat_id = DEFAULT_CHAT_ID
        if not chat_id:
            logging.warning("rsi_extreme_checker: no chat_id")
            return
        now_utc = datetime.utcnow()
        for coin in data_map.keys():
            if coin in ALERT_COIN_BLACKLIST:
                continue
            coin_data = data_map.get(coin)
            if not isinstance(coin_data, dict):
                continue
            rsi = _snapshot_float(coin_data.get("rsi"))
            if rsi is None:
                continue
            price = _snapshot_float(coin_data.get("price"))
            if price is None:
                continue
            if not ngov.is_coin_snapshot_fresh(coin_data):
                logging.warning("rsi_extreme_checker: skip %s — stale snapshot data", coin)
                ngov.record_skipped_stale("rsi_extreme")
                continue
            trend = str(coin_data.get("trend") or "—")
            if rsi < 30:
                if not _snapshot_alert_allowed(coin, "oversold", now_utc):
                    continue
                msg = (
                    "🔵 RSI OVERSOLD ALERT\n\n"
                    f"{coin} RSI: {rsi:.1f} — Oversold!\n"
                    f"Harga: {_fmt_snapshot_usd(price)} | Trend: {trend}\n"
                    "💡 Potensi reversal bullish — pantau konfirmasi\n"
                    "——\n"
                    f"Aliza Engine • {_wib_now_label()}"
                )
                ngov.queue_alert("rsi_extreme", "RSI OVERSOLD", f"{coin} RSI {rsi:.1f}", msg)
            elif rsi > 75:
                if not _snapshot_alert_allowed(coin, "overbought", now_utc):
                    continue
                msg = (
                    "🔴 RSI OVERBOUGHT ALERT\n\n"
                    f"{coin} RSI: {rsi:.1f} — Overbought!\n"
                    f"Harga: {_fmt_snapshot_usd(price)} | Trend: {trend}\n"
                    "💡 Pertimbangkan ambil profit atau wait for pullback\n"
                    "——\n"
                    f"Aliza Engine • {_wib_now_label()}"
                )
                ngov.queue_alert("rsi_extreme", "RSI OVERBOUGHT", f"{coin} RSI {rsi:.1f}", msg)
    except Exception as e:
        logging.error("rsi_extreme_checker: %s", e, exc_info=True)


async def big_move_checker(context: ContextTypes.DEFAULT_TYPE):
    """Perubahan harga ≥3% (1h jika ada, else fallback snapshot); cooldown (coin, up|down)."""
    try:
        snapshot = get_market_snapshot()
        data_map = snapshot.get("data") or {}
        if not data_map:
            logging.warning("big_move_checker: empty snapshot")
            return
        chat_id = None
        if context and getattr(context, "bot_data", None):
            chat_id = context.bot_data.get("chat_id")
        if not chat_id:
            chat_id = DEFAULT_CHAT_ID
        if not chat_id:
            logging.warning("big_move_checker: no chat_id")
            return
        now_utc = datetime.utcnow()
        for coin in data_map.keys():
            if coin in ALERT_COIN_BLACKLIST:
                continue
            coin_data = data_map.get(coin)
            if not isinstance(coin_data, dict):
                continue
            pct = _snapshot_big_move_pct(coin_data)
            if pct is None or abs(pct) < 3.0:
                continue
            price = _snapshot_float(coin_data.get("price"))
            if price is None:
                continue
            # Validasi umur data — skip jika snapshot coin lebih dari SNAPSHOT_MAX_AGE_SEC.
            # (Sebelumnya cek ini membandingkan epoch float dengan hasattr/isoformat dan
            # selalu gagal secara diam-diam — lihat NOTIFIKASI_MITIGASI_REPORT.md.)
            if not ngov.is_coin_snapshot_fresh(coin_data):
                logging.warning("big_move_checker: skip %s — stale snapshot data", coin)
                ngov.record_skipped_stale("big_move")
                continue
            direction = "up" if pct > 0 else "down"
            # Cooldown khusus big_move (BIG_MOVE_COOLDOWN_SEC, default 2 jam), per (coin, arah) —
            # terpisah dari cooldown 4 jam near_support/near_resistance/rsi supaya bisa
            # dikonfigurasi independen dan supaya alert naik & turun tidak saling menekan.
            key = f"{coin}:{direction}"
            # See _whale_alert_allowed for why .replace(tzinfo=timezone.utc) is required
            # here instead of a bare now_utc.timestamp() on this naive datetime.
            now_ts = now_utc.replace(tzinfo=timezone.utc).timestamp()
            if not ngov.is_cooldown_allowed("big_move", key, ngov.BIG_MOVE_COOLDOWN_SEC, now=now_ts):
                continue
            if ngov.is_duplicate_value("big_move", key, pct):
                continue  # nilai persis sama dengan alert terakhir — data tidak benar-benar berubah
            if pct > 0:
                msg = (
                    "🚀 BIG MOVE ALERT\n\n"
                    f"{coin} naik {pct:+.2f}% dalam 1 jam!\n"
                    f"Harga: {_fmt_snapshot_usd(price)}\n"
                    "💡 Momentum kuat — pantau apakah breakout atau bull trap\n"
                    "——\n"
                    f"Aliza Engine • {_wib_now_label()}"
                )
            else:
                msg = (
                    "💥 BIG MOVE ALERT\n\n"
                    f"{coin} turun {abs(pct):.2f}% dalam 1 jam!\n"
                    f"Harga: {_fmt_snapshot_usd(price)}\n"
                    "💡 Penurunan tajam — pantau support dan potensi entry\n"
                    "——\n"
                    f"Aliza Engine • {_wib_now_label()}"
                )
            ngov.record_cooldown("big_move", key, now=now_ts)
            ngov.record_value("big_move", key, pct)
            ngov.queue_alert("big_move", "BIG MOVE", f"{coin} {pct:+.2f}% @ {_fmt_snapshot_usd(price)}", msg)
    except Exception as e:
        logging.error("big_move_checker: %s", e, exc_info=True)


async def alert_digest_flush_job(context: ContextTypes.DEFAULT_TYPE):
    """Drain the ngov "noise" alert buffer (near_support/near_resistance/rsi/
    big_move/whale/volume_spike/breakout/funding) every 60s.

    Why a flush job instead of dispatching straight from each checker: the
    2026-07-21 incident (NOTIFIKASI_MITIGASI_REPORT.md) showed that after a
    process restart, every checker's first run fires within the same ~60s
    window and can independently produce a handful of alerts each — 19-20
    Telegram messages landed within 30 seconds. Routing all of them through
    one periodic flush lets a burst be recognized *across* checkers and
    collapsed into a single digest message, and gives the per-hour rate
    limit one choke point to enforce.
    """
    try:
        chat_id = None
        if context and getattr(context, "bot_data", None):
            chat_id = context.bot_data.get("chat_id")
        if not chat_id:
            chat_id = DEFAULT_CHAT_ID

        now = datetime.now(timezone.utc).timestamp()
        summary = ngov.pop_previous_hour_summary(now)
        messages = ngov.flush_pending()
        if not messages and not summary:
            return
        if not chat_id:
            logging.warning("alert_digest_flush_job: no chat_id — dropping %d pending message(s)", len(messages))
            return

        if summary:
            await safe_dispatch(summary, chat_id=chat_id, force=False)

        for msg in messages:
            if ngov.allow_rate_limited_dispatch(now):
                await safe_dispatch(msg, chat_id=chat_id, force=False)
            else:
                logging.warning(
                    "alert_digest_flush_job: MAX_ALERTS_PER_HOUR (%d) reached — suppressing 1 message",
                    ngov.MAX_ALERTS_PER_HOUR,
                )
    except Exception as e:
        logging.error("alert_digest_flush_job: %s", e, exc_info=True)


async def levels_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the current near support/resistance rows without creating an alert."""
    logging.info("COMMAND RECEIVED: /levels")
    target = update.effective_message
    if not target:
        return
    if not _authorized_chat(update):
        await target.reply_text("⛔ Unauthorized.")
        return
    args = list(getattr(context, "args", None) or [])
    if len(args) > 1:
        await target.reply_text("Format: /levels atau /levels 1.5")
        return
    tolerance = NEAR_LEVEL_DEFAULT_TOLERANCE_PCT
    if args:
        try:
            tolerance = float(args[0])
            if tolerance <= 0:
                raise ValueError
        except (TypeError, ValueError):
            await target.reply_text("Toleransi harus angka positif, contoh: /levels 1.5")
            return
    try:
        await target.reply_text(_format_near_levels_section(_near_levels_for_display(tolerance), tolerance))
    except Exception as e:
        logging.error("levels_command: %s", e, exc_info=True)
        await target.reply_text("Terjadi kesalahan saat cek level.")


def _near_levels_for_display(tolerance_pct: float = NEAR_LEVEL_DEFAULT_TOLERANCE_PCT) -> list[dict]:
    """Single on-demand data path shared by /levels and legacy side commands."""
    return get_coins_near_levels(tolerance_pct)


def _format_near_levels_side(levels: list[dict], side: str, tolerance_pct: float) -> str:
    """Present one side of the already-unified near-level result without rechecking it."""
    is_support = side == "support"
    label = "support" if is_support else "resistance"
    icon = "📉" if is_support else "📈"
    level_name = "Support" if is_support else "Resistance"
    rows = [row for row in levels if row.get("side") == side]
    if not rows:
        return f"Tidak ada coin yang dekat {label} saat ini."
    lines = [f"{icon} Near {label} (toleransi ±{float(tolerance_pct):.2f}%):", ""]
    lines.extend(
        f"{row['coin']} — jarak {row['distance_pct']:.2f}% | Harga {_fmt_snapshot_usd(row['price'])} | "
        f"{level_name} {_fmt_snapshot_usd(row['level'])}"
        for row in rows
    )
    return "\n".join(lines)


async def _check_near_level_side_command(update: Update, side: str) -> None:
    target = update.effective_message
    if not target:
        return
    try:
        tolerance = NEAR_LEVEL_DEFAULT_TOLERANCE_PCT
        await target.reply_text(
            _format_near_levels_side(_near_levels_for_display(tolerance), side, tolerance)
        )
    except Exception as e:
        logging.error("check_near_%s_command: %s", side, e, exc_info=True)
        await target.reply_text(f"Terjadi kesalahan saat cek near {side}.")


async def check_near_support_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("COMMAND RECEIVED: /check_near_support")
    await _check_near_level_side_command(update, "support")


async def check_near_resistance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("COMMAND RECEIVED: /check_near_resistance")
    await _check_near_level_side_command(update, "resistance")


async def check_rsi_extreme_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("COMMAND RECEIVED: /check_rsi_extreme")
    target = update.effective_message
    if not target:
        return
    try:
        snapshot = get_market_snapshot()
        data_map = snapshot.get("data") or {}
        oversold: list[str] = []
        overbought: list[str] = []
        for coin in sorted(data_map.keys()):
            coin_data = data_map.get(coin)
            if not isinstance(coin_data, dict):
                continue
            rsi = _snapshot_float(coin_data.get("rsi"))
            if rsi is None:
                continue
            trend = str(coin_data.get("trend") or "—")
            if rsi < 30:
                oversold.append(f"{coin} — RSI {rsi:.1f} | Trend: {trend}")
            elif rsi > 75:
                overbought.append(f"{coin} — RSI {rsi:.1f} | Trend: {trend}")
        if not oversold and not overbought:
            await target.reply_text("Tidak ada coin dengan RSI ekstrem (oversold <30 / overbought >75) saat ini.")
            return
        lines = ["🔵 RSI ekstrem (snapshot):", ""]
        if oversold:
            lines.append("Oversold (<30):")
            lines.extend(oversold)
            lines.append("")
        if overbought:
            lines.append("Overbought (>75):")
            lines.extend(overbought)
        await target.reply_text("\n".join(lines).strip())
    except Exception as e:
        logging.error("check_rsi_extreme_command: %s", e, exc_info=True)
        await target.reply_text("Terjadi kesalahan saat cek RSI ekstrem.")


async def check_big_move_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("COMMAND RECEIVED: /check_big_move")
    target = update.effective_message
    if not target:
        return
    try:
        snapshot = get_market_snapshot()
        data_map = snapshot.get("data") or {}
        up: list[str] = []
        down: list[str] = []
        for coin in sorted(data_map.keys()):
            coin_data = data_map.get(coin)
            if not isinstance(coin_data, dict):
                continue
            pct = _snapshot_big_move_pct(coin_data)
            if pct is None or abs(pct) < 3.0:
                continue
            price = _snapshot_float(coin_data.get("price"))
            if price is None:
                continue
            # Validasi umur data — skip jika snapshot coin lebih dari 30 menit
            coin_ts = coin_data.get("timestamp") or coin_data.get("last_updated")
            if coin_ts:
                try:
                    from datetime import timezone as _tz
                    if hasattr(coin_ts, "timestamp"):
                        age_sec = (datetime.now(_tz.utc) - coin_ts.replace(tzinfo=_tz.utc) if coin_ts.tzinfo is None else datetime.now(_tz.utc) - coin_ts).total_seconds()
                    else:
                        age_sec = (datetime.utcnow() - datetime.fromisoformat(str(coin_ts))).total_seconds()
                    if age_sec > 1800:  # 30 menit
                        continue
                except Exception:
                    pass
            line = f"{coin} — {pct:+.2f}% | Harga {_fmt_snapshot_usd(price)}"
            if pct > 0:
                up.append(line)
            else:
                down.append(line)
        if not up and not down:
            await target.reply_text("Tidak ada coin dengan perubahan ≥3% (1h atau fallback snapshot) saat ini.")
            return
        lines = ["💥 Big move (|Δ|≥3%):", ""]
        if up:
            lines.append("Naik:")
            lines.extend(up)
            lines.append("")
        if down:
            lines.append("Turun:")
            lines.extend(down)
        await target.reply_text("\n".join(lines).strip())
    except Exception as e:
        logging.error("check_big_move_command: %s", e, exc_info=True)
        await target.reply_text("Terjadi kesalahan saat cek big move.")


def _format_signal_duration(signal_time: str | None, close_time: str | None) -> str:
    try:
        if not signal_time or not close_time:
            return "—"
        st = datetime.fromisoformat(signal_time)
        ct = datetime.fromisoformat(close_time)
        delta = ct - st
        total_sec = int(delta.total_seconds())
        if total_sec < 3600:
            mins = max(1, total_sec // 60)
            return f"{mins} menit"
        if total_sec < 86400:
            return f"{total_sec / 3600:.1f} jam"
        return f"{total_sec / 86400:.1f} hari"
    except Exception:
        return "—"


def _format_signal_closed_alert(item: dict) -> str:
    coin = item.get("coin", "—")
    setup = item.get("setup", "—")
    entry = item.get("entry_price")
    close = item.get("close_price")
    pnl = item.get("pnl_pct")
    status = item.get("status", "")
    dur = _format_signal_duration(item.get("signal_time"), item.get("close_time"))

    entry_s = f"${float(entry):,.4f}" if entry is not None else "—"
    close_s = f"${float(close):,.4f}" if close is not None else "—"
    pnl_s = f"{float(pnl):+.2f}%" if pnl is not None else "—"

    if status == "WIN":
        return (
            f"✅ SINYAL WIN — {coin}\n"
            f"Setup: {setup} | Entry: {entry_s} → Close: {close_s}\n"
            f"Profit: {pnl_s}\n"
            f"Durasi: {dur}\n"
            "——\n"
            "Aliza Engine • Signal Tracker"
        )
    if status == "LOSS":
        return (
            f"❌ SINYAL LOSS — {coin}\n"
            f"Setup: {setup} | Entry: {entry_s} → Close: {close_s}\n"
            f"Loss: {pnl_s}\n"
            f"Durasi: {dur}\n"
            "——\n"
            "Aliza Engine • Signal Tracker"
        )
    return ""


async def signal_check_job(context: ContextTypes.DEFAULT_TYPE):
    """Cek sinyal OPEN setiap 10 menit, update WIN/LOSS/EXPIRED, dan kirim notifikasi."""
    try:
        closed = check_open_signals()
        if not closed:
            return
        chat_id = None
        if context and getattr(context, "bot_data", None):
            chat_id = context.bot_data.get("chat_id")
        if not chat_id:
            chat_id = DEFAULT_CHAT_ID
        if not chat_id:
            logging.warning("signal_check_job: no chat_id")
            return
        for item in closed:
            if item.get("status") not in {"WIN", "LOSS"}:
                continue
            msg = _format_signal_closed_alert(item)
            if msg:
                await safe_dispatch(msg, chat_id=chat_id, force=False)
    except Exception as e:
        logging.warning("signal_check_job: %s", e)


async def signal_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("COMMAND RECEIVED: /signal_stats")
    target = update.effective_message
    if not target:
        return
    try:
        stats = get_signal_stats()
        if int(stats.get("total_signals", 0)) == 0:
            await target.reply_text("Belum ada data sinyal yang tercatat.")
            return

        best = stats.get("best_trade")
        worst = stats.get("worst_trade")
        best_line = "Best trade: —"
        worst_line = "Worst trade: —"
        if best:
            best_line = (
                f"Best trade: {best.get('coin', '—')} {best.get('setup', '—')} "
                f"{float(best.get('pnl_pct', 0.0)):+.2f}%"
            )
        if worst:
            worst_line = (
                f"Worst trade: {worst.get('coin', '—')} {worst.get('setup', '—')} "
                f"{float(worst.get('pnl_pct', 0.0)):+.2f}%"
            )

        lines = [
            "📊 Signal Accuracy Stats",
            "",
            f"Total sinyal: {int(stats.get('total_signals', 0))}",
            (
                f"✅ WIN: {int(stats.get('win', 0))} | ❌ LOSS: {int(stats.get('loss', 0))} | "
                f"⏳ Open: {int(stats.get('open', 0))} | ⌛ Expired: {int(stats.get('expired', 0))}"
            ),
            f"Win Rate: {float(stats.get('win_rate', 0.0)):.1f}%",
            f"Avg P&L: {float(stats.get('avg_pnl', 0.0)):+.1f}%",
            "",
            best_line,
            worst_line,
            "",
            "Per Coin:",
        ]
        by_coin = stats.get("by_coin") or []
        if by_coin:
            for row in by_coin:
                lines.append(
                    f"{row.get('coin', '—')}: {int(row.get('win', 0))}W/{int(row.get('loss', 0))}L — {float(row.get('win_rate', 0.0)):.1f}% win rate"
                )
        else:
            lines.append("Belum ada data per coin.")
        lines.append("")
        lines.append(f"⏰ {_wib_now_label()}")
        await target.reply_text("\n".join(lines))
    except Exception as e:
        logging.warning("signal_stats_command: %s", e)
        await target.reply_text("Terjadi kesalahan saat membaca statistik sinyal.")



async def shadow_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ringkasan outcome E3 shadow, terpisah dari /signal_stats produksi."""
    msg = update.effective_message
    if not msg or not _authorized_chat(update):
        return
    try:
        stats = get_signal_stats(source="shadow_e3")
        lines = [
            "🧪 Shadow E3 Stats",
            f"N: {int(stats.get('total_signals', 0))} | WIN {int(stats.get('win', 0))} | LOSS {int(stats.get('loss', 0))} | OPEN {int(stats.get('open', 0))}",
            f"WR: {float(stats.get('win_rate', 0)):.2f}% | Expectancy: {float(stats.get('avg_pnl', 0)):+.3f}%",
            "Per setup:",
        ]
        for row in stats.get("by_setup") or []:
            lines.append(f"- {row.get('setup')}: N={row.get('total')} W={row.get('win')} L={row.get('loss')} WR={float(row.get('win_rate', 0)):.1f}%")
        await msg.reply_text("\n".join(lines))
    except Exception as exc:  # noqa: BLE001
        logging.warning("shadow_stats_command: %s", exc)
        await msg.reply_text("Gagal membaca statistik shadow.")


# ========== WEEKLY WINRATE SUMMARY (proaktif, tanpa perlu /signal_stats manual) ==========

# Ambang "cukup data untuk winrate bermakna" -- sengaja disamakan dengan
# LEARNING_MIN_SAMPLES (default 10, engine/learning/confidence_adjuster.py) supaya
# konsisten: angka yang sama dipakai baik untuk menahan penyesuaian confidence
# maupun untuk memutuskan kapan menampilkan winrate tanpa disclaimer di ringkasan
# ini. Dibaca independen (bukan impor fungsi privat lintas modul) supaya modul
# statistik yang sudah ada tidak perlu diubah sama sekali.
WEEKLY_SUMMARY_MIN_SAMPLES_DEFAULT = 10


def _weekly_summary_min_samples() -> int:
    try:
        value = int(os.environ.get("LEARNING_MIN_SAMPLES", str(WEEKLY_SUMMARY_MIN_SAMPLES_DEFAULT)))
        return value if value > 0 else WEEKLY_SUMMARY_MIN_SAMPLES_DEFAULT
    except (TypeError, ValueError):
        return WEEKLY_SUMMARY_MIN_SAMPLES_DEFAULT


def _format_source_block(label: str, emoji: str, source: str) -> str:
    """Satu blok ringkasan (total/WIN/LOSS/OPEN, winrate + disclaimer bila perlu,
    avg RR/profit factor bila ada closed trade) untuk satu source."""
    stats = get_signal_stats(source=source)
    total = int(stats.get("total_signals", 0) or 0)
    win = int(stats.get("win", 0) or 0)
    loss = int(stats.get("loss", 0) or 0)
    open_n = int(stats.get("open", 0) or 0)
    expired = int(stats.get("expired", 0) or 0)
    closed = win + loss
    win_rate = float(stats.get("win_rate", 0.0) or 0.0)

    lines = [
        f"{emoji} {label}",
        f"Total sinyal: {total} | WIN: {win} | LOSS: {loss} | OPEN: {open_n} | EXPIRED: {expired}",
    ]

    if total == 0:
        lines.append("Belum ada sinyal tercatat untuk source ini.")
        return "\n".join(lines)

    min_samples = _weekly_summary_min_samples()
    if closed < min_samples:
        lines.append(
            f"Winrate: {win_rate:.1f}% (N={closed} closed) — ⚠️ BELUM CUKUP DATA "
            f"untuk kesimpulan bermakna (ambang {min_samples} closed outcome)."
        )
    else:
        lines.append(f"Winrate: {win_rate:.1f}% (N={closed} closed)")

    if get_closed_history is not None and analyze_performance is not None:
        try:
            closed_history = get_closed_history(source=source)
            perf = analyze_performance(closed_history)
            if perf.get("total_trades", 0) > 0:
                lines.append(
                    f"Avg RR: {float(perf.get('avg_rr', 0.0)):.2f} | "
                    f"Profit Factor: {float(perf.get('profit_factor', 0.0)):.2f}"
                )
        except Exception as exc:  # noqa: BLE001
            logging.debug("weekly_winrate_summary avg_rr/profit_factor (%s): %s", source, exc)

    return "\n".join(lines)


def _weekly_summary_new_signal_note(source: str, current_total: int) -> str:
    """Bandingkan total_signals sekarang dengan yang tersimpan saat ringkasan
    terakhir dikirim (persisted via notification_governor, tahan restart).
    Tidak pernah men-skip pengiriman -- hanya menambah satu baris status."""
    key = f"last_total_{source}"
    last_total = ngov.get_value("weekly_winrate_summary", key, 0)
    try:
        last_total = int(last_total)
    except (TypeError, ValueError):
        last_total = 0
    new_count = max(0, current_total - last_total)
    if new_count == 0:
        return "Tidak ada sinyal baru minggu ini."
    return f"+{new_count} sinyal baru sejak ringkasan minggu lalu."


def _weekly_summary_save_totals(deterministic_total: int, shadow_total: int) -> None:
    ngov.set_value("weekly_winrate_summary", "last_total_deterministic", deterministic_total)
    ngov.set_value("weekly_winrate_summary", "last_total_shadow_e3", shadow_total)


def format_weekly_winrate_summary() -> str:
    """Bangun teks ringkasan winrate mingguan lengkap: produksi (deterministic)
    + riset (shadow_e3), status breaker, dan catatan sinyal baru sejak ringkasan
    terakhir. Angka lifetime sejak Fase 1 deploy (bukan direset per minggu) --
    winrate makin bermakna makin banyak data terkumpul."""
    det_stats = get_signal_stats(source="deterministic")
    shadow_stats = get_signal_stats(source="shadow_e3")
    det_total = int(det_stats.get("total_signals", 0) or 0)
    shadow_total = int(shadow_stats.get("total_signals", 0) or 0)

    lines = ["📅 RINGKASAN WINRATE MINGGUAN", ""]
    lines.append(_format_source_block("PRODUKSI (deterministic)", "🟢", "deterministic"))
    lines.append(_weekly_summary_new_signal_note("deterministic", det_total))
    lines.append("")
    lines.append(_format_source_block("RISET (shadow_e3 — BUKAN sinyal produksi)", "🧪", "shadow_e3"))
    lines.append(_weekly_summary_new_signal_note("shadow_e3", shadow_total))
    lines.append("")

    breaker_line = "⚙️ Circuit breaker: status tidak tersedia."
    if check_drawdown is not None:
        try:
            dd = check_drawdown()
            if dd.get("trading_allowed", True):
                breaker_line = "⚙️ Circuit breaker: tidak aktif (sinyal produksi berjalan normal)."
            else:
                breaker_line = (
                    f"⚙️ Circuit breaker: AKTIF — loss streak {dd.get('loss_streak')} "
                    "(pengiriman [TRADE SIGNAL] baru sedang dijeda)."
                )
        except Exception as exc:  # noqa: BLE001
            logging.debug("weekly_winrate_summary check_drawdown: %s", exc)
    lines.append(breaker_line)

    lines.append("")
    lines.append(f"⏰ {_wib_now_label()}")

    _weekly_summary_save_totals(det_total, shadow_total)
    return "\n".join(lines)


async def weekly_winrate_summary_job(context: ContextTypes.DEFAULT_TYPE):
    """Kirim ringkasan winrate mingguan proaktif (Senin 08:00 WIB) -- lihat
    WEEKLY_WINRATE_SUMMARY_REPORT.md. Satu pesan per minggu, tidak pernah di-skip
    walau tidak ada sinyal baru (hanya menyatakan itu secara eksplisit)."""
    chat_id = None
    try:
        if context and getattr(context, "bot_data", None):
            chat_id = context.bot_data.get("chat_id")
    except Exception:
        chat_id = None
    if not chat_id:
        chat_id = DEFAULT_CHAT_ID
    if not chat_id:
        logging.warning("weekly_winrate_summary_job: no chat_id (set TELEGRAM_CHAT_ID or /start)")
        return

    try:
        message = format_weekly_winrate_summary()
    except Exception as exc:  # noqa: BLE001
        logging.error("weekly_winrate_summary_job: failed to build message: %s", exc)
        return

    try:
        await safe_dispatch(message, chat_id=chat_id, force=True)
    except Exception as exc:  # noqa: BLE001
        logging.error("weekly_winrate_summary_job: dispatch failed: %s", exc)


async def weekly_winrate_summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("COMMAND RECEIVED: /weekly_winrate")
    await weekly_winrate_summary_job(context)


async def shadow_promotion_check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Read-only: hitung status kriteria promosi shadow_e3 -> produksi
    (FASE4_REPORT.md) dari data live. Tidak pernah mengubah SHADOW_E3_ENABLED/
    SHADOW_E3_DISPATCH atau state apa pun -- keputusan promosi tetap manual.
    Command terpisah dari /shadow_stats (bukan perluasan) -- lihat
    SHADOW_PROMOTION_CHECKLIST_REPORT.md untuk alasannya."""
    msg = update.effective_message
    if not msg:
        return
    if not _authorized_chat(update):
        await msg.reply_text("⛔ Unauthorized.")
        return
    try:
        result = evaluate_promotion_criteria(source="shadow_e3")
        await msg.reply_text(format_promotion_check_message(result))
    except Exception as exc:  # noqa: BLE001
        logging.warning("shadow_promotion_check_command: %s", exc)
        await msg.reply_text("Gagal menghitung kriteria promosi shadow.")


# ========== SNAPSHOT JOB (background, every 60s) ==========

DRAWDOWN_BREAKER_ACTIVATED_MSG = (
    "⚠️ Circuit breaker aktif — 3 sinyal produksi beruntun rugi. Pengiriman sinyal "
    "[TRADE SIGNAL] dijeda sampai ada sinyal yang profit lagi. (Ini bukan berarti "
    "trading dihentikan permanen — cuma jeda otomatis untuk mencegah kerugian beruntun.)"
)
DRAWDOWN_BREAKER_RESET_MSG = (
    "✅ Circuit breaker nonaktif — sinyal [TRADE SIGNAL] kembali dikirim normal."
)


async def _notify_drawdown_breaker_transition(chat_id) -> None:
    """Kirim SATU notifikasi saat status drawdown breaker berubah (aktif pertama
    kali / reset), tanpa spam tiap siklus snapshot (~60s). Status terakhir yang
    sudah dinotifikasi disimpan lewat notification_governor (persisted ke
    data/alert_cooldown_state.json, tahan restart proses) -- pola yang sama dipakai
    shadow_e3 cooldown. Lihat DRAWDOWN_BROADCAST_GATE_REPORT.md."""
    if check_drawdown is None:
        return
    try:
        dd = check_drawdown()
    except Exception as exc:
        logging.debug("drawdown breaker transition check failed: %s", exc)
        return
    active_now = not dd.get("trading_allowed", True)
    was_active = bool(ngov.get_value("drawdown_breaker", "active", False))
    if active_now == was_active:
        return
    ngov.set_value("drawdown_breaker", "active", active_now)
    msg = DRAWDOWN_BREAKER_ACTIVATED_MSG if active_now else DRAWDOWN_BREAKER_RESET_MSG
    try:
        await safe_dispatch(msg, chat_id=chat_id, force=True)
    except Exception as exc:
        logging.warning("drawdown breaker transition notify failed: %s", exc)


async def _dispatch_and_record_deterministic_signal(sig: dict, chat_id) -> bool:
    """Dispatch lewat gateway; persist tracking hanya setelah pengiriman sukses (atau
    setelah lolos seluruh gate tapi ditekan oleh drawdown breaker -- lihat
    DRAWDOWN_BROADCAST_GATE_REPORT.md). Breaker hanya menahan dispatch Telegram;
    sinyal tetap dicatat ke signal_tracking (dispatch_status='SUPPRESSED') supaya
    statistik/winrate tidak bolong."""
    key = f"{sig.get('coin', '')}|{sig.get('setup', '')}"
    uni = attach_strategy_source(sig)

    breaker_active = False
    loss_streak = None
    if check_drawdown is not None:
        try:
            dd = check_drawdown()
            breaker_active = not dd.get("trading_allowed", True)
            loss_streak = dd.get("loss_streak")
        except Exception as dd_err:
            logging.debug("drawdown check failed, defaulting to allowed: %s", dd_err)

    sent = await process_signal(
        key,
        uni,
        format_signal_message(uni),
        chat_id=chat_id,
        suppress_dispatch=breaker_active,
    )
    if not sent:
        return False

    if breaker_active:
        logging.info(
            "[TRADE SIGNAL] SUPPRESSED — drawdown breaker active, loss_streak=%s coin=%s setup=%s",
            loss_streak, sig.get("coin"), sig.get("setup"),
        )

    try:
        sig_to_record = dict(sig)
        sig_to_record.setdefault(
            "signal_time",
            datetime.now(timezone(timedelta(hours=7))).isoformat(),
        )
        sig_to_record.setdefault(
            "tp", sig.get("tp") or sig.get("tp1") or sig.get("take_profit")
        )
        sig_to_record["dispatch_status"] = "SUPPRESSED" if breaker_active else "SENT"
        sig_to_record["source"] = "deterministic"
        mctx = calculate_market_score()
        sig_to_record["market_score"] = mctx.get("total_score")
        try:
            snapshot = get_market_snapshot()
            regime = (
                (snapshot.get("market_intelligence") or {}).get("market_regime")
                or "UNKNOWN"
            )
        except Exception:
            regime = "UNKNOWN"
        sig_to_record["regime"] = regime
        record_signal(sig_to_record)
    except Exception as track_err:
        logging.warning("signal_tracker record failed after dispatch: %s", track_err)
    return True


def _shadow_signal_allowed(coin: str, setup: str, side: str, now_ts: float | None = None) -> bool:
    """Persisted cooldown gate per (coin, setup, side) — survives process restart,
    same mechanism as near_support/near_resistance/whale (see notification_governor).
    Prevents re-firing every ~60s snapshot cycle while a setup stays satisfied."""
    key = f"{coin}:{setup}:{side}"
    return ngov.is_cooldown_allowed("shadow_e3", key, shadow_dispatch_cooldown_sec(), now=now_ts)


def _record_shadow_cooldown(coin: str, setup: str, side: str, now_ts: float | None = None) -> None:
    key = f"{coin}:{setup}:{side}"
    ngov.record_cooldown("shadow_e3", key, now=now_ts)


async def _run_shadow_e3(snapshot: dict, chat_id) -> int:
    """Jalankan E3 riset secara terpisah; tidak pernah memanggil process_signal."""
    try:
        candidates = collect_shadow_signals(snapshot)
        dispatched = shadow_dispatch_enabled()
        now_ts = time_module.time()
        recorded = 0
        for candidate in candidates:
            shadow = dict(candidate)
            coin = str(shadow.get("coin") or "")
            setup = str(shadow.get("setup") or "")
            side = str(shadow.get("side") or "")
            if dispatched:
                if not _shadow_signal_allowed(coin, setup, side, now_ts):
                    shadow["dispatch_status"] = "COOLDOWN"
                else:
                    sent = await safe_dispatch(format_shadow_message(shadow), chat_id=chat_id)
                    if not sent:
                        logging.warning("shadow_e3 dispatch failed coin=%s", shadow.get("coin"))
                        continue
                    _record_shadow_cooldown(coin, setup, side, now_ts)
                    shadow["dispatch_status"] = "SENT"
            else:
                shadow["dispatch_status"] = "RECORDED"
            if record_signal(shadow):
                recorded += 1
        logging.info("shadow_e3 recorded=%d dispatch=%s", recorded, dispatched)
        return recorded
    except Exception as exc:  # noqa: BLE001
        logging.warning("shadow_e3 runtime error: %s", exc)
        return 0


async def snapshot_job(context: ContextTypes.DEFAULT_TYPE):
    """Refresh market snapshot; run in executor to avoid blocking the event loop."""
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, update_market_snapshot)
        logging.info("Market snapshot updated")

        # ambil snapshot sekali saja agar tidak double call
        snapshot = get_market_snapshot()
        if not is_snapshot_valid(snapshot, SNAPSHOT_MAX_AGE_SEC):
            logging.warning("GLOBAL GUARD: SNAPSHOT INVALID — ABORTING PROCESS")
            with snapshot_state._snapshot_lock:
                cb_active = snapshot_state.CIRCUIT_BREAKER_ACTIVE
                cb_alert_sent = snapshot_state.CB_ALERT_SENT
            if cb_active:
                logging.critical("SYSTEM HALTED: CIRCUIT BREAKER ACTIVE")
                chat_id = context.bot_data.get("chat_id")
                if not cb_alert_sent:
                    try:
                        await process_signal(
                            "system_halt",
                            {"source": "system", "type": "halt"},
                            "⚠️ SYSTEM HALTED: Market data invalid. Trading paused.",
                            chat_id=chat_id,
                            force=True,
                        )
                    finally:
                        with snapshot_state._snapshot_lock:
                            snapshot_state.CB_ALERT_SENT = True
            return
        with snapshot_state._snapshot_lock:
            cb_active = snapshot_state.CIRCUIT_BREAKER_ACTIVE
            cb_alert_sent = snapshot_state.CB_ALERT_SENT
            recovery_pending = snapshot_state.CB_RECOVERY_ALERT_PENDING
        if cb_active:
            logging.critical("SYSTEM HALTED: CIRCUIT BREAKER ACTIVE")
            chat_id = context.bot_data.get("chat_id")
            if not cb_alert_sent:
                try:
                    await process_signal(
                        "system_halt",
                        {"source": "system", "type": "halt"},
                        "⚠️ SYSTEM HALTED: Market data invalid. Trading paused.",
                        chat_id=chat_id,
                        force=True,
                    )
                finally:
                    with snapshot_state._snapshot_lock:
                        snapshot_state.CB_ALERT_SENT = True
            return
        if recovery_pending:
            chat_id = context.bot_data.get("chat_id")
            await process_signal(
                "system_recovered",
                {"source": "system", "type": "recovery"},
                "✅ SYSTEM RECOVERED: Market data normal.",
                chat_id=chat_id,
                force=True,
            )
            with snapshot_state._snapshot_lock:
                snapshot_state.CB_RECOVERY_ALERT_PENDING = False

        # Auto alert: score default ≥70 (valid 0–100), rr≥2.5, confidence≥65.
        if process_auto_alerts is not None:
            try:
                opportunities = scan_opportunities()
                alerts = process_auto_alerts(opportunities)
                if alerts:
                    for a in alerts:
                        try:
                            key = f"{a.get('coin', '')}|{a.get('setup', '')}"
                            sent = await process_signal(
                                key,
                                a.get("signal"),
                                a["message"],
                                chat_id=context.bot_data.get("chat_id"),
                            )
                            if sent:
                                logging.info("Auto alert sent for %s", a["coin"])
                        except Exception as send_err:
                            logging.warning("Auto alert send failed for %s: %s", a.get("coin"), send_err)
            except Exception as alert_err:
                logging.debug("Auto alert process error: %s", alert_err)

        # Drawdown breaker transition notice: checked every cycle (not only when a
        # new signal is detected) so a streak that closes via signal_check_job
        # between detections still gets a timely transition message.
        try:
            await _notify_drawdown_breaker_transition(context.bot_data.get("chat_id"))
        except Exception as dd_notify_err:
            logging.debug("Drawdown breaker transition notice error: %s", dd_notify_err)

        # High probability trade (strategy): unified gateway (risk + dedup + state)
        try:
            sig = scan_for_signals()
            if sig:
                chat_id = context.bot_data.get("chat_id")
                await _dispatch_and_record_deterministic_signal(sig, chat_id)
        except Exception as sig_err:
            logging.debug("Signal engine dispatch error: %s", sig_err)

        # E3 shadow: jalur riset terisolasi, default OFF, tanpa dedup gateway produksi.
        await _run_shadow_e3(snapshot, context.bot_data.get("chat_id"))

        # BTC smart alert (NON-SPAM): hanya kirim saat signal berubah
        if analyze_btc_signal is not None and should_alert_btc is not None and should_send_alert is not None:
            try:
                chat_id = context.bot_data.get("chat_id")
                if chat_id:
                    btc_signal = analyze_btc_signal(snapshot)
                    signal = btc_signal.get("signal")
                    confidence = btc_signal.get("confidence", 0)

                    if should_alert_btc(signal) and confidence >= 75:
                        if should_send_alert("BTC", signal):
                            message = (
                                f"🚨 BTC SMART ALERT\n\n"
                                f"Signal       : {signal}\n"
                                f"Phase        : {btc_signal.get('phase')}\n"
                                f"Confidence   : {btc_signal.get('confidence')}\n\n"
                                f"Reason:\n{btc_signal.get('reason')}\n\n"
                                f"📌 Action:\n{btc_signal.get('recommendation')}"
                            )
                            btc_row = (snapshot.get("data") or {}).get("BTC") or {}
                            tsu = btc_row.get("trade_setup") or {}
                            btc_sig = {
                                "symbol": "BTCUSDT",
                                "type": str(signal),
                                "entry": btc_row.get("price"),
                                "stop_loss": tsu.get("sl"),
                                "take_profit": tsu.get("tp1"),
                                "confidence": confidence,
                                "source": "btc_alert",
                                "coin": "BTC",
                                "setup": str(btc_signal.get("phase") or ""),
                                "signal_type": SIGNAL_TYPE_INFORMATIONAL,
                            }
                            await process_signal(
                                f"BTC|{signal}",
                                btc_sig,
                                message,
                                chat_id=chat_id,
                            )
            except Exception as btc_err:
                logging.debug("BTC smart alert error: %s", btc_err)
    except Exception as e:
        logging.error("Snapshot job error: %s", e)


# ========== WATCHDOG JOB (AI Watchdog, every 2 min) ==========

async def watchdog_job(context: ContextTypes.DEFAULT_TYPE):
    """AI Watchdog: health check setiap 2 menit; kirim alert ke Telegram jika ada masalah."""
    try:
        alerts = check_system_health()
        if alerts:
            message = "⚠️ ALIZA SYSTEM WARNING\n\n"
            for alert in alerts:
                message += f"• {alert}\n"
            chat_id = context.bot_data.get("chat_id")
            if chat_id:
                await process_signal(
                    "watchdog_health",
                    {"source": "watchdog", "type": "health"},
                    message,
                    chat_id=chat_id,
                )
            else:
                logging.warning("Watchdog: alerts generated but no chat_id (user has not /start)")
    except Exception as e:
        logging.error("Watchdog error", exc_info=True)


# ========== MAIN ==========

async def _post_init_set_bot_commands(application):
    """Daftarkan command menu Telegram (BotFather / slash menu)."""
    try:
        await application.bot.set_my_commands(
            [
                BotCommand("start", "Mulai bot"),
                BotCommand("help", "Panduan command"),
                BotCommand("market", "Kondisi market coin"),
                BotCommand("radar", "Radar trend semua coin"),
                BotCommand("setfutures", "Peluang trading terbaik"),
                BotCommand("entry", "Buka posisi"),
                BotCommand("close", "Tutup posisi"),
                BotCommand("portfolio", "Posisi aktif"),
                BotCommand("set_balance", "Set modal akun (USDT) untuk position sizing"),
                BotCommand("balance", "Lihat ringkasan akun dan risk"),
                BotCommand("status", "Status sistem"),
                BotCommand("levels", "Cek coin dekat support/resistance"),
                BotCommand("performance", "Kinerja Trade (RR/PF)"),
                BotCommand("alert_stats", "Statistik alert dan digest"),
                BotCommand("snapshot", "Snapshot market saat ini"),
                BotCommand("health", "Health sistem"),
                BotCommand("weekly_winrate", "Ringkasan winrate mingguan"),
                BotCommand("shadow_stats", "Statistik shadow E3"),
                BotCommand("shadow_promotion_check", "Cek promosi Shadow E3"),
            ]
        )
    except Exception as e:
        logging.warning("set_my_commands failed: %s", e)


def main():
    if not BOT_TOKEN:
        logging.error("TELEGRAM_BOT_TOKEN not set. Stopping Telegram bot service.")
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set")

    init_trade_db()
    init_signal_tracking_db()
    update_market_snapshot()
    logging.info("Market snapshot initial update done")
    logging.info(
        "Telegram dispatcher mode: %s",
        "PRIMARY (alerts enabled)" if IS_PRIMARY_DISPATCHER else "NON-PRIMARY (alerts skipped)",
    )
    logging.info(
        "Shadow E3 mode: enabled=%s dispatch=%s",
        os.getenv("SHADOW_E3_ENABLED", "false"),
        os.getenv("SHADOW_E3_DISPATCH", "false"),
    )

    shutdown_controller = None

    async def _post_shutdown(application):
        if shutdown_controller is not None:
            await shutdown_controller.post_shutdown(application)

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(_post_init_set_bot_commands)
        .post_shutdown(_post_shutdown)
        .build()
    )
    shutdown_controller = GracefulShutdownController(app, timeout_seconds=8.0)

    app.add_handler(TypeHandler(Update, _authorization_gate), group=-1)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("why", why_command))
    app.add_handler(CommandHandler("spot", spot_command))
    app.add_handler(CommandHandler("btc", btc_command))
    app.add_handler(CommandHandler("market", market))
    app.add_handler(CallbackQueryHandler(coin_selector_callback))
    app.add_handler(CommandHandler("radar", radar))
    app.add_handler(CommandHandler("radarpro", radarpro_command))
    app.add_handler(CommandHandler("setfutures", setfutures))
    app.add_handler(CommandHandler("entry", entry))
    app.add_handler(CommandHandler("set_balance", cmd_set_balance))
    app.add_handler(CommandHandler("balance", cmd_get_balance))
    logging.info("Handlers aktif: set_balance, balance (Portfolio & Risk — pastikan restart bot setelah deploy)")
    app.add_handler(CommandHandler("close", close))
    app.add_handler(CommandHandler("performance", performance_command))
    app.add_handler(CommandHandler("portfolio", portfolio))
    app.add_handler(CommandHandler("predict", predict))
    app.add_handler(CommandHandler("quant", quant_command))
    app.add_handler(CommandHandler("marketstate", marketstate_command))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("alert_stats", alert_stats_command))
    app.add_handler(CommandHandler("levels", levels_command))
    app.add_handler(CommandHandler("testalert", testalert))
    app.add_handler(CommandHandler("marketdebug", marketdebug))
    app.add_handler(CommandHandler("market_context", market_context_command))
    app.add_handler(CommandHandler("snapshot", snapshot_command))
    app.add_handler(CommandHandler("health", health_command))
    app.add_handler(CommandHandler("morning_brief", morning_brief_command))
    app.add_handler(CommandHandler("evening_summary", evening_summary_command))
    app.add_handler(CommandHandler("spot_signal", spot_signal_command))
    app.add_handler(CommandHandler("check_breakout", check_breakout_command))
    app.add_handler(CommandHandler("check_volume_spike", check_volume_spike_command))
    app.add_handler(CommandHandler("check_funding", check_funding_command))
    app.add_handler(CommandHandler("cfra", cfra_command))
    app.add_handler(CommandHandler("check_macro", check_macro_command))
    app.add_handler(CommandHandler("check_calendar", check_calendar_command))
    app.add_handler(CommandHandler("check_whale", check_whale_command))
    app.add_handler(CommandHandler("check_near_support", check_near_support_command))
    app.add_handler(CommandHandler("check_near_resistance", check_near_resistance_command))
    app.add_handler(CommandHandler("check_rsi_extreme", check_rsi_extreme_command))
    app.add_handler(CommandHandler("check_big_move", check_big_move_command))
    app.add_handler(CommandHandler("signal_stats", signal_stats_command))
    app.add_handler(CommandHandler("stats", signal_stats_command))
    app.add_handler(CommandHandler("shadow_stats", shadow_stats_command))
    app.add_handler(CommandHandler("weekly_winrate", weekly_winrate_summary_command))
    app.add_handler(CommandHandler("shadow_promotion_check", shadow_promotion_check_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_button_handler))

    app.add_error_handler(_error_handler)

    if app.job_queue:
        app.job_queue.run_repeating(snapshot_job, interval=60, first=5)
        logging.info("Market snapshot job scheduled (every 60s, first in 5s).")
        app.job_queue.run_repeating(
            near_support_checker,
            interval=300,
            first=10,
            name="near_support_checker",
        )
        logging.info("Near support checker job scheduled (every 300s, first in 10s).")
        app.job_queue.run_repeating(
            near_resistance_checker,
            interval=300,
            first=15,
            name="near_resistance_checker",
        )
        logging.info("Near resistance checker job scheduled (every 300s, first in 15s).")
        app.job_queue.run_repeating(
            rsi_extreme_checker,
            interval=300,
            first=20,
            name="rsi_extreme_checker",
        )
        logging.info("RSI extreme checker job scheduled (every 300s, first in 20s).")
        app.job_queue.run_repeating(
            big_move_checker,
            interval=300,
            first=25,
            name="big_move_checker",
        )
        logging.info("Big move checker job scheduled (every 300s, first in 25s).")
        app.job_queue.run_repeating(watchdog_job, interval=120, first=30)
        logging.info("AI Watchdog job scheduled (every 120s, first in 30s).")
        app.job_queue.run_repeating(
            breaking_news_job,
            interval=3600,
            first=300,
            name="breaking_news_checker",
        )
        logging.info("Breaking news job scheduled (every 3600s, first in 300s).")
        app.job_queue.run_daily(
            morning_brief_job,
            time=time(hour=1, minute=0, second=0, tzinfo=timezone.utc),
            name="morning_brief",
        )
        logging.info("Morning brief job scheduled (daily 01:00 UTC = 08:00 WIB).")
        app.job_queue.run_daily(
            weekly_winrate_summary_job,
            time=time(hour=1, minute=10, second=0, tzinfo=timezone.utc),
            days=(0,),
            name="weekly_winrate_summary",
        )
        logging.info(
            "Weekly winrate summary job scheduled (Monday 01:10 UTC = 08:10 WIB, "
            "10 minutes after morning brief to avoid dispatch overlap)."
        )
        app.job_queue.run_daily(
            evening_summary_job,
            time=time(hour=13, minute=0, second=0, tzinfo=timezone.utc),
            name="evening_summary",
        )
        logging.info("Evening summary job scheduled (daily 13:00 UTC = 20:00 WIB).")
        app.job_queue.run_repeating(
            pre_fetch_brief_data_job,
            interval=900,
            first=10,
            name="pre_fetch_brief_data",
        )
        logging.info(
            "Pre-fetch brief data job scheduled (every 900s, window 06:00–07:50 / 18:00–19:50 WIB)."
        )
        WIB_TIMES_UTC = [
            (23, 0),  # 06:00 WIB
            (5, 0),  # 12:00 WIB
            (14, 5),  # 21:00 WIB (14:05 UTC — hindari bentrok evening_calendar 14:00 UTC)
        ]
        for i, (hour, minute) in enumerate(WIB_TIMES_UTC):
            app.job_queue.run_daily(
                spot_signal_job,
                time=time(hour=hour, minute=minute, second=0, tzinfo=timezone.utc),
                name=f"spot_signal_{i}",
            )
        logging.info("Spot signal jobs scheduled (3x daily: 06/12/21 WIB).")
        app.job_queue.run_repeating(
            breakout_check_job,
            interval=300,
            first=30,
            name="breakout_checker",
        )
        logging.info("Breakout checker job scheduled (every 300s, first in 30s).")
        app.job_queue.run_repeating(
            volume_spike_job,
            interval=300,
            first=45,
            name="volume_spike_checker",
        )
        logging.info("Volume spike checker job scheduled (every 300s, first in 45s).")
        app.job_queue.run_repeating(
            funding_alert_job,
            interval=300,
            first=60,
            name="funding_alert_checker",
        )
        logging.info("Funding alert checker job scheduled (every 300s, first in 60s).")
        app.job_queue.run_repeating(
            alert_digest_flush_job,
            interval=60,
            first=65,
            name="alert_digest_flush",
        )
        logging.info("Alert digest flush job scheduled (every 60s, first in 65s).")
        app.job_queue.run_repeating(
            cfra_alert_job,
            interval=1800,
            first=300,
            name="cfra_alert",
        )
        logging.info("CFRA alert job scheduled (every 1800s).")
        app.job_queue.run_repeating(
            macro_check_job,
            interval=3600,
            first=75,
            name="macro_checker",
        )
        logging.info("Macro checker job scheduled (every 3600s, first in 75s).")
        app.job_queue.run_repeating(
            whale_alert_job,
            interval=600,
            first=120,
            name="whale_alert_checker",
        )
        logging.info("Whale alert checker job scheduled (every 600s, first in 120s).")
        app.job_queue.run_repeating(
            signal_check_job,
            interval=600,
            first=150,
            name="signal_checker",
        )
        logging.info("Signal checker job scheduled (every 600s, first in 150s).")
        app.job_queue.run_daily(
            evening_calendar_job,
            time=time(hour=14, minute=0, second=0, tzinfo=timezone.utc),
            name="evening_calendar",
        )
        logging.info("Evening calendar job scheduled (daily 14:00 UTC = 21:00 WIB).")
        # DISABLED: calendar_reminder_job — redundant with evening_calendar_job
        # Uncomment block below to re-enable "dalam 1 jam!" reminders.
        # app.job_queue.run_repeating(
        #     calendar_reminder_job,
        #     interval=1800,
        #     first=90,
        #     name="calendar_reminder",
        # )
        # logging.info("Calendar reminder job scheduled (every 1800s, first in 90s).")

    try:
        initialize_macro_seen_dates()
    except Exception as e:
        logging.warning("initialize_macro_seen_dates: %s", e)

    shutdown_controller.install_sigterm_handler()

    logging.info("AlizaAI Telegram Bot aktif (polling). Semua command terdaftar.")
    try:
        # SIGTERM is handled by GracefulShutdownController so blocking jobs cannot
        # consume the complete systemd stop window before PTB closes its clients.
        app.run_polling(stop_signals=None)
    finally:
        shutdown_controller.finish_process()


if __name__ == "__main__":
    main()
