# Audit: Menu Informasi Per-Coin & Kesiapan Data 4 Kategori Analisis

Tanggal audit: 21 Agustus 2026
Target yang diaudit: `interfaces/telegram_bot.py` (7680 baris, state produksi terkini — mencakup restrukturisasi menu 5 Agustus 2026) dan modul `engine/` terkait.
Metode: pembacaan kode statis (READ-ONLY) + grep menyeluruh. Tidak ada perubahan kode, instalasi, atau panggilan API eksternal baru yang dilakukan selama audit ini. Sebagian evidensi Bagian 1 memverifikasi ulang klaim di `AUDIT_MENU_TELEGRAM_LENGKAP_REPORT.md` (5 Agustus 2026) dan `TELEGRAM_MENU_RESTRUCTURE_REPORT.md` (5 Agustus 2026) terhadap kode saat ini — dikonfirmasi masih akurat pada 21 Agustus 2026.

## Ringkasan eksekutif

User ingin menu "Informasi": pilih satu coin dari list → tampil info dalam 4 kategori (Teknikal, Fundamental, On-chain, Makro & Sentimen). Dari **13 item** yang diminta untuk diaudit:

- **Siap tampil hari ini tanpa sumber data baru** (format ulang saja): price action/trend, RSI, BTC Dominance, Fear & Greed, suku bunga Fed (FRED) — 5 item. Volume 24h dan level Support/Resistance juga **ADA** di data tapi perlu keputusan kecil (yang mana dipakai / cara format) sebelum tampil.
- **TIDAK ADA sama sekali**, butuh sumber baru: seluruh Fundamental (tokenomics, use case terstruktur, tim/kemitraan terstruktur), Exchange netflow, Aktivitas jaringan on-chain, MACD, EMA — 8 item.
- **Ada tapi cacat/menyesatkan jika ditampilkan apa adanya**: Whale movement (proxy BTC global, bukan per-coin — lihat C.1), Stablecoin flow (bug lama masih ada: menghitung total market cap stablecoin, bukan arus — lihat C.2), FMP kalender ekonomi (key ada tapi flag nonaktif secara default, jatuh ke kalender rule-based).
- Belum ada alur Telegram "pilih coin → info 4 kategori" sama sekali. Yang paling dekat adalah tombol **🔍 Analisis Coin** (selector 21 coin → `/spot <COIN>`), tapi isinya murni sinyal trading teknikal (signal/entry/SL/target/RR), bukan 4 kategori informasi.
- Desain pemisahan aman **memungkinkan**: semua fungsi yang relevan untuk menu Informasi adalah fungsi *read* dari cache/snapshot (`get_market_snapshot()`, `get_global_market_data()`, fungsi `institutional_data.py`/`macro_monitor.py`). Tidak satu pun dari command teknis di atas memanggil `generate_signal()` untuk mengirim alert, `queue_alert()`, `notification_governor`, atau modul `engine/shadow/e3_shadow.py` — selama handler menu baru hanya memanggil fungsi getter yang sudah ada (bukan fungsi checker/alert), ia otomatis terisolasi dari pipeline sinyal produksi/shadow.

---

## Bagian 1 — Inventaris UI/menu Telegram saat ini

### 1.1 Command dan menu interaktif

Registrasi command terjadi di `CommandHandler(...)` (`interfaces/telegram_bot.py:7378-7424` per audit sebelumnya, terverifikasi masih berlaku pada revisi terkini). Ringkasan struktur navigasi aktual (reply keyboard) per `_main_menu_keyboard()` (`telegram_bot.py:323-331`):

```text
Menu Utama
├─ 📊 Market            (_market_submenu_keyboard, :363-374)
│  ├─ Ringkasan Pagi/Malam, Radar, Radar Pro, Kondisi Global
│  └─ 🔔 Monitor Pasar   (_market_monitor_submenu_keyboard, :425-436)
│     ├─ Cek Breakout, Cek Volume Spike
│     ├─ 📍 Levels (S/R)
│     ├─ Cek Big Move (snapshot), Cek RSI Ekstrem (snapshot)
│     └─ Snapshot Market
├─ 💹 Trading            (_trading_submenu_keyboard, :385-396)
│  ├─ Saran Spot, 🟢 Peluang Spot
│  ├─ 🔎 Scan Futures, 🔍 Analisis Coin   ← selector coin (lihat 1.2)
│  ├─ Posisi Aktif, Buka Posisi, Tutup Posisi
├─ 📈 Analisis           (_analysis_submenu_keyboard, :399-409)
│  ├─ Konteks Market, Prediksi Market, Skor Quant, Penjelasan AI
│  └─ 📊 Performance     (_performance_submenu_keyboard, :439-448)
│     ├─ Akurasi Sinyal, Kinerja Trade (RR/PF), Ringkasan Mingguan, Riset Shadow E3
├─ 🌍 Makro & Sentimen   (_macro_submenu_keyboard, :412-422)
│  ├─ Data Makro, Funding Rate & OI, CFRA, Kalender Ekonomi
│  └─ 🐋 Monitor Whale    ← lihat C.1, bukan per-coin sungguhan
└─ ⚙️ Sistem             (_system_submenu_keyboard, :451-461)
   ├─ Status/Health Sistem, Alert Stats
   └─ Test Alert, Debug Market, Cek Promosi Shadow
```

