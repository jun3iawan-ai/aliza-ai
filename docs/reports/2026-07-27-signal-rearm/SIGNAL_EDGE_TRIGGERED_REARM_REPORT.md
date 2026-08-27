# Implementasi Edge-Triggered Re-Arm `[TRADE SIGNAL]`

Branch: `feat/signal-edge-triggered-rearm` (dibuat dari `main` terkini).  
Status: **implementasi dan test selesai; belum merge, belum push, belum deploy, belum restart service.**

## Ringkasan keputusan

Audit sebelumnya membuktikan re-fire bukan kebocoran TTL: setup valid yang sama boleh mengirim ulang setiap 900 detik. Implementasi ini mengganti **syarat re-arm** bagi sinyal deterministic menjadi edge-triggered, sambil mempertahankan TTL 900 detik sebagai floor pengaman kedua.

Parameter dipilih: `SIGNAL_REARM_DEBOUNCE_SCANS=3` (default). Dengan snapshot 60 detik, setup harus tidak valid selama tiga evaluasi yang benar-benar memiliki data (sekitar tiga menit) sebelum episode lama dianggap reset. Dua scan invalid singkat tidak cukup, sehingga flicker di batas RSI/level tidak menghasilkan sinyal baru.

State memakai `engine.state_store`, bukan `notification_governor`, karena `state_store` memang hanya dipakai oleh jalur `engine/trading/signal_engine.py`; ini menjaga ownership dan menghindari perubahan checker lain. Format persisted baru menyimpan dua namespace:

```json
{
  "last_signals": { "coin|setup": { "signal": {}, "time": 0 } },
  "edge_signal_state": {
    "coin|setup|side": { "active": true, "inactive_scans": 0 }
  }
}
```

Loader tetap menerima format lama `LAST_SIGNALS` flat. Pada rollout pertama, deterministic key lama dibootstrap sebagai episode `active`, agar restart/deploy tidak otomatis menganggap setup yang sedang berjalan sebagai `new`.

## Langkah 0 — diagnosis

1. `TradingBrain.analyze()` membuat `trade_setup` per coin (`engine/brain/trading_brain.py:102-335`). Titik evaluasi produksi yang tepat adalah `engine/trading/signal_engine.py:321-369`: setiap row market yang valid diperiksa untuk `trade_setup`, `NO SETUP`, RR minimum, dan confidence minimum. Sesudah seluruh coin diproses, `observe_signal_validity(candidates, observed_coins)` dipanggil sekali per scan (`engine/trading/signal_engine.py:385-387`). Karena ia menerima seluruh kandidat yang lolos—not only best-RR candidate—counter reset tidak bergantung kandidat mana yang akhirnya dipilih untuk dispatch.
2. Row market yang error/tidak ada tidak dihitung sebagai invalid (`engine/trading/signal_engine.py:309-325`). Dengan demikian outage data tidak bisa me-reset episode dan memicu false re-arm.
3. Identity episode adalah `(coin, setup, side)` melalui `_edge_key()` (`engine/trading/signal_engine.py:80-96`). Ini memenuhi pemisahan LONG/SHORT dan isolasi antar coin.

## Perubahan implementasi

- `engine/trading/signal_engine.py`
  - Tambah state persisted `EDGE_SIGNAL_STATE` dan parser env `signal_rearm_debounce_scans()` (`:62-151`).
  - Tambah `observe_signal_validity()`: valid menghapus counter invalid; invalid berturut-turut menaikkan counter; pada tiga scan, `active` berubah `False`/reset (`:107-151`).
  - `can_send_signal()` kini hanya menerapkan edge gate untuk `source='deterministic'`; source lain mempertahankan perilaku TTL lama (`:176-203`).
  - Emit observability tag persis: `new`, `suppressed_same_episode`, dan `suppressed_floor_cooldown` (`:185-202`).
  - `record_signal_sent()` menandai episode active hanya setelah dispatch sukses (`:206-215`). TTL tetap dipakai sebagai floor dengan key lama `(coin,setup)`.
  - Loader/saver state backward-compatible dan tahan restart (`:99-104,218-247`).
