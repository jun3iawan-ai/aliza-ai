# Audit Read-Only: Duplikasi "KEPUTUSAN HARI INI" & SARAN SPOT Hilang di Evening Summary

**Tanggal audit:** 2026-08-31
**Kejadian:** 2026-08-31 13:22-13:23 WIB
**Tipe:** Audit read-only murni. Tidak ada perubahan kode/commit/restart/dispatch di task ini.

---

## Ringkasan eksekutif

Dua bug independen ditemukan, keduanya di jalur narasi LLM (`_generate_brief_analysis` dan fungsi-fungsi pendukungnya di `interfaces/telegram_bot.py`), **bukan** di jalur trading signal deterministik/E3 shadow:

1. **Duplikasi "⚡ KEPUTUSAN HARI INI"**: satu-satunya panggilan LLM untuk section 6-bagian (`main_prompt` via `_call_llm_async`) mengembalikan completion yang isinya SUDAH mengandung dua blok penuh 6-section secara berurutan. Kode dedup yang ada hanya membuang teks setelah marker `SARAN SPOT`/`SARAN FUTURES`/`DISCLAIMER` — tidak pernah memeriksa duplikasi header `⚡ KEPUTUSAN HARI INI` itu sendiri, sehingga kedua blok lolos ke pesan final.
2. **Header "🟢 SARAN SPOT" hilang total**: prompt `_generate_spot_analysis` (baris 4162, `interfaces/telegram_bot.py`) menyuruh LLM, untuk kondisi "tidak ada setup layak", **"Tulis: Tidak ada setup spot yang layak..."** — instruksi ini TIDAK mengulang header di dalam contoh, sehingga LLM cenderung mengabaikan header sama sekali. Prompt `_generate_futures_analysis` (baris 4343-4344) untuk kondisi yang sama justru mengulang header penuh di dalam contoh bracket-nya. Asimetri prompt inilah yang menjelaskan mengapa SARAN FUTURES tetap tampil dengan header sedangkan SARAN SPOT hilang total.

Ditambah satu temuan pendukung: dispatch "header" deterministik (`brief_header`, section KONDISI MARKET/funding/dst.) gagal terkirim dengan error asli Telegram **"Message is too long"**, walau sudah lolos pengecekan panjang `_split_message_for_telegram()` — kemungkinan besar karena fungsi split menghitung panjang pakai `len()` Python (code point), sementara batas 4096 milik Telegram dihitung dalam UTF-16 code unit, dan hampir semua emoji yang dipakai di header (🌅🌙🎯🚨📊📈🟢🌍📅🕒📋🔔💹🟡🔴) adalah karakter astral-plane yang makan 2 UTF-16 unit tapi cuma dihitung 1 oleh `len()`. Ini bug terpisah dari #1 dan #2, tapi menjelaskan kenapa pesan "Ringkasan Malam" yang diterima user langsung mulai dari "⚡ KEPUTUSAN HARI INI" tanpa section header market data di depannya (beda dari contoh scheduled 30 Agustus 20:00 yang terkirim sebagai 2 pesan terpisah).

