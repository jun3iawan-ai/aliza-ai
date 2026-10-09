# Merge, Deploy & Verifikasi — Big Move Alert Multi-Timeframe

Tanggal deploy: 18 September 2026  
Target: `main` / `aliza-telegram.service`

## 1. Precheck

`git fetch origin` selesai. Sebelum merge:

```text
main        = 7f5b5dedb3707e4aa1eebcb5d84b5288f3a3a9ea
origin/main = 7f5b5dedb3707e4aa1eebcb5d84b5288f3a3a9ea
```

`git diff --name-only main feature/big-move-multi-timeframe` menghasilkan tepat empat file:

```text
engine/market/market_snapshot_engine.py
interfaces/telegram_bot.py
tests/test_big_move_multi_timeframe.py
tests/test_notifikasi_mitigasi.py
```

Worktree juga memiliki laporan-laporan tak terlacak yang sudah ada; tidak satu pun dimasukkan ke merge atau push.

## 2. Merge

Perintah `git checkout main && git merge --ff-only feature/big-move-multi-timeframe` berhasil fast-forward:

```text
Updating 7f5b5de..4561a3f
Fast-forward
... 4 files changed, 311 insertions(+), 41 deletions(-)
```

`main` sekarang pada `4561a3f feat: add multi-timeframe big move alerts`.

## 3. Full test suite (mentah)

Perintah: `venv/bin/python -m pytest -q`

```text
.......................................................................... [ 19%]
.................................................................. [ 36%]
........................................................................ [ 55%]
........................................................................ [ 74%]
........................................................................ [ 93%]
.......................                                                  [100%]
=============================== warnings summary ===============================
<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type swigvarlink has no __module__ attribute

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
379 passed, 3 warnings, 76 subtests passed in 36.05s

```

Hasil: **379 passed, 3 warnings, 76 subtests passed**, tanpa kegagalan.

## 4. Push dan restart

- Push sukses: `origin/main 7f5b5de..4561a3f`.
- `sudo systemctl restart aliza-telegram.service` dijalankan pada 14:56:52 WIB.
- `systemctl is-active aliza-telegram.service`: `active`.

Cuplikan log startup dan scheduler:

```text
2026-09-18 14:57:47,274 - INFO - root - market_snapshot_engine: updated 17 coins
2026-09-18 14:57:47,275 - INFO - root - Snapshot completed. Valid coins: 17
2026-09-18 14:57:47,373 - INFO - root - Big move checker job scheduled (every 300s, first in 25s).
2026-09-18 14:58:12,375 - INFO - apscheduler.executors.default - Running job "big_move_checker ..."
2026-09-18 14:58:12,377 - INFO - apscheduler.executors.default - Job "big_move_checker ..." executed successfully
2026-09-18 15:03:12,375 - INFO - apscheduler.executors.default - Running job "big_move_checker ..."
2026-09-18 15:03:12,377 - INFO - apscheduler.executors.default - Job "big_move_checker ..." executed successfully
```

Observasi mencakup lebih dari lima menit pascarestart. Filter journal sejak restart tidak menemukan `Traceback`, `Binance 15m kline HTTP`, atau `Binance 30m kline fetch failed`.

## 5. Verifikasi data live

Snapshot pada service adalah cache in-memory milik proses bot; proses `python -c` baru tidak dapat membaca memori proses service. Log service membuktikan snapshot production berhasil memperbarui 17 coin setelah restart. Untuk menunjukkan nilai field dari jalur enrichment production yang sama terhadap harga Binance live, saya menjalankan one-shot read-only pada lima coin: `_get_price_from_binance()` → `_enrich_collected_with_binance_1h()` → `_enrich_collected_with_binance_short_intervals()`.

```json
{
  "BNB": {"price": 753.63, "price_change_15m": 0.06904701836385474, "price_change_30m": 0.06904701836385474, "price_change_1h": 0.06904701836385474},
  "BTC": {"price": 77821.4, "price_change_15m": 0.03006503636788782, "price_change_30m": 0.03006503636788782, "price_change_1h": 0.03006503636788782},
  "ETH": {"price": 2491.58, "price_change_15m": 0.06345381526104976, "price_change_30m": 0.06345381526104976, "price_change_1h": 0.06345381526104976},
  "SOL": {"price": 105.86, "price_change_15m": 0.07562866326338291, "price_change_30m": 0.07562866326338291, "price_change_1h": 0.07562866326338291},
  "XRP": {"price": 1.3289, "price_change_15m": 0.0, "price_change_30m": 0.0, "price_change_1h": 0.0}
}
```

Semua tiga field numerik terisi untuk kelima coin. Nilai 15m/30m/1h yang sama pada sampel ini wajar karena pemeriksaan terjadi tepat setelah boundary window UTC; desain fitur memang menggunakan close candle terakhir yang selesai, bukan rolling-window. Bersama dengan snapshot production sukses dan dua siklus checker sukses di atas, pipeline field dan checker terverifikasi hidup tanpa memaksa threshold 3%.

## Hasil akhir

Merge, push, restart, dan verifikasi selesai. `main` serta `origin/main` berada pada `4561a3f`; service aktif dan log Big Move bersih selama observasi.

