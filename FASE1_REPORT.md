# Laporan Fase 1 — Integritas Sinyal

Tanggal audit: 21 Juli 2026 (WIB).

## Status awal dan branch

Status Git yang dicatat sebelum pekerjaan:

```text
## fix/fase1-signal-integrity
 M engine/alerts/auto_alert_engine.py
 M engine/trading/opportunity_scanner.py
 M engine/trading/signal_engine.py
?? audit-output/
?? engine/utils/formatters.py
```

Branch `fix/fase1-signal-integrity` sudah aktif saat pekerjaan dimulai, sehingga tidak dibuat ulang. Perubahan di atas adalah perubahan pengguna yang sudah ada; tidak disentuh dan tidak dimasukkan ke commit Fase 1.

## Perubahan per item

### 1. Side eksplisit dan short tracker

- `engine/brain/trading_brain.py:TradingBrain.analyze()` mengembalikan `side` eksplisit melalui `SETUP_SIDE`/`_side_for_setup()`: `OVERSOLD BOUNCE` dan `PULLBACK LONG` menjadi `LONG`; `OVERBOUGHT REJECTION` dan `PULLBACK SHORT` menjadi `SHORT`.
- `engine/trading/signal_tracker.py:init_signal_tracking_db()` melakukan migrasi idempotent dengan `PRAGMA table_info`/`ALTER TABLE` untuk `side`, `source`, `signal_id`, `dispatch_status`.
- Baris lama di-backfill side dari setup, source `legacy`, dispatch `UNKNOWN`, dan UUID `uuid.uuid4()`; unique index dibuat pada `signal_id`.
- `check_open_signals()` memakai side. Short menang bila `low <= TP`, kalah bila `high >= SL`; long memakai aturan kebalikannya.

Commit: `4d3c266e`, `5d54ddb0`.

### 2. Record hanya setelah dispatch sukses

`interfaces/telegram_bot.py:_dispatch_and_record_deterministic_signal()` menjalankan `process_signal()` lebih dahulu. Jika hasilnya false, tidak ada insert tracking. Jika true, payload diberi `dispatch_status='SENT'`, `source='deterministic'`, market score/regime, lalu `record_signal()` dipanggil. `snapshot_job()` memakai helper ini.

Commit: `4760d76b`.

### 3. Provenance LLM

`interfaces/telegram_bot.py:_parse_and_record_signals()` memberi `source='llm'`, side eksplisit, dan `dispatch_status='SENT'`. `morning_brief_job()`/`evening_summary_job()` hanya mem-parsing setelah `safe_dispatch()` berhasil. `engine/trading/signal_tracker.py:get_signal_stats(source='deterministic')` default hanya menghitung deterministic; `source=None` mencakup semua source; breakdown tersedia melalui `by_source`, `by_side`, `by_setup`.

Commit: `4d3c266e`.

### 4. Outcome OHLC 5m dan biaya

`engine/trading/signal_tracker.py:_fetch_5m_klines()` mengambil kline Binance interval `5m` sejak waktu signal. `_evaluate_outcome()` menggunakan high/low. TP dan SL dalam candle sama dicatat sebagai `LOSS` pada SL. `_net_pnl_pct()` mengurangi fee round-trip `0,2%`. `check_open_signals()` memperbarui status, close price/time dan PnL.

Commit: `7d3dc235`.

### 5. Kontrak score auto-alert

`engine/alerts/auto_alert_engine.py:_load_min_score()` memakai default 70 dan env `AUTO_ALERT_MIN_SCORE`; validasi finite `0..100` menulis error lalu melempar `RuntimeError` jika threshold invalid. `process_auto_alerts()` memakai threshold ini, RR 2,5 dan confidence 65.

Commit: `ac1a5537`.

### 6. Pipeline candle bersih

