# AUDIT — Mekanisme Evaluasi & Pembelajaran dari Hasil Sinyal

**Tanggal audit:** 25 Juli 2026
**Branch:** `main` (read-only — tidak ada file/config yang diubah, tidak ada commit, tidak ada restart service)
**Scope:** `/opt/aliza-ai`

---

## Ringkasan Eksekutif

Pemahaman awal user **secara umum akurat, dengan satu koreksi penting**:

1. **Evaluasi/pencatatan hasil sinyal ADA dan berjalan otomatis** — `signal_check_job` mengecek sinyal OPEN setiap 10 menit, meng-update status WIN/LOSS/EXPIRED di tabel `signal_tracking`, dan statistiknya bisa dibaca lewat perintah manual `/signal_stats` (alias `/stats`) dan `/shadow_stats`. Tidak ada dashboard/API endpoint lain yang membacanya.

2. **KOREKSI PENTING atas pemahaman awal:** ada satu mekanisme kode yang **secara teknis** membaca "hasil trading" dan otomatis menyesuaikan `confidence` sinyal berikutnya — `engine/learning/confidence_adjuster.py`, dipanggil dari `TradingBrain.analyze()` yang merupakan jalur produksi. **Namun mekanisme ini secara fungsional mati (inert)**: sumber datanya (`data/trade_history.json`) hanya berisi 2 baris data seed/contoh dari Maret 2025 dan **tidak pernah ditulis oleh kode manapun yang berjalan live** — fungsi penulisnya (`record_trade_open`/`record_trade_close`) tidak dipanggil dari mana pun di luar definisinya sendiri. Jadi secara *desain* ada "learning loop", tapi secara *praktik* loop itu tidak pernah menerima data baru dari sinyal live sejak deploy — ia hanya mengulang-ulang keputusan berdasarkan 2 trade contoh yang sama.

3. Ada juga **circuit breaker loss-streak** (`engine/portfolio/drawdown_protector.py`, ambang 3 loss beruntun) yang membaca sumber data yang sama (`trade_history.json`) — sehingga **sama-sama inert** untuk alasan yang sama. Circuit breaker ini pun hanya menggerbangi perintah manual `/entry` (konfirmasi eksekusi trade oleh satu user untuk position sizing), **bukan** jalur broadcast sinyal otomatis ke seluruh subscriber.

4. **Tidak ada** mekanisme otomatis yang menyesuaikan SL/TP/threshold strategi produksi berdasarkan hasil live `signal_tracking` (SQLite). Circuit breaker lain yang ada di kode (`CIRCUIT_BREAKER_ACTIVE` di `market_snapshot_engine.py`, dan `COIN_FAIL_THRESHOLD`/`COIN_SUSPEND_HOURS` di `market_universe.py`) murni berbasis **kualitas/ketersediaan data pasar** (snapshot stale, gagal fetch harga), bukan berbasis hasil trading/winrate — sesuai dugaan awal user.

5. Backtest engine (`backtest/`) dan shadow mode E3 (`engine/shadow/e3_shadow.py`) berjalan sesuai pemahaman sebelumnya: **manual/on-demand**, tidak dijadwalkan di crontab, dan kriteria promosi shadow→produksi hanya didokumentasikan di `FASE4_REPORT.md` — **tidak ada enforcement di kode**. Shadow mode saat ini **aktif dan dispatch ke Telegram** (`SHADOW_E3_ENABLED=true`, `SHADOW_E3_DISPATCH=true` di `.env` produksi), baru mulai mengumpulkan outcome sejak 24 Juli 2026 (3 outcome tercatat: 1 LOSS, 2 OPEN) — jauh di bawah ambang promosi (≥60 outcome atau ≥6 minggu).

