# ALIZA AI — DEVELOPMENT RULES

Aturan berikut wajib diikuti saat mengubah kode.

---

# 1. Jangan Mengubah Arsitektur

Struktur utama project tidak boleh diubah.

engine/
interfaces/
api/
core/

---

# 2. Jangan Mengubah Database

Database SQLite:

`data/aliza.db`

Struktur tabel `trades` atau `signal_tracking` tidak boleh diubah tanpa migrasi resmi dan test.

---

# 3. Batasi Penulis Database

Penulis yang sah untuk `data/aliza.db`:

- `engine/trading/trade_manager.py` untuk trade
- `engine/trading/signal_tracker.py` untuk schema/migrasi dan tracking signal

`engine/user_config.py` memakai database terpisah. Jangan menambah penulis baru ke `data/aliza.db` tanpa persetujuan eksplisit.

---

# 4. Utamakan Snapshot di Telegram

Jalur market terjadwal dan opportunity scanner harus menggunakan:

`market_snapshot_engine.get_market_snapshot()`

Opportunity scanner wajib abort saat snapshot stale/invalid dan tidak boleh fallback ke market cache. Direct API call yang sudah ada pada command/checker khusus harus tetap memiliki timeout dan error handling; jangan menambah call baru tanpa kebutuhan eksplisit.

---

# 5. Jangan Membuat Blocking Code di Telegram Handler

Telegram handler harus ringan.

Logika berat atau blocking harus ditempatkan di engine module/executor, bukan dijalankan langsung pada event loop.

---

# 6. Gunakan Engine Modules

Logika baru harus ditambahkan di:

`engine/`

Koordinasi handler/job boleh berada di `interfaces/telegram_bot.py`, tetapi logika domain baru tetap ditempatkan di engine.

---

# 7. Jangan Menghapus Handler Telegram

Command berikut harus selalu ada:

/start
/market
/radar
/setfutures
/entry
/portfolio

---

# 8. Jangan Mengubah Struktur Trade Setup

Trade setup harus selalu memiliki:

coin
setup
entry
sl
tp1
tp2
risk_reward
confidence
risk_quality

<!-- Diverifikasi akurat per 2026-07-21, commit f38ab55 -->