Tidak ada tombol/menu bernama "Informasi" atau semacamnya di struktur ini. Detail lengkap 45 command dan pemetaannya ke keyboard sudah didokumentasikan di `AUDIT_MENU_TELEGRAM_LENGKAP_REPORT.md` §1-2 — tidak diulang di sini karena masih akurat (diverifikasi line count file: 7680 baris, konsisten dengan struktur pasca-restrukturisasi).

### 1.2 Alur "pilih coin dari list → info per coin": sudah ada sebagian, bentuknya apa

**Ada, tapi selalu single-purpose (satu kategori data), tidak pernah 4-kategori sekaligus.** Semua memakai satu pola builder yang sama, `_build_coin_selector(prefix, coins)` (`telegram_bot.py:483-494`), yang membuat `InlineKeyboardMarkup` 2 kolom dengan `callback_data=f"{prefix}_{coin}"`. Satu handler `coin_selector_callback()` (`:888-943`) menangani semua prefix:

| Tombol pemicu | prefix | Coin list | Aksi setelah pilih coin |
|---|---|---|---|
| 🔍 Analisis Coin (`:635-636`) | `spot` | `MAJOR_COINS` (21 coin, `engine/market/market_universe.py:15-21`) | `spot_command(symbol)` → **hanya teknikal**: signal/type/confidence/reason, price, RSI, trend, entry/SL/target/RR (`:1010-1120`) |
| Route legacy "📊 Market Coin" (`:794`) | `market` | `ALLOWED_COINS` | `_get_market_report_text(symbol)` → **hanya teknikal**: Price, Trend, RSI, 4H/1D Trend, Alignment, Support, Resistance (`:1220-1259`) — **tidak termasuk Volume** meski field `volume_24h` tersedia di snapshot |
| 🔎 Scan Futures (`:619,811`) | `scan` | `MAJOR_COINS` | Daftar peluang trading futures untuk coin tsb |
| 📈 Buka Posisi (`:643,818`) | `entry` | `ALLOWED_COINS` | Membuka posisi (aksi trading, bukan info) |
| 📉 Tutup Posisi (`:652,827`) | `close` | posisi aktif user | Menutup posisi |
| 🔎 Penjelasan AI (`:689,847`) | `why` | `MAJOR_COINS` | Penjelasan keputusan AI trading terakhir untuk coin tsb |

Tidak ada satu pun prefix yang menggabungkan Teknikal + Fundamental + On-chain + Makro dalam satu tampilan per-coin — semuanya sinyal/trading-oriented (spot, entry, scan, why) atau teknikal murni (market). Kalau fitur "Informasi" dibangun, pola `_build_coin_selector()` + `coin_selector_callback()` sudah bisa dipakai ulang langsung (tinggal tambah prefix baru, mis. `info`), tidak perlu membangun mekanisme selector dari nol.

### 1.3 Penanganan pertanyaan info coin via chat bebas

Jalur ini **LLM/web-search, bukan deterministik terhadap data internal**, dan **terpisah total** dari command Telegram di atas. Berdasarkan `docs/agent-rules/runtime/intent-routing.md` dan `docs/agent-rules/runtime/ai-output-rules.md`:

