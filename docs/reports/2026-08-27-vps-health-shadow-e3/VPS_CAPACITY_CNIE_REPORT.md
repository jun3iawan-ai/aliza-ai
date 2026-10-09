# Audit Kapasitas VPS untuk CNIE (Crypto News Impact Engine)

**Tanggal audit:** 2026-08-27
**Host:** `VM-6-46-ubuntu` · **Repo:** `/opt/aliza-ai` (branch `main`, bersih, read-only)
**Sifat audit:** READ-ONLY MURNI — tidak ada instalasi paket, tidak ada perubahan config/`.env`, tidak ada service/file baru dibuat, tidak ada restart service. Satu-satunya file yang ditulis adalah laporan ini (dan salinannya).

---

## Bagian 1 — Spesifikasi & Utilisasi VPS Saat Ini

### 1.1 Spesifikasi mentah

```
nproc --all       : 2
uname -a          : Linux VM-6-46-ubuntu 5.15.0-171-generic #181-Ubuntu SMP Fri Feb 6 22:44:50 UTC 2026 x86_64 GNU/Linux
lscpu (ringkas)   : Intel(R) Xeon(R) Platinum 8255C CPU @ 2.50GHz, 1 socket, 2 core, 1 thread/core,
                    Hypervisor vendor: KVM, Virtualization: full (VM tervirtualisasi, bukan bare metal)

free -h:
               total        used        free      shared  buff/cache   available
Mem:           3.6Gi        1.4Gi       640Mi       4.0Mi      1.6Gi        2.0Gi
Swap:          4.0Gi        1.1Gi       2.9Gi

df -h:
Filesystem      Size  Used Avail Use% Mounted on
/dev/vda2        59G   32G   25G  57% /
```

**Provider/tier — dmidecode:** `dmidecode -s system-product-name` gagal dengan `Permission denied` (butuh akses ke `/dev/mem` / SMBIOS table, perlu root). **TIDAK PASTI — butuh sudo, tidak bisa dijalankan di sesi ini.**

Catatan tambahan (bukti tidak langsung, bukan tebakan): ditemukan proses berjalan `/usr/local/qcloud/YunJing/YDEyes/YDService` dan `barad_agent` di daftar proses (Bagian 1.3) — keduanya adalah agent monitoring/security bawaan **Tencent Cloud (QCloud)**. Ini mengindikasikan kuat provider adalah Tencent Cloud, tapi **tier/paket spesifik (mis. Lighthouse vs CVM vs kelas apa) tetap tidak bisa dipastikan** tanpa akses panel provider atau dmidecode dengan sudo.

### 1.2 Load average & history

```
uptime: 10:40:56 up 172 days, 12:36, 0 users, load average: 0.39, 0.15, 0.08
```

Load sangat rendah untuk 2 vCPU (nilai 1.0 = 1 core penuh terpakai rata-rata; 0.39 jauh di bawah kapasitas).

**Keterbatasan eksplisit:** `sar` terpasang (`/usr/bin/sar`) tapi **tidak ada data collector aktif** — `sar -q` gagal dengan "Cannot open /var/log/sysstat/sa27: No such file or directory, Please check if data collecting is enabled". Direktori `/var/log/sysstat/` ada tapi kosong. `atop` **tidak terpasang** (`which atop` tidak menghasilkan output). Jadi **tidak ada riwayat load/CPU historis** yang bisa diperiksa — angka `uptime` di atas hanyalah **snapshot satu titik waktu (2026-08-27 10:40 WIB)**, bukan tren. Laporan audit sebelumnya (`docs/reports/2026-07-21-maintenance/VPS_HEALTH_REPORT.md` dan `docs/reports/2026-08-27-vps-health-shadow-e3/VPS_HEALTH_REPORT_2.md`) mencatat snapshot serupa pada tanggal lain (load 0.06/0.03/0.12 pada 21 Juli; 0.49/0.37/0.21 pada 27 Agustus pagi) — konsisten rendah di setiap titik yang pernah diperiksa, tapi tetap bukan data historis kontinu.

### 1.3 Memory breakdown

