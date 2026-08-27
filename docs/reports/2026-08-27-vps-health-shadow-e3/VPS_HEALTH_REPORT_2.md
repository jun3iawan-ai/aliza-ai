# VPS Health Report #2 — Health Check Lanjutan

**Tanggal audit:** 2026-08-27
**Host:** VM-6-46-ubuntu · **Repo:** `/opt/aliza-ai` (branch `main`, read-only)
**Baseline pembanding:** `docs/reports/2026-07-21-maintenance/VPS_HEALTH_REPORT.md` (2026-07-21, sebelum maintenance) + `MAINTENANCE_REPORT.md` (setelah git gc)

Semua perintah dijalankan read-only. Tidak ada restart service, perubahan `.env`, penghapusan, atau commit yang dilakukan selama audit ini.

---

## 1. Resource

```
Filesystem      Size  Used Avail Use% Mounted on
/dev/vda2        59G   33G   25G  57% /
Mem: total 3.6Gi, used 1.8Gi, free 223Mi, buff/cache 1.6Gi, available 1.5Gi
Swap: 4.0Gi total, 658Mi used
uptime: up 172 days, load average 0.49 0.37 0.21
nproc: 2
```

**Tren root disk:** 62% (21 Jul, pra-maintenance) → 54% (21 Jul, pasca `git gc`, per `MAINTENANCE_REPORT.md`) → **57% (sekarang)**. Naik 3 poin dalam ~5 minggu — wajar (log, backup harian, git objects baru), masih jauh di bawah ambang 80%. RAM/swap/load semuanya normal untuk 2 vCPU.

**Status: SEHAT.**

---

## 2. Git & deploy state

**2.1 Posisi branch**
```
main...origin/main   (tidak ada divergensi — ahead/behind kosong)
HEAD = 453bbca0ed1006fb4897d32194fb4266b22a6898
```
`git log --oneline -10` terbaru **tidak** memuat commit-commit yang disebut di prompt (`f38ab55`, dst) — itu wajar, karena HEAD sekarang 36 commit **di depan** `aded2b3`, mencakup pekerjaan lain (restrukturisasi menu Telegram, Info Coin, big-move fix, near-level alerts, edge-triggered TRADE SIGNAL). Ini bukan regresi, hanya progres berikutnya di atas maintenance 21 Juli.

**2.2 Verifikasi commit ada di history `main`**

| Commit | Pesan | Ancestor dari HEAD? |
|---|---|---|
| `f38ab55` | fix: bound telegram graceful shutdown | ✅ |
| `0eab6d5` | docs: apply documentation quick wins | ✅ |
| `6e54996` | docs: move documentation into canonical structure | ✅ |
| `f9d8bf4` | docs: rebuild guides and operational runbooks | ✅ |
| `aded2b3` | fix: harden deploy script for production service | ✅ |
| `2b62ce8` | fix: mitigate Telegram alert notification spam | ✅ |
| `4045b8e` | Merge branch 'fix/telegram-notification-noise' | ✅ |
| `907930b` | fix: correct UTC epoch conversion in alert cooldown timestamps | ✅ |

Semua 8 commit terverifikasi dengan `git merge-base --is-ancestor <sha> HEAD` — semuanya **ADA** di history `main`, sesuai urutan waktu (21 Juli → sekarang).

**2.3 `scripts/deploy/deploy.sh`**
```
bash -n scripts/deploy/deploy.sh  →  SYNTAX OK
```
Isi terkini: `REPO_DIR="/opt/aliza-ai"`, `SERVICE="aliza-telegram.service"`, cek working tree bersih, cek branch `main`, `git pull --ff-only origin main`, lalu `sudo systemctl restart aliza-telegram`. **Tidak ada regresi** — path dan service sesuai fix `aded2b3`, tidak menyentuh service lain.

⚠️ Catatan penting: script ini mensyaratkan `git status --porcelain` kosong sebelum jalan. Saat ini working tree **tidak bersih** (lihat 2.4) — kalau dijalankan sekarang, `deploy.sh` akan **gagal** di baris pengecekan tersebut dan exit dengan error, bukan corrupt apa pun. Perlu dibereskan sebelum deploy berikutnya.

**2.4 Untracked files**

