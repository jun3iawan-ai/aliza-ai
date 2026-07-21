# DOCS RESTRUCTURE REPORT — Tahap 2

Tanggal audit/eksekusi: 2026-07-21
Repo: `/opt/aliza-ai`
Branch: `docs/restructure-phase2`
Base: `0eab6d5 docs: apply documentation quick wins`
Commit pemindahan: `6e54996 docs: move documentation into canonical structure`
Commit isi aktif: `f9d8bf4 docs: rebuild guides and operational runbooks`

## 1. Ringkasan

Restrukturisasi besar selesai tanpa menyentuh file `.py`, runtime data, `.env`, log, backtest data/result, atau script deploy. Struktur aktif kini memakai `docs/agent-rules/`, `docs/architecture/`, dan `docs/runbooks/`; material historis berada di `docs/audits/` dan report fase/maintenance tetap di `docs/reports/`.

Folder lama `docs/cursor-ai/`, `docs/instructions/`, `docs/audit/`, dan root `audit-output/` telah kosong lalu dihapus. Isinya tidak dibuang: file tracked dipindahkan dalam commit khusus dengan rename 100%, sedangkan raw evidence yang sebelumnya ignored ditambahkan ke arsip bertanggal.

## 2. Pemetaan path lama ke baru

### 2.1 Rules dan arsitektur

| Path lama | Path baru | Keputusan |
|---|---|---|
| `docs/cursor-ai/ALIZA_SYSTEM_PROMPT.md` | `docs/agent-rules/coding/coding-agent-context.md` | Pindah, current |
| `docs/cursor-ai/ALIZA_AI_BEHAVIOR_RULES.md` | `docs/agent-rules/coding/behavior-rules.md` | Pindah, current |
| `docs/cursor-ai/ALIZA_DEVELOPMENT_RULES.md` | `docs/agent-rules/coding/development-rules.md` | Pindah, current |
| `docs/cursor-ai/ALIZA_ENGINE_CONTRACTS.md` | `docs/architecture/engine-contracts.md` | Pindah, current |
| `docs/cursor-ai/ALIZA_ARCHITECTURE_MAP.md` | `docs/architecture/system-overview.md` | Pindah, current |
| `docs/instructions/system-prompt.md` | `docs/agent-rules/runtime/runtime-llm-system-prompt.md` | Pindah, current |
| `docs/instructions/ai-rules.md` | `docs/agent-rules/runtime/ai-output-rules.md` | Pindah dan referensi diperbarui |
| `docs/instructions/persona.md` | `docs/agent-rules/runtime/persona.md` | Pindah, current |
| `docs/instructions/intent-routing.md` | `docs/agent-rules/runtime/intent-routing.md` | Pindah dan referensi diperbarui |
| `docs/architecture/position-sizing.md` | tetap | Sudah berada di lokasi kanonik |

### 2.2 Debug dan test

| Sumber | Tujuan | Hasil |
|---|---|---|
| `ALIZA_DEBUG_PLAYBOOK.md` | `docs/runbooks/troubleshooting.md` | Prosedur detail lintas Telegram, snapshot, signal, DB, scheduler, dan dashboard |
| `ALIZA_SYSTEM_HEALTH_CHECK.md` | `docs/runbooks/health-check.md` | Checklist ringkas yang merujuk troubleshooting |
| `ALIZA_TEST_SYSTEM.md` | `docs/runbooks/smoke-test.md` | Verifikasi manual service/Telegram/API, termasuk Bearer auth dashboard |
| `ALIZA_TEST_SYSTEM.md` | `docs/architecture/testing.md` | Kebijakan unit/full suite, fixture DB, dan reproducibility backtest |

Duplikasi prosedur snapshot/signal/SQLite/scheduler di dua dokumen sumber dihapus saat pembagian ulang. Commit `6e54996` menyimpan rename sumber 100% sebelum rewrite di `f9d8bf4`, sehingga history sumber tetap dapat ditelusuri.

