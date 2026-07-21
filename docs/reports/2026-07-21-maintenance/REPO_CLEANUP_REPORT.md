# Repo Cleanup Report — Aliza AI

Waktu audit: **2026-07-21 13:11–13:16 WIB**  
Repo: `/opt/aliza-ai`, branch `main`  
Aturan: laporan saja; tidak ada file/branch yang dihapus dan tidak ada commit.

## Ringkasan keputusan

| Kategori | Temuan utama | Ukuran terukur | Klasifikasi |
|---|---|---:|---|
| Cache Python/test | 30 `__pycache__`, 162 `*.pyc`, 1 `.pytest_cache` | 1,3 MiB disk allocation | **AMAN DIHAPUS** |
| Egg metadata | Tidak ditemukan di luar `venv` | 0 | **AMAN DIHAPUS** bila kelak muncul |
| Backup manual/cron | 105 file; 102 adalah backup `telegram_bot.py` | 25.281.440 byte (~24,1 MiB) | **PERLU KONFIRMASI USER** |
| Backtest raw cache | `backtest/data/` | 186.938.983 byte (~178,3 MiB) | **PERLU KONFIRMASI USER** |
| Backtest result | `backtest/results/` | 874.065 byte | **PERLU KONFIRMASI USER** |
| Git garbage pack | `.git/objects/pack/tmp_pack_W9KN2w` | 255,50 MiB | **PERLU KONFIRMASI USER**; gunakan maintenance Git, jangan `rm` manual |
| Untracked audit/report | 4 status entries | ~136 KiB | **PERLU KONFIRMASI USER** |
| Report fase duplikat tracked | 7 pasang root vs folder hasil | 30.263 byte untuk satu set ekstra | **PERLU KONFIRMASI USER** |
| Local merged branches | 5 branch sudah merged | Ruang ref dapat diabaikan | **AMAN DIHAPUS** dengan `git branch -d` |
| Runtime venv | `venv/` | 8.619.890.138 byte (~8,03 GiB) | **JANGAN SENTUH**; dipakai service aktif |
| Runtime DB/config/log | `.env`, `data/`, current logs | DB/data 94.814 byte; logs 24.013.603 byte | **JANGAN SENTUH** |

Total yang aman dibebaskan sekarang: **1,3 MiB** plus ref branch yang ukurannya tidak material. Potensi tambahan setelah konfirmasi: sekitar **458,7 MiB** dari backup + backtest cache/result + Git garbage; angka ini tidak memasukkan log aktif, venv, DB, atau dokumen runtime.

## 1. Artefak Python

Output aktual di luar `venv`:

```text
$ find ... -type d -name '__pycache__' ...
pycache_dirs=30 pycache_bytes=916189

$ find ... -type f -name '*.pyc' ...
pyc_count=162 pyc_bytes=793309

$ find ... -type d -name '.pytest_cache' ...
pytest_dirs=1 pytest_bytes=25698

$ find ... -type d -name '*.egg-info' ... | wc -l
0

$ du gabungan __pycache__ + .pytest_cache
1.3M total
```

`*.pyc` berada di dalam `__pycache__`, sehingga ukurannya tidak dijumlahkan dua kali. Klasifikasi seluruh cache ini: **AMAN DIHAPUS**; Python/pytest akan membuatnya lagi.

`.gitignore` aktual sudah mencakup:

```text
venv/
__pycache__/
*.pyc
```

Catatan: `.pytest_cache/` belum ditulis di `.gitignore` repo. Direktori saat ini terlihat ignored karena file internal `.pytest_cache/.gitignore` berisi rule `*`, dibuktikan oleh `git check-ignore -v`:

```text
.pytest_cache/.gitignore:2:*  .pytest_cache/
```

Sebaiknya rule repo `.pytest_cache/` tetap ditambahkan agar eksplisit dan konsisten setelah cache dibuat ulang.

## 2. File tracked yang seharusnya diperiksa

Pencarian tracked log/DB/dump/CSV/output eksperimen:

