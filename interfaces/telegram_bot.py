import os
import sys
import atexit
import logging
from datetime import datetime
from dotenv import load_dotenv

# =========================
# FIX PYTHON PATH
# =========================

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# =========================
# ENGINE IMPORT
# =========================

from engine.market.market_analyzer import market_signal, multi_market_scan
from engine.market.market_report_formatter import format_market_report
from engine.trading.opportunity_scanner import opportunity_report
from engine.trading.trade_manager import init_trade_db, create_trade, get_active_trades, close_trade
from engine.trading.signal_engine import (
    scan_for_signals,
    format_signal_message,
    can_send_signal,
    record_signal_sent,
)
from engine.utils.market_cache import get_market_data
from engine.market.market_universe import MAJOR_COINS
from engine.brain.ai_trade_guardian import analyze_trades
from engine.detectors.crash_detector import detect_market_crash
from engine.detectors.whale_tracker import detect_whale_activity
from engine.detectors.whale_signal_engine import scan_whale_signals, format_whale_alert
from engine.detectors.altseason_detector import detect_altseason
from engine.intelligence.market_intelligence import scan_market_intelligence
from engine.intelligence.market_radar_pro import calculate_market_probabilities, format_radar_report
from engine.intelligence.predictive_market_ai import calculate_market_predictions, format_prediction_report
from engine.intelligence.quant_market_model import calculate_market_score, format_quant_report

# =========================
# TELEGRAM
# =========================

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# =========================
# ENV
# =========================

load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN tidak ditemukan")

# =========================
# LOGGING
# =========================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# =========================
# SINGLE INSTANCE LOCK (PID FILE)
# =========================

def _lock_file_path():
    base = os.getcwd()
    return os.path.join(base, "data", "telegram_bot.lock")

_lock_file_handle = None

def _release_lock():
    global _lock_file_handle
    path = _lock_file_path()
    if _lock_file_handle is not None:
        try:
            _lock_file_handle.close()
        except Exception:
            pass
        _lock_file_handle = None
    try:
        if os.path.exists(path):
            os.remove(path)
            logging.info("Lock file dilepas.")
    except Exception as e:
        logging.warning("Gagal menghapus lock file: %s", e)

def acquire_single_instance_lock():
    """
    Hanya satu instance bot yang boleh jalan.
    Menggunakan PID file. Return True jika berhasil, False jika instance lain aktif.
    """
    path = _lock_file_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)

    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                old_pid = int(f.read().strip())
        except (ValueError, OSError):
            try:
                os.remove(path)
            except Exception:
                pass
        else:
            # Cek apakah proses dengan PID tersebut masih jalan
            try:
                os.kill(old_pid, 0)
                logging.warning(
                    "Bot sudah berjalan (PID %s). Hanya satu instance yang diizinkan.",
                    old_pid
                )
                return False
            except (ProcessLookupError, OSError, ValueError):
                # Proses sudah tidak ada (stale lock) atau OS tidak dukung signal 0
                pass
            try:
                os.remove(path)
            except Exception:
                pass

    try:
        global _lock_file_handle
        _lock_file_handle = open(path, "w")
        _lock_file_handle.write(str(os.getpid()))
        _lock_file_handle.flush()
        atexit.register(_release_lock)
        logging.info("Lock diperoleh (PID %s). Satu instance bot aktif.", os.getpid())
        return True
    except OSError as e:
        logging.error("Tidak dapat membuat lock file: %s", e)
        return False

# =========================
# BACKGROUND JOBS
# =========================

async def trade_guardian_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        alerts = analyze_trades()

        if not alerts:
            return

        chat_id = context.bot_data.get("chat_id")

        if not chat_id:
            return

        for alert in alerts:
            await context.bot.send_message(chat_id=chat_id, text=alert)

    except Exception as e:
        logging.error(f"TRADE GUARDIAN ERROR: {e}")


async def crash_detector_job(context: ContextTypes.DEFAULT_TYPE):

    try:
        alerts = detect_market_crash()

        if not alerts:
            return

        chat_id = context.bot_data.get("chat_id")

        if not chat_id:
            return

        for alert in alerts:
            await context.bot.send_message(chat_id=chat_id, text=alert)

    except Exception as e:
        logging.error(f"CRASH DETECTOR ERROR: {e}")


