# 06 — Kualitas Kode dan Masalah

> **Status: SUPERSEDED.** Snapshot pada 2026-07-21. Kondisi sistem terkini ada di `docs/README.md` dan report Fase 1–4 (`docs/reports/` — lihat Bagian 3). Jangan jadikan dokumen ini sebagai acuan status aktif.

## Ringkasan risiko

Kualitas sintaks cukup baik—125 file Python aktif berhasil diparse AST tanpa syntax error—dan hardening dashboard/Telegram memiliki test. Namun mesin trading tidak mempunyai test strategi/backtest, state terfragmentasi, dan beberapa defect deterministik langsung merusak signal atau metrik. Risiko terbesar bukan crash aplikasi, melainkan sistem tetap berjalan sambil memberi hasil yang terlihat valid tetapi salah.

## Temuan kritis

### K-01 — Auto alert tidak mungkin lolos

`engine/trading/opportunity_scanner.py:get_top_opportunities()` menimpa score ranking besar dengan `engine/brain/signal_quality_engine.py:calculate_signal_quality()`, yang membatasi score 0–100. `engine/alerts/auto_alert_engine.py` meminta `MIN_SCORE=160`. Tidak ada kandidat yang dapat lolos.

Dampak: fitur auto alert inti diam tanpa error eksplisit; opportunity ada tetapi tidak pernah didispatch.

### K-02 — Short outcome salah arah

`engine/trading/signal_tracker.py:check_open_signals()` mendeteksi short hanya untuk label persis `SHORT`. Setup `PULLBACK SHORT` dan `OVERBOUGHT REJECTION` dianggap long.

Dampak: WIN/LOSS dan PnL bisa terbalik; winrate tidak dapat dipercaya.

### K-03 — Sinyal dicatat sebelum lolos gateway

`interfaces/telegram_bot.py:snapshot_job()` memanggil `record_signal()` sebelum `engine/signal_engine.py:process_signal()`. Gateway dapat menolak karena risiko, makro, dedup atau kegagalan dispatch.

Dampak: phantom signal masuk statistik walau user tidak pernah menerimanya.

### K-04 — Candle aktif/duplikasi harga dan false MTF

`engine/market/market_analyzer.py:market_signal()` menambahkan ticker ke close kline yang sudah mengandung candle aktif. Ia juga memakai seri utama yang sama sebagai fallback `4h` dan `1d` ketika data kurang.

Dampak: lookahead/intrabar contamination, harga terakhir berbobot ganda, dan alignment multi-timeframe palsu. Ini bagian paling berisiko memicu signal entry salah.

### K-05 — Sinyal LLM masuk tracking tanpa validasi risiko

`interfaces/telegram_bot.py:_generate_spot_analysis()`, `_generate_futures_analysis()`, `_reorder_section_by_rr()` dan `_parse_and_record_signals()` membuat, menulis ulang dan mencatat level generatif. SL dapat dipaksa 6% dan TP tepat 2R tanpa hubungan dengan support/resistance; jalur ini tidak melewati gateway/risk manager.

Dampak: signal dengan metodologi berbeda tercampur ke winrate engine deterministik.

## Temuan tinggi

### K-06 — Risk validation tidak memeriksa sisi level

`engine/risk_manager.py:validate_proposed_trade()` memakai jarak absolut dan tidak mengecek `SL < entry < TP` untuk long atau kebalikannya untuk short. Kesalahan level dapat lolos. Error penghitung open position juga fail-open.

### K-07 — Tracker outcome tidak memakai OHLC/intrabar

`signal_tracker.py:check_open_signals()` memeriksa harga titik setiap 10/30 menit. TP/SL yang tersentuh lalu berbalik dapat hilang; jika keduanya tersentuh, urutan tidak diketahui. Tidak ada fee, spread, slippage atau funding.

### K-08 — Rezim satu siklus lama

`engine/brain/trading_brain.py:TradingBrain.analyze()` membaca `get_market_snapshot()` ketika snapshot baru masih dibangun. Rezim yang digunakan dapat berasal dari siklus sebelumnya; pada startup bisa unknown. Intelligence current cycle baru ditambahkan setelah analisis signal coin selesai.

