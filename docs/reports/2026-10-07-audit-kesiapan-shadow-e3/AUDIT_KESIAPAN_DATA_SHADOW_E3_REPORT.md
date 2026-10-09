# Audit Kesiapan Data Shadow E3 untuk Evaluasi Promosi

**Waktu audit:** 7 Oktober 2026 WIB (DB dan journal dibaca read-only)  
**Repo:** `main` = `origin/main` (`2c82301a66b6dd1ec42f304089f84424f3a58cf2`, 0 ahead / 0 behind).  
**Batas audit:** tidak ada perubahan kode aplikasi, `.env`, database, maupun flag. Artefak baru yang dibuat hanya laporan ini dan CSV `/tmp/shadow_e3_closed.csv` yang diminta. Worktree sudah memiliki banyak file laporan *untracked* sebelum audit; tidak disentuh.

## Verdict wajib

**BELUM SIAP.** Data bersih dari distorsi zona waktu pada baris `shadow_e3`, confidence adjuster sedang inert, dan tidak ditemukan perubahan pasca-24 Juli yang mengubah keputusan kandidat E3. Namun:

1. `N closed = 59`, **kurang 1** dari 60. Umur observasi sudah **10 minggu penuh** (10,63 minggu), sehingga semantik asli **N ≥60 DAN ≥6 minggu** tetap gagal karena N.
2. Empat dari lima kriteria beku gagal: expectancy `-1,0448%` (harus `> +0,3%`), PF `0,43` (harus `>1,2`), batas bawah bootstrap CI95 `-1,7375%` (harus `>-0,1%`), dan observasi dengan semantik **DAN**. Hanya konsentrasi profit lulus.
3. Laju closed terbaru adalah **0/minggu**: tidak ada sinyal sejak 26 September (10,41 hari), tidak ada close dalam 7 hari terakhir, dan journal 7 Oktober terus mencatat 0 kandidat (`no_setup=17`). Jadi tanggal N=60 **tidak dapat diproyeksikan** pada laju konstan saat ini (laju 0). Sebagai konteks, 22 close/28 hari terakhir sebelum waktu audit = 5,5/minggu; bila laju historis itu pulih, satu outcome lagi kira-kira 1,3 hari, tetapi ini bukan proyeksi laju terkini.

Tidak ada tindakan promosi dilakukan atau direkomendasikan oleh audit ini.

## 1. Jumlah dan komposisi

### Output mentah — tiga query yang diminta

```text
setup                 side   status  n
--------------------  -----  ------  --
OVERBOUGHT REJECTION  SHORT  LOSS    39
OVERBOUGHT REJECTION  SHORT  WIN     5
OVERSOLD BOUNCE       LONG   LOSS    12
OVERSOLD BOUNCE       LONG   WIN     3

total  closed  open_n  first_sig                         last_sig                          last_close
-----  ------  ------  --------------------------------  --------------------------------  --------------------------------
59     59      0       2026-07-24T16:05:57.258751+00:00  2026-09-26T16:00:20.919600+00:00  2026-09-27T10:08:24.213171+07:00

status  COUNT(*)
------  --------
LOSS    51
WIN     8
```

`/shadow_promotion_check` membaca hanya `status IN ('WIN','LOSS')` dengan `pnl_pct IS NOT NULL`; jadi WIN/LOSS dihitung, sedangkan `OPEN`, `EXPIRED`, `SUPPRESSED`, atau status lain tidak dihitung. Pada data aktual tidak ada status selain WIN/LOSS, jadi total=closed=59 dan open=0.

Sinyal pertama adalah 24 Juli 2026 16:05:57 UTC. Pada 7 Oktober elapsed time adalah 10,63 minggu, yaitu **10 minggu penuh**. Syarat asli yang dibekukan adalah `N>=60 AND minggu>=6`: `(59>=60) AND (10,63>=6) = false`. Implementasi command saat ini memakai `OR`, sehingga sub-check observasinya sendiri akan tampil lulus; ini adalah perbedaan semantik yang penting dan tidak dipakai untuk verdict audit.

### Integritas waktu

