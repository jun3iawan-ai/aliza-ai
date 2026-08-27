# Info Coin Paket 1 — Display-Only, Tanpa API Baru

Tanggal: 21 Agustus 2026
Branch: `feat/info-coin-menu` (dihapus setelah merge)
Basis: `main@5613f95` (state pasca-restrukturisasi menu 5 Agustus 2026)
Commit fitur: `e7eb6ac feat: tambah menu Telegram Info Coin (display-only, paket 1)`
Merge commit: `453bbca Merge branch feat/info-coin-menu`
Push: `5613f95..453bbca main -> main` (berhasil)

Ref: `AUDIT_MENU_INFORMASI.md` Bagian 3 — hanya item kategori **KECIL** yang dikerjakan di paket ini (price/tren, S/R, volume, SMA yang sudah dihitung tapi dibuang, tokenomics dari endpoint CoinGecko yang sudah dipakai, whale proxy dengan disclaimer jujur, suku bunga Fed/FRED, BTC Dominance, Fear & Greed). Item SEDANG/BESAR (EMA, MACD, use case, tim/kemitraan, exchange netflow, aktivitas jaringan) **tidak** dikerjakan di paket ini.

## Ringkasan

Menu Telegram baru **ℹ️ Info Coin** (submenu 📊 Market) menampilkan ringkasan 4 seksi — Teknikal, Tokenomics, On-chain, Makro & Sentimen — untuk satu coin dari 21 watchlist, dipilih lewat selector inline yang sudah ada polanya di codebase. Seluruh fitur murni *display*: tidak ada perubahan pada `generate_signal`, `process_signal`, `signal_tracker`, `notification_governor`, checker/alert job, atau `engine/shadow/` — dikonfirmasi eksplisit lewat test spy (`tests/test_info_coin.py::TestInfoCoinDoesNotTouchSignalPipeline`), bukan sekadar klaim. Tidak ada API eksternal baru; satu-satunya sumber data yang belum pernah dipanggil sebelumnya (CoinGecko `coins/markets?ids=...` untuk tokenomics) adalah endpoint gratis-tanpa-key yang polanya sudah ada persis di `engine/market/dynamic_universe.py`.

Full regresi sebelum dan sesudah merge: **317 passed** (298 baseline + 19 test baru), tidak ada kegagalan.

## Perubahan per file/fungsi

### 1. `engine/market/market_analyzer.py` — ekspos `ma20`/`ma50`/`ma200`

- `market_signal()`: dict `result` (sekitar baris 470-500) ditambah 3 key baru — `"ma20": ma20, "ma50": ma50, "ma200": ma200` — memakai variabel lokal yang **sudah dihitung** sebelumnya di fungsi yang sama (`_moving_average(prices, 20/50/200)`, sekitar baris 372-374) tapi sebelumnya dibuang begitu saja sebelum masuk ke dict hasil. **Tidak ada key/logika lama yang diubah** — perubahan murni penambahan 3 baris.
- `_fallback_market_data()`: ditambah `"ma20": None, "ma50": None, "ma200": None` untuk konsistensi struktur saat data gagal — sebelumnya dict fallback tidak punya key ini sama sekali.
- Dibuktikan lewat `tests/test_info_coin.py::TestMarketSignalMovingAverages`: (a) key baru ada dan nilainya identik dengan `engine.market.features.moving_average()` dihitung independen atas fixture harga yang sama, (b) seluruh 22 key lama (`symbol`, `price`, `trend`, `rsi`, `support`, `resistance`, `fear_greed`, `dominance`, `trend_4h`, `trend_1d`, `trend_alignment`, `cycle_phase`, `funding_status`, `whale_activity`, `stablecoin_flow`, `open_interest_level`, `liquidation_risk`, `market_phase_prediction`, `bull_probability`, `market_risk_score`, `trade_setup`, `data_coverage`, `timestamp`) tetap ada dengan nilai yang sama seperti sebelum perubahan.

### 2. `engine/market/coin_info.py` — baru, tokenomics per-coin

