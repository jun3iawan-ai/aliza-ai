# FASE2_REPORT — Backtester Event-Driven

Tanggal: 21 Juli 2026  
Branch: `feat/fase2-backtester`  
HEAD: `218fb1c6b422d7bf294b016df41e771c388e7396`  
Parameter strategi, jalur live, service, dan `.env` tidak diubah.

## Commit

- `c148f306` — refactor feature murni bersama runtime/backtester.
- `f418872e` — data loader Binance, costs, simulator, metrics, CLI.
- `360564de` — test Fase 2.
- `218fb1c6` — optimasi RSI stream dengan paritas matematis.

## Perubahan

- `engine/market/features.py`: fungsi murni moving average, Wilder RSI, support/resistance, trend, alignment, dan `compute_features()`. `calculate_rsi_series()` mempertahankan rekursi Wilder untuk simulasi cepat.
- `engine/market/market_analyzer.py`: runtime memanggil `compute_features()`; output indikator dan alignment tetap berasal dari jalur bersama.
- `backtest/data_loader.py`: cache CSV lokal, pagination Binance 4h/1d/5m/1h, funding history Binance, retry/backoff+jitter untuk 418/429/5xx.
- `backtest/simulator.py`: event loop 4h, feature sampai candle tertutup, `TradingBrain.analyze()` langsung, entry open candle 4h berikutnya, satu posisi/coin, TP1/SL, same-bar konservatif LOSS, time-stop 7 hari.
- `backtest/costs.py`: fee 0,1%/sisi, slippage 0,05%/sisi, funding short historis atau fallback 0,01%/8 jam.
- `backtest/metrics.py`: expectancy, profit factor, winrate Wilson 95%, avg win/loss, drawdown seri, median durasi, distribusi PnL, grouping dan kuartal.
- `backtest/run_backtest.py`: CLI, config/hash commit, dua varian `production_filters` dan `no_rr_conf_filters`, hasil versioned.
- `.gitignore`: cache data mentah dan hasil run tidak dilacak ke Git.
- `tests/test_fase2.py`: 8 test integritas.

## Verifikasi

```
venv/bin/python -m pytest -q
126 passed, 3 warnings, 74 subtests passed in 14.75s
```

Test mencakup paritas feature, anti-lookahead, entry next-open, same-bar TP/SL, short outcome, biaya/funding, reproduksibilitas, Wilson interval, dan RSI stream. Smoke CLI tanpa data juga berhasil menghasilkan artefak kosong deterministik.

## Dataset baseline

Cache Binance di `backtest/data/` berisi 2 tahun + warm-up 60 hari untuk 11 coin wajib: BTC, ETH, BNB, SOL, XRP, ADA, SUI, ARB, PEPE, WLD, TAO. Kline 4h dan 1d tersedia. Kline 5m tidak diunduh massal; simulator memakai fallback 1h dan setiap trade mencatat `resolution=1h`. Funding history tidak tersedia di cache baseline sehingga short memakai `fallback_0.01pct_8h`.

Hasil disimpan di `backtest/results/20260721T1038Z/` (CSV mentah/hasil di-ignore Git).

## Keterbatasan

- Regime direkonstruksi dengan `detect_market_regime()` dari feature BTC historis (trend/RSI); whale/fear-greed/funding lama tidak tersedia sehingga tidak direkonstruksi sebagai data live.
- Filter RR/confidence diterapkan persis pada output TradingBrain; varian tanpa filter hanya pembanding berlabel.
- Position sizing notional tetap 100 USDT; tidak ada compounding.
- Cache 1h membuat baseline konservatif dalam resolusi waktu yang lebih kasar daripada 5m. Angka tidak boleh dibandingkan langsung dengan tracker live tanpa menyamakan resolusi dan sumber funding.
- Sinyal yang masih terbuka pada akhir periode dicatat `EXPIRED`/end-of-period; metrik win/loss tetap transparan karena `n` mencakup outcome tersebut.
