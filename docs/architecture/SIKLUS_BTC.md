# Siklus BTC (konteks jangka panjang)

Modul: `engine/market/btc_cycle.py`. Konteks dasar/puncak BTC, **bukan sinyal entry**, **tidak masuk skor Konteks Market**.

## Data (gratis)
- Coin Metrics Community: `PriceUSD`, `CapMVRVCur`, `HashRate` (harian, 1000 hari terakhir)
- FRED `VIXCLS` (butuh `FRED_API_KEY`; gagal -> VIX tidak tersedia, sisanya tetap jalan)

## Indikator (ambang dari backtest 10 Nov 2026, tidak di-tuning)
- Dasar: MVRV < 1; VIX > 30 (maks 5 hari terakhir); Hash ribbon pulih (MA30 hash menembus MA60 setelah capitulation, aktif 30 hari); Breakout MA128 & MA200 setelah di bawah keduanya dalam 90 hari (aktif 30 hari)
- Puncak: Pi Cycle (MA111 vs 2xMA350, "dekat" bila >= 95%); jendela halving hari 480-560 (info)
- Zona: Rawan Puncak bila Pi >= 95%; Akumulasi bila MVRV<1 atau >= 2 sinyal dasar; selain itu Netral
- Caveat backtest: N kecil (4-20), in-sample; konfluensi tidak terbukti lebih baik dari indikator tunggal

## Operasional
- Job harian 00:05 UTC (07:05 WIB) `btc_cycle_job`; notifikasi hanya saat zona BERUBAH dan zona baru bertahan 3 hari data berbeda (`CONFIRM_DAYS`); perubahan sementara tidak dialert. State di `ngov`: `btc_cycle.zone` (terkonfirmasi), `btc_cycle.pending` (zona calon + hitungan hari); observasi pertama = baseline. Kirim gagal -> zona terkonfirmasi tidak berubah, dicoba lagi besok
- Perintah `/siklus`: tampilkan cache; bila cache > 26 jam, ambil ulang; sumber gagal -> cache + catatan
- Cache: `data/btc_cycle_last.json` (env `ALIZA_CYCLE_CACHE`)
- `context.json`: field tambahan `cycle` (ringkasan; v tetap 1), diisi dari cache saat `export_context`; tidak ada cache -> field tidak ditulis

## Peringatan data usang
- Data segar = `asof` tertinggal <= 2 hari dari hari ini (UTC). Refresh gagal atau data usang selama >= 3 hari -> SATU peringatan Telegram (`btc_cycle.stale_warned`); pulih -> satu pesan pemulihan.
- Selama usang, alert zona tidak dihitung (zona terkonfirmasi tetap). State `ngov`: `btc_cycle.last_fresh`.