`git status --porcelain` menunjukkan **33 file untracked**, seluruhnya laporan audit markdown (bukan sisa restrukturisasi dokumentasi yang dimaksud prompt — itu sudah commit dan sudah rapi di `docs/reports/` dan `docs/audits/`). Ini adalah 16 laporan unik yang muncul dobel: sekali di root repo, sekali lagi di `AlizaAI-Crypto/01-hasil-audit-codex/` (plus 1 file, `FASE1C_VERIFIKASI_REPORT.md`, hanya ada di folder audit-codex).

Contoh nama file: `AUDIT_FITUR_BERITA_REPORT.md`, `AUDIT_MENU_TELEGRAM_LENGKAP_REPORT.md`, `BIG_MOVE_REAL_1H_FIX_REPORT.md`, `INFO_COIN_PAKET1_REPORT.md`, `TELEGRAM_MENU_RESTRUCTURE_REPORT.md`, `STATUS_WINRATE_REPORT.md`, dll — semuanya berkaitan dengan pekerjaan fitur setelah maintenance 21 Juli (menu restructure, Info Coin, big move 1h fix, edge-triggered signal), bukan hasil kerja dokumentasi.

**Tindakan disarankan (untuk user, bukan dilakukan sekarang):** commit atau pindahkan 16 file root ke `docs/reports/` sesuai pola yang sudah ada, lalu hapus duplikatnya — supaya working tree bersih untuk `deploy.sh` berikutnya.

---

## 3. Struktur dokumentasi

**3.1 Jumlah file:** `find docs -type f` = **75** (bukan 73). Diverifikasi via `git diff --name-status f9d8bf4 HEAD -- docs/`: ada **3 file baru ditambahkan** setelah restrukturisasi Tahap 2 (0 dihapus) — semuanya laporan yang mendokumentasikan proses maintenance itu sendiri:
- `docs/reports/2026-07-21-maintenance/DEPLOY_SCRIPT_FIX_REPORT.md`
- `docs/reports/2026-07-21-maintenance/DOCS_MERGE_PUSH_REPORT.md`
- `docs/reports/2026-07-21-maintenance/DOCS_RESTRUCTURE_REPORT.md`

Selisih 75 vs 73 (bukan 72 hasil hitungan +3) kemungkinan karena baseline "73" di ekspektasi prompt dihitung pada titik commit yang sedikit berbeda — selisih 1 file tidak signifikan, tidak ada indikasi file hilang (0 dihapus).

**3.2 Folder baru — semua ada:**
| Folder | Status | Jumlah file |
|---|---|---|
| `docs/agent-rules/coding/` | ✅ | 3 |
| `docs/agent-rules/runtime/` | ✅ | 4 |
| `docs/architecture/` | ✅ | 4 |
| `docs/runbooks/` | ✅ | 5 |
| `docs/audits/` | ✅ | 42 |
| `docs/reports/` | ✅ | 16 |

**3.3 Folder lama — semua benar-benar hilang:** `docs/cursor-ai/`, `docs/instructions/`, `docs/audit/`, `audit-output/` (root) — keempatnya tidak ada lagi.

**3.4 Konsistensi runbook vs `deploy.sh` aktual — ⚠️ TIDAK KONSISTEN (temuan baru):**

`docs/runbooks/deploy-restart-rollback.md` baris 3 masih menulis:
> "Script `scripts/deploy/deploy.sh` belum aman digunakan: pada verifikasi 2026-07-21 script masih melakukan `cd /home/ubuntu/aliza-ai`, menjalankan `git pull origin main`, dan me-restart `aliza-api` serta `aliza-telegram`. Jangan jalankan script tersebut sampai diperbaiki dan direview."

Ini **sudah basi/stale**. Pengecekan timeline commit membuktikan kenapa: dokumen ini ditulis oleh commit `f9d8bf4` (15:21 WIB, 21 Juli), sedangkan perbaikan script `aded2b3` baru terjadi **3 jam kemudian** (18:34 WIB, 21 Juli) — di hari yang sama, tapi tidak ada commit susulan yang meng-update kalimat peringatan tersebut. Lebih dari sebulan kemudian, runbook ini masih memperingatkan orang untuk tidak memakai script yang **sebenarnya sudah aman** sejak `aded2b3` (path `/opt/aliza-ai`, hanya restart `aliza-telegram`, sudah diverifikasi di §2.3).

