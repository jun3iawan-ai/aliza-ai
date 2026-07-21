# Graceful Shutdown aliza-telegram

Runbook ini mendokumentasikan kontrak shutdown yang diperkenalkan oleh commit `f38ab55`. Diagnosis insiden lengkap tetap berada di [MAINTENANCE_REPORT.md](../reports/2026-07-21-maintenance/MAINTENANCE_REPORT.md#bagian-b--fix-graceful-shutdown).

## Kontrak aktif

| Lapisan | Nilai aktual | Bukti |
|---|---:|---|
| systemd `TimeoutStopSec` | 15 detik | `/etc/systemd/system/aliza-telegram.service` |
| Deadline aplikasi | 8 detik | `GracefulShutdownController(..., timeout_seconds=8.0)` di `interfaces/telegram_bot.py` |
| Scheduler stop | tidak menunggu pending future | `scheduler.shutdown(wait=False)` di `core/graceful_shutdown.py` |
| Fallback | watchdog memaksa proses keluar | `core/graceful_shutdown.py` |

Rekomendasi saat ini adalah mempertahankan 15 detik: deadline aplikasi 8 detik menyisakan sekitar 7 detik untuk teardown systemd. Jangan menaikkan timeout untuk menutupi job blocking tanpa bukti baru.

## Tanda log

Sukses:

- `SIGTERM received — graceful shutdown requested (deadline 8.0s)`
- `Job scheduler shutdown requested without waiting`
- `Graceful shutdown completed`
- tidak ada `State 'stop-sigterm' timed out` atau SIGKILL.

Gagal/degraded:

- `Failed to stop job scheduler during shutdown`
- `Graceful shutdown exceeded 8.0s; forcing process exit`
- `Application cleanup completed but process is still alive; forcing exit`
- systemd melaporkan stop-timeout atau SIGKILL.

## Verifikasi dua restart

Perubahan service memerlukan sudo/change control:

```bash
date --iso-8601=seconds
sudo systemctl restart aliza-telegram
systemctl status aliza-telegram --no-pager
sudo systemctl restart aliza-telegram
systemctl status aliza-telegram --no-pager
journalctl -u aliza-telegram --since "10 minutes ago" --no-pager
```

Kedua restart harus selesai di bawah 10 detik, unit kembali `active (running)`, marker sukses muncul, dan tidak ada timeout/SIGKILL.

## Bila macet lagi

1. Jangan melakukan restart berulang; simpan journal lengkap dan durasi tiap stop.
2. Identifikasi job/future yang masih blocking dan pastikan commit aktif benar.
3. Jalankan `tests/test_shutdown.py`.
4. Jika regresi berasal dari commit `f38ab55` dan rollback disetujui, buat revert commit (bukan reset destruktif), deploy, lalu ulangi dua restart:

```bash
git revert f38ab55
```

Rollback mengembalikan perilaku lama yang pernah mengalami SIGKILL; gunakan hanya sebagai tindakan terkontrol sambil menyiapkan perbaikan pengganti.
