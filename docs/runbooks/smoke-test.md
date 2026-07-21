# ALIZA AI — TEST SYSTEM

Dokumen ini menjelaskan prosedur pengujian sistem AlizaAI sebelum dan sesudah perubahan kode.

Tujuan:
- memastikan perubahan kode tidak merusak pipeline
- memastikan modul utama tetap kompatibel
- memverifikasi data contract antar engine

AI yang memodifikasi kode harus menjalankan atau memverifikasi test berikut.

---

# 1. MARKET PIPELINE TEST

Pipeline utama:

market_cache
↓
market_analyzer
↓
market_radar
↓
TradingBrain
↓
trade_setup

Test:

1. Jalankan market_signal("BTC")
2. Pastikan output mengandung field berikut:

symbol  
price  
trend  
rsi  
support  
resistance  
fear_greed  
dominance  
cycle_phase  
whale_activity  
market_risk_score  
trade_setup  

Jika field hilang, pipeline rusak.

---

# 2. TRADE SETUP TEST

Jalankan:

TradingBrain.analyze(market_data)

Output harus mengandung:

setup  
entry  
sl  
tp1  
tp2  
risk_reward  
confidence  
risk_quality  

Test validasi:

entry ≠ 0  
sl ≠ 0  
tp1 ≠ 0  
tp2 ≠ 0  

Risk reward harus > 0.

---

# 3. OPPORTUNITY SCANNER TEST

Jalankan:

scan_opportunities()

Pastikan output berupa list opportunity.

Setiap item harus mengandung:

coin  
setup  
entry  
sl  
tp1  
tp2  
rr  
confidence  

List harus bisa di-sort berdasarkan rr.

---

# 4. SIGNAL ENGINE TEST

Jalankan:

scan_for_signals()

Pastikan:

signal memiliki struktur:

coin  
setup  
entry  
sl  
tp1  
tp2  
rr  
confidence  

Jika tidak ada signal, fungsi harus tetap return None tanpa crash.

---

# 5. DATABASE TEST

Test SQLite database.

File:

data/aliza.db

Langkah:

1. Jalankan init_trade_db()
2. Buat trade:

create_trade("BTC", setup, entry, sl, tp1, tp2)

3. Ambil trade:

get_active_trades()

Output harus berisi trade yang baru dibuat.

4. Tutup trade:

close_trade("BTC")

Status harus berubah menjadi CLOSED.

---

# 6. MARKET SNAPSHOT TEST

Jalankan:

update_market_snapshot()

Lalu:

get_market_snapshot()

Snapshot harus memiliki struktur:

{
 "data": {...},
 "timestamp": datetime
}

Snapshot["data"] tidak boleh kosong.

---

# 7. TELEGRAM COMMAND TEST

Pastikan handler berikut tersedia:

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

Jika handler hilang, bot tidak akan merespon command.

---

# 8. DASHBOARD API TEST

Test endpoint berikut:

/health  
/api/dashboard/market  
/api/dashboard/predict  
/api/dashboard/quant  
/api/dashboard/signals  
/api/dashboard/portfolio  

Endpoint harus return JSON valid.

---

# 9. ERROR HANDLING TEST

Semua modul harus menangani error.

Test dengan:

- API offline
- coin data kosong
- database error

Sistem tidak boleh crash.

---

# 10. SYSTEM INTEGRATION TEST

Test end-to-end:

1. update_market_snapshot()
2. scan_opportunities()
3. scan_for_signals()
4. create_trade()
5. analyze_positions()

Jika seluruh pipeline berjalan tanpa exception,
maka sistem dianggap stabil.

---

END OF DOCUMENT