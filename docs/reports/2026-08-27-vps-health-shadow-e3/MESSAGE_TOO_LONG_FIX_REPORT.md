# Fix: Telegram "Message is too long" pada morning_brief / evening_summary

Branch: `fix/telegram-message-length` (dari `main`, belum di-push/merge)
Tanggal: 2026-08-27

## 1. Akar masalah

### 1.1 Bukti dari log produksi

`grep`/`zgrep` untuk `"Message is too long"` di seluruh `logs/aliza.log*` (termasuk
`.gz`, retensi ~8 hari) menemukan **12 kejadian** dalam periode 20–26 Agustus 2026 —
lebih banyak dari 4 kejadian yang tercatat di `VPS_HEALTH_REPORT_2.md` (laporan itu
hanya menyampel window 4 hari terakhir yang dapat diaudit):

```
logs/aliza.log.7.gz: 2026-08-20 08:00:10,327 - ERROR - root - morning_brief dispatch header: Message is too long
logs/aliza.log.7.gz: 2026-08-20 20:00:09,800 - ERROR - root - evening_summary dispatch header: Message is too long
logs/aliza.log.6.gz: 2026-08-21 08:00:11,549 - ERROR - root - morning_brief dispatch header: Message is too long
logs/aliza.log.6.gz: 2026-08-21 20:00:06,300 - ERROR - root - evening_summary dispatch header: Message is too long
logs/aliza.log.5.gz: 2026-08-22 08:00:06,495 - ERROR - root - morning_brief dispatch header: Message is too long
logs/aliza.log.4.gz: 2026-08-23 08:00:11,878 - ERROR - root - morning_brief dispatch header: Message is too long
logs/aliza.log.3.gz: 2026-08-24 08:00:46,685 - ERROR - root - morning_brief dispatch analysis: Message is too long
logs/aliza.log.3.gz: 2026-08-24 20:00:07,690 - ERROR - root - evening_summary dispatch header: Message is too long
logs/aliza.log.3.gz: 2026-08-24 20:01:03,146 - ERROR - root - evening_summary dispatch analysis: Message is too long
logs/aliza.log.2.gz: 2026-08-25 08:00:42,918 - ERROR - root - morning_brief dispatch analysis: Message is too long
logs/aliza.log.1:    2026-08-26 08:00:13,001 - ERROR - root - morning_brief dispatch header: Message is too long
logs/aliza.log.1:    2026-08-26 20:00:14,001 - ERROR - root - evening_summary dispatch header: Message is too long
```

Dua pola gagal berbeda muncul, dari `interfaces/telegram_bot.py`:
- `dispatch header` → gagal pada `safe_dispatch(brief_header, ...)` (baris ±5550/5682,
  sebelum patch) — bagian **deterministik** (bukan LLM): kondisi market, funding &
  OI per coin, makro, cross-asset, market intelligence, near-level, event besok.
- `dispatch analysis` → gagal pada `safe_dispatch(str(analysis).strip(), ...)`
  (baris ±5567/5699, sebelum patch) — teks **narasi hasil LLM** (`_generate_brief_analysis`),
  panjangnya tidak dibatasi sama sekali.