```text
$ git ls-files | rg -i '(^|/)(\.env($|\.)|.*\.(log|db|sqlite|sqlite3|dump|csv)$|.*(backtest|experiment|robustness).*(result|output|artifact))'
.env.example
.env.market
AlizaAI-Crypto/01-hasil-audit-codex/EXPERIMENT_RESULTS.md
AlizaAI-Crypto/01-hasil-audit-codex/ROBUSTNESS_RESULTS.md
EXPERIMENT_RESULTS.md
ROBUSTNESS_RESULTS.md
```

Verifikasi khusus:

```text
$ git ls-files '.env' '*.db' '*.sqlite' '*.sqlite3'
(tidak ada output)

$ git ls-files '.env.market' -s
100644 89e2080c28bdc0f23ea32365b73650f4b2a3612b 0 .env.market
```

- `.env`: ignored dan tidak tracked — **JANGAN SENTUH**, kondisi benar.
- `data/aliza.db` dan `data/user_config.db`: ignored dan tidak tracked — **JANGAN SENTUH**, kondisi benar.
- Tidak ada tracked `*.log`, SQLite, dump, atau CSV backtest.
- `.env.market` (28 byte) adalah file env-like yang tracked. Isi sengaja tidak dibuka/ditulis. **PERLU KONFIRMASI USER**: review apakah file hanya config non-secret; bila ada credential, rotate credential dan keluarkan dari Git history melalui prosedur security terpisah.
- `EXPERIMENT_RESULTS.md` dan `ROBUSTNESS_RESULTS.md` adalah dokumen hasil yang sengaja ikut commit, bukan raw output; **JANGAN SENTUH** sampai lokasi kanonik docs diputuskan.

Raw cache/result backtest sudah benar-benar ignored:

```text
.gitignore:21:backtest/data/     backtest/data/BTCUSDT_5m.csv
.gitignore:22:backtest/results/  backtest/results/20260721T1038Z/metrics.json
```

## 3. Untracked dan ignored yang menumpuk

Status sebelum dua laporan audit ini dibuat:

```text
## main...origin/main [ahead 13]
?? AlizaAI-Crypto/01-hasil-audit-codex/FASE1C_VERIFIKASI_REPORT.md
?? AlizaAI-Crypto/01-hasil-audit-codex/FASE1D_REPORT.md
?? FASE1D_REPORT.md
?? audit-output/
```

Ukuran aktual:

```text
8.0K  AlizaAI-Crypto/01-hasil-audit-codex/FASE1C_VERIFIKASI_REPORT.md
4.0K  AlizaAI-Crypto/01-hasil-audit-codex/FASE1D_REPORT.md
4.0K  FASE1D_REPORT.md
120K  audit-output/
```

Semua **PERLU KONFIRMASI USER**, karena tampak sebagai hasil audit yang mungkin memang perlu diarsip/commit. Jangan hapus otomatis.

### Backup manual/cron

```text
interfaces/telegram_bot.py.bak* count=102 bytes=25230622 min=147671 max=265794
interfaces/market_bot.py.bak* count=1 bytes=3319
engine/market/funding_rate_monitor.py.bak* count=1 bytes=10635
data/aliza.db.bak* count=1 bytes=36864
backup_files=105 backup_bytes=25281440
```

Rentang backup Telegram:

```text
oldest 2026-04-18 06:26 147671 ./interfaces/telegram_bot.py.bak.20260418_072625
newest 2026-07-21 01:00 265794 ./interfaces/telegram_bot.py.bak.20260721
```

Seluruh backup ini ignored dan **PERLU KONFIRMASI USER**. Penyebab pertumbuhan terbukti dari cron:

```text
0 2 * * * cp /opt/aliza-ai/interfaces/telegram_bot.py /opt/aliza-ai/interfaces/telegram_bot.py.bak.$(date +\%Y\%m\%d) 2>/dev/null
```

Saran: simpan 7–14 versi atau pindahkan ke sistem backup `/opt/aliza-backups`, lalu hentikan backup source tanpa retensi.

### Artefak Fase 2–4

