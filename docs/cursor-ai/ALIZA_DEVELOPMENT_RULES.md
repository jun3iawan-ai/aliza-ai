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

data/aliza.db

Struktur tabel trades tidak boleh diubah tanpa migrasi resmi.

---

# 3. Trade Manager Adalah Satu-satunya Modul Database

Database hanya boleh dimodifikasi oleh:

engine/trading/trade_manager.py

---

# 4. Telegram Command Tidak Boleh Memanggil API

Telegram command harus menggunakan:

market_snapshot_engine.get_market_snapshot()

Bukan memanggil API langsung.

---

# 5. Jangan Membuat Blocking Code di Telegram Handler

Telegram handler harus ringan.

Logika berat harus ditempatkan di engine modules.

---

# 6. Gunakan Engine Modules

Logika baru harus ditambahkan di:

engine/

bukan langsung di telegram_bot.py.

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