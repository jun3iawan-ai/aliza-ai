# Panduan Dev Lokal (WSL2) dan Alur Deploy ke VPS

Dibuat 9 Nov 2026. Tujuan: perubahan kode dikerjakan dan dites di laptop, VPS hanya menarik kode yang sudah lulus tes.
Terverifikasi: clone bersih + venv baru + tanpa `.env` + tanpa cache model Hugging Face di Linux (Python 3.10.12) = **575 tes lulus** (±33 dtk).
Belum diuji di WSL asli milik Jun; bagian yang belum terbukti diberi tanda (belum diuji).

## 0. Prasyarat
- Windows 10 versi 2004+ atau Windows 11. Disk bebas minimal ±15 GB (venv terukur **6,7 GB**, belum termasuk WSL).
- RAM disarankan 8 GB ke atas. Opsional batasi memori WSL di `C:\Users\<nama>\.wslconfig`:
  ```
  [wsl2]
  memory=6GB
  processors=4
  ```
  lalu `wsl --shutdown`.

## 1. Pasang WSL2 (PowerShell sebagai Administrator)
```
wsl --install -d Ubuntu-22.04
wsl -l -v          # kolom VERSION harus 2
```
Restart bila diminta, lalu buat user Ubuntu. Ubuntu 22.04 membawa Python 3.10 (sama dengan VPS).

## 2. Paket dasar (di terminal Ubuntu)
```
sudo apt update && sudo apt install -y git python3 python3-venv python3-pip build-essential
python3 --version   # 3.10.x
git config --global user.name "<nama>"
git config --global user.email "<email>"
```

## 3. Akses GitHub (SSH key khusus WSL)
```
ssh-keygen -t ed25519 -C "wsl-laptop"
cat ~/.ssh/id_ed25519.pub     # tempel di GitHub > Settings > SSH and GPG keys
ssh -T git@github.com
```
Jangan menyalin key atau token dari VPS.

## 4. Clone (di filesystem WSL, BUKAN /mnt/d)
```
cd ~ && git clone git@github.com:jun3iawan-ai/aliza-ai.git && cd aliza-ai
git log --oneline -1
```
Jangan menaruh repo/`.env` di `D:\My System\AlizaAI-Crypto` (folder itu terhubung ke sesi Claude).

## 5. Virtualenv dan dependensi
```
python3 -m venv venv
venv/bin/pip install -r requirements-dev.txt
```
Ukuran ±6,7 GB, ±10 menit di VPS (lebih lama bila internet lambat). Nama venv `venv` atau `.venv` sama-sama aman
(tes pemindai dotenv sudah melewati keduanya sejak commit `660dd6e`).
(belum diuji) Mengecilkan ukuran dengan torch versi CPU: `venv/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu` sebelum langkah di atas.

## 6. Jalankan tes
```
venv/bin/python -m pytest -q
```
Harapan: **575 passed**. Tes tidak butuh `.env`, jaringan produksi, atau model Hugging Face; `tests/conftest.py` mengisolasi cache dan path.

## 7. Menjalankan bot lokal (opsional)
```
cp .env.example .env     # isi sendiri; JANGAN salin .env produksi
```
- `TELEGRAM_BOT_TOKEN` dan `TELEGRAM_CHAT_ID`: bot **staging** buatan sendiri (BotFather). Satu token tidak boleh dipakai dua proses.
- `IS_PRIMARY_DISPATCHER=true`; key lain boleh kosong (fitur terkait tidak aktif).
- Arahkan file Porto ke salinan lokal supaya tidak menyentuh yang asli:
  ```
  mkdir -p ~/aliza-local
  export MARKET_CONTEXT_PATH=$HOME/aliza-local/context.json
  export PORTO_COINS_PATH=$HOME/aliza-local/coins.json
  echo '{"v":1,"source":"lokal","symbols":["BTC","ETH","SOL"],"coins":[]}' > $PORTO_COINS_PATH
  venv/bin/python interfaces/telegram_bot.py
  ```
- Pertama kali jalan, `core/knowledge_base.py` mengunduh model `all-MiniLM-L6-v2` (±90 MB). Hanya perlu untuk bot, bukan untuk tes.

## 8. Alur kerja harian
1. `git checkout main && git pull --ff-only` lalu `git checkout -b fix/nama-singkat`.
2. Edit, `pytest -q` sampai hijau.
3. Commit, push branch. Gabung ke `main` dengan merge `--no-ff` (lewat PR GitHub atau lokal), push `main`.
4. Beri tag rilis sebelum deploy: `git tag -a rel-YYYYMMDD-N -m "..." && git push --tags`.

## 9. Deploy ke VPS (VPS hanya menarik)
- Minta Claude menjalankan, atau manual di VPS: `cd /opt/aliza-ai && scripts/deploy/deploy.sh`.
- `deploy.sh` menolak jalan bila working tree kotor atau branch bukan `main`, lalu `git pull --ff-only origin main` dan restart `aliza-telegram`.
- Sesudahnya: cek journal PID baru (0 error/traceback) dan smoke test `docs/runbooks/smoke-test.md`.
- Rollback: `docs/runbooks/deploy-restart-rollback.md` (checkout ke tag sebelumnya, restart). Jangan `git reset --hard`.

## 10. Aturan
- VPS tidak diedit manual. Hotfix darurat: commit di VPS, segera `git push`, lalu `git pull` di laptop (kalau tidak, `deploy.sh` gagal karena tree kotor/divergen).
- Tidak dites di laptop: path dan izin `/var/lib/market-context` dan `/var/lib/porto`, systemd, jaringan Binance/FRED dari IP VPS, tuning yang butuh data live. Karena itu smoke test pasca-deploy tetap wajib.
- Jangan menyentuh `/opt/metamask-bot`, user `mmbot`, atau menulis ke `/var/lib/porto` (tetap berlaku).
- Rahasia tidak masuk git: `.env` dan `data/` sudah di-`.gitignore`; jangan commit file kredensial.

## 11. Kondisi awal terverifikasi (9 Nov 2026)
`main` di GitHub = VPS = `660dd6e`; working tree VPS bersih; 575 tes lulus di clone bersih.
