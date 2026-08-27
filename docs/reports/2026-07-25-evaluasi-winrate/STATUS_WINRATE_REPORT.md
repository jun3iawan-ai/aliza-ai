# Laporan Status Winrate Sinyal (Read-Only)

Branch: `main` (read-only — tidak ada kode/config/DB yang diubah, tidak ada commit, service tidak di-restart).

Tanggal kerja: 2026-07-25, ~08:05 WIB. Sumber: `data/aliza.db` tabel `signal_tracking` (query SQL langsung + pemanggilan `engine.trading.signal_tracker.get_signal_stats()` langsung dari Python, tanpa Telegram).

---

## Ringkasan eksekutif

**Belum ada satupun WIN sejak Fase 1 deploy (21 Juli 2026, 09:08:51 WIB) — di semua source (`deterministic`, `llm`, `shadow_e3`), tanpa kecuali.**

| Source | Total | OPEN | WIN | LOSS | Winrate mentah |
|---|---|---|---|---|---|
| `deterministic` (produksi resmi) | 2 | 1 | 0 | 1 | 0% (N=1 closed — **BELUM CUKUP DATA**) |
| `llm` (SPOT/advisory) | 8 | 8 | 0 | 0 | — (0 closed) |
| `shadow_e3` (riset) | 2 | 2 | 0 | 0 | — (0 closed) |
| **Total post-Fase1** | **12** | **11** | **0** | **1** | — |

- Winrate resmi produksi (`source='deterministic'`, sesuai default `get_signal_stats()`): **0/(0+1) = 0%, tapi N=1 closed outcome — jauh di bawah ambang bermakna (~20-30) → BELUM CUKUP DATA untuk winrate bermakna.** Satu LOSS bukan tren, hanya satu titik data.
- 11 dari 12 sinyal post-Fase1 masih `OPEN` — belum ada outcome sama sekali untuk sebagian besar sampel.
- Tidak ada sinyal yang "macet" melebihi batas expiry yang berlaku di kode saat ini (7 hari, lihat bagian Time-Stop) — sinyal tertua post-Fase1 baru berumur ~84 jam (3,5 hari).
- **Temuan tambahan (di luar pertanyaan literal, tapi relevan)**: time-stop live yang berlaku untuk *semua* source (termasuk `shadow_e3`) adalah **7 hari flat** (`engine/trading/signal_tracker.py:412`), BUKAN 3 hari seperti asumsi backtest E3 yang divalidasi (`E3 3×ATR/3 hari`, lihat `ROBUSTNESS_RESULTS.md`/`FASE3_REPORT.md`). Ini bukan bug yang bikin sinyal macet, tapi berarti outcome live shadow_e3 ke depan **tidak akan 1:1 sebanding** dengan angka backtest yang jadi dasar rekomendasi Fase 4, karena tracker live memberi TP/SL waktu >2× lebih lama untuk kena sebelum di-expire. Dicatat sebagai temuan untuk ditindaklanjuti terpisah kalau relevan — tidak diperbaiki di sini (read-only).

---

## 1-2. Query & data mentah per source/status (created_at setelah Fase 1 deploy)

Fase 1 deploy: commit `cdaf551e` (`Merge branch 'fix/fase1-signal-integrity'`), `2026-07-21 09:08:51 +0700` = `2026-07-21 02:08:51 UTC`. `created_at` di tabel disimpan UTC (`datetime('now')` SQLite, dikonfirmasi cocok dengan `signal_time` WIB per baris).

```sql
SELECT source, status, COUNT(*) AS n
FROM signal_tracking
WHERE created_at > '2026-07-21 02:08:51'
GROUP BY source, status
ORDER BY source, status;
```

```
source         status  n
-------------  ------  -
deterministic  LOSS    1
deterministic  OPEN    1
llm            OPEN    8
shadow_e3      OPEN    2
```

Total baris post-Fase1: **12** (`SELECT COUNT(*) ... WHERE created_at > '2026-07-21 02:08:51'` → 12).

Sanity check — tidak ada kebocoran source lintas fase (baris `legacy` yang nyasar post-deploy, atau baris `deterministic`/`llm`/`shadow_e3` yang nyasar pre-deploy):

