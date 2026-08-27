# Changelog

Changelog ini dimulai dari checkpoint Git nyata pada 21 Juli 2026. Repo memiliki tag lama `v0.4-stable-bot`, tetapi perubahan di bawah belum dipetakan ke release/tag semantik baru; hash dan tanggal berasal dari `git log` pada `main`.

## [Unreleased]

### 2026-08-27

- (branch `docs/rapikan-27agustus`, menunggu review manual) — Perapian dokumentasi lanjutan: memindahkan 3 file `.md` report yang menumpuk lagi di root repo sebagai untracked (`MERGE_PUSH_BERES_MESSAGEFIX_REPORT.md`, `MERGE_PUSH_SHADOW_OBSERVABILITY_REPORT.md`, `REPLY_TEXT_MESSAGE_LENGTH_AUDIT_REPORT.md`) ke `docs/reports/2026-08-27-vps-health-shadow-e3/`, karena ketiganya adalah lanjutan langsung dari VPS health check #2 dan investigasi shadow_e3 di hari yang sama (merge/push `docs/beres-beres`+fix message-too-long, merge/push shadow_e3 observability, dan audit risiko "Message is too long" di 172 titik `reply_text()`). Ketiga file diverifikasi identik (`sha256sum`) dengan salinan di bundle ekspor `AlizaAI-Crypto/01-hasil-audit-codex/` sebelum dipindah; bundle ekspor tidak disentuh. Detail lengkap di `RAPIKAN_27AGUSTUS_REPORT.md`.
- (branch `shadow-e3/evaluation-and-observability`, menunggu review manual) — Kebijakan promosi shadow_e3 diubah: kriteria "kapan boleh dievaluasi" dari tanggal kalender tetap (perkiraan 1 September 2026) menjadi murni jumlah outcome closed (≥60 outcome), tanpa batas tanggal keras — lihat `SHADOW_PROMOTION_CHECKLIST_REPORT.md` §"Update Kebijakan (27 Agustus 2026)" dan bukti pendukung `docs/reports/2026-08-27-vps-health-shadow-e3/SHADOW_E3_STAGNATION_REPORT.md`. Dokumen checklist juga menambah bagian "Limitasi Desain" yang menjelaskan shadow_e3 hanya menghasilkan kandidat saat `market_regime` (dihitung dari BTC) berstatus RANGE/DOWNTREND. Ditambah observability per-alasan-gagal (counter in-memory, reset per siklus) di `engine/shadow/e3_shadow.py::collect_shadow_signals()` — murni tambahan logging, tidak mengubah logika candidate generation; lihat `SHADOW_E3_CHECKLIST_OBSERVABILITY_REPORT.md` untuk detail lengkap.
- `0370c42` — Perapian dokumentasi (`docs/beres-beres`): perbaiki peringatan basi di `docs/runbooks/deploy-restart-rollback.md` yang masih menyebut `scripts/deploy/deploy.sh` "belum aman" (path `/home/ubuntu/aliza-ai`, restart `aliza-api`) — sudah tidak benar sejak `aded2b3` (21 Juli 2026); paragraf diganti dengan deskripsi akurat script saat ini (path `/opt/aliza-ai`, precheck worktree bersih + branch `main`, `git pull --ff-only`, hanya restart `aliza-telegram`, verifikasi `systemctl is-active`). Runbook lain (`graceful-shutdown.md`, `health-check.md`, `smoke-test.md`, `troubleshooting.md`) dicek terhadap kode aktual dan masih akurat, tidak diubah. Memindahkan 18 file `.md` report/audit fitur pasca-maintenance 21 Juli yang sebelumnya untracked di root repo ke folder bertanggal di `docs/reports/` (`2026-07-21-post-maintenance/`, `2026-07-25-evaluasi-winrate/`, `2026-07-27-signal-rearm/`, `2026-08-05-signal-fixes/`, `2026-08-05-telegram-menu-restructure/`, `2026-08-21-info-coin/`, `2026-08-27-vps-health-shadow-e3/`), lihat `BERES_BERES_REPORT.md` untuk detail pemetaan path lama → baru. Salinan identik di `AlizaAI-Crypto/01-hasil-audit-codex/` tidak disentuh.

### 2026-07-21

- `6e54996` — Memindahkan dokumentasi ke `agent-rules/`, `architecture/`, `runbooks/`, dan `audits/` dengan rename 100%; tahap isi berikutnya menggabungkan playbook debug, memecah panduan test, dan memperbarui indeks.
- `f38ab55` — Membatasi graceful shutdown Telegram agar selesai sebelum timeout systemd.
- `bc2ef97` — Merge Fase 4: robustness E3 dan runtime shadow yang terisolasi.
- `ab23716` — Merge Fase 3: runner eksperimen backtester, holdout, dan analisis hasil.
- `c5bcab8` — Merge Fase 2: backtester event-driven dengan biaya, funding, dan guard anti-lookahead.
- `c350a21` — Merge Fase 1d: observability data coverage dan universe coverage gate.
- `cdaf551` — Merge Fase 1: perbaikan integritas sinyal, tracking, risk validation, dan scheduler runtime.

Tidak ada rilis lama yang direkonstruksi tanpa tag atau bukti release resmi.
