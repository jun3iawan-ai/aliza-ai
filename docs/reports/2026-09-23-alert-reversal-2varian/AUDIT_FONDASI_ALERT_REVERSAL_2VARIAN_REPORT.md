# Audit Read-Only — Fondasi Dua Varian Alert Reversal Tren Per-Coin

Tanggal audit: 23 September 2026  
Ruang lingkup: jalur snapshot/analyzer, klines 4H/1D, volume, persistence, dan pola transition notification.  
Mutasi: tidak ada perubahan kode atau konfigurasi. File laporan ini adalah satu-satunya artefak audit.

## Ringkasan hasil

Fondasi untuk kedua varian **sudah ada sebagian besar**:

- setiap siklus snapshot menjalankan analisis per coin dan menghasilkan `trend_4h`, `trend_1d`, serta `trend_alignment`;
- sumber alignment saat ini secara normal adalah **closed candle only** 4H dan 1D;
- `notification_governor` dapat menyimpan baseline alignment per coin secara persisten dan bounded (21 key);
- pola edge-triggered drawdown breaker adalah preseden langsung untuk “kirim hanya ketika state berubah”.

Batas penting yang perlu diketahui sebelum implementasi:

1. Kline 4H/1D dicache 5/10 menit. Alignment dihitung ulang per snapshot, tetapi input close dapat tetap sama sampai TTL habis; deteksi tidak harus muncul persis saat candle tutup.
2. Snapshot generik tidak menyimpan `close_time` 4H/1D ataupun raw candle. Filter closed-candle memang dilakukan sebelum MA/alignment dihitung, tetapi checker baru yang hanya membaca snapshot tidak bisa mengaudit timestamp close tersebut lagi tanpa memperluas data yang dipass.
3. `volume_24h` tersedia, tetapi itu quote volume rolling 24 jam dari endpoint ticker. Rata-rata volume 14 hari yang ada dapat dipakai ulang, namun saat ini mengambil raw `1d` klines tanpa memfilter candle harian yang masih berjalan; secara praktik dapat berisi 13 closed daily candles + candle hari ini yang parsial.
4. Persyaratan **transisi langsung** `STRONG_BULLISH -> STRONG_BEARISH` (atau kebalikannya) jauh lebih ketat daripada “arah mulai berbalik”: perubahan lazimnya akan melewati `PARTIAL`/`MIXED`, dan status `STRONG_*` sendiri dibatasi oleh close 1D.

## 1. Kapan dan seberapa sering alignment dihitung

### Jalur rutin: snapshot job, bukan hanya command user

Scheduler Telegram mendaftarkan `snapshot_job` setiap 60 detik:

```python
app.job_queue.run_repeating(snapshot_job, interval=60, first=5)
```

`interfaces/telegram_bot.py:7984-7985`.

`snapshot_job` menjalankan updater di executor sebelum membaca snapshot:

```python
loop = asyncio.get_event_loop()
await loop.run_in_executor(None, update_market_snapshot)
snapshot = get_market_snapshot()
```

(`interfaces/telegram_bot.py:7692-7701`.) Jadi jalur ini adalah background rutin; tidak memerlukan command Telegram pengguna.

Di `engine/market/market_snapshot_engine.py:433-514`, `update_market_snapshot()`:

```python
coins = get_tradable_coins_fallback()
...
for symbol in coins:
    data = _fetch_with_radar_retry(symbol, radar_data)
    ...
    collected[symbol] = data
```

`_fetch_with_radar_retry()` memanggil `generate_signal(symbol, radar_data)` (`market_snapshot_engine.py:125-156`), yang hanya meneruskan ke `market_analyzer.market_signal()`:

```python
def generate_signal(symbol, radar_data=None):
    signal = _market_signal(symbol, radar_data)
    if signal is None:
        return None
    return signal
```

(`engine/market_signal.py:9-13`.) Dengan demikian, setiap coin yang berhasil dipoll dianalisis pada setiap snapshot cycle.

Universe normal adalah fixed 21 coin (`CORE_COINS`) di `engine/market/market_universe.py:12-18`. Namun “semua 21” bukan jaminan absolut pada setiap cycle: `get_polling_coins()` dapat mengeluarkan coin melalui `UNIVERSE_EXCLUDE` atau menangguhkan coin yang gagal validasi berulang (`market_universe.py:74-94`); updater juga hanya memasukkan hasil valid ke `collected`.

### Perhitungan di dalam satu analisis coin

