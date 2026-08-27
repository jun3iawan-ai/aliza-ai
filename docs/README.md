# Dokumentasi Aliza AI

Folder `docs/` adalah sumber kanonik dokumentasi manusia. Struktur memisahkan aturan aktif, arsitektur, prosedur operasional, report implementasi, dan audit historis.

## Indeks

| Lokasi | Status | Isi |
|---|---|---|
| [agent-rules/coding/](agent-rules/coding/) | current | Konteks dan guardrail untuk coding agent. |
| [agent-rules/runtime/](agent-rules/runtime/) | current | System prompt, persona, routing, dan aturan output runtime LLM. |
| [architecture/](architecture/) | current | Overview sistem, engine contracts, position sizing, dan strategi testing. |
| [runbooks/](runbooks/) | current | Health check, troubleshooting, smoke test, deploy/restart/rollback, dan graceful shutdown. |
| [reports/](reports/) | historical (fase/maintenance) + current (fitur pasca-maintenance) | Report fase, eksperimen, robustness, maintenance bertanggal, serta report audit/deploy fitur pasca-maintenance 21 Juli 2026 (current, belum superseded). |
| [audits/](audits/) | historical/superseded | Audit sistem/security dan raw evidence yang dipertahankan sebagai audit trail. |

Folder lama `docs/cursor-ai/`, `docs/instructions/`, dan `docs/audit/` sudah digantikan oleh struktur di atas dan tidak boleh dibuat kembali.

## Aturan aktif

### Coding agent

- [Coding agent context](agent-rules/coding/coding-agent-context.md)
- [Behavior rules](agent-rules/coding/behavior-rules.md)
- [Development rules](agent-rules/coding/development-rules.md)

### Runtime LLM

- [Runtime system prompt](agent-rules/runtime/runtime-llm-system-prompt.md)
- [AI output rules](agent-rules/runtime/ai-output-rules.md)
- [Persona](agent-rules/runtime/persona.md)
- [Intent routing](agent-rules/runtime/intent-routing.md)

### Arsitektur

- [System overview](architecture/system-overview.md)
- [Engine contracts](architecture/engine-contracts.md)
- [Position sizing](architecture/position-sizing.md)
- [Testing](architecture/testing.md)

### Runbook

- [Health check](runbooks/health-check.md)
- [Troubleshooting](runbooks/troubleshooting.md)
- [Smoke test](runbooks/smoke-test.md)
- [Deploy, restart, rollback](runbooks/deploy-restart-rollback.md)
- [Graceful shutdown](runbooks/graceful-shutdown.md)

## Report kanonik

- [Fase 1](reports/phases/2026-07-21/fase-1/): integritas sinyal dan observability universe.
- [Fase 2](reports/phases/2026-07-21/fase-2/): backtester event-driven dan hasil baseline.
- [Fase 3](reports/phases/2026-07-21/fase-3/): eksperimen dan holdout.
- [Fase 4](reports/phases/2026-07-21/fase-4/): robustness E3 dan shadow mode.
- [Maintenance 21 Juli](reports/2026-07-21-maintenance/): VPS health, cleanup, shutdown, dan audit/perapian dokumentasi.

### Report fitur pasca-maintenance (current)

- [21 Juli — deploy pasca-maintenance](reports/2026-07-21-post-maintenance/): audit & deploy fitur berita, evening summary, notifikasi, dan merge/push fix `deploy.sh` (commit `aded2b3`).
- [25 Juli — evaluasi & winrate](reports/2026-07-25-evaluasi-winrate/): audit mekanisme evaluasi/pembelajaran dan status winrate sinyal.
- [27 Juli — signal re-arm](reports/2026-07-27-signal-rearm/): audit re-fire `[TRADE SIGNAL]` dan implementasi edge-triggered re-arm.
- [5 Agustus — perbaikan sinyal](reports/2026-08-05-signal-fixes/): evaluasi big-move alert, near-level on-demand, dan fix big-move 1h sungguhan.
- [5 Agustus — restrukturisasi menu Telegram](reports/2026-08-05-telegram-menu-restructure/): audit menu lengkap dan restrukturisasi menu Telegram.
- [21 Agustus — Info Coin](reports/2026-08-21-info-coin/): audit menu informasi dan implementasi Info Coin Paket 1.
- [27 Agustus — VPS health & shadow E3](reports/2026-08-27-vps-health-shadow-e3/): VPS health report #2, investigasi stagnasi shadow_e3, merge/push `docs/beres-beres`+fix message-too-long, merge/push shadow_e3 observability, dan audit risiko "Message is too long" di 172 titik `reply_text()` command interaktif.

## Audit historis

| Lokasi | As-of | Status |
|---|---|---|
| [2026-06-02/system/](audits/2026-06-02/system/) | 2 Juni 2026 | Superseded system inspection/audit. |
| [2026-07-15/security/](audits/2026-07-15/security/) | 15 Juli 2026 | Audit security dan raw evidence. |
| [2026-07-16/runtime-hardening/](audits/2026-07-16/runtime-hardening/) | 16 Juli 2026 | Evidence dan report hardening runtime. |
| [2026-07-21/system-baseline-pre-fase/](audits/2026-07-21/system-baseline-pre-fase/) | 21 Juli 2026 pagi | Baseline superseded sebelum Fase 1–4. |

## Di luar sumber kanonik

- [Bundle ekspor](../AlizaAI-Crypto/01-hasil-audit-codex/) adalah salinan untuk workflow eksternal; jangan diedit langsung.
- `knowledge/documents/` adalah material knowledge/RAG, bukan aturan dokumentasi repo.
- `memory/` adalah state/artefak aplikasi, bukan dokumentasi manusia.

## Pemeliharaan

1. Edit hanya lokasi kanonik di `docs/`.
2. Beri report metadata tanggal/commit dan jangan menulis ulang fakta historis agar terlihat current.
3. Perbarui link saat file dipindah; validasi seluruh relative Markdown link.
4. Sinkronkan bundle ekspor dari report kanonik setelah perubahan disetujui.
5. Jangan menaruh secret, token, credential, atau isi `.env` di dokumentasi.

