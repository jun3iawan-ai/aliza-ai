# Maintenance Report — Cleanup + Graceful Shutdown

Waktu eksekusi: **2026-07-21 13:51–14:03 WIB**  
Repo: `/opt/aliza-ai`  
Branch akhir: `main`  
Commit patch: `f38ab5546e1b77b57f20fce23e9346b5a4774d8b`  
Push/restart/sudo: **tidak dilakukan**.

## Ringkasan hasil

- Cleanup yang disetujui selesai.
- Disk root turun dari **62%** ke **54%**.
- `.git` turun dari **4,5G** ke **9,8M**; garbage pack menjadi 0 dan `tmp_pack_W9KN2w` hilang.
- 30 cache `__pycache__`, 162 `*.pyc`, dan `.pytest_cache` dibersihkan; setelah full test dibersihkan ulang dan hasil akhir semuanya 0/tidak ada.
- Lima branch fase yang sudah merged dihapus menggunakan `git branch -d`.
- Dari 102 backup Telegram, 88 dihapus dan 14 terbaru dipertahankan.
- Crontab backup jam 02:00 diberi retensi `-mtime +14 -delete`; entry lain identik.
- `backtest/data`, `backtest/results`, `venv`, `data`, `.env`, `logs`, `audit-output`, report fase, dan tiga backup non-Telegram tidak disentuh.
- `.env.market` dibaca lokal dan **tidak mengandung secret/credential**; nilainya tidak ditulis di laporan.
- Patch graceful shutdown selesai, 138 test + 74 subtest lulus, commit sudah fast-forward ke `main`.
- Service produksi belum restart, sehingga proses aktif masih memuat kode lama sampai tindakan user.

# Bagian A — Cleanup

## 1. Disk sebelum dan sesudah

### Sebelum

```text
$ df -h /
Filesystem      Size  Used Avail Use% Mounted on
/dev/vda2        59G   35G   22G  62% /

$ du -sh .git interfaces
4.5G  .git
25M   interfaces
```

### Sesudah

```text
$ df -h /
Filesystem      Size  Used Avail Use% Mounted on
/dev/vda2        59G   31G   27G  54% /

$ du -sh .git interfaces
9.8M  .git
3.9M  interfaces
```

Perubahan terbesar berasal dari repack/prune normal `git gc`: pack 4,11 GiB yang sebagian besar tidak lagi diperlukan menjadi pack 9.536 KiB. Cleanup backup Telegram membebaskan sekitar 21,5 MiB tambahan.

## 2. Cache Python/test

Blok cleanup dijalankan tanpa menyentuh `venv`. Bentuk awal `find ... -delete` untuk `*.pyc` memberi warning bahwa `-delete` mengaktifkan `-depth` sehingga `-prune` tidak efektif. Perintah kemudian dikoreksi menjadi target eksplisit dengan `-exec rm -- {} +`.

Verifikasi akhir setelah full suite:

```text
remaining_pycache=0
remaining_pyc=0
pytest_cache_exists=no
```

Full test memang membuat cache ulang; cache tersebut sudah dibersihkan lagi setelah hasil test dicatat.

## 3. Branch lokal merged

Perintah aktual:

```text
$ git branch -d feat/fase2-backtester feat/fase3-experiments feat/fase4-shadow fix/fase1-signal-integrity fix/fase1d-observability-universe
Deleted branch feat/fase2-backtester (was e9793308).
Deleted branch feat/fase3-experiments (was 53dbc447).
Deleted branch feat/fase4-shadow (was 48403ed7).
Deleted branch fix/fase1-signal-integrity (was 735b3559).
Deleted branch fix/fase1d-observability-universe (was 51681225).
```

Tidak digunakan `-D`. Branch patch baru `fix/graceful-shutdown` tetap ada dan sudah merged/menunjuk commit yang sama dengan `main`.

## 4. Git GC

Precheck:

```text
pgrep -x git: tidak ada output
find .git -type f -name '*.lock': tidak ada output
precheck: no git process, no lock
```

Sebelum:

```text
warning: garbage found: .git/objects/pack/tmp_pack_W9KN2w
count: 540
size: 41336
in-pack: 65001
packs: 3
size-pack: 4315986
prune-packable: 0
garbage: 1
size-garbage: 261632
```

Segera setelah `git gc` standar:

```text
count: 1
size: 4
in-pack: 858
packs: 1
size-pack: 9536
prune-packable: 0
garbage: 0
size-garbage: 0
tmp_pack_W9KN2w=HILANG
```

Kondisi final setelah commit baru:

```text
count: 10
size: 104
in-pack: 858
packs: 1
size-pack: 9536
prune-packable: 0
garbage: 0
size-garbage: 0
```

