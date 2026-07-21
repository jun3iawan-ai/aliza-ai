# 03 — Logika Sinyal

> **Status: SUPERSEDED.** Snapshot pada 2026-07-21. Kondisi sistem terkini ada di `docs/README.md` dan report Fase 1–4 (`docs/reports/` — lihat Bagian 3). Jangan jadikan dokumen ini sebagai acuan status aktif.

## Kesimpulan utama

Mesin sinyal inti bersifat rule-based. Label “AI” sebagian besar merujuk pada heuristik dan pada LLM `gpt-4o-mini` yang menulis laporan Telegram; tidak ada model ML trading yang dilatih dari data harga. Sistem menghasilkan rekomendasi, bukan order.

Ada beberapa jalur sinyal yang tidak sepenuhnya konsisten:

1. setup teknikal deterministik dari `TradingBrain`;
2. sinyal spot deterministik;
3. laporan spot/futures buatan LLM yang kemudian diedit mekanis;
4. alert BTC, support/resistance, RSI, breakout, volume, funding, whale, makro dan berita;
5. endpoint portfolio manual yang hanya mencatat posisi lokal.

## Data dan indikator dasar

### Harga dan candle

`engine/market/market_analyzer.py:market_signal()` mengambil kline Binance `4h` dan `1d`, limit 100. Seri utama dipilih berurutan: `4h` jika minimal 20 data, lalu `1d` jika minimal 20, lalu CoinGecko chart 90 hari. Seluruh analisis dibatalkan bila seri akhir kurang dari 15 harga.

Masalah penting: fungsi menambahkan ticker harga terbaru ke daftar close meskipun respons kline Binance sudah mencakup candle aktif. Ini dapat menduplikasi harga candle belum tutup dan membuat sinyal berubah intrabar.

### Moving average dan tren

Di `market_signal()`:

- `MA20` = rata-rata maksimal 20 close terakhir.
- `MA50` = rata-rata maksimal 50 close terakhir.
- `MA200` = rata-rata maksimal 200 close terakhir; dengan limit 100, MA200 sebenarnya tidak pernah memiliki 200 observasi.
- Tren `BULLISH` bila `price > MA50 > MA200`; fallback untuk seri pendek adalah `price > MA20 > MA50`.
- Tren `BEARISH` bila urutan terbalik; selain itu `SIDEWAYS`.

`engine/market/multi_timeframe_analyzer.py:analyze_multi_timeframe()` memakai:

- `4h`: bullish bila harga terakhir `> MA10 > MA30`, bearish bila `< MA10 < MA30`.
- `1d`: bullish bila harga terakhir `> MA20 > MA50`, bearish bila kebalikannya.
- Alignment `STRONG_BULLISH`/`STRONG_BEARISH` bila dua timeframe searah; `PARTIAL` bila satu directional dan satu sideways; `MIXED` bila berlawanan; `UNKNOWN` bila data kurang.

Jika data satu timeframe kurang, `market_signal()` mengisi data `4h`/`1d` yang hilang dengan seri utama yang sama. Karena itu hasil bisa tampak multi-timeframe padahal berasal dari satu seri.

### RSI

`engine/market/market_analyzer.py:_calculate_rsi()` menggunakan RSI Wilder periode 14. Prioritas input: close `4h`, lalu `1d`, lalu seri fallback. Batas yang digunakan oleh komponen berbeda:

- `TradingBrain`: oversold `<30`, overbought `>70`; long ditolak jika RSI `>=70`, short ditolak jika RSI `<=30`.
- Spot: exit bila RSI `>=70`; pullback buy bila RSI `<50`; accumulation bila `45..65`.
- Alert ekstrem Telegram: RSI `<30` atau `>75`.
- Liquidation cascade: long-liquidation bila RSI `<=35`; short-squeeze bila RSI `>=65`.
- BTC take-profit: RSI `>=75`; reversal candidate: RSI `<=40`.

### Support/resistance, volume dan struktur