Top proses berdasarkan `ps aux --sort=-%mem` (20 teratas, disaring untuk relevansi):

| PID | %MEM | RSS | Proses |
|---|---|---|---|
| 191620 | 11.3% | 433.9 MB | `/opt/aliza-ai/venv/bin/python interfaces/telegram_bot.py` (**aliza-telegram**) |
| 2165588 | 7.5% | 286.1 MB | VS Code Server (Claude Code CLI session — sesi kerja interaktif ini) |
| 2165223 | 5.9% | 226.4 MB | VS Code Server node (extension host) |
| — | 2.8% | 109.6 MB | `systemd-journald` |
| 2150781 | 2.4% | 93.9 MB | VS Code Server node |
| 1544842 | — | 109.6 MB | `barad_agent` (Tencent Cloud monitoring, root) |
| 859291 | 1.0% | 40.3 MB | `/opt/gmail-agent/venv/.../telegram_bot.py` |
| 2410772 | 0.3% | 14.4 MB | gmail-agent gunicorn worker |

**Angka akurat untuk `aliza-telegram.service`** (via `MainPID` + `ps -o pid,rss,vsz,cmd`):
```
PID    RSS     VSZ     CMD
191620 433900  6784676 /opt/aliza-ai/venv/bin/python /opt/aliza-ai/interfaces/telegram_bot.py
```
→ **RSS ≈ 424 MB** (433,900 KB), konsisten dengan `MemoryCurrent=434204672` bytes (≈414 MiB / 434 MB) dari `systemctl show`.

**Proses lain yang berjalan bersamaan di VPS ini (di luar Aliza):** `gmail-agent.service` (~12 MB RSS via cgroup), `gmail-telegram-bot.service` (~38.5 MB), PostgreSQL 14, nginx, fail2ban, dan **sesi kerja interaktif VS Code Server/Claude Code Anda saat ini** (~600+ MB gabungan RSS lintas beberapa proses node — ini bukan beban permanen, hanya aktif selama sesi audit berlangsung).

**Swap:**
```
swapon --show:  NAME       TYPE  SIZE  USED  PRIO
                /swapfile  file  4G    1.1G  -2
free -h Swap:   total 4.0Gi, used 1.1Gi, free 2.9Gi
```
Swap terpakai 1.1 GB dari 4 GB — bukan tanda darurat, tapi menunjukkan RAM fisik 3.6 GB **sudah cukup ketat** sehingga kernel rutin memakai swap untuk halaman idle. Menambah proses baru yang aktif terus-menerus akan memperbesar tekanan ini.

### 1.4 Disk breakdown

```
du -sh /opt/aliza-ai/* (top, terurut):
8.2G   venv            (virtualenv Python — dependency library)
180M   backtest
27M    logs
6.1M   knowledge
4.9M   interfaces
1.4M   engine
1.3M   docs
912K   tests
844K   AlizaAI-Crypto
168K   data
```

**Ukuran spesifik:**
- `data/aliza.db` = **88 KB** (sangat kecil — database utama SQLite Aliza).
- `logs/` total = **27 MB**.
- `knowledge/` struktur aktual: bukan `knowledge/vector_store` langsung berisi data besar — isinya `documents/`, `uploads/`, dan `vector_store/` (total keseluruhan folder `knowledge/` hanya 6.1 MB, jadi vector store saat ini kecil/minim terisi).

**Laju pertumbuhan log (dari rotasi historis):**
```
aliza.log       (hari berjalan, belum rotate) : 6.76 MB (baru ~10.7 jam sejak 00:00)
aliza.log.1     (1 hari penuh, uncompressed)  : 15.17 MB
aliza.log.2.gz  : 1.01 MB    aliza.log.5.gz : 1.03 MB
aliza.log.3.gz  : 1.00 MB    aliza.log.6.gz : 1.04 MB
aliza.log.4.gz  : 1.01 MB    aliza.log.7.gz : 1.03 MB
```
→ **Estimasi kasar: ~15 MB/hari log mentah (uncompressed), terkompresi ke ~1 MB/hari** (rasio kompresi teks ~15:1). Retensi 7 rotasi terkompresi ⇒ arsip log Aliza stabil di ~7 MB, tidak menjadi masalah disk untuk Aliza sendiri. Root disk sendiri naik dari 62%→54%→57% dalam ~5 minggu terakhir (menurut `VPS_HEALTH_REPORT_2.md`), tren wajar dan lambat.

