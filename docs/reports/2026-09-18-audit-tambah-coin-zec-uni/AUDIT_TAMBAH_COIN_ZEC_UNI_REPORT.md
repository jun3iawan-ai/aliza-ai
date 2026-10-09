# Audit Read-Only: Kelayakan Menambah ZEC dan UNI ke Watchlist

Tanggal audit: 18 September 2026  
Branch saat audit: `main` pada `7f5b5de`  
Ruang lingkup: source, konfigurasi, endpoint publik, dan fungsi baca proyek. Tidak ada kode, `CORE_COINS`, state aplikasi, database, atau konfigurasi service yang diubah.

## 1. Ketersediaan data Binance

### Endpoint yang benar-benar dipakai proyek

Jalur teknikal/snapshot memakai spot Binance, bukan klines futures:

```python
# engine/market/market_analyzer.py:131-175
BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"

def _get_binance_klines(symbol_usdt, interval, limit=100):
    ...
    r = requests.get(
        BINANCE_KLINES_URL,
        params={"symbol": sym, "interval": interval, "limit": min(limit, 1000)},
        ...,
    )
```

`market_signal()` memakai kline spot 4h dan 1d (`engine/market/market_analyzer.py:312-315`). Shadow E3 juga memakai endpoint spot yang sama, dengan pair dibentuk generik sebagai `f"{coin}USDT"` (`engine/shadow/e3_shadow.py:25,51-68`). Outcome tracker membaca kline spot 5m dengan pair generik yang sama (`engine/trading/signal_tracker.py:316-351`).

### Pemeriksaan live endpoint Binance

Pemeriksaan dilakukan langsung terhadap endpoint public Binance pada waktu audit. Output mentah untuk kline spot:

```text
ZECUSDT 5m=rows=2
ZECUSDT 4h=rows=2
ZECUSDT 1d=rows=2
UNIUSDT 5m=rows=2
UNIUSDT 4h=rows=2
UNIUSDT 1d=rows=2
```

Pemeriksaan spot/futures 4h dibandingkan dengan empat pair pembanding yang diperlakukan non-Binance oleh snapshot:

```text
ZECUSDT spot=rows=2
ZECUSDT futures=rows=2
UNIUSDT spot=rows=2
UNIUSDT futures=rows=2
BONEUSDT spot=code=-1121 msg=Invalid symbol.
BONEUSDT futures=code=-1121 msg=Invalid symbol.
FARTCOINUSDT spot=code=-1121 msg=Invalid symbol.
FARTCOINUSDT futures=rows=2
HYPEUSDT spot=code=-1121 msg=Invalid symbol.
HYPEUSDT futures=rows=2
ZEREBROUSDT spot=code=-1121 msg=Invalid symbol.
ZEREBROUSDT futures=rows=2
```

Jadi ZEC dan UNI tidak berada dalam kategori masalah yang relevan bagi pipeline saat ini: **spot kline tidak tersedia**. Tiga pembanding (`FARTCOIN`, `HYPE`, `ZEREBRO`) kini mempunyai futures klines, tetapi itu tidak menyelesaikan masalah pipeline karena pipeline teknikal/shadow/outcome memakai spot klines. `BONE` tidak tersedia pada dua endpoint yang diuji.

Konfigurasi snapshot secara eksplisit memperlakukan keempatnya sebagai non-Binance dan prefetch harga CoinGecko (`engine/market/market_snapshot_engine.py:358-380`):

```python
NON_BINANCE = ["BONE", "FARTCOIN", "HYPE", "ZEREBRO"]
cg_ids = [resolve_coin_id(s) for s in NON_BINANCE]
...
set_cg_price_cache(_price_map)
```

Tidak ada alasan untuk memasukkan ZEC atau UNI ke list tersebut: spot pair keduanya `TRADING` dan kline-nya tersedia.

### Pemeriksaan dengan fungsi proyek sendiri

Fungsi internal pembaca klines dijalankan read-only terhadap data live:

```text
ZEC spot_4h_closed= 99
ZEC spot_1d_closed= 99
ZEC shadow_4h_closed= 99
ZEC project_funding= None
UNI spot_4h_closed= 99
UNI spot_1d_closed= 99
UNI shadow_4h_closed= 99
UNI project_funding= None
```

