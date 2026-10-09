# Audit Read-Only: Fondasi Alert Perubahan Status Konteks Market

Tanggal audit: 18 September 2026  
Ruang lingkup: pembacaan source saja. Tidak ada file aplikasi, konfigurasi layanan, database, atau scheduler yang diubah. Satu-satunya artefak audit ini adalah laporan ini.

## 1. Scheduler yang sudah ada

Pencarian lintas seluruh source Python untuk `run_repeating`, `run_daily`, `AsyncIOScheduler`, `BackgroundScheduler`, `add_job(`, dan `schedule.` hanya menemukan pendaftaran aktif di `interfaces/telegram_bot.py:7872-8016`. Scheduler yang dipakai adalah `app.job_queue` (Python Telegram Bot); tidak ada pendaftaran scheduler kedua di source yang diaudit.

Pendaftaran dimulai dengan guard berikut (`interfaces/telegram_bot.py:7870-7874`):

```python
app.add_error_handler(_error_handler)

if app.job_queue:
    app.job_queue.run_repeating(snapshot_job, interval=60, first=5)
    logging.info("Market snapshot job scheduled (every 60s, first in 5s).")
```

### Daftar seluruh job aktif yang terdaftar

| Fungsi/job | Jadwal aktif | Bukti pendaftaran |
|---|---:|---|
| `snapshot_job` | setiap 60 detik; pertama +5 dtk | `interfaces/telegram_bot.py:7873` |
| `near_support_checker` | setiap 300 detik; +10 dtk | `:7875-7880` |
| `near_resistance_checker` | setiap 300 detik; +15 dtk | `:7882-7887` |
| `rsi_extreme_checker` | setiap 300 detik; +20 dtk | `:7889-7894` |
| `big_move_checker` | setiap 300 detik; +25 dtk | `:7896-7901` |
| `watchdog_job` | setiap 120 detik; +30 dtk | `:7903` |
| `breaking_news_job` | setiap 3.600 detik / 1 jam; +300 dtk | `:7905-7910` |
| `morning_brief_job` | harian 01:00 UTC = 08:00 WIB | `:7912-7917` |
| `weekly_winrate_summary_job` | Senin 01:10 UTC = 08:10 WIB | `:7918-7926` |
| `evening_summary_job` | harian 13:00 UTC = 20:00 WIB | `:7928-7933` |
| `pre_fetch_brief_data_job` | setiap 900 detik; +10 dtk | `:7934-7942` |
| `spot_signal_job` (`spot_signal_0..2`) | harian 06:00, 12:00, 21:00 WIB | `:7943-7954` |
| `breakout_check_job` | setiap 300 detik; +30 dtk | `:7955-7960` |
| `volume_spike_job` | setiap 300 detik; +45 dtk | `:7962-7967` |
| `funding_alert_job` | setiap 300 detik; +60 dtk | `:7969-7974` |
| `alert_digest_flush_job` | setiap 60 detik; +65 dtk | `:7976-7981` |
| `cfra_alert_job` | setiap 1.800 detik / 30 menit; +300 dtk | `:7983-7988` |
| `macro_check_job` | setiap 3.600 detik / 1 jam; +75 dtk | `:7990-7995` |
| `whale_alert_job` | setiap 600 detik / 10 menit; +120 dtk | `:7997-8002` |
| `signal_check_job` | setiap 600 detik / 10 menit; +150 dtk | `:8004-8009` |
| `evening_calendar_job` | harian 14:00 UTC = 21:00 WIB | `:8011-8016` |

`calendar_reminder_job` bukan job aktif: blok pendaftarannya dikomentari sebagai disabled di `interfaces/telegram_bot.py:8017-8025`.

Interval aktif tersempit adalah **60 detik (1 menit)**, dipakai oleh `snapshot_job` dan `alert_digest_flush_job` (`telegram_bot.py:7873`, `7976-7981`). Ini fakta konsistensi scheduler, bukan rekomendasi bahwa `calculate_market_score()` harus dipanggil tiap menit: fungsi tersebut sendiri melakukan akses global market, funding, macro, dan sinyal (lihat bagian 2).

### Bentuk job dan pola pengiriman