- `detect_intent()` di `core/tool_router.py` mengembalikan salah satu dari 4 intent (`memory`, `math`, `search`, `chat`) lewat **aturan substring berurutan**, bukan model klasifikasi — tidak ada skor confidence, pemenang adalah rule pertama yang cocok.
- Pertanyaan fundamental bebas seperti "apa use case token X" atau "siapa tim di belakang project Y" akan jatuh ke intent `search` (memicu kata seperti "siapa") atau `chat` (fallback).
- Cabang `search` di `ask_aliza()` (`engine/brain/aliza_engine.py`) memakai `SerperDevTool` (`core/tools.py:11`) — pencarian web umum + sintesis LLM (`gpt-4o-mini`), **bukan** query ke `market_snapshot`, `institutional_data.py`, atau modul market lain.
- Ada tool `knowledge_search` (RAG lokal, FAISS, `core/knowledge_base.py`) tapi isi `knowledge/documents/` **tidak relevan dengan crypto** — hanya berisi dokumen tugas jabatan fungsional PNS (`Tabel Kegiatan Tugas Jabfung Penata Kelola Perumahan.pdf/.xlsx`, `Instructions.txt`). Untuk pertanyaan fundamental coin, `knowledge_search` akan mengembalikan hasil tidak relevan atau kosong.
- Kesimpulan: jalur chat bebas untuk info fundamental coin **bukan pipeline data terstruktur** — akurasinya bergantung sepenuhnya pada hasil pencarian web + pengetahuan umum LLM, tidak ada verifikasi terhadap sumber data internal proyek ini.

---

## Bagian 2 — Matriks kesiapan data per kategori

### A. Teknikal *(diaudit sesi sebelumnya — dilampirkan ulang di sini)*

Struktur data pusat: `market_snapshot` dict di `engine/market/market_snapshot_engine.py` (baris 56-61), diisi `update_market_snapshot()` (baris 331) untuk **21 coin fixed watchlist** (`CORE_COINS`/`MAJOR_COINS`, `engine/market/market_universe.py:15-21` — dynamic universe sudah dinonaktifkan). Dijadwalkan tiap **60 detik** (`interfaces/telegram_bot.py:7509`), TTL stale **300 detik** (`MAX_AGE_SEC`, `market_snapshot_engine.py:65`). Diakses via `get_market_snapshot()` (`:467`).

| Item | Status | Sumber data & fungsi persis | Per-coin/global | Live/statis (TTL) | Catatan kualitas |
|---|---|---|---|---|---|
| 1. Price action & tren | ADA | `_trend_from_ma()` `engine/market/market_analyzer.py:259-266`, dipanggil dari `market_signal()` (`:372-382`). Ditampilkan via `_get_market_report_text()` `telegram_bot.py:1220-1259` (`/market`). | Per-coin, 21 coin | Live per cycle 60 detik, TTL 300 detik | Trend hanya 3 kelas (BULLISH/BEARISH/SIDEWAYS) dari SMA50 vs SMA200 (fallback SMA20/SMA50); data tidak cukup → fallback diam-diam ke "SIDEWAYS" (`market_analyzer.py:381-382, 440-442`), tidak dibedakan dari sideways sungguhan |
| 2. Support & resistance | ADA — **dua implementasi berbeda, tidak konsisten** | (a) `_support_resistance()` `market_analyzer.py:252-256` — min/max 20 candle terakhir, dipakai `/market` & snapshot utama. (b) `get_sr_levels()` `engine/market/breakout_detector.py:119-147` — cluster 3 level tertinggi/terendah dari 1D high/low, cache 4 jam, **hanya** dipakai untuk alert breakout | Per-coin (keduanya generik untuk semua 21 coin) | (a) live 60 detik; (b) cache 4 jam | Dua algoritma S/R berjalan paralel dengan hasil berbeda tergantung command; menu Informasi harus memilih salah satu secara sadar dan didokumentasikan, bukan tercampur |
| 3. Volume perdagangan (bukan spike) | PARSIAL | `_enrich_collected_with_binance_24h()` `market_snapshot_engine.py:162-209` mengisi `volume_24h` (quoteVolume USDT) dari Binance `/ticker/24hr`. Terpisah dari `volume_spike_detector.py` (deteksi anomali saja, `get_avg_volume`/`check_volume_spike`) | Per-coin | Live 60 detik | Field `volume_24h` ADA di snapshot tapi **tidak pernah ditampilkan langsung** ke user di `telegram_bot.py` manapun — hanya dipakai internal untuk prompt AI (`_top_coins_analysis_dict()` `:2293-2315`). Tidak ada command yang menunjukkan "Volume 24h: $X" |
| 4. MA/EMA, RSI, MACD | PARSIAL/TIDAK ADA | RSI-14 Wilder smoothed: `_calculate_rsi()` `market_analyzer.py:227-249` (duplikat di `engine/market/features.py:13-32`). MA: `_moving_average()` `market_analyzer.py:221-224` = **SMA murni** (`sum/period`), **BUKAN EMA** — tidak ada fungsi EMA di manapun. MACD: **tidak ditemukan sama sekali** (grep "macd" di seluruh `engine/` nihil) | RSI: per-coin, terekspos ke user via `/market`, `/radar`. MA: dihitung (`features.py:172-174`) tapi **dibuang** sebelum masuk hasil akhir `market_signal()` (`market_analyzer.py:401-408`) — nilai numerik SMA20/50/200 tidak pernah tersimpan di snapshot atau terlihat user, hanya kesimpulan trend kategorikal. MACD: perlu dibangun dari nol | RSI live 60 detik | RSI-14 sudah siap tampil apa adanya. SMA dan MACD butuh kerja tambahan (lihat Bagian 3) |