```text
backtest/data     186938983 byte (du -sh: 179M)
backtest/results     874065 byte (du -sh: 864K)
```

Data berisi CSV 5m/1h/4h/1d/funding untuk 11 coin; file terbesar `PEPEUSDT_5m.csv` 18.195.289 byte. Result saat audit hanya folder `20260721T1038Z` dengan:

```text
696561 trades.csv
124575 quarterly_metrics.json
40005  metrics.json
636    config.json
```

Klasifikasi: **PERLU KONFIRMASI USER**. Keduanya bisa diregenerasi, tetapi penghapusan akan menghilangkan cache dan bukti reproduksi eksperimen lokal.

## 4. Kode yang tampak mati / one-off

Metode statis yang digunakan:

```bash
git grep -l -E 'from <module> import|import <module>|from <package> import <basename>' -- '*.py'
```

Scan awal menghasilkan modul tanpa import langsung berikut:

```text
api/market.py
api/server.py
api_server.py
backtest/data_loader.py
backtest/robustness.py
backtest/run_backtest.py
backtest/run_experiments.py
engine/intelligence/document_analyzer.py
engine/market/market_radar_pro.py
engine/monitoring/market_monitor.py
engine/utils/market_cache_updater.py
interfaces/market_bot.py
main.py
memory/document_registry.py
memory/memory_manager.py
project/cleanup_documents.py
skills_custom/weather.py
```

Hasil ini sudah direkonsiliasi terhadap relative import, CLI entrypoint, tests, dan `systemctl ExecStart`:

| Path | Byte | Bukti | Klasifikasi |
|---|---:|---|---|
| `api/market.py` | 602 | Router tidak di-include oleh source lain; endpoint utama memakai `api/dashboard_api.py` | **PERLU KONFIRMASI USER** |
| `api_server.py` | 3.030 | Docs sendiri menandai deprecated sejak 2026-04-16; tidak ada unit VPS yang menunjuk file ini | **PERLU KONFIRMASI USER**, cek traffic legacy |
| `engine/intelligence/document_analyzer.py` | 1.793 | Tidak ada import; hanya disebut inventory doc lama | **PERLU KONFIRMASI USER** |
| `engine/market/market_radar_pro.py` | 2.922 | Tidak ada import; memakai import lama `engine.market_cache` | **PERLU KONFIRMASI USER** |
| `engine/monitoring/market_monitor.py` | 3.753 | Standalone `main()`, tidak ada unit/timer/cron | **PERLU KONFIRMASI USER** |
| `engine/utils/market_cache_updater.py` | 444 | Tidak ada import/entrypoint terjadwal | **PERLU KONFIRMASI USER** |
| `memory/document_registry.py` | 448 | Tidak ada import | **PERLU KONFIRMASI USER** |
| `memory/memory_manager.py` | 968 | Tidak ada import | **PERLU KONFIRMASI USER** |
| `project/cleanup_documents.py` | 382 | Script one-off yang langsung menghapus upload >30 hari bila dieksekusi; tidak terjadwal | **PERLU KONFIRMASI USER**, jangan jalankan saat audit |
| `skills_custom/weather.py` | 205 | Stub, kemungkinan dapat dimuat dinamis oleh skill loader | **PERLU KONFIRMASI USER**, static grep tidak cukup |

Yang **bukan kode mati** walau tidak diimpor secara langsung:

| Path | Byte | Alasan | Klasifikasi |
|---|---:|---|---|
| `api/server.py` | 8.877 | Entrypoint `api.server:app` dari `scripts/run_dashboard.py` dan unit dashboard | **JANGAN SENTUH** |
| `backtest/data_loader.py` | 7.029 | Diimpor relatif oleh tiga runner (`from .data_loader ...`) | **JANGAN SENTUH** |
| `backtest/robustness.py` | 5.315 | CLI Fase 4 dan bukti reproduksi | **JANGAN SENTUH** |
| `backtest/run_backtest.py` | 4.890 | CLI Fase 2 | **JANGAN SENTUH** |
| `backtest/run_experiments.py` | 5.255 | CLI Fase 3 | **JANGAN SENTUH** |
| `interfaces/market_bot.py` | 3.919 | Masih dirujuk `aliza-market.service`, walau unit disabled | **JANGAN SENTUH** sebelum unit dipensiunkan |
| `main.py` | 1.310 | CLI CrewAI yang didokumentasikan | **JANGAN SENTUH** |