### K-09 — TradingBrain memakai level sebelum fallback final

Di `market_analyzer.py:market_signal()`, `TradingBrain.analyze()` dipanggil sebelum fallback support/resistance final diberlakukan. Nilai kosong/nol dapat menyebabkan `NO SETUP` walau sesudahnya output market mempunyai level fallback yang terlihat valid.

### K-10 — Proses market menjalankan source lama

`aliza-market.service` belum restart sejak 2 Juni 2026; journal menampilkan watchlist tujuh coin, berbeda dari 21 coin di source saat audit. Ia non-primary tetapi tetap memanggil API dan membangun snapshot mandiri.

Dampak: duplikasi load/rate-limit dan diagnosis runtime membingungkan; perubahan kode tidak berlaku pada proses tersebut.

### K-11 — Snapshot parsial dianggap sehat

`market_snapshot_engine.py:update_market_snapshot()` dapat mempublikasikan 17/21 coin. Freshness hanya timestamp snapshot lokal; tidak ada completeness SLA per coin/upstream. Empat coin gagal berulang pada runtime.

### K-12 — Tidak ada backtesting atau test trading

Ada 105 method test dalam sembilan file test, tetapi fokus pada auth, rate limit, binding, dotenv isolation dan Telegram authorization. Pencarian referensi TradingBrain, market signal, position size, tracker, RR dan backtest dalam test tidak menghasilkan coverage.

## Temuan menengah

### K-13 — Fragmentasi state/risk

- PostgreSQL: user/chat/usage/docs.
- SQLite: trade dan signal tracking.
- JSON: learning, drawdown dan dedup.
- RAM per proses: snapshot/cache.
- Dua risk manager dan dua position sizer dengan default 1% vs 2%.

Ini menciptakan state yang tidak sinkron dan perilaku berbeda per command.

### K-14 — Learning overfit dan memakai data salah

`confidence_adjuster.py` menyesuaikan pada sampel mulai satu trade. Datanya berasal dari `trade_history.json` legacy, bukan `signal_tracking`; dua outcome sampel cukup mempengaruhi confidence. Profit factor `performance_analyzer.py` juga bergantung RR yang bisa tidak signed.

### K-15 — BTC smart alert kekurangan candle input

`btc_smart_alert.py` mengharapkan candle OHLCV untuk volume/strong-close/healthy-pullback, tetapi `market_analyzer.py` meneruskan close series. Cabang konfirmasi penting tidak bekerja sebagaimana desain. Selain itu `should_alert_btc()` tidak dispatch `TAKE PROFIT`.

### K-16 — Heuristik market salah label/ambang

- `market_ai_predictor.py:bull_probability()` mencari `stablecoin_flow == "HIGH"`, sementara producer menghasilkan `HIGH INFLOW`; bonus tidak aktif.
- `stablecoin_inflow` sebenarnya total sirkulasi, bukan flow/delta.
- `crypto_intelligence.py:analyze_funding()` memakai ±5%, sedangkan monitor aktif memakai ±0,1%.
- OI diklasifikasi dalam jumlah BTC absolut, tidak dinormalisasi USD/regime historis.
- Fear/greed dan dominance gagal → nilai 50, menyembunyikan data outage.

### K-17 — Threshold dan scheduler duplikat

- Volume spike detector >2×, dispatch >4×.
- Komentar cooldown breakout 4 jam, implementasi 8 jam.
- `rsi_extreme_checker` didaftarkan dua kali (5 dan 10 menit).
- Outcome tracker didaftarkan pada dua interval.
- Docstring spot menyebut enam kali/hari, scheduler hanya tiga.

### K-18 — Health check terlalu dangkal

`api/server.py:/health` selalu mengembalikan `ok`; tidak memeriksa DB, snapshot, LLM atau upstream. `core/database.py` membuka satu koneksi global dan DDL saat import, sehingga kegagalan DB menggagalkan startup dan koneksi jangka panjang rawan stale.

### K-19 — Dynamic universe tidak dinamis