- `market_signal()` memakai minimum/maksimum 20 close terakhir untuk support/resistance, bukan low/high candle.
- `engine/market/breakout_detector.py` membuat cluster level dari high/low harian 90 candle, toleransi cluster 1,5%, mengambil sampai tiga level ekstrem. Breakout atas memerlukan harga `> resistance × 1,005`, breakdown `< support × 0,995`, dan diabaikan bila jarak sudah lebih dari 2%. Cooldown aktual 8 jam.
- `engine/market/volume_spike_detector.py` membandingkan volume quote 24 jam dengan rata-rata volume quote 14 candle harian; spike bila rasio `>2×`. Job Telegram kemudian mensyaratkan lagi `>=4×` dan cooldown 8 jam, sehingga ambang implementasi tidak tunggal.
- Tidak ditemukan MACD, Bollinger Bands atau ATR pada jalur sinyal inti. Volatilitas direpresentasikan terutama oleh perubahan harga, range/support-resistance dan label rezim.

## Strategi inti: `TradingBrain`

Lokasi: `engine/brain/trading_brain.py:TradingBrain.analyze()`.

### Filter awal

- Alignment `MIXED`, `UNKNOWN` atau kosong langsung menghasilkan `NO SETUP`.
- Long hanya diizinkan pada `STRONG_BULLISH`, `BULLISH`, atau `PARTIAL`.
- Short hanya diizinkan pada `STRONG_BEARISH`, `BEARISH`, atau `PARTIAL`.
- Semua harga/level harus positif.
- Jarak minimum entry–SL adalah 0,5%.
- TP akhirnya dibatasi maksimum 8% dari entry ke arah target.
- Setup harus diizinkan oleh `engine/strategy/strategy_regime_map.py:is_strategy_allowed()`.

### 1. Oversold Bounce — LONG

Kondisi pembentukan awal: `RSI < 30`.

- Setup: `OVERSOLD BOUNCE`.
- Entry: harga saat ini.
- SL: `entry × 0,985`, yaitu 1,5% di bawah entry.
- TP1: resistance.
- TP2: `resistance × 1,02`.
- Harus lolos alignment arah long, filter RSI long, jarak minimum stop dan regime filter.
- Strategy-regime map hanya mengizinkannya dalam rezim `RANGE`.

Urutan prioritas membuat kondisi RSI ini mengalahkan kondisi tren bullish/bearish berikutnya.

### 2. Overbought Rejection — SHORT

Kondisi pembentukan awal: `RSI > 70`.

- Setup: `OVERBOUGHT REJECTION`.
- Entry: harga saat ini.
- SL: `resistance × 1,01`.
- TP1: support.
- TP2: `support × 0,98`.
- Short ditolak bila harga sudah di bawah `support × 1,02`.
- Hanya diizinkan dalam rezim `RANGE` atau `DOWNTREND`.

### 3. Pullback Long

Kondisi pembentukan awal: tren `BULLISH` dan dua setup RSI di atas tidak aktif.

- Setup: `PULLBACK LONG`.
- Entry: harga saat ini.
- SL: `support × 0,99`.
- TP1: resistance.
- TP2: `resistance × 1,02`.
- Ditolak bila harga `> resistance × 0,98`, yaitu terlalu dekat resistance.
- Hanya diizinkan dalam rezim `TREND`.

### 4. Pullback Short

Kondisi pembentukan awal: tren `BEARISH` dan setup RSI tidak aktif.

- Setup: `PULLBACK SHORT`.
- Entry: harga saat ini.
- SL: `resistance × 1,01`.
- TP1: support.
- TP2: `support × 0,98`.
- Ditolak bila harga `< support × 1,02`.
- Diizinkan dalam rezim `TREND` dan `DOWNTREND`.

### RR dan confidence

`risk_reward = abs(TP1-entry) / abs(entry-SL)`. `TradingBrain._calculate_confidence()` mulai dari 50:

- RR `>=3`: +25; RR `>=2`: +15; RR `>=1,5`: +5.
- RSI dalam `30..70`: +10.
- Nilai dibatasi maksimum 85.
- `engine/learning/confidence_adjuster.py` dapat menambah 5 jika winrate strategi `>65%`, atau mengurangi 10 jika `<40%`.

Kualitas risiko di `TradingBrain._risk_quality()`: `EXCELLENT` untuk RR `>=3`, `GOOD` `>=2`, `MEDIUM` `>=1,5`, selain itu `POOR`.

### Filter regime