Nilai 99 masuk akal: request limit 100 mencakup satu candle yang masih terbuka lalu `_extract_closed_kline_closes()` hanya menyimpan candle yang telah close (`market_analyzer.py:120-128,169-172`). `project_funding=None` bukan kegagalan endpoint; penyebabnya adalah `SYMBOL_MAP` funding belum memiliki dua coin itu (dibuktikan pada bagian 3).

## 2. Konsumen `CORE_COINS` / `TRADABLE_COINS` / `MAJOR_COINS`

Pencarian lintas source Python menemukan modul berikut. Tidak ada modul lain yang mengimpor `TRADABLE_COINS` secara langsung; ia didefinisikan sebagai salinan `CORE_COINS` di `engine/market/market_universe.py:26`. Sumber tunggal saat ini:

```python
# engine/market/market_universe.py:14-28
CORE_COINS = [ ... 21 symbol ... ]
TRADABLE_COINS = list(CORE_COINS)
MAJOR_COINS = list(CORE_COINS)
```

| Modul | Referensi dan dampak bila list menjadi 23 |
|---|---|
| `engine/market/market_universe.py:98-129` | `get_polling_coins()` dan `get_universe_status()` default ke `CORE_COINS`; ZEC/UNI otomatis masuk polling kecuali `UNIVERSE_EXCLUDE` atau suspended. |
| `engine/market/dynamic_universe.py:14-17,273,276-278` | `get_tradable_coins()` mengembalikan `list(CORE_COINS)`; fallback memakai `MAJOR_COINS`. |
| `engine/market/market_snapshot_engine.py:21-27,79-87,331-429` | snapshot mengambil tradable/fallback major dan mengiterasi setiap symbol (`for symbol in coins` pada :388); dua coin akan ikut snapshot serta coverage validation. |
| `engine/market/market_analyzer.py:14` | mengimpor `MAJOR_COINS`; jalur analisis pair itu sendiri generik (`market_signal(symbol)`). |
| `engine/utils/market_cache.py:9,36-45` | cache multi-coin memilih tradable, fallback ke major, lalu mengiterasi semua symbol. |
| `engine/utils/market_cache_updater.py:2,6-21` | updater mengiterasi `MAJOR_COINS`. |
| `engine/market/coin_info.py:23-24,49-104` | tokenomics batched mengiterasi `MAJOR_COINS` dan membangun request CoinGecko. |
| `interfaces/telegram_bot.py:87,265,673,728,735,745,798,920,956,989,1457` | selector menu `/info`, `/scan`, `/spot`, `/why`, validasi symbol, dan `ALLOWED_COINS` mengikuti major/tradable list. |
| `backtest/run_backtest.py:12,44`; `backtest/run_experiments.py:9,16`; `backtest/robustness.py:11,81` | default backtest/experiment/robustness bertambah dua coin, kecuali dieksklusi lewat `UNIVERSE_EXCLUDE`. |

Radar, prediction, scanner, dan signal tidak mengimpor konstanta list ini secara langsung, tetapi mengonsumsi `snapshot["data"]`; akibatnya keduanya ikut bertambah secara tidak langsung saat snapshot menghasilkan baris ZEC/UNI:

```python
# engine/trading/opportunity_scanner.py:40-50,53-87
snapshot = get_market_snapshot()
...
return snapshot.get("data") or {}
...
for coin, data in market_data_dict.items():
    ...

# engine/trading/signal_engine.py:304-327
# scan mengambil snapshot/current market cache dan membaca snapshot["data"]

# engine/prediction/prediction_engine.py:1-6,21-45
# prediction hanya membaca snapshot; tidak mengubah pipeline.
```

### Asumsi hardcoded “21”

Pencarian `len(...)=21`, `range(21)`, dan validasi/alokasi berbasis 21 tidak menemukan asumsi runtime. Referensi yang ditemukan hanya:

- docstring `Fixed watchlist 21 coin` di `market_universe.py:4`;
- teks UI `Saran Spot — saran swing entry 21 coin` di `interfaces/telegram_bot.py:702`;
- komentar/dokumen test yang menyebut 21 (`tests/test_radar_pro_crash_risk.py:10`).

Artinya tidak ada blocker berupa validasi panjang atau resource allocation hardcoded. Namun teks UI di `telegram_bot.py:702` akan menjadi stale jika daftar berubah menjadi 23.

## 3. Data pendukung per-coin dan precision/notional

### Funding, OI, dan long/short ratio

