# Beres-Beres Report — Runbook Fix + Rapikan Report Root

Branch: `docs/beres-beres` (dari `main`, commit dasar `453bbca`), lokal saja, tidak di-push.
Tanggal kerja: 2026-08-27.
Commit di branch ini: `0370c42` (fix runbook + pindah 18 report) dan `0caf1ed` (entri CHANGELOG).
Lingkup: **hanya file `.md`** di dalam `/opt/aliza-ai/` yang diubah/dipindah/dibuat. Tidak ada file `.py`/`.sh`/config/`.env` yang disentuh — dibuktikan di bagian Verifikasi.

## Bagian A — Perbaikan runbook basi

### Verifikasi isi `scripts/deploy/deploy.sh` (dibaca langsung, tidak diasumsikan)

Isi aktual script (tidak diubah sama sekali oleh task ini):

- `REPO_DIR="/opt/aliza-ai"`, `SERVICE="aliza-telegram.service"`.
- `cd "$REPO_DIR"` lalu **gagal (`fail`)** jika `git status --porcelain` tidak kosong (worktree harus bersih).
- **Gagal** jika `git branch --show-current` bukan `main`.
- Mencatat `before_commit` (`git rev-parse HEAD`), lalu `git pull --ff-only origin main`, lalu mencatat `after_commit`.
- Hanya menjalankan `sudo systemctl restart aliza-telegram.service` — **tidak menyentuh `aliza-api`**.
- Memverifikasi `systemctl is-active`; jika bukan `active`, mencetak `systemctl status` dan **gagal**.
- Pesan sukses akhir mengarahkan ke `docs/runbooks/smoke-test.md`.

Ini cocok persis dengan deskripsi commit `aded2b3` ("fix: harden deploy script for production service", 21 Juli 2026 15:42) yang juga dikonfirmasi via `git show --stat aded2b3` dan isi `docs/reports/2026-07-21-maintenance/DEPLOY_SCRIPT_FIX_REPORT.md` serta `docs/reports/2026-07-21-post-maintenance/DEPLOY_MERGE_PUSH_REPORT.md` (laporan proses rebase/merge/push perbaikan ini ke `main`, yang ternyata juga ditemukan sebagai file root untracked dan ikut dirapikan di Bagian B).

### Perubahan di `docs/runbooks/deploy-restart-rollback.md`

**Sebelum** (baris 3):

> Runbook manual ini authoritative untuk deployment di `/opt/aliza-ai`. Script `scripts/deploy/deploy.sh` belum aman digunakan: pada verifikasi 2026-07-21 script masih melakukan `cd /home/ubuntu/aliza-ai`, menjalankan `git pull origin main`, dan me-restart `aliza-api` serta `aliza-telegram`. Jangan jalankan script tersebut sampai diperbaiki dan direview.

**Sesudah**:

> Runbook manual ini authoritative untuk deployment di `/opt/aliza-ai`. Sejak commit `aded2b3` ("fix: harden deploy script for production service", 21 Juli 2026), `scripts/deploy/deploy.sh` sudah aman digunakan sebagai jalur deploy standar. Script tersebut: `cd /opt/aliza-ai` (bukan lagi `/home/ubuntu/aliza-ai`), gagal (`fail`) bila `git status --porcelain` menunjukkan working tree tidak bersih, gagal bila branch aktif bukan `main`, mencatat commit sebelum dan sesudah pull, menjalankan `git pull --ff-only origin main`, hanya me-restart `aliza-telegram.service` (tidak lagi menyentuh `aliza-api`), lalu memverifikasi `systemctl is-active` setelah restart dan gagal (menampilkan `systemctl status`) bila service tidak `active`. Syarat pakai: jalankan dari `/opt/aliza-ai` dengan working tree bersih di branch `main`, dan user punya akses `sudo systemctl restart aliza-telegram.service`. Langkah manual di bawah ini tetap berlaku sebagai referensi rinci dan untuk kasus di luar jalur fast-forward biasa (mis. rollback).