```text
dispatch_status  n
---------------  --
COOLDOWN         21
SENT             38

signal_format  close_format  n
-------------  ------------  --
ISO +00:00     ISO +07:00    59
```

Seluruh 59 `signal_time` shadow memakai offset eksplisit `+00:00`; seluruh `close_time` memakai offset eksplisit `+07:00`. `created_at` adalah timestamp SQLite naïf, tetapi tidak dipakai untuk umur/urutan/metrik audit. Karena umur dihitung dari `signal_time` yang ber-offset dan distribusi minggu memakai `signal_time`, campuran WIB/UTC historis pada baris lama tidak mendistorsi dataset `shadow_e3` ini. Urutan CSV memakai `COALESCE(close_time, signal_time)`; keduanya ber-offset eksplisit.

## 2. Lima kriteria beku

### Output lengkap evaluator, direkonstruksi read-only dengan algoritme yang sama

Evaluator Telegram tidak dipanggil agar tidak mengirim pesan. Perhitungan di bawah menggunakan query read-only yang sama (`WIN/LOSS`, `pnl_pct NOT NULL`), bootstrap percentile 10.000 iterasi dan seed `20260721`, persis implementasi `promotion_criteria.py`.

```text
🔍 SHADOW E3 → PRODUKSI: CEK KRITERIA PROMOSI
(read-only, TIDAK mengubah SHADOW_E3_ENABLED/SHADOW_E3_DISPATCH apa pun)

N closed outcome: 59

❌ Expectancy: -1.0448% (ambang >+0.3%)
❌ Profit Factor: 0.43 (ambang >1.2)
❌ Batas bawah bootstrap CI95: -1.7375% (ambang >-0.1%)
✅ Konsentrasi profit: PEPE = 26.4% dari total profit (ambang <=50%)
✅ Observasi: N=59 closed (ambang ≥60) ATAU 10.6 minggu sejak sinyal pertama (ambang ≥6 minggu)

❌ BELUM MEMENUHI — kriteria yang belum: expectancy, profit factor, batas bawah bootstrap CI.

Keputusan promosi tetap manual — command ini tidak mengubah apa pun.
```

Catatan: baris kesimpulan evaluator di atas tidak menyebut observasi karena implementasi `OR` menganggapnya lulus. Dengan kriteria beku `AND`, observasi juga **gagal**.

### Hitungan manual independen

| Metrik | Hasil |
|---|---:|
| N / WIN / LOSS | 59 / 8 / 51 |
| Win rate | 13,5593% |
| Gross win / gross loss | 47,204009 / 108,846031 poin-% |
| Expectancy | -1,044780% per trade |
| Profit factor | 0,433677 |
| Bootstrap CI95 lower | -1,737492% |
| Profit positif total | 47,204009 poin-% |
| Top 1 | PEPE 12,463883 = 26,4043% |
| Top 2 | XRP 11,701579 = 24,7894% |
| Top 3 | ETHFI 8,420990 = 17,8396% |

Hitungan independen **sama** dengan evaluator setelah pembulatan tampilan. Konsentrasi memakai share dari jumlah PnL positif, sesuai kode evaluator; enam coin yang profit adalah PEPE, XRP, ETHFI, ADA, SOL, BNB. Tidak ada coin melebihi 50%.

```text
setup                 side   n   win  loss  winrate_pct  expectancy_pct  gross_win  gross_loss
--------------------  -----  --  ---  ----  -----------  --------------  ---------  ----------
OVERBOUGHT REJECTION  SHORT  44  5    39    11.3636      -1.382907       26.341623  87.189530
OVERSOLD BOUNCE       LONG   15  3    12    20.0000      -0.052941       20.862386  21.656501
```

### CSV mentah closed shadow

File dibuat di `/tmp/shadow_e3_closed.csv`. Totalnya 60 baris termasuk header, sehingga seluruh isi ditempel di bawah.

