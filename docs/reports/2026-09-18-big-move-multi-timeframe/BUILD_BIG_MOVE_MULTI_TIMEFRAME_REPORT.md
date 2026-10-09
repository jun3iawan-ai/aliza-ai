# Build Report — Big Move Alert Multi-Timeframe

Tanggal: 18 September 2026  
Branch: `feature/big-move-multi-timeframe`  
Commit lokal: `4561a3f feat: add multi-timeframe big move alerts`  
Basis: `main` pada `7f5b5de`. Belum di-merge atau di-push.

## Implementasi

- Snapshot engine kini menambahkan `price_change_15m` dan `price_change_30m` dari close candle Binance Spot terakhir yang sudah selesai. Cache short interval terpisah dan refresh pada boundary UTC 15 menit / 30 menit; kegagalan tetap dicache 300 detik, sama dengan pola 1h.
- Enrichment dan helper 1h lama tidak diubah: `price_change_1h`, prioritas field, formula, cache 1h, dan fallback 24h tetap berjalan seperti sebelumnya.
- `big_move_checker` mengevaluasi `15m`, `30m`, lalu `1h` per coin dengan threshold konstan `3.0`. Hanya 1h memakai helper lama sehingga boleh fallback 24h; 15m/30m membaca field tepatnya dan skip bila tidak ada.
- Identity cooldown/dedup kini `<coin>:<direction>:<timeframe>`; default cooldown yang dipakai tetap `ngov.BIG_MOVE_COOLDOWN_SEC` (7200 detik), tanpa konstanta baru. Karena itu ketiga alert dapat lolos independen.
- Test baru ditempatkan pada `tests/test_big_move_multi_timeframe.py`. Satu ekspektasi test lama di `tests/test_notifikasi_mitigasi.py` diperbarui dari key legacy `OM:down` menjadi `OM:down:1h`, sesuai kontrak state baru.

## Estimasi request Binance

Untuk sekitar 21 coin, cache hanya refetch ketika boundary masing-masing interval:

| Interval baru | Refresh/jam | Request/jam |
| --- | ---: | ---: |
| 15m | 4 × 21 | 84 |
| 30m | 2 × 21 | 42 |
| Tambahan |  | **126** |