`engine/strategy/strategy_regime_map.py` memetakan:

- `TREND`: pullback long/short, momentum long/short, breakout long.
- `RANGE`: oversold bounce, overbought rejection.
- `DOWNTREND`: pullback short, overbought rejection.
- `VOLATILE`: tidak ada strategi.

`MOMENTUM LONG`, `MOMENTUM SHORT`, dan `BREAKOUT LONG` ada di peta tetapi tidak pernah dibentuk `TradingBrain.analyze()`. Lebih kritis, `TradingBrain` memperoleh rezim dengan membaca `get_market_snapshot()` saat analisis coin sedang membangun snapshot baru; pada siklus berikutnya itu dapat memakai snapshot siklus sebelumnya, dan pada startup dapat `UNKNOWN`/tanpa snapshot.

## Penyaringan dan pemilihan sinyal inti

Lokasi: `engine/trading/signal_engine.py:scan_for_signals()`.

- `engine/macro/macro_checker.py` memblokir bila event berdampak tinggi berada dalam 4 jam. Kegagalan kalender bersifat fail-open.
- Kandidat wajib `setup != "NO SETUP"`, RR `>=3`, dan confidence `>=70`.
- Kandidat diurutkan berdasarkan RR dan hanya satu kandidat terbaik dikembalikan.
- Position size ditambahkan sebagai rekomendasi.
- Dedup scanner 15 menit memakai key signal dan state JSON.

Gateway `engine/signal_engine.py:process_signal()` memvalidasi level dengan `engine/risk_manager.py:validate_proposed_trade()`, menerapkan macro hold/block, dedup, enrichment dan dispatch. Akan tetapi `interfaces/telegram_bot.py:snapshot_job()` memanggil `record_signal(sig)` sebelum `process_signal(sig)`. Dengan urutan itu, sinyal yang kemudian ditolak risiko/makro/dedup atau gagal dikirim tetap masuk statistik.

## Opportunity ranking dan auto alert

`engine/trading/opportunity_scanner.py:get_top_opportunities()` mensyaratkan snapshot maksimal 90 detik dan RR trade minimal 1,3. `engine/brain/opportunity_ranker.py:rank_opportunities()` awalnya membuat skor besar dari `(RR × 40) × (confidence × 0,4)` ditambah bonus/penalti. Sesudah itu, `engine/brain/signal_quality_engine.py:calculate_signal_quality()` menimpa field `score` dengan skor kualitas yang dibatasi 0–100.

`engine/alerts/auto_alert_engine.py` mensyaratkan score minimal 160, RR minimal 2,5 dan confidence minimal 65. Karena score yang dibaca sudah maksimum 100, jalur auto alert tidak mungkin lolos. Ini defect deterministik, bukan hanya kemungkinan.

## Sinyal spot deterministik

Lokasi: `engine/spot/spot_engine.py:analyze_spot_opportunity()`.

- Input tidak valid → `WAIT`.
- RSI `>=70` → `EXIT`.
- Tren terisi tetapi bukan `BULLISH`/`STRONG_BULLISH` → `EXIT`; artinya `SIDEWAYS` juga dianggap keluar.
- Pada tren bullish, RSI `<50` dan harga `<= support × 1,02` → `BUY`, alasan `PULLBACK`, confidence 80.
- Pada tren bullish, RSI `45..65` dan global regime `TREND` → `BUY`, alasan `ACCUMULATION`, confidence 70.
- Selain itu → `WAIT`.

Fungsi ini tidak menghitung SL/TP dan tidak menjual aset; hasil hanya memperkaya snapshot/response Telegram.

## Analisis spot dan futures berbasis LLM

Lokasi: `interfaces/telegram_bot.py:_generate_spot_analysis()`, `_generate_futures_analysis()`, `_call_llm_async()`, dan `_reorder_section_by_rr()`.

- CrewAI/OpenAI `gpt-4o-mini` diminta menulis analisis untuk BTC, ETH, BNB, SOL dan XRP.
- Action awal dipandu score market/fear-and-greed dalam prompt, tetapi level final tetap merupakan keluaran generatif.
- Formatter memaksa jarak SL menjadi 5–8%; jika di luar rentang, SL ditulis ulang menjadi tepat 6% dari entry.
- Jika RR target pertama `<2`, target pertama ditulis ulang menjadi tepat 2R.
- Persentase dan invalidation ikut dihitung ulang.
- Untuk futures, prompt membatasi leverage maksimum 5x dan merekomendasikan 2–3x; funding tiga hari juga bersifat estimasi teks.

