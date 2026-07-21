# 01 — Struktur Repositori Aliza AI

> **Status: SUPERSEDED.** Snapshot pada 2026-07-21. Kondisi sistem terkini ada di `docs/README.md` dan report Fase 1–4 (`docs/reports/` — lihat Bagian 3). Jangan jadikan dokumen ini sebagai acuan status aktif.

## Ruang lingkup dan metode

Audit dilakukan secara read-only pada `/opt/aliza-ai` tanggal 21 Juli 2026 (WIB). Pohon di bawah mencakup kode dan konfigurasi aktif. Direktori `.git`, `venv`, `node_modules`, semua `__pycache__`, log terotasi, database/data biner, PDF/XLSX/PPTX, indeks FAISS, serta 103 salinan `.bak.*` tidak diekspansi. Nama berkas data pengguna juga disensor.

Status Git sebelum audit sudah tidak bersih: `engine/alerts/auto_alert_engine.py`, `engine/trading/opportunity_scanner.py`, dan `engine/trading/signal_engine.py` termodifikasi; `engine/utils/formatters.py` belum dilacak. Itu adalah perubahan yang sudah ada dan tidak disentuh audit ini.

## Pohon direktori

```text
/opt/aliza-ai/
├── .env                         # rahasia runtime; mode 0600
├── .env.example                 # contoh konfigurasi
├── .env.market                  # override service market
├── 1000:                        # berkas kosong anomali
├── 100M:                        # berkas kosong anomali
├── api/
│   ├── auth.py
│   ├── dashboard_api.py
│   ├── execution_limit.py
│   ├── market.py
│   ├── passwords.py
│   ├── rate_limit.py
│   ├── security.py
│   └── server.py
├── api_server.py                # API lama/deprecated
├── config/
│   └── agent.yaml
├── core/
│   ├── agent.py
│   ├── database.py
│   ├── environment.py
│   ├── knowledge_base.py
│   ├── rag_engine.py
│   ├── skill_loader.py
│   ├── tool_router.py
│   └── tools.py
├── dashboard/                   # kosong
├── data/
│   ├── aliza.db                 # SQLite runtime trading/sinyal
│   ├── signal_state.json
│   ├── trade_history.json
│   └── user_config.db
├── docs/                        # dirinci dalam 07-perbandingan-dengan-docs.md
├── engine/
│   ├── alerts/
│   │   ├── alert_manager.py
│   │   ├── auto_alert_engine.py
│   │   └── btc_smart_alert.py
│   ├── analytics/performance_analyzer.py
│   ├── brain/
│   │   ├── aliza_engine.py
│   │   ├── opportunity_ranker.py
│   │   ├── signal_quality_engine.py
│   │   └── trading_brain.py
│   ├── detectors/
│   │   ├── altseason_detector.py
│   │   ├── crash_detector.py
│   │   ├── liquidation_detector.py
│   │   ├── liquidation_monitor.py
│   │   ├── smart_money_tracker.py
│   │   └── whale_accumulation_detector.py
│   ├── explain/explain_engine.py
│   ├── indicators/constants.py
│   ├── intelligence/
│   │   ├── altseason_model.py
│   │   ├── crypto_intelligence.py
│   │   ├── document_analyzer.py
│   │   ├── market_ai_predictor.py
│   │   ├── market_intelligence_engine.py
│   │   ├── market_regime_detector.py
│   │   ├── market_state_engine.py
│   │   └── whale_flow_analyzer.py
│   ├── learning/
│   │   ├── confidence_adjuster.py
│   │   ├── learning_engine.py
│   │   ├── strategy_performance.py
│   │   └── trade_history_tracker.py
│   ├── macro/
│   │   ├── macro_checker.py
│   │   └── macro_monitor.py
│   ├── market/
│   │   ├── breakout_detector.py
│   │   ├── coin_id_resolver.py
│   │   ├── dynamic_universe.py
│   │   ├── economic_calendar.py
│   │   ├── funding_rate_monitor.py
│   │   ├── global_market_cache.py
│   │   ├── investing_calendar.py
│   │   ├── klines_cache.py
│   │   ├── macro_monitor.py
│   │   ├── market_analyzer.py
│   │   ├── market_context_engine.py
│   │   ├── market_intelligence.py
│   │   ├── market_radar.py
│   │   ├── market_radar_pro.py
│   │   ├── market_radar_pro_analyzer.py
│   │   ├── market_report_formatter.py
│   │   ├── market_snapshot_engine.py
│   │   ├── market_universe.py
│   │   ├── multi_timeframe_analyzer.py
│   │   └── volume_spike_detector.py
│   ├── monitoring/
│   │   ├── market_monitor.py
│   │   └── system_monitor.py
│   ├── portfolio/
│   │   ├── drawdown_protector.py
│   │   ├── portfolio_ai_engine.py
│   │   ├── portfolio_state.py
│   │   ├── position_sizer_legacy.py
│   │   └── risk_manager.py
│   ├── prediction/
│   │   ├── bias_score_engine.py
│   │   ├── prediction_engine.py
│   │   └── probability_engine.py
│   ├── reasoning/why_reason_engine.py
│   ├── spot/spot_engine.py
│   ├── strategy/
│   │   ├── strategy_engine.py
│   │   ├── strategy_filter.py
│   │   └── strategy_regime_map.py
│   ├── trading/
│   │   ├── opportunity_scanner.py
│   │   ├── signal_engine.py
│   │   ├── signal_tracker.py
│   │   └── trade_manager.py
│   ├── utils/
│   │   ├── formatters.py
│   │   ├── market_cache.py
│   │   └── market_cache_updater.py
│   ├── binance_balance.py
│   ├── market_signal.py
│   ├── position_sizer.py
│   ├── risk_manager.py
│   ├── signal_engine.py
│   ├── state_store.py
│   └── user_config.py
├── interfaces/
│   ├── market_bot.py
│   ├── telegram_bot.py
│   └── *.bak.*                  # 103 backup; 2026-04-18 s.d. 2026-07-21
├── knowledge/
│   ├── documents/               # instruksi + data besar yang tidak diekspansi
│   ├── uploads/                 # dokumen unggahan
│   └── vector_store/            # index.faiss dan index.pkl
├── logs/                        # log aktif/rotasi; tidak diekspansi
├── main.py
├── memory/
│   ├── active_document.py
│   ├── document_registry.py
│   ├── memory_manager.py
│   ├── user_profile.py
│   └── users/<user-id>.json
├── project/
│   └── aliza.code-workspace
├── requirements-dev.txt
├── requirements.txt
├── scripts/
│   ├── backup_aliza.sh
│   ├── deploy/
│   │   ├── deploy.sh
│   │   └── hooks.json
│   ├── run_dashboard.py
│   └── server-monitor/monitor.sh
├── skills_custom/
│   ├── calculator.py
│   ├── datetime_skill.py
│   ├── summarizer.py
│   └── weather.py
├── test_*.py                    # suite keamanan/API/Telegram
└── web/
    ├── app.js
    ├── index.html
    ├── style.css
    └── btc/{index.html,btc.js,btc.css}
```

