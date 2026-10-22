# Komponen Makro Konteks Market: label CPI dan ketahanan FRED

Diterapkan 22 Okt 2026 (permintaan dari sisi Porto). Skema `context.json` v1 tidak berubah; hanya teks `detail` komponen `macro`.

## 1. Label CPI
- `get_macro_data("CPIAUCSL","pct_change_yoy")`: `value` = inflasi **tahunan (YoY)**, `change` = inflasi **bulanan (MoM)**.
- Skor Makro memakai MoM (`cpi_change`). Dulu detail hanya "CPI: +0.65%" sehingga terbaca seperti inflasi tahunan.
- Sekarang: `CPI MoM: +0.65% (YoY 4.02%) | Fed: 3.75% (naik)`. Format "bagian1 | bagian2" dan awalan "Fed" dipertahankan.
  YoY tidak tampil bila datanya tidak ada; tanpa data sama sekali: `CPI MoM: — | Fed: —`.
- Pesan Telegram `/market_context` memakai builder yang sama, jadi teksnya ikut berubah.
- Field internal baru di komponen (bukan di JSON): `cpi_yoy`, `cpi_yoy_prev`, `stale_sec`.

## 2. Keputusan skor: TIDAK diubah
- Aturan skor: MoM < 0 & Fed tidak naik = 20; MoM < 0 & Fed naik = 12; MoM < 0,5 & Fed tidak naik = 10; selain itu 4.
- Data 22 Okt: MoM +0,65% (>= 0,5) → 4/20. YoY 4,02% naik dari 3,71% (hawkish juga) → pembacaan YoY memberi arah yang sama, jadi memasukkannya
  hari ini tidak mengubah skor. Menambah YoY ke rumus berarti menggeser skor historis tanpa backtest; belum ada alasan cukup.
- Catatan desain untuk nanti: ambang MoM 0,5%/bulan (~6% setahun) tinggi; tren YoY (naik/turun) kandidat sinyal tambahan bila ada backtest.

## 3. Ketahanan FRED (`engine/market/macro_monitor.py`)
- Retry: 3 percobaan (jeda 2 dtk lalu 5 dtk) untuk HTTP 5xx/429, timeout/koneksi/protokol, body kosong atau JSON rusak, observasi kosong.
  HTTP 4xx lain (key salah, dsb.) tidak diulang. Timeout per percobaan 25 dtk (dulu 60 tanpa retry).
- Gagal total → backoff 60 dtk (tidak menghajar FRED tiap panggilan), lalu pakai **last-good**.
- Last-good: observasi terakhir yang berhasil, disimpan di memori + `data/macro_last_good.json` (mode 600, atomik; env `ALIZA_MACRO_CACHE`),
  selamat dari restart. Dipakai maksimal **7 hari**. Bila umurnya > 6 jam (TTL cache normal), `stale=True`.
- Respons gagal/kosong **tidak pernah** di-cache sebagai valid: observasi harus berupa list dengan >= 2 titik bernilai angka. (Sebelumnya respons 200 dengan
  `observations: []` ikut di-cache 6 jam.)
- `ok=false` + skor netral 10/20 hanya bila tidak ada data sama sekali (tidak ada last-good <= 7 hari).
- Saat stale, detail diberi suffix: `... | Fed: 3.75% (naik) | data cache 3 jam` / `... | data cache 2 hari`; `ok` tetap true.
- `get_macro_data` mengembalikan tambahan `stale` dan `age_sec`; pemanggil lama mengabaikannya.

## 4. Tes
`tests/test_macro_resilience.py` (retry per jenis gangguan, 4xx, backoff, tidak men-cache gagal/kosong, last-good, batas 7 hari, selamat restart, detail, skor tidak berubah).
`tests/test_market_context_export.py` disesuaikan dengan label baru. `tests/conftest.py` mengisolasi cache makro.