`market_signal()` mengambil dua seri kline:

```python
closes_4h = _get_binance_klines(symbol_usdt, "4h", KLINES_LIMIT)
closes_1d = _get_binance_klines(symbol_usdt, "1d", KLINES_LIMIT)
```

(`engine/market/market_analyzer.py:314-315`.)

Setelah memastikan data cukup, ia langsung menghitung MTF:

```python
_closes_4h_mtf = closes_4h if len(closes_4h) >= 30 else []
_closes_1d_mtf = closes_1d if len(closes_1d) >= 50 else []
mtf = analyze_multi_timeframe(_closes_4h_mtf, _closes_1d_mtf)
trend_4h = mtf.get("trend_4h")
trend_1d = mtf.get("trend_1d")
alignment = mtf.get("alignment")
```

(`market_analyzer.py:354-360`.) Nilai akhirnya ditaruh dalam row snapshot:

```python
"trend_4h": trend_4h,
"trend_1d": trend_1d,
"trend_alignment": alignment,
"ma20": ma20, "ma50": ma50, "ma200": ma200,
```

(`market_analyzer.py:473-484`.)

Ada pemanggilan kedua yang ekuivalen melalui `compute_features(closes_4h, closes_1d, ...)` sebelum blok di atas (`market_analyzer.py:336`); `compute_features` juga memanggil `analyze_multi_timeframe` (`engine/market/features.py:129`). Bila feature valid, hasilnya menimpa nilai lokal (`market_analyzer.py:401-408`). Jadi fungsi MTF dieksekusi dua kali per analisis coin saat data cukup; keduanya pure calculation dari daftar close yang sama.

### Apa yang fresh, dan apa yang dicache

MA10/MA30 (4H) dan MA20/MA50 (1D) dalam `multi_timeframe_analyzer` tidak memiliki cache sendiri. Fungsi hanya menghitung rerata slice terakhir:

```python
def _ma(values, period):
    return sum(values[-period:]) / period
```

dan menetapkan arah berdasarkan close terakhir:

```python
# 4H
ma10 = _ma(prices_4h, 10); ma30 = _ma(prices_4h, 30)
trend_4h = _trend_from_mas(price_4h, ma10, ma30)

# 1D
ma20 = _ma(prices_1d, 20); ma50 = _ma(prices_1d, 50)
trend_1d = _trend_from_mas(price_1d, ma20, ma50)
```

(`engine/market/multi_timeframe_analyzer.py:8-56`.) Artinya nilai MA dihitung ulang setiap `market_signal()` dipanggil, tetapi dapat memakai daftar close yang sama.

Daftar close tersebut memiliki cache in-memory di `engine/market/klines_cache.py`:

```python
TTL_SEC = {"4h": 300, "1d": 600}
```

dan `_get_binance_klines()` mengambil cache sebelum request:

```python
cached = get_cached_klines(sym, interval)
if cached:
    return cached
...
closes = _extract_closed_kline_closes(data)
set_cached_klines(sym, interval, closes)
```

(`engine/market/market_analyzer.py:130-173`.) Kesimpulannya:

- `market_signal` dan MA/alignment memang dijalankan setiap snapshot siklus (sekitar 60 detik untuk coin yang dipoll);
- sumber 4H bisa tertunda sampai sekitar 300 detik setelah cache diisi, sumber 1D sampai sekitar 600 detik;
- cache menyimpan **hanya list harga close**, bukan MA maupun close timestamp. Bila cache diisi tepat sebelum boundary candle, close candle baru baru dapat terlihat sesudah TTL, bukan tepat di boundary.

## 2. Bukti candle 4H/1D sudah close penuh

### Implementasi analyzer sudah membuang candle berjalan

`market_analyzer._extract_closed_kline_closes()` adalah jalur yang dipakai `_get_binance_klines()` untuk 4H/1D:

```python
def _extract_closed_kline_closes(data, now_ms=None):
    cutoff_ms = int(now_ms if now_ms is not None else time.time() * 1000)
    closes = []
    for candle in data if isinstance(data, list) else []:
        close_time = int(candle[6])
        close_price = float(candle[4])
        if close_time > cutoff_ms:
            continue
        if close_price > 0:
            closes.append(close_price)
    return closes
```

(`engine/market/market_analyzer.py:112-127`.) Binance kline index `6` dipakai sebagai `close_time`, sehingga candle dengan close time di masa depan—termasuk candle yang masih berjalan—dibuang. Karena `analyze_multi_timeframe` menerima hanya list ini, MA10/30 dan MA20/50 alignment normalnya sudah **closed-candle-only**.

