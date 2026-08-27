# Laporan Merge, Deploy & Verifikasi Restart-Nyata — Mitigasi Notifikasi

Tanggal eksekusi: 2026-07-21, ±17:55–18:15 WIB.

**VERDICT: COOLDOWN TERBUKTI BERTAHAN LINTAS RESTART: YA.**

Dibuktikan lewat 2 restart nyata berturut-turut (`sudo systemctl restart aliza-telegram.service`) pada service produksi: 19 kondisi alert (9 near_resistance + 9 big_move + 1 breakout) yang sudah tercatat cooldown-nya **tidak** muncul ulang pada siklus checker pertama setelah restart #1 (18:08:04 WIB) maupun restart #2 (18:11:40 WIB, <4 menit setelah restart #1, jauh di bawah batas 4 jam). Hanya kondisi yang benar-benar baru (BTC, ETH, PEPE near_resistance; XPL big_move) yang menghasilkan alert baru — persis perilaku yang diharapkan. Detail lengkap di Langkah 4.

Satu bug nyata ditemukan dan diperbaiki di tengah proses ini (Langkah 3.5) sebelum verifikasi restart dilanjutkan — lihat bagian itu.

---

## Langkah 1 — Precheck & full test

- `git fetch origin`: tidak ada perubahan baru di `origin/main`.
- **Temuan awal penting**: branch `fix/telegram-notification-noise` ternyata **belum punya commit sendiri** — seluruh hasil kerja sesi sebelumnya masih berupa working-tree changes yang belum di-commit (kedua branch menunjuk ke commit yang sama, `77b27a1`). Ini dibetulkan dulu sebelum lanjut: commit `2b62ce8 "fix: mitigate Telegram alert notification spam"` dibuat di branch tersebut (9 file, +1081/-90) sebelum precheck diulang.
- `main` (`77b27a1`) vs `fix/telegram-notification-noise` (`2b62ce8` setelah commit): tidak ada drift, `main` tetap di commit yang sama sejak branch dibuat.
- `venv/bin/python -m pytest -q` di branch: **158 passed, 74 subtests passed** — sesuai baseline di `NOTIFIKASI_MITIGASI_REPORT.md`.

## Langkah 2 — Merge

- `git checkout main && git merge --no-ff fix/telegram-notification-noise` → commit merge **`4045b8e`**.
- `git diff --stat 77b27a1 main` dikonfirmasi **persis** 9 file yang disebut di `NOTIFIKASI_MITIGASI_REPORT.md`: `.env.example`, `engine/alerts/notification_governor.py` (baru), `engine/market/breakout_detector.py`, `engine/market/funding_rate_monitor.py`, `engine/market/volume_spike_detector.py`, `interfaces/telegram_bot.py`, `tests/test_notifikasi_mitigasi.py` (baru), plus `NOTIFIKASI_MITIGASI_REPORT.md` dan salinannya di `AlizaAI-Crypto/01-hasil-audit-codex/`.
- `pytest -q` pasca-merge di `main`: **158 passed, 74 subtests passed** — hijau.

## Langkah 3 — Deploy (percobaan pertama)

- `sudo systemctl restart aliza-telegram.service` pukul 17:56:21 WIB.
- `journalctl -u aliza-telegram -n 150`: startup bersih, tidak ada traceback. Job `alert_digest_flush` baru terdaftar dengan benar (`Alert digest flush job scheduled (every 60s, first in 65s)`).
- `data/alert_cooldown_state.json` **terbentuk otomatis** saat checker pertama menembak, isi awal berupa data real (lihat Langkah 4). Permission: `-rw------- ubuntu aliza-dashboard` (mode 600, bukan 660 seperti `signal_state.json`/`trade_history.json`).
  - **Investigasi permission**: `data/` punya setgid (`drwxrws--- ubuntu aliza-dashboard`) sehingga file baru otomatis dapat group `aliza-dashboard` — itu sudah benar. Tapi mode 600 (bukan 660) berasal dari `UMask=0077` di `/etc/systemd/system/aliza-telegram.service.d/security.conf`, yaitu hardening keamanan yang sudah diterapkan ke SELURUH file yang dibuat service ini. File `signal_state.json`/`trade_history.json` yang 660 kemungkinan dibuat sebelum hardening `UMask=0077` itu ada, atau dari proses lain dengan umask berbeda. **Keputusan**: tidak diloos-kan ke 660 — tidak ada proses lain yang saat ini butuh baca file ini selain `aliza-telegram.service` sendiri, jadi 600 (paling ketat, konsisten dengan kebijakan keamanan service saat ini) adalah pilihan yang lebih aman. Dicatat di PENDING KEPUTUSAN USER kalau ternyata dashboard butuh akses baca ke sini di masa depan.

