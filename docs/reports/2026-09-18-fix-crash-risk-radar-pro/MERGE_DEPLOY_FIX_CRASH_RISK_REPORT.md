# Merge, Deploy & Verifikasi: Fix Label "Crash Risk" Radar Pro

**Tanggal:** 2026-09-18
**Branch sumber:** `fix/radarpro-crash-risk-label` → merge ke `main`
**Commit:** `23d6b0d` — "fix: crash risk label no longer defaults to every coin on global HIGH risk"
**Laporan terkait:** `RADAR_MARKET_VS_RADAR_PRO_AUDIT_REPORT.md` (audit), `FIX_CRASH_RISK_RADAR_PRO_REPORT.md` (fix + test)

---

## 0. Klarifikasi angka baseline test (248 vs 353)

Sudah dicek — **ini murni beda cakupan invoke, bukan penyusutan test.** `FIX_CRASH_RISK_RADAR_PRO_REPORT.md` menjalankan `venv/bin/python3 -m pytest tests/ -q` (scoped ke folder `tests/` saja) yang menghasilkan 248 passed. Sesi 31 Agustus (fix duplikasi header) memakai command penuh sesuai `README.md` baris 30, yaitu `venv/bin/python -m pytest -q` **tanpa scope path** — ini juga mengumpulkan 9 file test level-root yang berada di luar folder `tests/` (`test_dashboard_binding.py`, `test_dashboard_endpoint_auth.py`, `test_dashboard_passwords.py`, `test_dashboard_security.py`, `test_dashboard_rate_limit.py`, `test_dashboard_execution_limit.py`, `test_dashboard_dotenv_isolation.py`, `test_dashboard_docs.py`, `test_telegram_authorization.py`). Dikonfirmasi dengan menjalankan `pytest -q` (tanpa scope) di branch fix SEBELUM merge: hasilnya **359 passed** = 353 (baseline penuh, cocok persis dengan angka 31 Agustus) + 6 test baru dari fix ini. Tidak ada test yang hilang/disusutkan — task-task berikutnya sebaiknya selalu memakai command penuh tanpa scope (`pytest -q`) untuk laporan baseline, bukan `pytest tests/ -q`, supaya konsisten dengan angka yang biasa dipakai di riwayat proyek ini.

---

## 1. Precheck

```
$ git fetch origin
$ git status -sb          # di branch fix/radarpro-crash-risk-label, sebelum checkout main
## fix/radarpro-crash-risk-label
M  engine/market/market_radar_pro_analyzer.py
A  tests/test_radar_pro_crash_risk.py
(+ banyak file *_REPORT.md untracked dari sesi-sesi audit sebelumnya — dibiarkan, di luar lingkup task ini, tidak disentuh)
```

Fix belum sempat di-commit sebelumnya (hanya staged dari sesi audit/fix sebelumnya) — dikomit dulu di branch fix sebelum merge:

```
$ git commit -m "fix: crash risk label no longer defaults to every coin on global HIGH risk ..."
[fix/radarpro-crash-risk-label 23d6b0d] 2 files changed, 180 insertions(+), 5 deletions(-)
```

```
$ git diff --name-only main fix/radarpro-crash-risk-label
engine/market/market_radar_pro_analyzer.py
tests/test_radar_pro_crash_risk.py
```

Cocok persis dengan yang dilaporkan di `FIX_CRASH_RISK_RADAR_PRO_REPORT.md` — hanya 2 file. Local `main` juga sudah sinkron dengan `origin/main` sebelum merge (`git log origin/main..main` dan `git log main..origin/main` sama-sama kosong).

---

## 2. Merge

```
$ git checkout main
$ git merge --ff-only fix/radarpro-crash-risk-label
Updating d35c6c2..23d6b0d
Fast-forward
 engine/market/market_radar_pro_analyzer.py |  14 ++-
 tests/test_radar_pro_crash_risk.py         | 171 +++++++++++++++++++++++++++++
 2 files changed, 180 insertions(+), 5 deletions(-)
```

Fast-forward bersih, tidak ada konflik, tidak perlu rebase.

---

## 3. Full test suite (cakupan paling lengkap, sesuai README)

```
$ venv/bin/python3 -m pytest -q      # di main, setelah merge
359 passed, 3 warnings, 74 subtests passed in 33.68s
```

**0 gagal.** Angka 359 = 353 (baseline penuh proyek) + 6 test baru dari fix ini — konsisten dengan klarifikasi di bagian 0.

---

## 4. Push & Restart

```
$ git push origin main
To https://github.com/jun3iawan-ai/aliza-ai.git
   d35c6c2..23d6b0d  main -> main

$ sudo systemctl restart aliza-telegram.service
$ sudo systemctl is-active aliza-telegram.service
active
```

Log 2 menit pertama setelah restart (`journalctl -u aliza-telegram.service --since "2 minutes ago"`): graceful shutdown proses lama selesai bersih (`Graceful shutdown completed`), proses baru start normal — load model embedding, `Market radar fetched once per snapshot`, `dynamic_universe: fetched 50 coins`, snapshot job pertama jalan sukses (`Snapshot completed. Valid coins: 17`, lihat catatan di bagian 5 soal 4 coin yang gagal validasi — tidak terkait fix ini). **Tidak ditemukan ERROR/Exception/Traceback** di window ini (dicek dengan grep khusus `error|exception|traceback|CRITICAL`, hasil kosong).

---

