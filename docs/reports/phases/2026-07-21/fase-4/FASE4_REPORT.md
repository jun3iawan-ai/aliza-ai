# Laporan Fase 4 — Uji Ketahanan E3 dan Shadow Mode

Branch: `feat/fase4-shadow`, dibuat dari `main` pada 21 Juli 2026. Tidak ada service, `.env`, atau parameter produksi yang diubah.

## Perubahan kode per file/commit

- `engine/shadow/e3_shadow.py`, `engine/shadow/__init__.py` — modul riset terisolasi; flag `SHADOW_E3_ENABLED`/`SHADOW_E3_DISPATCH` default `false`, fetch/cache candle 4h tertutup, ATR(14), TradingBrain, filter support, level SL 1×ATR dan TP 3×ATR. Commit `fe7c18e1`.
- `interfaces/telegram_bot.py` — `_run_shadow_e3()` dipanggil setelah pipeline produksi; pencatatan `source='shadow_e3'` tidak memakai `process_signal`/dedup produksi. Dispatch opsional lewat `safe_dispatch` dengan header `🧪 SHADOW/RISET — BUKAN SINYAL PRODUKSI`. Command `/shadow_stats` menampilkan N/WR/expectancy/per setup. Commit `fe7c18e1`.
- `engine/trading/signal_tracker.py` — breakdown default mengecualikan `shadow_e3`, sedangkan `get_signal_stats(source='shadow_e3')` khusus shadow. Outcome existing tetap memakai OHLC 5m, same-bar LOSS, fee. Commit `5f8fa8b4`.
- `backtest/costs.py`, `backtest/simulator.py`, `backtest/robustness.py` — parameter slippage eksperimen dan runner bootstrap/stress/rolling/per-coin/post-hoc. Default biaya produksi tidak berubah. Commit `c385bb8d`.
- `tests/test_fase4.py` — flag OFF tanpa mutasi payload, source/stats terpisah, dispatch OFF tanpa Telegram, level ATR. Commit `91303161`.

## Hasil test

Test Fase 4: **3 passed**. Full suite: **133 passed, 3 warnings, 74 subtests passed** dalam 24,85 detik.

## Bagian A — robustness

Hasil lengkap ada di [ROBUSTNESS_RESULTS.md](ROBUSTNESS_RESULTS.md). Verdict: **CAMPURAN**. Bootstrap CI positif dan biaya 3× masih positif, tetapi performa bergantung regime dan PF tanpa WLD turun. Tidak ada dasar cukup untuk melewati shadow.

## Bagian B — operasi shadow

Default aman: `SHADOW_E3_ENABLED=false`, sehingga snapshot produksi dan payload sinyal tidak berubah. Jika diaktifkan, shadow hanya membaca snapshot, mengambil candle 4h tertutup dengan cache 15 menit, dan menulis row terpisah. `check_open_signals()` yang sudah ada akan mengevaluasi row shadow menggunakan OHLC 5m, same-bar LOSS, time-stop, dan fee yang sama. Query stats produksi default tetap tidak memasukkan `shadow_e3`; gunakan `/shadow_stats` untuk breakdown shadow.

Dispatch Telegram tetap OFF secara default. Jika `SHADOW_E3_DISPATCH=true`, pesan dikirim langsung melalui dispatcher aman (tanpa gateway dedup produksi) dan hanya row yang berhasil dikirim diberi `dispatch_status='SENT'`; mode OFF memakai `RECORDED` tanpa pesan.

## Aktivasi (user yang menjalankan)

Jangan aktifkan otomatis oleh Codex. Setelah review, user dapat menambahkan `SHADOW_E3_ENABLED=true` ke `.env` (dan opsional `SHADOW_E3_DISPATCH=true`), lalu menjalankan restart service manual. Secret tidak ditulis di laporan. Observasi minimal 6 minggu dari aktivasi yang disarankan berakhir sekitar **1 September 2026**.

## Kriteria promosi

Promosi shadow → produksi hanya bila setelah ≥6 minggu atau ≥60 outcome selesai (mana yang lebih lama): expectancy >+0,3%/trade, PF>1,2, batas bawah bootstrap CI >−0,1%, tidak ada coin >50% profit, dan verdict Bagian A bukan RAPUH. Keputusan tetap pada user; fase ini tidak mengubah runtime produksi.