Catatan tambahan dari audit sebelumnya: `market_signal()` generik untuk symbol apa pun (bukan hardcode BTC); semua command Telegram teknikal membaca dari cache snapshot 60 detik, bukan fetch langsung per klik user.

### B. Fundamental

| Item | Status | Sumber data & fungsi persis | Per-coin/global | Live/statis | Catatan kualitas |
|---|---|---|---|---|---|
| 1. Tokenomics (circulating/total/max supply, FDV, market cap) | **TIDAK ADA** | Endpoint CoinGecko `coins/markets` **sudah dipanggil** di `engine/market/dynamic_universe.py:19,168-173` (`MARKETS_URL`) dan secara alami mengembalikan field `circulating_supply`, `total_supply`, `max_supply`, `fully_diluted_valuation`, `market_cap` per response CoinGecko — **tapi kode hanya membaca** `total_volume`, `market_cap`, `price_change_percentage_24h` dari tiap item (`dynamic_universe.py:203-210`) untuk filter likuiditas; field lain dibuang. Endpoint detail `coins/{id}` (yang berisi deskripsi, links, komunitas) **tidak pernah dipanggil** di manapun — grep `coins/{` di seluruh repo hanya menemukan `coins/{coin_id}/market_chart` (harga historis), bukan endpoint detail coin | N/A — belum ada sama sekali | N/A | Kompleksitas mengisi gap ini **kecil** karena panggilan API yang sama sudah ada di codebase; tinggal menangkap field tambahan dari response yang sudah diterima, atau menambah 1 field param `ids=` pada endpoint `coins/markets` yang sudah dipanggil untuk 21 coin watchlist sekaligus |
| 2. Utilitas & use case | **TIDAK ADA sumber terstruktur** | Tidak ada field/endpoint project description di kode manapun (grep `whitepaper`, `use_case`, `tokenomics` di seluruh `engine/`, `interfaces/`, `core/` = nihil). Jalur satu-satunya adalah chat bebas → intent `search`/`chat` → LLM + web search (lihat Bagian 1.3) | N/A | N/A (jawaban LLM real-time, bukan data tersimpan) | Tidak bisa diandalkan sebagai sumber informasi konsisten/terverifikasi — jawaban bisa berbeda tiap kali ditanya, tidak ada caching/validasi terhadap sumber resmi project |
| 3. Tim & kemitraan | **TIDAK ADA sumber terstruktur** | Sama seperti B.2 — tidak ada endpoint/field terstruktur; grep `"team"`, `partnership` di kode nihil. Hanya via LLM/web search generik (`SerperDevTool`), tanpa filter sumber berita resmi project | N/A | N/A | Risiko akurasi lebih tinggi dibanding B.2 (info tim/kemitraan lebih rentan berubah/palsu di web daripada definisi use case yang relatif stabil) |

### C. On-chain

