# Strategi Testing

Dokumen ini memisahkan automated test dari smoke test runtime.

## Tingkat pengujian

| Tingkat | Tujuan | Perintah/lokasi |
|---|---|---|
| Test terarah | Memvalidasi unit/fitur yang baru berubah | `venv/bin/python -m pytest -q tests/test_<fase>.py` |
| Shutdown | Kontrak deadline dan cleanup | `venv/bin/python -m pytest -q tests/test_shutdown.py` |
| Full suite | Regresi seluruh test repo | `venv/bin/python -m pytest -q` |
| Backtest reproducibility | Hasil deterministik, anti-lookahead, biaya/metric | `tests/test_fase2.py` dan runner `backtest.run_backtest` |
| Manual smoke | Service, Telegram, snapshot, DB, dashboard | [smoke-test.md](../runbooks/smoke-test.md) |

## Kebijakan

1. Perubahan kode harus menjalankan test terarah; perubahan lintas pipeline juga menjalankan full suite.
2. Perubahan dokumentasi murni tidak wajib menjalankan Python test, tetapi wajib menjalankan pemeriksaan link dan diff docs-only.
3. Test database harus memakai fixture/temp DB; jangan menulis `data/aliza.db` produksi.
4. Test API/provider eksternal harus diisolasi dengan mock/fixture bila tujuannya unit test.
5. Kegagalan harus dicatat apa adanya; jangan menyatakan lulus jika test dilewati.

## Kontrak pipeline yang diuji

Automated test perlu melindungi:

- market feature dan snapshot contract;
- `TradingBrain` serta level entry/SL/TP/RR/confidence;
- opportunity scan dan signal filtering;
- dispatch-before-record serta signal provenance;
- trade lifecycle pada DB test;
- scheduler/shutdown deadline;
- backtest fees, funding, entry timing, same-bar policy, dan anti-lookahead.

## Reproducibility backtest

`tests/test_fase2.py::test_reproducibility` membandingkan dua simulasi identik dan `test_anti_lookahead_simulator_ignores_future_candles` memastikan candle masa depan tidak mengubah hasil.

Untuk run riset yang dapat diulang, pin commit dan rentang waktu, gunakan dataset yang sama, dan simpan `config.json` hasil runner. Contoh:

```bash
venv/bin/python -m backtest.run_backtest \
  --start 2024-01-01T00:00:00+00:00 \
  --end 2026-01-01T00:00:00+00:00 \
  --no-download \
  --data-dir backtest/data \
  --output-dir backtest/results/manual-repro-check
```

Runner menyimpan commit, konfigurasi, metrics, dan trades. Jangan membandingkan run dengan dataset atau konfigurasi berbeda seolah-olah identik.