Baris 46 pada file yang sama ("Jangan me-restart `aliza-api` dari repo ini; unit utama yang diverifikasi adalah `aliza-telegram`.") **dibiarkan** — sudah akurat dan konsisten dengan script yang sudah diperbaiki, bukan klaim basi.

### Runbook lain — dicek, tidak ditemukan klaim basi

Dibaca seluruhnya dan diverifikasi terhadap kode aktual:

| Runbook | Klaim yang dicek | Bukti verifikasi | Status |
|---|---|---|---|
| `graceful-shutdown.md` | `TimeoutStopSec=15`, deadline app 8s, `scheduler.shutdown(wait=False)`, path `/etc/systemd/system/aliza-telegram.service` | `docs/audits/2026-07-15/security/evidence/aliza-telegram.service.txt` → `TimeoutStopSec=15`, `WorkingDirectory=/opt/aliza-ai`; `interfaces/telegram_bot.py:7685` → `GracefulShutdownController(app, timeout_seconds=8.0)`; `core/graceful_shutdown.py:59` → `scheduler.shutdown(wait=False)` | Akurat, tidak diubah |
| `health-check.md` | Command `/start /market /radar /status`, `data/aliza.db`, dashboard `GET /health` | Cocok dengan `scripts/run_dashboard.py` (default `127.0.0.1:8001`) dan struktur `interfaces/telegram_bot.py` | Akurat, tidak diubah |
| `smoke-test.md` | Dashboard loopback `8001`, endpoint `market/quant/predict/signals/portfolio` perlu Bearer, health tanpa token | `scripts/run_dashboard.py` → `DEFAULT_HOST="127.0.0.1"`, `DEFAULT_PORT=8001`, validasi loopback-only | Akurat, tidak diubah |
| `troubleshooting.md` | RR minimum opportunity 1,3; RR minimum signal produksi 3 + confidence 70; gateway RR minimum 2; `aliza-market` bukan scheduler aktif; writer DB `trade_manager.py`/`signal_tracker.py` | `engine/trading/opportunity_scanner.py:71` → `if rr < 1.3`; `engine/trading/signal_engine.py:49-50` → `MIN_RR = 3`, `MIN_CONFIDENCE = 70`; `engine/risk_manager.py:11` → `MIN_RR = 2`; file `engine/trading/trade_manager.py` dan `engine/trading/signal_tracker.py` ada dan sesuai deskripsi | Akurat, tidak diubah |

Tidak ada temuan basi lain selain paragraf di `deploy-restart-rollback.md` baris 3.

## Bagian B — Rapikan file `.md` untracked di root

### Baseline

`git status --porcelain` di awal (sebelum kerja) menghasilkan **37 baris**, terdiri dari **18 file `.md` untracked di root repo** dan **19 file `.md` untracked di `AlizaAI-Crypto/01-hasil-audit-codex/`** (18 pasangan identik + `FASE1C_VERIFIKASI_REPORT.md` yang hanya ada di bundle ekspor).

### Verifikasi identik root vs bundle ekspor

Semua 18 file root diverifikasi dengan `cmp` terhadap salinan di `AlizaAI-Crypto/01-hasil-audit-codex/` sebelum dipindah — **semuanya identik byte-for-byte**. Tidak ada temuan file yang berbeda isi; tidak ada yang perlu direview manual dari kategori ini.

`FASE1C_VERIFIKASI_REPORT.md` (hanya ada di bundle ekspor, tidak ada versi root) **tidak disentuh sama sekali** — sesuai instruksi, tidak disalin ke root atau dipindah.

### Pemetaan path lama → path baru

