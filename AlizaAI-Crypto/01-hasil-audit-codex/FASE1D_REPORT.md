# Laporan Fase 1d — Observability dan Data-Coverage Gate

Tanggal: 21 Juli 2026  
Branch kerja: `fix/fase1d-observability-universe`  
Branch hasil merge: `main`  
Hash merge: `c350a21c` (HEAD setelah follow-up: `6831ad0d`)  
Tidak ada perubahan pada `.env`, parameter strategi, atau threshold sinyal.

## Ringkasan hasil

Fase 1d selesai dan sudah di-merge ke `main`. Commit implementasi:

- `86dfcb0b` — `feat(fase1d): add data coverage observability`
- `51681225` — `feat(fase1d): add universe coverage gate`
- `c350a21c` — merge Fase 1d ke `main`
- `6831ad0d` — memastikan snapshot invalid selalu menulis log coverage terstruktur

Full test suite:

```
venv/bin/python -m pytest -q
118 passed, 3 warnings, 74 subtests passed in 15.71s
```

Warning tersisa adalah DeprecationWarning dari dependency native (SwigPy), bukan kegagalan test.

## Perubahan per file/fungsi

### `engine/market/market_analyzer.py`

- Menambahkan `_record_data_coverage()` dan `get_data_coverage()`.
- `market_signal()` melabeli sumber harga `binance`, `coingecko`, atau `none`.
- Data invalid mencatat log terstruktur: `data_coverage coin=X klines_4h=N klines_1d=M price_source=... reason=...`.
- Alignment `UNKNOWN` menjelaskan timeframe kurang (`insufficient_4h`, `insufficient_1d`, atau keduanya).
- Hasil sinyal menyertakan field `data_coverage`.
- Kline tetap berasal dari candle yang sudah close; ticker tidak ditambahkan ke seri indikator.

### `engine/market/market_snapshot_engine.py`

- Snapshot global dan `get_market_snapshot()` menyertakan `data_coverage`.
- Setiap coin menyimpan panjang kline, sumber harga, alasan valid/invalid, dan flag `valid`.
- Status universe disimpan pada key `_universe`.
- Validasi akhir setelah retry dicatat sekali per coin melalui `record_coin_validation()`.

### `engine/market/market_universe.py`

- Gate baru: `record_coin_validation()`, `get_polling_coins()`, `get_universe_status()`, dan `reset_coverage_gate()`.
- Default: 10 kegagalan berturut-turut men-suspend coin selama 6 jam.
- Override: `COIN_FAIL_THRESHOLD` dan `COIN_SUSPEND_HOURS`.
- Exclude statis: `UNIVERSE_EXCLUDE` (comma-separated, default kosong).
- Counter reset saat sukses; setelah cooldown coin dipoll lagi. State dilindungi lock.

### `tests/test_fase1d.py`

Menguji suspend/cooldown, reset counter, exclude env, serta log coverage ketika data 1d kurang.

## Analisis coverage empat coin

Pemeriksaan langsung Binance `/api/v3/exchangeInfo` menunjukkan semua pair berikut tidak tersedia; kline manual 4h/1d mengembalikan HTTP 400 dan 0 candle.

| Coin | CoinGecko | Rekomendasi |
|---|---|---|
| BONE | ID `bone-shibaswap`; simple price berhasil pada pemeriksaan awal | Jangan hapus dari CORE. Exclude sementara dari pipeline Binance atau pertahankan hanya setelah sumber historis CoinGecko tervalidasi. |
| FARTCOIN | ID `fartcoin`; pemeriksaan langsung berikutnya HTTP 429; runtime menunjukkan fallback sesekali | Exclude melalui env sampai fallback historis dan rate-limit handling tervalidasi. |
| HYPE | ID `hyperliquid`; pemeriksaan langsung HTTP 429 | Exclude melalui env atau tambahkan sumber historis sehat. |
| ZEREBRO | ID `zerebro`; pemeriksaan langsung HTTP 429; runtime tidak konsisten | Exclude sementara sampai sumber historis tervalidasi. |

Kecukupan fallback CoinGecko untuk tiga coin terakhir **TIDAK PASTI** karena HTTP 429. Tidak ada coin yang dihapus dari `CORE_COINS`; keputusan permanen tetap pada user.

## Verifikasi operasional

- Merge tanpa konflik.
- Codex tidak me-restart service. User perlu menjalankan:
  `sudo systemctl restart aliza-telegram`
- Jika disetujui, set `UNIVERSE_EXCLUDE` di `.env`; perubahan env memerlukan restart.
- `main` lokal 4 commit di depan `origin/main`; push ke remote adalah tindakan user.

## Catatan batasan

Gate disimpan di memori proses sehingga counter kembali nol setelah restart. Persistence lintas restart tidak ditambahkan karena fase ini tidak menambah fitur baru. Coverage ringkasan tersedia melalui snapshot diagnostik yang ada.
