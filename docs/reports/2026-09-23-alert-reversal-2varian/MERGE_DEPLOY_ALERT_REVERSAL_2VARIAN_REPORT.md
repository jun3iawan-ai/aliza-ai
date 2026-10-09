# Merge, Deploy & Verifikasi — Alert Reversal Tren 2 Varian

Tanggal deploy: 24 September 2026 (WIB)  
Branch sumber: `feature/trend-reversal-alert`  
Commit deployed: `2c82301a66b6dd1ec42f304089f84424f3a58cf2` (`feat: add per-coin trend reversal alerts`)

## 1. Precheck

`git fetch origin` selesai. Verifikasi commit menghasilkan:

```text
local_main=4561a3fccfd1ae30c978c7738d4c7845d208fb88
origin_main=4561a3fccfd1ae30c978c7738d4c7845d208fb88
feature=2c82301a66b6dd1ec42f304089f84424f3a58cf2
expected=4561a3fccfd1ae30c978c7738d4c7845d208fb88
```

Jadi `main` lokal dan `origin/main` keduanya tepat di baseline `4561a3f` sebelum merge. Output `git diff --name-only main feature/trend-reversal-alert` persis:

```text
interfaces/telegram_bot.py
tests/test_trend_reversal_alert.py
```

Feature sebelumnya belum memiliki commit. Satu commit dibuat hanya dari dua file di atas; laporan-laporan untracked yang sudah ada tidak dimasukkan.

## 2. Merge fast-forward

Perintah `git checkout main && git merge --ff-only feature/trend-reversal-alert` berhasil:

```text
Switched to branch 'main'
Your branch is up to date with 'origin/main'.
Updating 4561a3f..2c82301
Fast-forward
 interfaces/telegram_bot.py         | 141 ++++++++++++++++++++++++++
 tests/test_trend_reversal_alert.py | 199 +++++++++++++++++++++++++++++++++++++
 2 files changed, 340 insertions(+)
 create mode 100644 tests/test_trend_reversal_alert.py
```

Tidak ada merge commit dan tidak ada konflik.

## 3. Full test suite setelah merge

Perintah yang dijalankan dari `main`:

```text
venv/bin/python -m pytest -q 2>&1 | tee /tmp/pytest_main_after_trend_reversal_deploy.txt
```

Output mentah lengkap:

```text
.......................................................................... [ 18%]
.................................................................. [ 35%]
........................................................................ [ 54%]
........................................................................ [ 72%]
........................................................................ [ 91%]
..................................                                       [100%]
=============================== warnings summary ===============================
<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type swigvarlink has no __module__ attribute

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
390 passed, 3 warnings, 76 subtests passed in 37.25s
```

Hasil: 390 passed, 0 failed.

## 4. Push dan restart

`git push origin main` berhasil dan remote telah diverifikasi:

```text
To https://github.com/jun3iawan-ai/aliza-ai.git
   4561a3f..2c82301  main -> main
2c82301a66b6dd1ec42f304089f84424f3a58cf2
2c82301a66b6dd1ec42f304089f84424f3a58cf2	refs/heads/main
```

`sudo systemctl restart aliza-telegram.service` dijalankan. `systemctl is-active aliza-telegram.service` mengembalikan:

```text
active
```

Restart terjadi pada 13:24:48 WIB. Log dipantau hingga 13:31:44 WIB, yaitu 6 menit 56 detik pascarestart.

## 5. Verifikasi live: bootstrap pertama

### Scheduler dan eksekusi

Cuplikan startup menunjukkan job terdaftar dengan konfigurasi yang diminta:

```text
2026-09-24T13:25:54+0700 ... INFO - root - Trend reversal checker job scheduled (every 300s, first in 210s).
2026-09-24T13:25:57+0700 ... INFO - apscheduler.scheduler - Added job "trend_reversal_checker" to job store "default"
```

Snapshot terakhir sebelum checker selesai diperbarui pada 13:29:05 WIB. Kemudian eksekusi bootstrap pertama terjadi pada 13:29:24 WIB dan selesai sukses:

```text
2026-09-24T13:28:59+0700 ... INFO - apscheduler.executors.default - Running job "snapshot_job ..." (scheduled at 2026-09-24 06:28:59.200473+00:00)
2026-09-24T13:29:05+0700 ... INFO - root - Market snapshot updated
2026-09-24T13:29:05+0700 ... INFO - apscheduler.executors.default - Job "snapshot_job ..." executed successfully
2026-09-24T13:29:24+0700 ... INFO - apscheduler.executors.default - Running job "trend_reversal_checker (trigger: interval[0:05:00], next run at: 2026-09-24 06:34:24 UTC)" (scheduled at 2026-09-24 06:29:24.209433+00:00)
2026-09-24T13:29:24+0700 ... INFO - apscheduler.executors.default - Job "trend_reversal_checker (trigger: interval[0:05:00], next run at: 2026-09-24 06:34:24 UTC)" executed successfully
```

Tidak ada `trend_reversal_checker:` error, `Traceback`, atau exception dari checker pada rentang observasi. Tidak ada `ALERT DISPATCHED` pada rentang eksekusi checker 13:29:24. Durasi run sekitar 2 ms dan log hanya memuat start/sukses, konsisten dengan bootstrap senyap tanpa dispatch.

### State tersimpan

Isi penuh `data/alert_cooldown_state.json` setelah bootstrap:

```json
{"cooldown:volume_spike": {"SOL": 1790231049.8483274}, "drawdown_breaker": {"active": true}, "breakout_level": {"ETH": 2666.792, "BNB": 758.5333333333333, "SOL": 114.205}, "cooldown:breakout": {"ETH": 1790231184.3607073, "BNB": 1790231184.5108242, "SOL": 1790231184.656041}, "rate_limit_sent": {"2026092406": 3}, "market_context_alert": {"status": "Bullish"}, "trend_reversal_state": {"XAUT": "BEARISH"}}
```

Namespace `trend_reversal_state` ada dan berisi satu key: `XAUT: BEARISH`. Jumlah satu adalah wajar: checker hanya melakukan bootstrap untuk alignment `STRONG_BULLISH` atau `STRONG_BEARISH`; coin dengan `PARTIAL`, `MIXED`, atau `UNKNOWN` tidak ditulis.

### Perbandingan state dengan snapshot yang dipakai checker

Tidak ada file snapshot di disk: `market_snapshot_engine` menyimpan snapshot service di memori proses. Karena itu snapshot persis yang dibaca proses service tidak dapat dibuka kembali dari shell tanpa menambah instrumentasi atau memodifikasi service.

Namun hubungan dengan snapshot bootstrap dapat dibuktikan langsung dari urutan log dan kode yang dideploy:

1. `snapshot_job` sukses memperbarui snapshot pada 13:29:05 WIB, 19 detik sebelum checker berjalan.
2. Pada bootstrap, `trend_reversal_checker` hanya menulis `ngov.set_value("trend_reversal_state", coin, current_direction)` bila `current_direction` berasal dari `_strong_alignment_direction(alignment)`.
3. Mappingnya adalah `STRONG_BULLISH -> BULLISH` dan `STRONG_BEARISH -> BEARISH`.

Maka entry `XAUT: BEARISH` adalah bukti bahwa snapshot live yang benar-benar dikonsumsi checker pada 13:29:24 memiliki `XAUT.trend_alignment == STRONG_BEARISH`; nilainya konsisten tepat dengan state. Tidak ada key state kedua/ketiga untuk dibandingkan karena hanya XAUT yang strong pada snapshot bootstrap tersebut.

## Kesimpulan

Alert Reversal Tren 2 Varian telah di-fast-forward ke `main`, dipush ke `origin/main`, dan service production telah direstart dalam keadaan `active`. Suite penuh lulus 390 passed tanpa kegagalan. Scheduler menjalankan bootstrap pertama sesuai `first=210`, menyimpan baseline XAUT yang valid, dan tidak mengirim alert reversal pada bootstrap itu.