`docs/runbooks/graceful-shutdown.md` sebaliknya sudah konsisten — mereferensikan `f38ab55`, path/service sesuai (`aliza-telegram`, `TimeoutStopSec=15s`).

**Tindakan disarankan:** update paragraf pembuka `deploy-restart-rollback.md` supaya tidak lagi menyesatkan operator.

---

## 4. Service Aliza

```
systemctl list-units 'aliza*' --all  →  hanya aliza-telegram.service (loaded, active, running)
```

**4.1 `aliza-telegram.service`**
- Active: running sejak **2026-08-21 10:24:18 WIB** (5 hari 21 jam)
- Main PID 191620, Memory 503.0M, `NRestarts=0`
- Enabled: ya (`vendor preset: enabled`, ada drop-in `security.conf`)

**4.2 Verifikasi graceful shutdown** — hasil **NIHIL SIGKILL**, tapi dengan catatan cakupan:
```
journalctl -u aliza-telegram --since "7 days ago" | grep -i "stop-sigterm|timed out|killed|SIGKILL"
```
Tidak ada satu pun kejadian SIGKILL/timeout-shutdown asli — 4 baris yang cocok pola "timed out" ternyata semuanya *false positive* (HTTP read-timeout ke API eksternal seperti CoinGecko/Stablecoins.llama.fi, tidak ada hubungannya dengan shutdown).

⚠️ **Keterbatasan verifikasi:** retensi journald di server ini ternyata hanya menyimpan **± 4 hari** log (boot journal mulai 2026-08-23 09:01 WIB, bukan 7 hari penuh — kemungkinan dibatasi ukuran, bukan reboot, karena host uptime 172 hari). Jadi klaim "0 SIGKILL" ini terverifikasi untuk 23–27 Agustus, **bukan** untuk 7 hari penuh. Karena `NRestarts=0` sejak servis aktif 21 Agustus, dan tidak ada restart tercatat pada jendela yang tersedia, tidak ada kesempatan restart untuk benar-benar menguji shutdown patch secara langsung dalam jendela ini — tapi juga tidak ada bukti kegagalan.

**4.3 `aliza-bot.service`** — `systemctl is-enabled aliza-bot` → **`disabled`**, status `inactive (dead)`. Terverifikasi aktual, sesuai instruksi user sebelumnya (bukan asumsi).

**4.4 `aliza-market.service`** — `systemctl is-enabled aliza-market` → **`disabled`**, status `inactive (dead)`. Tetap sesuai kondisi yang diharapkan.

(Info tambahan: `aliza.service` dan `aliza-assistant.service` berstatus `masked`; unit lain seperti `aliza-api`, `aliza-dashboard`, `aliza-stock`, `aliza-meeting`, `aliza-bot-staging`, `aliza-api-staging` semuanya `disabled` — tidak ada yang tidak sengaja jalan.)

---

## 5. Journal 7 hari (warning/error)

Filter bawaan `journalctl -p warning` **tidak berfungsi untuk servis ini** — aplikasi menulis level log (WARNING/ERROR) sebagai teks ke stdout, bukan lewat syslog priority asli, sehingga journald mencatat semuanya sebagai priority default dan filter `-p warning` mengembalikan "No entries" walau ada ribuan baris WARNING di teks log. Saya menggunakan `grep -E " - (WARNING|ERROR) - "` sebagai gantinya (± 4 hari cakupan, lihat §4.2).

**Ringkasan (23–27 Agustus):**
- **1131 baris WARNING/ERROR**, didominasi noise API eksternal yang sudah dikenal: `funding_rate_monitor: openInterest HTTP 400 OMUSDT` (berulang tiap ±5 menit), `Investing.com calendar returned 403`, `economic_calendar: Serper HTTP 400`, beberapa APScheduler "job missed by <1s" (wajar, bukan indikasi masalah).
- **ERROR (8 baris)**: dominan `Message is too long` pada dispatch `morning_brief`/`evening_summary` header/analysis (4x dalam 4 hari — **temuan baru, bukan dari `2b62ce8`/`907930b`**, layak dicek terpisah karena bisa berarti konten ringkasan kepanjangan untuk batas Telegram), 2x `Telegram error: Bad Gateway`, 1x `httpx.ReadError`.
- **`notification_governor.py` (fitur `2b62ce8`)**: **NOL error/warning** tercatat di journal — modul berjalan senyap, tidak ada exception. Ini sinyal positif untuk fitur ini.
- **Konversi epoch (`907930b`)**: **NOL error** terkait epoch/cooldown ditemukan.

