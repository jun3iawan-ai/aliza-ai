# Fix BEARISH Palsu dan Fallback Konteks

Tanggal: 18 September 2026
Branch: `fix/bearish-palsu-fallback-konteks`
Status: belum di-commit, belum di-push, dan belum di-merge; menunggu review manual.

## Bug 1 — label BEARISH pada skor seri

- `generate_market_prediction()` sekarang memakai tiga cabang eksplisit: BULLISH, BEARISH, dan NEUTRAL.
- `quant_command()` memakai tiga cabang eksplisit yang sama untuk skor mentah.
- Skenario audit 0–0 (SIDEWAYS, RSI 50, RANGE, whale NEUTRAL, altseason 60) sekarang menghasilkan `NEUTRAL` di output `/predict` dan `/quant`.
- Regresi arah non-seri tetap diverifikasi untuk BULLISH dan BEARISH.
- Pencarian semua konsumen `prediction["bias"]` / `prediction.get("bias")` menemukan satu konsumen langsung: handler `/predict`. Ia hanya menampilkan nilai apa adanya, sehingga tidak ada cabang dua-nilai yang perlu disesuaikan.
- Format Telegram sudah konsisten: label BULLISH/BEARISH sebelumnya juga ditampilkan tanpa emoji tambahan, sehingga NEUTRAL tampil sebagai label setara.

## Bug 2 — fallback global market diam-diam

- `calculate_market_score()` kini memeriksa `fear_greed_status` dan `btc_dominance_status`.
- Jika status bernilai `failed`, komponen diperlakukan identik dengan data `None`: komponen tidak dihitung dari fallback 50.0 dan dihitung sebagai komponen gagal melalui jalur neutral-existing.
- Dengan fixture yang sama, status `ok` mempertahankan skor historis 88; fallback Fear & Greed menghasilkan 85, dominance 86, dan keduanya gagal 83.
- `format_context_for_brief()` diuji untuk status `ok` dan `failed`: output normal tetap sama; fallback tidak crash atau menampilkan `None`, dan menggunakan total yang sudah mengecualikan komponen gagal. Morning Brief dan Evening Summary memanggil formatter yang sama.

## Test

- Baseline sebelum perubahan: 359 passed (sesuai suite awal proyek).
- Regression test baru: 4 passed; bersama `tests/test_message_length_guard.py`: 20 passed.
- Full suite sesudah perubahan: 363 passed, 3 warnings, 74 subtests passed dalam 33.63s.
- Tiga warning berasal dari deprecation warning SWIG saat import, tanpa kegagalan test.

## Scope dan diff

`git diff --stat main`:

- `engine/market/market_context_engine.py` — 4 baris
- `engine/prediction/prediction_engine.py` — 6 baris
- `interfaces/telegram_bot.py` — 7 baris
- `tests/test_prediction_bias_and_market_context.py` — 109 baris baru