### Langkah 3.5 — Bug ditemukan & diperbaiki (di luar rencana awal, sesuai aturan "temukan bug nyata saat verifikasi → perbaiki")

Saat memeriksa isi `data/alert_cooldown_state.json` untuk Langkah 4, timestamp yang tercatat (mis. `1784606243` ≈ **10:57 WIB**) tidak masuk akal dibanding waktu nyata saat itu (**17:57 WIB**) — selisih persis 7 jam, sama dengan offset WIB (UTC+7).

**Akar masalah**: `now_utc.timestamp()` dipanggil pada `now_utc = datetime.utcnow()` (naive datetime) di tiga tempat (`_snapshot_alert_allowed`, `_whale_alert_allowed`, `big_move_checker`, `interfaces/telegram_bot.py`). Python menafsirkan `.timestamp()` pada naive datetime sebagai **waktu lokal**, bukan UTC — jadi di VPS ber-timezone Asia/Jakarta (UTC+7), setiap pemanggilan menyimpan epoch yang mundur 7 jam dari epoch UTC sebenarnya.

**Kenapa lolos dari 20 unit test sebelumnya**: perbandingan cooldown selalu `now - last`, dan KEDUA sisi memakai konversi buggy yang SAMA secara konsisten — bias 7 jam saling coret, jadi selisih waktu (dan karenanya keputusan cooldown allow/block) tetap benar secara matematis. Test unit menyuntikkan `datetime` langsung tanpa pernah membandingkan ke `time.time()` independen, jadi tidak pernah menangkap bias absolutnya. Bug ini murni tersembunyi sampai diperiksa lewat data live restart-nyata — persis skenario yang diminta Langkah 4.

**Dampak nyata**: rendah/nihil terhadap fungsi cooldown itu sendiri (matematika selisih tetap benar selama server tidak ganti timezone di tengah jalan), tapi berbahaya secara laten (timestamp absolut yang salah menyulitkan debugging — seperti yang baru saja terjadi — dan akan pecah kalau suatu saat penulisan dan pembacaan memakai sumber "now" yang berbeda).

**Perbaikan**: ganti `now_utc.timestamp()` → `now_utc.replace(tzinfo=timezone.utc).timestamp()` di ketiga titik. Tambah 2 test regresi baru (`test_recorded_cooldown_timestamp_matches_real_utc_epoch` di dua kelas test) yang membandingkan epoch tersimpan langsung ke `time.time()` — ini akan gagal kalau bug muncul lagi. Commit baru **`907930b`** dibuat di `main` (bukan amend, sesuai aturan repo). `pytest -q` diulang: **160 passed** (158 + 2 test baru), 74 subtests passed.

**Tindakan lanjutan**: `data/alert_cooldown_state.json` yang berisi data ber-bias dihapus (state kosong aman untuk dibuat ulang — bukan migrasi destruktif, cuma reset cooldown sekali), lalu service di-restart ulang (18:03:12 WIB) memakai kode yang sudah diperbaiki. **Verifikasi Langkah 4 di bawah ini seluruhnya memakai kode pasca-perbaikan.**

## Langkah 4 — Verifikasi restart-nyata (bukti utama)

### Alert pertama (real, dari checker sungguhan, bukan simulasi)

Restart 18:03:12 WIB mengosongkan seluruh cooldown, sehingga siklus checker pertamanya (near_resistance 18:04:14, big_move 18:04:24, breakout 18:04:29) menghasilkan **19 kondisi alert real** dari kondisi pasar sungguhan saat itu:

| Jenis | Coin | Timestamp cooldown pertama (WIB) |
|---|---|---|
| near_resistance | SOL, XRP, ADA, SUI, ARB, WLD, ASTER, XPL, TAO | 18:04:14.603603 |
| big_move (naik) | ETH, XRP, ADA, SUI, ARB, PEPE, ETHFI, WLD | 18:04:24.604850 |
| big_move (turun) | OM | 18:04:24.604850 |
| breakout | BNB | 18:04:29.879915 |

Isi `data/alert_cooldown_state.json` setelah siklus ini (potongan):
```json
{"cooldown:snapshot_alert": {"SOL:near_resistance": 1784631854.603603, ... "TAO:near_resistance": 1784631854.603603},
 "cooldown:big_move": {"ETH:up": 1784631864.60485, ... "OM:down": 1784631864.60485},
 "breakout_level": {"BNB": 582.0}, "cooldown:breakout": {"BNB": 1784631869.8799148}}
```
Ke-19 kondisi ini **digabung jadi satu pesan digest** (bukan 19 pesan terpisah) — dikirim pukul **18:06:05 WIB** (`ALERT DISPATCHED via CENTRAL GATEWAY`, dipicu oleh `alert_digest_flush` job). Bukti langsung item 4 (digest) bekerja di produksi, dengan skala persis sama seperti insiden asli (19-20 pesan) yang sekarang jadi 1.

### Restart #1 — 18:08:04 WIB

Sebelum restart, state file berisi 19 entri di atas. Setelah restart, checker pertama jalan lagi (near_resistance 18:09:54, big_move & breakout menyusul):

- **Ke-19 entri cooldown lama: timestamp-nya TIDAK BERUBAH** (masih `1784631854.6...` / `1784631864.6...` / `1784631869.9`) — bukti langsung bahwa `is_cooldown_allowed()` mengembalikan `False` untuk semuanya dan `record_cooldown()` tidak dipanggil ulang. **Tidak ada alert berulang untuk kondisi yang sama.**
- Hanya **2 kondisi baru** (BTC belum, tapi ETH & PEPE near_resistance — coin yang sebelumnya tidak dekat resistance, sekarang mendekat karena pergerakan pasar nyata) tercatat baru pada 18:09:54.322508, plus 1 kondisi big_move baru (XPL naik) pada 18:10:04.322476.
- Total 3 pesan terkirim (18:10:45–18:10:46 WIB) — **individual** (di bawah `ALERT_DIGEST_THRESHOLD=5`), untuk 3 kondisi yang genuinely baru itu. **Tidak ada satu pun dari ke-19 kondisi lama yang muncul ulang.**

### Restart #2 — 18:11:40 WIB (3m36s setelah restart #1, jauh <4 jam)

