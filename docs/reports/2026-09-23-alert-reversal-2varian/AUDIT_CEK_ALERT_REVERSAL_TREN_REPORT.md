# Audit Read-Only — Alert Konfirmasi Pembalikan Arah Tren

Tanggal audit: 23 September 2026  
Ruang lingkup: `engine/` dan `interfaces/`, terutama scheduler Telegram.  
Mutasi: tidak ada perubahan kode/konfigurasi. File ini adalah satu-satunya artefak audit.

## Jawaban singkat

**BELUM ADA alert aktif yang mengonfirmasi pembalikan arah tren teknikal per-coin.** Tidak ada job yang menyimpan state tren/alignment coin sebelumnya lalu membandingkannya dengan snapshot sekarang untuk mendeteksi, misalnya, `BULLISH -> BEARISH` atau `BEARISH -> BULLISH`.

Yang ada adalah (a) alert kondisi/sinyal sesaat yang *dapat mengisyaratkan* potensi reversal, (b) breakout, dan (c) alert perubahan **konteks makro global**. Ketiganya bukan konfirmasi perubahan arah tren per-coin. Fondasi teknikal terdekat adalah `multi_timeframe_analyzer` dan field snapshot `trend`, `trend_4h`, `trend_1d`, serta `trend_alignment`; semuanya saat ini dipakai sebagai snapshot, bukan seri state yang dilacak antar-run.

## Kriteria audit

Sebuah alert dihitung sebagai “konfirmasi pembalikan tren” hanya bila ia memiliki seluruh unsur berikut:

1. menilai arah teknikal coin saat ini dan arah sebelumnya (atau crossover/pola yang secara eksplisit membuktikan perubahan arah);
2. memicu ketika terjadi transisi arah, bukan hanya saat sebuah nilai tunggal berada di ambang;
3. mengirim notifikasi per-coin atas transisi tersebut.

Alert yang menyebut kata “potensi reversal”, oversold, dekat support/resistance, breakout, atau status market global tidak memenuhi definisi tersebut tanpa unsur transisi/state di atas.

## Pendaftaran scheduler yang diperiksa

Seluruh pendaftaran aktif berada di `interfaces/telegram_bot.py:7984-8135`. Tidak ada job bernama `reversal`, `trend_flip`, `trend_change`, atau ekuivalennya. Job aktifnya adalah snapshot, near level, RSI ekstrem, big move, watchdog, berita, brief harian, prefetch brief, market-context, breakout, volume, funding, digest, CFRA, makro, whale, signal tracker, dan kalender.

| Job | Interval | Kesimpulan terhadap reversal tren per-coin |
|---|---:|---|
| `snapshot_job` | 60 dtk | Memperbarui snapshot dan menjalankan auto-signal/BTC smart alert. **Bukan** tracker perubahan tren. |
| `near_support_checker`, `near_resistance_checker` | 5 mnt | Kedekatan harga terhadap level. **Bukan** reversal. |
| `rsi_extreme_checker` | 5 mnt | Ambang RSI `<30`/`>75`. **Bukan** reversal terkonfirmasi. |
| `big_move_checker` | 5 mnt | Perubahan harga 15m/30m/1j di atas ambang. **Bukan** reversal. |
| `watchdog_job` | 2 mnt | Kesehatan sistem. Tidak terkait tren. |
| `market_context_alert_job` | 15 mnt | Perubahan status skor market global; hanya menampilkan coin yang *saat ini* aligned. **Bukan** perubahan tren coin. |
| `breakout_check_job` | 5 mnt | Harga menembus S/R. **Bukan** perubahan arah tren. |
| `volume_spike_job` | 5 mnt | Volume 24j vs rata-rata 14 hari. **Bukan** reversal. |
| `funding_alert_job`, `cfra_alert_job` | 5/30 mnt | Funding rate/squeeze risk. **Bukan** reversal. |
| `whale_alert_job` | 10 mnt | Tekanan whale/akumulasi. **Bukan** reversal. |
| `signal_check_job` | 10 mnt | Menutup dan memberi hasil WIN/LOSS sinyal yang sudah terbuka. **Bukan** detektor tren. |
| `breaking_news_job`, `macro_check_job`, kalender, brief, prefetch, digest, weekly summary | beragam | Berita, makro, penjadwalan/formatting, atau ringkasan; tidak mengevaluasi transisi tren coin. |

