# 07 — Perbandingan Kode dengan Dokumentasi

> **Status: SUPERSEDED.** Snapshot pada 2026-07-21. Kondisi sistem terkini ada di `docs/README.md` dan report Fase 1–4 (`docs/reports/` — lihat Bagian 3). Jangan jadikan dokumen ini sebagai acuan status aktif.

## Inventaris seluruh dokumen

Ada 43 file di `docs/`. Ringkasan berikut menyebut semuanya.

### Dokumen umum dan arsitektur

| File | Ringkasan |
|---|---|
| `docs/ALIZA_FULL_SYSTEM_AUDIT.md` | Audit 14 Maret 2026: health, pipeline, warning dan rekomendasi; menyatakan tidak ada critical bug saat itu. |
| `docs/architecture/position-sizing.md` | Desain fixed-fractional sizing, sumber saldo, integrasi risk manager dan roadmap implementasi. |

### `docs/cursor-ai/`

| File | Ringkasan |
|---|---|
| `ALIZA_AI_BEHAVIOR_RULES.md` | Guardrail perubahan: jangan ubah arsitektur/data/command tanpa permintaan. |
| `ALIZA_ARCHITECTURE_MAP.md` | Peta interface → snapshot → trading/intelligence/risk/database. |
| `ALIZA_CURRENT_SYSTEM_INSPECTION_REPORT.md` | Inspeksi 17 Maret 2026 atas struktur, Telegram, pipeline, fungsi hilang dan mismatch docs. |
| `ALIZA_DEBUG_PLAYBOOK.md` | Langkah diagnosis bot, market data, signal, scanner, DB, import dan regresi. |
| `ALIZA_DEVELOPMENT_RULES.md` | Aturan kontribusi: trade manager sebagai jalur DB, handler non-blocking, kontrak struktur. |
| `ALIZA_ENGINE_CONTRACTS.md` | Kontrak dictionary market/snapshot/setup/opportunity/signal. |
| `ALIZA_SYSTEM_HEALTH_CHECK.md` | Checklist service, command, snapshot, analyzer, scanner dan database. |
| `ALIZA_SYSTEM_PROMPT.md` | Deskripsi tujuan, struktur dan perilaku sistem untuk konteks AI. |
| `ALIZA_TEST_SYSTEM.md` | Checklist manual market pipeline, setup, scanner, gateway dan DB. |

### `docs/instructions/`

| File | Ringkasan |
|---|---|
| `ai-rules.md` | Aturan sumber market yang sah, larangan mengarang harga, disclaimer dan penyajian signal. |
| `intent-routing.md` | Diagram/decision tree intent dan prosedur menambah intent. |
| `persona.md` | Persona Aliza sebagai asisten analitis, bukan oracle. |
| `system-prompt.md` | System prompt runtime yang menjelaskan identitas, kapabilitas dan batasan. |

### Audit utama 15 Juli 2026

| File | Ringkasan |
|---|---|
| `audit/2026-07-15/AUDIT_FINDINGS.json` | Register temuan terstruktur ALIZA-001 dst., severity, evidence dan rekomendasi. |
| `audit/2026-07-15/AUDIT_REPORT.md` | Audit trading/security menyeluruh; skor rendah/research-only, trace signal dan temuan kritis. |
| `audit/2026-07-15/REMEDIATION_PLAN.md` | Urutan containment, P0/P1/P2 untuk closed candle, MTF, tracking, security, testing dan live readiness. |

### Bukti runtime 15 Juli 2026

| File | Ringkasan |
|---|---|
| `audit/runtime-20260715/aliza-dashboard.service.txt` | Snapshot unit dashboard sebelum/selama hardening. |
| `audit/runtime-20260715/aliza-telegram.service.txt` | Snapshot unit Telegram. |
| `audit/runtime-20260715/dashboard-docs-disabled.txt` | Bukti Swagger/OpenAPI/Redoc dimatikan default. |
| `audit/runtime-20260715/dashboard-endpoint-auth.txt` | Bukti endpoint dashboard dilindungi auth/role. |
| `audit/runtime-20260715/dashboard-jwt-foundation.txt` | Bukti foundation JWT dan validasi secret. |
| `audit/runtime-20260715/dashboard-llm-execution-limits.txt` | Bukti timeout dan concurrency limiter LLM. |
| `audit/runtime-20260715/dashboard-loopback-binding.txt` | Bukti binding default loopback. |
| `audit/runtime-20260715/dashboard-password-argon2id.txt` | Bukti migrasi hashing Argon2id/legacy. |
| `audit/runtime-20260715/dashboard-rate-limits.txt` | Bukti rate limit endpoint. |
| `audit/runtime-20260715/global-telegram-authorization.txt` | Bukti global allowlist/authorization Telegram. |
| `audit/runtime-20260715/security-state.txt` | Ringkasan state keamanan host/aplikasi setelah remediasi. |
| `audit/runtime-20260715/ufw-status.txt` | Bukti status firewall UFW saat pemeriksaan. |