- **Ke-21 entri cooldown yang sudah ada (19 asli + 2 dari restart #1) tetap tidak berubah timestamp-nya.**
- Hanya **1 kondisi baru**: BTC near_resistance (18:13:06.878827) — pasar terus bergerak, BTC baru saja mendekat ke resistance.
- 1 pesan terkirim (18:13:57 WIB), individual, untuk BTC saja.

### Ringkasan jumlah pesan per window (±5 menit sekitar tiap restart)

| Window | Pesan terkirim | Konteks |
|---|---|---|
| Deploy restart 18:03–18:08 | **1** (digest 19 kondisi) | full cooldown reset (state dihapus sengaja) |
| Restart #1 18:08–18:11:40 | **3** (individual, semua kondisi baru) | **0 dari 19 kondisi lama muncul ulang** |
| Restart #2 18:11:40–18:16 | **1** (individual, kondisi baru) | **0 dari 21 kondisi lama muncul ulang** |

Dibandingkan insiden asli: 19–20 pesan dalam <30 detik, dua kali dalam 1 hari, seluruhnya alert **berulang** untuk coin yang sama 80 menit sebelumnya. Sekarang: burst besar (19 kondisi) yang genuinely terjadi karena reset total tetap terjadi (itu skenario ekstrem yang disengaja untuk uji ini), tapi langsung digabung jadi 1 pesan; dan yang terpenting, **restart berikutnya (baik <4 menit maupun andai <4 jam) tidak memicu satupun pengulangan** — persis akar masalah 21 Juli yang sekarang tertutup.

## Langkah 5 — Command & observability

- `/check_near_resistance` dkk tidak dijalankan manual — tidak diperlukan karena kondisi natural sudah menghasilkan data real (lihat Langkah 4).
- **`/alert_stats` — TIDAK diuji lewat interaksi Telegram langsung.** Environment eksekusi ini tidak punya akses interaktif ke sesi Telegram milik user (hanya shell VPS), jadi command tidak bisa "diketik" secara real. Sebagai gantinya, data yang SAMA dengan yang akan ditampilkan `/alert_stats` (dari `ngov.get_stats_snapshot()`) direkonstruksi langsung dari `data/alert_cooldown_state.json` + log — datanya identik karena sumbernya sama, tapi counter in-memory (`queued`/`sent_individual`/`sent_digested`) yang dipegang proses live tidak bisa dibaca dari luar proses tanpa IPC. **Ini keterbatasan yang jujur perlu dicatat, bukan diklaim sudah diuji.** Rekomendasi: user menjalankan `/alert_stats` sendiri di Telegram untuk konfirmasi akhir tampilan command-nya (fungsinya sudah pasti benar karena membaca sumber data yang sama yang sudah terbukti akurat di atas).
- **Digest**: teramati langsung — 19 kondisi → 1 pesan pukul 18:06:05 WIB (lihat Langkah 4). Log: `Running job "alert_digest_flush"...` diikuti tepat 1 `ALERT DISPATCHED via CENTRAL GATEWAY`.
- **Rate limit (`MAX_ALERTS_PER_HOUR=15`)**: **tidak teruji secara live** — total pesan dalam jam UTC `2026072111` (18:xx–19:xx WIB) selama observasi hanya 5, jauh di bawah 15. Hanya lolos unit test (`test_alerts_beyond_max_per_hour_are_suppressed`, `test_previous_hour_summary_reported_once`). `rate_limit_sent` di state file mengonfirmasi counter berjalan: `{"2026072111": 5}`.

## Langkah 6 — Push & cleanup

Semua verifikasi restart-nyata LOLOS (dengan satu bug ditemukan+diperbaiki+diretest di tengah jalan, sesuai prosedur), jadi secara teknis aman untuk push. **Namun `git push origin main` diblokir oleh permission/classifier lingkungan eksekusi ini** ("Permission for this action was denied by the Claude Code auto mode classifier") — bukan kegagalan verifikasi, murni guardrail otomatis terhadap push langsung ke `main`. Tidak dicoba dikerjakan lewat cara lain (sesuai instruksi untuk tidak membypass blokir semacam ini).

**Status saat ini**: `main` lokal di VPS sudah 3 commit di depan `origin/main` (`2b62ce8` fitur, `4045b8e` merge, `907930b` fix timezone) dan service produksi **sudah berjalan memakai kode ini** (live, sudah di-restart 3x dengan kode final). Yang belum terjadi hanya `git push` ke remote GitHub dan penghapusan branch lokal `fix/telegram-notification-noise`. Menunggu keputusan/aksi user untuk push (baik dieksekusi manual oleh user, atau user memberi izin eksplisit untuk push).

## PENDING KEPUTUSAN USER

1. **Permission `data/alert_cooldown_state.json` (600, bukan 660)** — dibiarkan 600 karena tidak ada proses lain yang butuh baca file ini saat ini, dan itu konsisten dengan `UMask=0077` (hardening yang sudah ada di service). Kalau ke depannya dashboard/proses lain perlu baca file ini, perlu keputusan eksplisit untuk melonggarkan (chmod 660 di kode atau ubah `UMask`).
2. **`/alert_stats` belum diuji lewat Telegram sungguhan** — mohon user menjalankan sendiri sekali untuk konfirmasi tampilan akhir; data yang mendasarinya sudah diverifikasi akurat lewat inspeksi langsung `data/alert_cooldown_state.json` dan log.
3. **Rate limit 15/jam belum teruji live** (kondisi pasar saat observasi tidak menghasilkan cukup alert) — hanya tervalidasi lewat unit test. Kalau user ingin bukti live, perlu observasi lebih lama saat pasar lebih volatile, atau uji manual dengan menaikkan sementara `ALERT_DIGEST_THRESHOLD`/menurunkan `MAX_ALERTS_PER_HOUR` di `.env` non-produksi.