- `.env.example:19-23`: dokumentasi `SIGNAL_REARM_DEBOUNCE_SCANS=3`. `.env` produksi tidak disentuh.
- `tests/test_signal_edge_triggered_rearm.py`: tujuh test baru.
- `tests/test_drawdown_broadcast_gate.py:35-48`: fixture sekarang mereset edge cache selain TTL cache, agar test gateway tetap terisolasi.

Tidak ada perubahan pada RSI, ATR, threshold, perhitungan RR, selection strategy, `shadow_e3`, atau checker `notification_governor` lain.

## Perilaku baru

| Kondisi saat evaluasi dispatch deterministic | Hasil | Tag log |
|---|---|---|
| Belum pernah terlihat / sudah reset, dan TTL sudah lewat | dispatch | `new` |
| Setup masih valid dalam episode active | tidak dispatch | `suppressed_same_episode` |
| Sudah reset, tetapi belum 900 detik sejak dispatch sebelumnya | tidak dispatch | `suppressed_floor_cooldown` |

Sinyal yang tidak valid kurang dari tiga scan lalu valid kembali tetap berada dalam episode active. Setelah tiga scan invalid, valid berikutnya membentuk edge baru, tetapi masih harus melewati floor TTL 15 menit.

## Test

Test khusus mencakup semua skenario wajib:

1. Setup valid terus selama 20 scan (melintasi TTL) → satu dispatch saja.
2. Flicker invalid dua scan → tetap `suppressed_same_episode`.
3. Invalid tiga scan, kemudian valid setelah 901 detik → `new` dispatch kedua.
4. Reset tiga scan pada detik 240 → `suppressed_floor_cooldown`.
5. SUI dan ARB independen walau setup/side sama.
6. Restart simulasi membaca state persisted dan tidak mengirim ulang episode active.
7. `shadow_e3` tetap memiliki default cooldown 14.400 dan snapshot-alert tetap empat jam.

Hasil fokus:

```text
$ ./venv/bin/python -m pytest -q tests/test_signal_edge_triggered_rearm.py tests/test_drawdown_broadcast_gate.py
18 passed, 3 warnings in 21.07s
```

Regresi penuh:

```text
$ ./venv/bin/python -m pytest tests/ test_telegram_authorization.py test_dashboard_*.py -q
280 passed, 3 warnings, 74 subtests passed in 30.19s
```

Warning hanya `DeprecationWarning` SWIG dependency yang sudah ada.

## Simulasi pola SUI audit sebelumnya

Audit read-only mencatat 90 dispatch `SUI|OVERSOLD BOUNCE` yang berulang tiap sekitar 15–16 menit, karena setup tetap valid sementara TTL saja yang habis. Dengan mekanisme lama, rentang yang sama menghasilkan **90 dispatch**.

Untuk replay kondisi yang sama—setup SUI tetap valid pada setiap snapshot dan tidak pernah ada tiga scan invalid berturut-turut—mekanisme baru menghasilkan:

```text
snapshot pertama:                new -> 1 dispatch
episode SUI yang masih valid:    suppressed_same_episode
total untuk rentang yang sama:   1 dispatch (bukan 90)
```

Jadi 89 re-fire TTL yang sebelumnya terlihat akan tertahan. Bila pada data live setup benar-benar hilang selama minimal tiga scan dan muncul lagi, satu dispatch baru diperbolehkan hanya jika juga melewati floor 900 detik. Ini adalah perubahan timing dispatch saja; logika yang menyatakan setup valid/tidak valid tidak diubah.

## Batasan dan langkah berikutnya