```sql
SELECT id, source, created_at
FROM signal_tracking
WHERE (source != 'legacy' AND created_at <= '2026-07-21 02:08:51')
   OR (source = 'legacy' AND created_at > '2026-07-21 02:08:51');
```
→ **0 baris** (kosong). Pemisahan fase bersih.

### Detail seluruh 12 baris post-Fase1 (untuk verifikasi manual)

```sql
SELECT id, coin, setup, side, source, status, entry_price, sl_price, tp_price,
       close_price, pnl_pct, signal_time, created_at, close_time
FROM signal_tracking
WHERE created_at > '2026-07-21 02:08:51'
ORDER BY created_at;
```

| id | coin | setup | side | source | status | entry | sl | tp | close | pnl% | signal_time | created_at (UTC) | close_time |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 25 | BTC | LONG | LONG | llm | OPEN | 66000.0 | 62040.0 | 73920.0 | — | — | 2026-07-21 20:01:03 WIB | 2026-07-21 13:01:03 | — |
| 26 | ETH | LONG | LONG | llm | OPEN | 1900.0 | 1795.0 | 2110.0 | — | — | 2026-07-21 20:01:03 WIB | 2026-07-21 13:01:03 | — |
| 27 | SOL | LONG | LONG | llm | OPEN | 77.0 | 73.0 | 85.0 | — | — | 2026-07-21 20:01:03 WIB | 2026-07-21 13:01:03 | — |
| 28 | XRP | LONG | LONG | llm | OPEN | 1.1 | 1.03 | 1.24 | — | — | 2026-07-21 20:01:03 WIB | 2026-07-21 13:01:03 | — |
| 29 | BTC | SPOT | LONG | llm | OPEN | 64280.01 | 60000.0 | 66676.54 | — | — | 2026-07-23 08:00:45 WIB | 2026-07-23 01:00:45 | — |
| 30 | ETH | SPOT | LONG | llm | OPEN | 1862.37 | 1740.0 | 1943.03 | — | — | 2026-07-23 08:00:45 WIB | 2026-07-23 01:00:45 | — |
| 31 | SOL | SPOT | LONG | llm | OPEN | 75.88 | 71.33 | 78.56 | — | — | 2026-07-23 08:00:45 WIB | 2026-07-23 01:00:45 | — |
| 32 | XRP | SPOT | LONG | llm | OPEN | 1.1 | 1.03 | 1.16 | — | — | 2026-07-24 08:00:55 WIB | 2026-07-24 01:00:55 | — |
| 33 | ARB | OVERSOLD BOUNCE | LONG | **deterministic** | **LOSS** | 0.0839 | 0.0826415 | 0.090612 | 0.0826415 | **-1.70** | 2026-07-24 23:05:52 WIB | 2026-07-24 16:05:57 | 2026-07-25 07:41:04 WIB |
| 34 | SUI | OVERSOLD BOUNCE | LONG | shadow_e3 | OPEN | 0.7176 | 0.706028 | 0.752315 | — | — | 2026-07-24T16:05:57 UTC | 2026-07-24 16:05:57 | — |
| 35 | ARB | OVERSOLD BOUNCE | LONG | shadow_e3 | OPEN | 0.0839 | 0.082010 | 0.089570 | — | — | 2026-07-24T16:05:57 UTC | 2026-07-24 16:05:58 | — |
| 36 | SUI | OVERSOLD BOUNCE | LONG | **deterministic** | OPEN | 0.7141 | 0.7033885 | 0.771228 | — | — | 2026-07-24 23:40:49 WIB | 2026-07-24 16:40:49 | — |

**Tidak ada baris `WIN`** — jadi tidak ada detail WIN yang bisa ditampilkan untuk verifikasi (poin 2 di prompt tidak berlaku, karena datanya memang kosong, bukan karena tidak dicari).

Satu-satunya outcome closed post-Fase1 adalah **id 33 (ARB OVERSOLD BOUNCE, deterministic) — LOSS, -1.70%**, kena SL persis di harga SL (`close_price` = `sl_price` = 0.0826415), dievaluasi otomatis oleh `signal_check_job` (job 10 menit) lewat candle 5m OHLC — konsisten dengan mekanisme resmi Fase 1/2 (same-bar konservatif → LOSS kalau TP&SL sama-sama tersentuh di candle sama, tidak berlaku di sini karena `tp_hit=False`).

