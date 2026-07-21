# 05 — Konfigurasi dan Operasional

> **Status: SUPERSEDED.** Snapshot pada 2026-07-21. Kondisi sistem terkini ada di `docs/README.md` dan report Fase 1–4 (`docs/reports/` — lihat Bagian 3). Jangan jadikan dokumen ini sebagai acuan status aktif.

## File konfigurasi

| File | Fungsi dan catatan |
|---|---|
| `.env` | Rahasia runtime Telegram/dashboard/sumber data; mode `0600 ubuntu:ubuntu`. Semua nilai rahasia disensor. |
| `.env.market` | Override `IS_PRIMARY_DISPATCHER` untuk market service; mode `0664`, tidak berisi secret pada pemeriksaan nama key. |
| `.env.example` | Template environment; mode `0664`; memuat nama variabel dan default non-rahasia. |
| `/etc/aliza-dashboard/dashboard.env` | Env khusus systemd dashboard; isi tidak dibaca dan tidak berada di repo. |
| `config/agent.yaml` | Metadata/persona agent; mengklaim model `gpt-4o` dan beberapa skill. Runtime `core/agent.py` memakai `gpt-4o-mini`, sehingga config ini tidak sepenuhnya authoritative. |
| systemd unit/drop-in host | Konfigurasi service, user, restart, hardening dan EnvironmentFile. Bukan bagian repo. |
| `/etc/logrotate.d/aliza-ai` | Rotasi log Aliza. |
| `data/user_config.db` | Mode saldo auto/manual dan balance per user. |
| `data/signal_state.json` | State dedup signal 15 menit. |

## Variabel environment

Nilai rahasia di bawah sengaja ditulis sebagai `<redacted>`. “Default” hanya dicatat bila terlihat eksplisit dalam kode/template dan bukan rahasia.

### Rahasia/kredensial

| Variabel | Nilai | Fungsi |
|---|---|---|
| `OPENAI_API_KEY` | `<redacted>` | CrewAI/OpenAI chat dan laporan market |
| `TELEGRAM_BOT_TOKEN` | `<redacted>` | autentikasi Bot API |
| `TELEGRAM_CHAT_ID` | `<redacted>` | allowlist sekaligus tujuan default Telegram |
| `DB_PASSWORD` | `<redacted>` | PostgreSQL `core/database.py` |
| `JWT_SECRET` | `<redacted>` | JWT HS256; minimum 32 karakter |
| `BINANCE_API_KEY` | `<redacted>` | signed account balance |
| `BINANCE_API_SECRET` | `<redacted>` | signature account balance |
| `COINGECKO_API_KEY` | `<redacted>` | header CoinGecko opsional |
| `SERPER_API_KEY` | `<redacted>` | search/news/calendar fallback |
| `NEWSAPI_KEY` | `<redacted>` | berita |
| `FRED_API_KEY` | `<redacted>` | data makro FRED |
| `FMP_API_KEY` | `<redacted>` | kalender ekonomi FMP |
| `EIA_API_KEY` | `<redacted>` | ada di `.env`, tetapi tidak ditemukan consumer source; kemungkinan sisa/tidak terpakai |

### Operasional dan risiko

| Variabel | Default/arti |
|---|---|
| `IS_PRIMARY_DISPATCHER` | default `true`; hanya proses primary boleh dispatch utama; `.env.market` mengoverride ke false |
| `SNAPSHOT_MAX_AGE_SEC` | 300 detik; batas freshness umum |
| `CB_THRESHOLD` | 10 kegagalan; circuit breaker snapshot |
| `CB_HEARTBEAT_EVERY` | 5; frekuensi heartbeat circuit breaker |
| `TRADING_MODE` | `INTRADAY`; alternatif logic threshold BTC mencakup scalping/swing |
| `RISK_PER_TRADE` | `0.02` = 2% |
| `MAX_ALLOCATION_PER_TRADE` | `0.30` = 30% |
| `MAX_TOTAL_RISK` | `0.06` = 6% |
| `ACCOUNT_BALANCE` | `<redacted>`; fallback saldo portfolio |
| `USER_CONFIG_DB` | `data/user_config.db` |
| `ALIZA_PORTFOLIO_BALANCE` | 10.000 pada engine portfolio legacy |
| `ALIZA_RISK_PCT` | `0.01` = 1% pada engine legacy |
| `BINANCE_API_BASE` | `https://api.binance.com` |
| `BINANCE_BALANCE_CACHE_SEC` | 300 detik |
| `ECONOMIC_CALENDAR_CACHE_SEC` | 3.600 detik |
| `INVESTING_CALENDAR_CACHE_SEC` | 3.600 detik |
| `INVESTING_MIN_FETCH_INTERVAL_SEC` | 3.600 detik |

