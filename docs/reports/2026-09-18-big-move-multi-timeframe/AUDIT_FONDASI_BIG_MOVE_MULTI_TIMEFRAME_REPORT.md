# Audit Read-Only — Fondasi Big Move Alert Multi-Timeframe (15m / 30m / 1h)

Tanggal audit: 18 September 2026  
Scope: inspeksi kode dan satu verifikasi HTTP read-only ke endpoint Binance. Tidak ada file kode aplikasi yang diubah.

## 1. Implementasi `big_move_checker` saat ini

### Lokasi, pemanggilan, dan fungsi lengkap

Definisi berada di `interfaces/telegram_bot.py:6907-6977`. Scheduler mendaftarkannya dengan APScheduler JobQueue setiap 300 detik, pertama kali 25 detik setelah startup (`interfaces/telegram_bot.py:7989-7995`):

```python
app.job_queue.run_repeating(
    big_move_checker,
    interval=300,
    first=25,
    name="big_move_checker",
)
```

Fungsi lengkap yang berjalan saat ini adalah:

```python
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
```

`/check_big_move` juga membaca helper yang sama dan memakai ambang yang sama, tetapi hanya membalas command—tidak memasuki cooldown/governor maupun mengirim alert otomatis (`interfaces/telegram_bot.py:7139-7191`, khususnya `:7153-7155` dan `:7178-7188`).

### Sumber harga dan perhitungan “1 jam”

1. Checker membaca `snapshot["data"]` lewat `get_market_snapshot()` (`telegram_bot.py:6910-6911`). Helper pemilih persentasenya berada di `telegram_bot.py:6649-6661`:

   ```python
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
   ```

   Jadi prioritasnya `price_change_1h`; apabila enrichment 1h tidak tersedia, ia **jatuh ke perubahan 24 jam snapshot**. Template pesan tetap berbunyi “dalam 1 jam” (`telegram_bot.py:6958` / `:6967`) pada jalur fallback tersebut. Test regresi mengonfirmasi prioritas dan fallback ini di `tests/test_big_move_real_1h_change.py:50-56`.

2. `price_change_1h` ditambahkan saat tiap pembaruan snapshot oleh `_enrich_collected_with_binance_1h(collected)` (`engine/market/market_snapshot_engine.py:293-307`) dan dipanggil sebelum atomic swap snapshot (`:431-458`):

   ```python
   reference_close = _latest_closed_1h_close(f"{str(sym).strip().upper()}USDT")
   pct = _price_change_from_1h_close(row.get("price"), reference_close)
   if pct is not None:
       row["price_change_1h"] = pct
       row["price_change_pct_1h"] = pct
   ```

3. Referensi diperoleh dari Binance Spot `GET https://api.binance.com/api/v3/klines` dengan `symbol=<COIN>USDT`, `interval="1h"`, `limit=2` (`market_snapshot_engine.py:217-278`, request tepatnya `:244-248`). Ia memilih hanya candle dengan `close_time < now_ms` (`:260-269`), sehingga candle yang masih terbuka dikeluarkan. Hasilnya disimpan per pair sampai detik pertama setelah boundary jam UTC berikutnya (`_one_hour_cache_refresh_after`, `:212-214`; cache `:229-233`, `:273-277`). Kegagalan disimpan 300 detik, bukan diretry pada setiap snapshot (`:235-242`).

4. Rumus persisnya (`market_snapshot_engine.py:281-290`) adalah:

   ```python
   return (current / reference - 1.0) * 100.0
   ```

   `current` adalah `row["price"]`. Jalur harga utamanya berasal dari Binance Spot ticker `GET /api/v3/ticker/price?symbol=<COIN>USDT` (`engine/market/market_analyzer.py:90-109`), lalu ada fallback CoinGecko dan last-known price (`:278-310`, `:330-341`).

**Fakta semantik window:** implementasi bukan perbandingan harga saat ini terhadap harga tepat 60 menit yang lalu (rolling 60m). Ia membandingkan harga live terhadap **close candle 1h terakhir yang sudah selesai**. Karena reference hanya berganti di boundary UTC tiap jam, umur referensi bergerak dari nyaris 0 hingga nyaris 60 menit sepanjang candle 1h yang sedang berjalan. Ini persis dinyatakan di komentar kode `market_snapshot_engine.py:33-36`.

### Threshold dan penghindaran spam