```csv
pnl_pct,coin,setup,signal_time,close_time
-2.452526,ARB,"OVERSOLD BOUNCE",2026-07-24T16:05:57.260134+00:00,2026-07-25T08:41:04.669385+07:00
-1.812548,SUI,"OVERSOLD BOUNCE",2026-07-24T16:05:57.258751+00:00,2026-07-25T13:37:05.478987+07:00
6.097268,PEPE,"OVERSOLD BOUNCE",2026-07-25T08:01:46.989429+00:00,2026-07-26T09:37:05.479284+07:00
-1.289748,ETH,"OVERBOUGHT REJECTION",2026-07-27T00:05:47.476002+00:00,2026-07-27T13:13:18.652282+07:00
-2.382528,ARB,"OVERSOLD BOUNCE",2026-07-25T01:41:43.565058+00:00,2026-07-27T21:33:18.652947+07:00
-1.770055,SUI,"OVERSOLD BOUNCE",2026-07-25T06:37:46.989821+00:00,2026-07-27T21:43:18.652851+07:00
-1.638566,ADA,"OVERSOLD BOUNCE",2026-07-27T16:03:59.923629+00:00,2026-07-28T05:43:18.652703+07:00
-1.882929,ARB,"OVERSOLD BOUNCE",2026-07-27T16:03:59.925901+00:00,2026-07-28T05:43:18.652703+07:00
-2.791518,ETHFI,"OVERSOLD BOUNCE",2026-07-25T08:01:46.991604+00:00,2026-07-29T10:33:18.653181+07:00
-1.093989,BNB,"OVERBOUGHT REJECTION",2026-07-30T12:03:59.977908+00:00,2026-07-31T00:43:18.652721+07:00
-2.414284,ADA,"OVERBOUGHT REJECTION",2026-07-30T16:05:00.482229+00:00,2026-08-01T20:43:18.653269+07:00
2.855734,BNB,"OVERBOUGHT REJECTION",2026-07-30T17:56:57.733555+00:00,2026-08-02T01:33:18.652847+07:00
-2.704824,ETHFI,"OVERSOLD BOUNCE",2026-08-04T16:01:01.212212+00:00,2026-08-05T07:13:18.653258+07:00
-0.731965,XAUT,"OVERBOUGHT REJECTION",2026-08-05T08:03:36.158677+00:00,2026-08-05T19:01:53.549975+07:00
-0.772633,XAUT,"OVERBOUGHT REJECTION",2026-08-05T12:03:33.805282+00:00,2026-08-05T21:11:53.550179+07:00
-0.884849,XAUT,"OVERBOUGHT REJECTION",2026-08-05T16:04:40.749982+00:00,2026-08-06T01:11:53.551758+07:00
-0.880818,XAUT,"OVERBOUGHT REJECTION",2026-08-05T18:15:32.462172+00:00,2026-08-06T07:31:53.550037+07:00
-0.924298,XAUT,"OVERBOUGHT REJECTION",2026-08-06T23:38:32.364500+00:00,2026-08-07T13:01:53.550625+07:00
-0.907642,XAUT,"OVERBOUGHT REJECTION",2026-08-07T08:00:34.809984+00:00,2026-08-07T18:11:53.549748+07:00
8.42099,ETHFI,"OVERSOLD BOUNCE",2026-08-05T00:13:57.515436+00:00,2026-08-07T18:31:53.549671+07:00
-1.82621,TAO,"OVERBOUGHT REJECTION",2026-08-09T03:15:39.363818+00:00,2026-08-09T10:41:53.549786+07:00
-2.655779,ETHFI,"OVERBOUGHT REJECTION",2026-08-13T20:01:34.138917+00:00,2026-08-14T04:41:53.549832+07:00
-3.045237,ETHFI,"OVERBOUGHT REJECTION",2026-08-14T00:06:36.230859+00:00,2026-08-15T02:31:53.550064+07:00
-3.208985,ETHFI,"OVERBOUGHT REJECTION",2026-08-14T20:02:35.339970+00:00,2026-08-15T15:31:53.550171+07:00
-3.250281,ETHFI,"OVERBOUGHT REJECTION",2026-08-15T12:00:43.208488+00:00,2026-08-16T20:11:53.550149+07:00
-1.917488,PEPE,"OVERSOLD BOUNCE",2026-08-17T01:04:34.801965+00:00,2026-08-18T09:51:53.549630+07:00
-0.797181,BTC,"OVERBOUGHT REJECTION",2026-08-18T00:05:34.932034+00:00,2026-08-18T21:31:53.553093+07:00
-2.936308,ETHFI,"OVERBOUGHT REJECTION",2026-08-16T16:03:32.794574+00:00,2026-08-20T07:01:53.549270+07:00
-1.029069,XAUT,"OVERSOLD BOUNCE",2026-08-29T00:00:25.543978+00:00,2026-08-31T09:07:42.886133+07:00
-0.636201,XAUT,"OVERSOLD BOUNCE",2026-08-31T02:08:22.003670+00:00,2026-08-31T09:37:42.885978+07:00
-0.638249,XAUT,"OVERSOLD BOUNCE",2026-08-31T02:38:21.882975+00:00,2026-09-01T15:31:55.527739+07:00
6.344128,ADA,"OVERSOLD BOUNCE",2026-08-31T00:05:24.861085+00:00,2026-09-03T08:31:55.527938+07:00
-2.025025,XRP,"OVERBOUGHT REJECTION",2026-09-03T16:03:42.191292+00:00,2026-09-04T03:31:55.528076+07:00
-1.242358,BTC,"OVERBOUGHT REJECTION",2026-09-03T16:03:42.178362+00:00,2026-09-04T04:31:55.528429+07:00
-3.674873,XPL,"OVERBOUGHT REJECTION",2026-09-03T20:03:37.740964+00:00,2026-09-04T18:31:55.527727+07:00
6.366615,PEPE,"OVERBOUGHT REJECTION",2026-09-03T16:03:42.194395+00:00,2026-09-04T19:31:55.528727+07:00
6.26157,XRP,"OVERBOUGHT REJECTION",2026-09-03T20:34:40.903843+00:00,2026-09-07T22:41:55.528294+07:00
-1.815595,XRP,"OVERBOUGHT REJECTION",2026-09-14T20:02:38.738929+00:00,2026-09-15T03:41:55.528448+07:00
5.440009,XRP,"OVERBOUGHT REJECTION",2026-09-14T20:53:40.852785+00:00,2026-09-15T15:11:55.528505+07:00
-2.35123,ASTER,"OVERBOUGHT REJECTION",2026-09-17T12:01:38.671355+00:00,2026-09-18T10:50:15.547259+07:00
-2.604057,TAO,"OVERBOUGHT REJECTION",2026-09-18T08:03:01.083470+00:00,2026-09-18T17:50:17.390630+07:00
-3.129933,WLD,"OVERBOUGHT REJECTION",2026-09-18T08:03:01.079694+00:00,2026-09-18T19:10:17.390599+07:00
-2.23907,SUI,"OVERBOUGHT REJECTION",2026-09-18T04:00:59.879901+00:00,2026-09-18T20:50:17.390951+07:00
-1.958638,SOL,"OVERBOUGHT REJECTION",2026-09-18T08:03:01.073959+00:00,2026-09-18T20:50:17.390951+07:00
-2.675465,TAO,"OVERBOUGHT REJECTION",2026-09-18T11:07:00.082784+00:00,2026-09-18T20:50:17.390951+07:00
-1.855921,ETH,"OVERBOUGHT REJECTION",2026-09-18T16:02:01.007742+00:00,2026-09-19T01:40:17.390667+07:00
-2.121409,SOL,"OVERBOUGHT REJECTION",2026-09-18T16:02:01.293485+00:00,2026-09-19T02:20:17.390196+07:00
-2.674747,ADA,"OVERBOUGHT REJECTION",2026-09-18T16:02:01.574566+00:00,2026-09-19T04:20:17.390515+07:00
-2.635981,SUI,"OVERBOUGHT REJECTION",2026-09-18T16:02:01.712129+00:00,2026-09-19T05:20:17.390487+07:00
-1.450648,BTC,"OVERBOUGHT REJECTION",2026-09-18T16:02:00.872939+00:00,2026-09-19T08:10:17.390546+07:00
-2.628071,ADA,"OVERBOUGHT REJECTION",2026-09-19T00:01:05.745720+00:00,2026-09-19T09:20:17.390979+07:00
-2.789269,TAO,"OVERBOUGHT REJECTION",2026-09-18T16:02:03.590117+00:00,2026-09-19T10:00:17.390390+07:00
-2.57939,SUI,"OVERBOUGHT REJECTION",2026-09-18T22:27:58.432040+00:00,2026-09-19T16:50:17.390176+07:00
5.417695,SOL,"OVERBOUGHT REJECTION",2026-09-18T20:05:57.933223+00:00,2026-09-20T10:00:17.390420+07:00
-1.82113,ETH,"OVERBOUGHT REJECTION",2026-09-18T20:05:57.930709+00:00,2026-09-21T07:20:17.390490+07:00
-3.333681,WLD,"OVERBOUGHT REJECTION",2026-09-18T12:10:59.871390+00:00,2026-09-21T16:40:17.391900+07:00
-4.18134,JTO,"OVERBOUGHT REJECTION",2026-09-25T20:06:03.655631+00:00,2026-09-26T13:38:24.213833+07:00
-3.966886,JTO,"OVERBOUGHT REJECTION",2026-09-26T06:41:03.818547+00:00,2026-09-26T21:48:24.213148+07:00
-3.814606,JTO,"OVERBOUGHT REJECTION",2026-09-26T16:00:20.919600+00:00,2026-09-27T10:08:24.213171+07:00
```