Job Telegram berbentuk coroutine `async def ..._job(context: ContextTypes.DEFAULT_TYPE)`, misalnya `morning_brief_job` (`telegram_bot.py:5572`) dan `alert_digest_flush_job` (`:6887`). Pengiriman otomatis umumnya memakai `await safe_dispatch(...)`; wrapper ini serialisasi maksimal lima pengiriman lalu memanggil dispatcher pusat:

```python
# interfaces/telegram_bot.py:369-406
async def dispatch_alert_message(message: str, chat_id: int | str | None = None, force: bool = False) -> bool:
    if not IS_PRIMARY_DISPATCHER:
        return False
    with snapshot_state._snapshot_lock:
        cb_active = snapshot_state.CIRCUIT_BREAKER_ACTIVE
    if cb_active and not force:
        return False
    bot = get_bot()
    target_chat_id = chat_id or DEFAULT_CHAT_ID
    if not target_chat_id:
        raise RuntimeError("CHAT_ID NOT SET")
    parts = _split_message_for_telegram(message)
    for part in parts:
        await bot.send_message(chat_id=target_chat_id, text=part)
    return True

async def safe_dispatch(message: str, chat_id: int | str | None = None, force: bool = False) -> bool:
    async with _dispatch_semaphore:
        return await dispatch_alert_message(message, chat_id, force=force)
```

`dispatch_alert_message()` selalu memecah pesan melalui `_split_message_for_telegram()` (`:391`). Fungsi pemecah (`:322-366`) mengukur UTF-16, memilih batas paragraf/baris/kata, dan menambahkan suffix `[lanjutan i/n]` bila diperlukan.

Untuk alert yang berisik, checker tidak selalu mengirim langsung. `alert_digest_flush_job` mengumpulkan buffer governor dan hanya melakukan dispatch jika ada `messages` atau `summary` (`telegram_bot.py:6907-6922`):

```python
summary = ngov.pop_previous_hour_summary(now)
messages = ngov.flush_pending()
if not messages and not summary:
    return
...
for msg in messages:
    if ngov.allow_rate_limited_dispatch(now):
        await safe_dispatch(msg, chat_id=chat_id, force=False)
```

### Preseden “kirim hanya saat berubah”

Ada preseden yang tepat: `_notify_drawdown_breaker_transition()` di `interfaces/telegram_bot.py:7447-7469`. Fungsi ini dijalankan setiap siklus `snapshot_job` (`:7665-7671`) tetapi berhenti tanpa mengirim bila kondisi sama; state terakhir persisten melalui `notification_governor`.

```python
# interfaces/telegram_bot.py:7460-7467
active_now = not dd.get("trading_allowed", True)
was_active = bool(ngov.get_value("drawdown_breaker", "active", False))
if active_now == was_active:
    return
ngov.set_value("drawdown_breaker", "active", active_now)
msg = DRAWDOWN_BREAKER_ACTIVATED_MSG if active_now else DRAWDOWN_BREAKER_RESET_MSG
await safe_dispatch(msg, chat_id=chat_id, force=True)
```

`spot_signal_job` juga memiliki deduplikasi konten persisten, meski bukan transition status: ia tidak mengirim teks identik dalam kurang dari 7.200 detik (`telegram_bot.py:5941-5963`).

```python
last = ngov.get_value("spot_signal", "last_sent") or {}
if last_text == spot_section and last_ts is not None and (now_ts - float(last_ts)) < 7200:
    return
ngov.set_value("spot_signal", "last_sent", {"text": spot_section, "ts": now_ts})
await safe_dispatch(msg, chat_id=chat_id, force=False)
```

## 2. Nilai status Konteks Market yang persis dipakai

Sumber otoritatif label adalah `_label_for_score()` di `engine/market/market_context_engine.py:31-40`, bukan string formatter Telegram. Nilai internal disimpan sebagai string pada key hasil `label` (`:180-188`); tidak ada enum terpisah.

```python
def _label_for_score(score: int) -> tuple[str, str, str]:
    if score <= 30:
        return ("Bearish", "🔴", ...)
    if score <= 45:
        return ("Weak", "🟠", ...)
    if score <= 55:
        return ("Neutral", "⚪", ...)
    if score <= 70:
        return ("Bullish", "🟢", ...)
    return ("Strong Bullish", "💚", ...)

# calculate_market_score(), :180-188
label, emoji, summary = _label_for_score(total_score)
return {"total_score": total_score, "label": label, "emoji": emoji,
        "components": components, "summary": summary, "timestamp": now_wib}
```

