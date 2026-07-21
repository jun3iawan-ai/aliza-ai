# Audit Dokumentasi Aliza AI

Waktu audit: **21 Juli 2026 (WIB)**  
Repo: `/opt/aliza-ai`  
Branch/HEAD saat audit: `main` / `f38ab55` (`main` sama dengan `origin/main`)  
Sifat audit: **read-only terhadap file yang diaudit**; tidak ada file lama yang diedit, dipindah, dihapus, atau di-commit. Hanya laporan ini dan salinan identiknya yang dibuat. Nilai secret tidak dibaca atau ditulis; pemeriksaan `.env` dibatasi pada empat flag non-secret.

## 1. Ringkasan eksekutif

**Kondisi umum: PERLU RAPIKAN.** Isi dokumentasi sebenarnya kaya dan banyak report memiliki bukti yang baik, tetapi belum ada satu indeks atau lokasi kanonik. Snapshot historis, rules aktif, output audit, dan salinan ekspor bercampur; akibatnya pembaca mudah mengambil klaim yang benar pada pagi 21 Juli sebagai kondisi aktif setelah Fase 1–4 dan maintenance siang hari.

Hasil inventaris aktual:

| Metrik | Hasil |
|---|---:|
| File | 79 |
| Markdown | 63 |
| Teks | 16 |
| Ukuran total | 535.965 byte (523,4 KiB / 0,51 MiB) |
| Tracked | 33 |
| Untracked | 46 |
| Pasangan salinan identik | 12 |
| Byte redundan pada satu sisi pasangan identik | 88.592 byte (86,5 KiB) |
| `README.md` root | Tidak ada |
| `CHANGELOG.md` | Tidak ada |
| `AGENTS.md` / `CLAUDE.md` | Tidak ada |
| README di `docs/`, `audit-output/`, dan folder audit tujuan | Tidak ada |

Bukti perintah aktual:

```text
$ find ... -iname '*.md' / '*.txt' + stat/wc/git log
md=63 txt=16 total=79 bytes=535965

$ git ls-files --error-unmatch ...
tracked=33 untracked=46 total=79

$ git rev-list --left-right --count origin/main...HEAD
0  0

$ find docs audit-output AlizaAI-Crypto/01-hasil-audit-codex -maxdepth 2 -iname 'README*'
(tidak ada output)
```

Masalah paling berdampak:

1. `docs/cursor-ai/ALIZA_CURRENT_SYSTEM_INSPECTION_REPORT.md` masih menyatakan bot tidak punya background job dan snapshot/signal engine tidak dipanggil. Kode kini memanggil initial snapshot, menjadwalkan snapshot 60 detik, memanggil scanner produksi, serta E3 shadow.
2. `audit-output/00`–`07` adalah snapshot pra-Fase pada pagi 21 Juli. Temuan threshold auto-alert 160, tracker rusak, candle aktif, tidak adanya backtester, dan dua service aktif telah ditangani. Folder itu perlu label **historis/superseded**, bukan dihapus tanpa review.
3. Rules coding dan rules runtime memakai nama hampir sama tetapi audiens berbeda. Keduanya perlu dipertahankan dengan nama/lokasi yang menjelaskan fungsi, bukan digabung buta.
4. Root report dan folder `AlizaAI-Crypto/01-hasil-audit-codex/` menggandakan file byte-for-byte; tidak ada penanda mana yang kanonik.
5. Report maintenance 13:51–14:03 menyatakan service belum restart. Itu benar pada waktu report, tetapi sudah usang sebagai status aktif: systemd mencatat restart bersih pukul 14:07 dan proses aktif sejak 14:07:22.

## 2. Inventaris lengkap

Kolom **Tanggal** adalah `git log -1 --format=%ci -- <file>` untuk file tracked. Untuk file untracked, Git tidak mempunyai tanggal; yang ditampilkan adalah filesystem mtime lokal server. Ukuran adalah byte dan baris berasal dari `wc -l`.

### Ringkasan per folder

| Folder | File | Byte |
|---|---:|---:|
| Root repo | 13 | 82.584 |
| `AlizaAI-Crypto/01-hasil-audit-codex/` | 12 | 88.592 |
| `audit-output/` | 10 | 95.344 |
| `docs/` langsung | 1 | 12.151 |
| `docs/architecture/` | 1 | 11.190 |
| `docs/audit/2026-07-15/` | 2 | 43.984 |
| `docs/audit/runtime-20260715/` | 12 | 5.794 |
| `docs/audit/runtime-20260716/` | 13 | 106.130 |
| `docs/cursor-ai/` | 9 | 37.247 |
| `docs/instructions/` | 4 | 51.704 |
| `knowledge/documents/` | 1 | 1.107 |
| `memory/` | 1 | 138 |

### `AlizaAI-Crypto/01-hasil-audit-codex/`

| Path | Byte | Baris | Git | Tanggal |
|---|---:|---:|---|---|
| `AlizaAI-Crypto/01-hasil-audit-codex/BACKTEST_REPORT.md` | 4142 | 58 | tracked | 2026-07-21 10:43:19 +0700 |
| `AlizaAI-Crypto/01-hasil-audit-codex/EXPERIMENT_RESULTS.md` | 5347 | 91 | tracked | 2026-07-21 12:17:54 +0700 |
| `AlizaAI-Crypto/01-hasil-audit-codex/FASE1C_VERIFIKASI_REPORT.md` | 6788 | 155 | untracked | 2026-07-21 09:44:54 |
| `AlizaAI-Crypto/01-hasil-audit-codex/FASE1D_REPORT.md` | 4013 | 80 | untracked | 2026-07-21 10:10:33 |
| `AlizaAI-Crypto/01-hasil-audit-codex/FASE1_REPORT.md` | 6223 | 120 | tracked | 2026-07-21 08:58:32 +0700 |
| `AlizaAI-Crypto/01-hasil-audit-codex/FASE2_REPORT.md` | 3322 | 49 | tracked | 2026-07-21 10:44:54 +0700 |
| `AlizaAI-Crypto/01-hasil-audit-codex/FASE3_REPORT.md` | 3902 | 34 | tracked | 2026-07-21 12:16:23 +0700 |
| `AlizaAI-Crypto/01-hasil-audit-codex/FASE4_REPORT.md` | 3295 | 33 | tracked | 2026-07-21 12:43:17 +0700 |
| `AlizaAI-Crypto/01-hasil-audit-codex/MAINTENANCE_REPORT.md` | 18905 | 546 | untracked | 2026-07-21 14:05:29 |
| `AlizaAI-Crypto/01-hasil-audit-codex/REPO_CLEANUP_REPORT.md` | 15423 | 408 | untracked | 2026-07-21 13:20:56 |
| `AlizaAI-Crypto/01-hasil-audit-codex/ROBUSTNESS_RESULTS.md` | 4032 | 71 | tracked | 2026-07-21 12:43:53 +0700 |
| `AlizaAI-Crypto/01-hasil-audit-codex/VPS_HEALTH_REPORT.md` | 13200 | 335 | untracked | 2026-07-21 13:19:38 |