### Dashboard/API

| Variabel | Default/arti |
|---|---|
| `ALIZA_DOTENV_ENABLED` | legacy default true; launcher dashboard/API mematikannya agar memakai env systemd khusus |
| `ALIZA_DASHBOARD_HOST` | `127.0.0.1` |
| `ALIZA_DASHBOARD_PORT` | `8001` |
| `ALIZA_DASHBOARD_DOCS_ENABLED` | false; menonaktifkan OpenAPI/Swagger/Redoc |
| `ALIZA_CHAT_LLM_TIMEOUT_SECONDS` | 45 detik, maksimum 120 |
| `ALIZA_CHAT_LLM_MAX_CONCURRENCY` | 2, maksimum 8 |

`.env.example` belum mencantumkan seluruh variabel yang dipakai source, khususnya `ALIZA_DOTENV_ENABLED`, host/docs/limit dashboard, cache kalender, `USER_CONFIG_DB`, variabel portfolio legacy, `BINANCE_API_BASE`, `NEWSAPI_KEY`, dan `COINGECKO_API_KEY`. Sebaliknya `EIA_API_KEY` ada di `.env` tetapi tidak ditemukan digunakan.

## Coin/pair yang dipantau

`engine/market/market_universe.py:CORE_COINS` adalah sumber aktual `get_tradable_coins()`:

```text
BTC, ETH, BNB, SOL, XRP, ADA, SUI, ARB, PEPE, JTO, ETHFI,
WLD, OM, ASTER, XPL, TAO, BONE, FARTCOIN, HYPE, ZEREBRO, XAUT
```

Pair utama dibentuk sebagai `<COIN>USDT`. Dynamic universe memiliki kode CoinGecko/filter volume/market-cap, tetapi fungsi publik saat ini langsung mengembalikan 21 core coin; auto-scan tidak aktif. Komentar “top 200” juga tidak sesuai implementasi fetch `per_page=50`.

Watchlist funding futures berisi 19 coin dan tidak identik dengan core universe. Analisis LLM terjadwal hanya fokus BTC, ETH, BNB, SOL, XRP. Blacklist alert berisi WLFI, SKY dan PIXEL, yang tidak termasuk core universe saat ini.

## Jadwal runtime

Scheduler utama berada di `interfaces/telegram_bot.py:main()` menggunakan `JobQueue`/APScheduler.

| Job | Jadwal |
|---|---|
| Refresh snapshot | setiap 60 detik; initial sync saat startup |
| Near support | setiap 5 menit |
| Near resistance | setiap 5 menit |
| RSI ekstrem | didaftarkan dua kali: setiap 5 menit dan 10 menit |
| Big move | setiap 5 menit |
| Watchdog | setiap 2 menit |
| Breaking news | setiap 1 jam |
| Morning analysis | 08:00 WIB (01:00 UTC) |
| Evening analysis | 20:00 WIB (13:00 UTC) |
| Prefetch laporan | setiap 15 menit di window terkait |
| Spot scheduled signals | 06:00, 12:00, dan 21:05 WIB; docstring masih menyebut enam kali/hari |
| Breakout | setiap 5 menit |
| Volume | setiap 5 menit |
| Funding | setiap 5 menit |
| CFRA/funding report | setiap 30 menit |
| Macro | setiap 1 jam |
| Whale | setiap 10 menit |
| Outcome signal | setiap 10 menit dan pemeriksaan lain setiap 30 menit |
| Kalender malam | 21:00 WIB (14:00 UTC) |

