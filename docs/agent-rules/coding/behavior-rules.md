# ALIZA AI — AI BEHAVIOR RULES

Dokumen ini mendefinisikan aturan perilaku AI (Cursor, ChatGPT, atau AI coding tools) saat memodifikasi sistem AlizaAI.

Tujuan:
- Mencegah refactor besar tanpa izin
- Menjaga stabilitas sistem
- Menghindari perubahan yang merusak modul lain

AI yang bekerja pada proyek ini harus mematuhi aturan berikut.

---

# 1. DO NOT CHANGE SYSTEM ARCHITECTURE

Struktur utama proyek tidak boleh diubah tanpa permintaan eksplisit.

Struktur utama:

api/
core/
engine/
interfaces/
dashboard/
scripts/
docs/
data/

Jika perubahan arsitektur diperlukan, AI harus terlebih dahulu menjelaskan dampaknya.

---

# 2. DO NOT REFACTOR LARGE MODULES WITHOUT REQUEST

AI tidak boleh melakukan refactor besar pada modul berikut tanpa diminta:

market_analyzer.py  
trading_brain.py  
signal_engine.py  
telegram_bot.py  
trade_manager.py  

Refactor hanya boleh dilakukan jika diminta secara eksplisit.

---

# 3. DO NOT REMOVE EXISTING COMMANDS

Telegram command berikut harus selalu tersedia:

/start  
/help  
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

AI tidak boleh menghapus command handler ini.

---

# 4. DO NOT CHANGE DATA STRUCTURES

Struktur berikut tidak boleh diubah:

Market Data Structure  
Trade Setup Structure  
Opportunity Structure  
Signal Structure  
Trade Database Structure  

Referensi ada di:

docs/cursor-ai/ALIZA_ENGINE_CONTRACTS.md

---

# 5. DO NOT CHANGE DATABASE BEHAVIOR

Database SQLite:

`data/aliza.db`

Modul yang sah memodifikasi database ini:

- `engine/trading/trade_manager.py` untuk trade
- `engine/trading/signal_tracker.py` untuk schema/migrasi dan tracking signal

`engine/user_config.py` menulis database terpisah. AI tidak boleh menambah penulis baru ke `data/aliza.db` tanpa migrasi, test, dan persetujuan eksplisit.

---

# 6. TELEGRAM HANDLERS MUST BE LIGHTWEIGHT

Handler Telegram tidak boleh melakukan operasi berat seperti:

- market scan sinkron panjang
- kalkulasi berat di event loop
- API call baru tanpa timeout dan error handling

Utamakan `market_snapshot_engine.get_market_snapshot()` untuk data terjadwal. Direct upstream call yang sudah ada pada command/checker khusus bukan alasan menambah call baru tanpa review.

---

# 7. DO NOT BYPASS MARKET SNAPSHOT

Opportunity scanner wajib memakai snapshot tervalidasi dan abort jika snapshot stale/invalid; tidak ada fallback ke market cache. Perubahan yang melewati guard ini memerlukan persetujuan eksplisit. Jalur khusus yang memang menggunakan upstream langsung wajib mempunyai timeout, error handling, dan tidak boleh mengarang fallback data.

`snapshot_job` memanggil `scan_for_signals()`; kandidat produksi yang lolos diproses melalui unified gateway dan baru dicatat sebagai signal deterministik setelah dispatch berhasil. Jangan mengembalikan urutan record-before-dispatch.

---

# 8. DO NOT REMOVE ERROR HANDLING

Semua handler dan job harus memiliki error handling.

Contoh:

try:
    ...
except Exception as e:
    logging.error(e)

AI tidak boleh menghapus blok error handling.

---

# 9. PRESERVE BACKWARD COMPATIBILITY

Jika AI menambahkan fitur baru:

- fitur lama harus tetap bekerja
- format data lama harus tetap valid

---

# 10. EXPLAIN BEFORE MAJOR CHANGE

Jika AI merasa perlu melakukan perubahan besar:

AI harus terlebih dahulu menjelaskan:

- alasan perubahan
- dampak terhadap modul lain
- risiko yang mungkin muncul

Perubahan hanya dilakukan setelah disetujui.

---

# 11. PREFER EXTENDING INSTEAD OF REWRITING

Jika ingin menambahkan fitur baru:

AI harus:

- menambah modul baru
- atau menambah fungsi baru

Bukan mengganti modul yang sudah ada.

---

# 12. KEEP TRADING LOGIC STABLE

Trading logic di modul berikut harus stabil:

TradingBrain  
Opportunity Scanner  
Signal Engine  

AI tidak boleh mengubah rule trading tanpa diminta.

---

# 13. NEVER BREAK THE MARKET PIPELINE

Pipeline snapshot utama adalah:

External APIs
↓
market_analyzer  
↓
market_radar  
↓
TradingBrain  
↓
market_snapshot_engine

`market_cache` melayani sebagian jalur on-demand/legacy, bukan fallback opportunity scanner. AI tidak boleh mem-bypass validasi snapshot pada jalur sinyal terjadwal.

---

# 14. ALWAYS RESPECT DOCUMENTATION

AI harus mengikuti dokumentasi berikut:

ALIZA_SYSTEM_PROMPT.md  
ALIZA_ARCHITECTURE_MAP.md  
ALIZA_DEVELOPMENT_RULES.md  
ALIZA_ENGINE_CONTRACTS.md  

Jika dokumentasi bertentangan dengan kode, AI harus melaporkannya.

---

<!-- Diverifikasi akurat per 2026-07-21, commit f38ab55 -->

END OF DOCUMENT