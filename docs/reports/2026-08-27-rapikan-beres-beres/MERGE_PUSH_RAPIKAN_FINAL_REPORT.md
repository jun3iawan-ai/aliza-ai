# Laporan Merge & Push `docs/rapikan-27agustus` + Pemindahan 3 File Tracked Terakhir

Tanggal: 2026-08-27

## Bagian A — Merge `docs/rapikan-27agustus` ke `main`

### Precheck

- `git fetch origin`: tidak ada perubahan baru dari remote.
- `git status -sb` di `main` sebelum mulai: `main...origin/main` (up to date).
- Titik cabang:
  - `main`: `9468f9e feat: shadow_e3 outcome-based promotion policy + per-reason observability`
  - `docs/rapikan-27agustus`: `42f3258` — bercabang LANGSUNG dari `9468f9e` (tip `main` saat itu).

### Merge

Karena branch bercabang langsung dari tip `main` saat ini (tidak ada commit lain masuk `main` sejak branch dibuat), **tidak perlu rebase**. `git checkout main && git merge --ff-only docs/rapikan-27agustus` → **berhasil, fast-forward** `9468f9e..42f3258`.

```
CHANGELOG.md                                       |   1 +
RAPIKAN_27AGUSTUS_REPORT.md                        |  95 ++++++++++++++++
docs/README.md                                     |   2 +-
.../MERGE_PUSH_BERES_MESSAGEFIX_REPORT.md          | 108 ++++++++++++++++++
.../MERGE_PUSH_SHADOW_OBSERVABILITY_REPORT.md      |  94 ++++++++++++++++
.../REPLY_TEXT_MESSAGE_LENGTH_AUDIT_REPORT.md      | 123 +++++++++++++++++++++
6 files changed, 422 insertions(+), 1 deletion(-)
```

### Verifikasi setelah merge pertama

- `bash -n scripts/deploy/deploy.sh` → **PASS**.
- `git diff --stat 9468f9e main -- '*.py'` → **kosong** (nol perubahan `.py`).
- `git branch -d docs/rapikan-27agustus` → **berhasil dihapus** (`Deleted branch docs/rapikan-27agustus (was 42f3258)`), dilakukan SEBELUM push sesuai instruksi (satu push di akhir).

## Bagian B — Pindahkan 3 file tracked terakhir

### Verifikasi tracked sebelum `git mv`

`git ls-files` mengonfirmasi ketiganya tracked:
- `MESSAGE_TOO_LONG_FIX_REPORT.md`
- `SHADOW_E3_CHECKLIST_OBSERVABILITY_REPORT.md`
- `SHADOW_PROMOTION_CHECKLIST_REPORT.md`

### Pemindahan

| Path lama | Path baru |
|---|---|
| `MESSAGE_TOO_LONG_FIX_REPORT.md` | `docs/reports/2026-08-27-vps-health-shadow-e3/MESSAGE_TOO_LONG_FIX_REPORT.md` |
| `SHADOW_E3_CHECKLIST_OBSERVABILITY_REPORT.md` | `docs/reports/2026-08-27-vps-health-shadow-e3/SHADOW_E3_CHECKLIST_OBSERVABILITY_REPORT.md` |
| `SHADOW_PROMOTION_CHECKLIST_REPORT.md` | `docs/reports/2026-08-27-vps-health-shadow-e3/SHADOW_PROMOTION_CHECKLIST_REPORT.md` |

Dilakukan via `git mv` untuk masing-masing (bukan cp+add+rm), sehingga riwayat commit tetap terlacak.

### Perbaikan link relatif

`SHADOW_PROMOTION_CHECKLIST_REPORT.md` memuat 2 link markdown relatif ke kode yang jadi rusak akibat kedalaman folder baru (dari root ke 3 level di bawah `docs/reports/<folder>/`):
- `[backtest/robustness.py:56-73](backtest/robustness.py#L56-L73)` → diperbaiki jadi `(../../../backtest/robustness.py#L56-L73)`
- `[interfaces/telegram_bot.py:1245-1247](interfaces/telegram_bot.py#L1245-L1247)` → diperbaiki jadi `(../../../interfaces/telegram_bot.py#L1245-L1247)`

Kedua target diverifikasi resolve dengan benar dari lokasi file baru (`test -f ../../../backtest/robustness.py` dan `../../../interfaces/telegram_bot.py` sukses). `MESSAGE_TOO_LONG_FIX_REPORT.md` dan `SHADOW_E3_CHECKLIST_OBSERVABILITY_REPORT.md` tidak memuat link markdown sama sekali — tidak ada yang perlu diperbaiki di keduanya.

Dicek referensi masuk (`rg` untuk pola link markdown `](...NAMA_FILE.md` di seluruh repo) ke ketiga nama file — **nol hasil**, tidak ada dokumen lain yang mereferensikan ketiganya lewat link markdown (hanya via nama file polos dalam backtext di `CHANGELOG.md`, yang mengikuti keputusan konvensi sebelumnya: referensi teks biasa dalam backtick tidak diubah).

### Update indeks

