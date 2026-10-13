# Daftar Pantau Aliza = Daftar Coin Portofolio Porto

Diterapkan 13 Okt 2026 (commit `f43f8e5` merge `d5f860b`; log ringkas `11aef98` merge `79b04b2`).
Status: LIVE di `aliza-telegram` (PID 128563 saat verifikasi), 0 error di journal.

## 1. Sumber
- Satu-satunya sumber daftar coin pantau: **`/var/lib/porto/coins.json`** (ditulis bot "Porto Crypto Jun", user `mmbot`, mode 644).
- Aliza **hanya membaca**. Tidak pernah menulis ke `/var/lib/porto`, tidak menyentuh `/opt/metamask-bot` atau user `mmbot`
  (ada test yang memastikan file itu hanya dibuka dengan mode baca).
- Format v1: `{"v":1,"source":"porto-crypto-jun","ts":...,"symbols":[...],"coins":[...]}`. Aliza memakai `symbols` (unik).
  `coins` bisa berisi lebih banyak entri dari `symbols` (mis. JTO di dua venue), jadi N = jumlah simbol unik (13 Okt: 17).

## 2. Aturan baca, validasi, fallback, cache
- Dibaca ulang bila (mtime, ukuran, inode) berubah (dicek tiap <=5 dtk) dan dipaksa tiap 5 menit.
- Ditolak seluruhnya (daftar tidak pernah dikosongkan oleh file buruk): bukan objek JSON, `v` != 1 (termasuk `true`/hilang),
  `symbols` kosong / bukan list, simbol bukan string atau tidak cocok `^[A-Z0-9]{1,20}$`, > 100 simbol.
- Urutan fallback: **file valid -> daftar valid terakhir (memori) -> cache disk -> daftar lama** (`LEGACY_CORE_COINS`, 18 coin).
  Setiap fallback dicatat warning (diulang paling cepat per jam per jenis masalah); tidak pernah crash.
- Cache sisi Aliza: `/opt/aliza-ai/data/watchlist_cache.json` (`symbols` + `announced`, ditulis atomik). Bertahan setelah restart.
- Env (opsional): `PORTO_COINS_PATH`, `ALIZA_WATCHLIST_CACHE`, `ALIZA_COIN_SUPPORT_CACHE`. `UNIVERSE_EXCLUDE` tetap berlaku.

## 3. Penerapan ke fitur
- `engine/market/watchlist_source.py` (loader) -> `market_universe.py`: `CORE_COINS`, `MAJOR_COINS`, `TRADABLE_COINS`
  **diperbarui di tempat**, sehingga semua modul yang meng-import-nya ikut berubah tanpa restart.
- Pemakai: snapshot market (`get_tradable_coins` -> `get_analyzable_coins`), cache pasar, selector Analisis Coin, validasi
  coin di perintah (`_allowed_coins()`), funding/OI/long-short & positioning (hanya coin yang punya futures), tokenomics.
- Konteks Market (Tren): teks `x/N coin` dinamis; skala skor Tren tetap 0-40 (breadth proporsional). Skema `context.json` (dibaca Porto)
  tidak berubah: set field identik, `v:1`.
- Job `watchlist_sync` tiap 60 dtk: menyegarkan daftar + dukungan coin, mengirim **1 notifikasi Telegram per perubahan**:
  `📋 Daftar pantau diperbarui dari Porto: +X (...), −Y (...) — total N coin.` (+ baris "Tanpa data Binance (dilewati)").
  Bila kirim gagal, dicoba lagi siklus berikutnya; status "sudah diumumkan" tersimpan di cache (tidak dobel setelah restart).
- Log ringkas (sekali saat pertama dan tiap berubah): `grep "watchlist: sumber=" ` -> `sumber=porto total=17 aktif=16 dilewati_tanpa_data=['BONE']`.
  (Log loader saat import tidak terlihat karena logging belum aktif; makanya log ini dibuat di job.)