### Bukti runtime 16 Juli 2026

| File | Ringkasan |
|---|---|
| `audit/runtime-20260716/dashboard-authenticated-functional-test-report.md` | Rencana/evidence functional test authenticated; status `NEED_INTERACTIVE_OPERATOR`, tidak dijalankan penuh. |
| `dashboard-controlled-start-report.md` | Start pertama gagal restart-loop karena service tidak dapat membaca legacy `.env`; service dikembalikan inactive. |
| `dashboard-controlled-start-retry-report.md` | Retry gagal karena permission `core/environment.py`; containment berhasil. |
| `dashboard-controlled-start-retry2-report.md` | Retry kedua lolos source permission tetapi gagal autentikasi PostgreSQL. |
| `dashboard-controlled-start-retry3-report.md` | Uji akhir PASS WITH WARNINGS: loopback, health, 401/404, resource dan shutdown lolos; service tetap disabled. |
| `dashboard-db-auth-diagnosis.md` | Diagnosis kegagalan kredensial PostgreSQL dashboard tanpa mencatat secret. |
| `dashboard-db-credential-remediation.md` | Bukti sinkronisasi/remediasi credential consumer dashboard. |
| `dashboard-dotenv-remediation.md` | Pemisahan dashboard dari legacy repo `.env`. |
| `dashboard-source-permission-remediation.md` | Perbaikan read-only source untuk akun service khusus. |
| `db-credential-consumer-impact-audit.md` | Analisis dampak perubahan credential pada consumer DB lain. |
| `nginx-hardening-pre-reload-report.md` | Pemeriksaan config/route/security header sebelum reload Nginx. |
| `nginx-reload-smoke-test.md` | Bukti reload dan smoke test Nginx. |
| `systemd-hardening-stage1-report.md` | Bukti hardening account, filesystem, capability, address family dan write path dashboard. |

## Klaim docs yang sesuai dengan kode saat ini

- Peta besar snapshot → TradingBrain → opportunity/signal → Telegram masih akurat (`ALIZA_ARCHITECTURE_MAP.md`, `ALIZA_ENGINE_CONTRACTS.md`).
- Batas sistem sebagai asisten/rekomendasi, bukan oracle, sesuai kenyataan: tidak ada execution order (`instructions/persona.md`, `ai-rules.md`).
- Position sizing fixed-fractional yang dirancang di `architecture/position-sizing.md` sudah diimplementasikan di `engine/position_sizer.py` dan terhubung ke scanner.
- Temuan audit 15 Juli tentang candle aktif, MTF fallback palsu, tidak ada backtest/execution, tracker lemah dan auto-alert score mismatch masih valid.
- Bukti hardening dashboard/Telegram cocok dengan source: JWT, Argon2, rate limit, LLM execution limit, docs disabled, loopback default dan global Telegram authorization tersedia.
- Keadaan akhir dashboard sesuai runtime doc terakhir: service disabled/inactive setelah uji terkontrol.

## Klaim docs yang sudah usang atau salah

### Audit/inspeksi Maret

- `ALIZA_FULL_SYSTEM_AUDIT.md` menyatakan tidak ada critical bug. Kode kini memiliki defect deterministik auto-alert, short tracker dan pre-dispatch tracking; klaim tidak lagi benar.
- `ALIZA_CURRENT_SYSTEM_INSPECTION_REPORT.md` menyatakan snapshot tidak mempunyai updater/job berjalan dan beberapa intelligence belum tersedia. Saat ini `update_market_snapshot()` dijadwalkan per 60 detik dan `market_intelligence.py` ada.
- Sebagian command/job yang dahulu dinyatakan belum tersambung kini aktif di `telegram_bot.py`.
- Sebaliknya, file opsional `predictive_market_ai.py` dan `quant_market_model.py` masih tidak ada; fallback `unavailable` tetap nyata.