Ada satu perbedaan presisi terhadap pola Big Move yang perlu dicatat. Big Move memilih candle dengan kondisi lebih ketat:

```python
if close_time < now_ms and value > 0:
    close = value
```

(`engine/market/market_snapshot_engine.py:259-275`, identik untuk 15m/30m di `334-354`.) Ia juga menyetel cache refresh ke satu detik setelah boundary:

```python
return float((int(now) // interval_sec + 1) * interval_sec + 1)
```

(`market_snapshot_engine.py:286-289`.) Sebaliknya extractor MTF membuang hanya `close_time > cutoff_ms`, sehingga ia menerima `close_time == cutoff_ms`. Dalam praktik equality millisecond jarang, tetapi untuk definisi “sudah benar-benar berlalu” yang sama persis dengan Big Move, comparator Big Move (`<`) lebih ketat daripada comparator MTF saat ini (`<=` secara efektif).

### Apa yang bisa/tidak bisa dipakai langsung oleh checker baru

Pola raw-kline Big Move bisa digeneralisasi untuk `4h` dan `1d`: request kline, baca `candle[6]`, pilih `close_time < now_ms`, cache sampai satu detik setelah boundary. Fakta yang mendukung reuse ini ada pada helper 1h dan 15m/30m di `market_snapshot_engine.py:223-374`.

Namun checker yang **hanya** membaca existing snapshot tidak menerima `close_time_4h`, `close_time_1d`, atau raw kline. Row yang dikembalikan `market_analyzer` menyimpan alignment/MA/timestamp analisis, tetapi tidak timestamp close kedua candle basis (`market_analyzer.py:471-502`). Jadi:

- validasi closed-only sudah dilakukan hulu sebelum alignment dihitung;
- snapshot freshness (`timestamp`) hanya membuktikan waktu analisis coin, **bukan** waktu candle 4H/1D terakhir close;
- validasi tambahan berbasis timestamp close secara eksplisit tidak dapat dilakukan ulang dari snapshot saat ini saja.

## 3. Data volume untuk syarat “tidak anomali rendah”

### Field yang tersedia di snapshot

Setelah row coin dihitung, snapshot updater memperkaya seluruh `collected` dengan endpoint Binance `/api/v3/ticker/24hr` sekali per cycle:

```python
qv = t.get("quoteVolume")
if qv is not None:
    row["volume_24h"] = float(qv)
```

(`engine/market/market_snapshot_engine.py:170-215` dan pemanggilnya `525-528`.) Dengan demikian `volume_24h` adalah **quote asset volume USDT rolling 24 jam** dari ticker Binance, bukan volume candle 4H/1D yang digunakan alignment. Bila endpoint/ticker pair tidak tersedia, field tidak dipasang.

Tidak ada field volume candle 4H/1D, average volume, maupun close-time 4H/1D dalam generic snapshot result `market_analyzer.py:471-502`. Satu-satunya volume generik yang siap dibaca checker dari snapshot adalah `volume_24h`.

### Rata-rata 14 hari yang sudah ada

`engine/market/volume_spike_detector.py` sudah menyediakan helper yang dapat dipakai sumber data yang sama:

```python
KLINES_LIMIT = 14
QUOTE_VOL_INDEX = 7
...
r = requests.get(..., params={"symbol": sym, "interval": "1d", "limit": 14})
...
qv = _safe_float(candle[QUOTE_VOL_INDEX])
...
avg = sum(vols) / len(vols)
```

(`volume_spike_detector.py:46-47`, `72-103`, `106-126`.) `get_avg_volume(symbol)` menyimpan hasil per symbol selama empat jam:

```python
AVG_VOL_CACHE_TTL_SEC = 4 * 3600
```

(`volume_spike_detector.py:40-44`.) Detector aktif menggunakannya untuk spike, dengan predicate:

```python
if cv <= avg * SPIKE_MULTIPLIER:
    return None
# SPIKE_MULTIPLIER = 4.0
```

(`volume_spike_detector.py:33-38`, `129-155`.) Helper `get_avg_volume` sendiri tidak dibatasi ke top-5; pembatasan top-5 (`WATCHLIST`) terjadi hanya di `run_volume_spike_check` (`201-229`). Jadi secara API kode, helper dapat dipanggil untuk coin lain yang punya pair Binance.

