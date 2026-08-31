# Fix: Duplikasi Header, SARAN SPOT Hilang, dan Panjang Pesan UTF-16

**Berdasarkan:** `EVENING_SUMMARY_DUPLIKASI_AUDIT_REPORT.md` (audit read-only, 31 Agustus 2026)
**Branch:** `fix/evening-summary-duplikasi-header-utf16` (belum di-push/merge — menunggu review manual)
**Status:** Task 1-4 selesai diimplementasikan dan diverifikasi via test suite.

---

## Ringkasan

Semua 3 bug terkonfirmasi di laporan audit sudah diperbaiki, plus pengaman idempoten tambahan (Task 4). Lingkup perubahan **hanya** `interfaces/telegram_bot.py` + 2 file test — tidak ada satu baris pun yang menyentuh `engine/shadow/`, `engine/trading/trading_brain.py`, atau `_dispatch_and_record_deterministic_signal` (dikonfirmasi via `git diff --stat main`, lihat bagian Verifikasi).

---

## Task 1 — Dedup header "⚡ KEPUTUSAN HARI INI" yang muncul >1 kali

**Berhasil.** Ditambahkan di `_generate_brief_analysis` (`interfaces/telegram_bot.py`), tepat sebelum dedup marker SARAN SPOT/FUTURES/DISCLAIMER yang sudah ada:

```python
_keputusan_marker = "⚡ KEPUTUSAN HARI INI"
if main_out.count(_keputusan_marker) > 1:
    _lines = main_out.split("\n")
    _hits = [i for i, l in enumerate(_lines) if _keputusan_marker in l]
    main_out = "\n".join(_lines[: _hits[1]]).strip()
```

Kalau `main_out` mengandung header ini lebih dari sekali, hanya blok pertama (sampai sebelum kemunculan kedua) yang dipertahankan — diterapkan SEBELUM dedup marker yang sudah ada, supaya kalau blok kedua juga membawa SARAN SPOT/FUTURES/DISCLAIMER hallucinated, itu ikut terpotong bersih bersama blok kedua.

**Test**: `DuplicateKeputusanHariIniTestCase.test_second_keputusan_block_is_dropped` (`tests/test_evening_summary_report.py`) — mereproduksi struktur persis insiden 31 Agustus 13:23 WIB (blok Bullish/BELI BERTAHAP diikuti blok Bearish/TAHAN dalam satu completion LLM). Assert: `analysis.count("⚡ KEPUTUSAN HARI INI") == 1`, konten blok pertama (Trending Bullish/BELI BERTAHAP) dipertahankan, dan konten blok kedua (Trending Bearish/Neutral-Bearish/TAHAN) hilang total — bukan cuma headernya.

**Catatan proses**: mock LLM routing awal disalin dari test lama (`FallbackMessageTestCase`) yang mengecek `"KEPUTUSAN HARI INI (WAJIB DIIKUTI)" in prompt and "6 section saja" in prompt` — ternyata substring pertama itu hanya ada di prompt `_generate_spot_analysis`/`_generate_futures_analysis`, TIDAK PERNAH di `main_prompt`, jadi kondisi itu selalu False untuk semua 3 prompt. Test lama tetap lolos karena assertion-nya lemah (`assertIn("KEPUTUSAN HARI INI", analysis)` — cocok juga dengan teks fallback generik). Test baru saya awalnya gagal karena mewarisi bug routing yang sama; diperbaiki dengan memakai `"6 section saja" in prompt` saja (terverifikasi unik untuk `main_prompt` via `grep`). Test lama (`FallbackMessageTestCase`) tidak disentuh — di luar lingkup 3 bug yang dikonfirmasi audit, dan tetap lolos apa adanya.

---

## Task 2 — Header "🟢 SARAN SPOT" hilang untuk kondisi "tidak ada setup"

**Berhasil, dua lapis sesuai instruksi.**

### Lapis 1 — perbaikan prompt

`_action_constraint` (kondisi TAHAN, `market_score < 40` atau `fear_greed < 25`):

```python
_action_constraint = (
    "TAHAN — JANGAN rekomendasikan entry baru. Tulis persis: "
    "\"🟢 SARAN SPOT (Swing 1-7 hari)\\nTidak ada setup spot yang layak — tunggu pullback ke support.\""
)
```

`OUTPUT FORMAT` di prompt — contoh kondisi "tidak ada setup" sekarang mengulang header lengkap (pola sama seperti `_generate_futures_analysis` yang sudah benar sejak awal):

```
[Jika tidak ada setup: "🟢 SARAN SPOT (Swing 1-7 hari)
Tidak ada setup spot yang layak — tunggu pullback ke support."]
```

### Lapis 2 — pengaman programatik

```python
out = await _call_llm_async(prompt)
if out:
    if not out.lstrip().startswith("🟢 SARAN SPOT"):
        out = "🟢 SARAN SPOT (Swing 1-7 hari)\n" + out.lstrip()
    return out
```

Kalau LLM tetap lupa header (terlepas dari prompt yang sudah diperbaiki di Lapis 1), header ditempel manual — jadi section ini tidak bisa hilang total lagi apa pun yang LLM lakukan.

**Test**: `SpotAnalysisHeaderSafeguardTestCase` (`tests/test_evening_summary_report.py`), 2 test:
- `test_missing_header_from_llm_gets_prepended`: mock `_call_llm_async` mengembalikan kalimat TANPA header (simulasi persis kegagalan asli) → assert output tetap diawali `"🟢 SARAN SPOT (Swing 1-7 hari)"`.
- `test_header_already_present_is_not_duplicated`: LLM sudah menulis header dengan benar → assert header muncul tepat 1 kali (pengaman tidak menduplikasi).

