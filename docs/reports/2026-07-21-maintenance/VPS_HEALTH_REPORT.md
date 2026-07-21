# VPS Health Report — Aliza AI

Waktu audit: **2026-07-21 13:11–13:15 WIB**  
Host: `VM-6-46-ubuntu`  
Repo: `/opt/aliza-ai`, branch `main`  
Sifat audit: read-only terhadap runtime; tidak ada restart, perubahan `.env`, penghapusan, atau commit.

## Kesimpulan

**Status: PERLU PERHATIAN.** Resource VPS masih cukup dan bot utama sedang berjalan, tetapi:

1. `aliza-telegram.service` mengalami dua stop-timeout yang berakhir SIGKILL pada 21 Juli; saat audit kembali `active (running)`, `NRestarts=0`.
2. `SHADOW_E3_ENABLED=true` dan `SHADOW_E3_DISPATCH=true`, tetapi DB masih mempunyai **0 row `shadow_e3`**. Log terbaru membuktikan job shadow dieksekusi, tetapi siklus itu menghasilkan `candidates=0` dan `recorded=0`. Jadi eksekusi shadow mengalir, data shadow belum mengalir ke DB/dispatch.
3. `aliza-bot.service` dan `aliza-telegram.service` sama-sama enabled, walau hanya `aliza-telegram` yang aktif. Tidak ada scheduler ganda yang aktif saat audit, tetapi ada risiko dua bot start saat reboot jika unit lama masih valid.
4. Lokal `main` **13 commit di depan** `origin/main`; bukan kondisi sinkron.
5. Cron membuat backup `telegram_bot.py` setiap hari tanpa retensi; sudah ada 102 backup berukuran total 25.230.622 byte.

## 1. Resource

Perintah dan output aktual:

```text
$ date --iso-8601=seconds; hostname; df -h; free -h; uptime; nproc
2026-07-21T13:11:20+07:00
VM-6-46-ubuntu
Filesystem      Size  Used Avail Use% Mounted on
tmpfs           372M  1.2M  371M   1% /run
/dev/vda2        59G   35G   22G  62% /
tmpfs           1.9G   56K  1.9G   1% /dev/shm
tmpfs           5.0M     0  5.0M   0% /run/lock
tmpfs           372M  4.0K  372M   1% /run/user/1000
               total        used        free      shared  buff/cache   available
Mem:           3.6Gi       1.5Gi       725Mi       5.0Mi       1.4Gi       1.9Gi
Swap:          4.0Gi       990Mi       3.0Gi
 13:11:20 up 135 days, 15:06,  0 users,  load average: 0.06, 0.03, 0.12
2
```

- Tidak ada partisi di atas 80%; root 62%.
- RAM available 1,9 GiB; swap terpakai 990 MiB dari 4,0 GiB.
- Load 0,06/0,03/0,12 pada 2 CPU sangat rendah.

## 2. Service Aliza

Unit yang sedang loaded menurut `systemctl list-units 'aliza*' --all`:

```text
UNIT                   LOAD   ACTIVE   SUB
aliza-api.service      loaded inactive dead
aliza-bot.service      loaded inactive dead
aliza-telegram.service loaded active   running
```

Seluruh unit file Aliza dan kondisi aktual dari `systemctl show`/`systemctl status`:

| Unit | Enabled state | Active state | PID / start | NRestarts | Catatan |
|---|---:|---:|---|---:|---|
| `aliza-api-staging.service` | disabled | inactive/dead | 0 / n/a | 0 | Repo lain |
| `aliza-api.service` | disabled | inactive/dead | 0 / 2026-04-20 12:47 | 0 | Mati sejak 2026-05-05 |
| `aliza-assistant.service` | masked | inactive/dead | 0 / n/a | 0 | Jangan diaktifkan tanpa review |
| `aliza-bot-staging.service` | disabled | inactive/dead | 0 / n/a | 0 | Repo lain |
| `aliza-bot.service` | **enabled** | inactive/dead | 0 / 2026-04-24 08:13 | 0 | Risiko start bersama bot utama saat reboot |
| `aliza-dashboard.service` | disabled | inactive/dead | 0 / n/a | 0 | Menunjuk repo ini |
| `aliza-market.service` | **disabled** | inactive/dead | 0 / n/a | 0 | Konfirmasi disabled berhasil |
| `aliza-meeting.service` | disabled | inactive/dead | 0 / n/a | 0 | Repo lain |
| `aliza-stock.service` | disabled | inactive/dead | 0 / n/a | 0 | Repo lain |
| `aliza-telegram.service` | **enabled** | **active/running** | 2230674 / 2026-07-21 12:47:05 | 0 | Bot utama |
| `aliza.service` | masked | inactive/dead | 0 / n/a | 0 | Jangan disentuh |

