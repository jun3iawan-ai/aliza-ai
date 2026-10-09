# Merge, Deploy & Verifikasi — Fix BEARISH Palsu + Fallback Konteks

Tanggal deploy: 18 September 2026
Commit production: `eac382a` — `fix: handle neutral prediction ties and failed global fallbacks`
Status: merged ke `main`, pushed ke `origin/main`, dan layanan Telegram telah direstart.

## Precheck dan merge

- `git fetch origin`: sukses.
- Sebelum merge, `main` dan `origin/main` sama-sama `23d6b0d`.
- Precheck menemukan branch fix belum memiliki commit. Dibuat commit terisolasi `eac382a` pada `fix/bearish-palsu-fallback-konteks`, hanya berisi empat file yang disetujui.
- `git diff --name-only main fix/bearish-palsu-fallback-konteks` menghasilkan tepat:

```text
engine/market/market_context_engine.py
engine/prediction/prediction_engine.py
interfaces/telegram_bot.py
tests/test_prediction_bias_and_market_context.py
```

- `git merge --ff-only fix/bearish-palsu-fallback-konteks`: sukses, `23d6b0d..eac382a` fast-forward.
- `git push origin main`: sukses, `23d6b0d..eac382a  main -> main`.

## Full test suite

Command: `venv/bin/python -m pytest -q`

```text
363 passed, 3 warnings, 74 subtests passed in 34.89s
```

Tidak ada test gagal. Tiga warning adalah deprecation warning SWIG yang sudah dikenal.

## Restart dan health check

- `sudo systemctl restart aliza-telegram.service`: sukses.
- `systemctl is-active aliza-telegram.service`: `active`.
- Restart tercatat pukul 09:56:49 WIB; observasi sampai 09:59:04 WIB mencakup lebih dari dua menit.
- Bot polling aktif, scheduler berjalan, dan snapshot lengkap untuk 17 coin berhasil pada 09:57:54 dan 09:58:54 WIB.
- Tidak ada `Traceback`, `Exception`, `PREDICT ERROR`, `QUANT ERROR`, atau `MARKET_CONTEXT ERROR` dalam log pascarestart.
## Verifikasi handler dengan snapshot live

Tidak ada connector Telegram interaktif dalam sesi deploy ini untuk mengirim Update pengguna ke polling bot. Karena itu handler dideploy dipanggil langsung menggunakan snapshot market segar dan adaptor Update lokal; teks reply di bawah adalah output handler asli. Ini memverifikasi jalur handler dan format respons, bukan injeksi pesan user lewat transport Telegram.

### `/predict`

```text
🧠 ALIZA MARKET PREDICTION

Bullish Probability : 50%
Bearish Probability : 50%

Short-term Bias : NEUTRAL
Confidence : LOW

🕒 Market Snapshot : 10:00:44
```

### `/quant`

```text
🧠 ALIZA QUANT MARKET SCORE

Bullish Score : 0
Bearish Score : 0

Market Bias : NEUTRAL
Market Strength : WEAK

Signals
Trend : SIDEWAYS
RSI : 45
Market Regime : RANGE
Whale Pressure : NEUTRAL
Altseason Prob : 35%

🕒 Market Snapshot : 10:00:44
```

Kedua output berada pada kondisi seri 0–0 dan konsisten menampilkan `NEUTRAL`, bukan `BEARISH`.

### `/market_context`

```text
🎯 Market Context Score

Total: 69/100 — Bullish 🟢

Breakdown:
• Fear & Greed: 17/20 (nilai: 56.0)
• BTC Dominance: 10/15 (nilai: 58.09%)
• Funding Rate: 25/25 (avg FR: +0.0081%)
• Makro: 12/25 (CPI: +0.40% | Fed: 3.63%)
• Teknikal: 5/15 (tidak ada sinyal)

Kondisi mendukung — pertimbangkan entry dengan manajemen risiko normal.

⏰ 2026-09-18 10:01:53 WIB
```

Breakdown tampil lengkap dan tidak ada string `None` yang bocor ke respons.

## Handoff

Deployment selesai. `main` dan `origin/main` berada pada commit `eac382a`; layanan aktif dan sehat berdasarkan observasi pascarestart.