`engine/market/funding_rate_monitor.py` tidak memakai `CORE_COINS`; ia memiliki `WATCHLIST` dan `SYMBOL_MAP` terpisah (`:32-46`), saat ini memuat 19 coin dan **tidak memuat ZEC maupun UNI**:

```python
WATCHLIST = [
    "BTC", "ETH", "BNB", "SOL", "XRP",
    "ADA", "SUI", "ARB", "JTO", "ETHFI",
    "WLD", "OM", "ASTER", "XPL", "TAO",
    "FARTCOIN", "HYPE", "ZEREBRO", "XAUT",
]
SYMBOL_MAP = { ... }  # tidak ada "ZEC" atau "UNI"
```

Karena itu fungsi per-coin mengembalikan kosong sebelum request bila mapping tidak ada:

```python
# funding_rate_monitor.py:170-178,218-226,284-289
coin = symbol.strip().upper()
sym = SYMBOL_MAP.get(coin)
if not sym:
    return None
```

`get_all_funding_data()` juga hanya mengiterasi `WATCHLIST` (`funding_rate_monitor.py:332-353`), dan section briefing/OI-LS memakai list yang sama (`:381-405`). Jadi menambah dua symbol ke `CORE_COINS` saja tidak akan menampilkan funding/OI untuk mereka.

Endpoint futures-nya sendiri tersedia dan memiliki data aktual:

```text
ZECUSDT premium=ok lastFundingRate=-0.00023452 markPrice=1499.50276937
ZECUSDT oi=ok openInterest=528730.626
ZECUSDT oi_hist=rows=2
ZECUSDT ls=rows=1
UNIUSDT premium=ok lastFundingRate=0.00010000 markPrice=8.52290270
UNIUSDT oi=ok openInterest=23468601
UNIUSDT oi_hist=rows=2
UNIUSDT ls=rows=1
```

Endpoint tersebut persis yang dipakai module: premium index/OI/OI history/global L-S (`funding_rate_monitor.py:25-28,184-212,241-259,293-323`). Jadi ini adalah kekurangan mapping internal, bukan kekurangan sumber Binance.

### CoinGecko / tokenomics / fallback harga

Resolver fallback statis mencantumkan semua 21 symbol kini, tetapi tidak ZEC/UNI (`engine/market/coin_id_resolver.py:12-35`). `resolve_coin_id()` mencoba dynamic map dulu, lalu mapping statis (`:38-54`). Dynamic map bukan jaminan: ia hanya diisi dari `top_dynamic` pada refresh (`dynamic_universe.py:239-264`) dan dapat kosong/fallback.

Akibatnya, jika ZEC/UNI hanya ditambahkan ke `CORE_COINS`, teknikal tetap berjalan dari Binance; tetapi tokenomics `/info` dapat menjadi unavailable dalam kondisi fallback, karena `coin_info._fetch_tokenomics_batch()` mengiterasi `MAJOR_COINS` namun hanya memasukkan symbol yang berhasil `resolve_coin_id()` (`engine/market/coin_info.py:49-60,86-104`). Static fallback perlu entries `ZEC -> zcash` dan `UNI -> uniswap` saat implementasi agar cakupan konsisten.

ZEC/UNI tidak memerlukan daftar `NON_BINANCE` atau prefetch CoinGecko khusus: spot price dan klines tersedia. Static CoinGecko entry dibutuhkan untuk fitur info/fallback, bukan untuk membuat snapshot teknikal utama hidup.

### Whale dan institutional data

Radar whale bukan feed per-asset: `market_radar.get_large_transactions()` mengambil transaksi **Bitcoin** Blockchair (`engine/market/market_radar.py:30-73`), lalu `market_radar()` mengembalikan level global yang diteruskan ke setiap row (`:149-153,227-265`). Begitu pula `institutional_data.py:1-4` mendokumentasikan Bitcoin spot ETF flow, aggregate liquidation, dan BTC netflow. Tidak ada mapping ZEC/UNI yang kurang di subsystem ini karena subsystem tersebut memang bukan data whale/institutional per-coin.

### Precision, minimum notional, dan execution

Tidak ada konfigurasi precision/minimum notional per coin di source. `position_sizer.calculate_position_size()` hanya memakai `entry_price`, `stop_loss`, balance, risk, dan allocation (`engine/position_sizer.py:48-112`); `trade_manager.create_trade()` menyimpan `quantity` yang sudah diberikan tanpa membulatkannya ke exchange filter (`engine/trading/trade_manager.py:81-126`). Ini proyek sinyal/tracker, bukan submit order ke Binance pada jalur yang diaudit.