## 5. Verifikasi Live `/radarpro`

**Catatan metodologi jujur:** saya tidak punya akses interaktif ke client Telegram milik user untuk benar-benar menekan tombol menu/command secara langsung. Sebagai gantinya, verifikasi dilakukan dengan memanggil langsung fungsi produksi yang SAMA PERSIS dipakai handler `/radarpro` (`update_market_snapshot()` → `generate_radar_pro()` → `format_radar_pro_report()` dari `engine/market/market_snapshot_engine.py` dan `engine/market/market_radar_pro_analyzer.py`) lewat script sekali-pakai, terhadap data pasar live (bukan mock) — read-only, hanya fetch API publik yang sama seperti yang sudah rutin dilakukan snapshot job setiap 60 detik. Ini menghasilkan output yang identik dengan yang akan dikirim `/radarpro` ke Telegram saat ini juga, hanya tidak lewat transport Telegram-nya. **Ini bukan pengganti user benar-benar mencoba `/radarpro` sendiri** — kalau ingin verifikasi 1:1 lewat Telegram, silakan trigger manual dan bandingkan dengan output di bawah (harus identik/sangat mirip, karena keduanya membaca snapshot dalam siklus waktu yang berdekatan).

Kondisi market saat verifikasi: `market_risk_score` GLOBAL ternyata **"LOW"** untuk semua coin (bukan "HIGH") — jadi skenario bug (semua coin ter-label Crash Risk) memang tidak bisa direproduksi apa adanya saat ini. Sesuai instruksi task, ini tidak dipaksakan; cukup dikonfirmasi output terlihat wajar dan bervariasi:

```
=== /radarpro OUTPUT ===
📡 ALIZA MARKET RADAR PRO

BTC   BEARISH ↓     • Neutral
ETH   BEARISH ↓     • Neutral
BNB   SIDEWAYS →    • Neutral
SOL   SIDEWAYS →    • Neutral
XRP   BEARISH ↓     • Neutral
ADA   SIDEWAYS →    • Neutral
SUI   SIDEWAYS →    • Neutral
ARB   BULLISH ↑     🚀 Momentum
PEPE  BULLISH ↑     🚀 Momentum
JTO   BULLISH ↑     📈 Strong Trend
ETHFI  SIDEWAYS →    • Neutral
WLD   SIDEWAYS →    • Neutral
OM    BULLISH ↑     📈 Strong Trend
ASTER  BULLISH ↑     🚀 Momentum
XPL   SIDEWAYS →    • Neutral
TAO   SIDEWAYS →    • Neutral
XAUT  SIDEWAYS →    • Neutral

🕒 Market Snapshot : 07:49:55
```

Verifikasi:
- **Tidak ada satupun coin berlabel "⚠ Crash Risk"** — sesuai ekspektasi karena `market_risk_score` global memang LOW saat ini (baik sebelum maupun sesudah fix, hasil untuk kondisi LOW ini identik — fix hanya mengubah perilaku saat kondisi global HIGH).
- Label **bervariasi wajar** antar coin sesuai kondisi teknikal masing-masing: coin bearish/sideways dapat "• Neutral", coin bullish dengan RSI tinggi dapat "🚀 Momentum", coin bullish tanpa RSI ekstrem dapat "📈 Strong Trend" — tidak ada keseragaman tanpa alasan yang mengindikasikan bug lain.
- Dikonfirmasi eksplisit lewat print `market_risk_score` per coin bahwa nilainya memang identik ("LOW") untuk seluruh 17 coin yang valid — bukti langsung sifat "global, bukan per-coin" yang jadi dasar analisis bug (lihat audit bagian 5.2), sekaligus bukti kondisi HIGH memang tidak sedang terjadi saat verifikasi ini.
- **Catatan di luar lingkup fix ini** (tidak disebabkan oleh perubahan yang di-deploy): 4 coin (`BONE`, `FARTCOIN`, `HYPE`, `ZEREBRO`) gagal validasi harga (`price_unavailable`) sehingga tidak muncul di output — hanya 17 dari 21 watchlist yang tampil. Ini konsisten dengan alur `NON_BINANCE` CoinGecko pre-fetch di `market_snapshot_engine.py` yang tampaknya gagal/timeout saat verifikasi dijalankan; tidak terkait dengan perubahan `market_radar_pro_analyzer.py` sama sekali. Dilaporkan sebagai observasi, bukan bug baru dari fix ini — silakan cek terpisah kalau memang berulang.

---

## Ringkasan Status

| Langkah | Status |
|---|---|
| Klarifikasi baseline test (248 vs 353) | Selesai — beda scope invoke, bukan penyusutan (bagian 0) |
| Precheck (fetch, diff scope) | Selesai — cocok laporan fix |
| Commit fix ke branch | Selesai (`23d6b0d`) |
| Merge ke `main` | Fast-forward bersih, tanpa konflik |
| Full test suite (`pytest -q`, tanpa scope) | **359 passed, 0 gagal** |
| Push ke `origin/main` | Selesai |
| Restart service | `active`, tidak ada exception di log 2 menit pertama |
| Verifikasi live `/radarpro` | Output wajar, tidak ada Crash Risk salah label; kondisi HIGH tidak sedang terjadi jadi skenario bug tidak direproduksi paksa (sesuai instruksi) |

**Deploy selesai dan live di `main` (commit `23d6b0d`), service `aliza-telegram.service` sudah restart dengan kode baru dan berjalan normal.**