---

## 3. Winrate mentah per source

```python
from engine.trading.signal_tracker import get_signal_stats
get_signal_stats()                    # default: source='deterministic'
get_signal_stats(source='llm')
get_signal_stats(source='shadow_e3')
```

| Source | total_signals* | win | loss | open | win_rate |
|---|---|---|---|---|---|
| `deterministic` (**resmi produksi**) | 2 | 0 | 1 | 1 | **0.0%** |
| `llm` | 8 | 0 | 0 | 8 | 0.0% (tidak bermakna — 0 closed) |
| `shadow_e3` | 2 | 0 | 0 | 2 | 0.0% (tidak bermakna — 0 closed) |

*`total_signals` di `get_signal_stats()` menghitung SEMUA baris untuk source itu tanpa filter tanggal — tapi karena label source `deterministic`/`llm`/`shadow_e3` baru mulai dipakai sejak Fase 1 (baris lama berlabel `legacy`), angkanya otomatis identik dengan hasil query manual post-Fase1 di atas. Dikonfirmasi cocok persis (2/8/2) — tidak ada perbedaan antara query SQL manual dan fungsi produksi.

**Winrate resmi (hanya `deterministic`, sesuai desain Fase 1 — `llm` dan `shadow_e3` dikecualikan dari statistik resmi by design):**
- WIN / (WIN+LOSS) = 0 / (0+1) = **0%**
- **N closed = 1 → BELUM CUKUP DATA untuk winrate bermakna.** Ambang minimal yang disebut di roadmap sebelumnya (~20-30 outcome closed) jauh di atas N=1 — satu LOSS tunggal tidak bisa dipakai menyimpulkan performa strategi ke arah manapun (bisa jadi ARB memang setup buruk, bisa juga cuma varians normal untuk N kecil). **Tidak ada kesimpulan tren yang diambil dari sampel ini.**

Angka mentah `llm` dan `shadow_e3` dilaporkan di atas untuk konteks saja sesuai instruksi — **bukan** bagian dari winrate resmi produksi.

---

## 4. Kecukupan data

**BELUM CUKUP DATA** untuk menjawab "apakah strategi produksi (deterministic) sudah profitable" — alasan:
- Hanya 1 outcome closed (LOSS) sejak Fase 1 deploy (4 hari berjalan: 21-25 Juli).
- 1 sinyal `deterministic` lain masih `OPEN` (SUI, id 36, umur ~8,4 jam saat laporan ini ditulis) — belum ada outcome.
- Ambang minimal bermakna secara statistik (~20-30 closed outcome) butuh puluhan sinyal lagi. Dengan laju saat ini (~1 sinyal deterministic per ~2-4 hari, berdasarkan sampel kecil ini), mengumpulkan 20-30 outcome bisa memakan waktu berbulan-bulan — bukan sesuatu yang bisa dipercepat lewat audit ini.

Untuk `llm` dan `shadow_e3`: **BELUM CUKUP DATA** juga, malah lebih parah — **0 closed outcome** untuk keduanya (semua masih OPEN). Tidak ada winrate yang bisa dihitung sama sekali untuk dua source ini, bukan cuma "kurang bermakna" — datanya benar-benar belum ada.

---

## 5. Cross-check `/shadow_stats`

`/shadow_stats` (command Telegram, `interfaces/telegram_bot.py:6712-6730`) adalah wrapper tipis di atas `get_signal_stats(source="shadow_e3")` — tidak ada logika tambahan. Dipanggil langsung lewat Python (tanpa Telegram):

```
=== source=shadow_e3 ===
{
  "source_filter": "shadow_e3",
  "total_signals": 2,
  "win": 0,
  "loss": 0,
  "open": 2,
  "win_rate": 0.0,
  "by_coin": [{"coin": "ARB", "total": 1, ...}, {"coin": "SUI", "total": 1, ...}],
  "by_setup": [{"setup": "OVERSOLD BOUNCE", "total": 2, "win": 0, "loss": 0, "win_rate": 0.0}]
}
```