### Kualifikasi penting untuk definisi longgar `>= avg * 0.5`

Menggunakan `volume_24h >= get_avg_volume(coin) * 0.5` akan konsisten dalam satuan (keduanya quote volume USDT) dan tidak memerlukan provider baru. Tetapi ada dua perbedaan fakta:

1. `volume_24h` adalah rolling 24 jam; `avg` adalah average quote volume daily kline. Jendelanya tumpang tindih tetapi bukan jendela identik.
2. `_fetch_daily_quote_volumes()` tidak membaca `candle[6]` dan tidak memfilter candle belum close. Karena request `limit=14` lazimnya menyertakan candle `1d` yang berjalan, angka yang diberi nama “rata-rata 14 candle daily” dapat memasukkan volume hari ini yang parsial. Cache empat jam memperpanjang nilai tersebut sampai TTL.

Ini bukan blocker untuk syarat “bukan volume sangat rendah”, tetapi perlu dibedakan dari syarat volume **closed-candle-only** yang ketat. Tidak ada helper existing untuk rata-rata 14 candle daily yang eksplisit closed-only.

## 4. Persistensi state alignment per coin

`notification_governor` sudah merupakan persistence key/value generik ke satu file JSON:

```python
STATE_FILE = os.path.join(_ROOT, "data", "alert_cooldown_state.json")
...
def get_value(namespace, key, default=None):
    return _load_state().get(namespace, {}).get(key, default)

def set_value(namespace, key, value):
    state = _load_state()
    state.setdefault(namespace, {})[key] = value
    _save_state()
```

(`engine/alerts/notification_governor.py:36-37`, `104-111`.) Dengan bentuk ini, satu namespace tetap dan key coin, misalnya konseptual `get_value("trend_alignment_state", coin)`, **didukung langsung**. Alternatif namespace per coin juga secara teknis mungkin, tetapi struktur current API memang namespaced dict-of-dicts, sehingga satu namespace + hingga 21 key lebih selaras dengan pola storage.

Preseden state transition global adalah:

```python
was_active = bool(ngov.get_value("drawdown_breaker", "active", False))
if active_now == was_active:
    return
ngov.set_value("drawdown_breaker", "active", active_now)
```

(`interfaces/telegram_bot.py:7558-7581`.) `market_context_alert_job` memakai pola sama untuk satu key status global (`interfaces/telegram_bot.py:5562-5588`). Tidak ada batas API yang membatasi key hanya satu; cooldown checker yang sudah ada juga menyimpan banyak key coin/kondisi.

Pertimbangan implementasi yang terbukti dari kode:

- **Ukuran:** 21 alignment string (atau dict kecil berisi alignment/timestamp) merupakan keyspace tetap dan sangat kecil. Dokumentasi governor sendiri menyebut keyspace fixed seperti coins sebagai kasus yang tidak memerlukan pruning (`notification_governor.py:142-166`).
- **Tahan restart:** setiap `set_value` menulis JSON dengan file temporary lalu `os.replace`, sehingga state bertahan restart dan write tidak meninggalkan file JSON parsial (`69-78`).
- **Granularitas write:** `set_value` menyimpan seluruh JSON setiap call. Jika baseline 21 coin diperbarui satu per satu dalam satu cycle, akan terjadi sampai 21 atomic rewrite; tidak ada API batch pada governor.
- **Concurrency:** governor memiliki cache modul dan tidak memakai lock untuk `get_value`/`set_value`. Snapshot job ini sendiri satu scheduler path, tetapi kode tidak memberikan sinkronisasi multi-writer eksplisit. Ini bukan masalah yang terlihat untuk pola sederhana single-job, namun fakta relevan bila beberapa job nantinya menulis namespace sama.

## 5. Cooldown/dedup: transition versus durasi tetap

### Preseden paling dekat: edge-triggered transition

`_notify_drawdown_breaker_transition()` dijalankan pada setiap snapshot cycle tetapi hanya dispatch ketika boolean state berubah. Tidak ada cooldown durasi:

```python
if active_now == was_active:
    return
ngov.set_value("drawdown_breaker", "active", active_now)
await safe_dispatch(msg, chat_id=chat_id, force=True)
```

(`interfaces/telegram_bot.py:7558-7587`.) Ini cocok secara bentuk dengan event `previous_alignment != current_alignment`; baik state lama maupun baru dapat dicatat/ditampilkan, dan re-run dengan alignment sama tidak mengirim ulang.