| Rentang total skor inklusif | `label` internal persis | Emoji |
|---:|---|---|
| 0–30 | `Bearish` | `🔴` |
| 31–45 | `Weak` | `🟠` |
| 46–55 | `Neutral` | `⚪` |
| 56–70 | `Bullish` | `🟢` |
| 71–100 | `Strong Bullish` | `💚` |

Konsekuensinya, permintaan alert tiga status Bullish/Netral/Bearish belum cocok satu-banding-satu dengan domain saat ini: ada lima label, khususnya `Weak` dan `Strong Bullish`. Build berikutnya perlu menyatakan eksplisit apakah `Weak` digabung ke Bearish dan `Strong Bullish` ke Bullish, atau apakah keduanya merupakan transition yang berbeda. Jangan menyamakan `Weak` dengan `Neutral` hanya dari emoji.

`format_context_for_brief()` memiliki pengelompokan tampilan lain (`market_context_engine.py:192-207`): `Trending Bullish` pada skor >=70, `Neutral-Bullish` >=55, `Ranging` >=45, `Neutral-Bearish` >=30, dan `Risk-Off` di bawahnya. Nilai `regime` ini adalah tampilan Morning Brief; ia bukan field `label` yang dikembalikan oleh `calculate_market_score()`.

Kalkulasi memakai lima komponen (`market_context_engine.py:54-178`): Fear & Greed, BTC dominance, funding rate, macro, dan technical signal. Secara konkret ia memanggil `get_global_market_data()` pada `:63` dan `:85`, `get_all_funding_data()` pada `:103`, `get_macro_data()` untuk CPI/FED pada `:129-130`, dan `scan_for_signals()` pada `:157`. Jika kelima komponen gagal, skor dipaksa menjadi 50 (`:175-178`), yang lalu berlabel `Neutral`.

## 3. Persistensi status terakhir lintas restart

### Pola yang sudah persisten

Pola paling dekat adalah `engine/alerts/notification_governor.py`. Ia sudah menyediakan K/V namespaced di `data/alert_cooldown_state.json` (`:41-53`), memuatnya saat proses mulai (`:59-77`), dan menulis atomically via berkas sementara + `os.replace` (`:80-87`).

```python
# engine/alerts/notification_governor.py:41-42, 59-87, 104-111
STATE_FILE = os.path.join(_ROOT, "data", "alert_cooldown_state.json")

def get_value(namespace: str, key: str, default: Any = None) -> Any:
    return _load_state().get(namespace, {}).get(key, default)

def set_value(namespace: str, key: str, value: Any) -> None:
    state = _load_state()
    state.setdefault(namespace, {})[key] = value
    _save_state()

def _save_state() -> None:
    tmp_path = f"{STATE_FILE}.tmp"
    with open(tmp_path, "w") as f:
        json.dump(_state_cache, f)
    os.replace(tmp_path, STATE_FILE)
```

Itulah mekanisme yang dipakai langsung oleh transition drawdown pada bagian 1 dan oleh dedup `spot_signal`; karena itu bukti bahwa state ini bertahan restart, bukan sekadar cache memori.

Ada juga state JSON terpisah untuk sinyal: `engine/state_store.py:4-18` menggunakan `data/signal_state.json` lewat `load_state()` / `save_state()`. Database SQLite yang nyata juga ada di `data/aliza.db`: `engine/trading/signal_tracker.py:15, 49-105` membuka `DB_PATH` itu dan membuat tabel `signal_tracking` untuk statistik sinyal. Tabel tersebut memiliki data trade/signal (`coin`, `side`, `status`, `market_score`, dll.), bukan state notifikasi market-context.

Sebaliknya, cooldown/suspensi universe memang in-memory. `engine/market/market_universe.py:32-34` mendefinisikan `_coin_failure_counts` dan `_coin_suspended_until` sebagai dict modul; `reset_coverage_gate()` membersihkannya (`:66-70`). Ini bukan preseden yang sesuai untuk alert yang harus ingat status setelah restart.

