# DEPLOY SCRIPT FIX REPORT

Tanggal: 2026-07-21
Repo: `/opt/aliza-ai`
Branch: `fix/deploy-script`
Base: `77b27a1 docs: report phase 2 merge and push`

## 1. Ringkasan

`scripts/deploy/deploy.sh` telah diperbaiki agar memakai repo aktual `/opt/aliza-ai`, hanya me-restart unit authoritative `aliza-telegram.service`, menolak worktree kotor atau branch selain `main`, memakai pull fast-forward-only, mencatat commit sebelum/sesudah update, dan memastikan service benar-benar kembali `active`.

Tidak ada restart, pull, atau sudo sungguhan yang dijalankan selama verifikasi.

## 2. Bukti kondisi awal

Isi lama yang dibaca utuh:

```bash
#!/bin/bash

cd /home/ubuntu/aliza-ai

echo "Pulling latest code..."
git pull origin main

echo "Restarting services..."
sudo systemctl restart aliza-api
sudo systemctl restart aliza-telegram

echo "Deploy completed"
```

Output aktual unit:

```text
$ systemctl list-units 'aliza*' --all --no-pager
UNIT                   LOAD   ACTIVE SUB     DESCRIPTION
aliza-telegram.service loaded active running AlizaAI Telegram Bot

$ systemctl list-unit-files 'aliza*' --no-pager
aliza-api.service         disabled enabled
aliza-telegram.service    enabled  enabled
```

Hanya `aliza-telegram.service` yang loaded dan aktif. Tidak ditemukan bukti untuk mempertahankan restart `aliza-api.service`.

## 3. Perubahan dan alasan

| Perubahan | Alasan |
|---|---|
| `/home/ubuntu/aliza-ai` → `/opt/aliza-ai` | Menyesuaikan path runtime aktual |
| Hapus restart `aliza-api` | Unit disabled dan bukan produksi authoritative |
| `set -euo pipefail` | Menghentikan deploy ketika command wajib gagal atau variable tidak tersedia |
| Precheck `git status --porcelain` | Mencegah pull di atas perubahan lokal |
| Precheck branch `main` | Mencegah deploy branch fitur/detached state |
| `git pull --ff-only origin main` | Menolak merge commit implisit/non-fast-forward |
| Log `git rev-parse HEAD` sebelum/sesudah | Memberi provenance commit dan pegangan rollback |
| Restart hanya `aliza-telegram.service` | Sesuai ownership service aktual |
| `systemctl is-active` setelah restart | Restart command sukses belum membuktikan proses hidup |
| Tampilkan `systemctl status` saat gagal | Memberi diagnosis awal tanpa menyembunyikan kegagalan |
| Reminder smoke test | Menjaga smoke test penuh tetap manual sesuai runbook |

## 4. Diff lengkap

```diff
diff --git a/scripts/deploy/deploy.sh b/scripts/deploy/deploy.sh
index 3f8bd7a..321123c 100755
--- a/scripts/deploy/deploy.sh
+++ b/scripts/deploy/deploy.sh
@@ -1,12 +1,49 @@
-#!/bin/bash
+#!/usr/bin/env bash

-cd /home/ubuntu/aliza-ai
+set -euo pipefail

-echo "Pulling latest code..."
-git pull origin main
+readonly REPO_DIR="/opt/aliza-ai"
+readonly SERVICE="aliza-telegram.service"

-echo "Restarting services..."
-sudo systemctl restart aliza-api
-sudo systemctl restart aliza-telegram
+log() {
+    printf '[deploy] %s\n' "$*"
+}

-echo "Deploy completed"
+fail() {
+    printf '[deploy] ERROR: %s\n' "$*" >&2
+    exit 1
+}
+
+cd "$REPO_DIR" || fail "Cannot access repository: $REPO_DIR"
+
+if [[ -n "$(git status --porcelain)" ]]; then
+    git status --short
+    fail "Working tree is not clean; commit, stash, or remove local changes before deploying."
+fi
+
+current_branch="$(git branch --show-current)"
+if [[ "$current_branch" != "main" ]]; then
+    fail "Deployment must run from main; current branch is '$current_branch'."
+fi
+
+before_commit="$(git rev-parse HEAD)"
+log "Commit before pull: $before_commit"
+
+log "Pulling origin/main with fast-forward only..."
+git pull --ff-only origin main
+
+after_commit="$(git rev-parse HEAD)"
+log "Commit after pull:  $after_commit"
+
+log "Restarting $SERVICE..."
+sudo systemctl restart "$SERVICE"
+
+service_state="$(systemctl is-active "$SERVICE" || true)"
+log "Service state after restart: $service_state"
+if [[ "$service_state" != "active" ]]; then
+    systemctl status "$SERVICE" --no-pager || true
+    fail "$SERVICE did not become active after restart."
+fi
+
+log "Deploy completed successfully: $before_commit -> $after_commit"
+log "Run the manual smoke test in docs/runbooks/smoke-test.md."
```

