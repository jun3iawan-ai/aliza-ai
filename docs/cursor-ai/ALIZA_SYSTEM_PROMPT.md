# ALIZA AI — SYSTEM PROMPT

AlizaAI adalah AI Trading Assistant untuk pasar cryptocurrency.

Aliza tidak mengeksekusi trading secara otomatis.
Aliza hanya melakukan analisis market dan memberikan rekomendasi trading melalui Telegram dan dashboard web.

AI yang bekerja pada proyek ini harus menjaga arsitektur sistem yang sudah ada.

---

# Tujuan Sistem

AlizaAI melakukan:

- Analisis market crypto
- Deteksi kondisi market
- Pembuatan trade setup
- Monitoring posisi
- Pengiriman alert ke Telegram
- Penyediaan data ke dashboard API

---

# Struktur Sistem

Repository utama:

api/
core/
engine/
interfaces/
dashboard/
scripts/
docs/
data/

---

# Engine

Semua logika market dan trading berada di folder:

engine/

Sub modul utama:

brain/
market/
detectors/
intelligence/
trading/
utils/

---

# Market Pipeline

Pipeline snapshot terjadwal mengikuti alur berikut:

External APIs
↓
market_analyzer
↓
market_radar
↓
TradingBrain
↓
market_snapshot_engine

`market_cache` tetap dipakai oleh sebagian jalur on-demand/legacy, tetapi bukan fallback opportunity scanner ketika snapshot stale.

---

# Market Snapshot System

Job utama memperbarui snapshot tervalidasi setiap 60 detik melalui:

`snapshot_job` → `update_market_snapshot()`

Opportunity scanner membaca `market_snapshot_engine.get_market_snapshot()`. Jika snapshot stale/invalid, scanner abort dan tidak fallback ke market cache. Sebagian command atau checker khusus masih memakai client upstream langsung; jangan menambah API call baru di handler tanpa kebutuhan eksplisit, timeout, dan error handling.

---

# Trading System

Trade disimpan di SQLite database:

`data/aliza.db`

Modul yang sah menulis database ini:

- `engine/trading/trade_manager.py` untuk tabel trade
- `engine/trading/signal_tracker.py` untuk schema/migrasi dan row `signal_tracking`

`engine/user_config.py` memakai database terpisah (`data/user_config.db` secara default).

---

# Telegram Interface

Telegram bot berada di:

interfaces/telegram_bot.py

Command utama:

/start
/market
/radar
/radarpro
/setfutures
/entry
/close
/portfolio
/predict
/quant
/status

Dashboard API tersedia di `api/dashboard_api.py` dan dipasang oleh `api/server.py`:

- `/api/dashboard/market`
- `/api/dashboard/quant`
- `/api/dashboard/predict`
- `/api/dashboard/signals`
- `/api/dashboard/portfolio`

---

# Background Jobs

Telegram bot mendaftarkan job aktual melalui `app.job_queue`:

- `snapshot_job`
- `near_support_checker`
- `near_resistance_checker`
- `rsi_extreme_checker`
- `big_move_checker`
- `watchdog_job`
- `breaking_news_job`
- `morning_brief_job`
- `evening_summary_job`
- `pre_fetch_brief_data_job`
- `spot_signal_job`
- `breakout_check_job`
- `volume_spike_job`
- `funding_alert_job`
- `cfra_alert_job`
- `macro_check_job`
- `whale_alert_job`
- `signal_check_job`
- `evening_calendar_job`

Di dalam `snapshot_job`, `scan_for_signals()` menjalankan filter RR/confidence. Kandidat yang lolos dikirim melalui unified gateway; signal deterministik baru dicatat setelah dispatch berhasil. E3 shadow berjalan pada jalur terpisah dan tidak memakai gateway produksi.

---

# Prinsip Pengembangan

Saat memodifikasi kode:

- Jangan mengubah arsitektur sistem
- Jangan mengubah struktur database
- Jangan mengubah interface trade_manager
- Utamakan snapshot engine untuk data market terjadwal
- Jangan menambah API call langsung tanpa kebutuhan eksplisit, timeout, dan error handling

<!-- Diverifikasi akurat per 2026-07-21, commit f38ab55 -->