### Root repo

| Path | Byte | Baris | Git | Tanggal |
|---|---:|---:|---|---|
| `BACKTEST_REPORT.md` | 4142 | 58 | tracked | 2026-07-21 10:43:19 +0700 |
| `EXPERIMENT_RESULTS.md` | 5347 | 91 | tracked | 2026-07-21 12:17:54 +0700 |
| `FASE1D_REPORT.md` | 4013 | 80 | untracked | 2026-07-21 10:10:33 |
| `FASE1_REPORT.md` | 6223 | 120 | tracked | 2026-07-21 08:58:32 +0700 |
| `FASE2_REPORT.md` | 3322 | 49 | tracked | 2026-07-21 10:44:54 +0700 |
| `FASE3_REPORT.md` | 3902 | 34 | tracked | 2026-07-21 12:16:23 +0700 |
| `FASE4_REPORT.md` | 3295 | 33 | tracked | 2026-07-21 12:43:17 +0700 |
| `MAINTENANCE_REPORT.md` | 18905 | 546 | untracked | 2026-07-21 14:05:29 |
| `REPO_CLEANUP_REPORT.md` | 15423 | 408 | untracked | 2026-07-21 13:20:56 |
| `ROBUSTNESS_RESULTS.md` | 4032 | 71 | tracked | 2026-07-21 12:43:53 +0700 |
| `VPS_HEALTH_REPORT.md` | 13200 | 335 | untracked | 2026-07-21 13:17:56 |
| `requirements-dev.txt` | 70 | 4 | tracked | 2026-06-02 13:32:30 +0700 |
| `requirements.txt` | 710 | 38 | tracked | 2026-07-16 07:45:14 +0700 |

### `audit-output/`

| Path | Byte | Baris | Git | Tanggal |
|---|---:|---:|---|---|
| `audit-output/00-ringkasan-eksekutif.md` | 9004 | 74 | untracked | 2026-07-21 08:26:44 |
| `audit-output/01-struktur-repo.md` | 11955 | 227 | untracked | 2026-07-21 08:17:27 |
| `audit-output/02-arsitektur-dan-alur-data.md` | 8546 | 121 | untracked | 2026-07-21 08:18:19 |
| `audit-output/03-logika-sinyal.md` | 16541 | 268 | untracked | 2026-07-21 08:20:03 |
| `audit-output/04-risk-management-dan-winrate.md` | 7694 | 125 | untracked | 2026-07-21 08:20:51 |
| `audit-output/05-konfigurasi-dan-operasional.md` | 8887 | 155 | untracked | 2026-07-21 08:22:36 |
| `audit-output/06-kualitas-kode-dan-masalah.md` | 10420 | 164 | untracked | 2026-07-21 08:24:19 |
| `audit-output/07-perbandingan-dengan-docs.md` | 10717 | 145 | untracked | 2026-07-21 08:25:39 |
| `audit-output/FASE1B_DEPLOY_REPORT.md` | 4792 | 132 | untracked | 2026-07-21 09:10:22 |
| `audit-output/FASE1C_VERIFIKASI_REPORT.md` | 6788 | 155 | untracked | 2026-07-21 09:44:42 |

### `docs/`, `docs/architecture/`, dan audit 15 Juli

| Path | Byte | Baris | Git | Tanggal |
|---|---:|---:|---|---|
| `docs/ALIZA_FULL_SYSTEM_AUDIT.md` | 12151 | 199 | tracked | 2026-06-02 13:32:30 +0700 |
| `docs/architecture/position-sizing.md` | 11190 | 362 | tracked | 2026-06-02 13:32:30 +0700 |
| `docs/audit/2026-07-15/AUDIT_REPORT.md` | 34477 | 415 | untracked | 2026-07-15 12:13:41 |
| `docs/audit/2026-07-15/REMEDIATION_PLAN.md` | 9507 | 164 | untracked | 2026-07-15 12:13:41 |
| `docs/audit/runtime-20260715/aliza-dashboard.service.txt` | 439 | 20 | untracked | 2026-07-15 13:48:08 |
| `docs/audit/runtime-20260715/aliza-telegram.service.txt` | 444 | 20 | untracked | 2026-07-15 13:48:08 |
| `docs/audit/runtime-20260715/dashboard-docs-disabled.txt` | 379 | 8 | untracked | 2026-07-16 07:34:41 |
| `docs/audit/runtime-20260715/dashboard-endpoint-auth.txt` | 481 | 10 | untracked | 2026-07-16 07:24:06 |
| `docs/audit/runtime-20260715/dashboard-jwt-foundation.txt` | 333 | 8 | untracked | 2026-07-15 17:23:49 |
| `docs/audit/runtime-20260715/dashboard-llm-execution-limits.txt` | 544 | 12 | untracked | 2026-07-16 08:04:37 |
| `docs/audit/runtime-20260715/dashboard-loopback-binding.txt` | 286 | 6 | untracked | 2026-07-15 17:11:14 |
| `docs/audit/runtime-20260715/dashboard-password-argon2id.txt` | 413 | 9 | untracked | 2026-07-16 07:45:25 |
| `docs/audit/runtime-20260715/dashboard-rate-limits.txt` | 527 | 11 | untracked | 2026-07-16 07:57:26 |
| `docs/audit/runtime-20260715/global-telegram-authorization.txt` | 243 | 6 | untracked | 2026-07-15 16:53:23 |
| `docs/audit/runtime-20260715/security-state.txt` | 270 | 5 | untracked | 2026-07-15 13:48:08 |
| `docs/audit/runtime-20260715/ufw-status.txt` | 1435 | 23 | untracked | 2026-07-15 13:48:08 |

