# Telegram Menu Restructure Report

Tanggal: 5 Agustus 2026  
Branch: `feat/telegram-menu-restructure`  
Commit: `5ebe80e feat: restructure Telegram menus`  
Basis: `main@2c283f9` (sudah mencakup fix Big Move 1h)

## Ringkasan

Restrukturisasi menu Telegram telah diimplementasikan, diuji, di-merge, di-push, dan di-deploy pada 5 Agustus 2026. Perubahan menyatukan path on-demand near-level, membuat Monitor Pasar dan Performance menjadi submenu bertingkat, memurnikan Sistem untuk administrasi, serta menambahkan command user-facing yang sebelumnya tersembunyi ke slash menu Telegram.

Scope commit hanya:

- `interfaces/telegram_bot.py`
- `tests/test_telegram_menu_restructure.py`

Tidak ada perubahan pada strategi/sinyal, helper `get_coins_near_levels()`, `_snapshot_big_move_pct()`, cooldown, deduplikasi, reversal, atau `.env`.

## Perubahan implementasi

### 1. Unifikasi Near Level

`/levels` kini memanggil `_near_levels_for_display()` (`interfaces/telegram_bot.py:6589-6598`), satu wrapper yang menjadi satu-satunya titik panggilan `get_coins_near_levels()` untuk path on-demand. Command kompatibilitas `/check_near_support` dan `/check_near_resistance` keduanya meneruskan ke `_check_near_level_side_command()` (`:6619-6640`), yang mengambil hasil wrapper yang sama lalu hanya memfilter **tampilan** berdasarkan `side` (`:6601-6616`). Dua loop kalkulasi lama telah dihapus.

Dengan demikian, filter freshness, blacklist, rentang level, dan tolerance sekarang identik dengan `/levels`; tidak ada lagi dua aturan eligibility terpisah.

### 2. Menu dan navigasi

`📊 Market` kini mempunyai `🔔 Monitor Pasar` (`telegram_bot.py:363-374`), dengan submenu berisi Levels, Big Move/RSI snapshot, Breakout, Volume Spike, dan Snapshot (`:425-436`). Router memanggil handler yang telah ada dari lokasi baru (`:547-587`). Submenu orphan `🔔 Alert & Monitor` lama dihapus, sehingga tidak ada dua jalur aktif menuju Breakout/Volume/Snapshot.

`📈 Analisis` kini membuka `📊 Performance` (`:399-409`); submenu tersebut memisahkan akurasi sinyal, kinerja trade RR/PF, ringkasan mingguan, dan riset Shadow E3 (`:439-448`, route `:695-721`).

`⚙️ Sistem` sekarang berisi fungsi admin/operasional saja: status, health, alert stats, test, debug, dan cek promosi Shadow (`:451-461`, `:750-776`). Label snapshot baru secara eksplisit menyebut `(snapshot)` (`:430`, `:573-577`).

`context.user_data["reply_menu_parent"]` menyimpan level keyboard aktif (`:464-480`): Back dari Monitor Pasar kembali ke Market dan Back dari Performance kembali ke Analisis (`:510-532`). Back dari level pertama tetap kembali ke menu utama.

Route label lama—termasuk Near Support/Resistance, RSI/Big Move lama, dan dua label Performance—tetap diterima untuk keyboard klien yang tersimpan/cached (`:715-720`, `:778-790`), tetapi tidak ada pada struktur menu baru.

### 3. Slash command dan help

`set_my_commands()` sekarang juga mendaftarkan `performance`, `alert_stats`, `snapshot`, `health`, `weekly_winrate`, dan `shadow_promotion_check` (`telegram_bot.py:7392-7419`). Command teknis `check_*` tidak ditambahkan. `/performance` diberi deskripsi **Kinerja Trade (RR/PF)** dan `/help` mendokumentasikan `/stats` sebagai alias `/signal_stats`.

## Struktur menu: sebelum → sesudah

```text
SEBELUM
📊 Market                         📈 Analisis                 ⚙️ Sistem
├─ ringkasan/radar/global         └─ Performa Sinyal          ├─ Status/Test
└─ (monitor tidak ada)                                        ├─ Near S/R
                                                              ├─ RSI/Big Move
🔔 Alert & Monitor (orphan)                                   └─ Debug
├─ Breakout / Volume Spike / Snapshot

SESUDAH
📊 Market
├─ Ringkasan Pagi / Malam / Radar / Radar Pro / Kondisi Global
└─ 🔔 Monitor Pasar
   ├─ 📍 Levels (S/R)                 → /levels, helper bersama
   ├─ 💥 Cek Big Move (snapshot)      → /check_big_move
   ├─ 🔵 Cek RSI Ekstrem (snapshot)   → /check_rsi_extreme
   ├─ 🚨 Cek Breakout
   ├─ 📊 Cek Volume Spike
   └─ 📌 Snapshot Market

📈 Analisis
├─ Konteks / Prediksi / Quant / Penjelasan AI
└─ 📊 Performance
   ├─ 📊 Akurasi Sinyal               → /signal_stats (/stats alias)
   ├─ 📈 Kinerja Trade (RR/PF)        → /performance
   ├─ 📅 Ringkasan Mingguan           → /weekly_winrate
   └─ 🧪 Riset Shadow E3              → /shadow_stats

⚙️ Sistem
├─ Status Sistem / Health Sistem / Alert Stats
├─ Test Alert / Debug Market
└─ Cek Promosi Shadow
```

