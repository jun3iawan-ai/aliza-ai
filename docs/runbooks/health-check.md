# Health Check Aliza AI

Checklist ringkas ini dipakai setelah deploy/restart atau ketika sistem terasa tidak responsif. Detail diagnosis ada di [troubleshooting.md](troubleshooting.md).

## Checklist

- [ ] `systemctl is-active aliza-telegram` menghasilkan `active`.
- [ ] `systemctl status aliza-telegram --no-pager` menunjuk `/opt/aliza-ai/interfaces/telegram_bot.py`.
- [ ] Journal startup tidak berisi traceback berulang atau stop-timeout/SIGKILL baru.
- [ ] Telegram merespons `/start`, `/market`, `/radar`, dan `/status` dari user yang diizinkan.
- [ ] Snapshot memiliki timestamp baru dan data coin tidak kosong.
- [ ] Market analyzer dapat membentuk data harga, trend, RSI, support/resistance, dan `trade_setup`.
- [ ] Opportunity/signal scan selesai tanpa exception; hasil kosong diterima bila log menunjukkan filter yang sah.
- [ ] `data/aliza.db` dapat dibuka aplikasi dan query trade/signal tidak error.
- [ ] Scheduler hanya berjalan di `aliza-telegram`; tidak ada instance bot/scheduler legacy yang aktif.
- [ ] Jika dashboard termasuk deployment: `GET /health` sukses, endpoint dashboard memberi 401 tanpa token dan JSON sukses dengan Bearer token sah.
- [ ] Jika shadow E3 diaktifkan: statistik menunjukkan job berjalan; dispatch tetap sesuai flag.

Sistem dinyatakan sehat bila semua item yang berlaku lulus. Bila ada item gagal, simpan output aktual dan ikuti bagian terkait di troubleshooting.
