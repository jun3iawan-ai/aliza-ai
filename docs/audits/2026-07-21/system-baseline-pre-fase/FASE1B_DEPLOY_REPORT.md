# Laporan Fase 1b — Dirty State, Full Test, Merge dan Deploy

> **Status: SUPERSEDED.** Snapshot pada 2026-07-21. Kondisi sistem terkini ada di `docs/README.md` dan report Fase 1–4 (`docs/reports/` — lihat Bagian 3). Jangan jadikan dokumen ini sebagai acuan status aktif.

Tanggal: 21 Juli 2026 (WIB).

## Status akhir

Fase 1 berhasil diuji dan di-merge ke `main`, tetapi deploy runtime **BERHENTI** pada restart Telegram karena systemd meminta autentikasi interaktif. Sesuai prosedur, market service tidak dinonaktifkan dan observasi 30–60 menit tidak dijalankan.

- Branch aktif: `main`.
- Merge commit: `cdaf551e489ade4d75ba2673c054516390cc3b8b`.
- `main` berada 15 commit di depan `origin/main`.
- Telegram masih proses lama, aktif sejak 07:38:20 WIB, PID 2122472.
- `aliza-market.service` tetap enabled dan active.
- `.env` dan secret tidak disentuh atau ditampilkan.

## Langkah 1 — Bereskan dirty state

### Status awal

```text
## fix/fase1-signal-integrity
 M engine/alerts/auto_alert_engine.py
 M engine/trading/opportunity_scanner.py
 M engine/trading/signal_engine.py
?? audit-output/
?? engine/utils/formatters.py
```

### Ringkasan diff dan keputusan

| File | Ringkasan | Keputusan |
|---|---|---|
| `engine/alerts/auto_alert_engine.py` | Memakai `format_price`/`format_ratio`, mengganti formatter lokal, dan menyelaraskan docstring threshold. Tidak mengubah parameter signal. | Diadopsi; `0c57c590`. |
| `engine/trading/opportunity_scanner.py` | Memakai formatter bersama untuk entry/SL/TP/RR. Pipeline kandidat tidak berubah. | Diadopsi; `05b5740a`. |
| `engine/trading/signal_engine.py` | Memakai formatter bersama untuk pesan signal; confidence tidak diformat sebagai harga. Pipeline/risk tidak berubah. | Diadopsi; `735b3559`. |
| `engine/utils/formatters.py` | Helper aktif `format_price()`/`format_ratio()`, dipakai tiga modul aktif. | Diadopsi; `c0714a99`. |

Perubahan aman karena hanya memusatkan presentasi angka dan tidak bertabrakan dengan logika Fase 1. Status setelah empat commit:

```text
## fix/fase1-signal-integrity
?? audit-output/
```

## Langkah 2 — Full test suite

Perintah:

```text
venv/bin/python -m pytest -q
```

Hasil:

```text
114 passed, 3 warnings, 74 subtests passed in 17.49s
```

Seluruh test lama dan `tests/test_fase1.py` lulus. Tiga warning adalah `DeprecationWarning` tipe SWIG dari dependency Telegram; tidak ada failure.

## Langkah 3 — Merge dan deploy

### Merge

Perintah:

```text
git checkout main
git merge --no-ff fix/fase1-signal-integrity
```

Merge sukses dengan strategi `ort`, tanpa conflict. Hash merge:

```text
cdaf551e489ade4d75ba2673c054516390cc3b8b
```

### Restart Telegram — GAGAL

Perintah:

```text
systemctl restart aliza-telegram.service
```

Hasil:

```text
Failed to restart aliza-telegram.service: Interactive authentication required.
See system logs and 'systemctl status aliza-telegram.service' for details.
```

Pemeriksaan read-only sesudahnya menunjukkan service tidak restart: masih `active (running)`, MainPID `2122472`, proses `/opt/aliza-ai/venv/bin/python /opt/aliza-ai/interfaces/telegram_bot.py`, aktif sejak 07:38:20 WIB. Karena itu merge commit belum terverifikasi berjalan di Telegram.

### Market service — TIDAK DIJALANKAN

Perintah berikut tidak dijalankan karena prosedur berhenti setelah restart gagal:

```text
systemctl disable --now aliza-market.service
```

Status read-only tetap `enabled` dan `active`. Service stale sejak 2 Juni; rekomendasi disable tetap berlaku setelah otorisasi systemd tersedia.

## Langkah 4 — Verifikasi runtime

Tidak dijalankan sebagai observasi pascadeploy karena restart Telegram gagal. Bukti read-only dari proses lama sebelum deploy:

- Snapshot berjalan sekitar tiap 60 detik; log menunjukkan `updated 17 coins`, `Valid coins: 17`, dan job `snapshot_job` sukses.
- `BONE`, `FARTCOIN`, `HYPE`, dan `ZEREBRO` berulang kali gagal validasi data.
- Sampel log menunjukkan `scan_for_signals: total=17 ... no_valid_setup=17 ... passed=0`.
- Tidak ada bukti pascadeploy untuk migrasi DB, error baru, scheduler satu kali, dispatch signal, atau before/after kandidat.

## Langkah 5 — Baseline metrik

Tidak dijalankan karena deploy berhenti sebelum runtime verification. Query yang harus dijalankan setelah akses systemd diperbaiki:

```sql
SELECT source, side, setup, status, COUNT(*), ROUND(AVG(pnl_pct),2)
FROM signal_tracking
GROUP BY source, side, setup, status;
```

## TIDAK SELESAI / tindakan lanjutan

1. Sediakan otorisasi systemd non-interaktif untuk akun deploy, atau minta operator administratif menjalankan restart.
2. Ulangi restart Telegram, tunggu 60 detik, lalu cek 100 baris journal tanpa traceback.
3. Jika startup bersih, jalankan `systemctl disable --now aliza-market.service`.
4. Baru setelah itu lakukan observasi runtime 30–60 menit dan baseline SQL.
5. Jangan menganggap proses lama sebagai bukti merge commit sudah deployed.

Tidak ada `.env`, secret, parameter strategi, atau data produksi yang diubah selama langkah ini.