`calendar_reminder_job` juga ada tetapi pendaftarannya dikomentari (`interfaces/telegram_bot.py:8137-8142`), sehingga tidak aktif dan juga tidak berhubungan dengan tren.

## Pemeriksaan fungsi yang disebutkan

### `breakout_check_job`

`interfaces/telegram_bot.py:6065-6083` hanya menjalankan detector lalu memasukkan hasilnya ke antrean alert:

```python
breakouts = await run_breakout_check()
for b in breakouts:
    ngov.queue_alert("breakout", "BREAKOUT", f"{coin} {direction}", msg)
```

Predikat sebenarnya ada di `engine/market/breakout_detector.py:164-206`:

```python
candidates_up = [r for r in resistances if price > r * (1 + MARGIN_BREAKOUT)]
candidates_down = [s for s in supports if price < s * (1 - MARGIN_BREAKOUT)]
```

Ia mendeteksi **penembusan resistance (UP) atau support (DOWN)** dengan margin 0,5%, cooldown, dan dedup level. Ini dapat menjadi bukti price-action tambahan dalam desain future reversal, tetapi **mendeteksi breakout/breakdown level, BUKAN pembalikan tren**: tidak ada pembacaan arah tren lama dan baru.

### `signal_check_job`

`interfaces/telegram_bot.py:7264-7285`:

```python
closed = check_open_signals()
for item in closed:
    if item.get("status") not in {"WIN", "LOSS"}:
        continue
    await safe_dispatch(_format_signal_closed_alert(item), ...)
```

Ini memantau lifecycle sinyal trading OPEN agar diberi status WIN/LOSS/EXPIRED. **Ini mendeteksi hasil/penutupan sinyal, BUKAN pembalikan tren.**

### `near_support_checker` dan `near_resistance_checker`

Keduanya adalah wrapper ke `_near_level_push_checker` (`interfaces/telegram_bot.py:6798-6861`). Kandidatnya sudah dihitung oleh `get_coins_near_levels()` dan difilter berdasarkan sisi level:

```python
levels = [row for row in get_coins_near_levels() if row["side"] == side]
```

Pesan support berbunyi “Potensi bounce — pantau konfirmasi bullish”; pesan resistance berbunyi “Potensi reversal atau breakout”. Job bahkan default-nya disuppress bila `NEAR_LEVEL_PUSH_ENABLED` false. **Ini mendeteksi harga dekat support/resistance, BUKAN reversal**; teks “potensi” secara eksplisit meminta konfirmasi lanjutan dan tidak ada state tren sebelumnya.

### `rsi_extreme_checker`

`interfaces/telegram_bot.py:6863-6922` memakai nilai RSI snapshot tunggal:

```python
if rsi < 30:
    ... "Potensi reversal bullish — pantau konfirmasi"
elif rsi > 75:
    ... "Pertimbangkan ambil profit atau wait for pullback"
```

**Ini mendeteksi RSI oversold/overbought, BUKAN pembalikan tren.** Tidak ada RSI slope, crossing ambang dari nilai sebelumnya, persilangan MA, maupun perubahan `trend` dari snapshot sebelumnya. Kalimat alert sendiri menggolongkannya sebagai *potensi* yang perlu dikonfirmasi.

### `watchdog_job`

`interfaces/telegram_bot.py:7843-7858`:

```python
alerts = check_system_health()
if alerts:
    await process_signal("watchdog_health", {"source": "watchdog", "type": "health"}, message, ...)
```

**Ini mendeteksi kesehatan layanan/data, BUKAN tren ataupun reversal.**

### `big_move_checker` (pembanding yang memang sudah ada)

`interfaces/telegram_bot.py:6925-6995` berulang atas `BIG_MOVE_TIMEFRAMES` dan mengirim ketika persentase perubahan memenuhi ambang (`abs(pct) >= BIG_MOVE_THRESHOLD_PCT`, dengan fallback snapshot 1 jam). **Ini mendeteksi besar dan arah pergerakan harga dalam jendela 15m/30m/1j, BUKAN perubahan arah tren teknikal.**