**Total disk terpakai:** 32 GB dari 59 GB (57%), sisa **25 GB free**. `venv` (8.2 GB) adalah kontributor terbesar tunggal — ini dependency environment Aliza, bukan data yang tumbuh terus.

### 1.5 Network

**Bandwidth cap provider: TIDAK PASTI, perlu dicek dari panel provider** — tidak ada cara mengecek batas bandwidth dari dalam VM.

**Domain eksternal yang dipanggil kode Aliza** (dari `rg -o "https?://..." engine/ interfaces/`):
```
api.alternative.me, api.binance.com, api.blockchair.com, api.coinbase.com, api.coingecko.com,
api.coinpaprika.com, api.exchangerate-api.com, api.stlouisfed.org, btcdash.org,
core.telegram.org, fapi.binance.com, farside.co.uk, financialmodelingprep.com,
google.serper.dev, newsapi.org, openapi.sosovalue.com, open-api-v4.coinglass.com,
stablecoins.llama.fi, www.deribit.com, www.investing.com
```

**Estimasi volume kasar** dari `logs/aliza.log` hari berjalan (00:00–10:41 WIB, ~10.7 jam): kata kunci "binance" muncul **10.879 kali** dalam log level INFO (`data_coverage coin=... price_source=binance ...`) → rata-rata **≈1.017 baris/jam** yang berkorelasi dengan pemanggilan data Binance (across ~21 coin watchlist × siklus analisis berkala). Domain lain jauh lebih jarang dalam jendela ini: `coingecko` 3×, `newsapi` 24×, `serper` 10×, `investing` 20×, `coinpaprika` 2×, sementara `coinglass`, `sosovalue`, `blockchair` 0× (kemungkinan dipanggil pada jadwal lebih jarang, mis. harian, bukan tidak terpakai). Ini adalah estimasi kasar dari satu hari log, bukan pengukuran bandwidth aktual (byte transfer) — volume request ≠ volume data.

### 1.6 Systemd services & resource limit

```
systemctl list-units --type=service --state=running | grep -i aliza:
  aliza-telegram.service       loaded active running  AlizaAI Telegram Bot
  gmail-telegram-bot.service   loaded active running  AlizaAI Email Telegram Bot
```

Service Aliza lain (`aliza-bot`, `aliza-market`, `aliza-api`, `aliza-dashboard`, dll) semuanya `disabled`/`masked` — tidak berjalan, sesuai temuan `VPS_HEALTH_REPORT_2.md`.

**Resource limit cgroup:**

| Service | MemoryMax | CPUQuota | MemoryCurrent |
|---|---|---|---|
| `aliza-telegram.service` | **infinity** | (tidak diset) | 434,204,672 bytes (≈414 MiB) |
| `gmail-telegram-bot.service` | **infinity** | (tidak diset) | 38,486,016 bytes (≈37 MiB) |
| `gmail-agent.service` | 629,145,600 bytes (**600 MB, satu-satunya yang punya limit**) | (tidak diset) | 12,181,504 bytes (≈12 MiB) |

**Temuan kunci:** `aliza-telegram.service` — service produksi yang sedang dalam evaluasi shadow_e3 — **TIDAK punya `MemoryMax` maupun `CPUQuota` eksplisit** (nilai "infinity" = unlimited). Hanya `gmail-agent.service` yang punya batas memori eksplisit (600 MB) di seluruh service yang diperiksa. Ini berarti **belum ada isolasi resource cgroup sama sekali** untuk proses inti Aliza — proses apa pun di VPS ini (termasuk proses CNIE baru jika ditambahkan tanpa limit) berpotensi menghabiskan seluruh RAM/CPU sistem tanpa dibatasi systemd terlebih dahulu.

---