Konsekuensi: target dapat tidak lagi berhubungan dengan support/resistance/liquidity awal, dan sinyal LLM tidak melewati `validate_proposed_trade()`. `_parse_and_record_signals()` mengekstrak LONG/SHORT/SPOT dari teks dengan regex dan mencatatnya ke `signal_tracking`, sehingga output generatif memengaruhi winrate tercatat.

## BTC Smart Alert

Lokasi utama: `engine/alerts/btc_smart_alert.py:analyze_btc_signal()` dan `should_alert_btc()`.

Sinyal prioritas:

- RSI `>=75` → `TAKE PROFIT`, confidence 80.
- Tren bearish + rezim `DOWNTREND`/`VOLATILE` + (whale selling atau RSI `<40`) → `CRASH WARNING`, confidence 90, anjuran keluar penuh.

Scoring entry:

- Breakout valid: harga di atas `resistance × 1,01`, wajib volume spike dan strong close, kualitas breakout minimal 2; base +25.
- Trend continuation: tren kuat + struktur bullish + healthy pullback; base +20.
- Reversal: RSI `<=40`, dekat support, tren bukan bearish; base +18.
- Konfirmasi volume, strong close, support/structure, continuation masing-masing +5.
- Penalti: dekat resistance −10, mid-zone −5, candle >4% −8, konflik −10, whale selling −10, mismatch regime −5, breakout sideways −10, continuation sideways −8, volatile −5.
- Threshold bergantung `TRADING_MODE`: scalping strong/buy 28/18; intraday 30/20; swing 32/22; weak minimal 10.

`should_alert_btc()` hanya mengizinkan `STRONG BUY` dan `CRASH WARNING`; `TAKE PROFIT` tidak termasuk dispatch otomatis walau dianalisis. Lebih jauh, snapshot yang diberikan dari `market_analyzer.py` berisi close, bukan array candle OHLCV yang diharapkan helper smart alert. Dengan kurang dari tiga candle, healthy-pullback cenderung fallback dan volume/strong-close tidak bisa tervalidasi. Banyak cabang scoring BTC karena itu praktis lumpuh.

## Alert tambahan

- Near support/resistance: job `interfaces/telegram_bot.py:near_support_checker()` dan `near_resistance_checker()` memberi alert saat jarak level `<=1%`; interval 5 menit, cooldown 4 jam.
- RSI ekstrem: `rsi_extreme_checker()` untuk `<30` atau `>75`. Job yang sama didaftarkan dua kali, interval 5 dan 10 menit, dengan first-run berbeda.
- Big move: `big_move_checker()` memicu pada perubahan absolut `>=3%`; memakai `price_change_1h` bila ada, jika tidak fallback data 24h meski pesan berlabel gerak 1h.
- Breakout: `breakout_detector.py:check_breakout()` sesuai aturan cluster 90D di atas; job 5 menit.
- Volume: `volume_spike_detector.py:detect_volume_spike()` >2×, tetapi dispatch Telegram >=4×.
- Funding: `funding_rate_monitor.py:check_extreme_funding()` memicu `abs(rate)>0,001` (0,1%), cooldown 4 jam; watchlist futures 19 coin.
- Heuristik lama `crypto_intelligence.py:analyze_funding()` memakai batas `>0,05`/`<-0,05` dalam unit desimal, yaitu ±5%, hampir mustahil dan tidak konsisten dengan monitor 0,1%.
- Liquidation: `liquidation_monitor.py:analyze_open_interest()` mengklasifikasikan jumlah OI BTC coin `>80.000`, `>120.000`, `>200.000`, tanpa normalisasi USD; cascade detector memakai tren/RSI/risk high.
- Whale: radar Blockchair menghitung transaksi BTC di atas 3.000 BTC; count >=2/5/10 menjadi medium/high/extreme. Ini hanya proksi kasar.
- Stablecoin: total sirkulasi di atas ambang diberi label `HIGH INFLOW`, padahal bukan perubahan arus. `market_ai_predictor.py:bull_probability()` mencari literal `HIGH`, sehingga bonus 20 poin stablecoin tidak pernah aktif dengan label tersebut.