`engine/market/market_analyzer.py:_extract_closed_kline_closes()` membuang candle yang `closeTime`-nya belum lewat. `market_signal()` tidak lagi meng-append ticker. Timeframe 4h di bawah 30 candle atau 1d di bawah 50 ditandai unavailable, bukan saling menggantikan; analyzer menghasilkan alignment `UNKNOWN` sehingga `TradingBrain` menolak setup.

Commit: `ad1f6af7`.

### 7. Invariant arah risk validator

`engine/risk_manager.py:validate_proposed_trade()` menerima side, menolak non-finite/nol, menegakkan `SL < entry < TP1` untuk LONG dan `TP1 < entry < SL` untuk SHORT. `_current_open_trades()` fail-closed ketika store tidak tersedia/gagal. `engine/signal_engine.py:validate_signal_risk()` dan `TradingBrain` meneruskan side.

Commit: `5d54ddb0`.

### 8. Runtime dan scheduler

`interfaces/telegram_bot.py:main()` kini hanya mendaftarkan satu `rsi_extreme_checker` tiap 300 detik dan satu `signal_check_job` tiap 600 detik. `aliza-market.service` stale sejak 2 Juni dan menjalankan kode lama; sesuai instruksi, tidak direstart/dinonaktifkan. Rekomendasi operasional adalah change-control terpisah untuk `systemctl restart aliza-market` atau disable setelah memastikan Telegram primary mencukupi.

Commit: `cb075e44`.

## Commit Fase 1

| Item | Commit |
|---|---|
| 1/7 side/schema/validator | `4d3c266e`, `5d54ddb0` |
| 2 dispatch-before-record | `4760d76b` |
| 3 provenance/stats | `4d3c266e` |
| 4 OHLC/fee | `7d3dc235` |
| 5 auto-alert score | `ac1a5537` |
| 6 candle/MTF | `ad1f6af7` |
| 8 scheduler | `cb075e44` |
| test wajib | `21ae77d4` |

Item 1 dan 7 berbagi `5d54ddb0` agar perubahan side pada caller dan validator tetap atomik; migrasi/provenance tracker berada di `4d3c266e`.

## Test dan verifikasi

Test wajib dibuat di `tests/test_fase1.py` dan dijalankan dengan:

```text
venv/bin/python -m pytest -q tests/test_fase1.py
```

Hasil: **9 passed, 3 warnings dalam 13,33 detik**. Test mencakup short TP/SL, same-bar konservatif LOSS, gateway rejection tanpa row, stats default tanpa LLM, closed candle/no ticker append, missing 1d → UNKNOWN, invalid long level, score 70/160, serta migrasi legacy idempotent.

Warning hanya `DeprecationWarning` tipe SWIG dari dependency saat import Telegram. `pytest` sistem tidak ada di PATH; virtualenv berhasil. Suite di luar `tests/test_fase1.py` tidak dijalankan sebagai verifikasi wajib.

## TIDAK SELESAI / batasan

- Service market tidak direstart/dinonaktifkan; hanya dicatat sesuai instruksi.
- Parameter strategi tidak diubah: RSI 30/70, SL oversold 1,5%, RR dan setup tetap.
- `.env`, token, API key, password, dan data produksi tidak disentuh.
- Tidak ada integration test Binance/Telegram; test memakai mock/fixture.
- Path `AlizaAI-Crypto/01-hasil-audit-codex/` tidak ada sebelum pekerjaan. Dengan asumsi path relatif terhadap repo kerja, folder dibuat di `/opt/aliza-ai/AlizaAI-Crypto/01-hasil-audit-codex/` dan laporan disalin identik ke sana.

## Pemeriksaan akhir

Perubahan pengguna yang tetap dirty dan tidak disentuh:

```text
 M engine/alerts/auto_alert_engine.py
 M engine/trading/opportunity_scanner.py
 M engine/trading/signal_engine.py
?? audit-output/
?? engine/utils/formatters.py
```

Tidak ada secret yang ditulis ke laporan.