## Bagian 2 — Estimasi Kebutuhan CNIE

**Catatan umum:** Tidak ditemukan file PRD CNIE di dalam repo `/opt/aliza-ai` (dicek dengan `find . -iname "*CNIE*"` — nihil hasil). Seluruh estimasi di bagian ini murni berbasis deskripsi arsitektur dari prompt tugas dan pengetahuan umum tentang library/beban kerja terkait — **bukan pengukuran langsung** (dilarang menginstal apa pun untuk mengetes). Semua asumsi dinyatakan eksplisit agar bisa dikoreksi.

### Skenario A — Hanya Telethon listener di VPS ini (Cloudflare menangani sisanya)

**Asumsi:** proses Python persisten hanya menjalankan client MTProto (Telethon) + forwarding event ke endpoint Cloudflare (via HTTP), tanpa LLM call, tanpa query database berat, tanpa pemrosesan NLP di proses itu sendiri.

- **RAM:** Estimasi **50–150 MB RSS saat idle**, naik ke ~150–250 MB saat traffic pesan padat (Telethon + dependency-nya seperti `pyaes`/`rsa` ringan; overhead utama adalah interpreter Python + koneksi TCP terenkripsi MTProto yang di-maintain). Ini jauh di bawah RAM `aliza-telegram` saat ini (424 MB) karena tidak ada beban LLM/analisis pasar.
- **CPU:** Minimal saat idle (< 1% dari satu core) — MTProto listener sebagian besar menunggu I/O socket. Spike kecil dan singkat (beberapa ratus ms) saat pesan masuk, untuk parsing/dekripsi event.
- **Disk:** Sangat kecil — file sesi Telethon (`.session`, SQLite internal Telethon) biasanya puluhan-ratusan KB. Kalau ada buffer log lokal sebelum dikirim ke Cloudflare, dengan asumsi volume beberapa ratus pesan/hari dari channel yang dipantau, estimasi **< 5 MB/hari** untuk log buffer teks.
- **Network:** Koneksi MTProto persisten (satu socket long-lived) + panggilan HTTP keluar ke endpoint Cloudflare Workers per event masuk. Volume tergantung jumlah channel dipantau, tapi karena ini murni teks (bukan download media), estimasi **puluhan KB–beberapa MB/hari** untuk skenario pemantauan wajar (5-20 channel).

**Kesimpulan Skenario A:** dampak resource ke VPS ini **sangat kecil dan dapat diabaikan secara teknis** dibanding kapasitas idle yang ada (RAM available saat ini ≈2.0 GB, CPU load 0.39/2 core). Risiko utama BUKAN resource, melainkan operasional/isolasi (lihat Bagian 3).

### Skenario B — Seluruh pipeline CNIE di VPS ini (tanpa Cloudflare)

**Asumsi eksplisit yang dipakai (nyatakan untuk dikoreksi user):**
- Ingestion: 3-5 job cron pendek (fetch RSS/API berita), berjalan singkat lalu keluar (bukan proses persisten tambahan besar).
- `market_poll` setiap 1 menit (job ringan, fetch harga/data pasar).
- D1 → SQLite lokal, R2 → filesystem lokal (tidak ada layer network tambahan untuk storage).
- Dashboard adalah SPA statis — cukup disajikan nginx/static file server (nginx **sudah berjalan** di VPS ini untuk keperluan lain, jadi tidak perlu proses baru untuk ini, hanya konfigurasi tambahan — meski konfigurasi baru di luar cakupan audit read-only ini).
- **Semua LLM call via API eksternal** (tidak ada model lokal) — asumsi utama yang dipakai untuk estimasi CPU/RAM di bawah. **Jika ternyata ada tahap embedding/clustering yang memakai model ML lokal (mis. sentence-transformers, spaCy dengan model besar), beban RAM/CPU akan JAUH lebih besar** (model embedding lokal kelas kecil-menengah saja bisa menambah 500 MB–2 GB RAM saat model dimuat, plus beban CPU signifikan per batch — ini di luar estimasi utama di bawah dan harus dikonfirmasi ulang jika berlaku).