- Ambangnya konstan `abs(pct) < 3.0` → skip (`telegram_bot.py:6930-6932`); maka `|pct| >= 3.0` lolos. Tidak ada pembacaan env/config threshold pada jalur ini.
- Identitas gate adalah `key = f"{coin}:{direction}"`, dengan direction hanya `up` atau `down` (`:6943-6947`). Kenaikan dan penurunan coin yang sama dipisahkan; timeframe tidak termasuk key.
- Cooldown adalah `ngov.BIG_MOVE_COOLDOWN_SEC`, default dari `BIG_MOVE_COOLDOWN_SEC` atau `7200` detik/2 jam (`engine/alerts/notification_governor.py:41-47`). State tahan restart di `data/alert_cooldown_state.json`, dengan write atomik (`:50-53`, `:59-87`).
- `is_cooldown_allowed()` membaca `cooldown:big_move` dan membandingkan elapsed time (`notification_governor.py:123-139`). Setelah lolos, checker langsung merekam cooldown (`telegram_bot.py:6973`) lalu merekam nilai (`:6974`). `is_duplicate_value()` memakai tolerance kurang dari `0.01` persen atas bucket `dedup:big_move` (`notification_governor.py:168-180`), bukan kesamaan literal seperti komentar checker menyiratkan.
- Sebelum gate itu, checker juga menolak snapshot stale melalui `ngov.is_coin_snapshot_fresh()` (`telegram_bot.py:6936-6942`); default batas umur snapshot 300 detik (`notification_governor.py:44, :213-219`).
- Checker tidak memanggil Telegram langsung. Ia menaruh event pada buffer `ngov.queue_alert()` (`telegram_bot.py:6975`; `notification_governor.py:251-253`). Job flush setiap 60 detik mengirimnya melalui `safe_dispatch()` (`telegram_bot.py:6980-7021`), dengan rate-limit global default 15 pesan/jam (`notification_governor.py:44-47, :334-346`).

## 2. Ketersediaan harga untuk 15 menit dan 30 menit

### Snapshot 60 detik: granular, tetapi tidak historis

`snapshot_job` terdaftar setiap 60 detik (`interfaces/telegram_bot.py:7965-7967`) dan mengeksekusi `update_market_snapshot()` di executor (`:7674-7679`). Setelah koleksi, snapshot engine melakukan satu **atomic replacement**:

```python
with _snapshot_lock:
    market_snapshot["data"] = collected
    market_snapshot["timestamp"] = snapshot_ts
```

(`engine/market/market_snapshot_engine.py:452-458`). `get_market_snapshot()` hanya mengembalikan deep copy dari objek terbaru tersebut (`:467-477`). Tidak ada deque/list/tabel yang menyimpan harga snapshot sebelumnya di modul ini.

Kesimpulan faktual: frekuensi 60 detik memberikan sampel harga current yang cukup rapat **hanya bila** suatu implementasi baru menambahkan retensi riwayatnya. Objek snapshot yang dibaca `big_move_checker` sekarang tidak memiliki harga 15 atau 30 menit lalu, sehingga tidak dapat menghitung dua window itu secara akurat dengan data yang sudah tersimpan saat ini.

### Verifikasi endpoint Kline Binance nyata

Pada audit ini endpoint yang sudah dipakai proyek (`BINANCE_KLINES_URL`, `market_snapshot_engine.py:31`) dipanggil read-only:

```text
GET /api/v3/klines?symbol=BTCUSDT&interval=15m&limit=2
HTTP payload: [[1789713900000, ..., "77604.00000000", ..., 1789714799999, ...],
               [1789714800000, ..., "77751.85000000", ..., 1789715699999, ...]]

GET /api/v3/klines?symbol=BTCUSDT&interval=30m&limit=2
HTTP payload: [[1789713000000, ..., "77604.00000000", ..., 1789714799999, ...],
               [1789714800000, ..., "77751.85000000", ..., 1789716599999, ...]]
```

Kedua request mengembalikan dua kline valid (array Binance berisi open time, OHLC, dan close time), jadi API Spot yang digunakan proyek memang menyediakan resolusi `15m` dan `30m`. Modul umum `_get_binance_klines(symbol_usdt, interval, limit)` juga menerima parameter interval apa adanya dan meminta endpoint yang sama (`engine/market/market_analyzer.py:131-176`), lalu menyaring candle belum close (`:112-128`).