## 3. Kebersihan parameter dan perubahan perilaku

### `LEARNING_MIN_SAMPLES`

Output mentah:

```text
.env:16:LEARNING_MIN_SAMPLES=100000

_min_samples= 100000
N=99999, base=65 -> 65
N=59, base=65 -> 65
```

`interfaces/telegram_bot.py` memanggil `load_project_dotenv()` ketika dimuat. `confidence_adjuster._min_samples()` membaca `os.environ['LEARNING_MIN_SAMPLES']`; guard mengembalikan base confidence bila `total_trades < _min_samples()`. Uji runtime fungsi dengan nilai `.env` yang sama membuktikan N=99.999 dan N=59 sama-sama tidak mengubah baseline 65. Dengan demikian adjuster **inert** untuk data ini. Selain itu, E3 tidak memakai confidence sebagai gerbang kandidat: setelah `TradingBrain.analyze`, E3 hanya memakai setup, side, entry dan ATR lalu menimpa level SL/TP/RR-nya sendiri.

### Raw `git log --since=2026-07-24 --name-only` untuk jalur inti yang diminta

```text
4561a3f  2026-09-18T14:35:06+07:00  feat: add multi-timeframe big move alerts
engine/market/market_snapshot_engine.py

9468f9e  2026-08-27T09:37:26+07:00  feat: shadow_e3 outcome-based promotion policy + per-reason observability
engine/shadow/e3_shadow.py

e7eb6ac  2026-08-21T10:02:50+07:00  feat: tambah menu Telegram Info Coin (display-only, paket 1)
engine/market/market_analyzer.py

9dc9782  2026-08-05T07:37:34+07:00  fix: calculate big move from closed 1h candle
engine/market/market_snapshot_engine.py

5909856  2026-07-27T10:18:55+07:00  fix: tie trade signal episodes to open tracking rows
engine/trading/signal_engine.py
engine/trading/signal_tracker.py

122c61f  2026-07-27T09:55:56+07:00  fix: bootstrap signal edge state from open tracking
engine/trading/signal_engine.py

e67eb45  2026-07-27T09:45:07+07:00  feat: edge-triggered re-arm for deterministic TRADE SIGNAL dispatch
engine/trading/signal_engine.py

c4bc614  2026-07-25T13:00:46+07:00  feat: add read-only shadow_e3 promotion criteria checklist
engine/shadow/promotion_criteria.py

bff3128  2026-07-25T07:37:30+07:00  fix: add persisted cooldown to shadow_e3 dispatch, stop SUI spam
engine/shadow/e3_shadow.py
```