### Position sizing

- `architecture/position-sizing.md` menggambarkan beberapa bagian sebagai “belum ada”; sizing utama kini ada.
- Dokumen belum mencerminkan dua implementation aktif (utama dan legacy), max total risk 6%, signed balance lookup, atau fragmentasi JSON/SQLite.

### Development contracts

- `ALIZA_DEVELOPMENT_RULES.md` menyatakan Trade Manager satu-satunya modul DB, tetapi `signal_tracker.py`, `state_store.py`, `user_config.py` dan `core/database.py` juga mengakses DB/state.
- Aturan handler Telegram tidak memanggil API secara langsung tidak sepenuhnya dipatuhi; beberapa handler/report/news/macro melakukan request eksternal atau memicu fungsi yang melakukannya.
- Kontrak snapshot mengasumsikan freshness/shape yang stabil, tetapi runtime menerima snapshot parsial dan fallback MTF dapat memalsukan semantik timeframe.

### Config/model

- `config/agent.yaml` dan sebagian system prompt menyebut `gpt-4o`; runtime utama `core/agent.py` memakai `gpt-4o-mini`.
- Dokumentasi “AI prediction” mudah dibaca sebagai model prediktif; kenyataannya sebagian besar heuristic scoring, dan dua modul predictive/quant yang dirujuk tidak tersedia.

### Operasional

- Script deploy/path lama tidak tercermin jelas dalam docs operasional: repo berjalan dari `/opt/aliza-ai`, sedangkan script memakai `/home/ubuntu/aliza-ai`.
- Watchlist market service di memori masih tujuh coin dari source lama, sementara docs/source current menggambarkan universe lebih besar.
- Docstring spot scheduler menyatakan enam kali sehari; actual tiga kali.

## Fitur terdokumentasi tetapi tidak ada/tidak efektif di kode

- Model predictive AI/quant: import opsional ada, file implementasi tidak ada.
- Auto-alert opportunity: komponen ada, tetapi threshold 160 vs score maksimum 100 membuatnya tidak efektif.
- Dynamic universe top-200: tidak aktif; source memaksa 21 core coin dan implementasi fetch hanya 50.
- Market health/readiness menyeluruh: docs checklist ada, endpoint `/health` hanya status statis.
- Backtesting, walk-forward, execution/live protection: direkomendasikan docs audit, belum diimplementasikan.
- Beberapa strategy map (`MOMENTUM`, `BREAKOUT LONG`) tidak punya producer di TradingBrain.
- Functional test dashboard authenticated lengkap: dokumen menyatakan `NEED_INTERACTIVE_OPERATOR`, sehingga belum menjadi bukti kelulusan end-to-end authenticated.

## Fitur kode yang kurang/tidak terdokumentasi

- Jalur laporan LLM spot/futures yang memaksa SL 5–8% dan TP minimal 2R, lalu parser memasukkannya ke signal tracking.
- Dual process snapshot/polling dan konsekuensi cache in-memory per proses.
- Double scheduling RSI/outcome.
- Core universe aktual 21 coin exotic serta kegagalan rutin empat coin.
- Detail short-detection bug dan urutan record-before-dispatch.
- Dua risk manager/two position sizer dengan default berbeda.
- Stablecoin label mismatch, funding threshold mismatch dan BTC candle-input mismatch.
- 103 backup harian di folder interface.

## Penilaian dokumentasi

Dokumentasi keamanan 15–16 Juli adalah bagian paling kuat: spesifik, ber-evidence dan sesuai source/runtime saat ini. Dokumen arsitektur Maret berguna sebagai intent, tetapi tidak boleh dijadikan source of truth operasional. Audit 15 Juli masih paling dekat dengan kenyataan trading, namun perlu addendum untuk perubahan Juli 21 dan temuan tracker/LLM/runtime stale service dalam audit ini.

Rekomendasi: tetapkan satu `CURRENT_ARCHITECTURE.md` versioned yang dihasilkan dari kontrak actual, dan pisahkan jelas status `implemented`, `optional/unavailable`, `disabled`, serta `planned`. Tambahkan matriks traceability docs → file/function → test untuk setiap strategi dan security control.