Tidak digunakan `--aggressive`, `--prune=now`, atau penghapusan pack manual.

## 5. Retensi backup Telegram

Hasil eksekusi:

```text
backup_before=102 backup_deleted=88 backup_kept=14
telegram_backup_count=14 bytes=3708697
```

Empat belas file yang dipertahankan, urut terbaru:

```text
2026-07-21 01:00:01 265794 interfaces/telegram_bot.py.bak.20260721
2026-07-20 01:00:01 265794 interfaces/telegram_bot.py.bak.20260720
2026-07-19 01:00:01 265794 interfaces/telegram_bot.py.bak.20260719
2026-07-18 01:00:01 265794 interfaces/telegram_bot.py.bak.20260718
2026-07-17 01:00:01 265794 interfaces/telegram_bot.py.bak.20260717
2026-07-16 01:00:01 265767 interfaces/telegram_bot.py.bak.20260716
2026-07-15 01:00:02 264245 interfaces/telegram_bot.py.bak.20260715
2026-07-14 01:00:01 264245 interfaces/telegram_bot.py.bak.20260714
2026-07-13 01:00:01 264245 interfaces/telegram_bot.py.bak.20260713
2026-07-12 01:00:01 264245 interfaces/telegram_bot.py.bak.20260712
2026-07-11 01:00:01 264245 interfaces/telegram_bot.py.bak.20260711
2026-07-10 01:00:01 264245 interfaces/telegram_bot.py.bak.20260710
2026-07-09 01:00:01 264245 interfaces/telegram_bot.py.bak.20260709
2026-07-08 01:00:01 264245 interfaces/telegram_bot.py.bak.20260708
```

Tiga backup non-Telegram tetap ada:

```text
36864 data/aliza.db.bak.20260716_154643
10635 engine/market/funding_rate_monitor.py.bak.20260418_080753
3319  interfaces/market_bot.py.bak.20260602
```

## 6. Crontab sebelum dan sesudah

Percobaan substitusi pertama tidak cocok dengan baris target dan berhenti dengan `ABORT: cron entry tidak berubah`; crontab belum berubah pada percobaan itu. Percobaan kedua memvalidasi tepat satu entry dan memasang hasil berikut.

### Sebelum — output lengkap `crontab -l`

```text
# Edit this file to introduce tasks to be run by cron.
# 
# Each task to run has to be defined through a single line
# indicating with different fields when the task will be run
# 
# To define the time you can provide concrete values for
# minute, hour, day of month (dom), month (mon), and day of week (dow)
# or use '*' in these fields (for 'any').
# 
# Notice that tasks will be started based on the cron's system
# daemon's notion of time and timezones.
# 
# Output of the crontab jobs (including errors) is sent through
# email to the user the crontab file belongs to (unless redirected).
# 
# For example, you can run a backup of all your user accounts at 5 a.m every week with:
# 0 5 * * 1 tar -zcf /var/backups/home.tgz /home/
# 
# For more information see the manual pages of crontab(5) and cron(8)
# 
# m h  dom mon dow   command
0 2 * * * /opt/aliza-backups/scripts/backup.sh
*/5 * * * * /home/ubuntu/server-monitor/monitor.sh
# 0 15 * * 1-5 cd /opt/aliza-etpp-agent && ./venv/bin/python -m app.automation.reminder # DIPINDAH KE VM 193
0 19 * * * /opt/aliza-backups/backup_db.sh >> /opt/aliza-backups/backup.log 2>&1
0 2 * * * cp /opt/aliza-ai/interfaces/telegram_bot.py /opt/aliza-ai/interfaces/telegram_bot.py.bak.$(date +\%Y\%m\%d) 2>/dev/null
# 0 20 * * 0 sudo systemctl restart aliza-telegram.service # DIMATIKAN - bot di VM 193
0 23 * * * /opt/gmail-agent/venv/bin/python3 /opt/gmail-agent/auto_scan.py >> /opt/gmail-agent/auto_scan.log 2>&1
0 5 * * * /opt/gmail-agent/venv/bin/python3 /opt/gmail-agent/auto_scan.py >> /opt/gmail-agent/auto_scan.log 2>&1
```

### Sesudah — output lengkap `crontab -l`