### Rekomendasi singkat

Untuk satu nilai status-terakhir, gunakan `notification_governor` yang ada dengan namespace/key baru, bukan tabel SQLite baru dan bukan file JSON baru. Alasannya: pola transition yang identik sudah memakai `ngov.get_value()`/`set_value()`, berkasnya sudah atomik dan restart-safe, serta tidak mencampur state notifikasi dengan tabel `signal_tracking`. Keputusan semantik yang tetap diperlukan saat build adalah bagaimana bootstrap awal diperlakukan (simpan baseline tanpa alert atau kirim alert pertama) dan pemetaan lima `label` ke tiga status produk.

## 4. Trend per-coin dari Radar

### Bentuk `trend_alignment`

`generate_radar_pro()` di `engine/market/market_radar_pro_analyzer.py:48-144` **tidak menghitung ulang** alignment. Ia mengambil snapshot sekali, mengiterasi `snapshot["data"]`, lalu meneruskan value field itu; jika absent/falsy, fallback-nya persis `"UNKNOWN"`.

```python
# engine/market/market_radar_pro_analyzer.py:57-69, 134-142
snapshot = get_market_snapshot()
markets = snapshot.get("data") or {}
...
for coin, data in markets.items():
    if not data or data.get("error"):
        continue
    trend = data.get("trend") or "SIDEWAYS"
    alignment = data.get("trend_alignment") or "UNKNOWN"
    ...
    radar_data.append({
        "coin": coin,
        "trend": trend,
        "trend_alignment": alignment,
        "label": label,
        "crash_risk": crash_risk_flag,
    })
return radar_data
```

Produsen alignment normalnya adalah `analyze_multi_timeframe()` di `engine/market/multi_timeframe_analyzer.py:29-77`. Nilai yang ia hasilkan adalah persis:

| Kondisi 4h/1d | `alignment` persis |
|---|---|
| salah satu data tidak cukup | `UNKNOWN` |
| keduanya `BULLISH` | `STRONG_BULLISH` |
| keduanya `BEARISH` | `STRONG_BEARISH` |
| salah satu BULLISH/BEARISH, lainnya SIDEWAYS | `PARTIAL` |
| kombinasi lain | `MIXED` |

```python
# engine/market/multi_timeframe_analyzer.py:58-77
if trend_4h == "UNKNOWN" or trend_1d == "UNKNOWN":
    alignment = "UNKNOWN"
elif trend_4h == "BULLISH" and trend_1d == "BULLISH":
    alignment = "STRONG_BULLISH"
elif trend_4h == "BEARISH" and trend_1d == "BEARISH":
    alignment = "STRONG_BEARISH"
elif ...:
    alignment = "PARTIAL"
else:
    alignment = "MIXED"
```

Jadi `BULLISH` dan `BEARISH` polos bukan output normal fungsi multi-timeframe saat ini. Formatter `/radar` memang dapat menampilkannya (`interfaces/telegram_bot.py:1605-1617`), tetapi `generate_radar_pro()` meneruskan apa pun yang ada di snapshot tanpa validasi. Untuk filter “searah status baru”, nilai yang secara jelas searah dari produsen saat ini adalah `STRONG_BULLISH` dan `STRONG_BEARISH`; perlakuan `PARTIAL`, `MIXED`, dan `UNKNOWN` harus diputuskan di desain.

### Daftar 21 coin

Watchlist fixed didefinisikan sebagai `CORE_COINS` di `engine/market/market_universe.py:14-28`:

```python
CORE_COINS = [
    "BTC", "ETH", "BNB", "SOL", "XRP",
    "ADA", "SUI", "ARB", "PEPE", "JTO",
    "ETHFI", "WLD", "OM", "ASTER", "XPL",
    "TAO", "BONE", "FARTCOIN", "HYPE", "ZEREBRO",
    "XAUT",
]
TRADABLE_COINS = list(CORE_COINS)
MAJOR_COINS = list(CORE_COINS)
```

Walau `dynamic_universe.py` masih memiliki kode scan lama, fungsi aktifnya mengembalikan fixed list: `engine/market/dynamic_universe.py:276-278`:

```python
def get_tradable_coins():
    """Return fixed custom watchlist. Auto-scan disabled."""
    return list(CORE_COINS)
```

Snapshot mengambil list ini melalui `get_tradable_coins_fallback()` lalu melewatkannya ke `get_polling_coins()` (`engine/market/market_snapshot_engine.py:79-87`). `get_polling_coins()` dapat mengecualikan coin dari `UNIVERSE_EXCLUDE` atau yang sedang suspended in-memory (`market_universe.py:98-117`). Karenanya hasil radar dapat berisi kurang dari 21 coin ketika suatu coin tidak dipoll atau data-nya error; `generate_radar_pro()` juga skip `data.get("error")`.

### Satu panggilan atau per coin

Untuk mendapatkan `trend_alignment` semua coin yang tersedia, cukup **satu panggilan** `generate_radar_pro()`. Fungsi itu memanggil `get_market_snapshot()` sekali (`market_radar_pro_analyzer.py:57`) dan mengiterasi semua `markets.items()` (`:64`); tidak ada API call per coin di fungsi tersebut.

Snapshot sendiri dibangun per cycle oleh `update_market_snapshot()` (`market_snapshot_engine.py:331-430`). Ia mengambil radar global sekali (`:348-356`) dan kemudian iterasi `for symbol in coins` (`:388`) untuk mengumpulkan data. Artinya job alert baru dapat membaca snapshot/radar yang sudah ada; tidak perlu memanggil `generate_radar_pro()` 21 kali.

## 5. Pengiriman Telegram dari job otomatis

Tujuan chat tidak bergantung pada `update`/`context` command handler. Nilai fallback konfigurasi didefinisikan dari environment pada `interfaces/telegram_bot.py:207-211`:

```python
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
IS_PRIMARY_DISPATCHER = os.getenv("IS_PRIMARY_DISPATCHER", "true").strip().lower() == "true"
DEFAULT_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
_bot_instance = None
_dispatch_semaphore = asyncio.Semaphore(5)
```

Morning Brief adalah contoh paling lengkap (`interfaces/telegram_bot.py:5572-5584, 5682-5701`). Job mengambil `context.bot_data["chat_id"]` bila sudah tersedia (misalnya telah diset alur bot), fallback ke `DEFAULT_CHAT_ID`, dan berhenti bila dua-duanya tidak ada. Lalu ia mengirim melalui `safe_dispatch`, tanpa `Update`.

```python
async def morning_brief_job(context: ContextTypes.DEFAULT_TYPE):
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
    ...
    await safe_dispatch(brief_header, chat_id=chat_id, force=True)
    ...
    await safe_dispatch(str(analysis).strip(), chat_id=chat_id, force=True)
```

`evening_summary_job` memakai pola resolusi `chat_id` yang sama di `interfaces/telegram_bot.py:5717-5729`, sedangkan `alert_digest_flush_job` melakukan pola yang sama di `:6900-6914` dan mengirim via `safe_dispatch` di `:6916-6922`.

Jalur akhir tetap dispatcher pusat di `telegram_bot.py:369-401`: ia menolak instance non-primary, menghormati circuit breaker kecuali `force=True`, mengambil bot dengan `get_bot()`, menggunakan `chat_id` eksplisit atau `DEFAULT_CHAT_ID`, melakukan split, lalu memanggil `bot.send_message`. Maka job alert konteks dapat mengikuti pola job async ini: resolve `chat_id` seperti Morning Brief/digest, lalu `safe_dispatch`; ia tidak memerlukan command handler atau objek `update`.

## Kesimpulan audit yang relevan untuk prompt build berikutnya

Fondasi yang sudah tersedia adalah: JobQueue dengan interval minimum 60 detik; snapshot yang sudah memegang radar seluruh watchlist; `generate_radar_pro()` yang menghasilkan list seluruh coin dalam satu panggilan; dan `notification_governor` restart-safe dengan preseden transition-only yang sangat dekat. Dua keputusan produk yang belum diwakili oleh source adalah pemetaan lima label mesin menjadi tiga status alert dan kriteria coin “searah” untuk `PARTIAL`/`MIXED`/`UNKNOWN`.
