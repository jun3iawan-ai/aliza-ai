# Dokumentasi Aliza AI

Dokumen ini adalah indeks dan source of truth untuk dokumentasi repo. Status menunjukkan apakah isi dimaksudkan sebagai aturan aktif atau snapshot historis; report historis tidak boleh dipakai sebagai status runtime tanpa memeriksa tanggal dan commit-nya.

## Indeks folder

| Lokasi | Status | Isi |
|---|---|---|
| [architecture/](architecture/) | current | Dokumen arsitektur tematik, termasuk position sizing. Verifikasi terhadap kode tetap diperlukan saat parameter berubah. |
| [cursor-ai/](cursor-ai/) | mixed: current + superseded | Rules untuk coding agent berada di sini dan tetap aktif untuk sementara. `ALIZA_CURRENT_SYSTEM_INSPECTION_REPORT.md` adalah snapshot superseded. Folder akan direstrukturisasi pada tahap berikutnya. |
| [instructions/](instructions/) | current | Rules untuk runtime LLM, persona, system prompt, dan intent routing. Ini berbeda dari rules coding agent di `cursor-ai/`. |
| [audit/](audit/) | historical / superseded | Audit keamanan dan raw evidence 15–16 Juli 2026. Gunakan untuk jejak audit, bukan status aktif. |
| [reports/](reports/) | historical, canonical | Lokasi kanonik report Fase 1–4 dan audit maintenance 21 Juli 2026. Report mencatat kondisi pada waktu tertentu. |

## Report kanonik 21 Juli 2026

- [Fase 1](reports/phases/2026-07-21/fase-1/): integritas sinyal dan observability universe.
- [Fase 2](reports/phases/2026-07-21/fase-2/): backtester event-driven dan hasil baseline.
- [Fase 3](reports/phases/2026-07-21/fase-3/): eksperimen dan holdout.
- [Fase 4](reports/phases/2026-07-21/fase-4/): robustness E3 dan shadow mode.
- [Audit maintenance](reports/2026-07-21-maintenance/): VPS health, cleanup repo, graceful shutdown, dan audit dokumentasi.

## Dokumen di luar `docs/`

- [audit-output/](../audit-output/) adalah baseline pra-Fase pada pagi 21 Juli 2026 dan berstatus superseded.
- [AlizaAI-Crypto/01-hasil-audit-codex/](../AlizaAI-Crypto/01-hasil-audit-codex/) adalah bundle ekspor read-only, bukan lokasi pengeditan kanonik.
- `knowledge/documents/` berisi material knowledge/RAG, bukan rules dokumentasi repo.
- `memory/` adalah state/artefak aplikasi, bukan dokumentasi manusia.

## Aturan pemeliharaan

1. Edit report dan rules pada lokasi kanonik di `docs/`.
2. Beri report bertanggal metadata waktu/commit dan status historical bila menggambarkan snapshot.
3. Jangan mengubah isi report historis untuk mengikuti keadaan baru; tambahkan banner superseded atau report baru.
4. Sinkronkan bundle ekspor hanya dari sumber kanonik setelah perubahan disetujui.