### `docs/audit/runtime-20260716/`

| Path | Byte | Baris | Git | Tanggal |
|---|---:|---:|---|---|
| `docs/audit/runtime-20260716/dashboard-authenticated-functional-test-report.md` | 5276 | 108 | untracked | 2026-07-16 12:59:45 |
| `docs/audit/runtime-20260716/dashboard-controlled-start-report.md` | 11004 | 238 | untracked | 2026-07-16 09:39:21 |
| `docs/audit/runtime-20260716/dashboard-controlled-start-retry-report.md` | 6180 | 129 | untracked | 2026-07-16 10:20:33 |
| `docs/audit/runtime-20260716/dashboard-controlled-start-retry2-report.md` | 6463 | 151 | untracked | 2026-07-16 10:52:21 |
| `docs/audit/runtime-20260716/dashboard-controlled-start-retry3-report.md` | 9283 | 183 | untracked | 2026-07-16 12:54:11 |
| `docs/audit/runtime-20260716/dashboard-db-auth-diagnosis.md` | 7762 | 167 | untracked | 2026-07-16 11:11:18 |
| `docs/audit/runtime-20260716/dashboard-db-credential-remediation.md` | 6521 | 141 | untracked | 2026-07-16 11:32:45 |
| `docs/audit/runtime-20260716/dashboard-dotenv-remediation.md` | 7508 | 169 | untracked | 2026-07-16 10:01:02 |
| `docs/audit/runtime-20260716/dashboard-source-permission-remediation.md` | 4323 | 90 | untracked | 2026-07-16 10:30:33 |
| `docs/audit/runtime-20260716/db-credential-consumer-impact-audit.md` | 8748 | 141 | untracked | 2026-07-16 12:03:44 |
| `docs/audit/runtime-20260716/nginx-hardening-pre-reload-report.md` | 11160 | 215 | untracked | 2026-07-16 09:15:32 |
| `docs/audit/runtime-20260716/nginx-reload-smoke-test.md` | 7126 | 164 | untracked | 2026-07-16 09:29:42 |
| `docs/audit/runtime-20260716/systemd-hardening-stage1-report.md` | 14776 | 239 | untracked | 2026-07-16 08:48:13 |

### `docs/cursor-ai/`

| Path | Byte | Baris | Git | Tanggal |
|---|---:|---:|---|---|
| `docs/cursor-ai/ALIZA_AI_BEHAVIOR_RULES.md` | 3541 | 215 | tracked | 2026-06-02 13:32:30 +0700 |
| `docs/cursor-ai/ALIZA_ARCHITECTURE_MAP.md` | 733 | 77 | tracked | 2026-06-02 13:32:30 +0700 |
| `docs/cursor-ai/ALIZA_CURRENT_SYSTEM_INSPECTION_REPORT.md` | 20421 | 309 | tracked | 2026-06-02 13:32:30 +0700 |
| `docs/cursor-ai/ALIZA_DEBUG_PLAYBOOK.md` | 3031 | 219 | tracked | 2026-06-02 13:32:30 +0700 |
| `docs/cursor-ai/ALIZA_DEVELOPMENT_RULES.md` | 1169 | 88 | tracked | 2026-06-02 13:32:30 +0700 |
| `docs/cursor-ai/ALIZA_ENGINE_CONTRACTS.md` | 994 | 47 | tracked | 2026-06-02 13:32:30 +0700 |
| `docs/cursor-ai/ALIZA_SYSTEM_HEALTH_CHECK.md` | 2445 | 211 | tracked | 2026-06-02 13:32:30 +0700 |
| `docs/cursor-ai/ALIZA_SYSTEM_PROMPT.md` | 1995 | 141 | tracked | 2026-06-02 13:32:30 +0700 |
| `docs/cursor-ai/ALIZA_TEST_SYSTEM.md` | 2918 | 237 | tracked | 2026-06-02 13:32:30 +0700 |

### `docs/instructions/` dan teks lain

| Path | Byte | Baris | Git | Tanggal |
|---|---:|---:|---|---|
| `docs/instructions/ai-rules.md` | 20645 | 302 | tracked | 2026-06-02 13:32:30 +0700 |
| `docs/instructions/intent-routing.md` | 11800 | 206 | tracked | 2026-06-02 13:32:30 +0700 |
| `docs/instructions/persona.md` | 10820 | 151 | tracked | 2026-06-02 13:32:30 +0700 |
| `docs/instructions/system-prompt.md` | 8439 | 96 | tracked | 2026-06-02 13:32:30 +0700 |
| `knowledge/documents/Instructions.txt` | 1107 | 33 | tracked | 2026-03-08 11:52:54 +0800 |
| `memory/active_document.txt` | 138 | 0 | tracked | 2026-03-10 23:37:09 +0800 |

Catatan: `requirements*.txt` adalah metadata dependency dan `memory/active_document.txt` adalah state/artefak aplikasi, bukan dokumentasi manusia. Keduanya masuk inventaris karena cakupan meminta semua `.txt`, tetapi tidak disarankan dipindah ke struktur docs.

## 3. Duplikasi dan tumpang tindih

### 3.1 Salinan identik

`sha256sum` membuktikan pasangan berikut identik byte-for-byte. Kolom rekomendasi mengasumsikan `docs/` menjadi lokasi kanonik dan folder `AlizaAI-Crypto/...` hanya ekspor yang dihasilkan bila memang masih diperlukan.