Output penting `systemctl status`:

```text
● aliza-telegram.service - AlizaAI Telegram Bot
     Loaded: loaded (/etc/systemd/system/aliza-telegram.service; enabled; vendor preset: enabled)
     Active: active (running) since Tue 2026-07-21 12:47:05 WIB; 27min ago
   Main PID: 2230674 (python)
      Tasks: 8 (limit: 4323)
     Memory: 605.7M
        CPU: 1min 7.353s
     CGroup: /system.slice/aliza-telegram.service
             └─2230674 /opt/aliza-ai/venv/bin/python /opt/aliza-ai/interfaces/telegram_bot.py

○ aliza-market.service - AlizaAI Market Bot
     Loaded: loaded (/etc/systemd/system/aliza-market.service; disabled; vendor preset: enabled)
     Active: inactive (dead)
```

Verifikasi durasi proses terpisah:

```text
$ ps -p 2230674 -o pid=,etime=,lstart=,cmd=
2230674       26:11 Tue Jul 21 12:47:05 2026 /opt/aliza-ai/venv/bin/python /opt/aliza-ai/interfaces/telegram_bot.py
```

`aliza-market` sempat berjalan dan berhenti normal pukul 09:12, tetapi pada saat audit benar-benar disabled/inactive:

```text
Jul 21 09:12:38 ... Stopping AlizaAI Market Bot...
Jul 21 09:12:38 ... aliza-market.service: Deactivated successfully.
Jul 21 09:12:38 ... Stopped AlizaAI Market Bot.
```

Catatan: `systemctl status` gabungan keluar dengan kode 3 karena mayoritas unit inactive; ini perilaku normal `systemctl`, bukan kegagalan audit.

## 3. Journal dan warning 7 hari

```text
$ journalctl --disk-usage
Archived and active journals take up 384.0M in the file system.
```

Perintah yang dijalankan untuk masing-masing dari 11 unit:

```bash
journalctl -u <unit> --since "7 days ago" -p warning --no-pager | tail -50
```

Sepuluh unit selain `aliza-telegram.service` menghasilkan `-- No entries --`. Output `aliza-telegram.service` berisi 6 warning/error:

```text
Jul 21 07:38:20 ... State 'stop-sigterm' timed out. Killing.
Jul 21 07:38:20 ... Main process exited, code=killed, status=9/KILL
Jul 21 07:38:20 ... Failed with result 'timeout'.
Jul 21 12:47:05 ... State 'stop-sigterm' timed out. Killing.
Jul 21 12:47:05 ... Main process exited, code=killed, status=9/KILL
Jul 21 12:47:05 ... Failed with result 'timeout'.
```

Query level `err` terpisah menghasilkan `-- No entries --`; enam baris di atas terambil pada filter `warning` dan berasal dari systemd. Journal dapat dibaca tanpa sudo.

## 4. Database SQLite dan shadow mode

Path DB ditemukan dari `find` dan source (`engine/trading/signal_tracker.py`):

```text
data/aliza.db bytes=40960 modified=2026-07-21 09:12:37.666148607 +0700 owner=ubuntu group=aliza-dashboard mode=660
data/user_config.db bytes=12288 modified=2026-04-16 08:58:18.370885793 +0700 owner=ubuntu group=aliza-dashboard mode=660
```

Tabel `data/aliza.db`:

```text
chats  signal_tracking  usage  documents  trades  users
```

Query aktual read-only:

```sql
SELECT COUNT(*) AS total FROM signal_tracking;
SELECT COALESCE(source,'<NULL>') AS source, COUNT(*) AS rows,
       MAX(created_at), MAX(close_time)
FROM signal_tracking GROUP BY source;
SELECT COUNT(*) FROM signal_tracking WHERE COALESCE(source,'') <> 'shadow_e3';
SELECT COUNT(*) FROM signal_tracking WHERE source='shadow_e3';
```