Sebaliknya, `BIG_MOVE` adalah condition/threshold yang dapat terus benar pada beberapa polling cycle. Ia memakai timestamp cooldown persisted per coin dan timeframe (`interfaces/telegram_bot.py:6958-6987`; `notification_governor.py:121-140`). Itu masalah yang berbeda dari event state transition.

### Seberapa cepat alignment dapat berubah menurut rumus sekarang

`multi_timeframe_analyzer` tidak memakai live ticker untuk MTF; ia menetapkan `price_4h = prices_4h[-1]` dan `price_1d = prices_1d[-1]`, keduanya close terakhir dalam list closed-only (`engine/market/multi_timeframe_analyzer.py:40-56`). Maka alignment tidak berganti setiap snapshot 60 detik hanya karena harga live berfluktuasi.

Secara struktur:

- `trend_4h` dapat berubah setelah close 4H baru tersedia (ditambah latency cache maksimum sekitar lima menit); pada daily trend tetap, strong alignment dapat berubah `STRONG_* -> MIXED/PARTIAL` lalu kembali pada close 4H berikutnya di pasar choppy.
- `trend_1d` hanya dapat berubah setelah close 1D baru tersedia (ditambah cache sampai sekitar 10 menit). Karena `STRONG_BULLISH` dan `STRONG_BEARISH` masing-masing mensyaratkan **dua timeframe searah**, transisi dari satu `STRONG_*` ke strong berlawanan tidak dapat terjadi lebih cepat dari perubahan data 1D. Dalam operasi normal, paling cepat sekitar satu daily close, bukan tiap 60 detik.
- Rantai label memungkinkan `PARTIAL` atau `MIXED` ketika satu timeframe berubah tetapi yang lain belum (`multi_timeframe_analyzer.py:59-72`). Karena itu transisi trend yang sesungguhnya lebih mungkin teramati sebagai `STRONG_BULLISH -> MIXED/PARTIAL -> STRONG_BEARISH` daripada satu langkah langsung.

Implikasi faktual terhadap spesifikasi alert sederhana/ketat adalah bahwa sebuah checker yang mengobservasi setiap beberapa menit akan hampir selalu merekam state intermediate. Predicate literal “previous harus `STRONG_BULLISH` dan current harus `STRONG_BEARISH`” dapat tidak memicu meskipun arah akhirnya benar-benar berbalik, karena previous yang tersimpan sudah `MIXED`/`PARTIAL`. Ini bukan argumen untuk mengubah spesifikasi, melainkan konsekuensi dari rumus alignment dan cadence snapshot yang perlu disadari.

Untuk spam, model edge-trigger sudah dengan sendirinya menahan duplikasi selama current alignment tidak berubah. Tetapi tidak ada hysteresis atau minimum-duration dalam `multi_timeframe_analyzer`; label 4H non-strong dapat bolak-balik antar close candle pada pasar choppy. Jika kelak event yang dipantau diperluas dari direct strong-to-strong menjadi setiap perubahan alignment, pola transition saja dapat mengirim pada setiap flip state tersebut; cooldown tambahan atau rule stabilitas menjadi pertimbangan terpisah. Untuk direct `STRONG_BULLISH <-> STRONG_BEARISH`, frekuensinya secara struktural dibatasi oleh candle 1D seperti dijelaskan di atas.

## Jawaban langsung untuk dua varian

| Kebutuhan | Status fondasi saat ini | Bukti/batas |
|---|---|---|
| Sederhana: compare alignment kuat lawan sebelumnya per coin | **Ada** | Snapshot rutin menulis `trend_alignment`; governor mendukung 21 baseline persistent key. Belum ada job pembandingnya. |
| Ketat, syarat candle 4H/1D sudah close | **Sebagian besar ada** | Analyzer sudah closed-only, tetapi snapshot tidak membawa close timestamp; comparator MTF kurang ketat satu edge case dibanding Big Move (`<= now` versus `< now`). |
| Ketat, volume tidak anomali rendah | **Ada data/helper, dengan kualifikasi** | `volume_24h` dan `get_avg_volume()` kompatibel satuan; baseline volume harian saat ini dapat memasukkan candle berjalan. |
| Dedup/event transition | **Ada preseden** | Drawdown breaker menyimpan prior state lalu send sekali pada perubahan; tidak ada cooldown durasi. |

Tidak ada kode yang diubah oleh audit ini.