Audit static grep tidak membuktikan ketidakgunaan absolut karena dynamic import/CLI mungkin ada. Sesuai aturan tahap ini, tidak ada kode yang dimasukkan ke blok cleanup aman.

## 5. Branch Git basi

Semua branch lokal berikut sudah merged ke `main`:

```text
$ git branch --merged main -vv
feat/fase2-backtester             e9793308
feat/fase3-experiments            53dbc447
feat/fase4-shadow                 48403ed7
fix/fase1-signal-integrity        735b3559
fix/fase1d-observability-universe 51681225
* main                            5ef5a9f7
```

Verifikasi `git rev-list --left-right --count <branch>...main`:

```text
feat/fase2-backtester             0 17
feat/fase3-experiments            0 9
feat/fase4-shadow                 0 2
fix/fase1-signal-integrity        0 27
fix/fase1d-observability-universe 0 24
```

Angka kiri 0 membuktikan tidak ada commit branch yang belum masuk main. Lima branch lokal: **AMAN DIHAPUS** menggunakan `git branch -d`, bukan `-D`.

Remote hanya mempunyai:

```text
origin/HEAD -> origin/main
origin/main 9ff08ba6
```

Tidak ditemukan branch fase remote untuk dihapus.

## 6. File/direktori besar

Top direktori (`du -sh`, urut terbesar):

```text
8.2G  venv
4.5G  .git
180M  backtest
25M   interfaces
23M   logs
6.1M  knowledge
1.3M  engine
416K  docs
196K  __pycache__
120K  audit-output
```

- `venv/` **JANGAN SENTUH**: `aliza-telegram.service` aktif memakai `/opt/aliza-ai/venv/bin/python`. Besarnya didominasi paket CUDA/Torch; file terbesar `libtorch_cuda.so` 996M. Optimasi venv memerlukan rebuild terencana dan downtime, bukan cleanup file.
- `.git/` **JANGAN SENTUH secara manual**. Output aktual:

```text
count: 540
size: 40.37 MiB
in-pack: 65001
packs: 3
size-pack: 4.11 GiB
garbage: 1
size-garbage: 255.50 MiB
warning: garbage found: .git/objects/pack/tmp_pack_W9KN2w
```

Garbage pack **PERLU KONFIRMASI USER** untuk `git gc` setelah memastikan tidak ada proses Git lain. Jangan hapus `tmp_pack` langsung.

File >10 MiB di luar `.git` terbagi menjadi dua kelompok:

1. Library `venv` — **JANGAN SENTUH**.
2. `backtest/data/*_5m.csv` (14–18 MiB per file) — **PERLU KONFIRMASI USER**.

`interfaces/` sebesar 25M hampir seluruhnya berasal dari 25.230.622 byte backup `telegram_bot.py`, bukan source tracked aktif.

## 7. Duplikasi dan docs usang

### Duplikasi report

`git ls-files` menunjukkan tujuh report fase berada di root dan folder hasil. SHA-256 membuktikan tiap pasangan identik:

```text
BACKTEST_REPORT.md        == AlizaAI-Crypto/.../BACKTEST_REPORT.md        (4142 byte)
EXPERIMENT_RESULTS.md     == AlizaAI-Crypto/.../EXPERIMENT_RESULTS.md     (5347 byte)
ROBUSTNESS_RESULTS.md     == AlizaAI-Crypto/.../ROBUSTNESS_RESULTS.md     (4032 byte)
FASE1_REPORT.md           == AlizaAI-Crypto/.../FASE1_REPORT.md           (6223 byte)
FASE2_REPORT.md           == AlizaAI-Crypto/.../FASE2_REPORT.md           (3322 byte)
FASE3_REPORT.md           == AlizaAI-Crypto/.../FASE3_REPORT.md           (3902 byte)
FASE4_REPORT.md           == AlizaAI-Crypto/.../FASE4_REPORT.md           (3295 byte)
```