- `get_tokenomics(symbol)`: satu panggilan batched ke CoinGecko `coins/markets?ids=<21 coin_id>&vs_currency=usd` (endpoint gratis, tanpa API key wajib — sama persis dengan yang dipakai `dynamic_universe.py` untuk keperluan lain) untuk **semua** coin watchlist sekaligus, cache TTL 1 jam (`TOKENOMICS_CACHE_SEC`, override via env). Mengembalikan `market_cap`, `fully_diluted_valuation`, `circulating_supply`, `total_supply`, `max_supply`, `market_cap_rank` per coin.
- Pola *fail-open-but-honest* sama seperti `engine/market/institutional_data.py`: gagal fetch → `status: "unavailable"` + `message` — **tidak pernah** angka default/palsu. Kalau fetch baru gagal tapi masih ada cache lama, cache lama tetap dipakai (lebih baik data agak basi daripada "unavailable" tiap kali rate-limited sesaat) — bukan silent stale tanpa keterangan, karena caller (Info Coin) tetap menampilkan angka apa adanya (bukan disamarkan sebagai "live").
- `resolve_coin_id()` (`engine/market/coin_id_resolver.py`, sudah ada) dipakai untuk mapping symbol→CoinGecko ID.
- `reset_cache_for_tests()` disediakan untuk isolasi test.

### 3. `engine/market/global_market_cache.py` — status eksplisit ok/failed

- `_fetch_fear_greed()` dan `_fetch_btc_dominance()`: sekarang mengembalikan tuple `(value, status)` alih-alih hanya `value`. Nilai default `50.0` saat gagal **tidak berubah** (kompatibilitas konsumen lama), tapi sekarang disertai `status="failed"`.
- `get_global_market_data()`: dict hasil ditambah `fear_greed_status` dan `btc_dominance_status` (`"ok"`/`"failed"`) — **murni aditif**. Dikonfirmasi tidak ada konsumen lain (`market_context_engine.py`, `market_analyzer.py`, `market_snapshot_engine.py`, 3 lokasi di `telegram_bot.py`, dan 4 test file yang monkeypatch fungsi ini) yang terpengaruh — semuanya hanya membaca `fear_greed`/`btc_dominance`, tidak pernah membaca seluruh dict secara strict-equal.

### 4. `interfaces/telegram_bot.py` — menu, formatter, disclaimer

- `_market_submenu_keyboard()`: tambah baris tombol `ℹ️ Info Coin`.
- `menu_button_handler()`: tombol `ℹ️ Info Coin` → `_build_coin_selector("info", MAJOR_COINS)` (pola yang sama persis dengan `🔍 Analisis Coin` yang sudah ada).
- `coin_selector_callback()`: tambah cabang `elif prefix == "info":` → panggil `_format_info_coin_message(symbol)`.
- `_format_info_coin_message(symbol)` (baru): fungsi inti, membangun pesan 4 seksi. **Hanya** memanggil `get_market_snapshot()`, `get_sr_levels()`, `get_tokenomics()`, `get_macro_data()`, `get_global_market_data()` — semua fungsi getter read-only.
- `_info_coin_nearest_levels()` (baru): pilih S/R dari `get_sr_levels()` (cluster 1D breakout_detector) bila tersedia — level terdekat dari harga di tiap sisi; fallback ke `support`/`resistance` naive (min/max 20 candle) dari snapshot dengan tanda `(est.)` bila cluster tidak tersedia.
- `_info_coin_fmt_price()` / `_info_coin_fmt_supply()` (baru): formatter angka lokal, meniru pola presisi-adaptif yang sudah dipakai `spot_command` (penting untuk coin sub-cent seperti PEPE/BONE/FARTCOIN/ZEREBRO di watchlist).
- Deteksi **"data terbatas"**: trend `"SIDEWAYS"` ditandai `(data terbatas)` hanya ketika terdeteksi sebagai fallback data-kurang (baik pasangan MA50/MA200 maupun MA20/MA50 sama-sama tidak tersedia) — dibedakan dari sideways sungguhan (MA lengkap, harga memang di antara MA) yang **tidak** ditandai. Ini murni logika baca (`ma20`/`ma50`/`ma200` yang baru diekspos), tidak mengubah kalkulasi trend produksi sama sekali.
- `check_whale_command()`: tambah satu baris disclaimer — *"Kolom Pressure berbasis proksi transaksi besar BTC (market-wide), bukan data per-coin."* Logika perhitungan **tidak diubah** sama sekali.

