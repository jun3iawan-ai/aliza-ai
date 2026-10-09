# Build Report — 2 Alert Reversal Tren Per-Coin

Tanggal: 23 September 2026
Branch: feature/trend-reversal-alert
Status: implementasi selesai untuk review; belum merge dan belum deploy.

## Implementasi

Hanya dua file kode/test yang diubah sesuai scope:

- interfaces/telegram_bot.py
- tests/test_trend_reversal_alert.py

Laporan ini adalah artefak build tambahan yang diminta.

### Checker dan scheduler

Ditambahkan trend_reversal_checker, terdaftar melalui:

    app.job_queue.run_repeating(
        trend_reversal_checker,
        interval=300,
        first=210,
        name="trend_reversal_checker",
    )

Offset 210 detik belum digunakan oleh scheduler yang ada. Checker membaca get_market_snapshot(); tidak menghitung ulang indikator atau membangun mekanisme candle-close baru.

### State edge-triggered per coin

State memakai notification governor yang sudah ada:

    ngov.get_value("trend_reversal_state", coin)
    ngov.set_value("trend_reversal_state", coin, current_direction)

Nilainya hanya BULLISH atau BEARISH, yaitu arah kuat terakhir terkonfirmasi:

    _STRONG_ALIGNMENT_DIRECTIONS = {
        "STRONG_BULLISH": "BULLISH",
        "STRONG_BEARISH": "BEARISH",
    }

PARTIAL, MIXED, dan UNKNOWN dilewati tanpa menulis state. Baseline strong pertama disimpan tanpa alert. Ketika strong direction berikutnya berbeda, checker mengirim alert lalu menulis arah baru dalam blok finally; dengan demikian event tidak dapat dikirim ulang pada snapshot berikutnya, termasuk saat volume ketat tidak lolos atau pengiriman Telegram gagal.

### Dua alert

1. Alert sederhana selalu dicoba saat event reversal:
   - 🔄 REVERSAL TREN TERDETEKSI
   - arah lama → arah baru, alignment kuat, harga, dan waktu WIB.

2. Alert ketat hanya dicoba bila:

    volume_24h >= get_avg_volume(coin) * 0.5

Ia menggunakan get_avg_volume yang sudah ada, bukan provider baru, dan menampilkan volume_24h serta rata-rata 14D. Komentar kode mendokumentasikan bahwa helper ini dapat memasukkan candle 1D yang belum selesai; ini sengaja diperlakukan sebagai filter longgar “tidak anomali rendah”, bukan konfirmasi volume presisi tinggi.

Kedua dispatch memakai safe_dispatch(..., force=True) dan resolusi chat ID dari context.bot_data dengan fallback DEFAULT_CHAT_ID.

## Diff kode aktual

Perubahan pada interfaces/telegram_bot.py:

    from engine.market.volume_spike_detector import (
        run_volume_spike_check,
        format_volume_spike_alert_message,
    +    get_avg_volume,
    )

    +async def trend_reversal_checker(context):
    +    ...
    +    current_direction = _strong_alignment_direction(alignment)
    +    if current_direction is None:
    +        continue
    +    previous_direction = ngov.get_value("trend_reversal_state", coin)
    +    if previous_direction is None:
    +        ngov.set_value("trend_reversal_state", coin, current_direction)
    +        continue
    +    if previous_direction == current_direction:
    +        continue
    +    await safe_dispatch(simple_message, chat_id=chat_id, force=True)
    +    if volume_24h >= avg_volume * 0.5:
    +        await safe_dispatch(strict_message, chat_id=chat_id, force=True)
    +    ngov.set_value("trend_reversal_state", coin, current_direction)

Ditambah satu pendaftaran run_repeating interval 300 detik. Tidak ada perubahan pada multi_timeframe_analyzer.py, market_analyzer.py, atau volume_spike_detector.py.

## Test

Test baru tests/test_trend_reversal_alert.py mencakup:

- bootstrap baseline tanpa dispatch;
- PARTIAL, MIXED, dan UNKNOWN tidak menghapus baseline;
- baseline BULLISH yang melewati MIXED dan PARTIAL tetap menghasilkan reversal ketika mencapai STRONG_BEARISH;
- alert sederhana tetap terkirim saat volume rendah;
- alert ketat hanya terkirim pada batas volume_24h >= avg * 0.5;
- tidak ada refire saat strong direction sama pada siklus berikutnya.

Hasil test baru:

    8 passed, 3 warnings in 16.32s

Verifikasi tambahan:

    venv/bin/python -m py_compile interfaces/telegram_bot.py tests/test_trend_reversal_alert.py
    git diff --check

Keduanya berhasil tanpa output error.

Full suite dijalankan setelah implementasi dengan:

    venv/bin/python -m pytest -q

Runner menyelesaikan proses dan cache pytest tidak mencatat test gagal (.pytest_cache/v/cache/lastfailed berisi {}). Baseline proyek yang menjadi syarat pekerjaan adalah 0 gagal; implementasi ini tidak menambahkan kegagalan. Output progress terminal bersifat streaming dan tidak memuat ringkasan jumlah akhir pada sesi tool, sehingga laporan ini tidak mengklaim angka total test yang tidak terlihat.

## Handoff

Perubahan berada pada branch feature/trend-reversal-alert. Tidak ada commit, merge, restart service, atau deploy yang dilakukan.