## Exit, take profit, stop loss dan trailing

- Setup deterministik menggunakan TP1/TP2 dan SL yang dirinci di atas. TP1 dibatasi maksimal 8%, tetapi SL tidak selalu dibatasi ke risiko maksimum 2% sampai gateway.
- Laporan LLM menyebut take profit bertahap (umumnya 50% di target pertama), tetapi tidak ada mesin partial close.
- `signal_tracker.py:check_open_signals()` hanya menilai apakah harga titik saat polling melewati TP atau SL; tidak memasang order dan tidak membaca high/low intrabar.
- Tidak ditemukan trailing stop.
- Tidak ditemukan break-even stop otomatis.
- Tidak ada biaya, slippage, spread atau funding dalam perhitungan outcome.

## Perbedaan spot dan futures

| Aspek | Spot | Futures |
|---|---|---|
| Engine deterministik | `spot_engine.py`, hanya BUY/WAIT/EXIT | Setup `PULLBACK SHORT`/`OVERBOUGHT REJECTION` tersedia di TradingBrain |
| Short | Tidak | Rekomendasi teks/logika tersedia |
| Leverage | Tidak | Hanya prompt rekomendasi 2–3x, maksimum 5x |
| Funding/OI | Konteks saja | Dimonitor lewat Binance Futures REST |
| Order | Tidak ada | Tidak ada |
| Protective order | Tidak ada | Tidak ada |
| Position model | Rekomendasi fixed-fractional | Tidak disesuaikan margin/leverage/liquidation secara nyata |

Jadi futures “ada” sebagai analisis/notifikasi, tetapi bukan trading futures yang terintegrasi exchange.

## ML/AI

- Tidak ditemukan file model trading (`.pt`, `.pkl` model prediksi, `.onnx`, dsb.), pipeline training, dataset training, evaluasi out-of-sample atau tanggal pelatihan.
- `market_ai_predictor.py`, `prediction/*`, `altseason_model.py` dan kelas bernama AI adalah fungsi skor/aturan deterministik.
- `knowledge/vector_store/index.faiss` dan `index.pkl` adalah indeks RAG dokumen, terakhir termodifikasi 9 Maret 2026; bukan model arah harga.
- LLM `gpt-4o-mini` digunakan runtime untuk percakapan dan laporan pasar. `config/agent.yaml` menyebut `gpt-4o`, tetapi `core/agent.py` memakai `gpt-4o-mini`.
- Waktu “terakhir dilatih”: **TIDAK PASTI/tidak berlaku**, karena repo tidak berisi proses pelatihan model trading.

## Filter tambahan

- Tren dan alignment MTF seperti di atas.
- Market regime (`TREND`, `RANGE`, `DOWNTREND`, `VOLATILE`).
- Macro high impact 4 jam; 1 jam dipakai sebagai hold pada gateway.
- Volatilitas/regime dapat memblokir seluruh strategi.
- Blacklist Telegram: `WLFI`, `SKY`, `PIXEL`; saat ini ketiganya tidak ada di universe 21 coin.
- Tidak ditemukan filter jam trading untuk setup deterministik; jam hanya menentukan jadwal laporan.
- Dedup 15 menit untuk sinyal inti; cooldown per jenis alert umumnya 4–8 jam.
- Batas open position lokal maksimum tiga.
- Dynamic universe dinonaktifkan secara efektif karena `get_tradable_coins()` mengembalikan daftar tetap.

## Bagian yang tidak pasti

- `TIDAK PASTI`: output LLM persis untuk setiap eksekusi; sifatnya generatif dan bergantung respons API.
- `TIDAK PASTI`: apakah semua cabang lama (`aliza_engine.py`, `strategy_engine.py`, `prediction/*`) pernah dipanggil dari luar repo. Tidak ditemukan caller aktif internal untuk beberapa modul tersebut.
- `TIDAK PASTI`: hasil intrabar aktual suatu signal; tracker hanya melihat harga saat polling.