```text
# Edit this file to introduce tasks to be run by cron.
# 
# Each task to run has to be defined through a single line
# indicating with different fields when the task will be run
# 
# To define the time you can provide concrete values for
# minute, hour, day of month (dom), month (mon), and day of week (dow)
# or use '*' in these fields (for 'any').
# 
# Notice that tasks will be started based on the cron's system
# daemon's notion of time and timezones.
# 
# Output of the crontab jobs (including errors) is sent through
# email to the user the crontab file belongs to (unless redirected).
# 
# For example, you can run a backup of all your user accounts at 5 a.m every week with:
# 0 5 * * 1 tar -zcf /var/backups/home.tgz /home/
# 
# For more information see the manual pages of crontab(5) and cron(8)
# 
# m h  dom mon dow   command
0 2 * * * /opt/aliza-backups/scripts/backup.sh
*/5 * * * * /home/ubuntu/server-monitor/monitor.sh
# 0 15 * * 1-5 cd /opt/aliza-etpp-agent && ./venv/bin/python -m app.automation.reminder # DIPINDAH KE VM 193
0 19 * * * /opt/aliza-backups/backup_db.sh >> /opt/aliza-backups/backup.log 2>&1
0 2 * * * cp /opt/aliza-ai/interfaces/telegram_bot.py /opt/aliza-ai/interfaces/telegram_bot.py.bak.$(date +\%Y\%m\%d) 2>/dev/null; find /opt/aliza-ai/interfaces -name 'telegram_bot.py.bak.*' -mtime +14 -delete
# 0 20 * * 0 sudo systemctl restart aliza-telegram.service # DIMATIKAN - bot di VM 193
0 23 * * * /opt/gmail-agent/venv/bin/python3 /opt/gmail-agent/auto_scan.py >> /opt/gmail-agent/auto_scan.log 2>&1
0 5 * * * /opt/gmail-agent/venv/bin/python3 /opt/gmail-agent/auto_scan.py >> /opt/gmail-agent/auto_scan.log 2>&1
```

Diff aktual hanya satu baris:

```diff
-0 2 * * * cp /opt/aliza-ai/interfaces/telegram_bot.py /opt/aliza-ai/interfaces/telegram_bot.py.bak.$(date +\%Y\%m\%d) 2>/dev/null
+0 2 * * * cp /opt/aliza-ai/interfaces/telegram_bot.py /opt/aliza-ai/interfaces/telegram_bot.py.bak.$(date +\%Y\%m\%d) 2>/dev/null; find /opt/aliza-ai/interfaces -name 'telegram_bot.py.bak.*' -mtime +14 -delete
```

## 7. Path yang wajib disimpan

Verifikasi sesudah cleanup:

```text
179M  backtest/data
864K  backtest/results
8.2G  venv
108K  data
24M   logs
120K  audit-output
```

Semua tetap ada. `.env`, report fase di root, dan untracked audit sebelumnya juga tidak dihapus.

## 8. Verdict `.env.market`

Pemeriksaan lokal menemukan satu entri:

```text
env_market_entries=1 contains_secret_or_credential=TIDAK
```

**Verdict: tidak mengandung secret/credential.** File tetap tracked dan tidak diubah. Nilai/key aktual sengaja tidak ditulis dalam laporan.

# Bagian B — Fix Graceful Shutdown

## 1. Diagnosis SIGKILL

### Koreksi kondisi unit aktual

Lampiran menyebut default 90 detik, tetapi unit VPS aktual sudah mempunyai **15 detik**:

```text
$ systemctl show aliza-telegram.service -p TimeoutStopUSec -p KillSignal -p SendSIGKILL -p Restart
Restart=always
TimeoutStopUSec=15s
KillSignal=15
SendSIGKILL=yes
```

Unit:

```ini
[Service]
TimeoutStopSec=15
User=ubuntu
WorkingDirectory=/opt/aliza-ai
EnvironmentFile=-/opt/aliza-ai/.env
ExecStart=/opt/aliza-ai/venv/bin/python /opt/aliza-ai/interfaces/telegram_bot.py
Restart=always
RestartSec=5
```

### Insiden 07:38

Timeline journal aktual:

```text
07:38:01 snapshot_job mulai
07:38:05 systemd: Stopping AlizaAI Telegram Bot...
07:38:05–08 snapshot tetap memproses BONE/FARTCOIN/HYPE/ZEREBRO
07:38:06 near_support_checker tetap dijalankan
07:38:11 near_resistance_checker tetap dijalankan
07:38:16 rsi_extreme_checker tetap dijalankan
07:38:20 State 'stop-sigterm' timed out. Killing.
07:38:20 main process dan worker threads dibunuh SIGKILL
```

Output penting:

```text
2026-07-21T07:38:05+0700 systemd[1]: Stopping AlizaAI Telegram Bot...
2026-07-21T07:38:06+0700 ... Running job "near_support_checker ..."
2026-07-21T07:38:11+0700 ... Running job "near_resistance_checker ..."
2026-07-21T07:38:16+0700 ... Running job "rsi_extreme_checker ..."
2026-07-21T07:38:20+0700 systemd[1]: aliza-telegram.service: State 'stop-sigterm' timed out. Killing.
2026-07-21T07:38:20+0700 systemd[1]: ... Main process exited, code=killed, status=9/KILL
```

`snapshot_job` memakai default executor:

```python
loop = asyncio.get_event_loop()
await loop.run_in_executor(None, update_market_snapshot)
```

`update_market_snapshot()` menjalankan request sinkron berurutan dan, ketika coin gagal, `time.sleep(RETRY_DELAY_SEC)` dengan dokumentasi retry 30 detik. Pada insiden pertama, beberapa coin gagal tepat saat SIGTERM, sehingga job blocking dapat melampaui window unit 15 detik.

### Insiden 12:46–12:47

```text
12:46:45 snapshot_job mulai
12:46:50 systemd: Stopping AlizaAI Telegram Bot...
12:46:51 snapshot_job selesai
12:46:53 Scheduler has been shut down
12:47:05 State 'stop-sigterm' timed out. Killing.
12:47:05 main process dan tiga worker/native threads dibunuh SIGKILL
```

Output penting:

```text
2026-07-21T12:46:50+0700 systemd[1]: Stopping AlizaAI Telegram Bot...
2026-07-21T12:46:51+0700 ... Job "snapshot_job ..." executed successfully
2026-07-21T12:46:53+0700 ... Scheduler has been shut down
2026-07-21T12:47:05+0700 systemd[1]: aliza-telegram.service: State 'stop-sigterm' timed out. Killing.
```

Ini membuktikan akar masalah bukan hanya satu snapshot lambat: walau scheduler selesai, interpreter/cleanup masih tertahan sampai batas systemd. Systemd mencatat beberapa thread Python dan `jemalloc_bg_thd` di cgroup saat SIGKILL.

### Handler lama dan library

Handler lama:

```python
def _handle_sigterm(signum, frame):
    logging.info("SIGTERM received — shutting down gracefully")
    sys.exit(0)
```

Tidak ada log `SIGTERM received` pada dua jendela insiden. `python-telegram-bot 22.6` memasang handler event-loop miliknya sendiri ketika `run_polling()` dipanggil dengan default `stop_signals`. Dengan demikian handler sinkron lokal tidak menjadi orkestrator shutdown yang andal.

Source library aktual juga menunjukkan `Application.stop()` memanggil `JobQueue.stop()`, dan `JobQueue.stop(wait=True)` mengumpulkan pending futures sebelum scheduler shutdown. Job executor sinkron yang blocking dapat mengonsumsi seluruh `TimeoutStopSec=15`.

Pencarian tidak menemukan persistent custom `requests.Session`, `aiohttp.ClientSession`, atau websocket di jalur bot. Request market memakai one-shot `requests.get/post` dengan timeout; HTTP client Telegram ditutup oleh `Application.shutdown()`.

**Akar masalah:** kombinasi pending job/default executor blocking, shutdown JobQueue yang menunggu future, kemungkinan worker/native thread yang masih hidup, serta handler lokal yang bertabrakan dengan signal handling `run_polling`. Bukti kuat langsung tersedia untuk pending job pada insiden pertama dan lingering process setelah scheduler shutdown pada insiden kedua.

## 2. Patch minimal

Commit:

```text
f38ab5546e1b77b57f20fce23e9346b5a4774d8b
f38ab55 fix: bound telegram graceful shutdown
```

Stat:

```text
.gitignore                 |  18 ++++++++++++++++++
core/graceful_shutdown.py  | 104 ++++++++++++++++++++++++++++++++++++++++++
interfaces/telegram_bot.py |  27 ++++++-----
tests/test_shutdown.py     | 109 +++++++++++++++++++++++++++++++++++++++++++++
4 files changed, 248 insertions(+), 10 deletions(-)
```

Perubahan runtime:

1. `GracefulShutdownController` memasang handler SIGTERM tunggal dan idempotent.
2. Scheduler diminta `shutdown(wait=False)` agar tidak menerima job baru dan tidak menunggu blocking future.
3. `Application.stop_running()` meminta PTB menjalankan urutan updater stop, application stop, shutdown HTTP client, dan callback `post_shutdown`.
4. `run_polling(stop_signals=None)` mencegah PTB menimpa handler controller.
5. Deadline watchdog daemon 8 detik menjamin proses keluar sebelum unit systemd mencapai 15 detik.
6. Setelah cleanup PTB selesai, proses keluar eksplisit agar thread non-daemon/native yang tertinggal tidak menahan systemd.
7. Logika sinyal, shadow, filter, dan dispatch tidak diubah.

