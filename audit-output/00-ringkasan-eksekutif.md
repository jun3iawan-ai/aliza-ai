# 00 — Ringkasan Eksekutif

> **Status: SUPERSEDED.** Snapshot pada 2026-07-21. Kondisi sistem terkini ada di `docs/README.md` dan report Fase 1–4 (`docs/reports/` — lihat Bagian 3). Jangan jadikan dokumen ini sebagai acuan status aktif.

## Apa itu Aliza AI saat ini

Aliza AI adalah platform analisis pasar crypto dan notifikasi Telegram berbasis Python. Sistem mengambil data terutama dari Binance Spot/Futures dan CoinGecko, memperkaya dengan fear-and-greed, makro, berita, whale, stablecoin, funding dan open interest, lalu membangun snapshot 21 coin. Dari snapshot itu sistem menghasilkan setup long/short rule-based, signal spot, alert khusus, serta laporan natural-language dengan CrewAI/OpenAI `gpt-4o-mini`.

Aliza bukan trading bot eksekusi. Tidak ada endpoint Binance order, order-management system, protective stop di exchange, trailing stop, atau rekonsiliasi posisi. “Entry”, “close”, position size dan leverage yang muncul adalah rekomendasi/pencatatan lokal. Dengan keadaan sekarang, klasifikasi yang tepat adalah **research/paper-signal system**, bukan sistem siap live trading.

Dua service utama aktif saat audit: Telegram dan market bot. Telegram menjalankan snapshot/scheduler utama; market bot menjalankan polling terpisah tetapi non-primary. Dashboard FastAPI telah memperoleh hardening JWT, Argon2, rate limit, limit eksekusi LLM, binding loopback dan systemd sandbox, namun tetap disabled/inactive. State tersebar di PostgreSQL, dua SQLite, JSON dan cache RAM per proses.

## Kemampuan utama

- Analisis 21 pair USDT dengan kline Binance `4h`/`1d`, RSI Wilder 14, MA20/50/200, support/resistance 20 close dan alignment multi-timeframe.
- Empat setup teknikal utama: `OVERSOLD BOUNCE`, `OVERBOUGHT REJECTION`, `PULLBACK LONG`, `PULLBACK SHORT`.
- Position sizing fixed-fractional dengan default risk 2%, allocation cap 30%, total-risk cap 6% dan maksimum tiga posisi lokal.
- Filter market regime, makro high-impact, RR, confidence dan dedup.
- Alert support/resistance, RSI, gerak besar, BTC smart signal, breakout, volume, funding, whale, berita dan kalender.
- Analisis spot/futures terjadwal dan on-demand melalui Telegram.
- Signal tracking SQLite dan dashboard statistik dasar.
- Hardening API/Telegram yang relatif baru dan jauh lebih baik daripada state audit awal 15 Juli.

## Kelemahan utama

Kelemahan terbesar adalah integritas signal dan evaluasinya. Auto-alert opportunity tidak mungkin aktif karena threshold 160 membaca score yang sudah dibatasi maksimum 100. Signal dicatat sebelum gateway membuktikan bahwa signal lolos risiko/makro/dedup dan berhasil dikirim. Tracker mengenali short hanya jika label persis `SHORT`, sehingga `PULLBACK SHORT` dan `OVERBOUGHT REJECTION` dinilai sebagai long. Data aktual berisi 10 signal: lima loss, lima open, nol win; winrate realized 0%, tetapi angka ini **tidak valid sebagai ukuran strategi** akibat sampel sangat kecil dan defect tracker tersebut.

Input indikator juga rentan. Ticker terbaru ditambahkan ke close Binance yang sudah memuat candle aktif, membuat kemungkinan duplikasi dan intrabar contamination. Ketika satu timeframe kurang, seri yang sama dapat digunakan sebagai `4h` sekaligus `1d`, sehingga alignment palsu. MA200 hanya mempunyai maksimum 100 kline. Support/resistance memakai close, bukan high/low. Snapshot parsial tetap dianggap valid—saat audit hanya 17 dari 21 coin berhasil—dan proses market yang belum restart sejak 2 Juni masih memakai watchlist source lama.

Jalur LLM menambah risiko berbeda: level generatif dapat ditulis ulang menjadi SL tepat 6% dan TP tepat 2R tanpa kembali mengecek struktur pasar, kemudian hasil parsing dicampur ke statistik deterministic. Tidak ada pemisahan provenance signal, fee, slippage, funding, high/low intrabar, atau backtest. “AI predictor” di repo pada dasarnya heuristik; tidak ada model trading terlatih atau artefak training. Indeks FAISS adalah RAG dokumen, bukan model arah harga.

Risk management yang ada cukup baik sebagai kalkulator, tetapi tidak menjadi proteksi modal karena tidak terhubung order exchange. Dua risk manager dan dua position sizer memakai default berbeda. Validator memakai nilai absolut dan tidak memastikan sisi SL/TP sesuai long/short. Drawdown/learning membaca JSON legacy, bukan outcome signal aktual.

## Status kelayakan

