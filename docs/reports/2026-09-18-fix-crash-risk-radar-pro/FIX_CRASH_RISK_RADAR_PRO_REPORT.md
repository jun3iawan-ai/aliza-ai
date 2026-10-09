# Fix: Label "⚠ Crash Risk" Salah Nempel ke Semua Coin di `/radarpro`

**Tanggal:** 2026-09-18
**Branch:** `fix/radarpro-crash-risk-label` (belum di-push/merge, menunggu review manual)
**Sumber temuan:** `RADAR_MARKET_VS_RADAR_PRO_AUDIT_REPORT.md`, bagian 5.1

---

## Langkah 1 — Cascade lengkap `generate_radar_pro()` (sebelum fix)

File: `engine/market/market_radar_pro_analyzer.py:48-144`.

Urutan eksekusi per coin di dalam loop `for coin, data in markets.items():`:

1. **Baca field mentah dari snapshot**: `trend`, `alignment`, `rsi`, `whale` (= `whale_activity`), `risk` (= `market_risk_score`), `phase` (= `market_phase_prediction`). Field `phase` sudah tidak dipakai di manapun dalam fungsi ini sejak sebelum fix (dead read, di luar lingkup task ini, tidak disentuh).
2. **Default label** (cascade if/elif/else berbasis field mentah, TANPA melalui detector):
   ```python
   if risk == "HIGH":
       label = "⚠ Crash Risk"          # <-- SUMBER BUG
   elif whale in ["HIGH", "EXTREME"]:
       label = "🐋 Whale Activity"
   elif trend == "BULLISH" and rsi is not None and rsi > 60:
       label = "🚀 Momentum"
   elif trend == "BEARISH" and rsi is not None and rsi < 40:
       label = "⚡ Breakdown Risk"
   elif trend == "BULLISH":
       label = "📈 Strong Trend"
   else:
       label = "• Neutral"
   ```
3. **`detect_crash_risk(data)`** — hanya menimpa `label` jadi `"⚠ Crash Risk"` kalau `crash_risk_flag` True. Tidak ada cabang else untuk mengembalikan label ke nilai lain kalau False.
4. **`detect_altseason(coin, data, btc_data)`** (skip untuk BTC) — hanya menimpa `label` jadi `"🚀 Altseason Signal"` kalau True. Tidak ada else.
5. **`detect_whale_accumulation(coin, data)`** — hanya menimpa `label` jadi `"🐋 Whale Accumulation"` kalau True. Tidak ada else. (Catatan: baris ini juga menimpa variabel lokal `whale` dengan dict hasil detector, shadowing nilai mentah `whale_activity` yang sudah dipakai di langkah 2 — tidak berdampak fungsional karena hanya dipakai sekali di atas, tapi penamaan variabel yang membingungkan; di luar lingkup fix ini, tidak disentuh.)
6. **`detect_liquidation_cascade(coin, data)`** — hanya menimpa `label` jadi `"⚡ Long Liquidation"`/`"⚡ Short Squeeze"` kalau True. Tidak ada else.

### Konfirmasi pola per detector (menjawab pertanyaan Langkah 1)

Keempat detector (`detect_crash_risk`, `detect_altseason`, `detect_whale_accumulation`, `detect_liquidation_cascade`) **memang sama-sama** memakai pola "hanya timpa kalau True, tidak pernah membatalkan kalau False". Tapi pola ini **bukan bug** untuk keempatnya — ini cascade "upgrade satu arah" yang disengaja: tiap detector boleh mempertajam label jadi lebih spesifik, dan karena masing-masing detector sudah mensyaratkan kondisi teknikal per-coin (trend/RSI milik coin itu sendiri, bukan nilai global), false-positive di satu detector tidak bisa "menempel" ke coin yang tidak memenuhi kondisinya.

**Yang benar-benar bermasalah cuma langkah 2, baris `if risk == "HIGH": label = "⚠ Crash Risk"`.** Ini beda dari 4 detector di atas karena:
- `risk` (`market_risk_score`) adalah **nilai global** — sama untuk seluruh 21 coin dalam satu siklus snapshot (dibuktikan di audit bagian 5.2: dihitung sekali oleh `market_radar()` dari fear&greed + BTC dominance, lalu disalin identik ke setiap coin oleh `market_analyzer.py:487-493`).
- Baris ini memasang label "Crash Risk" HANYA berdasarkan nilai global itu, tanpa syarat teknikal per-coin apa pun — berbeda dengan `detect_crash_risk()` sendiri yang mensyaratkan `risk == HIGH` **DAN** (`trend BEARISH` **ATAU** `RSI ≥ 70` **ATAU** `liquidation_risk kuat`).
- Karena baris ini di langkah 2 (sebelum detector jalan) dan detector di langkah 3 tidak pernah reset label balik, begitu `risk` global HIGH, **semua 21 coin** otomatis dapat label "Crash Risk" di awal — detector di langkah 3 cuma bisa mengkonfirmasi ulang (redundant) untuk coin yang memang berisiko, tapi tidak bisa membersihkan label yang salah untuk coin yang tidak berisiko.