## Contoh output pesan

### Coin sehat (semua sumber berhasil)

```
ℹ️ INFO COIN — BTC
━ 📈 TEKNIKAL
Harga: $65,000.12 (24h: +2.50% | 1h: +0.30%)
Tren: BULLISH (4H: BULLISH | 1D: BULLISH | Align: STRONG_BULLISH)
RSI-14: 61.2
SMA20/50/200: $64,000.00 / $62,000.00 / $58,000.00
Support: $63,000.00 (est.) | Resistance: $67,000.00 (est.)
Volume 24h: $1.23B
━ 🪙 TOKENOMICS
MCap: $1280.00B (rank #1) | FDV: $1365.00B
Supply: 19.70M beredar / 21.00M total / 21.00M max
━ ⛓️ ON-CHAIN
Whale (market-wide): MEDIUM ⚠️ proxy transaksi besar BTC — bukan spesifik BTC
Netflow & aktivitas jaringan: belum tersedia
━ 🌍 MAKRO & SENTIMEN
Fed Funds Rate: 5.33% (FRED, per 2026-07-01)
BTC Dominance: 54.30% | Fear & Greed: 62 (Greed)
🕒 Market Snapshot : —
```

*(Catatan kosmetik kecil, bukan bug: `MCap: $1280.00B` — formatter `_brief_fmt_vol` yang dipakai ulang dari kode lama hanya punya unit sampai B (miliar), belum ada unit T (triliun); untuk BTC/ETH angka market cap trilliun tetap tampil benar secara numerik, hanya kurang ringkas. Tidak diperbaiki di paket ini karena `_brief_fmt_vol` dipakai bersama oleh fitur lain — mengubahnya di luar scope "display-only, tanpa ubah fungsi lama".)*

### Coin dengan data gagal fetch (tokenomics, FRED, dominance, Fear&Greed semua gagal)

```
ℹ️ INFO COIN — BTC
━ 📈 TEKNIKAL
Harga: $65,000.12 (24h: +2.50% | 1h: +0.30%)
Tren: BULLISH (4H: BULLISH | 1D: BULLISH | Align: STRONG_BULLISH)
RSI-14: 61.2
SMA20/50/200: $64,000.00 / $62,000.00 / $58,000.00
Support: $63,000.00 (est.) | Resistance: $67,000.00 (est.)
Volume 24h: $1.23B
━ 🪙 TOKENOMICS
Tokenomics: tidak tersedia saat ini.
━ ⛓️ ON-CHAIN
Whale (market-wide): MEDIUM ⚠️ proxy transaksi besar BTC — bukan spesifik BTC
Netflow & aktivitas jaringan: belum tersedia
━ 🌍 MAKRO & SENTIMEN
Fed Funds Rate: tidak tersedia (FRED_API_KEY belum dikonfigurasi atau fetch gagal)
BTC Dominance: 50.00% (fetch gagal, nilai default) | Fear & Greed: 50 (Neutral) (fetch gagal, nilai default)
🕒 Market Snapshot : —
```

Perhatikan: nilai default `50` untuk Dominance/Fear&Greed **selalu** disertai `(fetch gagal, nilai default)` — tidak pernah tampil seolah data asli. Teknikal (dari snapshot lokal, bukan fetch langsung saat render) tetap tampil karena datanya memang tersedia di kedua skenario ini.

## Hasil test

`tests/test_info_coin.py` — 19 test baru, dikelompokkan sesuai spesifikasi tugas:

| Kelompok | Jumlah | Yang diverifikasi |
|---|---:|---|
| `TestMarketSignalMovingAverages` | 3 | ma20/50/200 baru ada & sesuai `features.moving_average()`; 22 key lama + nilainya tidak berubah; `_fallback_market_data` punya key ma baru sebagai `None` |
| `TestInfoCoinDoesNotTouchSignalPipeline` | 1 | `process_signal`, `record_signal`, `ngov.queue_alert`, `collect_shadow_signals` di-mock — dipastikan **nol** panggilan saat render Info Coin |
| `TestGetTokenomics` | 5 | fetch gagal → `unavailable` (bukan angka palsu); fetch sukses → field lengkap; cache TTL dihormati (1 HTTP call untuk 2 panggilan dalam window); refetch setelah TTL lewat; symbol tak ada di response → `unavailable` |
| `TestFormatInfoCoinMessage` | 7 | fixture sehat → 4 seksi terisi tanpa "tidak tersedia"; fixture gagal → "tidak tersedia" + tag `(fetch gagal, nilai default)` muncul tepat 2×; coin tak dikenal → error rapi; coin hilang dari snapshot → error rapi; SIDEWAYS dari data kurang → ditandai `(data terbatas)`; SIDEWAYS sungguhan (MA lengkap) → **tidak** ditandai |
| `TestInfoCoinTelegramWiring` | 4 | tombol menu membangun selector dengan `callback_data="info_<COIN>"`; tombol ada di submenu Market; callback `info_BTC` memanggil `_format_info_coin_message("BTC")` lalu reply hasilnya; callback dengan error memberi balasan error tanpa crash |
| **Total** | **19** | |

```
$ venv/bin/python -m pytest tests/test_info_coin.py -v
19 passed in 9.22s
```

Full regresi (sebelum dan sesudah merge, identik):
```
$ venv/bin/python -m pytest tests/ test_telegram_authorization.py test_dashboard_*.py -q
317 passed, 3 warnings, 74 subtests passed in ~33s
```
317 = 298 (baseline sebelum paket ini) + 19 test baru. Tidak ada regresi.

## Konfirmasi eksplisit: jalur sinyal/shadow tidak tersentuh

Tiga lapis bukti, bukan sekadar klaim:

1. **Desain kode**: `_format_info_coin_message()` hanya memanggil `get_market_snapshot()`, `get_sr_levels()`, `get_tokenomics()`, `get_macro_data()`, `get_global_market_data()` — seluruhnya fungsi *read* murni terhadap cache/snapshot yang sudah ada, tanpa efek samping (tidak menulis ke tracker, tidak mengantre alert).
2. **Test spy** (`TestInfoCoinDoesNotTouchSignalPipeline::test_forbidden_functions_never_called`): `process_signal`, `record_signal`, `ngov.queue_alert`, `collect_shadow_signals` di-*mock* sebelum memanggil `_format_info_coin_message("BTC")`, lalu diverifikasi `assert_not_called()` untuk keempatnya — bukan asumsi, tapi bukti dijalankan.
3. **Cakupan diff**: `git diff --stat` merge (`5613f95..453bbca`) mengonfirmasi hanya 5 file berubah (`coin_info.py` baru, `global_market_cache.py`, `market_analyzer.py`, `telegram_bot.py`, `test_info_coin.py`) — tidak ada file di `engine/shadow/`, `engine/trading/signal_tracker.py`, `engine/signal_engine.py`, `engine/alerts/notification_governor.py`, atau checker/alert job manapun yang tersentuh.

Evaluasi shadow E3 (berjalan hingga sekitar 1 September 2026) **tidak terpengaruh** oleh perubahan ini.

## Status deploy

| Tahap | Hasil |
|---|---|
| Commit fitur | `e7eb6ac` di branch `feat/info-coin-menu` |
| Full test pra-merge | 317 passed |
| Merge ke `main` | `453bbca` (non-fast-forward), scope dikonfirmasi tepat 5 file |
| Full test pasca-merge | 317 passed (identik) |
| Push | `5613f95..453bbca main -> main`, berhasil |
| Cleanup branch | `feat/info-coin-menu` dihapus lokal |

**Restart service**: belum dilakukan — sesuai instruksi tugas, ini langkah manual yang disengaja diserahkan ke user (`sudo systemctl restart aliza-telegram.service`). Sampai restart dilakukan, bot yang berjalan di produksi masih menjalankan kode sebelum perubahan ini; menu ℹ️ Info Coin baru akan muncul setelah restart.

Tidak ada secret yang ditulis atau ditampilkan di laporan ini.