## Fungsi folder utama

| Folder | Fungsi | Berkas penting |
|---|---|---|
| `api/` | FastAPI dashboard, autentikasi JWT/Argon2, pembatasan laju dan eksekusi LLM. | `server.py`, `auth.py`, `dashboard_api.py`, `rate_limit.py` |
| `core/` | Agen CrewAI, koneksi PostgreSQL, RAG, alat dan routing permintaan. | `agent.py`, `database.py`, `rag_engine.py`, `tools.py` |
| `data/` | State lokal trading/sinyal dan konfigurasi pengguna. | `aliza.db`, `user_config.db`, `signal_tracking` di SQLite, JSON riwayat/dedup |
| `engine/` | Seluruh analisis pasar, strategi, sinyal, risiko, alert, pembelajaran heuristik, dan portfolio lokal. | `market/market_analyzer.py`, `brain/trading_brain.py`, `trading/signal_engine.py`, `risk_manager.py` |
| `interfaces/` | Dua proses bot Telegram berbasis polling. | `telegram_bot.py` (7.103 baris), `market_bot.py` |
| `knowledge/` | Dokumen dan indeks vektor untuk RAG percakapan, bukan model trading. | `vector_store/index.faiss`, `index.pkl` |
| `memory/` | Memori dokumen/profil per pengguna. | `memory_manager.py`, `user_profile.py` |
| `scripts/` | Peluncur dashboard, deploy, backup dan monitor host. | `run_dashboard.py`, `deploy/deploy.sh` |
| `web/` | UI statis lama/dashboard BTC. | `index.html`, `app.js`, `btc/` |
| `docs/` | Dokumen desain, aturan AI, audit keamanan dan bukti runtime. | Lihat laporan 07 |
| `dashboard/` | Ditargetkan `api/server.py` sebagai lokasi SPA, tetapi kosong. | Tidak ada |

