# Deploy, Restart, dan Rollback aliza-telegram

Runbook manual ini authoritative untuk deployment di `/opt/aliza-ai`. Script `scripts/deploy/deploy.sh` belum aman digunakan: pada verifikasi 2026-07-21 script masih melakukan `cd /home/ubuntu/aliza-ai`, menjalankan `git pull origin main`, dan me-restart `aliza-api` serta `aliza-telegram`. Jangan jalankan script tersebut sampai diperbaiki dan direview.

## 1. Precheck

```bash
cd /opt/aliza-ai
git status --short --branch
git branch --show-current
git rev-parse HEAD
systemctl status aliza-telegram --no-pager
```

Syarat lanjut:

- branch adalah `main`;
- worktree bersih;
- service menunjuk `WorkingDirectory=/opt/aliza-ai` dan entrypoint yang benar;
- commit target sudah direview.

Jika worktree kotor, berhenti dan identifikasi pemilik perubahan. Jangan memakai `git reset --hard`.

## 2. Backup DB bila ada migrasi

Jika deploy menyentuh schema/writer SQLite, ambil backup konsisten sebelum update. Idealnya hentikan writer dengan change window yang disetujui, lalu:

```bash
mkdir -p data/backups
cp --preserve=mode,timestamps data/aliza.db \
  "data/backups/aliza.db.pre-deploy.$(date +%Y%m%dT%H%M%S).bak"
```

Catat path dan checksum backup tanpa menyalin isi DB ke report. Untuk deploy tanpa migrasi DB, dokumentasikan bahwa backup tidak diperlukan.

## 3. Update dan restart

```bash
git fetch origin
git pull --ff-only origin main
git rev-parse HEAD
sudo systemctl restart aliza-telegram
systemctl status aliza-telegram --no-pager
```

Jangan me-restart `aliza-api` dari repo ini; unit utama yang diverifikasi adalah `aliza-telegram`. Perintah sudo memerlukan user/operator berwenang.

## 4. Verifikasi

Jalankan [smoke-test.md](smoke-test.md). Jika deploy menyentuh shutdown/scheduler, tambahkan prosedur dua restart dari [graceful-shutdown.md](graceful-shutdown.md).

Minimal bukti:

```bash
journalctl -u aliza-telegram --since "10 minutes ago" --no-pager
git status --short --branch
```

## 5. Rollback kode

Tentukan commit buruk dan parent yang telah diverifikasi:

```bash
git log --oneline -5
git show --stat <bad_commit>
```

Setelah persetujuan, gunakan revert commit agar audit trail tetap utuh:

```bash
git revert <bad_commit>
sudo systemctl restart aliza-telegram
```

Ulangi smoke test dan simpan journal. Jika beberapa commit harus dibatalkan, review urutan revert terlebih dahulu.

## 6. Rollback database

Restore DB hanya bila migrasi tidak backward-compatible dan rollback telah disetujui. Hentikan writer, simpan salinan DB gagal untuk forensik, restore backup yang checksum-nya diverifikasi, lalu start service dan smoke test. Jangan menimpa `data/aliza.db` ketika service masih menulis.
