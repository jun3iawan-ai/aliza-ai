# 04 — Risk Management dan Winrate

> **Status: SUPERSEDED.** Snapshot pada 2026-07-21. Kondisi sistem terkini ada di `docs/README.md` dan report Fase 1–4 (`docs/reports/` — lihat Bagian 3). Jangan jadikan dokumen ini sebagai acuan status aktif.

## Position sizing

Implementasi utama berada di `engine/position_sizer.py:calculate_position_size()` dan `calculate_position_size_for_user()`.

Rumus fixed-fractional:

```text
risk_amount = balance × risk_pct / 100
stop_distance = abs(entry - stop_loss)
quantity_by_risk = risk_amount / stop_distance
max_notional = balance × max_position_allocation_pct / 100
quantity = min(quantity_by_risk, max_notional / entry)
```

Default dari environment/kode:

- risiko per trade: 2%;
- maksimum alokasi satu posisi: 30% portfolio;
- maksimum total risk aktif: 6% portfolio.

Saldo dipilih oleh `engine/user_config.py:get_portfolio_balance()` dengan prioritas mode auto dari akun Binance Spot USDT, saldo manual database, lalu `ACCOUNT_BALANCE`. Private Binance yang ditemukan hanya signed `GET /api/v3/account`; tidak ada endpoint order.

Total risk aktif dihitung dari `engine/state_store.py`/trade lokal. Bila posisi lama tidak punya quantity, fungsi mengasumsikan risiko 2% balance per trade. Position size ini hanya saran dalam sinyal; tidak ada eksekusi exchange.

Ada implementasi kedua di `engine/portfolio/position_sizer_legacy.py` dengan default balance 10.000 dan risk 1%, masih dipakai `engine/portfolio/portfolio_ai_engine.py:prepare_entry()`. Fragmentasi ini dapat menghasilkan ukuran berbeda untuk setup sama.

## Validasi risiko

`engine/risk_manager.py:validate_proposed_trade()` menerapkan:

- jarak entry–SL maksimum 2%;
- RR minimum 2;
- maksimum tiga trade lokal berstatus `OPEN`.

RR dihitung dengan nilai absolut. Fungsi tidak memvalidasi invariant arah:

- long seharusnya `SL < entry < TP`;
- short seharusnya `TP < entry < SL`.

Karena hanya memakai `abs`, level di sisi yang salah masih dapat lolos bila jarak dan RR memenuhi. Bila pembacaan jumlah open trade gagal, kode mengembalikan nol dan bersifat fail-open.

`engine/portfolio/risk_manager.py:RiskManager` adalah guard lain dengan konstanta max posisi 3, max portfolio risk 5%, risk per trade 1%, tetapi pada jalur aktifnya hanya batas jumlah posisi yang benar-benar dicek. `drawdown_protector.py:can_open_trade()` memblokir setelah tiga loss beruntun dari JSON legacy.

## Stop loss, take profit, dan risk:reward

| Setup/jalur | Stop loss | TP1 | TP2/RR |
|---|---|---|---|
| Oversold Bounce | 1,5% di bawah entry | resistance | resistance +2%; TP dicap maks 8% |
| Pullback Long | support −1% | resistance | resistance +2%; TP dicap maks 8% |
| Overbought Rejection | resistance +1% | support | support −2%; TP dicap maks 8% |
| Pullback Short | resistance +1% | support | support −2%; TP dicap maks 8% |
| Laporan LLM | dipaksa dalam 5–8%; default rewrite 6% | bila RR<2 ditulis ulang menjadi 2R | level generatif, bukan order |

`TradingBrain` dapat membuat kandidat dengan berbagai RR, tetapi `scan_for_signals()` hanya mengirim kandidat RR `>=3`, sedangkan gateway risk manager menerima RR `>=2`. Opportunity scanner memakai RR `>=1,3`, dan auto-alert memerlukan `>=2,5` tetapi saat ini terhalang bug score. Tidak ada satu kebijakan RR global.

Tidak ada trailing stop, break-even otomatis, partial close nyata atau protective order. Label take-profit 50% pada teks LLM hanya instruksi kepada user.

## Tracking hasil sinyal

Lokasi: `engine/trading/signal_tracker.py` dan tabel SQLite `data/aliza.db:signal_tracking`.

- `record_signal()` menulis coin, setup, entry, SL, TP dan status `OPEN`.
- `check_open_signals()` mengambil harga terbaru, menandai `WIN` bila target terlewati atau `LOSS` bila stop terlewati; signal lebih dari 7 hari menjadi expired menurut logika kode.
- `get_signal_stats()` menghitung winrate sebagai `WIN / (WIN + LOSS) × 100`, rata-rata PnL dan agregat coin.
- Scheduler menjalankan pemeriksaan outcome setiap 10 menit dan juga job lain setiap 30 menit.