| Path lama (root, untracked) | Path baru (canonical) | Tanggal (mtime) |
|---|---|---|
| `AUDIT_FITUR_BERITA_REPORT.md` | `docs/reports/2026-07-21-post-maintenance/AUDIT_FITUR_BERITA_REPORT.md` | 2026-07-21 |
| `BERITA_DEPLOY_VERIFIKASI_REPORT.md` | `docs/reports/2026-07-21-post-maintenance/BERITA_DEPLOY_VERIFIKASI_REPORT.md` | 2026-07-21 |
| `DEPLOY_MERGE_PUSH_REPORT.md` | `docs/reports/2026-07-21-post-maintenance/DEPLOY_MERGE_PUSH_REPORT.md` | 2026-07-21 |
| `EVENING_SUMMARY_DEPLOY_REPORT.md` | `docs/reports/2026-07-21-post-maintenance/EVENING_SUMMARY_DEPLOY_REPORT.md` | 2026-07-21 |
| `NOTIFIKASI_DEPLOY_VERIFIKASI_REPORT.md` | `docs/reports/2026-07-21-post-maintenance/NOTIFIKASI_DEPLOY_VERIFIKASI_REPORT.md` | 2026-07-21 |
| `AUDIT_MEKANISME_EVALUASI_REPORT.md` | `docs/reports/2026-07-25-evaluasi-winrate/AUDIT_MEKANISME_EVALUASI_REPORT.md` | 2026-07-25 |
| `STATUS_WINRATE_REPORT.md` | `docs/reports/2026-07-25-evaluasi-winrate/STATUS_WINRATE_REPORT.md` | 2026-07-25 |
| `AUDIT_REFIRE_TRADE_SIGNAL_REPORT.md` | `docs/reports/2026-07-27-signal-rearm/AUDIT_REFIRE_TRADE_SIGNAL_REPORT.md` | 2026-07-27 |
| `SIGNAL_EDGE_TRIGGERED_REARM_REPORT.md` | `docs/reports/2026-07-27-signal-rearm/SIGNAL_EDGE_TRIGGERED_REARM_REPORT.md` | 2026-07-27 |
| `EVALUASI_BIG_MOVE_ALERT_REPORT.md` | `docs/reports/2026-08-05-signal-fixes/EVALUASI_BIG_MOVE_ALERT_REPORT.md` | 2026-08-05 |
| `NEAR_LEVEL_ON_DEMAND_REPORT.md` | `docs/reports/2026-08-05-signal-fixes/NEAR_LEVEL_ON_DEMAND_REPORT.md` | 2026-08-05 |
| `BIG_MOVE_REAL_1H_FIX_REPORT.md` | `docs/reports/2026-08-05-signal-fixes/BIG_MOVE_REAL_1H_FIX_REPORT.md` | 2026-08-05 |
| `AUDIT_MENU_TELEGRAM_LENGKAP_REPORT.md` | `docs/reports/2026-08-05-telegram-menu-restructure/AUDIT_MENU_TELEGRAM_LENGKAP_REPORT.md` | 2026-08-05 |
| `TELEGRAM_MENU_RESTRUCTURE_REPORT.md` | `docs/reports/2026-08-05-telegram-menu-restructure/TELEGRAM_MENU_RESTRUCTURE_REPORT.md` | 2026-08-05 |
| `AUDIT_MENU_INFORMASI.md` | `docs/reports/2026-08-21-info-coin/AUDIT_MENU_INFORMASI.md` | 2026-08-21 |
| `INFO_COIN_PAKET1_REPORT.md` | `docs/reports/2026-08-21-info-coin/INFO_COIN_PAKET1_REPORT.md` | 2026-08-21 |
| `VPS_HEALTH_REPORT_2.md` | `docs/reports/2026-08-27-vps-health-shadow-e3/VPS_HEALTH_REPORT_2.md` | 2026-08-27 |
| `SHADOW_E3_STAGNATION_REPORT.md` | `docs/reports/2026-08-27-vps-health-shadow-e3/SHADOW_E3_STAGNATION_REPORT.md` | 2026-08-27 |

Pengelompokan didasarkan pada pembacaan isi (judul + ringkasan pembuka) tiap file, bukan tebakan dari nama file, dikombinasikan dengan tanggal mtime yang berkerumun rapi per topik:

- **2026-07-21-post-maintenance/**: rangkaian deploy/verifikasi fitur yang dijalankan pada hari yang sama setelah maintenance 21 Juli selesai — audit+deploy fitur berita, fix evening summary, verifikasi mitigasi notifikasi, dan proses rebase/merge/push perbaikan `deploy.sh` (`DEPLOY_MERGE_PUSH_REPORT.md`, yang memuat bukti langsung asal commit `aded2b3` dipakai di Bagian A).
- **2026-07-25-evaluasi-winrate/**: audit mekanisme evaluasi/pembelajaran sinyal + laporan status winrate, sama hari, saling mereferensikan.
- **2026-07-27-signal-rearm/**: audit re-fire `[TRADE SIGNAL]` berulang + implementasi perbaikannya (edge-triggered re-arm).
- **2026-08-05-signal-fixes/**: evaluasi kualitas big-move alert, near-level on-demand, dan fix perhitungan big-move 1 jam — tiga perbaikan sinyal di hari yang sama.
- **2026-08-05-telegram-menu-restructure/**: audit menu Telegram lengkap + laporan restrukturisasi menu, hari yang sama, `AUDIT_MENU_INFORMASI.md` (21 Agustus) secara eksplisit mereferensikan dua file ini sebagai basis verifikasi ulang.
- **2026-08-21-info-coin/**: audit kesiapan data menu informasi per-coin + implementasi fitur Info Coin Paket 1.
- **2026-08-27-vps-health-shadow-e3/**: VPS Health Report #2 (yang memicu task ini) + investigasi stagnasi shadow_e3 yang dirujuk di dalamnya.

Nama folder mengikuti konvensi yang sudah ada di `docs/reports/2026-07-21-maintenance/` (tanggal-ISO + slug topik).

### Perbaikan link relatif akibat pemindahan

3 dari 18 file punya markdown link relatif ke path kode (root-relative, mis. `interfaces/telegram_bot.py`, `engine/...`, `docs/architecture/testing.md`, `AlizaAI-Crypto/01-hasil-audit-codex/...`). Karena file pindah dari root ke `docs/reports/<folder>/` (3 level lebih dalam), semua link tersebut diberi prefix `../../../` agar tetap resolve ke lokasi yang sama:

| File | Jumlah link diperbaiki |
|---|---|
| `docs/reports/2026-07-21-post-maintenance/AUDIT_FITUR_BERITA_REPORT.md` | 34 |
| `docs/reports/2026-07-25-evaluasi-winrate/AUDIT_MEKANISME_EVALUASI_REPORT.md` | 46 |
| `docs/reports/2026-07-21-post-maintenance/EVENING_SUMMARY_DEPLOY_REPORT.md` | 1 |

Semua target link diverifikasi resolve dengan benar dari lokasi baru (`interfaces/telegram_bot.py`, `engine/trading/signal_tracker.py`, `engine/market/economic_calendar.py`, `docs/architecture/testing.md`, `AlizaAI-Crypto/01-hasil-audit-codex/ROBUSTNESS_RESULTS.md`, dll — semua ada). 15 file lainnya tidak punya link relatif sama sekali sehingga dipindah tanpa modifikasi isi.

Referensi tekstual (bukan markdown link, sekadar sebutan nama file dalam tanda kutip backtick) ke file-file yang dipindah ditemukan di 4 file root lain yang sudah tracked sebelumnya (`LEARNING_LOOP_LIVE_DATA_REPORT.md`, `BERITA_MITIGASI_REPORT.md`, `INSTITUTIONAL_DATA_REPORT.md`, `WEEKLY_WINRATE_SUMMARY_REPORT.md`) — ini **bukan** link markdown (`[teks](path)`) sehingga tidak "patah" secara teknis, dan sengaja **tidak diubah** karena merupakan narasi historis milik laporan lain yang sudah tracked (di luar lingkup "file yang dipindah/diedit" pada task ini, dan mengubahnya berisiko menulis ulang fakta historis, yang dilarang aturan pemeliharaan `docs/README.md`).

### `docs/README.md`

Baris indeks untuk `reports/` diperbarui dari status `historical, canonical` menjadi campuran `historical (fase/maintenance) + current (fitur pasca-maintenance)`, dan ditambahkan subsection baru **"Report fitur pasca-maintenance (current)"** yang mendaftar ketujuh folder baru dengan ringkasan isinya.

### `CHANGELOG.md`

Ditambahkan entri baru di bawah `## [Unreleased]`, tanggal **2026-08-27**, mereferensikan commit `0370c42` — merangkum fix runbook dan pemindahan 18 file report ke folder bertanggal di `docs/reports/`.

## File yang sengaja TIDAK dipindah/diubah

- `AlizaAI-Crypto/01-hasil-audit-codex/*` (26 file tracked + 19 file untracked termasuk `FASE1C_VERIFIKASI_REPORT.md`) — bundle ekspor di luar scope, dibiarkan 100% apa adanya sesuai instruksi.
- `LEARNING_LOOP_LIVE_DATA_REPORT.md`, `BERITA_MITIGASI_REPORT.md`, `INSTITUTIONAL_DATA_REPORT.md`, `WEEKLY_WINRATE_SUMMARY_REPORT.md`, `DRAWDOWN_BROADCAST_GATE_REPORT.md`, `SHADOW_PROMOTION_CHECKLIST_REPORT.md`, `SHADOW_SIGNAL_SPAM_REPORT.md`, `NOTIFIKASI_MITIGASI_REPORT.md`, `README.md`, `CHANGELOG.md` — sudah **tracked** di root sebelum task ini mulai (bukan bagian dari 18 file untracked yang jadi lingkup Bagian B), sehingga tidak dipindah. Referensi tekstual (bukan link) ke file yang dipindah, yang ada di 4 di antaranya, dibiarkan sebagai narasi historis (lihat penjelasan di atas).

## Verifikasi wajib

1. **`git status --porcelain` bersih untuk semua yang diproses** — konfirmasi: baris tersisa hanya 19 file untracked di `AlizaAI-Crypto/01-hasil-audit-codex/` (bundle ekspor di luar scope, sengaja dibiarkan, lihat pola tracking bundle di bawah). Tidak ada sisa untracked baru dari pekerjaan ini.
2. **`bash -n scripts/deploy/deploy.sh` → PASS** (script tidak disentuh sama sekali).
3. **`git diff --stat main` (branch ini vs `main`) → hanya file `.md`** — `git diff --name-only main | grep -vE '\.md$'` kosong. 21 file berubah: `CHANGELOG.md`, `docs/README.md`, `docs/runbooks/deploy-restart-rollback.md`, dan 18 file report baru di `docs/reports/`.
4. **Broken relative markdown link** — 3 file dengan link root-relative (34 + 46 + 1 = 81 link) diperbaiki dengan prefix `../../../`; semua target diverifikasi ada secara fisik dari lokasi baru. `docs/README.md` juga dicek penuh — seluruh link resolve.
5. **Commit lokal di `docs/beres-beres`, tidak push** — dua commit: `0370c42` (fix runbook + pindah 18 report + update `docs/README.md`) dan `0caf1ed` (entri `CHANGELOG.md`). Tidak ada `git push` dijalankan.

## Salinan bundle ekspor

`AlizaAI-Crypto/01-hasil-audit-codex/` berisi campuran file tracked (26) dan untracked (19, termasuk salinan report yang baru saja dipindah di root). Pola commit-ke-git di folder itu tidak konsisten/lengkap (tidak semua file di dalamnya di-`git add`), jadi salinan `BERES_BERES_REPORT.md` ke folder ini **tidak di-`git add`**, mengikuti pola file lain yang saat ini juga untracked di situ.