Tidak ada commit setelah 24 Juli yang menyentuh `engine/brain/`, strategi E3/`engine/strategy/`, filter RR, `features.py`, `multi_timeframe_analyzer.py`, atau `market_universe.py`. Jalur confidence tambahan berikut juga diperiksa:

| Tanggal / commit | Ringkasan | Dampak pada keputusan kandidat E3 |
|---|---|---|
| 25 Jul `bff3128` | Cooldown dispatch per `(coin,setup,side)`. | **Tidak mengubah** data input/aturan kandidat/level E3. Mengubah transport dan `dispatch_status`; pasca-commit kandidat COOLDOWN tetap tercatat. Dataset memiliki 2 close sebelum dan 57 sesudah, sehingga metadata tracking tidak homogen, tetapi tidak ada bukti seleksi kandidat berubah. |
| 25 Jul `c4bc614` | Menambah evaluator promosi read-only. | Tidak mengubah E3 atau DB; hanya pembacaan. |
| 25 Jul `41b55b8` | Confidence adjuster membaca outcome live + guard minimum sample. | Tidak mengubah setup/RR/gerbang E3; confidence bukan input filter E3 dan sekarang dibekukan di 100.000. |
| 27 Jul `e67eb45`, `122c61f`, `5909856` | Re-arm, bootstrap, dan episode tracking sinyal **deterministic**. | Tidak memanggil / tidak disentuh oleh `e3_shadow`; tidak mengubah shadow. |
| 5 Agu `9dc9782` | Menambah `price_change_1h` untuk Big Move snapshot. | Tidak mengubah keputusan E3: `TradingBrain` hanya membaca price/trend/rsi/support/resistance/trend_alignment; field baru tidak dibaca. |
| 21 Agu `e7eb6ac` | Ekspos `ma20/ma50/ma200` untuk Info Coin. | Additive/display; field MA tidak dibaca `TradingBrain`. |
| 27 Agu `9468f9e` | Counter alasan gagal observability E3. | Tidak mengubah kondisi; counter lokal sebelum return dan log saja. |
| 18 Sep `4561a3f` | Menambah `price_change_15m/30m` untuk Big Move. | Sama: field additive alert, tidak dibaca E3/TradingBrain. |
| 18 Sep `eac382a` | Fix neutral/BEARISH tie dan fallback konteks global. | Hanya `market_context_engine`, `prediction_engine`, Telegram; bukan `market_intelligence`/E3. Tidak mengubah input E3. |
| 18 Sep `7f5b5de` | Alert transisi konteks market. | Job Telegram alert; tidak mengubah snapshot atau E3. |
| 24 Sep `2c82301` | Alert reversal tren per coin. | Job Telegram alert; tidak mengubah snapshot atau E3. |