`engine/market/dynamic_universe.py` memiliki kode seleksi, tetapi `market_universe.py:get_tradable_coins()` selalu mengembalikan CORE_COINS. Klaim top-200 juga bertentangan dengan fetch 50. Coin exotic yang gagal terus tetap dipoll.

### K-20 — Deploy/path drift

`scripts/deploy/deploy.sh`, `hooks.json`, backup script dan shebang pip mengacu `/home/ubuntu/aliza-ai`; deployment ada di `/opt/aliza-ai`. Deploy script juga merestart unit `aliza-api` milik repo lain. Folder UI target kosong (`dashboard/`), sementara aset berada di `web/`.

## TODO/FIXME/HACK

Penanda utang teknis nyata yang ditemukan:

- `engine/macro/macro_checker.py`: TODO memasang kalender ekonomi real-time. Kode lain sudah mempunyai beberapa kalender, tetapi checker ini tetap mendeklarasikan TODO dan failure fail-open.
- `skills_custom/weather.py`: weather belum diimplementasikan.

String “exchange hack”/“crypto hack” di `interfaces/telegram_bot.py` adalah keyword berita keamanan, bukan penanda HACK kode. Tidak ditemukan FIXME/XXX lain.

## Kode mati, opsional, dan duplikasi

Calon kode tidak terpakai berdasarkan pencarian caller internal:

- `engine/utils/market_cache_updater.py:update_market_cache()` tidak mempunyai caller.
- `engine/trading/signal_engine.py:_signal_body_for_dedup()` tidak mempunyai caller.
- `engine/monitoring/market_monitor.py` tidak mempunyai caller/service aktif yang ditemukan.
- `engine/intelligence/predictive_market_ai.py` dan `quant_market_model.py` dirujuk secara opsional tetapi filenya tidak ada; API mengembalikan `unavailable`, Telegram fallback.
- Strategy map memuat `MOMENTUM LONG`, `MOMENTUM SHORT`, `BREAKOUT LONG`, tetapi producer `TradingBrain` tidak membuatnya.
- `dashboard/` kosong; `web/` tidak diserve oleh path FastAPI saat ini.

Duplikasi/legacy:

- `api_server.py` dan `api/server.py` dua API berbeda.
- Risk manager dan position sizer masing-masing memiliki dua implementasi.
- `market_radar.py`, `market_radar_pro.py`, `market_intelligence.py`, `market_intelligence_engine.py`, `market_state_engine.py` memiliki overlap terminologi dan sebagian fallback.
- 103 file backup bot berada di folder source, menambah noise audit/deploy.
- Tabel user/chat/docs ada di PostgreSQL dan SQLite.

Keterangan “tidak mempunyai caller” hanya mencakup repo yang diaudit. **TIDAK PASTI** apakah modul dipanggil tool eksternal/manual.

## Error handling dan rate limit

Banyak integrasi menggunakan `except Exception` lalu mengembalikan default/`None` atau hanya log singkat. Retry/backoff terpadu, jitter, pengenalan HTTP 429 dan per-host budget tidak ditemukan. Snapshot retry coin gagal setelah fixed 30 detik; dua proses aktif menggandakan request. Ini berisiko terhadap rate limit dan silent degradation.

FastAPI sendiri telah memiliki rate limiter dan execution limiter LLM yang jauh lebih baik, tetapi kontrol tersebut tidak melindungi polling market/Telegram.

## Prioritas perbaikan teknis

1. Pisahkan dan uji provenance signal; catat hanya sesudah gateway/dispatch sukses.
2. Perbaiki arah short dan gunakan candle high/low untuk outcome deterministik.
3. Perbaiki kontrak score auto-alert dan tambahkan integration test.
4. Gunakan closed candles dan larang fallback MTF dari seri sama.
5. Satukan risk manager/sizer/state dan enforce invariant arah.
6. Pisahkan statistik deterministic dari LLM, spot dari futures, serta paper/live.
7. Tambah backtest event-driven dengan fee/slippage/funding dan walk-forward.
8. Hilangkan proses source lama/duplikasi polling dan tambahkan upstream health/completeness.