- Implementasi tidak melakukan merge/deploy sesuai instruksi; review diperlukan sebelum perubahan inti ini aktif.
- Counter invalid dijalankan dari `scan_for_signals()`; early return karena macro block atau tidak ada snapshot tidak menghitung invalid, agar tidak menciptakan re-arm dari ketidaktersediaan evaluasi.
- Setelah review, langkah deploy harus mencakup backup/verifikasi `data/signal_state.json`, restart terkendali, dan observasi tag `new`/`suppressed_*`; itu sengaja tidak dilakukan dalam prompt ini.

## Commit & Deploy Attempt — 27 Juli 2026

### Commit dan test pra-merge

- Commit fitur dibuat di branch `feat/signal-edge-triggered-rearm`:
  `e67eb45` — `feat: edge-triggered re-arm for deterministic TRADE SIGNAL dispatch`.
- Commit hanya berisi empat file implementasi/test:
  `.env.example`, `engine/trading/signal_engine.py`,
  `tests/test_drawdown_broadcast_gate.py`, dan
  `tests/test_signal_edge_triggered_rearm.py` (330 insertions, 10 deletions).
  Tidak ada perubahan RSI/ATR/threshold/RR/strategy selection, `shadow_e3`, atau
  checker `notification_governor`.
- Full test pra-merge:

  ```text
  280 passed, 3 warnings, 74 subtests passed in 34.47s
  ```

### Backup state pra-restart

Path state dikonfirmasi dari `engine/state_store.py:5`:
`/opt/aliza-ai/data/signal_state.json`.

Backup byte-identik telah dibuat **sebelum merge atau restart**:

```text
/opt/aliza-ai/data/signal_state.json.bak-20260727_094520
SHA-256 21c294afc4298924908779d86edbf141ae9404692bb862e61cd7f0fc4955a7e3
```

SHA-256 source pada saat backup sama persis. State saat itu berbentuk envelope,
berisi satu `last_signals` LLM (`BONE|llm-advisory`) dan **nol**
`edge_signal_state` deterministic.

### STOP — pre-deploy safety gate gagal, tidak di-merge/deploy

Tidak dilakukan `git checkout main`, merge, restart service, push, atau cleanup
branch. Alasannya adalah stop condition pada prompt ditemukan **sebelum** restart:
state disk tidak punya episode deterministic yang dapat dibootstrap, padahal setup
ETH yang sama masih berjalan live.

Bukti log real:

```text
logs/aliza.log:59707  2026-07-27 09:42:47,887 [SIGNAL] ETH|OVERBOUGHT REJECTION from deterministic
logs/aliza.log:59708  2026-07-27 09:42:48,586 ALERT DISPATCHED via CENTRAL GATEWAY
logs/aliza.log:59908  2026-07-27 09:44:44,554 [SIGNAL TYPE] trade_signal | ETH|OVERBOUGHT REJECTION
logs/aliza.log:59909  2026-07-27 09:44:44,555 [BLOCKED] duplicate signal ETH|OVERBOUGHT REJECTION
logs/aliza.log:60023  2026-07-27 09:45:44,504 [SIGNAL TYPE] trade_signal | ETH|OVERBOUGHT REJECTION
logs/aliza.log:60024  2026-07-27 09:45:44,504 [BLOCKED] duplicate signal ETH|OVERBOUGHT REJECTION
```

Jadi ETH masih production-valid dan sedang berada dalam episode lama. Dengan
`edge_signal_state={}` dan tidak ada TTL `ETH|OVERBOUGHT REJECTION` di file state,
loader branch baru tidak dapat menandai ETH sebagai `active`; pada scan pertama
pasca-restart `can_send_signal()` akan memilih `new` dan mengirim ulang ETH.
Itu adalah precisely gelombang/dispatch dadakan yang dilarang prompt, sehingga
proses dihentikan sebelum produksi diubah.

Snapshot read-only `signal_tracking` setelah penghentian menunjukkan total tetap
5 row deterministic dan tidak ada row deterministic baru sejak 09:40 WIB. Karena
tidak ada restart/deploy, tidak ada tag `new`/`suppressed_*` produksi yang sah
untuk ditempelkan; bukti log di atas adalah alasan objektif penghentian, bukan
klaim verifikasi pascadeploy.