Kedua bug (#1 dan #2) murni terjadi pada **satu panggilan LLM tunggal per section** — bukan pemicu ganda dari command/scheduler, bukan proses duplikat, bukan retry internal yang menggabungkan hasil.

---

## 1. Berapa kali evening_summary di-dispatch pada window 13:15-13:30 WIB?

**Jawaban: kedua ringkasan (pagi & malam) dipicu MANUAL sekali masing-masing, via tombol menu Telegram, bukan scheduler. Tidak ada duplikasi trigger.**

Bukti dari `logs/aliza.log` (timestamp log = WIB lokal, dikonfirmasi dari `timedatectl` — server bertimezone Asia/Jakarta, dan baris log APScheduler sendiri menunjukkan offset 7 jam ke UTC):

```
2026-08-31 13:22:30,708 - INFO - root - COMMAND RECEIVED: /morning_brief
2026-08-31 13:22:36,233 - ERROR - root - morning_brief dispatch header: Message is too long
2026-08-31 13:22:49,204 - INFO - root - ALERT DISPATCHED via CENTRAL GATEWAY

2026-08-31 13:23:32,200 - INFO - root - COMMAND RECEIVED: /evening_summary
2026-08-31 13:23:37,273 - ERROR - root - evening_summary dispatch header: Message is too long
2026-08-31 13:23:48,298 - INFO - root - ALERT DISPATCHED via CENTRAL GATEWAY
```

Masing-masing command (`/morning_brief`, `/evening_summary`) muncul **tepat satu kali** di window ini, dan masing-masing hanya menghasilkan **satu** baris `ALERT DISPATCHED via CENTRAL GATEWAY` (bukan dua) — karena dispatch pertama (`brief_header`) gagal dengan exception yang di-catch (lihat `interfaces/telegram_bot.py:5610-5613` dan `:5742-5745`), jadi yang benar-benar terkirim ke user hanya pesan `analysis` (hasil `_generate_brief_analysis`). Ini menjelaskan kenapa pesan yang diterima user langsung mulai dari "⚡ KEPUTUSAN HARI INI" tanpa section market-data header di depannya, berbeda dari contoh scheduled 30 Agustus 20:00 yang terkirim 2 pesan terpisah (header header berhasil + analysis).

**Trigger source**: Tombol reply-keyboard "🌅 Ringkasan Pagi" / "🌙 Ringkasan Malam" (menu Market) memanggil `morning_brief_command`/`evening_summary_command` secara langsung (`interfaces/telegram_bot.py:618-623`):

```python
if text == "🌅 Ringkasan Pagi":
    await morning_brief_command(update, context)
    return
if text == "🌙 Ringkasan Malam":
    await evening_summary_command(update, context)
    return
```

Catatan minor: `logging.info("COMMAND RECEIVED: /morning_brief")` di `morning_brief_command` (baris 5641) dan `/evening_summary` di `evening_summary_command` (baris 5773) **selalu mencetak literal "/morning_brief"/"/evening_summary"** apa pun jalur pemicunya (slash command asli ATAU tombol menu) — jadi log ini tidak bisa dipakai untuk membedakan slash command vs tap tombol. Tidak berdampak ke bug, hanya membuat log sedikit ambigu.

**Instance check**: hanya **satu** proses `telegram_bot.py` berjalan (PID 191620, aktif sejak 21 Agustus, dikonfirmasi via `ps aux` dan `systemctl status aliza-telegram.service`) — tidak ada proses duplikat/race antar-instance yang bisa menyebabkan double-dispatch.

**Kesimpulan poin 1**: dugaan awal prompt bahwa manual command punya logic terpisah dari scheduled job **tidak terbukti** — `morning_brief_command`/`evening_summary_command` (baris 5640-5642, 5772-5774) hanya memanggil `morning_brief_job`/`evening_summary_job` secara langsung, fungsi yang **sama persis** dengan yang dipakai APScheduler untuk jadwal 08:00/20:00. Root cause duplikasi BUKAN soal jalur command vs scheduler — ini murni soal isi output LLM pada satu panggilan tunggal (lihat poin 2), yang bisa saja muncul juga di run terjadwal kapan pun modelnya "kambuh".

---

## 2. Kenapa main_out mengandung 2 blok "⚡ KEPUTUSAN HARI INI"?

**Jawaban: satu completion LLM (bukan loop/retry) mengembalikan teks yang sudah berisi dua blok penuh; tidak ada dedup untuk header berulang.**

### Bukti: tidak ada retry/pemanggilan ganda

`_generate_brief_analysis` (baris 4381) memanggil 3 LLM secara paralel via `asyncio.gather`:

```python
main_out, spot_raw, fut_raw = await asyncio.gather(
    _call_llm_async(main_prompt),
    _generate_spot_analysis(brief_data, coin_details, _cross_bundle=cross_bundle),
    _generate_futures_analysis(brief_data, coin_details, _cross_bundle=cross_bundle),
)
```

Log window untuk `/evening_summary` (13:23:32-13:23:48) menunjukkan **tepat 3** baris `OpenAI API usage`:

```
13:23:41,820 - OpenAI API usage: {...'total_tokens': 38341, 'cached_prompt_tokens': 37120}
13:23:46,222 - OpenAI API usage: {...'total_tokens': 41586, 'cached_prompt_tokens': 38272}
13:23:47,000 - OpenAI API usage: {...'total_tokens': 41495, 'cached_prompt_tokens': 40960}
```

(Pola sama untuk `/morning_brief`: tepat 3 baris.) Baris log ini berasal dari `crewai/llms/providers/openai/completion.py:1664` (`logging.info(f"OpenAI API usage: {usage}")`), yang dieksekusi **satu kali per panggilan `chat.completions.create()` aktual** — bukan agregat. Tidak ada baris `_generate_brief_analysis: gather failed` di log (yang berarti jalur fallback-retry di baris 4671-4682 tidak pernah tereksekusi). Kesimpulannya: `main_prompt` benar-benar hanya dipanggil **sekali**, dan responsnya sendiri (single completion dari `gpt-4o-mini`, via `core/agent.py`) sudah berisi dua blok.

### Kenapa dedup yang ada tidak menangkapnya

Kode dedup di `_generate_brief_analysis` (baris 4724-4731) hanya mencari 3 marker spesifik:

```python
for _marker in ("SARAN SPOT", "SARAN FUTURES", "DISCLAIMER"):
    if _marker in main_out:
        _lines = main_out.split("\n")
        _cut = next((i for i, l in enumerate(_lines) if _marker in l), None)
        if _cut is not None:
            main_out = "\n".join(_lines[:_cut]).strip()
            break
```

Ini didesain untuk kasus LLM "bocor" menulis section SARAN SPOT/FUTURES/DISCLAIMER padahal `main_prompt` sudah eksplisit melarangnya ("Jawab HANYA dengan 6 section... Jangan saran spot/futures", baris 4658). **Tidak ada pengecekan apakah `⚡ KEPUTUSAN HARI INI` muncul lebih dari sekali** di dalam `main_out`. Pola output yang dilaporkan user — dua blok KEPUTUSAN penuh lalu langsung ke disclaimer Entry/SL/Target tanpa SARAN SPOT sama sekali — cocok dengan skenario: completion asli LLM berisi [blok1 6-section] + [blok2 6-section, mengulang instruksi format dari awal] + [LLM lanjut menulis SARAN SPOT/FUTURES/DISCLAIMER juga, padahal dilarang] → dedup marker `"SARAN SPOT"` (prioritas pertama dalam loop) ditemukan → **semua teks sebelum baris itu dipertahankan apa adanya** (termasuk kedua blok duplikat), dan section SARAN SPOT hasil hallucinated LLM di dalam `main_out` ikut terpotong bersama sisanya.

Ini juga konsisten dengan disclaimer generik `⚠️ DISCLAIMER` yang seharusnya cuma muncul sekali di akhir pesan (baris 4719-4723, ditambahkan programmatic, bukan dari LLM) — user melaporkan disclaimer "Entry/SL/Target di atas estimasi AI (LLM)..." (bukan disclaimer generik ini, lihat poin 3) muncul, yang berasal dari `spot_section`/`futures_section` terpisah, bukan dari `main_out`.

**Kesimpulan poin 2**: root cause murni ada di sisi output LLM (satu completion `gpt-4o-mini` yang mengulang instruksi format dari awal alih-alih berhenti setelah section ke-6 seperti diminta) digabung dengan **guardrail dedup yang tidak lengkap** — dedup yang ada mengasumsikan pelanggaran LLM hanya berupa "section tambahan yang tidak diminta" (spot/futures/disclaimer bocor), bukan "instruksi 6-section diulang dari awal". Tidak ditemukan bukti loop/retry/concatenation eksplisit di kode `telegram_bot.py`, `_call_llm_async`, maupun di `crewai`/`core/agent.py` (`ask_aliza` hanya satu `crew.kickoff()` per panggilan, tanpa retry loop kustom).

---

## 3. Kenapa header "🟢 SARAN SPOT" hilang total padahal disclaimer-nya tetap ada?

**Jawaban: asimetri prompt antara `_generate_spot_analysis` dan `_generate_futures_analysis` untuk kondisi "tidak ada setup" — spot tidak mengulang header di contoh, futures mengulang.**

### Prompt SARAN SPOT (`_generate_spot_analysis`, baris 4160-4163):

```
OUTPUT FORMAT (HANYA section ini, tidak ada section lain):
🟢 SARAN SPOT (Swing 1-7 hari)
[Jika tidak ada setup: "Tidak ada setup spot yang layak — tunggu pullback ke support."]
[Jika ada setup, maksimal 3 coin terbaik:]
```

Instruksi kondisi "tidak ada setup" berupa kalimat tunggal dalam tanda kutip, TANPA header di dalamnya. Ditambah `_action_constraint` (baris 4134) untuk kondisi bearish/fear ekstrem eksplisit menyuruh: `"TAHAN — JANGAN rekomendasikan entry baru. Tulis: Tidak ada setup spot yang layak — tunggu pullback ke support."` — kalimat "Tulis: X" ini gampang dibaca model sebagai "seluruh output = X", tanpa header.

### Prompt SARAN FUTURES (`_generate_futures_analysis`, baris 4342-4344) untuk kondisi setara:

```
OUTPUT FORMAT (HANYA section ini):
📊 SARAN FUTURES (Swing 1-7 hari)
[Jika kondisi tidak mendukung: "📊 SARAN FUTURES (Swing 1-7 hari)
Kondisi tidak mendukung futures saat ini."]
```

Di sini, contoh untuk kondisi "tidak mendukung" **mengulang header lengkap** di dalam tanda kutip contoh. Ini instruksi yang jauh lebih eksplisit dan tahan salah-interpretasi dibanding versi spot.

Ini bukan dugaan buta — ini perbedaan literal string di dua prompt yang seharusnya paralel, dan cocok 100% dengan gejala yang dilaporkan: SARAN FUTURES muncul dengan header + isi fallback ("Kondisi tidak mendukung futures saat ini."), SARAN SPOT hilang total headernya.

### Kenapa fallback kode tidak menyelamatkan

Di `_generate_spot_analysis` (baris 4186-4192), fallback header HANYA dipakai kalau LLM benar-benar kosong/timeout:

```python
out = await _call_llm_async(prompt)
if out:
    return out          # dipercaya mentah-mentah, TANPA verifikasi header ada
return (
    "🟢 SARAN SPOT (Swing 1-7 hari)\n"
    "Tidak ada setup spot yang layak — tunggu pullback ke support. (LLM timeout/error)"
)
```

Kalau LLM merespons non-kosong TAPI lupa nulis header (skenario paling mungkin di sini), `out` (tanpa header) dikembalikan apa adanya sebagai `spot_raw`.

Lalu di `_generate_brief_analysis` (baris 4703-4708):

```python
spot_section = _reorder_section_by_rr(spot_raw, is_spot=True).strip()
if not spot_section:
    spot_section = spot_raw.strip() if spot_raw.strip() else (
        "🟢 SARAN SPOT (Swing 1-7 hari)\n"
        "Tidak ada setup spot yang layak — tunggu pullback ke support."
    )
```

`_reorder_section_by_rr` (baris 2953) memproses `spot_raw` baris demi baris: karena tidak ada baris bullet (`•`/`-`/dst.) — kondisi "tidak ada setup" memang tidak punya entry coin — SELURUH teks (termasuk kalimat "Tidak ada setup spot yang layak...", TANPA header karena memang tidak ada di `spot_raw`) masuk ke `header_lines`, lalu di akhir fungsi (baris 3300-3309) ditambahkan baris disclaimer "⚠️ Entry/SL/Target di atas estimasi AI (LLM)..." secara **programatik, tidak bersyarat pada keberadaan header** — inilah baris "⚠️ Entry/SL/Target..." yang dilaporkan user tetap muncul walau header sudah hilang. Karena `spot_section` hasilnya **non-empty** (`if not spot_section:` = False, sebab isinya kalimat + disclaimer), cabang fallback header (`spot_raw.strip() if spot_raw.strip() else (...ada header...)`) **tidak pernah tereksekusi** — jadi fallback header di baris 4706-4708 itu sia-sia untuk kasus ini, karena hanya jalan kalau `spot_raw` benar-benar string kosong, bukan kalau `spot_raw` non-kosong tapi tanpa header.

**Kesimpulan poin 3**: konfirmasi hipotesis dari user — baris disclaimer "Entry/SL/Target..." memang punya jalur cetak SENDIRI yang terpisah dari validasi keberadaan header (ditambahkan tanpa syarat di `_reorder_section_by_rr` baris 3300), sehingga saat LLM `_generate_spot_analysis` gagal menyertakan header (dipicu oleh instruksi prompt yang ambigu untuk kondisi "tidak ada setup"), disclaimer tetap tercetak sementara header+konten section-nya sendiri hilang. Ini **tidak terkait** dengan bug duplikasi di poin 2 — dua bug independen yang kebetulan muncul bersamaan di pesan yang sama, karena kondisi market saat itu (skor rendah / fear-greed rendah) memicu cabang "TAHAN" di kedua prompt spot DAN futures sekaligus.

---

## 4. Verifikasi isolasi dari jalur sinyal produksi/shadow

**Jawaban: isolasi TERKONFIRMASI untuk `e3_shadow.py` dan `trading_brain.py`, TAPI ada satu jalur tertulis (bukan dibaca) ke `signal_tracker.py` yang perlu dicatat — sudah ada by design sejak audit 21 Juli, tidak berubah, dan tidak menyebabkan pencatatan salah pada insiden kali ini.**

```
$ grep -rln "_generate_brief_analysis\|_generate_spot_analysis\|_generate_futures_analysis\|evening_summary_job\|morning_brief_job" --include="*.py" .
tests/test_message_length_guard.py
tests/test_near_level_on_demand.py
tests/test_evening_summary_report.py
interfaces/telegram_bot.py
```

Tidak ada satu pun referensi dari `engine/shadow/e3_shadow.py` atau `engine/trading/trading_brain.py` ke fungsi-fungsi narasi LLM ini, dan sebaliknya — fungsi-fungsi ini tidak memanggil apa pun dari kedua modul tersebut. Isolasi terhadap E3 shadow dan TradingBrain **terkonfirmasi utuh**, tidak ada perubahan sejak `EVENING_SUMMARY_AUDIT_FIX_REPORT.md` (21 Juli).

Yang perlu dicatat (bukan regresi baru, tapi relevan untuk konteks): `morning_brief_job`/`evening_summary_job` **memang** memanggil `_parse_and_record_signals(str(analysis), market_score=_ms)` setelah dispatch sukses (baris 5635, 5767), yang mem-parsing bullet-point coin entries (`• COIN ...` dengan Entry/SL/Target) dari teks `analysis` dan menulis ke `signal_tracking` via `record_signal()` (`engine.trading.signal_tracker`) dengan `"source": "llm"` — field ini secara eksplisit membedakannya dari sinyal `"source": "deterministic"` yang dicatat oleh jalur TradingBrain/E3 (`_dispatch_and_record_deterministic_signal`, baris 7400). Jadi **tidak murni "sama sekali terpisah"** dari `signal_tracker.py` di level modul — tapi ditandai sumbernya secara eksplisit, sehingga tidak bisa mencemari statistik/winrate jalur deterministik.

**Untuk insiden 31 Agustus spesifik ini**: `_parse_and_record_signals` mencari pola `•\s+\w` (bullet coin entry). Karena pada insiden ini SARAN SPOT tidak punya bullet entry (header+isinya hilang total, cuma kalimat "tidak ada setup") dan SARAN FUTURES juga fallback teks polos ("Kondisi tidak mendukung futures saat ini", tanpa bullet), maka **tidak ada bullet entry sama sekali di `analysis`** yang dikirim → `_parse_and_record_signals` tidak menemukan match apa pun → **tidak ada record yang tertulis ke `signal_tracking` akibat insiden ini** (baik record ganda maupun record salah). Risiko residual untuk masa depan: kalau bug duplikasi/hilang-section di poin 2/3 terjadi PADA SAAT market sedang punya setup valid (bukan kondisi TAHAN seperti kali ini), duplikasi blok bisa saja ikut menduplikasi bullet entry coin, yang berpotensi menulis record `source="llm"` dobel ke `signal_tracking`. Ini layak dipertimbangkan sebagai bagian scope fix berikutnya (idempoten/dedup di `_parse_and_record_signals` sendiri), walau di luar 4 pertanyaan utama audit ini.

---

## Temuan tambahan: dispatch header gagal dengan "Message is too long"

Tidak diminta eksplisit di 4 poin, tapi relevan untuk poin 1 (kenapa struktur pesan manual beda dari contoh scheduled 30 Agustus) dan untuk gambaran lengkap kejadian:

```
2026-08-31 13:22:36,233 - ERROR - root - morning_brief dispatch header: Message is too long
2026-08-31 13:23:37,273 - ERROR - root - evening_summary dispatch header: Message is too long
```

Baris ini berasal dari `except Exception as e: logging.error("evening_summary dispatch header: %s", e)` di `evening_summary_job` (baris 5742-5745), membungkus `await safe_dispatch(brief_header, chat_id=chat_id, force=True)`. String error "Message is too long" **tidak ditemukan** di source `python-telegram-bot` versi 20.7 yang terpasang (`/home/ubuntu/.local/lib/python3.10/site-packages/telegram`) — artinya ini string asli dari respons error Telegram Bot API server, bukan validasi lokal.

`dispatch_alert_message` (baris 334-366) sudah memakai `_split_message_for_telegram()` (baris 296-331) yang seharusnya memecah pesan panjang menjadi beberapa part di bawah `TELEGRAM_MESSAGE_LIMIT = 4096` (baris 219) dikurangi reserve 32 karakter untuk suffix `[lanjutan i/n]`. **Tapi** panjang dihitung pakai `len(text)` Python biasa — yaitu jumlah *code point* Unicode, bukan jumlah *UTF-16 code unit* yang dipakai Telegram untuk menghitung limit 4096-nya. Hampir semua emoji yang dipakai di `brief_header` (🌅🌙🎯🚨📊📈🟢🌍📅🕒📋🔔💹🟡🔴 — semuanya di luar Basic Multilingual Plane) memakan **2 UTF-16 unit tapi cuma dihitung 1 oleh `len()`** (diverifikasi langsung: `len('🌅'.encode('utf-16-le'))//2 == 2` sementara `len('🌅') == 1`). `brief_header` memuat banyak section dengan emoji berulang (funding per-coin, cross-asset, market intelligence, near-level, dst.) — kalau jumlah emoji astral-plane di sebuah chunk cukup banyak, chunk itu bisa lolos cek `len(text) <= effective_limit` di Python padahal secara UTF-16 (ukuran yang dipakai Telegram) sudah melebihi 4096, sehingga `bot.send_message()` ditolak Telegram dengan "Message is too long" walau sudah melalui `_split_message_for_telegram()`.

Ini konsisten dengan kenapa jalur SAMA PERSIS berhasil di contoh scheduled 30 Agustus 20:00 (isi/panjang data market hari itu kebetulan tidak menyentuh batas ini) tapi gagal di 31 Agustus 13:22-13:23 (kombinasi data market + jumlah emoji hari itu kebetulan pas melewati batas UTF-16 walau masih di bawah batas `len()` Python). Bug ini **independen** dari bug duplikasi (poin 2) dan bug header hilang (poin 3) — efeknya cuma bikin pesan "header market data" (KONDISI MARKET/funding/dst.) gagal terkirim sama sekali, sehingga pesan yang diterima user (`analysis` saja) langsung mulai dari "⚡ KEPUTUSAN HARI INI" tanpa konteks market di depannya.

---

## Verifikasi tambahan (prioritas rendah): SL Spot vs Futures ETH beda persentase

Dikonfirmasi **wajar/by design**, bukan bug. `_generate_spot_analysis` dan `_generate_futures_analysis` adalah **dua panggilan LLM independen** (baris 4666-4669, dijalankan paralel via `asyncio.gather`), masing-masing dengan prompt sendiri dan tidak saling melihat output satu sama lain. `_reorder_section_by_rr` (dipanggil terpisah untuk tiap section, baris 4703 & 4711) punya guardrail `enforce_sl_range()` (baris 3025-3051) yang **hanya mengoreksi SL ke tengah range (6%) kalau SL asli LLM berada DI LUAR rentang 5-8%** (`MIN_SL_PCT = 0.05`, `MAX_SL_PCT = 0.08`, baris 3022-3023):

```python
sl_pct = abs(entry - sl) / entry
if MIN_SL_PCT <= sl_pct <= MAX_SL_PCT:
    return entry_text  # sudah dalam range — TIDAK disentuh
```

SL Spot 6,0% dan SL Futures 7,4% untuk ETH **sama-sama berada di dalam rentang [5%, 8%]**, jadi keduanya lolos tanpa koreksi — angka aslinya murni hasil dua completion LLM independen yang kebetulan memilih persentase berbeda untuk entry yang sama. Tidak ada mekanisme di kode yang menyelaraskan SL% antar section spot/futures. Ini desain yang sudah ada (guardrail hanya meng-clamp ke rentang, bukan menyamakan lintas section), bukan regresi baru.

---

## Rekomendasi arah perbaikan (TIDAK diimplementasikan di task ini)

Sesuai instruksi, berikut arah perbaikan untuk prompt/task terpisah setelah dikonfirmasi:

1. **Duplikasi KEPUTUSAN HARI INI (poin 2)**: tambahkan dedup untuk header `⚡ KEPUTUSAN HARI INI` yang muncul >1 kali di `main_out`, dengan pola yang sama seperti dedup `🟢 SARAN SPOT` ganda yang sudah ada di "Final safety dedup" (baris 4773-4792) — potong dari kemunculan kedua header ini sampai section marker berikutnya, atau lebih sederhana: kalau ditemukan >1 kemunculan, ambil HANYA blok pertama (sampai sebelum kemunculan kedua) sebagai `main_out` final, sebelum proses gabungan dengan spot/futures/disclaimer.
2. **Header SARAN SPOT hilang (poin 3)**: samakan instruksi prompt `_generate_spot_analysis` dengan pola `_generate_futures_analysis` — ulangi header lengkap di dalam contoh kondisi "tidak ada setup" (`[Jika tidak ada setup: "🟢 SARAN SPOT (Swing 1-7 hari)\nTidak ada setup spot yang layak..."]`), dan/atau tambahkan verifikasi programatik di `_generate_spot_analysis`/`_generate_brief_analysis`: kalau `out`/`spot_raw` non-kosong tapi tidak diawali `🟢 SARAN SPOT`, prepend header secara manual sebelum dipakai — jangan mempercayai LLM mentah-mentah untuk kontrak format ini.
3. **Header brief_header gagal kirim (temuan tambahan)**: ubah `_split_message_for_telegram()` untuk menghitung panjang berdasarkan UTF-16 code unit (mis. `len(text.encode('utf-16-le'))//2`) alih-alih `len()` Python biasa, supaya konsisten dengan cara Telegram menghitung limit 4096 — atau turunkan `effective_limit`/`TELEGRAM_MESSAGE_LIMIT` dengan margin aman yang lebih besar untuk mengakomodasi kepadatan emoji di section header ini.
4. **Risiko residual signal_tracking (poin 4)**: pertimbangkan guard idempoten di `_parse_and_record_signals` (mis. dedup berdasarkan `(coin, setup, entry, sl, tp)` dalam satu pemanggilan) supaya kalau bug duplikasi di poin 2 kambuh saat market sedang punya setup valid, tidak ada record `source="llm"` yang tertulis dobel ke `signal_tracking`.

Tidak ada kode yang diubah dalam audit ini — semua di atas murni untuk perencanaan fix berikutnya.