### `market_context_alert_job` (pembanding yang memang sudah ada)

Ini satu-satunya job yang benar-benar menyimpan state “sebelumnya”, tetapi state itu adalah status global tiga-kelas dari skor market:

```python
current_status = map_label_to_alert_status(result.get("label", "Neutral"))
previous_status = ngov.get_value("market_context_alert", "status")
if previous_status == current_status:
    return
...
ngov.set_value("market_context_alert", "status", current_status)
```

(`interfaces/telegram_bot.py:5545-5588`.) Pada status Bullish/Bearish, ia menjalankan `generate_radar_pro()` lalu hanya mengambil coin yang **saat ini** memiliki `STRONG_BULLISH`/`STRONG_BEARISH` melalui `_coins_aligned_with_market_status` (`5507-5518`). **Ini mendeteksi perubahan konteks/skor makro global, BUKAN `alignment` atau `trend` suatu coin yang berubah dari run sebelumnya.**

## Job/alert lain yang secara nama atau logika dapat tampak relevan

### Auto-signal dan BTC smart alert dari `snapshot_job`

`snapshot_job` memperbarui snapshot per menit, memanggil scanner peluang/sinyal, lalu memanggil `analyze_btc_signal(snapshot)`. Ia otomatis mengirim alert BTC hanya untuk `STRONG BUY` atau `CRASH WARNING` dan confidence minimal 75 (`interfaces/telegram_bot.py:7692-7840`):

```python
if should_alert_btc(signal) and confidence >= 75:
    if should_send_alert("BTC", signal):
        await process_signal(f"BTC|{signal}", btc_sig, message, ...)
```

Ada base label internal `REVERSAL` dalam `engine/alerts/btc_smart_alert.py:99-114`:

```python
reversal_signal = (
    rsi is not None and rsi <= 40
    and zone == "near_support"
    and trend != "BEARISH"
)
...
elif reversal_signal:
    base_signal = "REVERSAL"
```

Ini adalah sinyal kandidat bullish **BTC saja**, bukan arah balik yang dikonfirmasi. Alasannya:

- tidak pernah membandingkan `trend` sekarang dengan trend BTC sebelumnya;
- secara eksplisit menolak `trend == "BEARISH"`, jadi bukan konfirmasi transisi `BEARISH -> BULLISH`;
- inputnya kondisi snapshot: RSI rendah, zona dekat support, dan trend tidak bearish;
- output publik akhirnya hanya `STRONG BUY`/`BUY`/`WEAK BUY`/`WAIT` (label base `REVERSAL` tidak menjadi tipe alert Telegram tersendiri); dan auto-alert hanya mengirim `STRONG BUY` atau `CRASH WARNING`.

Modul ini memang punya price action/micro-structure aktif: `detect_market_structure` mengklasifikasikan lima candle terakhir sebagai `bullish_structure` bila higher-high **dan** higher-low berturut-turut, atau `bearish_structure` bila lower-high **dan** lower-low (`engine/alerts/btc_smart_alert.py:527-555`). Ini adalah fondasi konfirmasi yang lebih dekat daripada checker lain, tetapi tetap snapshot pola candle sekarang, hanya BTC, dan bukan transisi tren tersimpan antar-siklus.

### `whale_alert_job` dan detector akumulasi

Job ini mengirim ketika tekanan whale sekarang BUYING/SELLING atau `detect_whale_accumulation` true (`interfaces/telegram_bot.py:6531-6580`). Detector akumulasi berbasis:

```python
whale_signal = whale_ok and trend == "SIDEWAYS" and 45 <= rsi <= 60
```

(`engine/detectors/whale_accumulation_detector.py:34-55`.) Ini menunjukkan fase akumulasi potensial/pra-pump, **BUKAN reversal tren**; tidak ada arah sebelumnya, crossover, atau konfirmasi perubahan struktur.

### `volume_spike_job`, funding/CFRA, dan detector risiko