## Bukti unifikasi near-level

Test menggunakan satu hasil helper yang sama:

```text
BTC  support     harga 99.5, level 99.0, jarak 0.51%
ETH  resistance  harga 104.5, level 105.0, jarak 0.48%
```

`/levels` menampilkan BTC dan ETH; command kompatibilitas Near Support menampilkan BTC dengan jarak **0.51%**, dan Near Resistance menampilkan ETH dengan jarak **0.48%**. Test mem-patch satu `_near_levels_for_display()` dan membuktikan ketiga jalur memanggilnya (3 panggilan), sehingga perbedaannya hanya filter presentasi, bukan perhitungan/eligibility. Bukti test: `tests/test_telegram_menu_restructure.py:test_levels_and_legacy_side_commands_share_the_single_display_path`.

## Hasil test

| Scope | Hasil |
|---|---|
| Fokus near-level + menu baru | `pytest tests/test_near_level_on_demand.py tests/test_telegram_menu_restructure.py -q` → **10 passed**, 3 warning. |
| Navigasi parent | Memverifikasi Market → Monitor → Back → Market dan Analisis → Performance → Back → Analisis. |
| Route Monitor Pasar | Memverifikasi route Levels, Big Move snapshot, RSI snapshot, Breakout, Volume Spike, Snapshot ke handler yang tepat. |
| Slash menu | Memverifikasi argumen aktual `set_my_commands()` mengandung enam command baru. |
| Regresi penuh (worktree terisolasi) | `pytest tests/ test_telegram_authorization.py test_dashboard_*.py -q` → **298 passed, 3 warnings, 74 subtests passed** (36,82 dtk). |

## Status handoff

## Deploy, verifikasi live, dan push

### Merge dan test

| Tahap | Hasil |
|---|---|
| Commit feature | `5ebe80e feat: restructure Telegram menus` |
| Merge commit | `5613f95 Merge branch feat/telegram-menu-restructure` (non-fast-forward) |
| Scope merge | Tepat `interfaces/telegram_bot.py` dan `tests/test_telegram_menu_restructure.py`; tidak ada file strategi/sinyal atau helper market berubah. `get_coins_near_levels()`, `_snapshot_big_move_pct()`, cooldown, dedup, dan reversal tidak diubah. |
| Regresi pra-merge | **298 passed, 3 warnings, 74 subtests passed** (34,80 dtk), worktree terisolasi. |
| Regresi pasca-merge | **298 passed, 3 warnings, 74 subtests passed** (35,10 dtk), worktree terisolasi. |

### Restart service

`aliza-telegram.service` direstart dan aktif dengan PID `3200854` sejak 08:18:34 WIB. Startup menyelesaikan snapshot awal 17 coin dan masuk polling pada 08:19:25 WIB (`AlizaAI Telegram Bot aktif (polling). Semua command terdaftar.`). Tidak ada `set_my_commands failed`, error pembentukan keyboard, atau exception router pada 150 baris journal pasca-restart yang diperiksa.

### Bukti slash command live

Panggilan Telegram Bot API **read-only** `getMyCommands` menghasilkan `HTTP 200`, `ok=True`, dengan daftar:

```text
start, help, market, radar, setfutures, entry, close, portfolio,
set_balance, balance, status, levels, performance, alert_stats,
snapshot, health, weekly_winrate, shadow_stats, shadow_promotion_check
```

Keenam command baru semuanya hadir: `performance`, `alert_stats`, `snapshot`, `health`, `weekly_winrate`, dan `shadow_promotion_check`; tidak ada yang hilang.

### Cek konsistensi command near-level live

Probe non-mutating menjalankan snapshot Binance live lalu memanggil handler `/levels`, `/check_near_support`, dan `/check_near_resistance` dengan output ditangkap lokal (tidak mengirim pesan Telegram). Hasil 08:21:53 WIB:

```text
support: tidak ada
resistance: BNB 0.7949%, BTC 0.2068%, ETH 0.9515%,
            SOL 0.7548%, SUI 0.9312%, XPL 0.3693%
```

`/levels` memuat keenam resistance tersebut dengan angka yang sama; `/check_near_resistance` juga memuat keenam coin dan angka yang sama. `/check_near_support` dan bagian support `/levels` sama-sama menyatakan tidak ada coin. Ini bukti live bahwa tiga command memakai eligibility/path yang konsisten.

### Verifikasi visual Telegram

**Belum dilakukan.** Tidak ada sesi akun Telegram admin interaktif yang tersedia dalam sesi ini, sehingga saya tidak mengirim `/start` maupun menavigasi menu secara otomatis. User perlu mengonfirmasi secara visual setelah deploy:

1. Market → Monitor Pasar → Back kembali ke Market.
2. Analisis → Performance → Back kembali ke Analisis.
3. Sistem hanya menampilkan item admin.

### Push dan cleanup

Push berhasil: `2c283f9..5613f95  main -> main`. `origin/main` menunjuk `5613f95`; branch lokal `feat/telegram-menu-restructure` telah dihapus. Tidak ada perubahan `.env`.