### Status akhir deployment

| Tahap | Status |
|---|---|
| Commit | selesai (`e67eb45`) |
| Test penuh pra-merge | lulus (280 passed) |
| Backup state | selesai, byte-identik |
| Merge ke `main` | **tidak dilakukan** |
| Restart/deploy | **tidak dilakukan** |
| Verifikasi 30–60 menit pascadeploy | tidak berlaku; stop sebelum restart |
| Push `origin/main` | **tidak dilakukan** |
| Hapus branch fitur | **tidak dilakukan** |

Sebelum deploy dapat dilanjutkan, diperlukan keputusan/review untuk memulihkan
atau merekonstruksi episode deterministic aktif ke state yang akan dibaca saat
startup (minimal `ETH|OVERBOUGHT REJECTION|SHORT`) tanpa mengirim ulang setup
lama. Tidak ada tindakan state mutation seperti itu dilakukan dalam run ini.



## Bootstrap dari `signal_tracking` & Deploy Attempt Kedua — 27 Juli 2026

### Diagnosis tambahan: mengapa TTL lama tidak ada di state file

`engine/state_store.py:5-17` memang menyimpan state TTL di
`data/signal_state.json`; ini bukan cache in-memory atau path lain. Penyebab state
disk berisi hanya `BONE|llm-advisory` adalah isolasi test yang belum lengkap:
`tests/test_drawdown_broadcast_gate.py` memanggil gateway produksi mock melalui
`process_signal()` tetapi hanya mereset cache memori, sehingga test LLM terakhir
menulis state persistent nyata. Dengan kata lain, file tidak dapat menjadi sumber
kebenaran episode deterministic pada rollout ini, walaupun log lama menunjukkan
`[BLOCKED] duplicate` untuk ETH.

SQLite adalah sumber kebenaran yang lebih andal untuk migrasi: sebelum restart,
query read-only ke `data/aliza.db` menemukan tiga baris
`source='deterministic' AND status='OPEN'`:

```text
id  coin  setup                 side   status  dispatch_status
38  ARB   OVERSOLD BOUNCE       LONG   OPEN    SENT
40  SUI   OVERSOLD BOUNCE       LONG   OPEN    SENT
45  ETH   OVERBOUGHT REJECTION  SHORT  OPEN    SENT
```

Semantiknya sesuai untuk bootstrap: `OPEN` berarti trade belum dievaluasi menjadi
WIN/LOSS/EXPIRED, sehingga `(coin, setup, side)` itu harus dianggap episode aktif
agar restart tidak memperlakukannya sebagai edge baru.

### Perubahan bootstrap dan test

Commit perbaikan terpisah di branch fitur:

```text
122c61f fix: bootstrap signal edge state from open tracking
```

`engine/trading/signal_engine.py` sekarang, hanya saat field marker
`edge_signal_state_bootstrapped` belum ada pada state file, melakukan query
`signal_tracking` OPEN deterministic dan menulis setiap identity sebagai:

```json
{"active": true, "inactive_scans": 0}
```

Marker ikut tersimpan sehingga migrasi idempoten dan tidak akan meng-overwrite
edge state yang sudah berjalan pada startup berikutnya. Tidak ada perubahan pada
deteksi setup, RSI/ATR/threshold/RR, seleksi strategi, `shadow_e3`, atau checker
lain. Fixture gateway test juga diisolasi dari file state produksi agar test tidak
lagi mengotori `data/signal_state.json`.

Test bootstrap baru mencakup legacy state kosong + row OPEN deterministic lalu
memverifikasi key menjadi active dan evaluasi berikutnya menghasilkan
`suppressed_same_episode`; test kedua memverifikasi marker mencegah reseed.

```text
Focused: 20 passed, 3 warnings in 23.04s
Full pre-merge: 282 passed, 3 warnings, 74 subtests passed in 30.63s
Full post-merge: 282 passed, 3 warnings, 74 subtests passed in 30.87s
```