**Kesimpulan singkat:** seluruh penyesuaian strategi yang *benar-benar berjalan* (SL/TP, threshold RSI, filter regime) tetap murni manual/human-in-the-loop, lewat siklus backtest → review → keputusan produk → shadow test → promosi manual. Satu-satunya kode yang *berniat* melakukan otomatisasi (`confidence_adjuster` + `drawdown_protector`) sudah ditulis dan terpasang di jalur eksekusi, tapi tidak berfungsi karena pipa datanya terputus (dead write-path) — sehingga hasilnya sama seperti tidak ada sama sekali, hanya dengan catatan berbeda: ini bukan "tidak pernah dibangun", melainkan "dibangun tapi tidak tersambung ke data live".

---

## 1. Evaluasi/Pencatatan Hasil Sinyal

### 1.1 `signal_check_job` — job pengecekan outcome

- Dijadwalkan di [interfaces/telegram_bot.py:7216-7222](../../../interfaces/telegram_bot.py#L7216-L7222):
  ```python
  app.job_queue.run_repeating(
      signal_check_job,
      interval=600,
      first=150,
      name="signal_checker",
  )
  logging.info("Signal checker job scheduled (every 600s, first in 150s).")
  ```
  **Interval: setiap 600 detik (10 menit)**, pertama kali jalan 150 detik setelah start.

- Implementasi job di [interfaces/telegram_bot.py:6629-6650](../../../interfaces/telegram_bot.py#L6629-L6650): memanggil `check_open_signals()`, lalu untuk setiap sinyal yang baru CLOSE dengan status `WIN`/`LOSS` (bukan `EXPIRED`), mengirim notifikasi lewat `safe_dispatch`.

- Logika penentuan outcome ada di [engine/trading/signal_tracker.py:367-448](../../../engine/trading/signal_tracker.py#L367-L448) (`check_open_signals`) dan [engine/trading/signal_tracker.py:338-364](../../../engine/trading/signal_tracker.py#L338-L364) (`_evaluate_outcome`):
  - Mengambil candle 5-menit dari Binance sejak `created_at` sinyal ([signal_tracker.py:261-327](../../../engine/trading/signal_tracker.py#L261-L327), `_fetch_5m_klines`).
  - **Same-bar handling** — jika TP dan SL sama-sama tersentuh dalam candle 5m yang sama, urutan tak diketahui, sehingga **hasil selalu dikonservatifkan sebagai LOSS di harga SL** ([signal_tracker.py:356-361](../../../engine/trading/signal_tracker.py#L356-L361)):
    ```python
    # Jika dua level tersentuh dalam candle yang sama, urutan tidak diketahui:
    # hasil konservatif selalu LOSS pada harga stop.
    if tp_hit and sl_hit:
        return "LOSS", sl, _net_pnl_pct(side, entry, sl)
    ```
  - Jika dalam 7 hari sejak sinyal tidak ada TP/SL yang tersentuh, status diubah menjadi `EXPIRED` ([signal_tracker.py:410-415](../../../engine/trading/signal_tracker.py#L410-L415)).
  - PnL dihitung net setelah fee round-trip 0,2% ([signal_tracker.py:22](../../../engine/trading/signal_tracker.py#L22), `ROUND_TRIP_FEE_PCT`; `_net_pnl_pct` di [signal_tracker.py:330-335](../../../engine/trading/signal_tracker.py#L330-L335)).

### 1.2 Daftar lengkap pembaca `signal_tracking` / penghasil statistik

Hasil grep menyeluruh (`grep -rn "get_signal_stats(" .` dan `grep -rn "check_open_signals(" .`, dikecualikan `__pycache__` dan file definisi):

| Pemanggil | Lokasi | Jenis |
|---|---|---|
| `signal_stats_command` (`/signal_stats`, alias `/stats`) | [interfaces/telegram_bot.py:6653-6708](../../../interfaces/telegram_bot.py#L6653-L6708), registrasi di [telegram_bot.py:7087-7088](../../../interfaces/telegram_bot.py#L7087-L7088) | Perintah Telegram manual — user harus mengetik `/signal_stats` atau `/stats` |
| `shadow_stats_command` (`/shadow_stats`) | [interfaces/telegram_bot.py:6712-6730](../../../interfaces/telegram_bot.py#L6712-L6730), registrasi di [telegram_bot.py:7089](../../../interfaces/telegram_bot.py#L7089) | Perintah Telegram manual, filter `source='shadow_e3'` |
| `tests/test_fase1.py`, `tests/test_fase4.py` | test suite | Hanya untuk pengujian otomatis (pytest), tidak berjalan di produksi |

**Bukti negatif:** `grep -rln "signal_tracking\|get_signal_stats\|win_rate\|winrate" api/ dashboard/ interfaces/*.py` (dikecualikan `telegram_bot.py`) — **hasil kosong**. Tidak ada endpoint API (`api/*.py`) atau dashboard yang membaca tabel `signal_tracking` atau statistiknya. Statistik hanya bisa dilihat lewat dua perintah Telegram manual di atas.

---

## 2. Loop Otomatis yang Menyesuaikan Strategi Berdasarkan Hasil?

### 2.1 Temuan: mekanisme ADA di kode, tapi mati secara fungsional

Ditemukan direktori `engine/learning/` berisi 4 modul yang **secara nama dan desain** persis menjawab pertanyaan audit ini:

| File | Fungsi |
|---|---|
| [engine/learning/trade_history_tracker.py](../../../engine/learning/trade_history_tracker.py) | Baca/tulis `data/trade_history.json` — `record_trade_open()` ([:44-62](../../../engine/learning/trade_history_tracker.py#L44-L62)), `record_trade_close()` ([:65-87](../../../engine/learning/trade_history_tracker.py#L65-L87)), `get_closed_history()` ([:90-92](../../../engine/learning/trade_history_tracker.py#L90-L92)) |
| [engine/learning/strategy_performance.py](../../../engine/learning/strategy_performance.py) | `analyze_strategy_performance()` ([:10-59](../../../engine/learning/strategy_performance.py#L10-L59)) — hitung winrate & avg RR per setup dari closed trades |
| [engine/learning/learning_engine.py](../../../engine/learning/learning_engine.py) | `get_strategy_stats()` ([:21-40](../../../engine/learning/learning_engine.py#L21-L40)) — jembatan antara trade history dan `TradingBrain` |
| [engine/learning/confidence_adjuster.py](../../../engine/learning/confidence_adjuster.py) | `adjust_confidence()` ([:11-48](../../../engine/learning/confidence_adjuster.py#L11-L48)) — **aturan eksplisit:** `winrate > 0.65 → confidence +5`; `winrate < 0.40 → confidence -10` ([:40-43](../../../engine/learning/confidence_adjuster.py#L40-L43)) |

Modul-modul ini **benar-benar dipanggil dari jalur produksi**, bukan kode mati/tak terpakai:

```python
# engine/brain/trading_brain.py:26-34
try:
    from engine.learning.confidence_adjuster import adjust_confidence
except ImportError:
    adjust_confidence = None
try:
    from engine.learning.learning_engine import get_strategy_stats
except ImportError:
    get_strategy_stats = None
```

```python
# engine/brain/trading_brain.py:293-299
confidence = _confidence_from_rr(rr, rsi)
if adjust_confidence is not None and get_strategy_stats is not None:
    try:
        strategy_stats = get_strategy_stats()
        confidence = adjust_confidence(setup, confidence, strategy_stats)
    except Exception:
        pass
```

`TradingBrain.analyze()` dipanggil dari jalur live: `engine/market/market_analyzer.py:424-425` (dipakai oleh `engine/market_signal.py`, `api/market.py`, `interfaces/market_bot.py`, dll — konfirmasi lewat `grep -rln "market_analyzer" .`), dan juga dari `engine/shadow/e3_shadow.py:106`.

### 2.2 Mengapa mekanisme ini tidak "belajar" dari hasil live

Sumber data `get_strategy_stats()` adalah `data/trade_history.json` (path di [trade_history_tracker.py:13](../../../engine/learning/trade_history_tracker.py#L13), `HISTORY_PATH = "data/trade_history.json"`). File ini di server:

```
-rw-rw---- 1 ubuntu aliza-dashboard 603 Mar 13 21:29 /opt/aliza-ai/data/trade_history.json
```

**Tidak diubah sejak 13 Maret 2025**, dan isinya hanya 2 trade contoh (BTC WIN, ETH LOSS) — jelas data seed/testing, bukan hasil live.

Pencarian menyeluruh untuk pemanggil fungsi *penulis* (`record_trade_open`, `record_trade_close`):

```
grep -rn "record_trade_open\|record_trade_close" --include="*.py" .
→ hanya definisi fungsi di engine/learning/trade_history_tracker.py, TIDAK ADA pemanggil lain di seluruh repo.
```

**Bukti negatif eksplisit:** tidak ada satu pun baris kode — di `signal_tracker.py`, `telegram_bot.py`, atau modul manapun — yang menjembatani hasil WIN/LOSS dari `signal_tracking` (SQLite, sumber kebenaran hasil live sejak Fase 1) ke `trade_history.json` (sumber data untuk learning engine). Kedua sistem pencatatan berjalan **paralel dan tidak pernah bertemu**.

Konsekuensinya: setiap kali `TradingBrain.analyze()` jalan, `get_strategy_stats()` selalu mengembalikan hasil analisis dari 2 trade yang sama (Maret 2025), dan `adjust_confidence()` mengambil jalur early-return jika `total_trades < 1` untuk setup yang tidak ada di data itu ([confidence_adjuster.py:28-29](../../../engine/learning/confidence_adjuster.py#L28-L29)), atau menerapkan penyesuaian yang identik berulang-ulang untuk setup `PULLBACK LONG` (satu-satunya setup dengan data). **Tidak ada penyesuaian berdasarkan performa sinyal live** — confidence yang keluar hari ini secara efektif sama seperti yang akan keluar tanpa modul ini sama sekali (untuk semua setup selain "PULLBACK LONG", dan bahkan untuk "PULLBACK LONG" nilainya statis/beku).

**Kesimpulan poin 2:** Bukan "TIDAK ADA sama sekali" secara literal — ada kode yang berniat melakukan ini. Tapi secara operasional statusnya setara dengan tidak ada, karena data input-nya beku sejak lebih dari setahun dan tidak pernah diisi oleh hasil sinyal live. Ini **gap tersembunyi** yang relevan untuk pengembangan: infrastrukturnya sudah 80% jadi (analisis, aturan penyesuaian, titik integrasi di TradingBrain) — yang hilang hanya satu jembatan: menulis outcome dari `signal_tracking`/`check_open_signals()` ke `trade_history.json` (atau mengganti sumber data `get_strategy_stats()` agar membaca SQLite langsung).

### 2.3 COIN_FAIL_THRESHOLD / COIN_SUSPEND_HOURS — beda cakupan, dikonfirmasi

Ditemukan di [engine/market/market_universe.py](../../../engine/market/market_universe.py):
```python
DEFAULT_COIN_FAIL_THRESHOLD = 10   # :30
DEFAULT_COIN_SUSPEND_HOURS = 6.0   # :31
```
`record_coin_validation()` ([:73-95](../../../engine/market/market_universe.py#L73-L95)) menaikkan counter kegagalan **validasi data pasar** (`valid` param — dipanggil saat fetch/parse harga gagal, bukan saat trade rugi), dan men-suspend coin dari polling selama `COIN_SUSPEND_HOURS` jika gagal berturut-turut ≥ `COIN_FAIL_THRESHOLD`. Ini **auto-suspend berbasis kegagalan fetch data**, sama sekali terpisah dari hasil trading/winrate — **dikonfirmasi sesuai dugaan awal user**, bukan bentuk "belajar dari hasil sinyal".

---

## 3. Circuit Breaker / Early Warning Berbasis Performa

### 3.1 Drawdown protector — loss-streak breaker (ADA, tapi terbatas cakupan dan inert)

[engine/portfolio/drawdown_protector.py:1-44](../../../engine/portfolio/drawdown_protector.py):
```python
LOSS_STREAK_THRESHOLD = 3  # :14

def check_drawdown():
    ...
    for t in reversed(closed):
        if result == "LOSS":
            streak += 1
        else:
            break
    if streak >= LOSS_STREAK_THRESHOLD:
        return {"trading_allowed": False, "loss_streak": streak}  # :39-40
```

Ini **benar-benar sebuah circuit breaker berbasis performa** (loss streak ≥ 3 → blokir). Dipanggil dari [engine/portfolio/portfolio_ai_engine.py:49-53](../../../engine/portfolio/portfolio_ai_engine.py#L49-L53) di dalam `evaluate_trade()`, yang pada gilirannya dipanggil dari perintah **`/entry`** di Telegram bot ([interfaces/telegram_bot.py:1291-1299](../../../interfaces/telegram_bot.py#L1291-L1299), fungsi `entry()` didefinisikan di [telegram_bot.py:1240](../../../interfaces/telegram_bot.py#L1240), diregistrasi di [telegram_bot.py:7056](../../../interfaces/telegram_bot.py#L7056)).

**Cakupan penting untuk diluruskan:**
- `/entry` adalah perintah **manual satu-user** untuk mengonfirmasi eksekusi/position-sizing sebuah trade (bukan jalur broadcast sinyal otomatis ke semua subscriber). Jadi breaker ini, bila aktif, hanya menolak konfirmasi manual user tersebut dengan pesan `"Trading ditangguhkan: loss streak ≥ 3"` ([portfolio_ai_engine.py:52](../../../engine/portfolio/portfolio_ai_engine.py#L52)) — **tidak menghentikan/mengubah pengiriman sinyal otomatis ke channel/subscriber**.
- Sama seperti confidence_adjuster, breaker ini membaca `get_closed_history()` dari `engine.learning.trade_history_tracker` — **sumber data yang sama, yang beku sejak Maret 2025**. Karena tidak pernah terisi data live, `streak` yang dihitung selalu berdasarkan 2 trade seed tersebut (1 WIN, 1 LOSS → streak=0 atau 1, tidak pernah mencapai 3 dari data ini). **Breaker ini secara praktik tidak pernah terpicu oleh hasil trading live.**

### 3.2 Tidak ada early-warning winrate berkelanjutan ke user

Pencarian menyeluruh untuk mekanisme monitoring winrate/performa berkelanjutan yang mengirim peringatan proaktif (bukan atas permintaan `/command`):
```
grep -rniE "circuit.?breaker|losing.?streak|loss.?streak|winrate.*threshold" --include="*.py" .
```
Hasil relevan hanya dua kelompok:
1. `drawdown_protector.py` / `portfolio_ai_engine.py` (dibahas di atas — cakupan manual `/entry`, inert).
2. `CIRCUIT_BREAKER_ACTIVE` di [engine/market/market_snapshot_engine.py:60-61,389-439](../../../engine/market/market_snapshot_engine.py#L389-L439) dan dipakai di [engine/monitoring/market_monitor.py:64-65](../../../engine/monitoring/market_monitor.py#L64-L65), [interfaces/market_bot.py:52-53](../../../interfaces/market_bot.py#L52-L53), [interfaces/telegram_bot.py:283-285](../../../interfaces/telegram_bot.py#L283-L285) — breaker ini murni berbasis **snapshot pasar stale/invalid** (`SNAPSHOT_INVALID_COUNT >= CIRCUIT_BREAKER_THRESHOLD`, env `CB_THRESHOLD` default 10), **bukan performa trading**.

`engine/monitoring/system_monitor.py` (`check_system_health()`, [:17-59](../../../engine/monitoring/system_monitor.py#L17-L59), dipanggil di [telegram_bot.py:6967](../../../interfaces/telegram_bot.py#L6967)) juga murni cek kesehatan sistem (jumlah coin di snapshot, staleness timestamp, keberadaan data BTC) — **bukan winrate**.

`engine/brain/signal_quality_engine.py` dan `engine/brain/opportunity_ranker.py` menghitung skor kualitas sinyal (Trade Score, ranking top-3 opportunity), tapi **seluruh bobotnya statis/hardcoded** berdasarkan atribut sinyal saat itu (RR, confidence, trend alignment, regime, whale pressure) — **tidak ada input historical winrate** di dalamnya (dikonfirmasi baca penuh kedua file, tidak ada pemanggilan ke `signal_tracking`/`trade_history`).

**Kesimpulan poin 3:** Tidak ada early-warning winrate/losing-streak yang aktif memantau performa live dan mengirim notifikasi proaktif ke user. Satu-satunya breaker berbasis performa (`drawdown_protector`) ada di kode tapi (a) cakupannya sempit — hanya menggerbangi perintah manual `/entry`, bukan sinyal broadcast, dan (b) inert karena sumber datanya beku.

---

## 4. Proses Backtest & Promosi (Mekanisme Manual)

### 4.1 Backtest engine — dikonfirmasi manual/on-demand

Struktur `backtest/`: `run_backtest.py`, `run_experiments.py`, `simulator.py`, `data_loader.py`, `metrics.py`, `robustness.py`, `costs.py`.

- **Tidak dijadwalkan** — dicek `crontab -l` di server: tidak ada entri yang memanggil `backtest.run_backtest` atau `backtest.run_experiments`. Satu-satunya referensi command line ada di dokumentasi manual: [docs/architecture/testing.md:42](../../../docs/architecture/testing.md#L42):
  ```
  venv/bin/python -m backtest.run_backtest \
  ```
  — perintah CLI yang harus dijalankan manusia secara manual.
- `AlizaAI-Crypto/01-hasil-audit-codex/REPO_CLEANUP_REPORT.md:220` bahkan menandai file ini dengan catatan eksplisit **"JANGAN SENTUH"** (CLI Fase 3), memperkuat statusnya sebagai tooling investigasi manual, bukan bagian dari runtime otomatis.
- `backtest/run_experiments.py:94` menulis dict `criteria` (`expectancy_pct_gt`, `profit_factor_gt`, `n_gte`, `coin_profit_share_lt`) ke `manifest.json` — **ini hanya metadata pelaporan** untuk dibaca manusia saat review hasil eksperimen; tidak ada kode yang membaca `manifest.json` untuk mengambil keputusan otomatis (dikonfirmasi: tidak ada pemanggil `manifest.json` di luar penulisannya sendiri).
- Hasil backtest disimpan sebagai dokumen: `ROBUSTNESS_RESULTS.md` (holdout 21 Jan–21 Jul 2026, bootstrap expectancy, stress test biaya, rolling walk-forward — lihat isi lengkap di [AlizaAI-Crypto/01-hasil-audit-codex/ROBUSTNESS_RESULTS.md](../../../AlizaAI-Crypto/01-hasil-audit-codex/ROBUSTNESS_RESULTS.md)) dan `FASE2_REPORT.md`/`FASE3_REPORT.md` — **masih akurat** sebagai catatan historis proses Fase 2-3, dan dikonfirmasi tidak ada kode produksi yang membaca file-file `.md` ini untuk mengubah parameter.

**Konfirmasi:** dijalankan manual/on-demand oleh manusia (developer/Codex atas instruksi user), trigger-nya adalah command CLI eksplisit, hasil disimpan di file `.md`/`.json` untuk direview manusia — sama sekali tidak ada jalur otomatis dari hasil backtest ke parameter produksi.

### 4.2 Shadow mode (Fase 4) — status kode dan aktivasi saat ini

- Flag dikonfirmasi di [engine/shadow/e3_shadow.py:31-36](../../../engine/shadow/e3_shadow.py#L31-L36):
  ```python
  def enabled() -> bool:
      return os.getenv("SHADOW_E3_ENABLED", "false")...
  def dispatch_enabled() -> bool:
      return os.getenv("SHADOW_E3_DISPATCH", "false")...
  ```
- **Status saat ini di `.env` produksi (dicek nama variabel saja, bukan isi file penuh):** `SHADOW_E3_ENABLED=true`, `SHADOW_E3_DISPATCH=true` — **shadow mode sedang aktif dan mengirim pesan ke Telegram** dengan header `"🧪 SHADOW/RISET — BUKAN SINYAL PRODUKSI"` ([e3_shadow.py:149-157](../../../engine/shadow/e3_shadow.py#L149-L157)).
- `source='shadow_e3'` terpisah dari statistik produksi, dikonfirmasi di [engine/trading/signal_tracker.py:477-481](../../../engine/trading/signal_tracker.py#L477-L481):
  ```python
  elif source_filter == "deterministic":
      # Legacy/LLM tetap terlihat pada breakdown historis Fase 1, tetapi
      # shadow tidak boleh mencemari statistik produksi default.
      source_clause = "WHERE IFNULL(source, '') != 'shadow_e3'"
  ```
- Query langsung ke `data/aliza.db` (read-only, `SELECT source, status, COUNT(*) ... GROUP BY`) pada saat audit menunjukkan shadow baru mengumpulkan **3 outcome** (1 LOSS, 2 OPEN) dengan `signal_time` antara 2026-07-24 dan 2026-07-25 — konsisten dengan `FASE4_REPORT.md` yang menyebutkan observasi disarankan mulai dan berakhir sekitar **1 September 2026**.

### 4.3 Kriteria promosi — murni dokumentasi, tidak ada enforcement di kode

[AlizaAI-Crypto/01-hasil-audit-codex/FASE4_REPORT.md](../../../AlizaAI-Crypto/01-hasil-audit-codex/FASE4_REPORT.md), bagian "Kriteria promosi":
> "Promosi shadow → produksi hanya bila setelah ≥6 minggu atau ≥60 outcome selesai (mana yang lebih lama): expectancy >+0,3%/trade, PF>1,2, batas bawah bootstrap CI >−0,1%, tidak ada coin >50% profit, dan verdict Bagian A bukan RAPUH. **Keputusan tetap pada user; fase ini tidak mengubah runtime produksi.**"

Pencarian kode untuk angka-angka ini (`0.3`, `1.2`, `60`, `expectancy`, `promot`) di luar dokumentasi — **tidak ditemukan enforcement**. Tidak ada fungsi yang membaca `/shadow_stats`/`get_signal_stats(source="shadow_e3")` lalu secara otomatis mengubah `SHADOW_E3_ENABLED`/`SHADOW_E3_DISPATCH` atau memindahkan setup shadow ke jalur produksi. Keputusan promosi 100% berada di luar kode — murni keputusan manual user berdasarkan angka yang dibaca lewat `/shadow_stats`.

---

## 5. Kesimpulan & Gap Konkret

### Sudah ada (evaluasi/pencatatan)
- Pencatatan otomatis setiap sinyal ke `signal_tracking` (SQLite) saat dispatch berhasil.
- Job otomatis setiap 10 menit yang menutup sinyal OPEN jadi WIN/LOSS/EXPIRED, dengan same-bar conservative-LOSS dan time-stop 7 hari.
- Statistik on-demand lewat `/signal_stats` dan `/shadow_stats` (Telegram, manual).
- Shadow mode E3 aktif berjalan paralel dengan tracking terpisah, siap dipakai sebagai basis keputusan promosi manual di masa depan.

### Ada di kode tapi TIDAK berfungsi secara praktik (temuan utama audit ini)
- `engine/learning/confidence_adjuster.py` + `learning_engine.py` — dipanggil di jalur produksi (`TradingBrain.analyze()`), tapi sumber datanya (`data/trade_history.json`) beku sejak Maret 2025 dan tidak pernah diisi hasil live → efeknya nol/statis.
- `engine/portfolio/drawdown_protector.py` — circuit breaker loss-streak ≥3 yang valid secara logika, tapi (a) hanya menggerbangi perintah manual `/entry`, bukan broadcast sinyal, dan (b) sama-sama membaca data beku yang sama sehingga tidak pernah terpicu oleh performa live.

### Belum ada sama sekali
- Tidak ada jalur kode yang membaca hasil `signal_tracking` (SQLite, sumber kebenaran live) lalu secara otomatis mengubah SL/TP/threshold/filter setup untuk sinyal berikutnya.
- Tidak ada scheduled job yang me-re-run backtest atau memperbarui parameter produksi secara otomatis.
- Tidak ada dashboard/API yang mengekspos statistik sinyal untuk dipakai keputusan otomatis apa pun — hanya dua perintah Telegram manual.
- Tidak ada enforcement kode atas kriteria promosi shadow→produksi; murni manual.

### Gap konkret sebagai kandidat pengembangan berikutnya
1. **Sambungkan `signal_tracking` (SQLite, live) sebagai sumber data untuk `get_strategy_stats()`**, menggantikan `trade_history.json` yang beku — ini akan langsung "menghidupkan" `confidence_adjuster` dan `drawdown_protector` yang sudah tertanam di jalur produksi tanpa perlu menulis kode baru dari nol.
2. Jika `drawdown_protector` ingin benar-benar menjadi circuit breaker sinyal (bukan hanya perintah `/entry`), perlu jalur baru yang menggerbangi `_dispatch_and_record_deterministic_signal`/broadcast job, bukan hanya `portfolio_ai_engine.evaluate_trade`.
3. Job berkala yang membaca `get_signal_stats()`/`get_signal_stats(source="shadow_e3")` dan mengirim ringkasan mingguan proaktif ke user (early warning), bukan hanya menunggu `/signal_stats` diketik manual.
4. Proses formal (bisa tetap manual, tapi terdokumentasi sebagai checklist/script) untuk mengevaluasi kriteria promosi shadow→produksi di `FASE4_REPORT.md` begitu ambang ≥60 outcome/≥6 minggu tercapai (diperkirakan sekitar 1 September 2026 berdasarkan tanggal aktivasi).

---

## Lampiran — Perintah Pencarian yang Digunakan (untuk verifikasi ulang)

```bash
grep -rn "signal_tracking" --include="*.py" .
grep -rn "adjust_confidence\|get_strategy_stats\|record_trade_open\|record_trade_close" --include="*.py" .
grep -rniE "auto.?(disable|adjust|tune|suspend)|circuit.?breaker|losing.?streak|loss.?streak|winrate.*threshold|auto_promote|re-?run backtest|retrain|self.?(adjust|tune|learn)" --include="*.py" .
grep -rn "COIN_FAIL_THRESHOLD|COIN_SUSPEND_HOURS" --include="*.py" .
grep -rn "get_signal_stats(\|check_open_signals(" --include="*.py" .
grep -rln "signal_tracking\|get_signal_stats\|win_rate\|winrate" api/ dashboard/ interfaces/*.py
crontab -l
sqlite3 data/aliza.db "SELECT source, status, COUNT(*) FROM signal_tracking GROUP BY source, status;"
```