Wiring aktual:

```text
core/graceful_shutdown.py:58-60 scheduler.shutdown(wait=False)
core/graceful_shutdown.py:64-69 watchdog daemon
core/graceful_shutdown.py:71-72 application.stop_running()
core/graceful_shutdown.py:82-87 exit setelah cleanup
core/graceful_shutdown.py:93-104 deadline 8 detik
interfaces/telegram_bot.py:6969 .post_shutdown(_post_shutdown)
interfaces/telegram_bot.py:6972 timeout_seconds=8.0
interfaces/telegram_bot.py:7165 install_sigterm_handler()
interfaces/telegram_bot.py:7171 run_polling(stop_signals=None)
interfaces/telegram_bot.py:7173 finish_process()
```

Comment usang diperbaiki:

```text
# Auto alert: score default ≥70 (valid 0–100), rr≥2.5, confidence≥65.
```

Tambahan `.gitignore`:

```gitignore
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/
*.egg-info/
build/
dist/
*.db-wal
*.db-shm
*.sqlite-wal
*.sqlite-shm
```

## 3. Test

Targeted:

```text
$ venv/bin/python -m pytest -q tests/test_shutdown.py
.....                                                                    [100%]
5 passed in 0.08s
```

Test mencakup:

- simulasi SIGTERM menghentikan scheduler dengan `wait=False`;
- stop application dipanggil;
- repeated SIGTERM idempotent;
- deadline fallback memaksa exit dalam batas;
- cleanup selesai keluar tanpa menunggu thread;
- callback `post_shutdown` menandai cleanup application selesai.

Full suite final:

```text
$ venv/bin/python -m pytest -q
.......................................................................... [ 53%]
................................................................         [100%]
138 passed, 3 warnings, 74 subtests passed in 15.60s
```

Tiga warning adalah `DeprecationWarning` SWIG (`SwigPyPacked`, `SwigPyObject`, `swigvarlink`); tidak ada failure.

Compile check:

```text
$ venv/bin/python -m py_compile core/graceful_shutdown.py interfaces/telegram_bot.py
(exit 0, tidak ada output)
```

## 4. Merge dan Git akhir

Branch dibuat dari `main`, patch di-commit, lalu di-merge dengan fast-forward:

```text
$ git merge --ff-only fix/graceful-shutdown
Updating 5ef5a9f..f38ab55
Fast-forward
4 files changed, 248 insertions(+), 10 deletions(-)
```

State:

```text
f38ab55 (HEAD -> main, fix/graceful-shutdown) fix: bound telegram graceful shutdown
$ git rev-list --left-right --count origin/main...HEAD
0  14
```

Lokal kini **14 commit di depan origin**: 13 commit lama + 1 commit maintenance. Tidak ada push.

File untracked audit/report lama tetap ada dan sengaja tidak ikut commit. `MAINTENANCE_REPORT.md` juga dibuat setelah merge dan tidak dimasukkan ke commit patch.

## 5. Rekomendasi unit systemd

Tidak perlu menurunkan atau menaikkan timeout untuk mengaktifkan fix. Unit aktual sudah `TimeoutStopSec=15`, sedangkan deadline aplikasi 8 detik, menyisakan margin sekitar 7 detik untuk systemd.

Konfigurasi yang direkomendasikan tetap:

```ini
[Service]
TimeoutStopSec=15
KillSignal=SIGTERM
SendSIGKILL=yes
```

Verifikasi produksi harus membuktikan restart selesai di bawah 10 detik dan journal tidak lagi memuat `State 'stop-sigterm' timed out`. Patch belum aktif pada proses PID 2230674 karena service tidak direstart dalam pekerjaan ini.

# TINDAKAN USER

1. Cegah dua bot enabled saat reboot:

   ```bash
   sudo systemctl disable aliza-bot
   ```

2. Aktifkan patch dan verifikasi dua siklus shutdown bersih:

   ```bash
   sudo systemctl restart aliza-telegram
   systemctl status aliza-telegram --no-pager
   sudo systemctl restart aliza-telegram
   journalctl -u aliza-telegram --since "10 minutes ago" --no-pager
   ```

   Kedua restart harus selesai **di bawah 10 detik**, tanpa timeout unit aktual 15 detik, tanpa `SIGKILL`, dan dengan log `SIGTERM received — graceful shutdown requested` serta `Graceful shutdown completed`.

3. Setelah verifikasi service, push 14 commit lokal:

   ```bash
   git push origin main
   ```

Tidak ada secret/token yang ditulis dalam laporan.