### Merge, backup, dan restart

Merge no-ff ke `main` berhasil:

```text
a953358 merge: deploy edge-triggered TRADE SIGNAL re-arm
```

Diff merge hanya empat file yang diizinkan: `.env.example`,
`engine/trading/signal_engine.py`, `tests/test_drawdown_broadcast_gate.py`, dan
`tests/test_signal_edge_triggered_rearm.py` (448 insertions, 11 deletions). Tidak
ada file strategi/checker lain dalam merge.

Backup state kedua dibuat sebelum restart:

```text
/opt/aliza-ai/data/signal_state.json.bak-20260727_095545
SHA-256 6026d68fe319659b1ddb9e75a5a807041bb68294ce015bf1ff5b15dd52c6139f
```

Sebelum restart, state yang sudah dibootstrap memuat marker `true` dan tiga key
active ARB/SUI/ETH di atas. `aliza-telegram.service` direstart pukul 09:57:00 WIB
dan tetap `active (running)`; journal tidak menunjukkan error
`signal_engine`, `state_store`, atau `observe_signal_validity`.

### STOP — safety gate kedua gagal, jangan push

Bootstrap DB sendiri berhasil, tetapi safety gate wajib tetap **gagal**. Dua scan
awal setelah restart menghasilkan kandidat ETH yang tidak lolos RR (2,75 dan
2,80); scan ketiga pada 09:59:56 mencapai debounce dan mereset episode:

```text
09:57:56 scan ... reject_rr=1 passed=0 rr_min=2.75
09:58:56 scan ... reject_rr=1 passed=0 rr_min=2.80
09:59:56 scan ... reject_rr=1 passed=0 rr_min=2.80
09:59:56 [TRADE SIGNAL EDGE] reset key=ETH|OVERBOUGHT REJECTION|SHORT invalid_scans=3 debounce=3
```

Ketika RR kemudian kembali valid, jalur dispatch menganggapnya edge baru walau
baris tracker ETH id 45 tetap `OPEN`:

```text
10:01:56 scan ... reject_rr=0 passed=1
10:01:56 [TRADE SIGNAL EDGE] new key=ETH|OVERBOUGHT REJECTION|SHORT
10:01:56 [SIGNAL] ETH|OVERBOUGHT REJECTION from deterministic
10:01:56 ALERT DISPATCHED via CENTRAL GATEWAY
10:02:59 [TRADE SIGNAL EDGE] suppressed_same_episode key=ETH|OVERBOUGHT REJECTION|SHORT
10:02:59 [BLOCKED] duplicate signal ETH|OVERBOUGHT REJECTION
```

Ini bukan bootstrap yang gagal membaca DB: state terbukti diisi active, lalu
di-reset oleh definisi core saat ini bahwa kandidat yang gagal filter RR adalah
`inactive`. Namun hasilnya masih melanggar safety criterion deployment: setup
tracker yang tetap `OPEN` dapat menjadi `new` dalam sekitar empat menit setelah
restart, bukan `suppressed_same_episode` sepanjang episode trade yang sama.

Query read-only sesudah event menunjukkan **tidak ada row tracking deterministic
baru** sejak 09:57 (open-trade guard mencegah duplicate row), tetapi Telegram
tetap menerima dispatch ETH baru. Karena perubahan ini menyentuh timing produksi
dan safety check meminta stop untuk temuan baru yang belum diantisipasi, observasi
30–60 menit, `git push origin main`, dan penghapusan branch **sengaja tidak
dilanjutkan**.

### Status akhir attempt kedua

| Tahap | Status |
|---|---|
| Bootstrap DB + test | selesai; 282 passed penuh |
| Backup kedua | selesai; SHA di atas |
| Merge `main` | selesai (`a953358`) |
| Restart | selesai, service sehat |
| Safety anti-dispatch bootstrap | **GAGAL**: ETH `new` pukul 10:01:56 setelah reset RR/debounce |
| Push `origin/main` | **tidak dilakukan** (`main` masih ahead 3) |
| Hapus branch fitur | **tidak dilakukan** |