| Item | Status | Sumber data & fungsi persis | Per-coin/global | Live/statis | Catatan kualitas |
|---|---|---|---|---|---|
| 1. Whale movement | **PARSIAL — proxy BTC global, bukan per-coin sungguhan** | `get_large_transactions()` `engine/market/market_radar.py:39-73` — Blockchair API transaksi BTC senilai >300.000.000.000 satoshi (~3000 BTC), lalu `whale_intensity()` (`:79-92`) membucket jumlah transaksi ke LOW/MEDIUM/HIGH/EXTREME. Hasil ini (`whale_activity`) **dibroadcast identik ke SEMUA 21 coin** lewat `market_signal(symbol, radar_data)` — dikonfirmasi eksplisit di docstring `market_analyzer.py:272` ("radar_data … dipakai agar radar tidak dipanggil per coin") dan penerapannya di `market_analyzer.py:484` (`radar.get("whale_activity")` sama untuk symbol apa pun) | **Global (BTC-only)**, ditempelkan ke semua coin | Live, dipanggil sekali per siklus radar (bukan per coin) | `check_whale_command()` (`telegram_bot.py:6129-6162`, tombol 🐋 Monitor Whale) menampilkan baris terpisah untuk `_WHALE_MONITOR_COINS = ("BTC","ETH","BNB","SOL","XRP")` (`:219`) dengan kolom "Pressure" — **karena input `whale_pressure` (`whale_flow_analyzer.py`) sepenuhnya berasal dari field global** (`whale_activity`, `liquidation_risk`, `open_interest_level` — semua broadcast sama, `market_analyzer.py:484-487`), kolom Pressure akan **identik untuk kelima coin** meski ditampilkan seolah per-coin. Hanya kolom "Accum" yang bisa berbeda (karena `detect_whale_accumulation()` juga memakai `trend`/`rsi` per-coin) |
| 2. Exchange netflow | **TIDAK ADA (default), plus bug lama masih ada** | `get_btc_exchange_netflow()` `engine/market/institutional_data.py` — status default `not_configured`; scraping fallback (`btcdash.org`) diimplementasi tapi `BTC_NETFLOW_SCRAPE_ENABLED` tidak diset di `.env` produksi (default `false` per `.env.example:64`). **BTC-only** meski diaktifkan — bukan per-coin. **Temuan lama dikonfirmasi masih ada**: `stablecoin_inflow()` `engine/detectors/smart_money_tracker.py:10-49` menjumlahkan `circulating.peggedUSD` **seluruh stablecoin** dari DeFiLlama (`stablecoins.llama.fi/stablecoins`) — ini **total circulating market cap** stablecoin (level), **bukan arus/flow**, lalu dibucket HIGH/NORMAL/LOW dengan ambang tetap (>150B/>100B). Field hasilnya (`stablecoin_flow`) diberi label "Arus Stablecoin" di `engine/market/market_report_formatter.py:40` (fungsi `format_market_report`, saat ini **dead code** — diimpor `telegram_bot.py:77` tapi tidak dipanggil di manapun, jadi label salah ini tidak live-tampil ke user hari ini) | Global (BTC-only untuk netflow; stablecoin bug global untuk semua stablecoin) | Netflow: N/A (nonaktif). Stablecoin bug: live tiap kali `market_radar()` jalan | Meski label "Arus Stablecoin" yang salah tidak tampil langsung ke user saat ini (dead code), nilai `stablecoin_flow` yang keliru tetap **dipakai sebagai input** `smart_money_score()` dan `bull_probability()` (`market_radar.py:180-184, 209-214`) — mencemari skor `bull_probability`/`market_phase_prediction` yang **memang** ditampilkan ke user (mis. via `/predict`), secara diam-diam, tanpa indikasi kualitas data ke user |
| 3. Aktivitas jaringan (active address, tx count) | **TIDAK ADA** | Grep `active_address`, `tx_count`, `transaction_count`, `network_activity`, `nvt` di seluruh repo = nihil. Tidak ada endpoint atau fungsi apa pun untuk metrik ini | N/A | N/A | Catatan desain penting untuk Bagian 3: sebagian besar dari 21 coin watchlist adalah **token**, bukan chain mandiri (mis. PEPE, ARB, JTO, ETHFI, WLD, OM, XPL, TAO, BONE, HYPE, FARTCOIN, ZEREBRO umumnya token di atas Ethereum/Solana/BNB Chain atau L2, bukan blockchain sendiri) — "aktivitas jaringan per coin" secara konsep hanya relevan penuh untuk coin dengan chain sendiri (BTC, ETH, SOL, BNB, ADA, SUI, XRP) |

### D. Makro & sentimen

