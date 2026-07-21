# Aliza AI

Aliza AI adalah sistem analisis pasar kripto dan paper-signal berbasis Python. Sistem mengumpulkan data pasar, membangun snapshot tervalidasi, menghasilkan setup deterministik dan analisis pendukung, lalu menyampaikan hasil melalui Telegram. Aliza AI tidak mengeksekusi order ke exchange.

## Runtime utama

- Entrypoint produksi: `interfaces/telegram_bot.py`.
- Unit systemd utama: `aliza-telegram.service`.
- `aliza-market.service` berstatus disabled dan bukan scheduler produksi aktif.
- Dashboard/API berada di `api/server.py`; status servicenya dikelola terpisah dari bot Telegram.

Dokumentasi kanonik dan status dokumen tersedia di [docs/README.md](docs/README.md). Report fase dan audit bertanggal disimpan di `docs/reports/`; dokumen lama dapat tetap dipertahankan sebagai audit trail dengan status historical atau superseded.

## Menjalankan test

Dari root repo dengan virtual environment proyek:

```bash
venv/bin/python -m pytest -q
```

Perubahan dokumentasi saja tidak memerlukan eksekusi test Python, tetapi tetap harus diverifikasi dengan diff agar tidak menyentuh file kode.