## 4. Subset mayor yang SENGAJA terpisah (tidak ikut daftar Porto)
BTC, ETH, BNB, SOL, XRP tetap hardcode untuk: rata-rata funding di komponen Konteks Market (`_COINS`), whale monitor
(`_WHALE_MONITOR_COINS`), section SARAN SPOT / SARAN FUTURES & ringkasan brief (`_BRIEF_COINS`, literal di `telegram_bot.py`),
dan `WATCHLIST` di `volume_spike_detector` / `breakout_detector`. Alasan: logika untuk mayor, bukan daftar pantau (keputusan Jun, 13 Okt).

## 5. Dukungan data per coin (cek real ke Binance, 13 Okt 2026)
Registri: `engine/market/coin_support.py` (spot `ticker/price` + futures `exchangeInfo` PERPETUAL USDT; cache 6 jam; jaringan hanya di
`maybe_refresh()`; data belum diketahui = semua coin dianggap didukung, perilaku lama).

| Coin | Spot | Futures | Funding/OI/LS | Trend/snapshot | CoinGecko id | Perlakuan |
|---|---|---|---|---|---|---|
| ADA ARB ASTER BNB BTC ETH JTO SOL SUI XPL XRP | ya | ya | ya | ya | ya | normal |
| PEPE | ya | `1000PEPEUSDT` | ya | ya | ya | normal |
| HYPE | ya (1D baru 20 candle) | ya | ya | ya (fallback futures lama) | ya | normal |
| TRX, ZEC | ya | ya | ya | ya | ditambah `tron`, `zcash` | normal |
| FARTCOIN | tidak | ya | ya | ya, klines + harga dari futures | ya | dianalisis via futures |
| BONE | tidak | tidak | - | - | ya | **dilewati total** (Tren, funding, positioning, menu Analisis Coin) |

- Tanpa skip eksplisit, BONE ~54 dtk per percobaan fetch (diulang saat retry) di setiap siklus snapshot sampai kena suspend.
- FARTCOIN: fetch pertama dulu ~28 dtk (harga jatuh ke CoinGecko -> `get_coin_id` memicu refresh universe ~86 request/429). Diperbaiki:
  `resolve_coin_id` cek peta statis dulu + harga futures-only dari `fapi/v1/ticker/price` -> 1,7 dtk.

## 6. Dampak ke Konteks Market (data live 13 Okt, komponen lain identik)
| | N | naik/turun/sideways | Skor Tren | Total |
|---|---|---|---|---|
| Daftar lama | 18 | 3/4/11 | 24/40 | 55 Neutral |
| Daftar Porto | 16 | 2/5/9 | 23/40 | 54 Neutral |
Keluar: ETHFI, WLD, OM, TAO (sideways), XAUT (bullish). Masuk: FARTCOIN, ZEC (sideways), TRX (bearish). Data historis coin yang keluar tetap di DB.
Hasil nyata pasca-deploy: `context.json` 16:44:37 -> skor 54, `2/16 coin 4H naik, 5/16 turun`, label Neutral (cocok prediksi).

## 7. Verifikasi deploy
- Siklus snapshot (BTC mulai -> "Snapshot completed"), 60 dtk sekali: sebelum (18 coin) median 2,9 dtk (min 2,5 / maks 7,3, n=10);
  sesudah (16 coin) median 2,1 dtk (min 1,9 / maks 2,3 setelah siklus dingin pertama 12,1 dtk).
  Pembanding hipotetis bila BONE tidak dilewati: >=54 dtk + retry (30 dtk jeda + ~54 dtk) per siklus.
- Notifikasi pertama terkirim 16:38:38 (+4/−5, total 17, catatan BONE); setelah restart kedua tidak dikirim ulang.
- `/var/lib/porto/coins.json`: sha256 dan mtime tidak berubah selama deploy.

## 8. Opsi nanti (tidak dikerjakan)
- BONE via MEXC (Porto memakai MEXC untuk BONE): butuh sumber harga/klines baru; dicatat sebagai opsi, bukan rencana.
- Menjadikan subset mayor ikut daftar Porto: mengubah makna skor funding (meme coin ikut dirata-ratakan) — perlu keputusan terpisah.