Output:

```text
total
-----
10

source  rows  latest_created_at    latest_close_time
------  ----  -------------------  --------------------------------
legacy  10    2026-07-21 01:00:41  2026-07-21T01:05:26.732660+07:00

production_rows
---------------
10

shadow_e3_rows
--------------
0
```

Baris terbaru adalah id 24, source `legacy`, coin `SOL`, status `OPEN`, created `2026-07-21 01:00:41`. Tidak ada source produksi baru seperti `deterministic`, dan tidak ada `shadow_e3`.

Log service pukul 13:15 membuktikan jalur shadow dijalankan:

```text
2026-07-21 13:15:02,575 - INFO - engine.shadow.e3_shadow - shadow_e3 candidates=0
2026-07-21 13:15:02,575 - INFO - root - shadow_e3 recorded=0 dispatch=True
2026-07-21 13:15:02,575 - INFO - apscheduler.executors.default - Job "snapshot_job ..." executed successfully
```

Kesimpulan shadow: **job hidup, tetapi belum menghasilkan row**. Dispatch `true` belum berarti pesan terkirim karena kandidat dan row sama-sama nol.

## 5. File log aplikasi dan rotasi

Perintah yang diminta:

```text
$ find . -name '*.log' -size +1M -exec ls -lh {} \;
-rw------- 1 ubuntu ubuntu 6.4M Jul 21 13:13 ./logs/aliza.log
```

Rincian aktual:

```text
11618766 logs/aliza.log.1
6658784  logs/aliza.log
984678   logs/aliza.log.6.gz
978743   logs/aliza.log.4.gz
971634   logs/aliza.log.5.gz
952295   logs/aliza.log.3.gz
942988   logs/aliza.log.2.gz
879291   logs/aliza.log.7.gz
0        logs/dashboard.log
0        logs/dashboard-new.log
rotated_count=9 rotated_bytes=17339757
```

Rotasi ada di `/etc/logrotate.d/aliza-ai`:

```text
/opt/aliza-ai/logs/aliza.log {
    daily
    rotate 7
    compress
    delaycompress
    copytruncate
    maxsize 50M
}

/opt/aliza-ai/logs/dashboard.log
/opt/aliza-ai/logs/dashboard-new.log {
    weekly
    rotate 4
    compress
    copytruncate
}
```

`logrotate --debug` dapat membaca konfigurasi dan menyatakan log sudah dirotasi, tetapi tidak dapat membuka `/var/lib/logrotate/status` (`Permission denied`). Pemeriksaan state penuh **butuh sudo**; file hasil rotasi membuktikan rotasi aktual berjalan.

## 6. Konfigurasi non-secret

Audit hanya membaca empat key yang diminta; tidak ada token/secret lain yang dibuka:

```text
UNIVERSE_EXCLUDE=BONE,FARTCOIN,HYPE,ZEREBRO
SHADOW_E3_ENABLED=true
SHADOW_E3_DISPATCH=true
COIN_FAIL_THRESHOLD=<TIDAK_ADA>
```

`COIN_FAIL_THRESHOLD` tidak terisi di `.env`; source aktual menetapkan default 10:

```text
engine/market/market_universe.py:30:DEFAULT_COIN_FAIL_THRESHOLD = 10
engine/market/market_universe.py:54:return _positive_int_env("COIN_FAIL_THRESHOLD", DEFAULT_COIN_FAIL_THRESHOLD)
```

## 7. Git state

```text
$ git status -sb
## main...origin/main [ahead 13]
?? AlizaAI-Crypto/01-hasil-audit-codex/FASE1C_VERIFIKASI_REPORT.md
?? AlizaAI-Crypto/01-hasil-audit-codex/FASE1D_REPORT.md
?? FASE1D_REPORT.md
?? audit-output/

$ git rev-list --left-right --count origin/main...HEAD
0       13

$ git show -s --format='%h %ci %s' HEAD origin/main
5ef5a9f7 2026-07-21 12:43:53 +0700 docs(fase4): clarify posthoc PF verdict
9ff08ba6 2026-07-21 10:44:54 +0700 docs(fase2): update final test timing
```