Uji dua request `GET /api/v3/klines?...&limit=2` menunjukkan header `x-mbx-used-weight-1m` naik 2 → 4, yaitu weight 2/request. Tambahan ini berarti sekitar **252 request-weight/jam**. Pada boundary jam, 15m + 30m + 1h dapat bertepatan: 63 request / 126 weight sekali jalan (tambahan short-window sendiri: 42 request / 84 weight). Endpoint `/api/v3/exchangeInfo` saat build melaporkan limit aktif `REQUEST_WEIGHT=6000` per menit; burst maksimum 126 adalah sekitar 2.1% limit. Binance juga mendokumentasikan bahwa rate limit berbasis IP, setiap route berbobot, dan 429 harus dibackoff. [Dokumentasi Binance](https://developers.binance.com/en/docs/products/spot/rest-api)

## Output test baru (mentah)

```text
============================= test session starts ==============================
platform linux -- Python 3.10.12, pytest-9.1.1, pluggy-1.6.0 -- /opt/aliza-ai/venv/bin/python
cachedir: .pytest_cache
rootdir: /opt/aliza-ai
plugins: anyio-4.12.1, langsmith-0.7.14
collecting ... collected 5 items

tests/test_big_move_multi_timeframe.py::ShortWindowSnapshotEnrichmentTests::test_15m_and_30m_caches_refresh_only_after_their_boundaries 
tests/test_big_move_multi_timeframe.py::ShortWindowSnapshotEnrichmentTests::test_15m_and_30m_caches_refresh_only_after_their_boundaries PASSED [ 20%]
tests/test_big_move_multi_timeframe.py::ShortWindowSnapshotEnrichmentTests::test_enrichment_writes_correct_15m_and_30m_fields PASSED [ 40%]
tests/test_big_move_multi_timeframe.py::BigMoveMultiTimeframeTests::test_15m_and_30m_do_not_fall_back_to_24h_but_1h_does PASSED [ 60%]
tests/test_big_move_multi_timeframe.py::BigMoveMultiTimeframeTests::test_short_window_cooldown_does_not_block_other_windows PASSED [ 80%]
tests/test_big_move_multi_timeframe.py::BigMoveMultiTimeframeTests::test_three_qualifying_windows_queue_three_independent_alerts PASSED [100%]

=============================== warnings summary ===============================
<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type swigvarlink has no __module__ attribute

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
============== 5 passed, 3 warnings, 2 subtests passed in 13.04s ===============
```

## Full suite sebelum (main worktree, mentah)

```text
.......................................................................... [ 19%]
.................................................................... [ 37%]
........................................................................ [ 57%]
........................................................................ [ 76%]
........................................................................ [ 95%]
................                                                         [100%]
=============================== warnings summary ===============================
<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type swigvarlink has no __module__ attribute

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
374 passed, 3 warnings, 74 subtests passed in 34.14s
```

## Full suite sesudah (branch fitur, mentah)

```text
.......................................................................... [ 19%]
.................................................................. [ 36%]
........................................................................ [ 55%]
........................................................................ [ 74%]
........................................................................ [ 93%]
.......................                                                  [100%]
=============================== warnings summary ===============================
<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type swigvarlink has no __module__ attribute

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
379 passed, 3 warnings, 76 subtests passed in 35.76s
```

Hasil: baseline **374 passed, 3 warnings, 74 subtests passed**; sesudah **379 passed, 3 warnings, 76 subtests passed**. Tidak ada kegagalan.

## Diff kode aktual

```diff
diff --git a/engine/market/market_snapshot_engine.py b/engine/market/market_snapshot_engine.py
index 19ee7e8..0f7b109 100644
--- a/engine/market/market_snapshot_engine.py
+++ b/engine/market/market_snapshot_engine.py
@@ -38,6 +38,12 @@ _one_hour_close_cache: dict[str, dict[str, float | int]] = {}
 _one_hour_close_cache_lock = Lock()
 ONE_HOUR_FAILURE_RETRY_SEC = 300
 
+# Short Big Move windows use the same closed-candle semantics as the existing
+# 1h reference. Their cache is intentionally separate so a 15m/30m refresh
+# never changes the established 1h cache behaviour.
+_short_interval_close_cache: dict[str, dict[str, float | int]] = {}
+_short_interval_close_cache_lock = Lock()
+
 
 def _get_cg_headers() -> dict:
     h = {"User-Agent": "AlizaAI"}
@@ -278,6 +284,84 @@ def _latest_closed_1h_close(pair: str, now: float | None = None) -> float | None
     return close
 
 
+def _interval_cache_refresh_after(now: float, interval_sec: int) -> float:
+    """First second after the next UTC interval candle has closed."""
+    return float((int(now) // interval_sec + 1) * interval_sec + 1)
+
+
+def _latest_closed_short_interval_close(
+    pair: str,
+    interval: str,
+    interval_sec: int,
+    now: float | None = None,
+) -> float | None:
+    """Return the latest closed 15m/30m Binance close, cached to rollover."""
+    now = time.time() if now is None else float(now)
+    symbol = str(pair or "").strip().upper()
+    if not symbol or interval_sec <= 0:
+        return None
+    cache_key = f"{symbol}:{interval}"
+    with _short_interval_close_cache_lock:
+        cached = _short_interval_close_cache.get(cache_key)
+        if cached and now < float(cached.get("refresh_after", 0.0)):
+            cached_close = float(cached.get("close", 0.0))
+            return cached_close if cached_close > 0 else None
+
+    def _cache_failed_lookup() -> None:
+        with _short_interval_close_cache_lock:
+            _short_interval_close_cache[cache_key] = {
+                "close": 0.0,
+                "refresh_after": now + ONE_HOUR_FAILURE_RETRY_SEC,
+            }
+
+    try:
+        response = requests.get(
+            BINANCE_KLINES_URL,
+            params={"symbol": symbol, "interval": interval, "limit": 2},
+            headers=ENRICH_HEADERS,
+            timeout=10,
+        )
+        if response.status_code != 200:
+            logging.warning(
+                "market_snapshot_engine: Binance %s kline HTTP %s pair=%s",
+                interval,
+                response.status_code,
+                symbol,
+            )
+            _cache_failed_lookup()
+            return None
+        raw = response.json()
+    except Exception as exc:
+        logging.warning(
+            "market_snapshot_engine: Binance %s kline fetch failed pair=%s: %s",
+            interval,
+            symbol,
+            exc,
+        )
+        _cache_failed_lookup()
+        return None
+
+    now_ms = int(now * 1000)
+    close = None
+    for candle in raw if isinstance(raw, list) else []:
+        try:
+            close_time = int(candle[6])
+            value = float(candle[4])
+        except (TypeError, ValueError, IndexError):
+            continue
+        if close_time < now_ms and value > 0:
+            close = value
+    if close is None:
+        _cache_failed_lookup()
+        return None
+    with _short_interval_close_cache_lock:
+        _short_interval_close_cache[cache_key] = {
+            "close": close,
+            "refresh_after": _interval_cache_refresh_after(now, interval_sec),
+        }
+    return close
+
+
 def _price_change_from_1h_close(price: object, reference_close: object) -> float | None:
     """Percent change of the live snapshot price against a closed 1h reference."""
     try:
@@ -305,6 +389,24 @@ def _enrich_collected_with_binance_1h(collected: dict) -> None:
             row["price_change_1h"] = pct
             row["price_change_pct_1h"] = pct
 
+def _enrich_collected_with_binance_short_intervals(collected: dict) -> None:
+    """Write 15m/30m Big Move percentages from fresh closed Binance candles."""
+    if not collected:
+        return
+    for sym, row in collected.items():
+        if not isinstance(row, dict):
+            continue
+        pair = f"{str(sym).strip().upper()}USDT"
+        for interval, interval_sec, field_name in (
+            ("15m", 15 * 60, "price_change_15m"),
+            ("30m", 30 * 60, "price_change_30m"),
+        ):
+            reference_close = _latest_closed_short_interval_close(pair, interval, interval_sec)
+            pct = _price_change_from_1h_close(row.get("price"), reference_close)
+            if pct is not None:
+                row[field_name] = pct
+
+
 
 def _coverage_for_symbol(symbol, data, valid, reason=None):
     payload = data.get("market_data") if isinstance(data, dict) and isinstance(data.get("market_data"), dict) else data
@@ -431,6 +533,7 @@ def update_market_snapshot():
     if collected:
         _enrich_collected_with_binance_24h(collected)
         _enrich_collected_with_binance_1h(collected)
+        _enrich_collected_with_binance_short_intervals(collected)
         snapshot_ts = datetime.utcnow()
         market_intelligence = None
         if generate_market_intelligence is not None:
diff --git a/interfaces/telegram_bot.py b/interfaces/telegram_bot.py
index b6dd5d1..eee0bdf 100644
--- a/interfaces/telegram_bot.py
+++ b/interfaces/telegram_bot.py
@@ -6661,6 +6661,24 @@ def _snapshot_big_move_pct(coin_data: dict) -> float | None:
     return None
 
 
+# Short windows deliberately do not fall back to the 24h snapshot fields: a
+# 24h value would misrepresent a 15m/30m alert. The established 1h helper is
+# preserved unchanged, including its legacy 24h fallback.
+BIG_MOVE_TIMEFRAMES = (
+    ("15m", "price_change_15m", "15 menit"),
+    ("30m", "price_change_30m", "30 menit"),
+    ("1h", None, "1 jam"),
+)
+
+
+def _snapshot_big_move_pct_for_timeframe(coin_data: dict, field_name: str | None) -> float | None:
+    if field_name is None:
+        return _snapshot_big_move_pct(coin_data)
+    if not isinstance(coin_data, dict):
+        return None
+    return _snapshot_float(coin_data.get(field_name))
+
+
 def _fmt_snapshot_usd(v: float) -> str:
     if v is None:
         return "$—"
@@ -6905,7 +6923,7 @@ async def rsi_extreme_checker(context: ContextTypes.DEFAULT_TYPE):
 
 
 async def big_move_checker(context: ContextTypes.DEFAULT_TYPE):
-    """Perubahan harga ≥3% (1h jika ada, else fallback snapshot); cooldown (coin, up|down)."""
+    """Check 15m/30m/1h moves ≥3%; 1h retains its snapshot fallback."""
     try:
         snapshot = get_market_snapshot()
         data_map = snapshot.get("data") or {}
@@ -6921,58 +6939,58 @@ async def big_move_checker(context: ContextTypes.DEFAULT_TYPE):
             logging.warning("big_move_checker: no chat_id")
             return
         now_utc = datetime.utcnow()
+        now_ts = now_utc.replace(tzinfo=timezone.utc).timestamp()
         for coin in data_map.keys():
             if coin in ALERT_COIN_BLACKLIST:
                 continue
             coin_data = data_map.get(coin)
             if not isinstance(coin_data, dict):
                 continue
-            pct = _snapshot_big_move_pct(coin_data)
-            if pct is None or abs(pct) < 3.0:
-                continue
             price = _snapshot_float(coin_data.get("price"))
             if price is None:
                 continue
-            # Validasi umur data — skip jika snapshot coin lebih dari SNAPSHOT_MAX_AGE_SEC.
-            # (Sebelumnya cek ini membandingkan epoch float dengan hasattr/isoformat dan
-            # selalu gagal secara diam-diam — lihat NOTIFIKASI_MITIGASI_REPORT.md.)
+            # Validate the shared snapshot before creating an alert for any window.
             if not ngov.is_coin_snapshot_fresh(coin_data):
                 logging.warning("big_move_checker: skip %s — stale snapshot data", coin)
                 ngov.record_skipped_stale("big_move")
                 continue
-            direction = "up" if pct > 0 else "down"
-            # Cooldown khusus big_move (BIG_MOVE_COOLDOWN_SEC, default 2 jam), per (coin, arah) —
-            # terpisah dari cooldown 4 jam near_support/near_resistance/rsi supaya bisa
-            # dikonfigurasi independen dan supaya alert naik & turun tidak saling menekan.
-            key = f"{coin}:{direction}"
-            # See _whale_alert_allowed for why .replace(tzinfo=timezone.utc) is required
-            # here instead of a bare now_utc.timestamp() on this naive datetime.
-            now_ts = now_utc.replace(tzinfo=timezone.utc).timestamp()
-            if not ngov.is_cooldown_allowed("big_move", key, ngov.BIG_MOVE_COOLDOWN_SEC, now=now_ts):
-                continue
-            if ngov.is_duplicate_value("big_move", key, pct):
-                continue  # nilai persis sama dengan alert terakhir — data tidak benar-benar berubah
-            if pct > 0:
-                msg = (
-                    "🚀 BIG MOVE ALERT\n\n"
-                    f"{coin} naik {pct:+.2f}% dalam 1 jam!\n"
-                    f"Harga: {_fmt_snapshot_usd(price)}\n"
-                    "💡 Momentum kuat — pantau apakah breakout atau bull trap\n"
-                    "——\n"
-                    f"Aliza Engine • {_wib_now_label()}"
-                )
-            else:
-                msg = (
-                    "💥 BIG MOVE ALERT\n\n"
-                    f"{coin} turun {abs(pct):.2f}% dalam 1 jam!\n"
-                    f"Harga: {_fmt_snapshot_usd(price)}\n"
-                    "💡 Penurunan tajam — pantau support dan potensi entry\n"
-                    "——\n"
-                    f"Aliza Engine • {_wib_now_label()}"
+            for timeframe, field_name, window_label in BIG_MOVE_TIMEFRAMES:
+                pct = _snapshot_big_move_pct_for_timeframe(coin_data, field_name)
+                if pct is None or abs(pct) < 3.0:
+                    continue
+                direction = "up" if pct > 0 else "down"
+                # Each timeframe has an independent persisted cooldown/dedup key.
+                key = f"{coin}:{direction}:{timeframe}"
+                if not ngov.is_cooldown_allowed("big_move", key, ngov.BIG_MOVE_COOLDOWN_SEC, now=now_ts):
+                    continue
+                if ngov.is_duplicate_value("big_move", key, pct):
+                    continue  # nilai tidak benar-benar berubah pada timeframe ini
+                if pct > 0:
+                    msg = (
+                        "🚀 BIG MOVE ALERT\n\n"
+                        f"{coin} naik {pct:+.2f}% dalam {window_label}!\n"
+                        f"Harga: {_fmt_snapshot_usd(price)}\n"
+                        "💡 Momentum kuat — pantau apakah breakout atau bull trap\n"
+                        "——\n"
+                        f"Aliza Engine • {_wib_now_label()}"
+                    )
+                else:
+                    msg = (
+                        "💥 BIG MOVE ALERT\n\n"
+                        f"{coin} turun {abs(pct):.2f}% dalam {window_label}!\n"
+                        f"Harga: {_fmt_snapshot_usd(price)}\n"
+                        "💡 Penurunan tajam — pantau support dan potensi entry\n"
+                        "——\n"
+                        f"Aliza Engine • {_wib_now_label()}"
+                    )
+                ngov.record_cooldown("big_move", key, now=now_ts)
+                ngov.record_value("big_move", key, pct)
+                ngov.queue_alert(
+                    "big_move",
+                    "BIG MOVE",
+                    f"{coin} {pct:+.2f}% ({timeframe}) @ {_fmt_snapshot_usd(price)}",
+                    msg,
                 )
-            ngov.record_cooldown("big_move", key, now=now_ts)
-            ngov.record_value("big_move", key, pct)
-            ngov.queue_alert("big_move", "BIG MOVE", f"{coin} {pct:+.2f}% @ {_fmt_snapshot_usd(price)}", msg)
     except Exception as e:
         logging.error("big_move_checker: %s", e, exc_info=True)
 
diff --git a/tests/test_big_move_multi_timeframe.py b/tests/test_big_move_multi_timeframe.py
new file mode 100644
index 0000000..6ab8d44
--- /dev/null
+++ b/tests/test_big_move_multi_timeframe.py
@@ -0,0 +1,149 @@
+"""Regression coverage for 15m/30m/1h Big Move alerts."""
+
+import time
+from types import SimpleNamespace
+from unittest import IsolatedAsyncioTestCase, TestCase
+from unittest.mock import Mock, patch
+
+from engine.alerts import notification_governor as ngov
+from engine.market import market_snapshot_engine as mse
+
+with patch("dotenv.load_dotenv", return_value=False):
+    from interfaces import telegram_bot as tb
+
+
+class ShortWindowSnapshotEnrichmentTests(TestCase):
+    def setUp(self):
+        mse._short_interval_close_cache.clear()
+
+    def tearDown(self):
+        mse._short_interval_close_cache.clear()
+
+    def test_enrichment_writes_correct_15m_and_30m_fields(self):
+        collected = {"MOVE": {"price": 105.0}}
+        with patch.object(
+            mse,
+            "_latest_closed_short_interval_close",
+            side_effect=[100.0, 102.0],
+        ):
+            mse._enrich_collected_with_binance_short_intervals(collected)
+
+        self.assertAlmostEqual(collected["MOVE"]["price_change_15m"], 5.0)
+        self.assertAlmostEqual(
+            collected["MOVE"]["price_change_30m"], (105.0 / 102.0 - 1.0) * 100.0
+        )
+
+    def test_15m_and_30m_caches_refresh_only_after_their_boundaries(self):
+        cases = (
+            ("15m", 15 * 60, 900.0, 1_200.0, 1_801.0, 899_999, 900_000),
+            ("30m", 30 * 60, 1_800.0, 2_400.0, 3_601.0, 1_799_999, 1_800_000),
+        )
+        for interval, interval_sec, at_boundary, in_window, after_boundary, first_close, second_open in cases:
+            with self.subTest(interval=interval):
+                mse._short_interval_close_cache.clear()
+                response = Mock(status_code=200)
+                response.json.return_value = [
+                    [0, "0", "0", "0", "100", "0", first_close],
+                    [second_open, "0", "0", "0", "101", "0", second_open + interval_sec - 1],
+                ]
+                with patch.object(mse.requests, "get", return_value=response) as get:
+                    self.assertEqual(
+                        mse._latest_closed_short_interval_close(
+                            "BTCUSDT", interval, interval_sec, now=at_boundary
+                        ),
+                        100.0,
+                    )
+                    self.assertEqual(
+                        mse._latest_closed_short_interval_close(
+                            "BTCUSDT", interval, interval_sec, now=in_window
+                        ),
+                        100.0,
+                    )
+                    self.assertEqual(
+                        mse._latest_closed_short_interval_close(
+                            "BTCUSDT", interval, interval_sec, now=after_boundary
+                        ),
+                        101.0,
+                    )
+                self.assertEqual(get.call_count, 2)
+
+
+class BigMoveMultiTimeframeTests(IsolatedAsyncioTestCase):
+    def setUp(self):
+        ngov.reset_state_for_tests()
+        self.context = SimpleNamespace(bot_data={})
+
+    async def test_three_qualifying_windows_queue_three_independent_alerts(self):
+        snapshot = {
+            "data": {
+                "MOVE": {
+                    "price": 105.0,
+                    "price_change_15m": 3.1,
+                    "price_change_30m": 3.2,
+                    "price_change_1h": 3.3,
+                    "timestamp": time.time(),
+                }
+            }
+        }
+        with patch.object(tb, "get_market_snapshot", return_value=snapshot), patch.object(
+            tb, "DEFAULT_CHAT_ID", "12345"
+        ):
+            await tb.big_move_checker(self.context)
+
+        self.assertEqual(ngov.pending_count(), 3)
+        messages = ngov.flush_pending()
+        self.assertEqual(len(messages), 3)
+        self.assertTrue(any("dalam 15 menit!" in message for message in messages))
+        self.assertTrue(any("dalam 30 menit!" in message for message in messages))
+        self.assertTrue(any("dalam 1 jam!" in message for message in messages))
+        for timeframe in ("15m", "30m", "1h"):
+            self.assertIsNotNone(
+                ngov.get_value("cooldown:big_move", f"MOVE:up:{timeframe}")
+            )
+
+    async def test_short_window_cooldown_does_not_block_other_windows(self):
+        now = time.time()
+        ngov.record_cooldown("big_move", "MOVE:up:15m", now=now)
+        ngov.record_value("big_move", "MOVE:up:15m", 3.1)
+        snapshot = {
+            "data": {
+                "MOVE": {
+                    "price": 105.0,
+                    "price_change_15m": 3.1,
+                    "price_change_30m": 3.2,
+                    "price_change_1h": 3.3,
+                    "timestamp": now,
+                }
+            }
+        }
+        with patch.object(tb, "get_market_snapshot", return_value=snapshot), patch.object(
+            tb, "DEFAULT_CHAT_ID", "12345"
+        ):
+            await tb.big_move_checker(self.context)
+
+        messages = ngov.flush_pending()
+        self.assertEqual(len(messages), 2)
+        self.assertFalse(any("dalam 15 menit!" in message for message in messages))
+        self.assertTrue(any("dalam 30 menit!" in message for message in messages))
+        self.assertTrue(any("dalam 1 jam!" in message for message in messages))
+
+    async def test_15m_and_30m_do_not_fall_back_to_24h_but_1h_does(self):
+        snapshot = {
+            "data": {
+                "FALLBACK": {
+                    "price": 105.0,
+                    "price_change_percentage_24h": 4.5,
+                    "timestamp": time.time(),
+                }
+            }
+        }
+        with patch.object(tb, "get_market_snapshot", return_value=snapshot), patch.object(
+            tb, "DEFAULT_CHAT_ID", "12345"
+        ):
+            await tb.big_move_checker(self.context)
+
+        messages = ngov.flush_pending()
+        self.assertEqual(len(messages), 1)
+        self.assertIn("dalam 1 jam!", messages[0])
+        self.assertNotIn("15 menit", messages[0])
+        self.assertNotIn("30 menit", messages[0])
diff --git a/tests/test_notifikasi_mitigasi.py b/tests/test_notifikasi_mitigasi.py
index c7dee7a..c8b5803 100644
--- a/tests/test_notifikasi_mitigasi.py
+++ b/tests/test_notifikasi_mitigasi.py
@@ -91,7 +91,7 @@ class SnapshotAlertCooldownTests(TestCase):
 
 
 class BigMoveCooldownTests(IsolatedAsyncioTestCase):
-    """Item 2 / test 2: big_move_checker cooldown per (coin, direction),
+    """Item 2 / test 2: big_move_checker cooldown per (coin, direction, timeframe),
     BIG_MOVE_COOLDOWN_SEC, persisted."""
 
     def setUp(self):
@@ -130,7 +130,7 @@ class BigMoveCooldownTests(IsolatedAsyncioTestCase):
         with patch.object(telegram_bot, "get_market_snapshot", return_value=snapshot), \
              patch.object(telegram_bot, "DEFAULT_CHAT_ID", "12345"):
             await telegram_bot.big_move_checker(ctx)
-        recorded = ngov.get_value("cooldown:big_move", "OM:down")
+        recorded = ngov.get_value("cooldown:big_move", "OM:down:1h")
         self.assertIsNotNone(recorded)
         self.assertLess(abs(recorded - real_now), 5)
 

```

