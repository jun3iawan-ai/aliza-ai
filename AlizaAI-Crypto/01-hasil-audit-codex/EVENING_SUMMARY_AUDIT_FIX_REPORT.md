# Audit & Perbaikan Bug "Evening Summary" / "Keputusan Hari Ini"

Repo: `/opt/aliza-ai`, branch `fix/evening-summary-report-bugs` (dari `main`, belum di-merge/deploy).
Kejadian yang dievaluasi: pesan Telegram nyata dari `evening_summary_job`, 21 Juli 2026 ~20:00-20:01 WIB.

---

## Langkah 0 — Kesimpulan Diagnosis (WAJIB dibaca dulu)

### Jawaban inti: (a) atau (b)?

**Jawabannya bukan murni (a) atau (b) — melainkan hibrida, dan itu penting:**

Angka Entry/SL/Target 1/Target 2/Leverage/RR di SARAN FUTURES (dan SARAN SPOT) **memang di-generate independen oleh LLM (`gpt-4o-mini` via `_call_llm_async`)** sebagai teks bebas — **jawaban (b) benar untuk sumber angkanya**. Prompt template di [interfaces/telegram_bot.py:3897-3939](interfaces/telegram_bot.py#L3897-L3939) (`_generate_futures_analysis`) secara harfiah meminta LLM **menghitung sendiri** angka-angka ini di dalam completion teks:

```
VALIDATION RULES:
RULE 2: SL wajib 5-8% dari entry
RULE 3: RR minimum 2.0x
...
OUTPUT FORMAT (HANYA section ini):
  Entry: $[level] — konfirmasi dulu sebelum entry
  SL: $[level] ([X]% dari entry)
  Target 1: $[level] (+[X]%) — ambil 50%
  Target 2: $[level] (+[X]%) — ambil sisa
  RR: [hitung: (T1-Entry)/(Entry-SL)]
```
([interfaces/telegram_bot.py:3915-3925](interfaces/telegram_bot.py#L3915-L3925), sama persis di `_generate_spot_analysis` untuk SARAN SPOT, [interfaces/telegram_bot.py:3719-3732](interfaces/telegram_bot.py#L3719-L3732)). Ini **persis** anti-pattern yang dikhawatirkan di konteks prompt ini ("LLM menulis ulang SL 6%/TP 2R mekanis") — jalur ini **sama sekali terpisah** dari `TradingBrain`/`signal_engine`/backtester deterministik yang disasar Fase 1-4, dan **tidak pernah** tersentuh validasi winrate manapun. Ini murni fitur presentasi/laporan harian, bukan bagian dari pipeline sinyal yang di-backtest.

**TIDAK BISA dikutip file:line untuk dokumen `03-analisis/02-roadmap-peningkatan-winrate.md`** yang disebut di konteks prompt ini — sudah dicari dengan `find` di seluruh `/opt/aliza-ai` dan tidak ditemukan sama sekali (kemungkinan ada di lokasi lain di luar checkout repo ini). **TIDAK PASTI** isi persis dokumen itu; kesimpulan di atas didasarkan murni pada pembacaan kode yang ada, bukan pada dokumen tersebut.

**TAPI** — dan ini bagian pentingnya — **ada lapisan kode Python deterministik** (`_reorder_section_by_rr`, [interfaces/telegram_bot.py:2555](interfaces/telegram_bot.py#L2555)) yang duduk di antara output mentah LLM dan pesan Telegram final. Fungsi ini **sudah lama ada** dan secara aktif:
- Menghitung ulang RR dari Entry/SL/Target yang ditampilkan (bukan percaya angka RR yang ditulis LLM).
- Memaksa SL ke rentang 5-8% kalau LLM menulis di luar rentang itu.
- Memaksa RR minimum 2.0x dengan menggeser target kalau LLM menulis RR di bawah itu.
- Menghitung ulang persentase Target 1/Target 2 dari Entry yang ditampilkan.
- Mengurutkan entry per-coin dari RR tertinggi ke terendah.

Jadi tim sebelumnya **sudah menyadari risiko LLM generatif untuk angka-angka ini** dan sudah membangun guardrail kode — **bug #2 dan #3 di audit ada DI DALAM guardrail ini, bukan di teks bebas LLM yang tak tersentuh kode**. Ini artinya kedua bug itu **murni bug logika Python yang bisa diperbaiki secara mekanis**, sesuai instruksi prompt ini (item 1 & 2 di bawah) — **bukan** kasus "LLM generatif tak tervalidasi" yang harus didiskusikan sebagai keputusan produk. Detail akar masalah di masing-masing bagian di bawah.

**Yang TETAP jadi temuan besar untuk didiskusikan** (di luar cakupan perbaikan formatting): fakta bahwa angka Entry/SL/Target *awal* tetap murni karangan LLM (guardrail hanya mengoreksi *setelah* LLM menulis, tidak menjamin levelnya make sense secara teknikal — mis. SL/Target tidak diverifikasi terhadap support/resistance aktual, funding rate, atau likuiditas) — lihat bagian "Rekomendasi" di bagian bawah laporan ini.

### Ringkasan temuan per poin audit

| # | Temuan audit | Root cause (kode) | Kategori |
|---|---|---|---|
| 1 | Fallback error bocor ke user | `main_out` kosong setelah dedup section SARAN SPOT/FUTURES/DISCLAIMER dari respons LLM utama → fallback generik | Bug formatting — **diperbaiki** |
| 2 | Target 1/Target 2 tertukar di 4/4 setup | `enforce_min_rr()` lama hanya menulis ulang "Target 1" untuk memenuhi RR≥2.0 tanpa mengecek posisinya vs Target 2 | Bug logika Python (bukan LLM) — **diperbaiki** |
| 3 | Label % SL tidak match angka (BTC, XRP) | `enforce_sl_range()` tidak pernah menulis ulang teks "(X% dari entry)", hanya angka dolar SL | Bug logika Python (bukan LLM) — **diperbaiki** |

---

## 1. Kode `evening_summary_job` & alur SARAN SPOT/FUTURES

`evening_summary_job()` — [interfaces/telegram_bot.py:5373](interfaces/telegram_bot.py#L5373) — mengirim **dua pesan**:
1. `brief_header` ("🌙 EVENING SUMMARY", data deterministik: snapshot, funding, macro, cross-asset) — [interfaces/telegram_bot.py:5449-5463](interfaces/telegram_bot.py#L5449-L5463).
2. `analysis = await _generate_brief_analysis(brief_data)` ("⚡ KEPUTUSAN HARI INI" + SARAN SPOT + SARAN FUTURES + DISCLAIMER, semuanya digabung jadi satu pesan) — [interfaces/telegram_bot.py:5471](interfaces/telegram_bot.py#L5471).

`_generate_brief_analysis()` ([interfaces/telegram_bot.py:3957](interfaces/telegram_bot.py#L3957)) menjalankan **3 pemanggilan LLM paralel** via `asyncio.gather` ([interfaces/telegram_bot.py:4242-4246](interfaces/telegram_bot.py#L4242-L4246)):
- `main_prompt` → 6 section "⚡ KEPUTUSAN HARI INI" s/d "📋 SKENARIO MINGGU INI".
- `_generate_spot_analysis()` → section "🟢 SARAN SPOT" saja.
- `_generate_futures_analysis()` → section "📊 SARAN FUTURES" saja.

**Poin krusial**: ketiga panggilan ini **independen** — kegagalan salah satu (mis. main_prompt gagal ikuti format) **tidak** berarti dua lainnya ikut gagal. Ini yang mendasari perbaikan item 3 di bawah.

---

## 2. Sumber angka SARAN FUTURES/SPOT — jawaban detail

Dijawab lengkap di Langkah 0 di atas: **LLM generatif, dengan lapisan koreksi deterministik `_reorder_section_by_rr` di belakangnya**. Prompt spesifik yang meminta LLM menghitung sendiri:

```
RULE 3: RR minimum 2.0x
RULE 4: Leverage maksimal 5x, rekomendasi 2-3x untuk swing
...
Target 1: $[level] (+[X]%) — ambil 50%
Target 2: $[level] (+[X]%) — ambil sisa
RR: [hitung: (T1-Entry)/(Entry-SL)]
```
([interfaces/telegram_bot.py:3915-3925](interfaces/telegram_bot.py#L3915-L3925))

---

## 3. Definisi fallback error & frekuensi di log

Fallback: [interfaces/telegram_bot.py:4308-4327](interfaces/telegram_bot.py#L4308-L4327) (sebelum perbaikan). Terpicu ketika:

1. `main_out` (respons LLM untuk 6 section) berhasil didapat (non-kosong) TAPI mengandung salah satu marker `"SARAN SPOT"`/`"SARAN FUTURES"`/`"DISCLAIMER"` — artinya LLM **mengabaikan instruksi** "Jangan tulis saran spot atau futures" dan menuliskan section itu sendiri.
2. Kode dedup ([interfaces/telegram_bot.py:4300-4307](interfaces/telegram_bot.py#L4300-L4307)) memotong `main_out` tepat SEBELUM baris marker pertama itu muncul.
3. Kalau baris marker itu muncul di **awal** respons LLM (artinya LLM sama sekali tidak menulis 6 section yang diminta, langsung "SARAN SPOT..." dari awal), hasil potongan jadi **string kosong** → fallback generik dipakai.

**Frekuensi di log 7 hari terakhir** (`logs/aliza.log` + rotasi `.1` s/d `.7.gz`, mencakup 15-21 Juli 2026): `grep "main_out kosong setelah dedup"` → **1 kali kejadian**, persis di `2026-07-21 20:01:02,582` — cocok tepat dengan insiden yang dievaluasi user. **Bukan kejadian sering** — ini kasus langka (1x dalam ~7 hari observasi, dari job yang jalan 2x/hari = ~14 run), tapi tetap layak diperbaiki karena user memang mengalaminya secara langsung dan bisa terjadi lagi kapan saja LLM "lupa" instruksi format.

Log tepat sebelum kejadian menunjukkan panggilan LLM utama **berhasil** (`OpenAI API usage: ... completion_tokens=498`), tapi isinya pasti dimulai dengan salah satu marker di atas — konten mentahnya sendiri tidak di-log di mana pun (tidak ada logging raw LLM completion), jadi tidak bisa dipastikan persis apa yang LLM tulis, hanya bisa dipastikan mekanismenya dari kode.

---

## 4. Reproduksi matematis bug Target1/Target2 & SL%

Direproduksi langsung dengan memanggil `_reorder_section_by_rr()` yang asli (kode SEBELUM perbaikan) memakai input yang meniru output LLM yang masuk akal — hasilnya **cocok persis** dengan angka yang dilaporkan user untuk BTC:

```python
sample = """• BTC: LONG
  Entry: $66,000.00 — konfirmasi dulu sebelum entry
  SL: $62,040.00 (5% dari entry)
  Target 1: $68,500.00 (+3.8%) — ambil 50%      # LLM: near target, RR asli < 2.0x
  Target 2: $70,000.00 (+6.1%) — ambil sisa      # LLM: far target
  RR: 1.1x
"""
# Output _reorder_section_by_rr (KODE LAMA):
#   Target 1: $73,920.00 (+12.0%) — ambil 50%   <- MATCH PERSIS temuan audit
#   Target 2: $70,000.00 (+6.1%) — ambil sisa    <- MATCH PERSIS temuan audit
#   RR: 2.0x                                       <- MATCH PERSIS temuan audit
#   SL: $62,040.00 (5% dari entry)                 <- label salah TETAP tidak disentuh, MATCH PERSIS
```

**Root cause #2 (Target1/Target2 tertukar)**: `enforce_min_rr()` lama ([interfaces/telegram_bot.py:2683](interfaces/telegram_bot.py#L2683) sebelum perbaikan) membaca `target = parse_target_t1(entry_text)` — **selalu Target 1**, lalu kalau RR-nya (dihitung dari Target 1) di bawah `MIN_RR=2.0`, menghitung target baru = `entry + sl_distance*2.0` dan **menulis ulang hanya baris "Target 1:"** — tanpa pernah mengecek posisinya relatif ke Target 2. Kalau Target 1 asli LLM sudah masuk akal (dekat, RR rendah — wajar untuk target "ambil 50% duluan"), fungsi ini memaksanya jadi LEBIH JAUH dari Target 2 yang tidak disentuh, membalik urutan operasional target dekat/jauh. Untuk kasus BTC: `SL distance = 66000-62040 = 3960`; `new_target1 = 66000 + 3960*2.0 = 73920` — **persis** angka $73.920 di laporan user.

**Root cause #3 (label % SL salah)**: `enforce_sl_range()` ([interfaces/telegram_bot.py:2627](interfaces/telegram_bot.py#L2627) sebelum perbaikan) HANYA mengganti **angka dolar** SL kalau `sl_pct` di luar rentang [5%, 8%] — kalau sudah dalam rentang (BTC: 6,00%, dalam rentang), fungsi return tanpa menyentuh apa pun, termasuk teks `"(5% dari entry)"` yang ditulis LLM (salah, seharusnya 6,00%). **Tidak ada fungsi analog `fix_target_percentages()` untuk baris SL** sebelum perbaikan ini — itulah kenapa Target 1/Target 2 punya persentase yang selalu benar (ada `fix_target_percentages()`) sementara SL tidak.

Direproduksi juga untuk XRP dengan angka SL yang sama persis dengan laporan user ($1.03 dari entry $1.10, forced target $1.24, RR 2.0x) — lihat commit/diff untuk detail eksperimen.

---

## Perbaikan yang Dilakukan

### 1. Urutan Target 1 (dekat)/Target 2 (jauh) — [interfaces/telegram_bot.py:2555](interfaces/telegram_bot.py#L2555)

Ditambahkan `enforce_target_order()`: membandingkan posisi Target 1 vs Target 2 relatif ke Entry (arah LONG/SHORT-aware), dan **menukar nilai dolar** keduanya kalau Target 1 ternyata lebih jauh dari Target 2 — dijalankan **sebelum** enforcement RR minimum, supaya langkah berikutnya selalu bekerja di atas pasangan target yang sudah benar posisinya.

`calc_rr()` dan `enforce_min_rr()` diubah untuk selalu memakai **Target 2 (far/final)** sebagai target yang mendefinisikan RR — bukan Target 1 lagi — via helper baru `parse_target_far()` (fallback ke Target 1/Target generik untuk teks legacy satu-target). Konsisten dengan instruksi prompt ini: **angka RR itu sendiri tidak diubah semantiknya** (tetap dari target final/jauh), cuma sekarang label Target 1 vs Target 2 dijamin sesuai posisi harga sebelum RR dihitung/ditulis ulang.

Kalau `enforce_min_rr()` perlu menggeser target untuk memenuhi RR≥2.0, yang digeser sekarang **Target 2** (target final), bukan Target 1 — Target 1 (partial/dekat) tidak pernah disentuh oleh enforcement RR ini lagi.

Diverifikasi ulang dengan input yang sama persis seperti reproduksi bug di atas:
```
Target 1: $70,000.00 (+6.1%) — ambil 50%   <- sekarang dekat, benar
Target 2: $73,920.00 (+12.0%) — ambil sisa <- sekarang jauh, benar
RR: 2.0x                                    <- tidak berubah, tetap dari target final
```

**Efek samping positif (ditemukan, tidak sengaja dicari)**: `_parse_and_record_signals()` ([interfaces/telegram_bot.py:5178](interfaces/telegram_bot.py#L5178)) — fungsi yang merekam sinyal dari teks laporan ke `signal_tracking` DB untuk evaluasi — membaca `tp` dari regex `Target\s+1` ([interfaces/telegram_bot.py:5200](interfaces/telegram_bot.py#L5200)). Selama bug ini aktif, nilai yang direkam sebagai "TP" untuk setiap sinyal dari laporan harian kemungkinan adalah target JAUH yang salah label, bukan target dekat yang sebenarnya dimaksud "Target 1". Setelah perbaikan ini, `_parse_and_record_signals()` otomatis membaca nilai yang benar tanpa perlu disentuh sama sekali (karena ia membaca ulang teks `analysis` final yang sudah benar) — **tidak ada perubahan kode di fungsi ini**, cuma dicatat sebagai temuan karena berdampak ke data historis yang mungkin sudah terekam salah (lihat Rekomendasi).

### 2. Label persentase SL — [interfaces/telegram_bot.py:2672-2686](interfaces/telegram_bot.py#L2672-L2686)

Ditambahkan `fix_sl_percentage()`: menghitung ulang `(Entry-SL)/Entry` dari Entry/SL yang **benar-benar ditampilkan** di pesan (setelah `enforce_sl_range()` menyesuaikan angka dolarnya kalau perlu), lalu menulis ulang teks `"(X% dari entry)"` — persis pola yang sudah ada untuk `fix_target_percentages()`, sekarang juga ada untuk SL. Dijalankan tepat setelah `enforce_sl_range()` di pipeline processing per-entry.

Diverifikasi: BTC "(5% dari entry)" → "(6.0% dari entry)"; XRP "(4.5% dari entry)" → "(6.4% dari entry)" — keduanya cocok dengan perhitungan manual audit (6,00% dan 6,36%≈6,4%).

### 3. Fallback error tidak bocor — [interfaces/telegram_bot.py:4308-4331](interfaces/telegram_bot.py#L4308-L4331)

Karena Langkah 0 mengonfirmasi SARAN SPOT/FUTURES berasal dari panggilan LLM **terpisah dan independen** dari kegagalan `main_out` (bukan jalur deterministik terpisah seperti opsi (a) yang dibayangkan di prompt, tapi tetap independen secara operasional) — keputusannya: **SARAN SPOT/FUTURES tetap tampil apa adanya** (tidak disembunyikan), hanya teks fallback untuk section "⚡ KEPUTUSAN HARI INI" yang diperhalus:

- `"Conviction: X/10 — Analisis tidak tersedia (LLM tidak mengikuti format)."` → `"Conviction: X/10 — Analisis makro harian gagal diproses untuk sesi ini."`
- `"Format analisis tidak sesuai — gunakan data di brief sebagai acuan."` → `"Ringkasan makro tidak tersedia untuk sesi ini — gunakan data snapshot di atas, serta SARAN SPOT/FUTURES di bawah, sebagai acuan."`

Tidak ada lagi frasa yang membocorkan detail implementasi ("LLM", "format") ke user, tapi tetap jujur bahwa BAGIAN INI (makro/regime) gagal — tidak berpura-pura semuanya normal.

**Catatan cakupan**: ditemukan pola serupa (lebih ringan) di fallback `_generate_spot_analysis`/`_generate_futures_analysis` sendiri — teks `"(LLM timeout/error)"` yang muncul kalau panggilan LLM itu spesifik timeout ([interfaces/telegram_bot.py:3936](interfaces/telegram_bot.py#L3936), [interfaces/telegram_bot.py:4058](interfaces/telegram_bot.py#L4058) kira-kira). Ini **tidak disebut eksplisit** di dua string yang diminta prompt ini untuk diperbaiki, jadi **tidak disentuh** di sini (tetap dalam cakupan sesuai instruksi) — dicatat sebagai temuan tambahan untuk pertimbangan sesi terpisah kalau user mau dibersihkan juga.

---

## Test (`tests/test_evening_summary_report.py`)

9 test, semua terhadap `_reorder_section_by_rr()` (fungsi terstruktur, bisa diuji penuh) dan `_generate_brief_analysis()` (untuk fallback):

| Test | Yang diverifikasi |
|---|---|
| `test_target1_forced_farther_than_target2_gets_swapped_back` | Reproduksi persis bug BTC — Target 1 tetap lebih dekat dari Target 2 setelah fix |
| `test_fully_swapped_labels_get_corrected` | LLM menulis Target 1=jauh, Target 2=dekat sepenuhnya terbalik → tetap dikoreksi ke posisi benar |
| `test_rr_is_still_computed_from_the_far_target` | RR tidak berubah semantik — tetap dari target final/jauh |
| `test_already_correct_ordering_is_left_unchanged_and_idempotent` | Kalau LLM sudah benar, tidak ada perubahan; fungsi idempotent |
| `test_short_entry_target1_stays_nearer_than_target2` | Perilaku sama untuk SHORT (arah terbalik) |
| `test_btc_mislabeled_5pct_corrected_to_actual_6pct` | Reproduksi persis bug SL% BTC |
| `test_xrp_mislabeled_4_5pct_corrected_to_actual_6_4pct` | Reproduksi persis bug SL% XRP |
| `test_already_correct_label_is_unaffected` | Label SL % yang sudah benar tidak diubah |
| `test_fallback_does_not_leak_internal_implementation_wording` | Simulasi LLM utama mengabaikan format → fallback tidak berisi "LLM tidak mengikuti format" |

```
$ venv/bin/python -m pytest tests/test_evening_summary_report.py -v
9 passed in 9.35s
```

Regresi — full test scope (sama seperti verifikasi deploy sebelumnya):
```
$ venv/bin/python -m pytest tests/ test_telegram_authorization.py test_dashboard_*.py -q
178 passed, 3 warnings, 74 subtests passed in 16.04s
```
178 = 169 (baseline sebelum item ini) + 9 test baru. Tidak ada regresi di checker/fitur lain.

---

## File yang Berubah

```
 interfaces/telegram_bot.py        | 91 insertions, 10 deletions (dalam _reorder_section_by_rr
                                       dan fallback _generate_brief_analysis)
 tests/test_evening_summary_report.py | baru, 9 test
```

Tidak ada perubahan pada `BREAKING_KEYWORDS`/prompt template LLM (isi instruksi ke LLM sama sekali tidak diubah — perbaikan murni di lapisan Python `_reorder_section_by_rr` yang MENGOREKSI output LLM setelah didapat), tidak ada checker/sinyal trading lain yang disentuh, `evening_summary_job`/fitur SARAN FUTURES **tidak dinonaktifkan**, `.env` tidak disentuh.

---

## Rekomendasi untuk Anda

1. **Keputusan produk (di luar cakupan perbaikan formatting ini)**: Entry/SL/Target *awal* untuk SARAN SPOT/FUTURES tetap murni karangan LLM berdasarkan level support/resistance yang diberikan sebagai teks — guardrail `_reorder_section_by_rr` yang sudah ada (dan diperbaiki di sini) menjamin RR≥2.0 dan SL dalam rentang 5-8% SETELAH LLM menulis, tapi **tidak** memverifikasi levelnya sendiri masuk akal secara teknikal (mis. Target tidak dicek terhadap resistance aktual, SL tidak dicek terhadap struktur candle). Karena job ini terpisah dan tidak tersentuh Fase 1-4, opsi yang bisa dipertimbangkan: (a) beri disclaimer eksplisit di pesan bahwa SARAN SPOT/FUTURES adalah estimasi AI generatif bukan sinyal tervalidasi (beda dari sinyal `TradingBrain`/E3 shadow yang sudah di-backtest), (b) matikan sementara sampai ada rencana validasi, atau (c) — opsi paling sejalan dengan arah Fase 1-4 — ganti isi section ini dengan level yang benar-benar dihitung dari `TradingBrain`/`signal_engine`/E3 shadow (kalau ada setup aktif untuk coin itu), dan LLM hanya bertugas menjelaskan setup deterministik itu dalam bahasa natural (persis rekomendasi "berhenti menulis ulang SL 6%/TP 2R mekanis" yang disebut dalam konteks prompt ini) — perubahan ini di luar cakupan "bug formatting" dan butuh keputusan Anda dulu sebelum dieksekusi.
2. **Data historis `signal_tracking`**: kalau tabel itu dipakai untuk evaluasi winrate, entri "TP" yang direkam dari laporan harian **selama bug Target1/Target2 aktif** kemungkinan salah (merekam target jauh, bukan target dekat yang seharusnya "Target 1"). Pertimbangkan audit terpisah terhadap data historis itu kalau evaluasi winrate pernah memasukkan sumber `"source": "llm"` ini.
3. **Fallback `"(LLM timeout/error)"`** di `_generate_spot_analysis`/`_generate_futures_analysis` (dicatat di bagian Perbaikan #3) — pertimbangkan dibersihkan juga di sesi terpisah kalau dianggap perlu, konsisten dengan pola kerja audit-dulu-baru-prompt-perbaikan.

Branch `fix/evening-summary-report-bugs` siap direview — belum di-merge/deploy/restart service, menunggu keputusan Anda terutama untuk rekomendasi #1 di atas sebelum lanjut ke tahap deploy.
