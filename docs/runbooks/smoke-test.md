# Smoke Test Aliza AI

Smoke test adalah verifikasi manual cepat setelah deploy/restart. Ia tidak menggantikan automated test di [testing.md](../architecture/testing.md).

## 1. Precheck

```bash
cd /opt/aliza-ai
git status --short --branch
git rev-parse --short HEAD
systemctl status aliza-telegram --no-pager
```

Catat commit dan waktu mulai. Jangan lanjut bila service memakai worktree/path yang berbeda dari `/opt/aliza-ai`.

## 2. Telegram

Dari akun yang diizinkan, kirim:

```text
/start
/market
/radar
/status
/portfolio
```

Semua command harus merespons tanpa traceback. Bila sebuah fitur memang tidak memiliki data, respons kosong/penjelasan terkontrol diterima; proses tidak boleh crash.

## 3. Snapshot, opportunity, dan signal

Verifikasi melalui command operasional/log:

- snapshot memiliki timestamp baru dan `data` tidak kosong;
- `scan_opportunities()` menghasilkan list atau list kosong tanpa exception;
- `scan_for_signals()` menghasilkan signal atau `None` tanpa exception;
- filter RR/confidence, market risk, coverage, dan anti-spam menjelaskan kandidat yang ditolak.

Jangan membuat trade produksi hanya untuk smoke test. Pengujian `create_trade()` dilakukan pada DB test/fixture.

## 4. Dashboard/API

Dashboard default bind ke loopback port 8001.

```bash
curl --fail --silent --show-error http://127.0.0.1:8001/health
curl --silent --output /dev/null --write-out '%{http_code}\n' \
  http://127.0.0.1:8001/api/dashboard/market
```

Hasil yang diharapkan: health HTTP 200 dengan `{"status":"ok"}`; endpoint dashboard tanpa token HTTP 401.

Untuk positive auth test, dapatkan token melalui alur login yang disetujui dan simpan sementara di environment shell—jangan tulis token ke command history/report:

```bash
curl --fail --silent --show-error \
  -H "Authorization: Bearer ${ALIZA_DASHBOARD_TOKEN}" \
  http://127.0.0.1:8001/api/dashboard/market
```

Ulangi bila diperlukan untuk `quant`, `predict`, `signals`, dan `portfolio`. Semua endpoint tersebut wajib Bearer auth.

## 5. Journal dan hasil akhir

```bash
journalctl -u aliza-telegram --since "10 minutes ago" --no-pager
```

Lulus bila service tetap aktif, command penting merespons, snapshot segar, DB tidak error, dan journal tidak menunjukkan crash loop. Untuk restart yang menyentuh shutdown, jalankan verifikasi dua siklus di [graceful-shutdown.md](graceful-shutdown.md).