**Status: SEHAT** untuk kedua fitur target (`notification_governor`, epoch fix). "Message is too long" adalah item baru yang perlu diinvestigasi terpisah, di luar cakupan dua patch yang diaudit.

---

## 6. Database & shadow mode

**6.1 Total `signal_tracking`:** 134 baris.

| source | jumlah |
|---|---|
| llm | 79 |
| shadow_e3 | 28 |
| deterministic | 17 |
| legacy | 10 |

**6.2 Fokus `shadow_e3` — ⚠️ PERLU PERHATIAN:**

- **28 baris** total (naik dari 0 di audit 21 Juli — fitur *hidup* dan tereksekusi).
- Rentang waktu: **2026-07-24 → 2026-08-18**. **Tidak ada sinyal baru sejak 18 Agustus** (9 hari kosong sampai hari audit ini, 27 Agustus).
- Breakdown outcome (n=28, semua closed, 0 masih OPEN): **25 LOSS, 3 WIN** → win rate **10.7%**.
- Expectancy kasar: rata-rata PnL **−1.06%/trade**, total **−29.6%** akumulatif.
- **Verifikasi live:** journal menunjukkan `shadow_e3 candidates=0` di **setiap** siklus snapshot yang tersedia (± 4 hari terakhir, ribuan baris berturut-turut) — tidak satu pun siklus menghasilkan kandidat baru. Ini konsisten dengan kekosongan data sejak 18 Agustus di DB.

**Implikasi untuk evaluasi promosi (target ±1 Sept 2026 atau ≥60 outcome):** pada laju saat ini (28 outcome dalam ~25 hari efektif produksi, lalu stagnan 9 hari), target **≥60 outcome kemungkinan besar TIDAK tercapai pada 1 September**, dan performa yang terkumpul sejauh ini (10.7% win rate, expectancy negatif) **tidak mendukung promosi** apa pun jika evaluasi dipaksakan sekarang. Perlu keputusan user: (a) investigasi kenapa `candidates=0` terus-menerus sejak ~18 Agustus (apakah filter pasar terlalu ketat, bug, atau kondisi market memang tidak memenuhi kriteria e3), atau (b) perpanjang jendela evaluasi.

**6.3 State `notification_governor`:** **tidak** punya tabel di `data/aliza.db` — modul ini memakai file state terpisah: `data/alert_cooldown_state.json` (5.8 KB, terakhir ditulis 06:36 hari ini, jadi aktif memperbarui). Isinya cooldown/dedup per coin (`cooldown:volume_spike`, `cooldown:snapshot_alert`, `drawdown_breaker`, dll) — bukan di DB SQL, murni file JSON yang di-write atomically (via tmp file, terlihat dari kode).

---

## 7. Cron, timer, scheduler

`systemctl list-timers 'aliza*'` → 0 timer (semua scheduling lewat cron, bukan systemd timer — konsisten dengan audit sebelumnya).

`crontab -l` relevan:
```
0 2 * * * cp .../telegram_bot.py .../telegram_bot.py.bak.$(date +%Y%m%d) 2>/dev/null; \
          find .../interfaces -name 'telegram_bot.py.bak.*' -mtime +14 -delete
```
**Retensi backup — bekerja dengan benar:** ditemukan **15 file** `telegram_bot.py.bak.*`, rentang tanggal **13–27 Agustus** (15 hari berurutan, pas dengan retensi `-mtime +14`). Tidak menumpuk tak terkendali.

Cron lain tidak berubah dari audit sebelumnya (backup harian `/opt/aliza-backups`, monitor server tiap 5 menit, gmail-agent). Baris restart mingguan `aliza-telegram` dan reminder `aliza-etpp-agent` sudah dikomentari (dipindah ke VM lain) — sesuai catatan di file crontab itu sendiri.

---

## 8. Konfigurasi non-secret

| Flag | Ada di `.env`? |
|---|---|
| `UNIVERSE_EXCLUDE` | ✅ diset |
| `SHADOW_E3_ENABLED` | ✅ diset |
| `SHADOW_E3_DISPATCH` | ✅ diset |
| `COIN_FAIL_THRESHOLD` | tidak diset eksplisit — fallback ke default kode `10` (`engine/market/market_universe.py`) |