| Item | Status | Sumber data & fungsi persis | Per-coin/global | Live/statis | Catatan kualitas |
|---|---|---|---|---|---|
| 1. Suku bunga/The Fed | **ADA** (FRED), kalender FMP **ADA tapi nonaktif default** | FRED: `engine/market/macro_monitor.py` — `MACRO_SERIES` (`:28-53`) mencakup `CPIAUCSL` (CPI), `PCEPILFE` (core PCE), `PAYEMS` (nonfarm payrolls), `FEDFUNDS` (fed funds rate); fetch via `FRED_OBS_URL` (`:22`), cache 6 jam per series_id (`:140`). `FRED_API_KEY` **terisi** di `.env` produksi (dikonfirmasi ada, nilai tidak ditampilkan). Kalender FMP: `_fetch_from_fmp()` `engine/market/economic_calendar.py:246-296`, endpoint `financialmodelingprep.com/api/v3/economic_calendar`; **hanya dipanggil jika `FMP_CALENDAR_ENABLED=true` DAN `FMP_API_KEY` terisi** (`:26-31`). `FMP_API_KEY` **ada** di `.env` produksi, tapi `FMP_CALENDAR_ENABLED` **tidak diset** di `.env` produksi (default `false` per `.env.example:37-41`, komentar kode menyebut alasan: key mengembalikan HTTP 403 terus-menerus, lihat `BERITA_MITIGASI_REPORT.md`) | Global (makro AS, tidak per-coin — secara konsep memang benar begitu) | FRED: live, cache 6 jam. FMP kalender: **tidak aktif** — sistem jatuh ke `_generate_rule_events()` (kalender rule-based statis) atau fallback Serper (`economic_calendar.py:123-211, 357-405`) | Data suku bunga (FEDFUNDS) via FRED sudah live dan siap tampil. Kalender jadwal rilis FMP **belum live** meski API key tersedia — perlu keputusan eksplisit user untuk mengaktifkan `FMP_CALENDAR_ENABLED=true` (risiko: key sudah dikonfirmasi 403 di riwayat sebelumnya, mungkin perlu key baru) |
| 2. BTC Dominance | **ADA** | `engine/market/global_market_cache.py` — `_fetch_btc_dominance_coingecko()` (`:54-80`, CoinGecko `/api/v3/global`) primer, fallback `_fetch_btc_dominance_fallback()` (`:83-103`, CoinPaprika `/v1/global`) jika CoinGecko gagal/429. Cache 300 detik (`CACHE_REFRESH_INTERVAL`, `:14`) | Global (memang secara konsep market-wide, bukan per-coin) | Live, cache 5 menit | Jika **kedua** sumber gagal, fungsi diam-diam mengembalikan default `50.0` (`_fetch_btc_dominance:117-118`) **tanpa status eksplisit** (`ok`/`not_configured`/`fetch_failed`) seperti pola di `institutional_data.py` — user tidak bisa membedakan "dominance benar-benar 50%" vs "kedua API gagal, ini angka default" |
| 3. Fear & Greed / sentimen | **ADA** | `_fetch_fear_greed()` `global_market_cache.py:41-51` — `api.alternative.me/fng/`. Cache sama (300 detik), satu fungsi `get_global_market_data()` (`:130-144`) mengembalikan `fear_greed` + `btc_dominance` sekaligus | Global | Live, cache 5 menit | Fallback diam-diam sama seperti BTC Dominance: gagal fetch → default `50.0` tanpa keterangan status ke user |

*(Konteks tambahan di luar 13 item wajib, relevan untuk D: ETF Flow institusional **ADA dan live** via SoSoValue/Farside fallback (`engine/market/institutional_data.py`), Liquidation 24h **TIDAK ADA** — `COINGLASS_API_KEY` kosong di `.env` produksi. Sudah diaudit tuntas di `INSTITUTIONAL_DATA_REPORT.md`, tidak diulang detail di sini.)*

---

## Bagian 3 — Gap analysis & estimasi

### 3.1 Tabel ringkas: siap hari ini vs butuh sumber baru

| # | Item | Bisa tampil HARI INI dari data existing? | Kompleksitas gap |
|---|---|---|---|
| A1 | Price action & tren | **Ya** — tinggal format ulang `_get_market_report_text()` | — |
| A2 | Support & resistance | **Ya**, tapi pilih 1 dari 2 implementasi dulu (naive min/max vs cluster breakout) | KECIL (keputusan + wiring) |
| A3 | Volume 24h | **Ya** — field `volume_24h` sudah ada di snapshot, tinggal ditambah ke pesan | KECIL |
| A4a | RSI | **Ya** — RSI-14 sudah dihitung & terekspos | — |
| A4b | MA (SMA) | Tidak langsung — nilai numerik dibuang sebelum masuk snapshot | KECIL (tangkap nilai yang sudah dihitung, jangan dibuang) |
| A4c | EMA | Tidak ada | SEDANG (fungsi baru, murni komputasi dari data harga yang sudah difetch — tidak perlu API baru) |
| A4d | MACD | Tidak ada | SEDANG (fungsi baru, butuh EMA dulu sebagai basis; data harga sudah tersedia) |
| B1 | Tokenomics | Tidak, tapi endpoint sumbernya sudah dipanggil untuk keperluan lain | **KECIL** (tangkap field tambahan dari response `coins/markets` yang sudah di-fetch, atau tambah 1 call `coins/markets?ids=...` untuk 21 coin watchlist) |
| B2 | Use case | Tidak ada jalur terstruktur | SEDANG (lihat 3.2) |
| B3 | Tim & kemitraan | Tidak ada jalur terstruktur | BESAR (lihat 3.2) |
| C1 | Whale movement | Ada tapi proxy BTC global, bukan per-coin — tidak boleh ditampilkan seolah per-coin tanpa disclaimer | KECIL untuk tampil dengan disclaimer jujur; BESAR untuk jadi genuinely per-coin |
| C2 | Exchange netflow | Tidak (default nonaktif, BTC-only) | BESAR (lihat 3.2) |
| C3 | Aktivitas jaringan | Tidak ada sama sekali | SEDANG–BESAR (lihat 3.2), dan secara konsep hanya relevan penuh untuk 7 dari 21 coin watchlist yang punya chain sendiri |
| D1 | Suku bunga Fed | **Ya** (FRED, key sudah ada) | — |
| D1b | Kalender FMP | Tidak aktif meski key ada | KECIL (ubah 1 flag `.env`), TAPI riwayat key 403 perlu dicek ulang dulu |
| D2 | BTC Dominance | **Ya** | — |
| D3 | Fear & Greed | **Ya** | — |