**Kondisi `whale in ["HIGH", "EXTREME"]` di langkah 2 diperiksa juga (sesuai instruksi task) — diputuskan TIDAK diubah**, dengan alasan:
- `whale_activity` juga nilai global (sama seperti `risk`), jadi secara arsitektur mirip.
- **Tapi tidak ada detector setara `detect_crash_risk()` untuk memvalidasi klaim "Whale Activity" secara umum.** `detect_whale_accumulation()` yang ada memeriksa kondisi yang BERBEDA dan lebih spesifik (akumulasi: sideways + RSI 45-60), bukan validasi ulang "apakah whale activity ini relevan untuk coin ini" — jadi tidak ada mekanisme koreksi yang sepadan untuk dipakai sebagai gerbang, berbeda dari kasus crash risk yang punya `detect_crash_risk()` persis untuk topik yang sama.
- Label "🐋 Whale Activity" juga tidak membuat klaim risiko spesifik yang bisa salah tentang coin tersebut (berbeda dari "Crash Risk" yang secara eksplisit menyiratkan coin itu sendiri sedang berisiko) — ini lebih ke informasi konteks pasar ("ada whale bergerak"), bukan vonis kondisi coin.
- Mengubahnya tanpa detector pengganti berarti menghapus total sinyal whale-activity dari 21 coin (bukan memperbaiki, tapi menghilangkan informasi) — perubahan yang jauh lebih besar dari lingkup bug yang dilaporkan. Sesuai instruksi "fix minimal yang tepat sasaran" dan larangan mengubah kondisi yang berbeda pola hanya demi konsistensi kosmetik, baris ini **dibiarkan seperti semula**.

---

## Langkah 2 — Perubahan yang diterapkan

**File:** `engine/market/market_radar_pro_analyzer.py` (satu-satunya file kode yang diubah)

```diff
@@ -68,13 +68,17 @@ def generate_radar_pro():
         alignment = data.get("trend_alignment") or "UNKNOWN"
         rsi = data.get("rsi")
         whale = data.get("whale_activity")
-        risk = data.get("market_risk_score")
         phase = data.get("market_phase_prediction")

-        # Default label dari kondisi existing
-        if risk == "HIGH":
-            label = "⚠ Crash Risk"
-        elif whale in ["HIGH", "EXTREME"]:
+        # Default label dari kondisi existing.
+        # "market_risk_score" adalah nilai GLOBAL (sama untuk semua coin dalam
+        # satu siklus snapshot, lihat market_radar.py + market_analyzer.py),
+        # jadi tidak dipakai langsung sebagai default di sini -- itu dulu
+        # membuat SEMUA coin ter-label "Crash Risk" begitu risk global HIGH,
+        # walau coin ybs sedang bullish. Label "Crash Risk" sekarang hanya
+        # dipasang oleh detect_crash_risk() di bawah, yang mensyaratkan risk
+        # HIGH *dan* kondisi teknikal coin ybs (bearish/overbought/liquidation).
+        if whale in ["HIGH", "EXTREME"]:
             label = "🐋 Whale Activity"
         elif trend == "BULLISH" and rsi is not None and rsi > 60:
             label = "🚀 Momentum"
```

Penjelasan:
- Baris `if risk == "HIGH": label = "⚠ Crash Risk"` **dihapus** dari cascade default. `elif whale in [...]` diubah jadi `if whale in [...]` sebagai kondisi pertama cascade default.
- Variabel `risk = data.get("market_risk_score")` **dihapus** karena setelah baris di atas dihapus, variabel ini jadi tidak terpakai sama sekali di fungsi ini (nilai `market_risk_score` tetap dibaca — oleh `detect_crash_risk(data)` dan `detect_liquidation_cascade(coin, data)` langsung dari dict `data`, bukan dari variabel lokal ini).
- **Tidak ada perubahan lain**: urutan prioritas cascade detector (crash → altseason → whale accumulation → liquidation) dipertahankan persis seperti semula. Field output (`coin`, `trend`, `trend_alignment`, `label`, `crash_risk`) tidak berubah strukturnya.
- Efek: label `"⚠ Crash Risk"` sekarang **hanya** bisa dipasang oleh `detect_crash_risk()` (langkah 3), yang sudah mensyaratkan kombinasi `market_risk_score == HIGH` **dan** kondisi teknikal per-coin. Field output `"crash_risk"` (dipakai konsumen lain di luar tampilan Telegram) tidak berubah nilainya sama sekali — sudah benar sebelumnya karena selalu berasal dari `detect_crash_risk()`, bukan dari default mentah.