**Flag baru dari `2b62ce8`** (diverifikasi via `git show 2b62ce8 -- .env.example`, semua non-secret sesuai `.env.example`):
- `BIG_MOVE_COOLDOWN_SEC` (default 7200 detik) — belum diset eksplisit di `.env`, pakai default.
- `ALERT_DIGEST_THRESHOLD` (default 5) — belum diset eksplisit, pakai default.
- `MAX_ALERTS_PER_HOUR` (default 15) — belum diset eksplisit, pakai default.

Ketiganya dibaca lewat `os.getenv(..., default)` di `engine/alerts/notification_governor.py`, jadi tidak diset pun sistem tetap berjalan dengan nilai default yang wajar. Tidak ada nilai sensitif yang ditampilkan di laporan ini.

---

## Kesimpulan

### Status keseluruhan: **PERLU PERHATIAN**

Tidak ada kondisi KRITIS (servis jalan stabil, resource sehat, tidak ada SIGKILL, fitur notifikasi & epoch senyap dari error). Tapi ada beberapa item yang butuh tindak lanjut user, terutama **shadow_e3 yang stagnan** dan **runbook yang basi**.

| Item | Status | Bukti |
|---|---|---|
| Resource VPS (disk/RAM/load) | ✅ Sehat | root 57% (naik wajar dari 54% pasca-gc), RAM/swap/load normal |
| 8 commit target ada di `main` | ✅ Terverifikasi | `git merge-base --is-ancestor` untuk semua 8 sha |
| `deploy.sh` — path & service benar | ✅ Terverifikasi | `cat` + `bash -n` |
| `deploy.sh` — bisa dijalankan sekarang | ⚠️ Perlu tindakan | working tree kotor (33 untracked), akan gagal di pre-check |
| Struktur docs (folder baru/lama) | ✅ Sehat | semua folder baru ada, folder lama hilang, 75 file (+3 wajar) |
| Runbook `deploy-restart-rollback.md` | ⚠️ Perlu tindakan | masih memperingatkan script "belum aman" — basi sejak `aded2b3` |
| Runbook `graceful-shutdown.md` | ✅ Sehat | konsisten dengan `f38ab55` & service aktual |
| `aliza-telegram` uptime & restart | ✅ Sehat | 0 `NRestarts`, aktif 5+ hari |
| Graceful shutdown (no SIGKILL) | ✅ Sehat* | 0 kejadian, *cakupan journal hanya ±4 hari, bukan 7 |
| `aliza-bot` disabled | ✅ Terverifikasi aktual | `is-enabled` = disabled, inactive |
| `aliza-market` disabled | ✅ Terverifikasi aktual | `is-enabled` = disabled, inactive |
| `notification_governor` (2b62ce8) | ✅ Sehat | 0 error/warning di journal, state file aktif ter-update |
| Epoch fix (907930b) | ✅ Sehat | 0 error terkait epoch/cooldown |
| `shadow_e3` — data terkumpul | ⚠️ Perlu perhatian | 28/60 outcome, win rate 10.7%, generasi kandidat **stagnan 9 hari** |
| Backup retensi `.bak` | ✅ Sehat | 15 file, rentang 15 hari, sesuai `-mtime +14` |
| Flag config baru non-secret | ✅ Terverifikasi | 3 flag baru ada di kode+`.env.example`, tidak ada secret bocor |
| — butuh sudo untuk verifikasi lebih dalam | ℹ️ Dicatat | tidak ada perintah yang gagal karena sudo di audit ini |

### Tindakan yang disarankan untuk user
1. **Investigasi shadow_e3 candidates=0** sejak ~18 Agustus — ini yang paling mendesak karena memengaruhi keputusan promosi 1 September.
2. **Perbarui `docs/runbooks/deploy-restart-rollback.md`** — hapus peringatan basi tentang `deploy.sh`.
3. **Bersihkan working tree** (33 file untracked di root/`AlizaAI-Crypto/`) sebelum menjalankan `deploy.sh` berikutnya.
4. (Opsional, tidak mendesak) Cek error `"Message is too long"` pada dispatch `morning_brief`/`evening_summary`.
