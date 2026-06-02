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

Semua data market mengikuti pipeline berikut:

market_cache
↓
market_analyzer
↓
market_radar
↓
TradingBrain
↓
trade_setup

---

# Market Snapshot System

Telegram bot tidak boleh memanggil API langsung.

Semua data market harus diambil dari:

market_snapshot_engine.get_market_snapshot()

Snapshot diupdate setiap 60 detik.

---

# Trading System

Trade disimpan di SQLite database:

data/aliza.db

Hanya modul berikut yang boleh mengubah database:

engine/trading/trade_manager.py

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

---

# Background Jobs

Telegram bot menjalankan job berikut:

market_snapshot_job
trade_guardian_job
position_management_job
crash_detector_job
whale_tracker_job
altseason_detector_job
signal_engine_job
market_intelligence_job

---

# Prinsip Pengembangan

Saat memodifikasi kode:

- Jangan mengubah arsitektur sistem
- Jangan mengubah struktur database
- Jangan mengubah interface trade_manager
- Jangan memanggil API langsung dari Telegram command
- Gunakan snapshot engine untuk data market