## Bahasa, framework, dan dependensi

- Bahasa utama: Python 3; interpreter host yang diperiksa adalah Python `3.10.12`.
- Antarmuka web: HTML/CSS/JavaScript tanpa `package.json`.
- API: FastAPI `0.135.1`, Uvicorn `0.41.0`, Pydantic `2.11.10`.
- Agen/LLM/RAG: CrewAI `1.10.1`, crewai-tools `1.10.1`, LangChain `1.2.10`, langchain-community `0.4.1`, OpenAI SDK `2.26.0`, FAISS CPU `1.13.2`, Sentence Transformers `5.2.3`, ChromaDB `1.1.1`.
- Bot dan HTTP: python-telegram-bot `22.6`, requests `2.32.5`, httpx `0.28.1`, aiohttp `3.13.3`.
- Penyimpanan/keamanan: psycopg2-binary `2.9.11`, Argon2-cffi `25.1.0`, PyJWT `2.11.0`, python-dotenv `1.1.1`.
- Scheduler: APScheduler `3.11.2` melalui `JobQueue` Telegram.
- Pengujian: `pytest>=7.0.0` di `requirements-dev.txt`.
- Tidak ditemukan `pyproject.toml`, `setup.py`, `package.json`, `go.mod`, `Dockerfile`, atau Compose.
- `numpy` diimpor langsung oleh `engine/market/dynamic_universe.py`, tetapi tidak dipin langsung; saat ini bergantung pada dependensi transitif.
- Virtualenv di repo mengalami drift: shebang `venv/bin/pip` menunjuk `/home/ubuntu/aliza-ai/venv/bin/python3`, bukan lokasi sekarang `/opt/aliza-ai`.

## Entry point dan cara berjalan

| Entry point | Cara menjalankan | Status saat audit |
|---|---|---|
| `interfaces/telegram_bot.py:main()` | systemd `aliza-telegram.service`, `venv/bin/python`, polling Telegram, `Restart=always` 5 detik | Aktif/enabled sejak 21-07-2026 07:38 WIB; sekitar 1,0 GB RAM saat diperiksa |
| `interfaces/market_bot.py:main()` | systemd `aliza-market.service`, membaca `.env` lalu `.env.market`, `Restart=always` 10 detik | Aktif/enabled sejak 02-06-2026; sekitar 40 MB |
| `scripts/run_dashboard.py` → `api.server:app` | systemd `aliza-dashboard.service`, Uvicorn loopback `127.0.0.1:8001` | Disabled/inactive; unit memakai akun khusus dan env `/etc/aliza-dashboard/dashboard.env` |
| `main.py` | `python main.py`; CLI interaktif CrewAI | Tidak tampak sebagai service |
| `api_server.py` | Uvicorn/API kompatibilitas lama | Tidak tampak berjalan; endpoint lama dinyatakan deprecated |

`aliza-market.service` berumur jauh lebih lama daripada source terbaru. Journal-nya masih menampilkan watchlist lama tujuh coin, sedangkan source kini mendefinisikan 21 coin. Ini bukti proses tersebut menjalankan kode lama yang sudah dimuat di memori. Override `IS_PRIMARY_DISPATCHER=false` membuatnya tidak mengirim dispatch utama, tetapi proses itu tetap melakukan polling pasar sendiri.

Tidak ditemukan PM2 maupun Docker terpasang/berjalan. Crontab pengguna memiliki backup harian `interfaces/telegram_bot.py` pukul 02:00; restart mingguan Aliza dikomentari. Ada job host lain di luar repo dan tidak dinilai sebagai komponen Aliza. Script deploy `scripts/deploy/deploy.sh` masih berpindah ke `/home/ubuntu/aliza-ai` serta merestart `aliza-api`—unit yang menunjuk repo lain—sehingga tidak cocok dengan deployment aktual `/opt/aliza-ai`.

## Catatan kepastian

- Isi unit systemd dan status runtime dapat dipastikan dari host saat audit.
- `TIDAK PASTI`: versi Python yang dipakai setiap proses persis sama dengan `python3 --version`; virtualenv tidak dieksekusi untuk query versi karena shebang tooling-nya drift dan audit menghindari tindakan runtime.
- `TIDAK PASTI`: service dashboard siap dinyalakan permanen. Bukti 16 Juli menunjukkan uji terakhir berhasil dengan peringatan, tetapi saat audit service memang disabled/inactive dan tidak ada journal baru.