| Area | Penilaian |
|---|---|
| Data acquisition | Berfungsi, tetapi banyak fallback netral, duplikasi polling dan snapshot parsial |
| Strategi deterministic | Dapat menghasilkan setup, tetapi feature pipeline belum bebas bias |
| Futures | Analisis/rekomendasi saja; tidak ada margin/leverage/liquidation engine nyata |
| Risk management | Advisory dan terfragmentasi; belum enforceable |
| Tracking/winrate | Tidak dapat dipercaya sebelum defect arah/provenance/intrabar diperbaiki |
| Backtesting | Tidak ada |
| ML model | Tidak ada model trading terlatih |
| Operasional | Telegram aktif; market service stale; dashboard inactive |
| Live trading readiness | **Tidak siap** |

## Rekomendasi teratas untuk meningkatkan winrate dan validitasnya

Urutan berikut berdasarkan dampak terbesar, bukan kemudahan implementasi.

1. **Bangun pipeline evaluasi yang benar sebelum tuning strategi.** Satukan event signal dengan `signal_id`, strategy version, side, timeframe, source, timestamp candle tutup dan status dispatch. Catat hanya setelah gateway sukses. Perbaiki short semantics dan evaluasi TP/SL dengan OHLC beresolusi lebih rendah serta aturan konservatif jika keduanya tersentuh. Pisahkan statistik spot, futures, deterministic dan LLM.

2. **Hilangkan bias feature.** Hanya gunakan candle yang sudah tutup, jangan menambahkan ticker ke seri close, dan jangan pernah memakai seri sama sebagai dua timeframe. Ambil minimal 200 observasi bila benar-benar menyebut MA200. Support/resistance sebaiknya memakai high/low dan timestamp yang konsisten.

3. **Tambahkan backtest event-driven dan walk-forward.** Uji setiap setup secara terpisah di banyak regime, coin dan periode; masukkan fee, spread, slippage, funding dan latency. Bekukan parameter sebelum out-of-sample. Gunakan expectancy, profit factor, max drawdown dan confidence interval—bukan winrate saja.

4. **Perbaiki jalur signal kritis dan kontraknya.** Samakan skala score opportunity/auto-alert; tetapkan satu threshold RR per kelas strategi; tambah invariant arah long/short; buat integration test dari snapshot → kandidat → risk → dispatch → outcome. Jalur yang gagal harus fail-closed dan observable.

5. **Pisahkan LLM dari keputusan level trading.** LLM sebaiknya menjelaskan signal deterministic, bukan menciptakan atau menulis ulang entry/SL/TP. Jika rekomendasi LLM tetap dipertahankan, simpan sebagai eksperimen terpisah dan jangan gabungkan ke winrate produksi sampai lolos evaluasi identik.

6. **Optimalkan strategi per regime, bukan satu aturan untuk semua coin.** Oversold bounce harus diuji khusus range/reversal dengan konfirmasi volume/structure; pullback trend memakai retracement/ATR dan trend strength; futures short menambah funding/OI/liquidation yang dinormalisasi. Hentikan polling coin dengan data tidak memadai sampai lolos health/data-coverage gate.

7. **Satukan risk dan portfolio state.** Gunakan satu risk manager/sizer, satu sumber balance/position, dan satu ledger. Enforce max portfolio heat, daily loss limit, max drawdown, loss cooldown, correlation/exposure cluster dan leverage-adjusted liquidation buffer. Untuk live kelak, protective order harus berada di exchange.

8. **Perbaiki konteks market yang salah ukur.** Stablecoin “inflow” harus merupakan delta/flow, bukan total sirkulasi; samakan label producer/consumer. Normalisasi OI terhadap USD dan distribusi historis. Selaraskan threshold funding, volume dan cooldown. Propagasi status `UNKNOWN/STALE` alih-alih default netral 50.

9. **Konsolidasikan runtime.** Restart/decommission proses market stale setelah change-control, hindari dua polling snapshot, pindahkan cache/state ke satu service/shared store, tangani HTTP 429 dengan exponential backoff/jitter, dan buat readiness check yang menguji DB, snapshot completeness serta upstream.

10. **Pertahankan disiplin dokumentasi dan test.** Dokumentasikan status `implemented/disabled/planned`, universe aktual dan semua parameter. Tambah unit/property test indikator, strategy, risk, short outcome dan scheduler; simpan artefak backtest versioned. Dokumen keamanan Juli dapat menjadi pola evidence yang baik.

## Kesimpulan

Aliza AI mempunyai cakupan data, alert dan interface yang luas, serta fondasi keamanan dashboard yang membaik. Namun banyaknya modul tidak sama dengan edge trading yang terbukti. Saat ini tidak ada bukti backtest, model terlatih, atau winrate yang valid; justru terdapat beberapa bug yang secara langsung memblokir alert atau salah menilai outcome. Prioritas tertinggi bukan menambah indikator/coin, melainkan membuat data candle, kontrak signal, risk semantics dan evaluasi outcome dapat dipercaya. Setelah itu barulah optimasi spot dan futures dapat dilakukan berdasarkan evidence out-of-sample.

Detail bukti dapat diverifikasi pada laporan 01–07 di folder ini; setiap pembahasan strategi mencantumkan path dan nama fungsi terkait.