Snapshot data saat audit:

- total 10 sinyal tracking;
- 5 `LOSS`, 5 `OPEN`, 0 `WIN`;
- winrate realized saat ini: **0%** (0 dari 5 outcome selesai);
- rentang pencatatan: 16–21 Juli 2026;
- loss: tiga `OVERSOLD BOUNCE` (rata-rata sekitar −1,17%), satu `PULLBACK LONG` (−3,55%), satu berlabel `SHORT` (−5,45%);
- open: tiga `LONG` dan dua `SPOT` dari parser laporan.

Angka ini tidak layak dianggap estimasi winrate strategi: sampel hanya lima outcome, campuran engine deterministik dan parser LLM, dan memiliki bug arah/tracking.

### Bug tracker yang merusak metrik

`check_open_signals()` menganggap short hanya bila `setup.upper() == "SHORT"`. Label nyata seperti `PULLBACK SHORT` dan `OVERBOUGHT REJECTION` diperlakukan sebagai long. Ini dapat membalik kriteria TP/SL dan PnL.

Tracker hanya membaca harga titik saat polling, bukan high/low candle. Jika TP dan SL sama-sama tersentuh di antara dua polling, urutan kejadian tidak diketahui. Fee, spread, slippage, funding dan latency tidak dimasukkan. Sinyal juga dicatat sebelum gateway mengonfirmasi dispatch, sehingga statistik bisa berisi signal yang tidak pernah diterima user.

## Trade history dan learning

`data/trade_history.json` dipakai oleh:

- `engine/learning/strategy_performance.py:get_strategy_winrate()`;
- `engine/learning/confidence_adjuster.py:adjust_confidence()`;
- `engine/portfolio/drawdown_protector.py:can_open_trade()`;
- `engine/analytics/performance_analyzer.py`.

File itu berisi dua trade closed sampel (satu win, satu loss) bertimestamp 13 Maret 2025 serta satu open, dan terakhir termodifikasi Maret 2026. Endpoint `/entry` dan `/close` menulis SQLite melalui `trade_manager.py`, bukan JSON tersebut. Jadi learning/drawdown tidak mengonsumsi tracking signal aktual Juli.

Confidence adjustment sudah aktif pada sampel `n>=1`: winrate >65% memberi +5 dan <40% memberi −10. Threshold sampel yang sangat rendah menimbulkan overfitting/noise. `performance_analyzer.py` menghitung profit factor dari field `rr`; `record_trade_close()` menyimpan RR input apa adanya, sehingga bila loss tetap diberi RR positif, profit factor salah secara semantik.

Tabel SQLite `trades` memiliki 14 baris, semuanya `CLOSED`, pada 11–13 Maret 2026. Tidak ada bukti bahwa ini hasil eksekusi exchange; operasi di kode hanya pencatatan lokal.

## Backtesting

Tidak ditemukan framework, skrip, fixture data, hasil, equity curve, walk-forward, atau laporan backtest. Pencarian file/fungsi terkait backtest tidak menemukan implementasi nyata. Dokumen audit lama juga menyatakan tidak ada backtesting.

Hasil backtest terakhir: **TIDAK ADA/TIDAK PASTI**. Database trade dan signal tracking bukan backtest terverifikasi dan tidak boleh diperlakukan sebagai hasil backtest.

## Batas risiko lain

| Kontrol | Status |
|---|---|
| Maks posisi bersamaan | 3 pada dua risk manager |
| Maks risiko per trade | 2% pada engine utama; 1% pada portfolio legacy |
| Maks total risk | 6% pada position sizer utama |
| Maks alokasi posisi | 30% portfolio |
| Max drawdown | Tidak ada persentase drawdown/equity stop yang nyata |
| Cooldown setelah loss | Tidak ditemukan cooldown berbasis loss |
| Loss streak | Blokir setelah 3 loss berturut-turut, tetapi memakai JSON legacy yang tidak sinkron |
| Cooldown signal | Dedup 15 menit; alert khusus 4–8 jam |
| Batas leverage | Hanya instruksi prompt maksimum 5x; tidak dienforce pada exchange |
| Macro block | Event high-impact dalam 4 jam; failure fail-open |
| Kill switch | Tidak ditemukan kill switch portfolio/exchange |

## Penilaian

Risk management saat ini bersifat advisory dan terpecah. Rumus sizing cukup standar, tetapi tidak bisa melindungi modal tanpa order stop nyata. Statistik winrate saat ini tidak dapat dipakai untuk mengoptimasi strategi sampai bug arah, provenance sinyal, data intrabar, biaya dan pemisahan jalur deterministic/LLM diperbaiki.