### 2.3 Arsip historis

| Path lama | Path baru |
|---|---|
| `docs/cursor-ai/ALIZA_CURRENT_SYSTEM_INSPECTION_REPORT.md` | `docs/audits/2026-06-02/system/current-system-inspection.md` |
| `docs/ALIZA_FULL_SYSTEM_AUDIT.md` | `docs/audits/2026-06-02/system/full-system-audit.md` |
| `docs/audit/2026-07-15/AUDIT_REPORT.md` | `docs/audits/2026-07-15/security/AUDIT_REPORT.md` |
| `docs/audit/2026-07-15/REMEDIATION_PLAN.md` | `docs/audits/2026-07-15/security/REMEDIATION_PLAN.md` |
| `docs/audit/2026-07-15/AUDIT_FINDINGS.json` | `docs/audits/2026-07-15/security/AUDIT_FINDINGS.json` |
| `docs/audit/runtime-20260715/README.md` | `docs/audits/2026-07-15/security/evidence/README.md` |
| `docs/audit/runtime-20260715/*.txt` | `docs/audits/2026-07-15/security/evidence/*.txt` |
| `docs/audit/runtime-20260716/*` | `docs/audits/2026-07-16/runtime-hardening/*` |
| `audit-output/00-ringkasan-eksekutif.md` | `docs/audits/2026-07-21/system-baseline-pre-fase/00-ringkasan-eksekutif.md` |
| `audit-output/01-struktur-repo.md` | `docs/audits/2026-07-21/system-baseline-pre-fase/01-struktur-repo.md` |
| `audit-output/02-arsitektur-dan-alur-data.md` | `docs/audits/2026-07-21/system-baseline-pre-fase/02-arsitektur-dan-alur-data.md` |
| `audit-output/03-logika-sinyal.md` | `docs/audits/2026-07-21/system-baseline-pre-fase/03-logika-sinyal.md` |
| `audit-output/04-risk-management-dan-winrate.md` | `docs/audits/2026-07-21/system-baseline-pre-fase/04-risk-management-dan-winrate.md` |
| `audit-output/05-konfigurasi-dan-operasional.md` | `docs/audits/2026-07-21/system-baseline-pre-fase/05-konfigurasi-dan-operasional.md` |
| `audit-output/06-kualitas-kode-dan-masalah.md` | `docs/audits/2026-07-21/system-baseline-pre-fase/06-kualitas-kode-dan-masalah.md` |
| `audit-output/07-perbandingan-dengan-docs.md` | `docs/audits/2026-07-21/system-baseline-pre-fase/07-perbandingan-dengan-docs.md` |
| `audit-output/FASE1B_DEPLOY_REPORT.md` | `docs/audits/2026-07-21/system-baseline-pre-fase/FASE1B_DEPLOY_REPORT.md` |
| `audit-output/FASE1C_VERIFIKASI_REPORT.md` | `docs/audits/2026-07-21/system-baseline-pre-fase/FASE1C_VERIFIKASI_REPORT.md` |

Isi arsip tidak ditulis ulang. Banner superseded dari Tahap 1 tetap dipertahankan.

## 3. Runbook dan indeks baru

| Dokumen | Isi |
|---|---|
| `docs/runbooks/troubleshooting.md` | Diagnosis berbasis bukti untuk Telegram, snapshot, opportunity/signal, SQLite, scheduler, alert, dan dashboard |
| `docs/runbooks/health-check.md` | Checklist singkat sesudah restart/deploy |
| `docs/runbooks/smoke-test.md` | Smoke test Telegram/snapshot/API; `/health` public dan endpoint dashboard wajib Bearer token |
| `docs/architecture/testing.md` | Pembagian test terarah/full suite/manual serta kontrak reproducibility |
| `docs/runbooks/graceful-shutdown.md` | Kontrak systemd 15 detik vs deadline aplikasi 8 detik, marker log, dua restart, dan rollback |
| `docs/runbooks/deploy-restart-rollback.md` | Precheck clean tree, backup DB bila migrasi, restart `aliza-telegram`, smoke test, revert commit, dan rollback DB |

