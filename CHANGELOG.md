# Changelog

Changelog ini dimulai dari checkpoint Git nyata pada 21 Juli 2026. Repo memiliki tag lama `v0.4-stable-bot`, tetapi perubahan di bawah belum dipetakan ke release/tag semantik baru; hash dan tanggal berasal dari `git log` pada `main`.

## [Unreleased]

### 2026-07-21

- `6e54996` — Memindahkan dokumentasi ke `agent-rules/`, `architecture/`, `runbooks/`, dan `audits/` dengan rename 100%; tahap isi berikutnya menggabungkan playbook debug, memecah panduan test, dan memperbarui indeks.
- `f38ab55` — Membatasi graceful shutdown Telegram agar selesai sebelum timeout systemd.
- `bc2ef97` — Merge Fase 4: robustness E3 dan runtime shadow yang terisolasi.
- `ab23716` — Merge Fase 3: runner eksperimen backtester, holdout, dan analisis hasil.
- `c5bcab8` — Merge Fase 2: backtester event-driven dengan biaya, funding, dan guard anti-lookahead.
- `c350a21` — Merge Fase 1d: observability data coverage dan universe coverage gate.
- `cdaf551` — Merge Fase 1: perbaikan integritas sinyal, tracking, risk validation, dan scheduler runtime.

Tidak ada rilis lama yang direkonstruksi tanpa tag atau bukti release resmi.