Exchange filter live tetap ada dan valid:

```text
ZECUSDT spot_filter=status=TRADING tick=0.01000000 step=0.00100000 minNotional=5.00000000
UNIUSDT spot_filter=status=TRADING tick=0.00100000 step=0.01000000 minNotional=5.00000000
ZECUSDT futures_filter=status=TRADING tick=0.01 step=0.001 minQty=0.001 minNotional=5
UNIUSDT futures_filter=status=TRADING tick=0.0010 step=1 minQty=1 minNotional=5
```

Kesimpulan precision: tidak ada entry source yang perlu ditambah untuk kalkulasi TP/SL/sizing saat ini. Jika proyek kelak melakukan order execution nyata, filter exchange di atas harus dipakai pada jalur eksekusi baru, tetapi itu bukan kebutuhan fitur watchlist/sinyal sekarang.

## 4. Dampak ke Shadow E3 dan `signal_tracking`

Penambahan ke `CORE_COINS` mengalir otomatis ke snapshot melalui `get_tradable_coins()` dan `update_market_snapshot()` (bagian 2). Shadow E3 tidak memiliki allow-list tersendiri; ia mengiterasi seluruh `snapshot["data"]`:

```python
# engine/shadow/e3_shadow.py:162-195
for symbol, market_data in (snapshot.get("data") or {}).items():
    total_processed += 1
    rows = _closed_4h_klines(symbol)
    signal = build_shadow_signal(symbol, market_data, rows, counters=counters)
    if signal:
        rows_by_coin.append(signal)
```

`snapshot_job` kemudian selalu menjalankan `_run_shadow_e3(snapshot, ...)` setelah snapshot valid (`interfaces/telegram_bot.py:7674-7776`). Kandidat dicatat ke tracker generic tanpa allow-list coin:

```python
# interfaces/telegram_bot.py:7641-7667
candidates = collect_shadow_signals(snapshot)
...
if record_signal(shadow):
    recorded += 1

# engine/trading/signal_tracker.py:202-285
coin, setup, side, source = _episode_parts(...)
...
INSERT INTO signal_tracking (coin, setup, side, source, ...)
VALUES (?, ?, ?, ?, ...)
```

Outcome evaluation pun menyusun `f"{coin}USDT"` dan meminta kline spot 5m generik (`signal_tracker.py:316-382,422-478`). Karena kline 5m spot ZEC/UNI telah diverifikasi tersedia, keduanya akan ikut jalur `shadow_e3` → `signal_tracking` → outcome evaluation yang sama tanpa perubahan tambahan **setelah** masuk snapshot.

Fakta penting untuk evaluasi yang sedang berjalan: menambahnya memang memperluas populasi observasi shadow mulai saat perubahan diterapkan; tidak ada isolasi otomatis yang akan mengecualikan dua coin baru dari N/current evaluation.

## Kesimpulan

**Kelayakan sumber data: LAYAK.** ZECUSDT dan UNIUSDT tersedia untuk spot 5m/4h/1d, futures 4h, funding, OI, OI history, L/S ratio, serta filter exchange; keduanya berbeda dari kategori pair non-spot-Binance yang memerlukan fallback CoinGecko.

**Kelayakan implementasi “ubah `CORE_COINS` saja”: BELUM LENGKAP.** Sebelum penambahan aktual, dua kekurangan internal perlu ditangani agar cakupan fitur tidak parsial:

1. Tambah ZEC/UNI ke `funding_rate_monitor.WATCHLIST` dan `SYMBOL_MAP`; tanpa ini, funding/OI/L-S untuk keduanya tetap kosong meski endpoint live tersedia.
2. Tambah static CoinGecko fallback `ZEC -> zcash` dan `UNI -> uniswap` ke `coin_id_resolver.COINGECKO_IDS`; tanpa ini, tokenomics `/info` dan fallback CoinGecko tidak deterministik saat dynamic map kosong.

Tidak ada blocker data Binance, hardcoded cardinality runtime, atau precision/TP-SL yang menghalangi. Namun dua mapping di atas adalah prasyarat teknis untuk penambahan yang setara dengan cakupan coin lain, dan perubahan nanti juga akan otomatis memasukkan dua coin ke populasi evaluasi Shadow E3—sesuai alasan keputusan eksekusi ditunda hingga evaluasi promosi selesai.