**Lingkup diambil sesuai batasan task**: tidak menyentuh `market_radar.py`, detector manapun di `engine/detectors/`, atau `interfaces/telegram_bot.py`. Perubahan murni pada logika pemilihan label di `generate_radar_pro()`.

---

## Langkah 3 — Test

**File baru:** `tests/test_radar_pro_crash_risk.py` (171 baris, tidak menyentuh test lain)

6 test, semua memanggil `generate_radar_pro()` yang sebenarnya (bukan mock detector) dengan `monkeypatch.setattr(analyzer, "get_market_snapshot", ...)` mengembalikan snapshot buatan — jadi keempat detector asli (`detect_crash_risk`, `detect_altseason`, `detect_whale_accumulation`, `detect_liquidation_cascade`) ikut jalan dengan logic aslinya, bukan di-stub.

| Test | Skenario | Assert |
|---|---|---|
| `test_bullish_coin_not_labeled_crash_risk_when_global_risk_high` | **Reproduksi bug persis**: `market_risk_score="HIGH"` global, ETH bullish (trend BULLISH, RSI 63, tidak overbought, tanpa liquidation risk) | `label != "⚠ Crash Risk"`, tepatnya `"🚀 Momentum"`; `crash_risk is False` |
| `test_crash_risk_still_applies_when_detector_confirms_it` | Kontrol positif: `market_risk_score="HIGH"` global, XRP benar-benar bearish (trend BEARISH, RSI 38) | `label == "⚠ Crash Risk"`, `crash_risk is True` — memastikan fix tidak menghilangkan deteksi yang valid |
| `test_low_global_risk_never_confuses_baseline_with_crash` | `market_risk_score="LOW"` global + coin bearish/oversold | `label != "⚠ Crash Risk"`, `crash_risk is False` |
| `test_altseason_signal_still_detected` | Regresi: BTC sideways, SUI bullish momentum, risk LOW | `label == "🚀 Altseason Signal"` |
| `test_whale_accumulation_still_detected` | Regresi: ADA sideways, RSI 50, whale HIGH, risk LOW | `label == "🐋 Whale Accumulation"` |
| `test_whale_activity_default_still_shown_when_not_accumulating` | Regresi: baris `whale in [...]` yang TIDAK diubah tetap berfungsi untuk kasus yang tidak match akumulasi | `label == "🐋 Whale Activity"` |

### Verifikasi test benar-benar mendeteksi bug (bukan test palsu)

Sebelum melapor selesai, fix di-`git stash` sementara (kode dikembalikan ke versi buggy) dan suite baru dijalankan ulang:

```
tests/test_radar_pro_crash_risk.py::TestCrashRiskNoLongerBlanket::test_bullish_coin_not_labeled_crash_risk_when_global_risk_high FAILED
    AssertionError: assert '⚠ Crash Risk' != '⚠ Crash Risk'
1 failed, 5 passed in 0.16s
```

Persis seperti prediksi: hanya test reproduksi bug yang gagal terhadap kode lama, 5 test lain (termasuk kontrol positif crash risk asli dan regresi 3 detector lain) tetap lolos — mengkonfirmasi test ini presisi menargetkan bug yang dilaporkan, bukan kebetulan lolos/gagal. Fix lalu dikembalikan (`git stash pop`) sebelum lanjut.

### Hasil test run

**Baru saja (isolated):**
```
$ venv/bin/python3 -m pytest tests/test_radar_pro_crash_risk.py -v
6 passed in 0.29s
```

**Full suite SEBELUM fix (baseline, di branch main sebelum perubahan apa pun):**
```
$ venv/bin/python3 -m pytest tests/ -q
248 passed, 3 warnings in 109.44s
```

**Full suite SESUDAH fix + test baru:**
```
$ venv/bin/python3 -m pytest tests/ -q
254 passed, 3 warnings in 32.83s
```

248 (baseline) + 6 (test baru) = 254. **0 gagal**, tidak ada regresi.

---

## `git diff --stat main`

```
 engine/market/market_radar_pro_analyzer.py |  14 ++-
 tests/test_radar_pro_crash_risk.py         | 171 +++++++++++++++++++++++++++++
 2 files changed, 180 insertions(+), 5 deletions(-)
```

Sesuai batasan task: hanya `market_radar_pro_analyzer.py` (kode fix) dan `tests/test_radar_pro_crash_risk.py` (test) yang berubah relatif terhadap `main`. Tidak ada file lain yang tersentuh (`market_radar.py`, detector, `telegram_bot.py`, dll tetap identik dengan `main`).

---

## Status

- **Branch:** `fix/radarpro-crash-risk-label`
- **Belum di-push, belum di-merge** — menunggu review manual seperti biasa.
- Perubahan bersifat display-only untuk `/radarpro`; `/radar` tidak terpengaruh sama sekali (sudah dikonfirmasi di audit sebelumnya bahwa `/radar` tidak pernah membaca field `label`).