`README.md`, `docs/README.md`, `CHANGELOG.md`, serta README bundle ekspor diperbarui ke struktur baru.

### Verifikasi deploy script

Output aktual `scripts/deploy/deploy.sh`:

```text
cd /home/ubuntu/aliza-ai
git pull origin main
sudo systemctl restart aliza-api
sudo systemctl restart aliza-telegram
```

Status: masih rusak/tidak authoritative untuk repo ini. Path server yang benar adalah `/opt/aliza-ai`; unit utama yang diverifikasi adalah `aliza-telegram`. Script tidak diedit karena file `.sh` berada di luar scope.

## 4. Verifikasi wajib

### 4.1 Pohon akhir

Output aktual `find docs -type f | sort` setelah laporan dibuat:

```text
docs/README.md
docs/agent-rules/coding/behavior-rules.md
docs/agent-rules/coding/coding-agent-context.md
docs/agent-rules/coding/development-rules.md
docs/agent-rules/runtime/ai-output-rules.md
docs/agent-rules/runtime/intent-routing.md
docs/agent-rules/runtime/persona.md
docs/agent-rules/runtime/runtime-llm-system-prompt.md
docs/architecture/engine-contracts.md
docs/architecture/position-sizing.md
docs/architecture/system-overview.md
docs/architecture/testing.md
docs/audits/2026-06-02/system/current-system-inspection.md
docs/audits/2026-06-02/system/full-system-audit.md
docs/audits/2026-07-15/security/AUDIT_FINDINGS.json
docs/audits/2026-07-15/security/AUDIT_REPORT.md
docs/audits/2026-07-15/security/REMEDIATION_PLAN.md
docs/audits/2026-07-15/security/evidence/README.md
docs/audits/2026-07-15/security/evidence/aliza-dashboard.service.txt
docs/audits/2026-07-15/security/evidence/aliza-telegram.service.txt
docs/audits/2026-07-15/security/evidence/dashboard-docs-disabled.txt
docs/audits/2026-07-15/security/evidence/dashboard-endpoint-auth.txt
docs/audits/2026-07-15/security/evidence/dashboard-jwt-foundation.txt
docs/audits/2026-07-15/security/evidence/dashboard-llm-execution-limits.txt
docs/audits/2026-07-15/security/evidence/dashboard-loopback-binding.txt
docs/audits/2026-07-15/security/evidence/dashboard-password-argon2id.txt
docs/audits/2026-07-15/security/evidence/dashboard-rate-limits.txt
docs/audits/2026-07-15/security/evidence/global-telegram-authorization.txt
docs/audits/2026-07-15/security/evidence/security-state.txt
docs/audits/2026-07-15/security/evidence/ufw-status.txt
docs/audits/2026-07-16/runtime-hardening/README.md
docs/audits/2026-07-16/runtime-hardening/dashboard-authenticated-functional-test-report.md
docs/audits/2026-07-16/runtime-hardening/dashboard-controlled-start-report.md
docs/audits/2026-07-16/runtime-hardening/dashboard-controlled-start-retry-report.md
docs/audits/2026-07-16/runtime-hardening/dashboard-controlled-start-retry2-report.md
docs/audits/2026-07-16/runtime-hardening/dashboard-controlled-start-retry3-report.md
docs/audits/2026-07-16/runtime-hardening/dashboard-db-auth-diagnosis.md
docs/audits/2026-07-16/runtime-hardening/dashboard-db-credential-remediation.md
docs/audits/2026-07-16/runtime-hardening/dashboard-dotenv-remediation.md
docs/audits/2026-07-16/runtime-hardening/dashboard-source-permission-remediation.md
docs/audits/2026-07-16/runtime-hardening/db-credential-consumer-impact-audit.md
docs/audits/2026-07-16/runtime-hardening/nginx-hardening-pre-reload-report.md
docs/audits/2026-07-16/runtime-hardening/nginx-reload-smoke-test.md
docs/audits/2026-07-16/runtime-hardening/systemd-hardening-stage1-report.md
docs/audits/2026-07-21/system-baseline-pre-fase/00-ringkasan-eksekutif.md
docs/audits/2026-07-21/system-baseline-pre-fase/01-struktur-repo.md
docs/audits/2026-07-21/system-baseline-pre-fase/02-arsitektur-dan-alur-data.md
docs/audits/2026-07-21/system-baseline-pre-fase/03-logika-sinyal.md
docs/audits/2026-07-21/system-baseline-pre-fase/04-risk-management-dan-winrate.md
docs/audits/2026-07-21/system-baseline-pre-fase/05-konfigurasi-dan-operasional.md
docs/audits/2026-07-21/system-baseline-pre-fase/06-kualitas-kode-dan-masalah.md
docs/audits/2026-07-21/system-baseline-pre-fase/07-perbandingan-dengan-docs.md
docs/audits/2026-07-21/system-baseline-pre-fase/FASE1B_DEPLOY_REPORT.md
docs/audits/2026-07-21/system-baseline-pre-fase/FASE1C_VERIFIKASI_REPORT.md
docs/reports/2026-07-21-maintenance/DOCS_AUDIT_REPORT.md
docs/reports/2026-07-21-maintenance/DOCS_QUICKWIN_REPORT.md
docs/reports/2026-07-21-maintenance/DOCS_RESTRUCTURE_REPORT.md
docs/reports/2026-07-21-maintenance/MAINTENANCE_REPORT.md
docs/reports/2026-07-21-maintenance/REPO_CLEANUP_REPORT.md
docs/reports/2026-07-21-maintenance/VPS_HEALTH_REPORT.md
docs/reports/phases/2026-07-21/fase-1/FASE1D_REPORT.md
docs/reports/phases/2026-07-21/fase-1/FASE1_REPORT.md
docs/reports/phases/2026-07-21/fase-2/BACKTEST_REPORT.md
docs/reports/phases/2026-07-21/fase-2/FASE2_REPORT.md
docs/reports/phases/2026-07-21/fase-3/EXPERIMENT_RESULTS.md
docs/reports/phases/2026-07-21/fase-3/FASE3_REPORT.md
docs/reports/phases/2026-07-21/fase-4/FASE4_REPORT.md
docs/reports/phases/2026-07-21/fase-4/ROBUSTNESS_RESULTS.md
docs/runbooks/deploy-restart-rollback.md
docs/runbooks/graceful-shutdown.md
docs/runbooks/health-check.md
docs/runbooks/smoke-test.md
docs/runbooks/troubleshooting.md
```