- Volume spike: `current_volume > avg_volume * 4.0` (`engine/market/volume_spike_detector.py:122-155`). Volume dapat mengonfirmasi reversal bila dipadukan rule lain, tetapi implementasi saat ini hanya mengirim anomali volume.
- Funding/CFRA: funding rate ekstrem `>|0.1%|`, plus CFRA yang dekat funding window. Itu sinyal crowding/squeeze risk, bukan arah tren yang berbalik.
- `crash_detector`, `liquidation_detector`, dan `altseason_detector` (`engine/detectors/`) menggabungkan **kondisi snapshot** trend/RSI/risk/likuidasi. Tidak satu pun menyimpan prior trend. Contohnya short-squeeze memerlukan `trend == "BULLISH" and rsi >= 65`, bukan transisi bearish ke bullish.
- `market_radar_pro` memiliki “BTC Bottom Detector” pada `RSI < 30 and fear <= 20`, dengan teks “Potensi reversal mulai terbentuk” (`engine/market/market_radar_pro.py:34-45`). Ini radar/report kondisi oversold, bukan scheduler alert reversal terkonfirmasi dan bukan pelacakan state tren.

## Fondasi analisis tren yang sudah tersedia

### Multi-timeframe analyzer

`engine/market/multi_timeframe_analyzer.py:18-77` adalah fondasi paling langsung:

```python
# 4H: price > MA10 > MA30 => BULLISH; kebalikannya => BEARISH
trend_4h = _trend_from_mas(price_4h, ma10, ma30)

# 1D: price > MA20 > MA50 => BULLISH; kebalikannya => BEARISH
trend_1d = _trend_from_mas(price_1d, ma20, ma50)
```

Lalu ia membentuk `alignment`: `STRONG_BULLISH` saat 4H dan 1D bullish, `STRONG_BEARISH` saat keduanya bearish, `PARTIAL`/`MIXED` pada kombinasi lain, dan `UNKNOWN` bila data kurang.

Pemanggil produksi yang ditemukan:

| Lokasi | Cara pakai | Tracking perubahan? |
|---|---|---|
| `engine/market/market_analyzer.py:357-481` | Hitung setiap analisis coin dan masukkan `trend_4h`, `trend_1d`, `trend_alignment`, `ma20`, `ma50`, `ma200` ke hasil/snapshot. | Tidak. |
| `engine/market/features.py:98-174` | Hitung feature contract yang sama untuk runtime/backtester. | Tidak. |
| `engine/market/market_radar_pro_analyzer.py:67-140` | Baca `trend_alignment` snapshot untuk data/label radar. | Tidak. |
| `interfaces/telegram_bot.py:1284-1638`, `5507-5518` | Tampilkan di informasi/radar atau filter coin yang searah dengan status market konteks. | Tidak. |
| `engine/brain/*`, `engine/explain/*` | Filter/ranking/penjelasan kualitas setup menggunakan alignment saat ini. | Tidak. |

Pencarian seluruh pemakaian persistent state (`ngov.get_value`/`set_value`) menemukan state untuk market-context global, cooldown, dedup, breakout level, statistik, dan drawdown; **tidak ada namespace/state `trend`, `trend_alignment`, `alignment` per coin, atau perbandingan old-vs-new**. Dengan demikian `multi_timeframe_analyzer` dipakai sebagai snapshot sesaat, bukan detector edge/transisi.

### Indikator/pola lain

Implementasi aktif yang relevan tetapi belum menjadi detector reversal umum adalah:

- MA: `market_analyzer`/`features` menghitung MA20/50/200 dan mengklasifikasikan trend berdasarkan posisi harga `price > MA50 > MA200` atau kebalikannya. Ini **bukan MA-crossover detector**: ia tidak membandingkan MA short/long candle sebelumnya vs sekarang.
- RSI: `calculate_rsi` dan `calculate_rsi_series` tersedia di `engine/market/features.py:13-57`. `calculate_rsi_series` menghasilkan seri historis untuk feature/backtest, tetapi tidak ditemukan pemanggil yang mendeteksi slope, divergence, atau crossing RSI sebagai alert Telegram reversal.
- Price action: `btc_smart_alert.detect_market_structure` (HH/HL atau LH/LL lima candle terakhir) dan breakout S/R tersedia, tetapi tidak ada rule yang mengubah observasi itu menjadi `trend lama -> trend baru` per coin.
- ATR tersedia (`average_true_range`) dan dipakai shadow E3 untuk level/risk; shadow E3 secara eksplisit research-only dan tidak mendispatch ke gateway produksi. Tidak ada detector reversal di `engine/shadow/`.

