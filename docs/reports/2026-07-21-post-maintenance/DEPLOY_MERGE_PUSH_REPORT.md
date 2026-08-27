# DEPLOY MERGE & PUSH REPORT — Perbaikan `deploy.sh`

Tanggal: 2026-07-21
Repo: `/opt/aliza-ai`
Target: `main`
Branch sumber: `fix/deploy-script`

## Status akhir: **BERHASIL** — rebase bersih, fast-forward merge, push sukses, branch sumber dihapus

## Ringkasan percobaan pertama (gagal, non-fast-forward)

Percobaan pertama `git merge --ff-only fix/deploy-script` gagal: `fix/deploy-script` (commit `24b3d03`) bercabang dari `77b27a1`, sementara `main` sudah maju 3 commit sejak itu — `2b62ce8` (mitigasi spam notifikasi Telegram), `4045b8e` (merge commit dari fix di atas), dan `907930b` (perbaikan konversi epoch UTC pada cooldown alert). `fix/deploy-script` tidak memuat ketiga commit itu sehingga `git merge --ff-only` menolak dengan `fatal: Not possible to fast-forward, aborting.` Proses dihentikan tanpa merge commit atau push, sesuai laporan sebelumnya. Percobaan kedua ini adalah lanjutannya: rebase `fix/deploy-script` di atas `main` terkini, lalu ulangi merge & push.

## 1. Precheck

```text
$ git fetch origin
(tidak ada output; sukses)

$ git log --oneline main -5
907930b fix: correct UTC epoch conversion in alert cooldown timestamps
4045b8e Merge branch 'fix/telegram-notification-noise'
2b62ce8 fix: mitigate Telegram alert notification spam
77b27a1 docs: report phase 2 merge and push
638af4d docs: report phase 2 restructure validation

$ git log --oneline fix/deploy-script -5
24b3d03 fix: harden deploy script for production service
77b27a1 docs: report phase 2 merge and push
638af4d docs: report phase 2 restructure validation
f9d8bf4 docs: rebuild guides and operational runbooks
6e54996 docs: move documentation into canonical structure
```

Konfirmasi bahwa 3 commit baru **tidak** menyentuh `scripts/deploy/deploy.sh`:

```text
$ git show --stat 2b62ce8
 .env.example                                       |  10 +
 .../NOTIFIKASI_MITIGASI_REPORT.md                  | 116 +++++++
 NOTIFIKASI_MITIGASI_REPORT.md                      | 116 +++++++
 engine/alerts/notification_governor.py             | 339 +++++++++++++++++++++
 engine/market/breakout_detector.py                 |  25 +-
 engine/market/funding_rate_monitor.py              |  11 +-
 engine/market/volume_spike_detector.py             |  22 +-
 interfaces/telegram_bot.py                         | 267 +++++++++++-----
 tests/test_notifikasi_mitigasi.py                  | 265 ++++++++++++++++

$ git show --stat 4045b8e
(merge commit — file list sama seperti 2b62ce8, tidak ada file lain)

$ git show --stat 907930b
 interfaces/telegram_bot.py        | 20 ++++++++++++++++----
 tests/test_notifikasi_mitigasi.py | 28 ++++++++++++++++++++++++++++
```

Tidak satu pun dari ketiga commit menyentuh `scripts/deploy/`. Aman untuk rebase otomatis.

## 2. Rebase

```text
$ git checkout fix/deploy-script
Switched to branch 'fix/deploy-script'

$ git rebase main
Rebasing (1/1)
Successfully rebased and updated refs/heads/fix/deploy-script.
```

Tidak ada konflik. Commit tunggal `24b3d03` ditulis ulang menjadi `aded2b3` di atas `907930b`.

## 3. Re-verifikasi setelah rebase