Satu set ekstra berjumlah 30.263 byte. **PERLU KONFIRMASI USER** untuk memilih lokasi kanonik; jangan hapus salah satu set sebelum link/reference diperbarui.

Duplikasi untracked tambahan:

```text
FASE1D_REPORT.md == AlizaAI-Crypto/.../FASE1D_REPORT.md (4013 byte)
audit-output/FASE1C_VERIFIKASI_REPORT.md == AlizaAI-Crypto/.../FASE1C_VERIFIKASI_REPORT.md (6788 byte)
```

### Kontradiksi/usang

1. `docs/cursor-ai/ALIZA_CURRENT_SYSTEM_INSPECTION_REPORT.md` menyatakan `market_snapshot_engine` “Not called by any job or entrypoint”. Kondisi saat audit bertentangan:

```text
interfaces/telegram_bot.py:6945: update_market_snapshot()
interfaces/telegram_bot.py:7014: app.job_queue.run_repeating(snapshot_job, interval=60, first=5)
```

Dokumen itu **PERLU DIPERBARUI**, bukan langsung dihapus.

2. Tidak ditemukan docs aktif yang mengklaim threshold alert 160. Namun inline comment runtime sudah usang:

```text
interfaces/telegram_bot.py:6811:# Auto alert ... score≥160 ...
engine/alerts/auto_alert_engine.py:17:raw = os.getenv("AUTO_ALERT_MIN_SCORE", "70")
engine/alerts/auto_alert_engine.py:24:... range 0-100
```

Comment 160 **PERLU DIPERBAIKI** pada perubahan kode berikutnya; nilai aktual default 70 dan rentang valid 0–100.

3. Penyebutan SL tetap 1,5% dalam `FASE1_REPORT.md`/`BACKTEST_REPORT.md` tidak kontradiktif untuk produksi saat ini. Source aktual masih memakai:

```text
engine/brain/trading_brain.py:150:# SL 1.5% di bawah ENTRY
engine/brain/trading_brain.py:153:sl = entry * 0.985
```

`FASE4_REPORT.md` membahas SL ATR untuk jalur `shadow_e3`, sehingga kedua dokumen menjelaskan jalur berbeda. **JANGAN SENTUH** hanya berdasarkan frasa 1,5%.

## 8. Blok cleanup siap-jalan — hanya kategori AMAN

**Belum dijalankan.** Blok ini sengaja hanya memuat cache Python/test dan lima branch lokal yang sudah terbukti merged:

```bash
cd /opt/aliza-ai

find . -path './venv' -prune -o -type d -name '__pycache__' -prune -exec rm -rf -- {} +
find . -path './venv' -prune -o -type f -name '*.pyc' -delete
rm -rf -- .pytest_cache

git branch -d \
  feat/fase2-backtester \
  feat/fase3-experiments \
  feat/fase4-shadow \
  fix/fase1-signal-integrity \
  fix/fase1d-observability-universe
```

Tidak ada perintah untuk backup, raw backtest, result, log, DB, `.env`, venv, Git pack, docs, atau kode kandidat mati.

## 9. Saran `.gitignore`

Tambahkan setelah persetujuan pada perubahan terpisah:

```gitignore
# Test/tool caches
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/

# Packaging artifacts
*.egg-info/
build/
dist/

# SQLite sidecar runtime files
*.db-wal
*.db-shm
*.sqlite-wal
*.sqlite-shm
```

Opsional, hanya jika `audit-output/` diputuskan sebagai output sementara dan bukan artefak yang perlu commit:

```gitignore
audit-output/
```

Jangan ignore seluruh `AlizaAI-Crypto/01-hasil-audit-codex/` karena folder itu sudah menjadi lokasi report yang diminta dan berisi dokumen tracked.

