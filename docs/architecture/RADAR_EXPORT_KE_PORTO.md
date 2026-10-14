# Ekspor Radar Aliza ke Dashboard Porto (`context.json` → field `radar`)

Diterapkan 14 Okt 2026 (commit `3392aea`, merge `51ab894`). Permintaan dari sisi Porto Crypto Jun; field **tambahan**, `v` tetap 1,
field lama tidak berubah. Porto hanya membaca; Aliza hanya menulis.

## 1. Alur (satu sumber hitung)
- Pesan Telegram `/radar` dan JSON dibangun dari **`generate_radar_pro(snapshot)`** yang sama
  (`engine/market/market_radar_pro_analyzer.py`). `engine/market/radar_export.py` hanya menerjemahkan hasilnya ke bentuk mesin.
- `snapshot_job` (tiap 60 dtk) memanggil `market_context_export.refresh_radar()` setelah snapshot valid. Fungsi ini membaca
  `context.json`, mengganti **hanya** `radar`, menulis atomik (tmp + rename, mode 644, di bawah lock yang sama dengan `export_context`).
  File belum ada / rusak / bukan v1 → tidak menulis apa pun.
- `export_context()` (skor Konteks Market, tiap 15 menit/on-demand) ikut menyertakan radar. Bila hitung radar gagal → skor tetap
  ditulis, radar TERAKHIR dipertahankan dengan ts lamanya. Bila radar belum pernah ada → field `radar` dihilangkan.
- `radar.ts` = waktu snapshot (WIB), bukan waktu tulis. `interval_min` = 1.

## 2. Skema `radar`
`{"ts","interval_min","def":{t4h,t1d,rsi4h,cond,strong},"coins":{SIMBOL:{t4h,t1d,rsi4h,cond,strong,label,src}}}`
- `t4h`/`t1d`: `up|down|side|na`; `rsi4h`: angka 1 desimal atau null; `cond`: `uptrend|downtrend|null`; `strong`: bool.
- Tambahan di luar permintaan: `label` (teks kondisi Telegram apa adanya, mis. "📈 Uptrend", "🚀 Momentum"; null bila netral).
- Kunci coin = SEMUA simbol `/var/lib/porto/coins.json` (urutan sama). Tanpa data (mis. BONE) → `na`/null, `src` null.
- `src`: `binance:XUSDT` (spot), `binance-futures:XUSDT` (coin tanpa spot, mis. FARTCOIN), null bila tidak ada data.
  Catatan: HYPE punya spot tetapi histori 1D spot baru 20 candle, jadi klines 1D diambil dari futures (otomatis); `src` tetap `binance:HYPEUSDT`.

## 3. Definisi persis
- **4H**: close candle 4H yang sudah tertutup (Binance klines, maks 100). MA10 dan MA30 sederhana. `up` bila close > MA10 > MA30,
  `down` bila close < MA10 < MA30, selain itu `side`. Tidak ada ambang persen. Butuh >=30 candle, kurang = `na`.
- **1D**: close 1D tertutup; MA20 vs MA50 dengan aturan sama. Butuh >=50 candle. (Berbeda dari "Tren (SMA50)" Porto; label bisa beda.)
- **RSI 4H**: RSI 14 Wilder dari close 4H tertutup. Candle berjalan tidak dipakai. JSON memberi null bila 4H tidak cukup
  (Telegram dalam kasus langka itu jatuh ke RSI 1D). JSON dibulatkan 1 desimal, Telegram membulatkan dari nilai mentah ke bulat,
  jadi angka bulat bisa beda 1 di titik x,5 (mentah 54,54 → Telegram 55, JSON 54,5).
- **Kondisi**: urutan label di Telegram: Whale Activity (whale HIGH/EXTREME) → Momentum (4H up & RSI>60) → Breakdown Risk (4H down & RSI<40)
  → Uptrend (4H up) → Downtrend (4H down) → Neutral; lalu detektor menimpa (Crash Risk, Altseason, Whale Accumulation, Long Liquidation/Short Squeeze).
  `cond` terisi hanya bila label akhir "Uptrend"/"Downtrend". Uptrend/Downtrend **tidak selalu ⭐** (hanya butuh 4H).
- **strong (⭐)**: 4H dan 1D sama-sama up atau sama-sama down.

## 4. Verifikasi (14 Okt 2026)
- 550 test lulus (14 baru: `tests/test_radar_export.py`). Semua simbol ada, nilai, cond, kesamaan dengan baris `/radar`, ts, radar gagal → skor tetap, `refresh_radar` hanya mengganti radar.
- Produksi: 17 coin = 17 simbol Porto; satu snapshot nyata dibandingkan dengan teks `/radar` → semua baris cocok (arah, RSI, kondisi, ⭐).
- Tidak menyentuh `/opt/metamask-bot`, user `mmbot`, `/var/lib/porto`.

## 5. Opsi nanti
- BONE (tidak ada di Binance spot maupun futures): butuh sumber klines MEXC; belum dikerjakan (keputusan 13 Okt: tidak sekarang).