Tidak ditemukan implementasi umum untuk EMA cross, MA cross event, RSI slope/divergence, candlestick reversal pattern (engulfing/hammer), atau state machine perubahan trend yang aktif sebagai alert per-coin.

## Hasil grep kata kunci langsung

Perintah yang digunakan (case-insensitive):

```text
rg -n -i -C 6 "reversal|pembalikan|trend[_ -]?(change|flip)" engine interfaces --glob '*.py'
```

Tidak ada match `pembalikan`, `trend_change`, atau `trend_flip`. Semua match `reversal` berikut telah diperiksa:

| Lokasi | Konteks | Logika aktif? | Putusan |
|---|---|---|---|
| `interfaces/telegram_bot.py:4660` | Instruksi prompt LLM: tunggu konfirmasi reversal saat extreme fear. | Tidak; teks prompt. | Bukan detector. |
| `interfaces/telegram_bot.py:6839` | Copy alert dekat resistance: “Potensi reversal atau breakout”. | Hanya pesan; predicate-nya near resistance. | Bukan detector. |
| `interfaces/telegram_bot.py:6904` | Copy RSI oversold: “Potensi reversal bullish”. | Hanya pesan; predicate-nya RSI `<30`. | Bukan detector. |
| `engine/market/market_radar_pro.py:44` | Copy BTC bottom detector. | Predicate aktif RSI `<30` dan fear `<=20`. | Potensi bottom, bukan reversal terkonfirmasi. |
| `engine/market/market_context_engine.py:33` | Rekomendasi label skor Bearish untuk “tunggu konfirmasi reversal”. | Hanya teks rekomendasi. | Bukan detector. |
| `engine/reasoning/why_reason_engine.py:183` | Narasi downtrend: tunggu reversal atau breakdown. | Hanya narasi alasan. | Bukan detector. |
| `engine/alerts/btc_smart_alert.py:99-113` | Predikat dan base label internal `REVERSAL`. | Ya, aktif sebagai kandidat snapshot BTC. | Bukan konfirmasi perubahan tren; alasan rinci di atas. |
| `engine/alerts/btc_smart_alert.py:587` | Komentar sideways “early reversal”. | Tidak; komentar. | Bukan detector. |

## Kesimpulan dan fondasi bila fitur nanti dibangun

**Status akhir: BELUM ADA SAMA SEKALI untuk mekanisme yang diminta**—yakni alert Telegram per-coin yang mengonfirmasi arah tren berubah dari uptrend ke downtrend atau sebaliknya.

Fondasi yang sudah siap dipakai tanpa menambah indikator dasar adalah output per-coin snapshot berikut dari `market_analyzer`: `trend`, `trend_4h`, `trend_1d`, `trend_alignment`, `ma20`, `ma50`, `ma200`, RSI, support/resistance, dan timestamp. `multi_timeframe_analyzer` adalah basis paling tepat untuk state-change detector karena memberikan arah 4H dan 1D eksplisit.

Namun masih diperlukan komponen baru untuk:

1. persist state per coin (minimal trend 4H/1D/alignment dan waktu candle close);
2. membandingkan state valid sebelumnya dengan state baru, serta mendefinisikan transisi yang dianggap reversal;
3. menerapkan konfirmasi (misalnya close candle, kedua timeframe selaras, MA cross yang benar-benar terjadi, atau breakout struktur dengan volume);
4. dedup/cooldown edge-triggered agar satu perubahan tidak berulang tiap snapshot; dan
5. jalur dispatch alert tersendiri.

Ketiadaan poin 1–4 adalah pembeda faktual antara fondasi/sinyal potensial yang ada dan alert konfirmasi reversal yang ditanyakan.