- **RAM tambahan:** Proses worker Python/Node untuk ingestion+scoring (I/O-bound, tanpa model lokal) diestimasi **150–400 MB RSS per proses worker aktif**, tergantung jumlah dependency (parser HTML/RSS, HTTP client, JSON processing). Jika dijalankan sebagai job cron pendek (bukan daemon persisten), beban RAM hanya muncul saat job berjalan (biasanya 1-few menit), lalu kembali ke 0. SQLite kedua (file lokal) menambah overhead memori minimal (puluhan MB untuk cache halaman SQLite, tergantung ukuran DB). Total estimasi **puncak sesaat 300-600 MB tambahan** saat beberapa job tumpang tindih, bukan beban konstan.
- **CPU:** Asumsi utama **mayoritas I/O-bound** (fetch HTTP ke 5-8 sumber berita/API, parsing teks/JSON ringan) — beban CPU rendah, serupa dengan pola kerja `aliza-telegram` saat ini yang juga banyak fetch API eksternal dengan load rendah (0.39/2 core). **KECUALI** jika ada tahap embedding/clustering lokal (di luar asumsi utama) — dalam hal itu, CPU bisa menjadi bottleneck signifikan pada VPS 2 vCPU karena inference model ML (bahkan model kecil) biasa memakai penuh 1 core selama beberapa detik-menit per batch, berpotensi bersaing langsung dengan siklus analisis Aliza yang juga berjalan periodik.
- **Disk:** Asumsi volume: **20-40 artikel berita crypto/hari** (dari 5-8 sumber), rata-rata ukuran per item (teks berita + metadata JSON) **~5-20 KB** (tanpa gambar/media, murni teks + skor). Estimasi harian: 20-40 item × ~15 KB rata-rata ≈ **300 KB - 600 KB/hari**. Proyeksi bulanan: **~10-20 MB/bulan** untuk `raw_items` archive lokal murni teks. Ini kecil relatif terhadap 25 GB free space saat ini — bahkan dalam 1 tahun (~120-240 MB) tidak akan jadi masalah disk, **selama tidak ada penyimpanan gambar/media penuh per artikel** (jika PRD ternyata menyimpan snapshot HTML penuh atau gambar, kalikan estimasi ini beberapa kali lipat).
- **Network tambahan:** Polling 5-8 sumber RSS/API setiap 1-3 menit ⇒ pada interval 2 menit rata-rata, itu **~30 request/jam per sumber** × 5-8 sumber = **150-240 request/jam** total, atau **3.600-5.760 request/hari**. Volume data per response RSS/API biasanya kecil (beberapa KB-puluhan KB per response, tergantung apakah full-text atau cuma metadata) — estimasi kasar **10-50 MB/hari** volume transfer masuk untuk polling ini, ditambah `market_poll` tiap 1 menit (1.440 request/hari, volume kecil per request karena hanya data harga).

**Kesimpulan Skenario B:** beban tambahan **jauh lebih besar dari Skenario A**, tapi berdasarkan asumsi I/O-bound murni tanpa model lokal, secara teori masih **within kapasitas idle** VPS 2 vCPU/3.6 GB saat ini SELAMA proses berjalan sebagai job cron pendek (bukan daemon berat 24/7) DAN memori tersedia ~2 GB cukup untuk menampung puncak sesaat 300-600 MB tambahan tanpa memicu swap berlebihan. Margin RAM saat ini (available ≈2.0 GB) relatif tipis jika beberapa job tumpang tindih dengan siklus analisis Aliza yang sudah memakai ~424 MB + overhead OS.

---

## Bagian 3 — Analisis Risiko Berbagi VPS dengan Sistem Produksi

### 3.1 Riwayat masalah performa/rate-limit

Pencarian `rg -il "circuit.breaker|429|rate.limit"` di `docs/reports/` dan root `*.md` menghasilkan cukup banyak file yang menyebutkan istilah tersebut. Diperiksa lebih dalam pada laporan yang paling relevan dengan resource/health VPS:

- **`docs/reports/2026-07-21-maintenance/VPS_HEALTH_REPORT.md`**: hanya menyebut "Load 0,06/0,03/0,12 pada 2 CPU sangat rendah" — tidak ada indikasi circuit breaker atau rate limit yang dipicu oleh keterbatasan resource VPS.
- **`docs/reports/2026-08-27-vps-health-shadow-e3/SHADOW_E3_STAGNATION_REPORT.md`**: menyebut penanganan `HTTP status ≠ 200` pada fetch Binance klines dengan early-return kosong (bukan circuit breaker resource-based) — **"nihil kejadian ini di log 20-27 Agustus"**, artinya tidak ada bukti API eksternal sedang di-throttle akibat volume request dari VPS ini.
- **`docs/reports/2026-08-27-vps-health-shadow-e3/VPS_HEALTH_REPORT_2.md`** (paling baru & relevan, 27 Agustus): mencatat **1.131 baris WARNING/ERROR** dalam 4 hari terakhir, didominasi noise **API eksternal** (`funding_rate_monitor: openInterest HTTP 400 OMUSDT`, `Investing.com calendar returned 403`, `economic_calendar: Serper HTTP 400`) — ini adalah **error dari sisi provider API pihak ketiga** (400/403, bukan 429 rate-limit dari beban VPS), dan laporan itu sendiri menyimpulkan **"Status: SEHAT"** untuk resource VPS (load, RAM, swap normal untuk 2 vCPU).
- Grep spesifik untuk "circuit.breaker|429" pada beberapa laporan fitur lain (`INFO_COIN_PAKET1_REPORT.md`, `EVALUASI_BIG_MOVE_ALERT_REPORT.md`, `BERITA_MITIGASI_REPORT.md`, `NOTIFIKASI_MITIGASI_REPORT.md`) **tidak menghasilkan match langsung** — kemunculan nama file-file itu pada pencarian awal kemungkinan dari kata "limit" dalam konteks lain (mis. "batas" fitur, bukan rate-limit API).

**Kesimpulan temuan (termasuk bukti negatif eksplisit):** **Tidak ditemukan satu pun indikasi bahwa VPS ini pernah mendekati batas resource (CPU/RAM/disk) sistem, atau bahwa circuit breaker/rate-limit yang pernah tercatat disebabkan oleh keterbatasan resource VPS** (semua kejadian 4xx yang ditemukan adalah error dari API pihak ketiga, independen dari beban lokal). Ini adalah bukti negatif — bermanfaat, tapi terbatas oleh keterbatasan Bagian 1.2 (tidak ada data historis `sar`/`atop`, hanya snapshot dan laporan naratif per-tanggal).

### 3.2 Dampak kegagalan CNIE terhadap `aliza-telegram` (shadow_e3)

`aliza-telegram.service` sedang dalam **masa evaluasi shadow_e3** yang sensitif (per `SHADOW_PROMOTION_CHECKLIST_REPORT.md`, kebijakan promosi kini berbasis **jumlah outcome closed (≥60)**, bukan tanggal kalender, dan sedang mengalami stagnasi kandidat karena regime pasar `TREND` sejak 18-20 Agustus). Evaluasi ini membutuhkan **kontinuitas operasional** proses `aliza-telegram` tanpa gangguan (restart tak terduga, downtime, atau performa terdegradasi bisa mempengaruhi keandalan logging siklus/outcome yang sedang dikumpulkan).

Dari Bagian 1.6: **`aliza-telegram.service` tidak punya `MemoryMax`/`CPUQuota` eksplisit (infinity/unlimited)**. Artinya:

- **Skenario A (Telethon listener):** risiko rendah secara resource (estimasi RAM/CPU sangat kecil), tapi **risiko bukan nol** — bug memory-leak pada proses Telethon (mis. event handler yang menumpuk referensi, reconnect loop yang tidak membersihkan koneksi lama) tetap **tidak dibatasi cgroup**, sehingga secara teori bisa tumbuh tanpa batas hingga RAM sistem habis. Karena `aliza-telegram` JUGA tidak dibatasi, ketika OOM killer bertindak, **kernel memilih korban berdasarkan skor `oom_score` (umumnya proses dengan RSS terbesar/terlama)** — tidak ada jaminan proses CNIE yang bermasalah yang dimatikan lebih dulu daripada `aliza-telegram`. Ini bisa mematikan proses produksi yang sedang dalam evaluasi sensitif, bukan proses yang sebenarnya bermasalah.
- **Skenario B (seluruh pipeline):** risiko ini **jauh lebih besar** karena lebih banyak proses/job berjalan, permukaan bug lebih luas (parsing HTML tak terduga, response API malformed, dsb.), dan estimasi puncak RAM (300-600 MB tambahan) yang jika ternyata meleset (mis. ada memory leak di parser, atau lonjakan volume berita mendadak) bisa mendorong sistem ke swap berat atau OOM — dengan konsekuensi acak yang sama: `aliza-telegram` bisa jadi korban OOM killer meskipun bukan penyebab masalah.

**Kesimpulan:** tanpa isolasi cgroup, **kedua skenario membawa risiko non-nol terhadap kontinuitas evaluasi shadow_e3**, dengan Skenario B secara signifikan lebih berisiko daripada Skenario A.

### 3.3 Rekomendasi mitigasi (jika tetap satu VPS)

1. **User Linux terpisah** untuk proses CNIE (bukan berjalan sebagai user `ubuntu` yang sama dengan Aliza) — membatasi blast radius kalau ada masalah permission/file, dan memudahkan audit `ps`/resource per-user.
2. **Systemd service terpisah dengan `MemoryMax` dan `CPUQuota` eksplisit** (bukan default unlimited seperti `aliza-telegram` saat ini) — misalnya CNIE dibatasi eksplisit ke suatu pagu RAM/CPU yang tidak bisa dilampaui, sehingga leak/bug di CNIE akan membuat *proses CNIE sendiri* yang dimatikan/dibatasi oleh cgroup, bukan proses lain di sistem yang jadi korban OOM killer acak.
3. Sebagai praktik tambahan (di luar cakupan langsung pertanyaan tapi konsisten dengan temuan): mengingat `aliza-telegram.service` sendiri saat ini juga belum punya `MemoryMax`/`CPUQuota`, menambahkan limit yang wajar untuknya juga akan mengurangi risiko dua arah (CNIE mengganggu Aliza, ATAU proses lain mengganggu Aliza) — ini murni rekomendasi observasi, bukan tindakan yang dilakukan dalam audit ini.
4. Monitoring tambahan: karena tidak ada `sar`/`atop` history saat ini (Bagian 1.2), pertimbangkan mengaktifkan data collection `sysstat` (`/etc/default/sysstat`, enable) SEBELUM menambahkan beban CNIE apa pun — supaya ada baseline historis nyata untuk membandingkan dampak sebelum/sesudah, bukan hanya snapshot satu titik waktu.

---

## Bagian 4 — Rekomendasi Akhir

### Skenario A — Hanya Telethon listener

**Rekomendasi: Tetap di VPS ini**, dengan syarat wajib:
- Systemd service baru untuk Telethon listener dengan `MemoryMax` eksplisit (mis. 256-512 MB — jauh di atas estimasi kebutuhan riil 50-250 MB, tapi sebagai pagu keras) dan `CPUQuota` eksplisit (mis. 25-50% dari satu core) — BUKAN dijalankan tanpa limit seperti `aliza-telegram` saat ini.
- Jalankan sebagai user Linux terpisah dari `ubuntu`/proses Aliza.
- Monitoring: aktifkan `sysstat` untuk punya baseline historis CPU/RAM sebelum dan sesudah listener aktif, mengingat saat ini tidak ada riwayat load selain snapshot.

Alasan: estimasi beban Skenario A (puluhan-ratusan MB RAM, CPU minimal) sangat kecil dibanding RAM available (~2.0 GB) dan load CPU saat ini (0.39/2 core) — tidak ada dasar teknis untuk VPS baru, selama syarat isolasi cgroup di atas dipenuhi untuk melindungi `aliza-telegram` dari risiko OOM acak (Bagian 3.2).