| Pasangan | SHA-256 (awal) | Ukuran satu salinan | Rekomendasi |
|---|---|---:|---|
| root `BACKTEST_REPORT.md` ↔ salinan tujuan | `f4c2669a...` | 4.142 | Pindahkan kanonik ke report Fase 2; ekspor jangan menjadi sumber edit |
| root `EXPERIMENT_RESULTS.md` ↔ salinan tujuan | `908628b5...` | 5.347 | Kanonik di report Fase 3 |
| root `FASE1_REPORT.md` ↔ salinan tujuan | `cf3caa62...` | 6.223 | Kanonik di report Fase 1 |
| root `FASE1D_REPORT.md` ↔ salinan tujuan | `d04cb285...` | 4.013 | Kanonik di report Fase 1 |
| root `FASE2_REPORT.md` ↔ salinan tujuan | `5989bf36...` | 3.322 | Kanonik di report Fase 2 |
| root `FASE3_REPORT.md` ↔ salinan tujuan | `f670bf96...` | 3.902 | Kanonik di report Fase 3 |
| root `FASE4_REPORT.md` ↔ salinan tujuan | `38d6ce0f...` | 3.295 | Kanonik di report Fase 4 |
| root `ROBUSTNESS_RESULTS.md` ↔ salinan tujuan | `93f40575...` | 4.032 | Kanonik di report Fase 4 |
| root `VPS_HEALTH_REPORT.md` ↔ salinan tujuan | `caba7c82...` | 13.200 | Kanonik di audit maintenance 21 Juli |
| root `REPO_CLEANUP_REPORT.md` ↔ salinan tujuan | `5d44da35...` | 15.423 | Kanonik di audit maintenance 21 Juli |
| root `MAINTENANCE_REPORT.md` ↔ salinan tujuan | `e8dc2db7...` | 18.905 | Kanonik di audit maintenance 21 Juli |
| `audit-output/FASE1C_VERIFIKASI_REPORT.md` ↔ salinan tujuan | `311cc3cb...` | 6.788 | Kanonik di report Fase 1 |

Jumlah ukuran satu sisi pasangan: **88.592 byte**. Ini bukan otomatis “boleh dihapus”; folder tujuan mungkin merupakan deliverable eksternal. Masalahnya adalah tidak ada metadata `generated/export` dan tidak ada sumber kanonik.

### 3.2 Tumpang tindih topik

| Dokumen | Bukti perbandingan | Klasifikasi | Rekomendasi |
|---|---|---|---|
| `cursor-ai/ALIZA_SYSTEM_PROMPT.md` vs `instructions/system-prompt.md` | Nama sama, tetapi hanya 1 baris nonblank ternormalisasi yang identik dari 83 vs 67 baris unik. Yang pertama menyapa “AI yang bekerja pada proyek” (`cursor...:8`); yang kedua mendefinisikan runtime LLM dan model (`instructions...:17`). | Beda audiens, bukan duplikat | Pertahankan keduanya; rename menjadi `coding-agent-context.md` dan `runtime-llm-system-prompt.md` |
| `cursor-ai/ALIZA_AI_BEHAVIOR_RULES.md` vs `instructions/ai-rules.md` | Hanya 1 baris exact-overlap dari 116 vs 193 baris unik. Yang pertama melarang perubahan arsitektur/DB; yang kedua mengatur sumber angka, disclaimer, routing, dan gateway (`ai-rules.md:15-69`). | Beda tujuan dengan nama membingungkan | Pertahankan; pisah jelas `agent-rules/coding/` dan `agent-rules/runtime/` |
| `ALIZA_DEBUG_PLAYBOOK.md` vs `ALIZA_SYSTEM_HEALTH_CHECK.md` | 16 baris exact-overlap; keduanya menguji snapshot, signal engine, SQLite, scheduler, dan error. | Sebagian tumpang tindih | Gabung prosedur ke `runbooks/troubleshooting.md`; health checklist menjadi checklist pendek yang merujuk runbook |
| Dua file di atas vs `ALIZA_TEST_SYSTEM.md` | Test doc mengulang snapshot, DB, signal, handler, dan endpoint; contoh endpoint ada di `ALIZA_TEST_SYSTEM.md:194-205`. | Sebagian tumpang tindih | Pisahkan automated-test policy dari manual smoke test; pindahkan smoke test ke runbook |
| `ALIZA_FULL_SYSTEM_AUDIT.md`, `ALIZA_CURRENT_SYSTEM_INSPECTION_REPORT.md`, dan `audit-output/00`–`07` | Semuanya memetakan arsitektur/risiko pada waktu berbeda; overlap exact rendah (3 baris untuk dua audit lama), tetapi kesimpulan saling menggantikan. | Snapshot historis berlapis | Pertahankan sebagai arsip bertanggal, tambahkan `as-of`, commit, dan `superseded-by` |
| `FASE2_REPORT.md` vs `BACKTEST_REPORT.md` | Fase 2 menjelaskan implementasi/test; backtest report menjelaskan hasil run. | Beda sudut pandang | Pertahankan bersama dalam folder Fase 2 |
| `FASE3_REPORT.md` vs `EXPERIMENT_RESULTS.md` | Fase 3 menjelaskan protokol/perubahan; results berisi angka eksperimen. | Beda sudut pandang | Pertahankan bersama dalam folder Fase 3 |
| `FASE4_REPORT.md` vs `ROBUSTNESS_RESULTS.md` | Fase 4 menjelaskan fitur shadow dan verdict; robustness memuat hasil rinci. Link relatif saat ini valid. | Beda sudut pandang | Pertahankan bersama dalam folder Fase 4 |
| `docs/audit/2026-07-15/*` vs `docs/audit/runtime-20260715/` dan `runtime-20260716/` | Report naratif memiliki raw output service/security dan 13 report remediation retry. | Report + evidence, bukan duplikat | Pertahankan, tetapi beri `README.md` manifest dan satukan pola tanggal folder |

Cuplikan bukti paling jelas:

```text
docs/cursor-ai/ALIZA_SYSTEM_PROMPT.md:8
AI yang bekerja pada proyek ini harus menjaga arsitektur sistem yang sudah ada.

docs/instructions/system-prompt.md:17
Model yang dipakai di kode saat ini: gpt-4o-mini (lihat core/agent.py).

selected normalized overlap:
SYSTEM_PROMPT pair: unique_a=83 unique_b=67 common=1
AI_BEHAVIOR pair: unique_a=116 unique_b=193 common=1
DEBUG vs HEALTH: unique_a=101 unique_b=101 common=16
```