Perlu review lanjutan sebelum push: apakah `OPEN` tracker harus menahan episode
sampai trade ditutup, atau apakah invalidation untuk edge harus dibedakan dari
gagal RR/confidence agar keadaan pasar yang sama tidak reset/re-fire hanya karena
RR berosilasi di ambang. Tidak ada perbaikan tambahan yang diimplementasikan
dalam attempt ini.


## Fix Lanjutan — Episode Mengikuti Row `OPEN` Tracker — 27 Juli 2026

### Keputusan diagnosis: identity episode diselaraskan

Sebelum fix ini, `EDGE_SIGNAL_STATE` memakai identity
`(coin, setup, side)`, tetapi secondary OPEN guard di
`engine/trading/signal_tracker.py` hanya mencari `(coin, setup, source)` dan
mengabaikan `side`. Ini tidak konsisten: LONG dan SHORT untuk coin/setup sama
adalah edge identity berbeda, sementara tracker sebelumnya menganggapnya satu
row OPEN yang sama.

Fix menyelaraskan kedua sisi ke identity kanonis:

```text
(coin, setup, side, source)
```

Normalisasi dilakukan pada coin (tanpa akhiran `USDT`), setup uppercase, side
`LONG`/`SHORT`, dan source lowercase. Kedua guard `record_signal()` (duplicate
exact-signal-time dan duplicate OPEN) sekarang memasukkan `side`; helper
`has_open_episode()` memakai query identity yang sama. Test membuktikan LONG dan
SHORT untuk `BTC|CUSTOM SETUP` dapat memiliki row OPEN independen, sementara
ulang identity yang sama ditolak.

`check_open_signals()` adalah titik terminal yang benar: ia mengubah row OPEN
menjadi `WIN`, `LOSS`, atau `EXPIRED`, melakukan `conn.commit()`, lalu secara
synchronous memanggil sinkronisasi edge ke inactive untuk row deterministic yang
baru tertutup. Dengan demikian re-arm tidak lagi bergantung pada hasil
TradingBrain/RR/confidence snapshot.

### Perubahan implementasi

Commit fix:

```text
5909856 fix: tie trade signal episodes to open tracking rows
```

- `engine/trading/signal_engine.py`
  - `observe_signal_validity()` menjadi compatibility no-op: RR/confidence tetap
    filter kelayakan dispatch baru, tetapi tidak pernah lagi me-reset episode row
    OPEN.
  - `can_send_signal()` menanyakan `signal_tracker.has_open_episode()` untuk
    identity penuh. Bila row OPEN ada, state dipulihkan/ditahan `active=true` dan
    hasilnya `suppressed_same_episode`, bahkan bila cache state lama menyatakan
    inactive.
  - State edge hanyalah mirror persisted; `record_signal_sent()` kini menyimpan
    floor TTL 900 detik saja. Commit row OPEN yang sukses menandai active;
    transisi terminal tracker menandai inactive.
  - `SIGNAL_REARM_DEBOUNCE_SCANS` dan dokumentasi `.env.example` dihapus karena
    tidak lagi relevan. `.env` produksi tidak disentuh.
- `engine/trading/signal_tracker.py`
  - tambah helper identity/query OPEN dan sinkronisasi lazy yang menghindari
    import-cycle;
  - row OPEN deterministic menandai episode active setelah commit;
  - `WIN`/`LOSS`/`EXPIRED` menandai inactive setelah commit.

Tidak ada perubahan pada deteksi TradingBrain, RSI, ATR, RR/confidence threshold,
strategy selection, `shadow_e3`, atau checker `notification_governor`.

### Test