Cocok persis dengan query SQL manual (2 baris shadow_e3, keduanya OPEN, 0 WIN, 0 LOSS). **Tidak ada perbedaan** antara angka `/shadow_stats` dan query DB manual — konsisten.

---

## 6. Sinyal OPEN terlalu lama / potensi bug tracking

```sql
SELECT id, coin, setup, source, status, created_at,
       ROUND((julianday('now') - julianday(created_at)) * 24, 1) AS age_hours
FROM signal_tracking
WHERE created_at > '2026-07-21 02:08:51'
ORDER BY created_at;
```

| id | coin | setup | source | umur (jam) |
|---|---|---|---|---|
| 25-28 | BTC/ETH/SOL/XRP | LONG | llm | **84,1** (≈3,5 hari) |
| 29-31 | BTC/ETH/SOL | SPOT | llm | 48,1 (2 hari) |
| 32 | XRP | SPOT | llm | 24,1 (1 hari) |
| 34-35 | SUI/ARB | OVERSOLD BOUNCE | shadow_e3 | 9,0 |
| 36 | SUI | OVERSOLD BOUNCE | deterministic | 8,4 |

**Tidak ada sinyal yang melebihi batas expiry yang benar-benar berlaku di kode saat ini (7 hari flat, semua source — `engine/trading/signal_tracker.py:412`, `check_open_signals()`).** Sinyal tertua post-Fase1 (id 25-28, `llm`, 84,1 jam) masih di bawah separuh batas 7 hari.

**Tapi ada catatan penting terkait asumsi "3 hari" di prompt**: asumsi itu berasal dari konfigurasi E3 yang divalidasi lewat backtest (`E3 3×ATR / 3 hari`, expectancy +1,08%, PF 1,48, holdout N=149 — `ROBUSTNESS_RESULTS.md`, `FASE3_REPORT.md`), yang direkomendasikan sebagai basis Fase 4 shadow_e3. **Kode live `check_open_signals()` TIDAK membedakan time-stop per source/setup — semua baris (termasuk `shadow_e3`) memakai fallback flat 7 hari yang sama.** Jadi:
- Bukan bug "sinyal macet tidak pernah di-close" — job `signal_check_job` (tiap 10 menit) berjalan aktif dan terbukti bekerja (dua baris `legacy` lama, id 19 dan id 24, baru saja di-close otomatis pukul 07:41 dan 08:01 WIB hari ini, selama audit ini berlangsung).
- Tapi **ada gap antara time-stop yang divalidasi backtest (3 hari, khusus E3) dan time-stop yang benar-benar jalan di produksi (7 hari, generik semua source)**. Efek praktis: sinyal `shadow_e3` diberi jendela >2× lebih lama untuk kena TP/SL dibanding skenario yang diuji backtest, sehingga winrate/expectancy live shadow_e3 ke depan berpotensi tidak sebanding langsung dengan angka holdout backtest yang jadi alasan fitur ini direkomendasikan. **Dicatat sebagai temuan, tidak diperbaiki** (di luar cakupan audit read-only ini; jika mau diperbaiki, perlu keputusan eksplisit soal apakah time-stop per-source/per-setup ingin ditambahkan ke `check_open_signals()`).
- Konteks tambahan: `FASE4_REPORT.md` merekomendasikan observasi shadow_e3 minimal 6 minggu sejak aktivasi, berakhir sekitar **1 September 2026**. Kandidat pertama shadow_e3 baru match **24 Juli 23:05 WIB** (lihat `SHADOW_SIGNAL_SPAM_REPORT.md`) — baru ~1 hari berjalan dari jendela observasi 6 minggu itu, jauh dari cukup untuk evaluasi apa pun soal performa E3.

---

## Catatan metodologi

- Semua angka di atas berasal dari query SQL langsung ke `data/aliza.db` (ditunjukkan apa adanya) dan satu pemanggilan fungsi Python `get_signal_stats()` (bukan lewat Telegram) — tidak ada ekstrapolasi atau opini yang menggantikan data yang hilang.
- Tidak ada perubahan pada kode, `.env`, database, atau service selama audit ini. `git status` tidak menunjukkan perubahan pada file source (hanya laporan baru ini + salinannya).