## 4. Klaim usang atau kontradiktif

Status **USANG** berarti benar sebagai snapshot pada waktu ditulis tetapi tidak boleh dipakai sebagai current state. **KONTRADIKTIF** berarti dokumen tanpa pembatas waktu menyatakan sesuatu yang berlawanan dengan implementasi kini. **SESUAI** berarti klaim masih cocok.

| Klaim dokumen | Lokasi dokumen | Kondisi aktual dan bukti | Status |
|---|---|---|---|
| Telegram bot command-only, tanpa background job/refresh otomatis | `docs/cursor-ai/ALIZA_CURRENT_SYSTEM_INSPECTION_REPORT.md:90` | `interfaces/telegram_bot.py:6947` melakukan initial update; `:7023` menjadwalkan snapshot 60 detik dan `:7025-7148` banyak checker/job | KONTRADIKTIF |
| `update_market_snapshot()` tidak dipanggil job/entrypoint | file sama `:120-123` | Dipanggil `interfaces/telegram_bot.py:6754`, `:6947`; scheduler `:7023` | KONTRADIKTIF |
| Opportunity scanner fallback ke market cache saat snapshot stale | file sama `:137-140` | `engine/trading/opportunity_scanner.py:40-50` abort dan mengembalikan `{}`; eksplisit “NO FALLBACK ALLOWED” | KONTRADIKTIF |
| Tidak ada job yang memanggil signal engine | file sama `:142-147` | `interfaces/telegram_bot.py:6834-6841` memanggil `scan_for_signals()` dan dispatch setelah lolos | KONTRADIKTIF |
| `api/dashboard_api.py`/endpoint dashboard tidak ditemukan | file sama `:48`, `:275`; `ALIZA_TEST_SYSTEM.md:194-205` | `api/dashboard_api.py:17-67` mendefinisikan `/api/dashboard/{market,quant,predict,signals,portfolio}` dan dipasang oleh `api/server.py:16,83` | USANG |
| Snapshot diupdate 60 detik dan Telegram membaca snapshot | `docs/cursor-ai/ALIZA_SYSTEM_PROMPT.md:73-81`; `ALIZA_ARCHITECTURE_MAP.md:32-38` | Scheduler 60 detik benar (`telegram_bot.py:7023`), tetapi larangan absolut API langsung tidak mencerminkan interface yang berisi `httpx` call (`telegram_bot.py:2319-2500,4286-4488`) | KONTRADIKTIF (sebagian) |
| Background jobs bernama `market_snapshot_job`, `trade_guardian_job`, `position_management_job`, dll. | `ALIZA_SYSTEM_PROMPT.md:119-130` | Registrasi aktual memakai `snapshot_job`, `near_support_checker`, `watchdog_job`, `signal_check_job`, dll. (`telegram_bot.py:7023-7148`); pencarian nama lama tidak menghasilkan caller | KONTRADIKTIF |
| Hanya `trade_manager.py` boleh memodifikasi `data/aliza.db` | `ALIZA_SYSTEM_PROMPT.md:87-93`; `ALIZA_AI_BEHAVIOR_RULES.md:84-94`; `ALIZA_DEVELOPMENT_RULES.md:18-32` | `engine/trading/signal_tracker.py:19,60-63,66-147,213-229` membuka DB yang sama, membuat/migrasi tabel, dan insert row | KONTRADIKTIF |
| Architecture flow memiliki Position Manager | `docs/cursor-ai/ALIZA_ARCHITECTURE_MAP.md:42-56` | `engine/trading/position_manager.py` tidak ada; inspection sendiri mencatat ini di `:154-160` | KONTRADIKTIF |
| Tidak ada critical bug | `docs/ALIZA_FULL_SYSTEM_AUDIT.md:194-199` | Sebagai snapshot Juni klaim tidak bisa menjadi status kini; audit 21 Juli menemukan defect deterministic yang kemudian diperbaiki Fase 1. Dokumen tidak mencantumkan commit/as-of yang tegas | USANG |
| Dua service utama Telegram dan market aktif | `audit-output/00-ringkasan-eksekutif.md:9`; `05-konfigurasi-dan-operasional.md:144-145` | `systemctl`: hanya `aliza-telegram` active; `aliza-market` disabled/inactive | USANG |
| Auto-alert mustahil karena minimum score 160 | `audit-output/00...:24`; `03-logika-sinyal.md:158-160`; `06-kualitas...:9-13` | `engine/alerts/auto_alert_engine.py:16-36` default 70, validasi 0–100, RR 2,5/confidence 65; dijalankan oleh snapshot job `telegram_bot.py:6812-6832` | USANG |
| Signal dicatat sebelum gateway; short setup salah arah; tidak ada provenance/fee/OHLC | `audit-output/00...:24,28`; `04-risk...:80-84` | Dispatch-before-record kini di `telegram_bot.py:6706-6721`; tracker punya `side/source/dispatch_status` (`signal_tracker.py:71-92`), map short `:26-33`, OHLC 5m dan fee `:20-23` | USANG |
| Candle aktif/ticker contaminate dan missing timeframe dipakai ganda | `audit-output/00...:26` | Closed candle diekstrak lewat closeTime (`market_analyzer.py:112-127`), ticker tidak diappend (`:328-331`), coverage memberi `insufficient_4h/1d` (`:363-367`) | USANG |
| Belum ada backtesting | `audit-output/00...:41,72`; `04-risk...:101-105`; `07-perbandingan...:126` | `backtest/` ada; Fase 2 event-driven, Fase 3 grid/holdout, Fase 4 robustness. Bukti: `FASE2_REPORT.md:10-28`, `FASE3_REPORT.md:12-32`, `FASE4_REPORT.md:5-19` | USANG |
| Produksi memakai SL oversold flat 1,5%; RR scan 3, gateway 2, opportunity 1,3 | `audit-output/04-risk...:48-56`; `docs/instructions/ai-rules.md:58-69` | Rumus produksi masih `entry*0.985` (`engine/brain/trading_brain.py:147-158`); scan `MIN_RR=3` (`engine/trading/signal_engine.py:49-50`), gateway `MIN_RR=2` (`engine/risk_manager.py:10-12`), opportunity `rr>=1.3` (`opportunity_scanner.py:53-72`) | SESUAI |
| E3 shadow default off, SL 1×ATR/TP 3×ATR, source terpisah | `FASE4_REPORT.md:7-10,21-25` | Default code false (`engine/shadow/e3_shadow.py:31-36`); level/source `:84-122`; statistik source terpisah di tracker. Ini benar sebagai default desain | SESUAI |
| Shadow hanya hipotetis “jika diaktifkan” | `FASE4_REPORT.md:21-29` | Runtime kini `SHADOW_E3_ENABLED=true`, `SHADOW_E3_DISPATCH=true`; journal 14:08–14:24 menunjukkan job tiap menit tetapi `candidates=0`, `recorded=0`; DB `shadow_e3=0` | USANG sebagai status operasi |
| Universe fixed 21 coin | `audit-output/00...:5,13`; komentar `market_universe.py:4` | `CORE_COINS` memang 21 (`market_universe.py:15-21`); `get_tradable_coins()` fixed (`dynamic_universe.py:276-278`). Runtime mengecualikan BONE/FARTCOIN/HYPE/ZEREBRO melalui flag | SESUAI dengan catatan runtime efektif |
| `COIN_FAIL_THRESHOLD` default 10 dan exclude opsional | `FASE1D_REPORT.md:45-51`; `VPS_HEALTH_REPORT.md:250-253` | Kode default 10 (`market_universe.py:30,53-58`); `.env` saat audit tidak mengisi threshold sehingga default berlaku; `UNIVERSE_EXCLUDE` terisi empat coin | SESUAI |
| Model runtime `gpt-4o-mini`, YAML `gpt-4o` tidak authoritative | `docs/instructions/system-prompt.md:17,84-88`; `intent-routing.md:174-189` | `core/agent.py:4-6` memakai `gpt-4o-mini`; `config/agent.yaml:7` masih `gpt-4o` | SESUAI |
| Fase 3 tidak mengubah parameter produksi; E3 hanya usulan | `FASE3_REPORT.md:20,28-34` | Produksi masih SL/TP rule-based di `trading_brain.py`; E3 berada di modul shadow terisolasi | SESUAI |
| Patch graceful shutdown belum aktif karena service belum restart | `MAINTENANCE_REPORT.md:20-21,519` | Benar pukul 14:03, tetapi systemd kemudian mencatat stop/start 14:07:08–14:07:22; proses aktif PID 2258029 sejak 14:07:22 | USANG |
| Lokal 14 commit di depan dan perlu push | `MAINTENANCE_REPORT.md:497-504,540-544` | Saat audit docs: `git rev-list ...` = `0 0`; `main`, `origin/main`, dan `fix/graceful-shutdown` menunjuk `f38ab55` | USANG |
| Backup 102 tanpa retensi dan root disk 62% | `VPS_HEALTH_REPORT.md:16,28,313-319` | Maintenance menurunkan root ke 54%, menyisakan 14 backup, dan cron kini memakai `-mtime +14 -delete`; output aktual count=14 | USANG |
| Data 10 signal, 5 LOSS/5 OPEN, realized WR 0% tetapi tidak valid sebagai estimasi strategi | `audit-output/00...:24`; `04-risk...:69-84` | Query saat audit tetap `LOSS=5`, `OPEN=5`, WR=0%; semua source `legacy`. Interpretasi “tidak valid sebagai ukuran strategi” tetap benar | SESUAI sebagai baseline legacy |