### 3.2 Opsi sumber data untuk gap yang butuh sumber baru (tanpa mendaftar/memanggil apa pun)

- **B1 Tokenomics** — **KECIL**. CoinGecko `coins/markets` (sudah dipanggil di `dynamic_universe.py`, free tier, tanpa API key) sudah mengembalikan `circulating_supply`, `total_supply`, `max_supply`, `fully_diluted_valuation`, `market_cap` per coin. Tidak perlu API baru sama sekali — hanya perlu menangkap field yang sudah datang dalam response yang sudah ada.
- **B2 Use case** — **SEDANG**. CoinGecko endpoint `coins/{id}` (belum pernah dipanggil di repo ini) punya field `description.en` gratis tanpa key, tapi rate limit publik CoinGecko cukup ketat (puluhan request/menit) sehingga untuk 21 coin perlu strategi cache/refresh jarang (mis. harian, bukan tiap snapshot 60 detik). Catatan kualitas: sejumlah coin di watchlist (PEPE, FARTCOIN, ZEREBRO, BONE, dll — token meme/kecil) kemungkinan punya deskripsi CoinGecko yang minim/kosong — perlu fallback jujur ("deskripsi belum tersedia") bukan mengarang.
- **B3 Tim & kemitraan** — **BESAR**, dan ini bukan cuma soal biaya API — tidak ada API terstruktur standar untuk "siapa tim project X" yang reliable untuk seluruh watchlist (termasuk banyak meme coin tanpa tim publik terverifikasi). Opsi realistis: (a) tetap serahkan ke jalur LLM/web search seperti sekarang dengan disclaimer eksplisit "hasil AI, bukan data terverifikasi", atau (b) kurasi manual per coin (bukan pekerjaan engineering, perlu riset manusia berkelanjutan).
- **C1 Whale movement per-coin sungguhan** — **BESAR**. Blockchair mendukung multi-chain (bukan cuma Bitcoin), jadi secara prinsip bisa diperluas per-chain untuk BTC/ETH/SOL/dll — tapi ini butuh redesain `market_radar()` dari "satu panggilan global" menjadi "N panggilan per coin/chain", plus rate-limit Blockchair free tier perlu diperhitungkan untuk 21 coin. Vendor on-chain khusus (Glassnode, CryptoQuant, Santiment — disebut tanpa memanggil apa pun) umumnya free tier-nya sangat terbatas: sedikit metrik, biasanya cuma BTC/ETH, dan quota harian kecil.
- **C2 Exchange netflow** — **BESAR**. Sudah diriset tuntas di `INSTITUTIONAL_DATA_REPORT.md`: CoinGlass punya endpoint tapi baru tersedia mulai plan berbayar (~$79/bulan untuk netflow spot), tidak ada tier gratis CoinGlass sama sekali. Alternatif scraping (btcdash.org) terbukti butuh render JavaScript dan datanya sendiri diberi label "estimasi" oleh situs sumbernya — kualitas rendah meski dipaksakan.
- **C3 Aktivitas jaringan** — **SEDANG–BESAR**. Untuk 7 coin dengan chain sendiri (BTC, ETH, SOL, BNB, ADA, SUI, XRP), Blockchair/block explorer publik masing-masing chain bisa memberi active address & tx count dengan free tier terbatas (rate limit ketat untuk 7 chain berbeda). Untuk 14 coin sisanya yang merupakan token, "aktivitas jaringan" perlu didefinisikan ulang (mis. transfer token di chain host, bukan aktivitas "jaringan sendiri") atau item ini secara jujur ditandai "tidak berlaku" untuk token.