Executable mode tetap `100755` di Git; mode filesystem saat verifikasi `775`.

## 5. Verifikasi

### Syntax dan shellcheck

```text
$ bash -n scripts/deploy/deploy.sh
bash -n: PASS

$ command -v shellcheck
shellcheck: NOT_AVAILABLE
```

Tidak ada paket baru yang diinstal.

### Abort pada worktree kotor

Script dijalankan pada branch kerja yang memang memiliki perubahan, sehingga harus berhenti sebelum pull/restart:

```text
 M scripts/deploy/deploy.sh
?? AlizaAI-Crypto/01-hasil-audit-codex/FASE1C_VERIFIKASI_REPORT.md
[deploy] ERROR: Working tree is not clean; commit, stash, or remove local changes before deploying.
exit_code=1
```

### Happy-path dengan stub

`git`, `sudo`, dan `systemctl` diganti fungsi stub. Tidak ada command eksternal berbahaya yang dieksekusi.

```text
[deploy] Commit before pull: 0123456789abcdef0123456789abcdef01234567
[deploy] Pulling origin/main with fast-forward only...
[dry-run] git pull --ff-only origin main
[deploy] Commit after pull:  0123456789abcdef0123456789abcdef01234567
[deploy] Restarting aliza-telegram.service...
[dry-run] sudo systemctl restart aliza-telegram.service
[deploy] Service state after restart: active
[deploy] Deploy completed successfully: 0123456789abcdef0123456789abcdef01234567 -> 0123456789abcdef0123456789abcdef01234567
[deploy] Run the manual smoke test in docs/runbooks/smoke-test.md.
```

### Jalur gagal tambahan

```text
WRONG BRANCH:
[deploy] ERROR: Deployment must run from main; current branch is 'fix/test'.
exit_code=1

FAILED SERVICE:
[deploy] Service state after restart: failed
[dry-run] systemctl status aliza-telegram.service --no-pager
[deploy] ERROR: aliza-telegram.service did not become active after restart.
exit_code=1
```

## 6. Kesesuaian dengan runbook

Script mengikuti `docs/runbooks/deploy-restart-rollback.md` untuk clean-tree/main precheck, commit provenance, `pull --ff-only`, satu service authoritative, dan kewajiban smoke test.

Runbook tetap menjadi acuan authoritative untuk langkah yang sengaja tidak diotomasi:

- review commit target dan pemeriksaan service sebelum deploy;
- backup/checksum DB bila ada migrasi;
- journal dan smoke test lengkap;
- dua-restart verification bila shutdown berubah;
- revert commit dan rollback DB setelah persetujuan.

Script tidak menambahkan rollback otomatis atau backup generik karena kebutuhan tersebut bergantung pada isi release dan change control.

## 7. Cakupan perubahan

Sebelum laporan dibuat, output aktual:

```text
$ git status --short --branch
## fix/deploy-script
 M scripts/deploy/deploy.sh
?? AlizaAI-Crypto/01-hasil-audit-codex/FASE1C_VERIFIKASI_REPORT.md

$ git diff --name-only | rg '\.py$'
(kosong)
```

File untracked `FASE1C_VERIFIKASI_REPORT.md` sudah ada sebelum pekerjaan ini dan tidak disentuh. Perubahan yang disengaja hanya script, laporan kanonik ini, dan salinan bundle-nya.

## 8. Catatan operasional

Restart sungguhan belum pernah dieksekusi melalui script yang diperbaiki. User/operator berwenang tetap harus menjalankannya dari clean `main` pada deploy berikutnya, memasukkan password hanya untuk `sudo systemctl restart aliza-telegram.service`, lalu mengikuti smoke test manual.