Output aktual terpilih:

```text
$ systemctl show aliza-telegram aliza-market ...
aliza-telegram: active/running, enabled, PID 2258029, since 14:07:22
aliza-market: inactive/dead, disabled

$ named non-secret flags only
UNIVERSE_EXCLUDE=BONE,FARTCOIN,HYPE,ZEREBRO
SHADOW_E3_ENABLED=true
SHADOW_E3_DISPATCH=true
COIN_FAIL_THRESHOLD=<TIDAK_ADA>  # kode memakai default 10

$ sqlite aggregate signal_tracking
legacy  10  latest_created_at=2026-07-21 01:00:41
shadow_rows=0
status: LOSS=5, OPEN=5

$ journalctl ... | rg shadow_e3
14:08:08 Shadow E3 mode: enabled=true dispatch=true
14:08:21 shadow_e3 candidates=0; recorded=0 dispatch=True
... pola sama tiap menit hingga pemeriksaan terakhir
```

Catatan penting: `.env.example` hanya 52 baris dan **tidak memuat** `UNIVERSE_EXCLUDE`, `SHADOW_E3_ENABLED`, `SHADOW_E3_DISPATCH`, atau `COIN_FAIL_THRESHOLD`. Ini bukan kebocoran secret, tetapi gap konfigurasi yang dapat membuat operator tidak mengetahui flag non-secret penting.

## 5. Struktur dan lokasi kanonik yang direkomendasikan

### 5.1 Masalah struktur/penamaan

- Tiga konvensi bercampur: `SCREAMING_SNAKE_CASE.md` (`cursor-ai`), `kebab-case.md` (`instructions`/audit runtime), dan `NN-kebab-case.md` (`audit-output`).
- Tiga rumah audit bercampur: `docs/audit/`, `audit-output/`, dan `AlizaAI-Crypto/01-hasil-audit-codex/`.
- `docs/audit/2026-07-15`, `runtime-20260715`, dan `runtime-20260716` memakai format tanggal berbeda.
- Nama `cursor-ai` mengikat dokumen ke satu editor, padahal isinya adalah rules coding-agent umum.
- Nama `instructions` tidak menjelaskan apakah untuk developer, prompt runtime, atau RAG.
- `dynamic_universe.py` masih memiliki header “Hybrid universe” sementara public runtime function mengembalikan fixed list; nama/source comment ikut menambah kebingungan dokumentasi.
- Tidak ada README/index di folder yang membutuhkan urutan baca dan status authoritative/historical.