### Skenario B — Seluruh pipeline CNIE

**Rekomendasi: Butuh VPS baru terpisah** (bukan tetap atau upgrade VPS ini), dengan alasan spesifik:

1. **Isolasi risiko produksi** — `aliza-telegram` sedang dalam evaluasi shadow_e3 yang eksplisit sensitif terhadap gangguan, dievaluasi berdasarkan akumulasi outcome dalam jangka waktu tidak pasti (bisa berminggu-minggu karena regime `TREND` sedang stagnan per `SHADOW_E3_STAGNATION_REPORT.md`). Menambahkan pipeline multi-proses (ingestion, scoring, dashboard server) dengan permukaan bug jauh lebih luas daripada Skenario A, TANPA riwayat operasional CNIE sama sekali di lingkungan ini, menciptakan risiko yang tidak proporsional terhadap nilai evaluasi yang sedang berjalan — satu insiden OOM/crash yang salah sasaran bisa merusak kontinuitas data yang sedang dikumpulkan untuk keputusan promosi produksi.
2. **Margin resource sudah relatif tipis untuk beban tambahan sebesar ini** — RAM fisik hanya 3.6 GB dengan available ~2.0 GB dan swap sudah terpakai 1.1 GB dari 4 GB (indikasi tekanan memori reguler), sementara estimasi Skenario B sendiri (300-600 MB puncak sesaat, berpotensi lebih tinggi jika asumsi "tanpa model ML lokal" ternyata salah) mengonsumsi porsi signifikan dari margin yang tersisa — terutama karena `aliza-telegram` sendiri TIDAK dibatasi cgroup dan bisa berfluktuasi.
3. Tidak adanya isolasi cgroup saat ini (Bagian 1.6, 3.2) berarti mitigasi minimum (limit systemd) BISA diterapkan di VPS yang sama, tapi kombinasi (a) sensitivitas evaluasi produksi yang sedang berjalan + (b) permukaan risiko operasional CNIE penuh yang jauh lebih besar dari Skenario A + (c) belum ada riwayat operasional CNIE sama sekali untuk memvalidasi estimasi Bagian 2 — membuat pemisahan VPS lebih aman daripada mengandalkan limit cgroup semata di sistem produksi yang sensitif ini.

**Spek minimal VPS baru yang disarankan untuk Skenario B** (berdasarkan estimasi Bagian 2, bukan angka sembarang):
- **vCPU:** 2 vCPU — cukup untuk beban I/O-bound cron pendek + market_poll 1 menit (asumsi tanpa model ML lokal); jika asumsi ini salah (ada embedding/clustering lokal), naikkan ke 4 vCPU.
- **RAM:** perhitungan — puncak sesaat CNIE (300-600 MB) + overhead OS dasar (~300-500 MB untuk sistem minimal, systemd, nginx statis) + margin aman 20-30% ⇒ (600+500) × 1.3 ≈ **~1.4-1.5 GB minimum**, dibulatkan ke **2 GB RAM** sebagai target praktis (memberi ruang untuk SQLite cache dan lonjakan volume berita di luar asumsi harian normal).
- **Disk:** estimasi pertumbuhan `raw_items` ~10-20 MB/bulan (murni teks) sangat kecil; disk **20 GB** sudah lebih dari cukup untuk beberapa tahun operasi dengan margin besar, termasuk OS, dependency Python/Node, dan log.
- **Bandwidth:** estimasi request 3.600-5.760/hari untuk polling + market_poll, volume data kemungkinan puluhan MB/hari — kebutuhan bandwidth rendah, tier standar VPS kecil mana pun umumnya cukup (verifikasi cap spesifik tetap perlu dicek ke provider, sesuai Bagian 1.5).

Catatan: jika asumsi utama Skenario B (LLM via API eksternal saja, tanpa model ML lokal) ternyata salah — misal ada tahap embedding/clustering lokal — estimasi RAM dan terutama CPU di atas harus dihitung ulang, dengan kemungkinan kebutuhan vCPU naik ke 4 dan RAM ke 4 GB atau lebih tergantung ukuran model.