Log hanya mencatat `str(exception)` dari `python-telegram-bot`
(`telegram.error.BadRequest: Message is too long`) — Telegram API tidak
menyertakan angka limit di pesan error ini; limit resminya adalah
**4096 karakter untuk `sendMessage`** per dokumentasi Bot API
(https://core.telegram.org/bots/api#sendmessage). Isi pesan sebenarnya
tidak pernah di-log (tidak ada logging DEBUG dengan body pesan), sehingga
panjang aktual harus direkonstruksi (lihat 1.3).

### 1.2 Jalur kode & konfirmasi endpoint

`interfaces/telegram_bot.py` adalah satu-satunya modul yang mengirim
`morning_brief`/`evening_summary` (dikonfirmasi via `rg -l`). Alurnya:

- `morning_brief_job` / `evening_summary_job` (baris ~5439 / ~5584, sebelum patch)
  membangun `brief_header` dengan mengonkatenasi banyak section
  (`format_context_for_brief()`, `format_funding_section_for_brief()`,
  `_format_macro_section_for_brief_with_data_per()`, `_format_cross_asset_section()`,
  `_format_market_intelligence_section()`, `_format_near_levels_section(...)`,
  preview event besok) — **tidak ada budget/limit panjang sama sekali** di titik ini.
- Header dikirim via `await safe_dispatch(brief_header, chat_id=chat_id, force=True)`.
- Kemudian `analysis = await _generate_brief_analysis(brief_data)` (narasi LLM,
  panjang tidak dibatasi) dikirim via `await safe_dispatch(str(analysis).strip(), ...)`.
- `safe_dispatch()` → `dispatch_alert_message()` → **`await bot.send_message(chat_id=..., text=message)`**
  — dikonfirmasi ini murni `sendMessage` biasa dari `python-telegram-bot`
  (`from telegram import Bot`), bukan endpoint lain. Tidak ada `parse_mode`
  yang di-set di mana pun dalam file ini (`grep -n "parse_mode"` kosong),
  jadi pesan selalu dikirim sebagai plain text — tidak ada risiko markdown
  entity Telegram yang rusak dari sisi parser Telegram, tapi tetap
  perlu dijaga agar potongan tidak memutus kalimat/kata di tengah demi keterbacaan.
- **Sebelum patch, `dispatch_alert_message` tidak melakukan pemeriksaan panjang
  apa pun** — satu `bot.send_message()` untuk seluruh isi, apa pun panjangnya.

### 1.3 Pengukuran panjang aktual (data representatif, tanpa panggilan API baru)

Karena `get_market_snapshot()` dkk. hanya membaca cache in-memory milik proses
yang sedang berjalan (kosong bila diimpor di proses baru), dan isi pesan asli
tidak pernah di-log, panjang aktual direkonstruksi dengan menjalankan
langsung fungsi-fungsi formatter asli (bukan menulis ulang logikanya) di
proses Python sementara, dengan hanya fungsi *fetch* data eksternal (funding
rate, OI, stablecoin dominance, dsb.) yang di-monkeypatch ke nilai statis
representatif — watchlist real (`engine/market/funding_rate_monitor.WATCHLIST`,
19 coin) dan template string aslinya tetap dipakai apa adanya. Tidak ada
request jaringan baru maupun restart service. Script dijalankan dari
`/tmp` dan dihapus setelah selesai.

Hasil pengukuran header morning_brief (19 coin, kondisi representatif):

| Section | Panjang (karakter) |
|---|---|
| 🎯 Kondisi Market (`format_context_for_brief`) | 232 |
| 🔄 Funding Rate & OI (19 coin) | 1.815 |
| 🌐 Macro | 173 |
| 🌍 Cross-Asset | 144 |
| 🧠 Market Intelligence | 727 |
| 📍 Near-Level (worst case 19 coin dekat level) | 1.214 |
| Event besok (preview) | 13 |
| **TOTAL brief_header** | **4.394** |
| Limit Telegram `sendMessage` | 4.096 |

Header **deterministik saja** (belum termasuk narasi LLM) sudah **298 karakter
di atas limit** dalam skenario representatif — ini cocok dengan log
`dispatch header: Message is too long` yang terjadi berulang. Kontributor
utama pembengkakan:
- **Funding & OI per coin tidak dibatasi**: satu baris teks per coin di
  `WATCHLIST` (19 coin aktif), tanpa cap jumlah coin atau ringkasan Top-N.
- **Near-level section tidak dibatasi**: satu baris per coin per sisi
  (support/resistance) untuk semua coin yang sedang dekat level — bisa
  sampai ~19 baris saat market sedang volatile dan banyak coin dekat S/R
  bersamaan (persis skenario yang memicu error).
- **Narasi `_generate_brief_analysis` (LLM) sama sekali tidak dibatasi
  panjangnya** — ini penyebab error kategori kedua (`dispatch analysis`),
  independen dari header.

Setelah fix, `_split_message_for_telegram()` dijalankan pada teks 4.394
karakter di atas: hasilnya 2 pesan (3.791 dan 633 karakter), keduanya di
bawah 4.096 — dikonfirmasi lewat unit-level run di proses sementara yang
sama, lalu dikonfirmasi ulang end-to-end melalui `dispatch_alert_message()`
dengan bot Telegram tiruan (lihat bagian Verifikasi).

## 2. Pendekatan perbaikan

**Dipilih: split otomatis pada satu titik sentral (`dispatch_alert_message`),
bukan truncate, dan bukan helper baru yang harus dipanggil manual di tiap
call site.**

Alasan:
1. **Konsistensi otomatis**: `dispatch_alert_message()` sudah menjadi
   *single source of truth* — docstring aslinya secara eksplisit menyebut
   ini "Centralized Telegram dispatcher" dan **semua** ±20 titik kirim
   pesan di `interfaces/telegram_bot.py` (termasuk `morning_brief`,
   `evening_summary`, alert funding, alert kalender, shadow signal, dsb.)
   sudah memanggilnya lewat `safe_dispatch()`. Menaruh logic split di sana
   berarti seluruh titik kirim otomatis terlindungi tanpa perlu diubah
   satu per satu atau berisiko lupa dipasang di titik baru di masa depan.
   Ini juga menjawab kebutuhan "helper umum dipakai konsisten oleh semua
   dispatch" — helper-nya sudah eksis (`dispatch_alert_message`/`safe_dispatch`),
   jadi tidak dibuat helper paralel baru yang justru berisiko duplikasi.
   Sudah dicek dengan `rg -i "def send_.*message"` di `interfaces/` — tidak
   ada helper split/kirim-panjang lain yang sudah ada sebelumnya.
2. **Split > truncate**: truncate akan membuang informasi (mis. baris
   funding rate untuk sebagian coin, atau potongan akhir analisis LLM)
   tanpa cara bagi user melihatnya kecuali lewat command lain — padahal
   /morning_brief dan /evening_summary sendiri sudah merupakan command
   on-demand, jadi tidak ada "lihat detail via command lain" yang natural
   untuk diarahkan. Split menjaga seluruh informasi tetap terkirim.
3. **Split pada boundary alami**: karena tidak ada `parse_mode` yang dipakai
   di file ini, tidak ada risiko Telegram me-reject markdown entity yang
   terputus — namun demi keterbacaan, pemotongan tetap dicari pada batas
   `"\n\n"` (antar paragraf/section) dahulu, lalu `"\n"` (antar baris), lalu
   spasi (antar kata), dan baru hard-cut sebagai jalan terakhir jika tidak
   ada boundary yang cocok dalam window limit.
4. Setiap bagian yang terpecah diberi penanda `[lanjutan i/n]` agar user
   tahu ada pesan lanjutan menyusul.

### Implementasi

File yang diubah: **`interfaces/telegram_bot.py`** saja (modul dispatch
pesan Telegram) — tidak menyentuh `engine/shadow/`, `engine/strategy/`,
atau modul logika sinyal/trading mana pun.

- Konstanta baru: `TELEGRAM_MESSAGE_LIMIT = 4096`, `_PART_SUFFIX_RESERVE = 32`.
- Fungsi baru `_split_message_for_telegram(text, limit=TELEGRAM_MESSAGE_LIMIT) -> list[str]`:
  - Mengembalikan `[text]` **tidak berubah** (tanpa suffix apa pun) bila
    sudah muat dalam satu pesan — perilaku untuk kasus umum (pesan pendek,
    yang jadi mayoritas dispatch lain seperti alert funding/kalender/shadow)
    identik byte-per-byte dengan sebelum patch.
  - Bila melebihi limit: cari titik potong terbaik (`\n\n` → `\n` → spasi →
    hard cut) dalam window `limit - 32` karakter, ulangi sampai sisa teks
    muat, lalu tambahkan suffix `"[lanjutan i/n]"` ke tiap bagian.
- `dispatch_alert_message()` diubah dari satu panggilan
  `bot.send_message(...)` menjadi loop mengirim tiap bagian hasil
  `_split_message_for_telegram(message)` secara berurutan, memakai
  bot/semaphore/circuit-breaker/force-flag yang sama persis seperti
  sebelumnya (pengecekan itu tidak diubah, hanya bagian pengiriman akhir).

### Cuplikan diff penting

```python
def _split_message_for_telegram(text: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    if not text or len(text) <= limit:
        return [text]

    effective_limit = max(1, limit - _PART_SUFFIX_RESERVE)
    raw_chunks: list[str] = []
    remaining = text
    while len(remaining) > effective_limit:
        window = remaining[:effective_limit]
        split_at = None
        for sep in ("\n\n", "\n", " "):
            idx = window.rfind(sep)
            if idx > 0:
                split_at = idx
                break
        if split_at is None:
            split_at = effective_limit  # no natural boundary found — hard cut
        raw_chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip("\n ")
    if remaining:
        raw_chunks.append(remaining)

    total = len(raw_chunks)
    if total <= 1:
        return raw_chunks or [text]
    return [f"{chunk}\n\n[lanjutan {i}/{total}]" for i, chunk in enumerate(raw_chunks, start=1)]
```

```python
    parts = _split_message_for_telegram(message)
    for part in parts:
        await bot.send_message(chat_id=target_chat_id, text=part)
    if len(parts) > 1:
        logging.info(
            "ALERT DISPATCHED via CENTRAL GATEWAY (%d parts, %d chars total)",
            len(parts), len(message),
        )
    else:
        logging.info("ALERT DISPATCHED via CENTRAL GATEWAY")
    return True
```

`git diff --stat main`:
```
 interfaces/telegram_bot.py | 67 +++++++++++++++++++++++++++++++++++++++++++---
 1 file changed, 64 insertions(+), 3 deletions(-)
```
(plus file test baru `tests/test_message_length_guard.py`, tidak dihitung
`--stat` di atas karena file baru/belum ter-track — lihat bagian Test).
Tidak ada satu baris pun perubahan di `engine/`, `backtest/`, atau modul
lain di luar `interfaces/telegram_bot.py`.

## 3. Hasil test

Test baru: **`tests/test_message_length_guard.py`** (10 test, semua PASS):

- `SplitMessageHelperTests` (unit test murni untuk `_split_message_for_telegram`):
  - pesan pendek dikembalikan tidak berubah,
  - pesan tepat di limit 4096 tidak dipecah,
  - pesan panjang terpecah jadi >1 bagian, semua ≤ 4096,
  - pemotongan tidak pernah memutus di tengah kata (boundary check eksplisit),
  - setiap bagian dari pesan multi-part mendapat suffix `[lanjutan i/n]` yang benar,
  - string kosong ditangani tanpa error.
- `DispatchAlertMessageSplittingTests` (via `IsolatedAsyncioTestCase`, bot Telegram di-mock):
  - pesan >4096 karakter terkirim sebagai beberapa panggilan `send_message`
    ke bot tiruan, tanpa exception, `dispatch_alert_message()` mengembalikan `True`,
  - pesan pendek tetap terkirim sebagai satu panggilan tunggal (regresi
    perilaku lama tidak berubah).
- `MorningBriefEveningSummaryOversizedContentTests` (end-to-end, memanggil
  langsung `tb.morning_brief_job` dan `tb.evening_summary_job` yang sudah
  ada di produksi, dengan semua dependency data di-monkeypatch — pola yang
  sama dipakai `tests/test_near_level_on_demand.py` — dan `get_bot()`
  diarahkan ke bot tiruan): funding section dan analysis LLM sengaja dibuat
  oversize (>4096 karakter masing-masing, meniru dua mode kegagalan asli di
  log), lalu dipastikan job berjalan sampai selesai **tanpa exception** dan
  seluruh pesan yang "terkirim" ke bot tiruan berjumlah >2 (bukti splitting
  benar-benar aktif) dan tak satu pun melebihi 4096 karakter.

Full suite (`venv/bin/python -m pytest -q`, sesuai `README.md`):

```
327 passed, 3 warnings, 74 subtests passed in 39.35s
```

Seluruh 327 test (termasuk semua test lama seperti
`test_near_level_on_demand.py`, `test_fase4.py`,
`test_drawdown_broadcast_gate.py`, `test_weekly_winrate_summary.py`, dll.
yang memanggil `safe_dispatch`/`dispatch_alert_message`) tetap lulus — tidak
ada regresi.

## 4. Verifikasi

1. **Simulasi payload yang gagal**: header representatif 19-coin (4.394
   karakter, lihat 1.3) dan payload sintetis oversize (funding section
   ~5.000 karakter, analysis ~10.800 karakter, meniru dua mode kegagalan di
   log produksi) dijalankan lewat `_split_message_for_telegram()` dan
   `dispatch_alert_message()` dengan bot tiruan — keduanya **tidak lagi
   memicu "Message is too long"**, terpecah rapi jadi beberapa pesan, semua
   ≤ 4096 karakter.
2. **`git diff --stat main`**: hanya `interfaces/telegram_bot.py` (+
   test baru) yang berubah. **Nol perubahan** di `engine/shadow/`,
   `engine/strategy/`, atau modul logika sinyal/trading lain — dikonfirmasi
   perubahan murni di lapisan dispatch pesan.
3. Commit dibuat di branch `fix/telegram-message-length` (lokal saja, tidak
   di-push, tidak di-merge — menunggu review manual).

## 5. Modul/dispatch lain yang berisiko serupa tapi SENGAJA TIDAK diperbaiki (di luar scope)

Fix ini menutup celah di jalur terpusat (`dispatch_alert_message`/
`safe_dispatch`), yang dipakai oleh morning_brief, evening_summary, dan
seluruh alert terjadwal lain (funding, kalender, shadow signal, dsb.) di
`interfaces/telegram_bot.py` — semuanya otomatis ikut terlindungi karena
memakai gateway yang sama.

**Namun ada ±172 titik pemanggilan `update.message.reply_text()` /
`msg.reply_text()` di `interfaces/telegram_bot.py`** untuk command
interaktif (mis. `radarpro_command`, `marketstate_command`,
`market_context_command`, `check_funding_command`, `/analisis_coin`,
`/scan_futures`, dan puluhan command lain) — jalur ini **tidak melewati
`dispatch_alert_message`** sama sekali, memanggil API Telegram `reply_text`
langsung, sehingga **tidak ikut terlindungi oleh fix ini**. Bila konten
balasannya bertumbuh (mis. tabel funding untuk banyak coin, hasil scan
futures, atau narasi AI panjang di command interaktif), titik-titik ini
berpotensi mengalami kegagalan "Message is too long" yang sama persis.
Ini sengaja tidak disentuh di patch ini karena:
- Scope task eksplisit adalah dispatch `morning_brief`/`evening_summary`
  dan helper dispatch bersama untuk *scheduled broadcast*, bukan seluruh
  command interaktif.
- 172 titik reply_text adalah perubahan yang jauh lebih luas (berisiko
  mengubah UX command interaktif) dan butuh audit terpisah untuk
  menentukan pendekatan yang tepat per command (beberapa mungkin lebih pas
  di-truncate dengan CTA command lain, bukan di-split).

**Rekomendasi**: bila error "Message is too long" muncul lagi di log
untuk command lain (bukan morning_brief/evening_summary/alert terjadwal),
kemungkinan besar sumbernya adalah salah satu dari 172 titik `reply_text`
tersebut — audit lanjutan disarankan sebagai task terpisah.
