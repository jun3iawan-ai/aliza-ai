# Aliza AI

Aliza AI adalah sistem analisis pasar kripto dan paper-signal berbasis Python. Sistem mengumpulkan data pasar, membangun snapshot tervalidasi, menghasilkan setup deterministik dan analisis pendukung, lalu menyampaikan hasil melalui Telegram. Aliza AI tidak mengeksekusi order ke exchange.

## Runtime utama

- Entrypoint produksi: `interfaces/telegram_bot.py`.
- Unit systemd utama: `aliza-telegram.service`.
- `aliza-market.service` disabled dan bukan scheduler produksi aktif.
- Dashboard/API berada di `api/server.py`, diluncurkan melalui `scripts/run_dashboard.py`, dan dikelola terpisah dari bot Telegram.

## Dokumentasi

Indeks dan status source of truth tersedia di [docs/README.md](docs/README.md).

- [Aturan coding agent](docs/agent-rules/coding/)
- [Aturan runtime LLM](docs/agent-rules/runtime/)
- [Arsitektur](docs/architecture/)
- [Runbook operasional](docs/runbooks/)
- [Report fase dan maintenance](docs/reports/)
- [Audit historis](docs/audits/)

Dokumen di `docs/audits/` dan `docs/reports/` adalah snapshot bertanggal. Jangan menggunakannya sebagai status runtime terkini tanpa memeriksa tanggal dan commit.

## Test

Dari root repo dengan virtual environment proyek:

```bash
venv/bin/python -m pytest -q
```

Kebijakan lengkap tersedia di [docs/architecture/testing.md](docs/architecture/testing.md); verifikasi manual setelah deploy ada di [docs/runbooks/smoke-test.md](docs/runbooks/smoke-test.md).