```text
$ bash -n scripts/deploy/deploy.sh
bash -n: PASS

$ git log --oneline -5 fix/deploy-script
aded2b3 fix: harden deploy script for production service
907930b fix: correct UTC epoch conversion in alert cooldown timestamps
4045b8e Merge branch 'fix/telegram-notification-noise'
2b62ce8 fix: mitigate Telegram alert notification spam
77b27a1 docs: report phase 2 merge and push

$ git diff --stat main fix/deploy-script
 .../DEPLOY_SCRIPT_FIX_REPORT.md                    | 219 +++++++++++++++++++++
 .../DEPLOY_SCRIPT_FIX_REPORT.md                    | 219 +++++++++++++++++++++
 scripts/deploy/deploy.sh                           |  53 ++++-
 3 files changed, 483 insertions(+), 8 deletions(-)
```

Hanya `scripts/deploy/deploy.sh` dan dua salinan laporan `DEPLOY_SCRIPT_FIX_REPORT.md` (kanonik + bundle `AlizaAI-Crypto`) yang berbeda dari `main` — sesuai ekspektasi, isi script tidak berubah oleh rebase karena tidak ada overlap dengan 3 commit baru.

### Skenario stub (ulang dari `DEPLOY_SCRIPT_FIX_REPORT.md`)

**Worktree kotor** — dijalankan nyata (bukan stub) karena worktree memang punya file untracked; harus berhenti sebelum pull/restart:

```text
$ bash scripts/deploy/deploy.sh
?? AlizaAI-Crypto/01-hasil-audit-codex/DEPLOY_MERGE_PUSH_REPORT.md
?? AlizaAI-Crypto/01-hasil-audit-codex/FASE1C_VERIFIKASI_REPORT.md
?? AlizaAI-Crypto/01-hasil-audit-codex/NOTIFIKASI_DEPLOY_VERIFIKASI_REPORT.md
?? DEPLOY_MERGE_PUSH_REPORT.md
?? NOTIFIKASI_DEPLOY_VERIFIKASI_REPORT.md
[deploy] ERROR: Working tree is not clean; commit, stash, or remove local changes before deploying.
exit_code=1
```

**Happy path, wrong branch, failed service** — `git`, `sudo`, `systemctl` diganti fungsi stub di harness terpisah (tidak ada command eksternal nyata dieksekusi):

```text
=== HAPPY PATH ===
[deploy] Commit before pull: 0123456789abcdef0123456789abcdef01234567
[deploy] Pulling origin/main with fast-forward only...
[dry-run] git pull --ff-only origin main
[deploy] Commit after pull:  0123456789abcdef0123456789abcdef01234567
[deploy] Restarting aliza-telegram.service...
[dry-run] sudo systemctl restart aliza-telegram.service
[deploy] Service state after restart: active
[deploy] Deploy completed successfully: 0123456789abcdef0123456789abcdef01234567 -> 0123456789abcdef0123456789abcdef01234567
[deploy] Run the manual smoke test in docs/runbooks/smoke-test.md.
exit_code=0

=== WRONG BRANCH ===
[deploy] ERROR: Deployment must run from main; current branch is 'fix/test'.
exit_code=1

=== FAILED SERVICE ===
[deploy] Commit before pull: 0123456789abcdef0123456789abcdef01234567
[deploy] Pulling origin/main with fast-forward only...
[dry-run] git pull --ff-only origin main
[deploy] Commit after pull:  0123456789abcdef0123456789abcdef01234567
[deploy] Restarting aliza-telegram.service...
[dry-run] sudo systemctl restart aliza-telegram.service
[deploy] Service state after restart: failed
[deploy] ERROR: aliza-telegram.service did not become active after restart.
exit_code=1
```

Keempat skenario cocok dengan hasil `DEPLOY_SCRIPT_FIX_REPORT.md` sebelum rebase (exit 1 / exit 0 / exit 1 / exit 1). Rebase tidak mengubah logic script. File script pada `fix/deploy-script` secara byte-for-byte identik dengan sebelum rebase, karena tidak ada commit `main` baru yang menyentuhnya.