- `docs/README.md`: baris deskripsi folder `2026-08-27-vps-health-shadow-e3/` diperluas untuk menyebutkan eksplisit fix message-too-long dan update checklist promosi shadow_e3 (sebelumnya cuma tersirat lewat "merge/push fix message-too-long").
- `CHANGELOG.md`: entri baru untuk merge `docs/rapikan-27agustus` (`42f3258`) dan pemindahan lanjutan 3 file tracked ini, plus entri merge `shadow-e3/evaluation-and-observability` (`9468f9e`) yang sebelumnya masih berlabel "menunggu review manual" — dikoreksi jadi "sudah di-push" karena sudah di-merge duluan (task sebelumnya).

### Bukti `--follow` — riwayat lama ikut terbawa

```
$ git log --follow --oneline -- docs/reports/2026-08-27-vps-health-shadow-e3/SHADOW_PROMOTION_CHECKLIST_REPORT.md
46b37ae docs: pindahkan 3 file report tracked terakhir + update indeks
9468f9e feat: shadow_e3 outcome-based promotion policy + per-reason observability
48c1e9e docs: add commit/merge/deploy verification section to promotion checklist report
c4bc614 feat: add read-only shadow_e3 promotion criteria checklist
```

4 commit historis (termasuk commit pembuatan awal `c4bc614`) ikut terbawa — bukti `git mv` bekerja, bukan file baru yang kehilangan riwayat.

Commit Bagian B: `46b37ae docs: pindahkan 3 file report tracked terakhir + update indeks`.

**Catatan koreksi selama pengerjaan**: langkah `git add` awal sempat memakai pathspec `'*.md'` yang secara tidak sengaja ikut men-stage seluruh isi folder untracked `AlizaAI-Crypto/01-hasil-audit-codex/` (bundle ekspor, di luar scope). Ini langsung terdeteksi dan di-`git restore --staged` sebelum commit — bundle ekspor TIDAK pernah masuk ke commit manapun, tetap sepenuhnya untracked seperti seharusnya.

## Verifikasi gabungan (Bagian A + B)

1. `git diff --stat 9468f9e main` (titik sebelum Bagian A vs `main` final): 9 file berubah, semuanya `.md` — `CHANGELOG.md`, `docs/README.md`, `RAPIKAN_27AGUSTUS_REPORT.md`, 3 file di `docs/reports/2026-08-27-vps-health-shadow-e3/` dari Bagian A, dan 3 file (2 rename murni + 1 rename dengan edit link) dari Bagian B. `git diff --stat ... -- '*.py'` di rentang yang sama → **kosong**.
2. `bash -n scripts/deploy/deploy.sh` → **PASS**.
3. Full test suite (`venv/bin/python -m pytest -q`) setelah kedua bagian: **342 passed, 3 warnings, 74 subtests passed, 0 failed** — identik dengan baseline sebelum task ini (tidak ada regresi, sesuai ekspektasi karena ini docs-only).
4. Scan broken-relative-link seluruh repo (skrip Python, mengecualikan `AlizaAI-Crypto/`): ditemukan 4 "match" tapi semuanya **false positive** — literal `[teks](target)`/`[text](path)` yang dipakai sebagai contoh sintaks di `BERES_BERES_REPORT.md`, `RAPIKAN_27AGUSTUS_REPORT.md`, dan dua laporan lama 21 Juli (`DOCS_RESTRUCTURE_REPORT.md`, `DOCS_AUDIT_REPORT.md`) — bukan link sungguhan, sudah ada sejak sebelum task ini. Tidak ada broken link baru yang diperkenalkan oleh perubahan hari ini.

## Push

`git push origin main`:

```
9468f9e..46b37ae  main -> main
```

Berhasil pada percobaan pertama, tidak ditolak/non-fast-forward, tidak perlu force-push.

## Status akhir

- `git status -sb` → `main...origin/main` (0 ahead/behind — sinkron penuh). Sisa hanya untracked bundle `AlizaAI-Crypto/01-hasil-audit-codex/*` (di luar scope, tidak berubah).
- `git log --oneline -6`:
  ```
  46b37ae docs: pindahkan 3 file report tracked terakhir + update indeks
  42f3258 docs: rapikan 3 laporan lepas 27 Agustus ke docs/reports
  9468f9e feat: shadow_e3 outcome-based promotion policy + per-reason observability
  4abb826 fix: split oversized Telegram messages instead of failing with "Message is too long"
  8857618 docs: add beres-beres cleanup report
  0caf1ed docs: add changelog entry for docs cleanup (0370c42)
  ```

## Ringkasan

| Langkah | Hasil |
|---|---|
| Bagian A: merge `docs/rapikan-27agustus` | Fast-forward langsung, tanpa rebase (branch bercabang dari tip `main` terkini) |
| Bagian B: `git mv` 3 file tracked | Sukses, riwayat terjaga (dibuktikan `--follow`), 2 link relatif diperbaiki |
| Insiden kecil | `git add -A '*.md'` sempat men-stage bundle ekspor tanpa sengaja — dikoreksi sebelum commit, tidak pernah ter-commit |
| Full test suite | 342 passed, 74 subtests, 0 failed |
| Broken link scan | 0 broken link baru (4 false positive pre-existing) |
| Push ke `origin/main` | Sukses, satu kali, `9468f9e..46b37ae` |
| Status akhir | `main` sinkron penuh dengan `origin/main` |

Tidak ada secret yang ditulis di laporan ini. Tidak ada file `.py` yang disentuh di seluruh rangkaian Bagian A + B.