`interfaces/market_bot.py` juga memperbarui snapshot tiap 60 detik dan melakukan scan tiap 5 menit di proses terpisah. Log memperlihatkan refresh kadang sekitar 40 detik dan APScheduler sesekali melewatkan run, sehingga interval efektif dapat lebih panjang.

Crontab menyalin `telegram_bot.py` ke backup bertanggal setiap 02:00. Akibatnya kini ada 103 backup source di folder aktif. Job restart mingguan Aliza ada tetapi dikomentari.

## Deploy dan restart

Deployment aktual:

```text
systemctl restart aliza-telegram.service
systemctl restart aliza-market.service
# dashboard sengaja disabled/inactive; jangan enable tanpa validasi terkontrol
```

Ini dokumentasi keadaan, bukan instruksi yang dijalankan oleh audit.

`scripts/deploy/deploy.sh` tidak dapat dipercaya untuk deployment aktual: ia memakai path lama `/home/ubuntu/aliza-ai`, `git pull`, `pip install`, lalu merestart `aliza-api` dan `aliza-telegram`. Unit `aliza-api` di host menunjuk `/opt/aliza-etpp-agent`, bukan dashboard repo ini. `scripts/deploy/hooks.json` juga menyimpan path lama. `scripts/backup_aliza.sh` menulis dump ke `/home/ubuntu/aliza_backup.sql`.

## Logging dan monitoring

- Bot menulis `/opt/aliza-ai/logs/aliza.log`; saat audit sekitar 3,9 MB dengan file rotasi sekitar 11,6 MB dan gzip lama.
- Log dashboard: `logs/dashboard.log` dan `logs/dashboard-new.log`; kosong/tidak aktif sejak Juni pada pemeriksaan.
- systemd journal tersedia untuk service Telegram dan market.
- Logrotate `aliza.log`: harian, tujuh rotasi, compressed/delaycompress, `copytruncate`, maksimum 50 MB.
- Log dashboard: mingguan, empat rotasi, compressed, `copytruncate`.
- `scripts/server-monitor/monitor.sh` berisi placeholder token/chat dan memonitor `aliza-api` yang salah repo serta Telegram. Ini bukan monitoring produksi yang meyakinkan.
- `api/server.py:/health` selalu mengembalikan `status=ok`; tidak mengecek PostgreSQL, snapshot, OpenAI atau upstream market, sehingga bukan readiness check.
- `engine/monitoring/system_monitor.py` dan `market_monitor.py` ada, tetapi tidak ditemukan service/caller aktif yang jelas.

## Kondisi operasional saat audit

- `aliza-telegram`: active/enabled, proses terbaru.
- `aliza-market`: active/enabled, belum restart sejak 2 Juni dan terbukti memakai universe kode lama; walau non-primary, ia tetap menambah load API.
- `aliza-dashboard`: disabled/inactive dan tidak membuka port 8001.
- PM2/Docker: tidak tersedia.
- Log live menunjukkan validasi gagal berulang untuk empat coin exotic dan OI `OMUSDT` HTTP 400.
- Permission state lokal cukup ketat untuk `.env` (0600), tetapi `.env.market`/`.env.example` 0664. Direktori `data` mode 2770 dan database/state mode 0660 untuk group `aliza-dashboard`; `logs` mode 0700.

## TIDAK PASTI

- Config Nginx, firewall dan env dashboard di `/etc` tidak disalin ke repo dan tidak dibaca nilainya dalam audit ini.
- Tidak dapat dipastikan siapa yang mengonsumsi UI `web/`; FastAPI merujuk folder `dashboard/` yang kosong.
- Tidak dapat dipastikan apakah backup eksternal sukses, karena audit tidak menjalankan job atau memeriksa lokasi output di luar repo.