## 4. Merge

```text
$ git checkout main
Switched to branch 'main'
Your branch is up to date with 'origin/main'.

$ git merge --ff-only fix/deploy-script
Updating 907930b..aded2b3
Fast-forward
 .../DEPLOY_SCRIPT_FIX_REPORT.md                    | 219 +++++++++++++++++++++
 .../DEPLOY_SCRIPT_FIX_REPORT.md                    | 219 +++++++++++++++++++++
 scripts/deploy/deploy.sh                           |  53 ++++-
 3 files changed, 483 insertions(+), 8 deletions(-)
 create mode 100644 AlizaAI-Crypto/01-hasil-audit-codex/DEPLOY_SCRIPT_FIX_REPORT.md
 create mode 100644 docs/reports/2026-07-21-maintenance/DEPLOY_SCRIPT_FIX_REPORT.md
```

Fast-forward berhasil, tanpa merge commit, tanpa konflik.

### Verifikasi pasca-merge

```text
$ bash -n scripts/deploy/deploy.sh
PASS

$ git diff --stat 907930b main -- '*.py'
(kosong — tidak ada perubahan Python dari merge ini)

$ git log --oneline -3 main
aded2b3 fix: harden deploy script for production service
907930b fix: correct UTC epoch conversion in alert cooldown timestamps
4045b8e Merge branch 'fix/telegram-notification-noise'
```

`find docs -type f | wc -l` menghasilkan **75**, bukan 73 seperti disebut di prompt. Ini diharapkan, bukan efek rebase: baseline 73 berasal dari verifikasi Tahap 2 (sebelum commit Telegram/epoch); commit `2b62ce8` (Telegram) sudah menambah `docs/.../NOTIFIKASI_MITIGASI_REPORT.md` sehingga `main` di `907930b` sudah berjumlah 74 dokumen sebelum merge ini. Merge `fix/deploy-script` menambah satu file lagi, `docs/reports/2026-07-21-maintenance/DEPLOY_SCRIPT_FIX_REPORT.md` (laporan resmi pekerjaan fix deploy.sh), menjadikan totalnya 75. `git diff --stat 907930b main -- docs/` mengonfirmasi hanya satu file itu yang berubah di bawah `docs/`.

## 5. Push

```text
$ git push origin main
To https://github.com/jun3iawan-ai/aliza-ai.git
   907930b..aded2b3  main -> main
```

Push berhasil sebagai fast-forward. Tidak ada penolakan, tidak ada force-push.

## 6. Penghapusan branch lokal

```text
$ git branch -d fix/deploy-script
Deleted branch fix/deploy-script (was aded2b3).
```

## 7. Status akhir integrasi

```text
$ git status -sb
## main...origin/main
?? AlizaAI-Crypto/01-hasil-audit-codex/DEPLOY_MERGE_PUSH_REPORT.md
?? AlizaAI-Crypto/01-hasil-audit-codex/FASE1C_VERIFIKASI_REPORT.md
?? AlizaAI-Crypto/01-hasil-audit-codex/NOTIFIKASI_DEPLOY_VERIFIKASI_REPORT.md
?? DEPLOY_MERGE_PUSH_REPORT.md
?? NOTIFIKASI_DEPLOY_VERIFIKASI_REPORT.md

$ git branch -a
  docs/quick-win
  fix/graceful-shutdown
* main
  remotes/origin/HEAD -> origin/main
  remotes/origin/main
```

`main` dan `origin/main` sinkron, tanpa ahead/behind. Branch `fix/deploy-script` sudah tidak ada di daftar lokal maupun remote (memang tidak pernah didorong ke remote). File untracked yang tersisa adalah laporan-laporan lama/sekarang yang belum di-`git add`, bukan bagian dari merge/push ini. Tidak ada restart service sungguhan yang dijalankan selama seluruh proses ini — semua verifikasi service memakai stub.