### 3.3 Estimasi kompleksitas — ringkasan per gap

| Kompleksitas | Item |
|---|---|
| **KECIL** (data sudah ada / sudah dipanggil, tinggal format menu) | A1 Price/tren, A2 S/R (pilih 1 impl), A3 Volume, A4b SMA (tangkap nilai yang dibuang), B1 Tokenomics, D1 Suku bunga Fed, D2 BTC Dominance, D3 Fear & Greed, C1 Whale (tampil dengan disclaimer jujur bahwa ini proxy BTC global) |
| **SEDANG** (API baru gratis, atau komputasi baru dari data existing) | A4c EMA, A4d MACD (murni komputasi, tanpa API baru), B2 Use case (CoinGecko `coins/{id}`, gratis tapi rate-limited), C3 Aktivitas jaringan (terbatas ke 7 coin dengan chain sendiri), D1b Kalender FMP (tinggal ubah flag, tapi perlu cek ulang validitas key) |
| **BESAR** (butuh API berbayar/infrastruktur baru, atau tidak ada solusi teknis yang bagus) | B3 Tim & kemitraan (bukan cuma soal API — tidak ada sumber terstruktur reliable), C2 Exchange netflow (CoinGlass berbayar, alternatif gratis kualitas rendah), C1 Whale per-coin sungguhan (redesain arsitektur + rate limit multi-chain) |

### 3.4 Risiko yang harus dihindari — konfirmasi pemisahan desain

**Menu Informasi harus murni fitur *display*, tidak boleh menyuntikkan data baru ke jalur sinyal produksi/shadow** (evaluasi E3 sedang berjalan hingga sekitar 1 September 2026). Berdasarkan penelusuran kode di audit ini, seluruh fungsi yang relevan untuk menu Informasi adalah fungsi **read-only** terhadap cache/snapshot yang sudah ada:

- `get_market_snapshot()` (`market_snapshot_engine.py:467`) — baca snapshot, tidak menulis apa pun.
- `get_global_market_data()` (`global_market_cache.py:130-144`) — baca cache dominance/fear&greed.
- Fungsi-fungsi `macro_monitor.py` (FRED) dan `institutional_data.py` (ETF/netflow/liquidation) — semua mengembalikan dict `status`/`message`/nilai, tidak memanggil `queue_alert()` atau menulis ke tracker manapun.
- `get_sr_levels()` (`breakout_detector.py`) — baca cache S/R 4 jam.

**Tidak satu pun** dari fungsi di atas memanggil `generate_signal()` (jalur sinyal produksi), `notification_governor`, atau modul `engine/shadow/e3_shadow.py`/`engine/trading/signal_tracker.py` (jalur evaluasi shadow). Selama handler baru untuk menu Informasi **hanya memanggil fungsi getter di atas** (bukan fungsi checker seperti `big_move_checker()`, `rsi_extreme_checker()`, atau `whale_alert_job()` yang memang mengantre alert), fitur ini secara arsitektural terisolasi dari pipeline sinyal produksi/shadow — **desain pemisahan yang diminta sudah didukung oleh struktur kode yang ada**, tidak perlu refactor tambahan untuk mencapainya. Yang perlu dijaga saat implementasi nanti: pastikan handler baru tidak "meminjam" fungsi checker (yang punya efek samping mengirim alert) hanya karena kebetulan menghitung angka yang sama.

---

## Batas kepastian

Audit ini murni pembacaan kode statis + grep; tidak ada command Telegram yang dijalankan, tidak ada API eksternal baru yang dipanggil (evidensi ETF/Liquidation/FRED/BTC Dominance/Fear&Greed diambil dari laporan audit sebelumnya yang sudah memverifikasi langsung ke produksi, bukan dari eksekusi baru di sesi ini). Ketersediaan `FRED_API_KEY`/`SERPER_API_KEY`/`OPENAI_API_KEY`/`FMP_API_KEY` di `.env` produksi dikonfirmasi lewat pengecekan nama variabel saja (nilai tidak pernah ditampilkan); validitas key tersebut (apakah masih aktif/tidak revoked) **TIDAK PASTI** tanpa memanggil API sungguhan. Rate limit CoinGecko/Blockchair free tier yang disebut di Bagian 3.2 adalah pengetahuan umum publik, bukan hasil verifikasi langsung di sesi ini — perlu dicek ulang sebelum keputusan implementasi final.
