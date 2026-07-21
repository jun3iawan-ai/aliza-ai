# ALIZA AI — SYSTEM HEALTH CHECK

Dokumen ini berisi prosedur cepat untuk memeriksa apakah seluruh sistem AlizaAI berjalan dengan normal.

Gunakan checklist ini setiap kali:

- bot restart
- deploy update
- sistem terasa tidak responsif
- signal tidak muncul
- market data hilang

Tujuan:
memastikan seluruh pipeline sistem Aliza berjalan dengan benar.

---

# 1. TELEGRAM BOT STATUS

Periksa apakah bot berjalan.

Command server:

ps aux | grep telegram_bot.py

Jika bot berjalan, akan terlihat proses Python.

Jika tidak:

restart bot.

---

# 2. TELEGRAM COMMAND TEST

Kirim command berikut:

/start  
/market  
/radar  

Jika bot merespon, interface Telegram berfungsi.

Jika tidak merespon:

periksa handler command di:

interfaces/telegram_bot.py

---

# 3. MARKET SNAPSHOT TEST

Periksa snapshot market.

Jalankan:

get_market_snapshot()

Snapshot harus memiliki struktur:

{
 "data": {...},
 "timestamp": datetime
}

Jika data kosong:

periksa:

update_market_snapshot()

---

# 4. MARKET ANALYZER TEST

Test analisis market:

market_signal("BTC")

Output harus mengandung:

price  
trend  
rsi  
support  
resistance  
trade_setup  

Jika error muncul, kemungkinan API market bermasalah.

---

# 5. OPPORTUNITY SCANNER TEST

Jalankan:

scan_opportunities()

Output harus berupa list opportunity.

Jika kosong:

periksa:

RR filter  
confidence filter  

---

# 6. SIGNAL ENGINE TEST

Jalankan:

scan_for_signals()

Jika tidak ada signal:

periksa:

RR ≥ 3  
confidence ≥ 70  
market_risk  

---

# 7. DATABASE TEST

Periksa database SQLite.

File:

data/aliza.db

Test:

get_active_trades()

Jika error muncul:

jalankan:

init_trade_db()

---

# 8. POSITION MANAGER TEST

Jalankan:

analyze_positions()

Jika tidak ada error, posisi monitoring berjalan.

---

# 9. DASHBOARD API TEST

Buka:

/health

Jika response:

{
 "status": "ok"
}

dashboard berjalan normal.

---

# 10. SYSTEM PIPELINE CHECK

Pipeline utama:

External APIs
↓
market_analyzer
↓
market_radar
↓
TradingBrain
↓
trade_setup
↓
opportunity_scanner
↓
signal_engine
↓
telegram alerts

Jika salah satu modul gagal, seluruh pipeline bisa terpengaruh.

---

# QUICK STATUS SUMMARY

Sistem dianggap sehat jika:

Telegram bot aktif  
Snapshot berisi data  
Market analyzer berjalan  
Opportunity scanner menghasilkan data  
Signal engine tidak crash  
Database dapat diakses  

Jika semua ini terpenuhi, sistem Aliza berjalan normal.

---

END OF DOCUMENT