Konvensi yang disarankan: folder dan filename `kebab-case`; tanggal ISO `YYYY-MM-DD`; setiap report memiliki front matter sederhana: `as-of`, `commit`, `status: current|historical|superseded`, `canonical-path`, `supersedes`.

### 5.2 Pohon usulan

```text
README.md
CHANGELOG.md
docs/
  README.md
  architecture/
  agent-rules/
    coding/
    runtime/
  configuration/
  runbooks/
  reports/
    phases/2026-07-21/fase-1/
    phases/2026-07-21/fase-2/
    phases/2026-07-21/fase-3/
    phases/2026-07-21/fase-4/
  audits/
    2026-06-02/system/
    2026-07-15/security/
    2026-07-16/runtime-hardening/
    2026-07-21/system-baseline-pre-fase/
    2026-07-21/maintenance/
  archive/
```

### 5.3 Pemetaan lama → lokasi kanonik

| Lama | Lokasi kanonik usulan | Keputusan |
|---|---|---|
| `docs/cursor-ai/ALIZA_SYSTEM_PROMPT.md` | `docs/agent-rules/coding/coding-agent-context.md` | Pertahankan, koreksi arsitektur/job |
| `ALIZA_AI_BEHAVIOR_RULES.md` + `ALIZA_DEVELOPMENT_RULES.md` | `docs/agent-rules/coding/change-guardrails.md` | Gabung setelah konflik DB/API diselesaikan |
| `ALIZA_ENGINE_CONTRACTS.md` | `docs/architecture/engine-contracts.md` | Pertahankan dan jadikan target link stabil |
| `ALIZA_ARCHITECTURE_MAP.md` | `docs/architecture/system-overview.md` | Rebuild dari current code |
| `ALIZA_DEBUG_PLAYBOOK.md` | `docs/runbooks/troubleshooting.md` | Gabung prosedur debug |
| `ALIZA_SYSTEM_HEALTH_CHECK.md` | `docs/runbooks/health-check.md` | Pertahankan sebagai checklist ringkas |
| `ALIZA_TEST_SYSTEM.md` | `docs/runbooks/smoke-test.md` dan test policy di `docs/architecture/testing.md` | Pecah manual vs automated |
| `ALIZA_CURRENT_SYSTEM_INSPECTION_REPORT.md` | `docs/audits/2026-06-02/system/current-system-inspection.md` | Arsipkan; label superseded |
| `docs/ALIZA_FULL_SYSTEM_AUDIT.md` | `docs/audits/2026-06-02/system/full-system-audit.md` | Arsipkan; label superseded |
| `docs/instructions/system-prompt.md` | `docs/agent-rules/runtime/runtime-llm-system-prompt.md` | Pertahankan |
| `docs/instructions/ai-rules.md` | `docs/agent-rules/runtime/ai-output-rules.md` | Pertahankan dan update Fase 4/config |
| `docs/instructions/persona.md` | `docs/agent-rules/runtime/persona.md` | Pertahankan |
| `docs/instructions/intent-routing.md` | `docs/agent-rules/runtime/intent-routing.md` | Pertahankan |
| `docs/architecture/position-sizing.md` | tetap `docs/architecture/position-sizing.md` | Sudah tepat; review drift |
| `FASE1_REPORT.md`, `FASE1D_REPORT.md`, `audit-output/FASE1B*`, `FASE1C*` | `docs/reports/phases/2026-07-21/fase-1/` | Satu rangkaian fase, nama berurutan |
| `FASE2_REPORT.md`, `BACKTEST_REPORT.md` | `docs/reports/phases/2026-07-21/fase-2/` | Implementation + result |
| `FASE3_REPORT.md`, `EXPERIMENT_RESULTS.md` | `docs/reports/phases/2026-07-21/fase-3/` | Protocol + result |
| `FASE4_REPORT.md`, `ROBUSTNESS_RESULTS.md` | `docs/reports/phases/2026-07-21/fase-4/` | Shadow + robustness |
| `audit-output/00`–`07` | `docs/audits/2026-07-21/system-baseline-pre-fase/` | Pertahankan sebagai baseline 08:xx, label superseded by Fase 1–4 |
| `docs/audit/2026-07-15/*` + `runtime-20260715/*` | `docs/audits/2026-07-15/security/` | Satukan report dan `evidence/` |
| `docs/audit/runtime-20260716/*` | `docs/audits/2026-07-16/runtime-hardening/` | Pertahankan; README manifest |
| `VPS_HEALTH_REPORT.md`, `REPO_CLEANUP_REPORT.md`, `MAINTENANCE_REPORT.md`, laporan docs ini | `docs/audits/2026-07-21/maintenance/` | Satu rangkaian audit/eksekusi |
| `AlizaAI-Crypto/01-hasil-audit-codex/*` | di luar sumber kanonik; ekspor/generated bundle | Simpan hanya jika dibutuhkan workflow eksternal; beri README “do not edit” |
| `knowledge/documents/Instructions.txt` | tetap di `knowledge/documents/` | Artefak knowledge/RAG; indeks dari docs, jangan dicampur dengan prompt kanonik |
| `memory/active_document.txt` | tetap di `memory/` atau pindah ke data runtime sesuai desain | Bukan dokumentasi manusia |
| `requirements*.txt` | tetap root | Metadata dependency, bukan docs |

Root repo sebaiknya hanya memuat `README.md`, `CHANGELOG.md`, file build/config, dan entrypoint penting. Report fase/audit di root memperbesar noise dan memicu duplikasi; `docs/reports/` adalah lokasi kanonik yang lebih tepat.

## 6. Gap dokumen yang perlu dibuat

Urutan prioritas berdasarkan risiko operasional nyata:

1. **P0 — `docs/runbooks/deploy-restart-rollback.md`.** Belum ada prosedur authoritative untuk deploy `/opt/aliza-ai`, restart hanya `aliza-telegram`, precheck dirty tree, backup/migrasi DB, smoke test, rollback commit, dan bukti journal. `audit-output/05...:117-129` justru menyatakan `scripts/deploy/deploy.sh` memakai path lama `/home/ubuntu/aliza-ai` dan merestart unit repo lain.
2. **P0 — `docs/runbooks/graceful-shutdown.md`.** Patch `f38ab55` dan diagnosis SIGKILL hanya hidup di report maintenance `:275-519`. Runbook perlu memuat kontrak `TimeoutStopSec=15`, deadline aplikasi 8 detik, tanda log sukses/gagal, dua-restart verification, dan rollback; report insiden tetap menjadi evidence terpisah.
3. **P0 — `docs/README.md` + root `README.md`.** Harus menjawab entrypoint, service authoritative, source-of-truth docs, cara membaca report historical, dan status `aliza-market` disabled.
4. **P1 — `docs/current-system-status.md`.** Ringkas Fase 1–4 pada satu halaman: integritas signal, data coverage, backtester, hasil eksperimen, E3 shadow, current flags, serta daftar keputusan yang masih menunggu user. Saat ini fakta tersebar di minimal delapan report.
5. **P1 — `docs/configuration/reference.md` dan update `.env.example`.** Dokumentasikan semua flag non-secret, tipe/default/range/restart requirement. Empat flag penting (`UNIVERSE_EXCLUDE`, `COIN_FAIL_THRESHOLD`, `SHADOW_E3_ENABLED`, `SHADOW_E3_DISPATCH`) sama sekali tidak ada di `.env.example`.
6. **P1 — `CHANGELOG.md`.** Commit log kuat, tetapi pengguna tidak memiliki daftar perubahan perilaku/restart/migrasi per release. Mulai dari checkpoint 21 Juli; jangan merekonstruksi release palsu tanpa tag.
7. **P1 — `docs/runbooks/shadow-e3.md`.** Aktivasi/deaktivasi, dispatch risk, query stats, kriteria promosi, observability saat candidates=0, dan rollback flag. Fase 4 adalah report implementasi, bukan runbook operasi.
8. **P2 — ADR/service ownership.** Catat mengapa `aliza-market` dinonaktifkan, `aliza-telegram` menjadi scheduler tunggal, dan bagaimana mencegah `aliza-bot` lama start saat reboot.
9. **P2 — audit index/manifests.** Tiap folder audit perlu README berisi scope, as-of/commit, report utama, evidence, status superseded, dan apakah raw output aman dibagikan.
10. **P2 — testing guide.** Bedakan unit/full suite, backtest reproducibility, integration smoke test, dan manual service verification; `ALIZA_TEST_SYSTEM.md` kini mencampur semuanya.

Gap ini konkret karena pencarian aktual menemukan:

```text
README.md MISSING
CHANGELOG.md MISSING
README files under docs/audit-output/export: none
MAINTENANCE_REPORT.md contains SIGKILL/graceful diagnosis, but no standalone runbook
FASE1_REPORT.md ... FASE4_REPORT.md exist separately, no consolidated status page
```

## 7. Referensi rusak atau menyesatkan

Pemeriksaan seluruh pola Markdown `[teks](target)` dengan resolusi relatif terhadap folder file menghasilkan **nol broken relative Markdown link**. Link HTTP, `mailto:`, dan anchor lokal dikecualikan. Output command kosong.

Namun, ditemukan referensi path dalam teks biasa yang tidak memakai syntax link:

| Referensi | Hasil aktual | Penilaian |
|---|---|---|
| `docs/cursor-ai/ALIZA_AI_BEHAVIOR_RULES.md:78-80` → `docs/ALIZA_ENGINE_CONTRACTS.md` | Path tidak ada; file aktual `docs/cursor-ai/ALIZA_ENGINE_CONTRACTS.md` | **Rusak**, perbaiki target atau pindahkan contract ke lokasi kanonik |
| `docs/cursor-ai/ALIZA_ARCHITECTURE_MAP.md:54` → Position Manager | `engine/trading/position_manager.py` tidak ada | Referensi arsitektur menyesatkan |
| `docs/cursor-ai/ALIZA_CURRENT_SYSTEM_INSPECTION_REPORT.md:48,275` → `api/dashboard_api.py` tidak ada | File sekarang ada dan dipasang oleh `api/server.py` | Klaim path hilang sudah usang |
| `ALIZA_TEST_SYSTEM.md:198-203` → endpoint dashboard | Seluruh endpoint kini ada di `api/dashboard_api.py:17-67`; `/health` ada di `api/server.py:155` | Referensi tidak rusak, tetapi test doc perlu menyebut auth requirement |
| Report fase menyebut `feat/fase2-backtester`, `feat/fase3-experiments`, `feat/fase4-shadow`, `fix/fase1-*` | Lima branch lokal telah dihapus setelah merge; `git branch -a` kini hanya `main`, `fix/graceful-shutdown`, dan remote main | **Bukan broken ref**: ini provenance historis. Tambahkan commit hash agar tidak bergantung branch |
| Maintenance menyebut `tmp_pack_W9KN2w` dan 88 backup yang dihapus | Objek memang tidak ada setelah cleanup | **Bukan broken ref**: output historis, jangan diubah menjadi link/path aktif |

Bukti path aktual:

```text
docs/ALIZA_ENGINE_CONTRACTS.md MISSING
engine/trading/position_manager.py MISSING
engine/trading/portfolio_engine.py MISSING
api/dashboard_api.py EXISTS
README.md MISSING
CHANGELOG.md MISSING
```

## Kesimpulan keputusan

Jangan mulai dengan menghapus dokumen lama. Urutan yang aman untuk prompt eksekusi berikutnya adalah: tetapkan `docs/` sebagai source of truth; buat indeks/status metadata; pindahkan report ke folder bertanggal; tandai baseline lama sebagai superseded; rename rules berdasarkan audiens; lalu evaluasi apakah bundle ekspor duplikat masih dibutuhkan. Dengan itu sejarah audit tetap utuh, sementara pembaca tidak lagi mengira snapshot 08:26, report 13:15, dan runtime 14:24 adalah kondisi yang sama.