async def whale_tracker_job(context: ContextTypes.DEFAULT_TYPE):

    try:
        alerts = detect_whale_activity()

        if not alerts:
            return

        chat_id = context.bot_data.get("chat_id")

        if not chat_id:
            return

        for alert in alerts:
            await context.bot.send_message(chat_id=chat_id, text=alert)

    except Exception as e:
        logging.error(f"WHALE TRACKER ERROR: {e}")


async def altseason_detector_job(context: ContextTypes.DEFAULT_TYPE):

    try:
        alerts = detect_altseason()

        if not alerts:
            return

        chat_id = context.bot_data.get("chat_id")

        if not chat_id:
            return

        for alert in alerts:
            await context.bot.send_message(chat_id=chat_id, text=alert)

    except Exception as e:
        logging.error(f"ALTSEASON DETECTOR ERROR: {e}")


async def signal_engine_job(context: ContextTypes.DEFAULT_TYPE):

    try:

        signal = scan_for_signals()

        if not signal:
            return

        if not can_send_signal(signal):
            return

        chat_id = context.bot_data.get("chat_id")

        if not chat_id:
            return

        message = format_signal_message(signal)

        await context.bot.send_message(
            chat_id=chat_id,
            text=message
        )

        record_signal_sent(signal)

    except Exception as e:
        logging.error(f"SIGNAL ENGINE ERROR: {e}")


async def whale_signal_job(context: ContextTypes.DEFAULT_TYPE):

    try:

        alerts = scan_whale_signals()

        if not alerts:
            return

        chat_id = context.bot_data.get("chat_id")

        if not chat_id:
            return

        for alert in alerts:

            message = format_whale_alert(alert)

            await context.bot.send_message(
                chat_id=chat_id,
                text=message
            )

    except Exception as e:
        logging.error(f"WHALE SIGNAL JOB ERROR: {e}")


async def market_intelligence_job(context: ContextTypes.DEFAULT_TYPE):

    try:

        alerts = scan_market_intelligence()

        if not alerts:
            return

        chat_id = context.bot_data.get("chat_id")

        if not chat_id:
            return

        for alert in alerts:

            await context.bot.send_message(
                chat_id=chat_id,
                text=alert
            )

    except Exception as e:
        logging.error(f"MARKET INTELLIGENCE JOB ERROR: {e}")


# =========================
# COMMANDS
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.bot_data["chat_id"] = update.effective_chat.id

    message = (
        "🤖 ALIZA AI TRADING ASSISTANT\n\n"
        "Auto market monitoring aktif.\n\n"

        "━━━━━━━━━━━━━━━━━━\n"
        "📊 MARKET\n"
        "/market BTC\n"
        "/radar\n\n"

        "━━━━━━━━━━━━━━━━━━\n"
        "🎯 TRADING\n"
        "/setfutures\n"
        "/entry BTC\n"
        "/close BTC\n"
        "/portfolio\n\n"

        "━━━━━━━━━━━━━━━━━━\n"
        "⚙️ SYSTEM\n"
        "/status\n"
        "/testalert\n"
        "/marketdebug"
    )

    await update.message.reply_text(message)