Segment yang mungkin relevan untuk metadata cooldown:

```text
segment                            n   wins  losses  expectancy_pct
---------------------------------  --  ----  ------  --------------
pre 2026-07-25 07:37 WIB cooldown  2   0     2       -2.132537
post-cooldown/pre-observability    26  3     23      -0.974389
post-observability                 31  5     26      -1.033640
```

Tidak ada segmen strategi/RR/universe untuk dihitung karena tidak ada perubahan kode tersebut dalam rentang audit. Perubahan cooldown tidak mengubah aturan seleksi; segmentasi di atas disediakan agar perbedaan metadata tercatat eksplisit.

### Universe coin

`CORE_COINS` berisi 21 coin tetap: BTC, ETH, BNB, SOL, XRP, ADA, SUI, ARB, PEPE, JTO, ETHFI, WLD, OM, ASTER, XPL, TAO, BONE, FARTCOIN, HYPE, ZEREBRO, XAUT. Tidak ada diff `market_universe.py` sejak baseline 24 Juli; perubahan terakhir file itu adalah 21 Juli. Nilai aktif `.env` adalah:

```text
UNIVERSE_EXCLUDE=BONE,FARTCOIN,HYPE,ZEREBRO
```

Artinya 17 coin dipoll (21 inti dikurangi empat exclude), cocok dengan journal 7 Oktober (`no_setup=17`). Tidak ada `COIN_FAIL_THRESHOLD`/`COIN_SUSPEND_HOURS` override aktif, sehingga default adalah threshold 10 dan suspend 6 jam. State suspend adalah memori proses (`_coin_suspended_until`), tidak dipersistkan; pencarian journal sejak 24 Juli tidak menemukan `universe_suspend` ataupun `universe_unsuspend`. Kombinasi 17 coin diproses sekarang dan tidak adanya log suspend menunjukkan tidak ada suspend aktif yang mengubah populasi pada audit. Riwayat nilai `.env` sebelum audit tidak versioned, sehingga perubahan manual historis tidak dapat dibuktikan dari Git; tidak ada indikasi DB bahwa populasi berubah.

