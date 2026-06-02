# ALIZA AI — DEBUG PLAYBOOK

Dokumen ini menjelaskan prosedur debugging standar untuk sistem AlizaAI.

Tujuan:
- Mencegah AI melakukan perubahan kode yang tidak perlu
- Mengidentifikasi akar masalah sebelum memperbaiki kode
- Menjaga stabilitas sistem

AI yang melakukan debugging harus mengikuti langkah-langkah berikut.

---

# 1. RULE: DO NOT MODIFY CODE BEFORE DIAGNOSIS

AI tidak boleh langsung mengubah kode.

Langkah pertama selalu:

1. Analisis log
2. Identifikasi modul yang bermasalah
3. Periksa dependency modul
4. Konfirmasi akar masalah

Hanya setelah diagnosis jelas, kode boleh diperbaiki.

---

# 2. TELEGRAM BOT NOT RESPONDING

Jika Telegram bot tidak merespon command:

Langkah diagnosis:

1. Periksa apakah proses bot berjalan

ps aux | grep telegram_bot.py

2. Periksa log output bot

Cari error seperti:

Traceback
Exception
Network error

3. Pastikan polling aktif

run_polling()

4. Periksa apakah command handler terdaftar

CommandHandler("start")
CommandHandler("market")

5. Periksa apakah Telegram token valid

TELEGRAM_BOT_TOKEN

---

# 3. MARKET DATA MISSING

Jika market data tidak muncul:

Periksa pipeline berikut:

market_snapshot_engine
↓
market_analyzer
↓
market_radar
↓
TradingBrain

Langkah diagnosis:

1. Periksa snapshot

market_snapshot_engine.get_market_snapshot()

2. Pastikan snapshot berisi data coin

snapshot["data"]

3. Jika kosong, periksa:

update_market_snapshot()

4. Periksa API:

CoinGecko
Binance
Fear & Greed

---

# 4. SIGNAL ENGINE NOT SENDING SIGNALS

Jika tidak ada signal trading:

Periksa:

signal_engine.scan_for_signals()

Langkah diagnosis:

1. Periksa market snapshot

2. Periksa apakah opportunity ditemukan

scan_opportunities()

3. Periksa filter signal:

RR ≥ 3
confidence ≥ 70

4. Periksa anti-spam rule

ANTI_SPAM_WINDOW = 30 minutes

---

# 5. OPPORTUNITY SCANNER NOT RETURNING DATA

Periksa:

scan_opportunities()

Langkah diagnosis:

1. Apakah market_data tersedia
2. Apakah trade_setup ada
3. Apakah RR ≥ 1.3

Jika RR terlalu kecil, opportunity tidak muncul.

---

# 6. TRADE ENTRY NOT WORKING

Jika /entry gagal:

Periksa:

trade_manager.create_trade()

Langkah diagnosis:

1. Periksa apakah trade_setup ada
2. Periksa validasi entry
3. Periksa SQLite database

data/aliza.db

---

# 7. DATABASE ERRORS

Jika SQLite error muncul:

Langkah diagnosis:

1. Periksa file database

data/aliza.db

2. Periksa apakah tabel trades ada

3. Jalankan:

init_trade_db()

---

# 8. MARKET SNAPSHOT NOT UPDATING

Periksa job berikut:

market_snapshot_job

Langkah diagnosis:

1. Apakah job berjalan
2. Apakah update_market_snapshot() dipanggil
3. Apakah API rate limit terjadi

---

# 9. TELEGRAM ALERTS NOT SENT

Periksa:

context.bot_data["chat_id"]

Jika kosong:

user belum menjalankan:

/start

---

# 10. SAFE DEBUGGING RULES

Saat debugging:

AI harus:

- membaca log terlebih dahulu
- tidak langsung refactor modul besar
- tidak menghapus handler
- tidak mengubah struktur database

Debugging harus dilakukan secara bertahap.

---

END OF DOCUMENT