`git fetch --dry-run` berhasil tanpa output perubahan remote. Kesimpulan: remote ref sudah diperiksa, tetapi lokal dan origin **tidak sama** karena 13 commit lokal belum ada di origin.

Lima commit terbaru:

```text
5ef5a9f7 docs(fase4): clarify posthoc PF verdict
bc2ef977 Merge Fase 4 E3 robustness and shadow mode
48403ed7 docs(fase4): report robustness and shadow mode
91303161 test(fase4): cover shadow isolation and ATR levels
c385bb8d feat(fase4): add robustness protocol and cost stress hooks
```

Tidak ada modified atau staged file sebelum laporan dibuat; yang ada adalah untracked milik pekerjaan/audit sebelumnya.

## 8. Cron, timer, dan scheduler

Entry aktif `crontab -l`:

```text
0 2 * * * /opt/aliza-backups/scripts/backup.sh
*/5 * * * * /home/ubuntu/server-monitor/monitor.sh
0 19 * * * /opt/aliza-backups/backup_db.sh >> /opt/aliza-backups/backup.log 2>&1
0 2 * * * cp /opt/aliza-ai/interfaces/telegram_bot.py /opt/aliza-ai/interfaces/telegram_bot.py.bak.$(date +\%Y\%m\%d) 2>/dev/null
0 23 * * * /opt/gmail-agent/venv/bin/python3 /opt/gmail-agent/auto_scan.py >> /opt/gmail-agent/auto_scan.log 2>&1
0 5 * * * /opt/gmail-agent/venv/bin/python3 /opt/gmail-agent/auto_scan.py >> /opt/gmail-agent/auto_scan.log 2>&1
```

Entry restart Aliza pukul 20:00 sudah dikomentari. Timer Aliza:

```text
$ systemctl list-timers --all 'aliza*' --no-pager
NEXT LEFT LAST PASSED UNIT ACTIVATES

0 timers listed.
```

Scheduler runtime berada di satu proses `aliza-telegram`, melalui `app.job_queue`. `rg` menemukan registrasi pada baris 7014–7143; `snapshot_job` hanya satu kali (`interval=60`) dan checker bernama didaftarkan satu kali masing-masing. Tidak ada proses `aliza-market` atau timer systemd aktif yang menggandakan scheduler saat audit.

Namun, `aliza-bot.service` tetap enabled walau inactive. Ini bukan duplikasi aktif sekarang, tetapi perlu dipastikan sebelum reboot karena `aliza-telegram.service` juga enabled.

Cron backup source tanpa retensi telah menghasilkan:

```text
interfaces/telegram_bot.py.bak* count=102 bytes=25230622 min=147671 max=265794
oldest: 2026-04-18 06:26 ...telegram_bot.py.bak.20260418_072625
newest: 2026-07-21 01:00 ...telegram_bot.py.bak.20260721
```

## Tindakan yang memerlukan user

Prioritas tinggi:

1. Investigasi dua stop-timeout `aliza-telegram` sebelum restart berikutnya; review `TimeoutStopSec`, shutdown handler, dan alasan restart manual. Perubahan unit/reload/restart **butuh sudo** dan change control.
2. Konfirmasi apakah `aliza-bot.service` adalah unit lama. Jika ya, disable agar tidak start bersama bot utama saat reboot; tindakan `systemctl disable` **butuh sudo**.
3. Putuskan apakah `SHADOW_E3_DISPATCH=true` memang diinginkan. Pipeline aktif tetapi belum ada row; jangan mengubah flag/restart tanpa persetujuan.
4. Push/reconcile 13 commit lokal dengan `origin/main`; tidak membutuhkan sudo, tetapi merupakan perubahan remote dan tidak dilakukan dalam audit ini.
5. Tambahkan retensi pada cron backup harian dan putuskan cleanup 102 backup; tidak membutuhkan sudo untuk crontab user, tetapi menunggu persetujuan.

Prioritas rendah:

- Pemeriksaan state logrotate yang lengkap **butuh sudo** untuk membaca `/var/lib/logrotate/status`.
- Journal 384 MiB belum kritis. Vacuum journal akan **butuh sudo** dan belum perlu dilakukan pada tahap ini.