## 4. Representativitas

### Distribusi waktu, setup, sisi, regime

```text
month    signals  closed  wins  expectancy_pct
-------  -------  ------  ----  --------------
2026-07  12       12      2     -0.881307
2026-08  20       20      2     -0.749145
2026-09  27       27      4     -1.336423

week_utc  signals  wins  losses  expectancy_pct
--------  -------  ----  ------  --------------
2026-W29  6        1     5       -0.851985
2026-W30  6        1     5       -0.910630
2026-W31  9        1     8       -0.134694
2026-W32  5        0     5       -3.019318
2026-W33  2        0     2       -1.357335
2026-W34  1        0     1       -1.029069
2026-W35  8        3     5       +1.344451
2026-W37  19       2     17      -1.568765
2026-W38  3        0     3       -3.987611

regime   n
-------  --
UNKNOWN  59
```

Tidak ada sinyal pada W36 (7–13 Sep), dan tidak ada lagi sejak 26 Sep. Gap 18–28 Agu juga terlihat (hanya 18 Agu lalu 29 Agu). Journal live pada 7 Oktober konsisten dengan stagnasi: setiap siklus menunjukkan 17 coin diproses dan semuanya `no_setup`, bukan error/ATR/coverage. Kolom `regime` record semuanya `UNKNOWN`, sehingga representativitas per regime **tidak dapat dinilai dari DB**. Sampel tidak didominasi satu coin pada jumlah baris (maksimum XAUT 9/59=15,3%), tetapi sangat terkonsentrasi pada dua setup: OVERBOUGHT REJECTION SHORT 44/59=74,6%; OVERSOLD BOUNCE LONG 15/59=25,4%. Profit positif juga tidak didominasi satu coin (top 26,4%).

Periode harian tanpa sinyal terbaru: 27 Sep–7 Okt = 11 hari kalender (10,41 hari elapsed sejak timestamp terakhir). Closed terakhir adalah 27 Sep WIB.

### Pembanding produksi pada jendela sama

Jendela: `MIN(signal_time)` sampai `MAX(signal_time)` `shadow_e3` (24 Jul 16:05 UTC s.d. 26 Sep 16:00 UTC).

```text
source         total  closed  wins  losses  winrate_pct  expectancy_pct
-------------  -----  ------  ----  ------  -----------  --------------
deterministic  60     60      5     55      8.3333       -0.414075
shadow_e3      59     59      8     51      13.5593      -1.044780
```

Shadow memiliki win rate lebih tinggi, tetapi magnitude loss/hasil membuat expectancy lebih buruk daripada deterministic. Keduanya buruk pada jendela ini; pembanding ini kontekstual, bukan justifikasi promosi.

## Penutup

Data dapat terus diobservasi, tetapi **belum cukup maupun memenuhi kualitas** untuk evaluasi promosi berdasarkan kriteria beku. Satu closed outcome lagi hanya akan memenuhi syarat kuantitas-waktu; ia tidak mengatasi kegagalan expectancy, PF, dan CI yang besar. Tidak ada kontaminasi yang teridentifikasi dari perubahan keputusan E3 pasca-start; caveat yang tersisa adalah perubahan metadata/transport cooldown pada 25 Juli dan tidak tersedianya histori `.env` atau state suspend in-memory sebelum audit.