Namun, memakai **close candle 15m/30m terakhir** dengan mekanisme yang sama seperti 1h akan menghasilkan reference yang boundary-aligned (umur 0–15 atau 0–30 menit), bukan harga rolling tepat 15/30 menit lalu. Untuk definisi window rolling yang ketat, codebase saat ini belum menyediakan referensi historis tersebut: perlu retensi sampel 60-detikan atau query candle beresolusi lebih kecil dengan reference time yang eksplisit. Ini adalah kebutuhan data tambahan, bukan perubahan yang dilakukan oleh audit.

## 3. Pola multi-timeframe dan dampak dedup bila tiga window terpenuhi

### Preseden multi-timeframe

Ada satu analyzer khusus di `engine/market/multi_timeframe_analyzer.py:29-78`:

```python
def analyze_multi_timeframe(prices_4h=None, prices_1d=None):
    # 4H: MA10 vs MA30, minimal 30 candle
    # 1D: MA20 vs MA50, minimal 50 candle
    ...
    return {
        "trend_4h": trend_4h,
        "trend_1d": trend_1d,
        "alignment": alignment,
    }
```

Ia menghitung `trend_4h` dan `trend_1d` secara terpisah, lalu menggabungkannya menjadi `STRONG_BULLISH`, `STRONG_BEARISH`, `PARTIAL`, `MIXED`, atau `UNKNOWN` (`:40-77`). `market_analyzer` mengumpulkan masing-masing seri 4h dan 1d lalu memanggilnya (`engine/market/market_analyzer.py:312-315, :353-360`). Ini adalah preseden struktur *satu fungsi dengan data per timeframe eksplisit*, bukan preseden alert yang sudah melakukan tiga pengecekan window.

Pencarian seluruh `engine/`, `interfaces/`, dan `tests/` menemukan tidak ada checker alert lain yang menjalankan 15m/30m/1h untuk kondisi yang sama. Referensi `5m` di test fase tidak merupakan job multi-window production.

### Tiga timeframe yang serentak lolos 3%

Hari ini hanya ada satu nilai `pct` per coin (`telegram_bot.py:6930`), sehingga tidak ada perilaku runtime “tiga alert” yang dapat diamati secara langsung. Tetapi dampak dari state existing dapat ditentukan dari key persisnya:

1. Jika implementasi baru memanggil jalur gate yang sama tiga kali tetapi **tetap menggunakan key saat ini** (`BTC:up`, tanpa timeframe), cek pertama yang lolos merekam cooldown 2 jam sebelum iterasi berikutnya (`telegram_bot.py:6951-6954, :6973-6974`). Dua timeframe berikutnya untuk coin dan arah sama akan ditolak oleh cooldown. Jadi hasilnya paling banyak satu event queued, bukan tiga pesan. Dalam satu coroutine ini berurutan (tidak ada `await` antara check dan record), jadi bukan race internal.
2. Dedup value juga tidak menyertakan timeframe karena disimpan dalam `dedup:big_move` dengan key yang sama (`notification_governor.py:168-180`). Dengan key existing, state tidak dapat membedakan “BTC naik 3% pada 15m” dari “BTC naik 3% pada 1h”.
3. Jika kelak key sengaja dibedakan per timeframe, tiga event dapat masuk buffer. `flush_pending()` mengirim masing-masing pesan bila total pending dalam siklus kurang dari 5; bila mencapai 5 atau lebih, ia mengirim satu digest gabungan (`notification_governor.py:288-303`). Flush job menjalankan dispatch dengan rate-limit per **pesan** (`telegram_bot.py:7012-7019`), bukan per row alert. Maka dalam kondisi hanya tiga event tersebut biasanya tiga pesan individual; bila ada event lain hingga threshold tercapai, satu digest. Ini adalah konsekuensi kondisional dari kode existing, bukan perilaku yang sudah diimplementasikan.

## Kesimpulan audit

Fondasi Binance sudah memiliki endpoint kline 15m dan 30m yang terverifikasi tersedia, serta pola analyzer yang menerima data per-timeframe. Namun, snapshot 60 detik saat ini tidak mempertahankan riwayat, dan helper 1h memakai close candle terakhir yang sudah selesai—bukan rolling window. Selain itu state big move saat ini hanya mengidentifikasi `(coin, arah)`, tidak ada dimensi timeframe. Fakta-fakta tersebut perlu dijadikan constraint eksplisit pada prompt build berikutnya.