### 4.2 Duplikasi identik

Metode: SHA-256 seluruh `.md`/`.txt` di `docs/`, `AlizaAI-Crypto/`, dan root.

```text
FILES_HASHED=92
IDENTICAL_GROUPS_ALL_SCOPE=14
IDENTICAL_GROUPS_INSIDE_DOCS=0
```

Tidak ada duplikat identik di dalam sumber kanonik `docs/`. Empat belas grup seluruh scope adalah pasangan yang disengaja antara report kanonik dan bundle ekspor: BACKTEST, DOCS_AUDIT, DOCS_QUICKWIN, DOCS_RESTRUCTURE, EXPERIMENT, FASE1, FASE1D, FASE2, FASE3, FASE4, MAINTENANCE, REPO_CLEANUP, ROBUSTNESS, dan VPS_HEALTH.

### 4.3 Broken relative Markdown link

Checker memindai seluruh `docs/**/*.md`, mengabaikan fenced/inline code, URL eksternal, dan anchor-only.

```text
CHECKED_RELATIVE_LINKS=43
BROKEN_RELATIVE_LINKS=0
```

Contoh literal `[teks](target)` pada `DOCS_AUDIT_REPORT.md` adalah inline code dan bukan link.

### 4.4 Git status dan batas perubahan

Output sesudah dua commit inti:

```text
## docs/restructure-phase2
?? AlizaAI-Crypto/01-hasil-audit-codex/FASE1C_VERIFIKASI_REPORT.md
```

File untracked itu sudah ada sebelum Tahap 2 dan sengaja tidak disentuh. Pemeriksaan diff dari base:

```text
NON_DOC_EXTENSIONS_VS_0eab6d5=0
PYTHON_FILES_CHANGED=0
```

Ekstensi `.json` yang ditambahkan hanya `AUDIT_FINDINGS.json`, yaitu evidence dokumentasi lama yang dipindahkan sesuai scope. Tidak ada test Python dijalankan karena perubahan docs-only.

### 4.5 Bukti history

File baru dipindahkan:

```text
$ git log --follow --oneline -- docs/agent-rules/coding/coding-agent-context.md
6e54996 docs: move documentation into canonical structure
0eab6d5 docs: apply documentation quick wins
ee1ffca fix: market_bot circuit breaker — tambah snapshot_updater_loop
```

Kontrol file yang pernah dipindah Tahap 1:

```text
$ git log --follow --oneline -- docs/reports/phases/2026-07-21/fase-1/FASE1_REPORT.md
0eab6d5 docs: apply documentation quick wins
5cfd25c docs(fase1): add signal integrity report
```

### 4.6 Ukuran sebelum/sesudah

```text
SEBELUM:
616K  docs
120K  audit-output

SESUDAH:
796K  docs
audit-output: NOT_FOUND
```

Pertumbuhan `docs/` berasal dari penggabungan seluruh raw evidence yang sebelumnya ignored dan folder `audit-output/` ke arsip kanonik, bukan duplikasi internal.

### 4.7 Folder lama dan whitespace

```text
docs/cursor-ai: NOT_FOUND
docs/instructions: NOT_FOUND
docs/audit: NOT_FOUND
audit-output: NOT_FOUND
```

`git diff --check` untuk commit isi aktif lulus. Commit pemindahan murni melaporkan trailing spaces pada alignment raw `ufw-status.txt`; file evidence tersebut dipertahankan verbatim dan tidak dinormalisasi.

## 5. Gap tersisa

| Prioritas | Gap | Status/tindakan berikut |
|---|---|---|
| P1 | `.env.example` | Empat flag penting belum terdokumentasi lengkap; sengaja di luar scope Tahap 2 |
| P1 | `docs/configuration/reference.md` | Belum ada; buat bersama audit default/type/range/restart requirement |
| P1 | Deploy script | `scripts/deploy/deploy.sh` masih memakai path/unit salah; perlu prompt kode terpisah |
| P1 | Current system status | Ringkasan tunggal Fase 1–4 dan shadow state belum dibuat |
| P1 | Shadow E3 runbook | Aktivasi, observability, promosi, dispatch risk, dan rollback flag belum menjadi runbook |
| P2 | ADR service ownership | Keputusan `aliza-telegram` sebagai scheduler tunggal dan status unit legacy belum dicatat sebagai ADR |
| P2 | Testing guide lanjutan | Baseline `docs/architecture/testing.md` selesai; CI ownership, integration fixture matrix, dan coverage target belum didefinisikan |
| P2 | Audit manifests | README rinci per folder audit belum konsisten; indeks global sudah tersedia di `docs/README.md` |

## 6. Kesimpulan

Struktur akhir bersih dan tersegmentasi, history tracked terjaga, broken relative link aktual nol, dan tidak ada duplikat identik di dalam `docs/`. Branch belum di-merge atau di-push; keputusan integrasi tetap pada user.