async def market(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:

        coin = "BTC"

        if context.args:
            coin = context.args[0].upper()

        if coin not in MAJOR_COINS:
            await update.message.reply_text("Coin tidak tersedia.")
            return

        data = get_market_data(coin)

        if not data or "error" in data:
            data = market_signal(coin)

        if not data or "error" in data:
            await update.message.reply_text("Market data tidak tersedia.")
            return

        message = format_market_report(data)

        await update.message.reply_text(message)

    except Exception as e:

        logging.error(f"MARKET ERROR: {e}")
        await update.message.reply_text("Terjadi kesalahan membaca market.")


async def radar(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:

        data = multi_market_scan()

        if not data:
            await update.message.reply_text("Radar market tidak tersedia.")
            return

        message = "📡 ALIZA MARKET RADAR\n\n"

        for coin, trend in data.items():
            message += f"{coin} → {trend}\n"

        await update.message.reply_text(message)

    except Exception as e:

        logging.error(f"RADAR ERROR: {e}")
        await update.message.reply_text("Terjadi kesalahan scan market.")


async def radarpro(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:

        data = calculate_market_probabilities()
        message = format_radar_report(data)
        await update.message.reply_text(message)

    except Exception as e:
        logging.error(f"RADARPRO ERROR: {e}")
        await update.message.reply_text("Terjadi kesalahan memuat radar pro.")


async def predict(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:

        data = calculate_market_predictions()
        message = format_prediction_report(data)
        await update.message.reply_text(message)

    except Exception as e:
        logging.error(f"PREDICT ERROR: {e}")
        await update.message.reply_text("Terjadi kesalahan memuat prediksi market.")


async def quant(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:

        data = calculate_market_score()
        message = format_quant_report(data)
        await update.message.reply_text(message)

    except Exception as e:
        logging.error(f"QUANT ERROR: {e}")
        await update.message.reply_text("Terjadi kesalahan memuat quant model.")


async def setfutures(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:

        message = opportunity_report()

        if not message:
            message = "Tidak ada setup trading."

        await update.message.reply_text(message)

    except Exception as e:

        logging.error(f"FUTURES ERROR: {e}")
        await update.message.reply_text("Terjadi kesalahan futures scanner.")

# =========================
# TRADE COMMANDS
# =========================

async def entry(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:

        if not context.args:
            await update.message.reply_text("Gunakan format:\n/entry BNB")
            return

        coin = context.args[0].upper()

        if coin not in MAJOR_COINS:
            await update.message.reply_text("Coin tidak tersedia.")
            return

        data = get_market_data(coin)

        if not data or "error" in data:
            await update.message.reply_text("Data market tidak tersedia.")
            return

        trade_setup = data.get("trade_setup")

        if not trade_setup:
            await update.message.reply_text("Tidak ada setup trading saat ini.")
            return

        setup = trade_setup.get("setup")
        if not setup or setup in ("NO SETUP", "NO DATA"):
            await update.message.reply_text("Tidak ada setup trading saat ini.")
            return

        entry_price = trade_setup.get("entry")
        sl = trade_setup.get("sl")
        tp1 = trade_setup.get("tp1")
        tp2 = trade_setup.get("tp2")

        if entry_price is None:
            await update.message.reply_text("Tidak ada setup trading saat ini.")
            return

        create_trade(coin, setup, entry_price, sl, tp1, tp2)

        message = (
            "📥 POSISI DIBUKA\n\n"
            f"Coin : {coin}\n"
            f"Setup : {setup}\n\n"
            f"Entry : {entry_price}\n"
            f"SL : {sl}\n"
            f"TP1 : {tp1}\n"
            f"TP2 : {tp2}\n\n"
            "Aliza akan memantau posisi ini."
        )
        await update.message.reply_text(message)

    except Exception as e:
        logging.error(f"ENTRY ERROR: {e}")
        await update.message.reply_text("Terjadi kesalahan saat membuka posisi.")


async def close(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:

        if not context.args:
            await update.message.reply_text("Gunakan format:\n/close BNB")
            return

        coin = context.args[0].upper()

        closed = close_trade(coin)

        if closed:
            await update.message.reply_text(
                f"📤 POSISI DITUTUP\n\n{coin} telah ditutup."
            )
        else:
            await update.message.reply_text(
                f"Tidak ada posisi terbuka untuk {coin}."
            )

    except Exception as e:
        logging.error(f"CLOSE ERROR: {e}")
        await update.message.reply_text("Terjadi kesalahan saat menutup posisi.")


async def portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:

        trades = get_active_trades()

        if not trades:
            await update.message.reply_text("Belum ada posisi aktif.")
            return

        message = "💼 PORTFOLIO AKTIF\n\n"

        for trade in trades:

            coin = trade[0]
            entry = trade[2]
            sl = trade[3]
            tp1 = trade[4]
            tp2 = trade[5]

            message += f"{coin}\n"
            message += f"Entry : {entry}\n"
            message += f"SL : {sl}\n"
            message += f"TP1 : {tp1}\n"
            if tp2 is not None:
                message += f"TP2 : {tp2}\n"
            message += "\n"

        await update.message.reply_text(message.strip())

    except Exception as e:
        logging.error(f"PORTFOLIO ERROR: {e}")
        await update.message.reply_text("Terjadi kesalahan memuat portfolio.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:

        trades = get_active_trades()
        active_count = len(trades)
        coins_count = len(MAJOR_COINS)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        message = (
            "⚙️ ALIZA SYSTEM STATUS\n\n"
            "Engine            : AKTIF\n"
            "Market Cache      : AKTIF\n"
            "Trade Monitor     : AKTIF\n"
            "Telegram Bot      : AKTIF\n\n"
            f"Active Trades     : {active_count}\n"
            f"Coins Dipantau    : {coins_count}\n\n"
            f"Server Time       : {now}"
        )
        await update.message.reply_text(message)

    except Exception as e:
        logging.error("STATUS ERROR: %s", e)
        await update.message.reply_text("Gagal memuat status sistem.")


async def testalert(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        message = (
            "🚨 TEST ALERT ALIZA\n\n"
            "Ini adalah simulasi alert sistem.\n\n"
            "Jika Anda melihat pesan ini,\n"
            "berarti sistem notifikasi Telegram bekerja dengan baik.\n\n"
            f"Server Time: {now}"
        )
        await update.message.reply_text(message)

    except Exception as e:
        logging.error("TESTALERT ERROR: %s", e)
        await update.message.reply_text("Gagal mengirim test alert.")


async def marketdebug(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:

        data = market_signal("BTC")

        if not data or "error" in data:
            await update.message.reply_text("Market debug gagal.")
            return

        price = data.get("price")
        trend = data.get("trend")
        rsi = data.get("rsi")
        support = data.get("support")
        resistance = data.get("resistance")
        fear_greed = data.get("fear_greed")
        dominance = data.get("dominance")

        trade_setup = data.get("trade_setup") or {}
        setup = trade_setup.get("setup")
        entry = trade_setup.get("entry")
        sl = trade_setup.get("sl")
        tp1 = trade_setup.get("tp1")
        tp2 = trade_setup.get("tp2")
        rr = trade_setup.get("risk_reward")

        def _fmt(v):
            if v is None:
                return "—"
            if isinstance(v, float):
                return round(v, 2) if v == v else "—"
            return str(v)

        message = (
            "🔎 MARKET DEBUG\n\n"
            f"Symbol      : {data.get('symbol', 'BTC')}\n"
            f"Price       : {_fmt(price)}\n"
            f"Trend       : {_fmt(trend)}\n"
            f"RSI         : {_fmt(rsi)}\n\n"
            f"Support     : {_fmt(support)}\n"
            f"Resistance  : {_fmt(resistance)}\n\n"
            f"Fear Greed  : {_fmt(fear_greed)}\n"
            f"Dominance   : {_fmt(dominance)}\n\n"
            f"Setup       : {_fmt(setup)}\n"
            f"Entry       : {_fmt(entry)}\n"
            f"SL          : {_fmt(sl)}\n"
            f"TP1         : {_fmt(tp1)}\n"
            f"TP2         : {_fmt(tp2)}\n"
            f"RR          : {_fmt(rr)}"
        )
        await update.message.reply_text(message)

    except Exception as e:
        logging.error("MARKETDEBUG ERROR: %s", e)
        await update.message.reply_text("Market debug gagal.")

# =========================
# MAIN
# =========================

def main():

    if not acquire_single_instance_lock():
        logging.error("Keluar. Hentikan instance bot yang sudah berjalan sebelum menjalankan lagi.")
        sys.exit(1)

    init_trade_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(CommandHandler("market", market))
    app.add_handler(CommandHandler("radar", radar))
    app.add_handler(CommandHandler("radarpro", radarpro))
    app.add_handler(CommandHandler("predict", predict))
    app.add_handler(CommandHandler("quant", quant))

    app.add_handler(CommandHandler("setfutures", setfutures))

    app.add_handler(CommandHandler("entry", entry))
    app.add_handler(CommandHandler("close", close))
    app.add_handler(CommandHandler("portfolio", portfolio))

    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("testalert", testalert))
    app.add_handler(CommandHandler("marketdebug", marketdebug))

    job_queue = app.job_queue

    job_queue.run_repeating(trade_guardian_job, interval=60, first=30)
    job_queue.run_repeating(crash_detector_job, interval=180, first=60)
    job_queue.run_repeating(whale_tracker_job, interval=180, first=90)
    job_queue.run_repeating(altseason_detector_job, interval=300, first=120)
    job_queue.run_repeating(signal_engine_job, interval=300, first=120)
    job_queue.run_repeating(whale_signal_job, interval=600, first=180)
    job_queue.run_repeating(market_intelligence_job, interval=900, first=300)

    logging.info("AlizaAI Telegram Bot aktif...")

    app.run_polling()

if __name__ == "__main__":
    main()