Replay eksplisit ETH 27 Juli menggunakan row OPEN yang sama dan urutan RR
`2.75 -> 2.80 -> 2.80 -> 3.08`: scan invalid tidak mengubah `active`; scan valid
terakhir menghasilkan `suppressed_same_episode`, bukan `new`. Test juga mencakup:

1. Row OPEN menahan dispatch walau RR melewati ambang dan floor TTL sudah lewat.
2. Masing-masing `WIN`, `LOSS`, dan `EXPIRED` dari `check_open_signals()`
   menyinkronkan inactive; kandidat valid berikutnya dapat `new` setelah floor
   900 detik lewat.
3. Key tanpa row OPEN dapat `new` langsung.
4. Konsistensi `side` antara tracker guard dan edge state.
5. Bootstrap dari row OPEN dan isolasi `shadow_e3`/notification-governor.

```text
Focused: 30 passed, 3 warnings in 21.30s
Full pre-merge: 283 passed, 3 warnings, 74 subtests passed in 32.29s
Full post-merge: 283 passed, 3 warnings, 74 subtests passed in 30.92s
```

### Backup, merge, dan deploy

Backup state dibuat sebelum merge/restart dan byte-identik dengan source:

```text
/opt/aliza-ai/data/signal_state.json.bak-20260727_101905
SHA-256 2631398072509bd669fc9a762d75bf8c501bbe8d3a5ffca9b873ac38883a2d2b
```

Merge no-ff ke `main`:

```text
83b5e6d merge: tie TRADE SIGNAL episodes to open tracking
```

Merge hanya memuat `.env.example`, `engine/trading/signal_engine.py`,
`engine/trading/signal_tracker.py`, dan test edge. Service direstart 10:20:00
WIB dan tetap `active (running)` tanpa error `signal_engine`, `state_store`, atau
`observe_signal_validity`.

### Safety check produksi — LOLOS

Window observasi: **10:20:00–10:35:50 WIB** (15 menit 50 detik). Pada saat
restart, row deterministic OPEN adalah ARB id 38, SUI id 40, dan ETH id 45.
ETH adalah kandidat valid di setiap scan yang teramati (`passed=1`); seluruhnya
ditahan tanpa dispatch baru:

```text
10:20:58 scan ... passed=1
10:20:58 [TRADE SIGNAL EDGE] suppressed_same_episode key=ETH|OVERBOUGHT REJECTION|SHORT
10:20:58 [BLOCKED] duplicate signal ETH|OVERBOUGHT REJECTION
...
10:29:57 scan ... passed=1
10:29:57 [TRADE SIGNAL EDGE] suppressed_same_episode key=ETH|OVERBOUGHT REJECTION|SHORT
10:29:57 [BLOCKED] duplicate signal ETH|OVERBOUGHT REJECTION
...
10:34:57 scan ... passed=1
10:34:57 [TRADE SIGNAL EDGE] suppressed_same_episode key=ETH|OVERBOUGHT REJECTION|SHORT
10:34:57 [BLOCKED] duplicate signal ETH|OVERBOUGHT REJECTION
```

Total 14 scan valid ETH yang teramati menghasilkan `suppressed_same_episode`;
tidak ada tag `new`, `[SIGNAL]`, atau `ALERT DISPATCHED` trade untuk key OPEN
setelah restart. Query tracker juga tidak menemukan row deterministic baru sejak
10:20 WIB; id 38/40/45 semuanya tetap OPEN. Tidak ada row yang benar-benar closed
selama window ini, sehingga re-arm live sesudah close **BELUM TERAMATI LANGSUNG**;
perilaku tersebut tervalidasi oleh unit test terminal `WIN`/`LOSS`/`EXPIRED` di
atas.

### Push dan cleanup

`git push origin main` berhasil:

```text
48c1e9e..83b5e6d  main -> main
```

Branch lokal `fix/edge-gate-tied-to-open-row` dan
`feat/signal-edge-triggered-rearm` telah dihapus setelah push. Status akhir:
`main` sama dengan `origin/main`; service produksi aktif.
