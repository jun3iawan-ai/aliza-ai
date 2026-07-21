# Laporan Fase 3 — Eksperimen Perbaikan Strategi

Tanggal run: 21 Juli 2026 (UTC). Branch: `feat/fase3-experiments`.

## Ruang lingkup dan protokol

Eksperimen dijalankan hanya di backtester; tidak ada perubahan parameter strategi live, jalur runtime, `.env`, atau service. Protokol ditetapkan sebelum run: TUNE 2024-07-21 s.d. 2026-01-20, HOLDOUT 2026-01-21 s.d. 2026-07-21; grid hanya nilai yang diminta; holdout dijalankan sekali untuk dua kandidat terbaik TUNE dengan N≥200. Kriteria holdout: expectancy >0,10%/trade, PF >1,15, N≥80, dan tidak ada satu coin menyumbang >50% profit.

Data 5m, 4h, 1d dan funding Binance dikache lokal (11 coin: BTC, ETH, BNB, SOL, XRP, ADA, SUI, ARB, PEPE, WLD, TAO). Seluruh trade TUNE menggunakan resolusi 5m. Funding tercatat per trade: `binance_history` 397, fallback 0,01%/8 jam 49, dan `none` 522 pada baseline production-filter. Cache mentah tidak di-commit (`backtest/data/` di-ignore).

## Perubahan kode dan commit

- `engine/market/features.py:average_true_range()` — ATR Wilder periode 14 berbasis OHLC candle tertutup, nilai indeks hanya memakai data sampai indeks tersebut (anti-lookahead). Commit `63cace6b`.
- `backtest/data_loader.py:BinanceDataLoader._get()` dan `load_funding()` — endpoint funding dipisah ke `fapi.binance.com`, tetap memakai retry/backoff yang ada. Commit `63cace6b`.
- `backtest/simulator.py:_exit_event()` — event loop lower timeframe dengan cursor, same-bar TP+SL konservatif LOSS, time-stop configurable; cursor tidak membocorkan state ke pemanggilan eksternal.
- `backtest/simulator.py:_mae_pct()`/`_trade_record()` — MAE dicatat per trade.
- `backtest/simulator.py:simulate_coin()` — hook eksperimen (SL ATR, TP ATR, konfirmasi candle berikutnya, filter support/funding, disable setup, RR/conf threshold), entry normal di open candle 4h berikutnya; konfirmasi menunda entry satu candle tambahan agar tidak memakai close masa depan. Commit simulator `d58c4c3a`.
- `backtest/run_experiments.py` — grid E1–E4, output manifest/CSV/JSON terurut dan konfigurasi versioned. `tests/test_fase3.py` — ATR manual+future invariance, MAE dan konfirmasi. Commit `f1d84a4a`.

Tidak ada perubahan pada `TradingBrain` atau parameter produksi. ATR dipakai sebagai feature murni backtester; jalur live tetap menggunakan feature produksi apa adanya.

## Verifikasi

`venv/bin/python -m pytest -q` → **130 passed, 3 warnings, 74 subtests passed** (26,44 detik). Tidak ada traceback test. Test mencakup ATR anti-lookahead, MAE, konfirmasi candle, dan seluruh suite lama.

## Keterbatasan

Data funding Binance tidak tersedia untuk setiap timestamp/coin; simulator menandai metode per trade dan memakai fallback hanya sesuai kontrak backtester. Regime direkonstruksi dari feature harga BTC historis (proxy untuk input runtime non-harga). Hasil adalah riset dengan notional tetap 100 USDT, bukan proyeksi equity compounding. E3 TP 2×ATR menghasilkan N=0 karena filter produksi RR≥3 menolak RR=2; ini efek kontrak filter, bukan crash.

## Kesimpulan dan usulan (belum diterapkan)

Baseline dan hampir semua varian TUNE masih expectancy negatif. E3 3×ATR/3 hari menjadi kandidat TUNE terbaik secara agregat, tetapi walk-forward tidak stabil (kuartal terakhir negatif). Holdout E3 3×ATR/3 hari memenuhi seluruh kriteria dan dapat diajukan sebagai **USULAN** review pengguna: implementasi terkontrol di backtester/live shadow dahulu, bukan perubahan produksi otomatis. E2 support-distance gagal PF/N holdout. Tidak ada parameter yang diubah di runtime pada fase ini.

Rekomendasi review berikutnya: (1) validasi ulang E3 pemenang dengan periode rolling dan biaya/slippage konservatif, (2) analisis konsentrasi WLD (45,2% profit holdout, masih di bawah batas 50%), (3) uji funding fallback dan kualitas data per coin, (4) jangan mengaktifkan perubahan produksi sebelum observasi paper/shadow dan kriteria risiko disetujui.