---

## Task 3 — `_split_message_for_telegram()` berbasis UTF-16, bukan `len()` Python

**Berhasil.** Ditambahkan 2 helper baru:

```python
def _utf16_len(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2

def _utf16_slice_index(text: str, max_units: int) -> int:
    units = 0
    for i, ch in enumerate(text):
        ch_units = 2 if ord(ch) > 0xFFFF else 1
        if units + ch_units > max_units:
            return i
        units += ch_units
    return len(text)
```

`_split_message_for_telegram` diubah untuk memakai `_utf16_len`/`_utf16_slice_index` di semua titik pengecekan panjang (pengecekan awal, kondisi loop, pengambilan `window`), sambil tetap mempertahankan logika titik-potong alami (`\n\n` → `\n` → spasi) yang sudah ada — window yang dicari titik potongnya sekarang dihitung dari budget UTF-16 (via `_utf16_slice_index`), bukan indeks karakter Python langsung. Ditambahkan juga pengaman forward-progress (`split_at = window_end if window_end > 0 else 1`) untuk mencegah infinite loop pada kasus pathological (limit sangat kecil) — tidak berdampak ke penggunaan produksi (`limit=4096`).

**Test** (`tests/test_message_length_guard.py`):
- `Utf16AwareLengthTests` (5 test): memverifikasi emoji astral-plane = 2 UTF-16 unit vs 1 code point Python; karakter BMP biasa sama di kedua pengukuran; **regresi inti** — teks 3200 code point (di bawah limit 4096 lama, dulu lolos tanpa dipecah) tapi 6400 UTF-16 unit (di atas limit asli Telegram) sekarang tetap terpecah dan setiap potongan ≤ 4096 UTF-16 unit; konten mirip `brief_header` (emoji per baris) tetap dalam batas UTF-16; `_utf16_slice_index` tidak pernah melebihi budget yang diminta.
- `TelegramRealLimitSimulationTests` (1 test): `StrictFakeBot` yang menolak teks dengan `_utf16_len > 4096` (mensimulasikan perilaku asli Telegram, bukan aproksimasi `len()` Python) — memverifikasi `dispatch_alert_message` dengan header padat-emoji tidak memicu penolakan tersimulasi ini.

---

## Task 4 — Pengaman idempoten di `_parse_and_record_signals` (prioritas rendah)

**Dikerjakan** (tidak dilewati — cukup ringan untuk diimplementasikan dengan aman tanpa mengganggu Task 1-3).

```python
_seen_keys: set[tuple] = set()
for block in coin_blocks:
    ...
    _dedup_key = (coin, setup, entry, sl, tp)
    if _dedup_key in _seen_keys:
        continue
    _seen_keys.add(_dedup_key)
    ...
    record_signal({...})
```

Dedup berdasarkan kombinasi `(coin, setup, entry, sl, tp)` dalam satu pemanggilan — kalau bug duplikasi Task 1 kambuh saat market sedang punya setup valid (skenario yang BELUM pernah terjadi di insiden 31 Agustus, tapi disebutkan sebagai risiko residual di audit), blok coin yang identik tidak akan tercatat dobel ke `signal_tracking`.

**Test**: `ParseAndRecordSignalsIdempotencyTestCase` (`tests/test_evening_summary_report.py`), 2 test — blok coin identik yang diduplikasi hanya memicu `record_signal` sekali; blok coin yang berbeda (BTC dan ETH) tetap masing-masing tercatat.

---

## Verifikasi

### Lingkup perubahan

```
$ git diff --stat main
 interfaces/telegram_bot.py           |  79 +++++++++++-
 tests/test_evening_summary_report.py | 231 +++++++++++++++++++++++++++++++++++
 tests/test_message_length_guard.py   |  91 ++++++++++++++
 3 files changed, 395 insertions(+), 6 deletions(-)
```

Hanya `interfaces/telegram_bot.py` + 2 file test — **tidak ada** perubahan di `engine/shadow/`, `engine/trading/trading_brain.py`, atau `_dispatch_and_record_deterministic_signal`, sesuai batasan wajib.

### Full test suite

**Sebelum fix** (branch di-stash sementara, kode identik dengan `main`):
```
342 passed, 3 warnings, 74 subtests passed in 34.22s
```

**Sesudah fix** (semua 4 task + test baru):
```
353 passed, 3 warnings, 74 subtests passed in 33.89s
```

0 gagal di kedua kondisi. Selisih +11 test baru (5 di `test_evening_summary_report.py`: dedup KEPUTUSAN duplikat, 2x safeguard header spot, 2x idempotency parse; 6 di `test_message_length_guard.py`: 5x UTF-16 length awareness, 1x simulasi penolakan Telegram asli), tidak ada test lama yang berubah hasilnya.

Catatan lingkungan: environment ini kadang mengalami kegagalan koneksi transient ke `huggingface.co` saat mengimpor `interfaces.telegram_bot` (rantai import via `core/knowledge_base.py` yang memuat model `sentence-transformers/all-MiniLM-L6-v2`) — tidak terkait perubahan ini, hilang sendiri saat di-retry, dan konsisten muncul di kedua run (sebelum & sesudah fix) sampai retry berhasil.

### Branch & commit

- Branch: `fix/evening-summary-duplikasi-header-utf16`
- **Belum di-push, belum di-merge, service belum di-restart** — menunggu review manual, sesuai pola kerja sebelumnya di proyek ini.
