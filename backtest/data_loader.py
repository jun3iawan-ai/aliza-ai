"""Binance kline/funding loader with local CSV cache and rate-limit backoff."""

from __future__ import annotations

import csv
import json
import logging
import random
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

BINANCE_BASE_URL = "https://api.binance.com"
KLINE_COLUMNS = ["open_time", "open", "high", "low", "close", "volume", "close_time"]
INTERVAL_MS = {
    "5m": 5 * 60 * 1000,
    "1h": 60 * 60 * 1000,
    "4h": 4 * 60 * 60 * 1000,
    "1d": 24 * 60 * 60 * 1000,
}


def to_ms(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value if value > 10_000_000_000 else value * 1000)
    text = str(value).strip()
    if text.isdigit():
        return to_ms(int(text))
    return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp() * 1000)


def _row_from_binance(row):
    return {
        "open_time": int(row[0]),
        "open": float(row[1]),
        "high": float(row[2]),
        "low": float(row[3]),
        "close": float(row[4]),
        "volume": float(row[5]),
        "close_time": int(row[6]),
    }


def _normalise_row(row):
    return {
        "open_time": int(row["open_time"]),
        "open": float(row["open"]),
        "high": float(row["high"]),
        "low": float(row["low"]),
        "close": float(row["close"]),
        "volume": float(row.get("volume", 0)),
        "close_time": int(row["close_time"]),
    }


class BinanceDataLoader:
    def __init__(self, data_dir="backtest/data", session=None, sleep_fn=time.sleep):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.session = session or requests.Session()
        self.sleep_fn = sleep_fn

    def cache_path(self, coin, interval):
        return self.data_dir / f"{coin.upper()}USDT_{interval}.csv"

    def load_cached(self, coin, interval):
        path = self.cache_path(coin, interval)
        if not path.exists():
            return []
        with path.open(newline="") as handle:
            return [_normalise_row(row) for row in csv.DictReader(handle)]

    def save_cached(self, coin, interval, rows):
        path = self.cache_path(coin, interval)
        rows = sorted({_normalise_row(row)["open_time"]: _normalise_row(row) for row in rows}.values(), key=lambda row: row["open_time"])
        with path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=KLINE_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        return path

    def _get(self, endpoint, params, retries=5):
        delay = 1.0
        for attempt in range(retries):
            response = self.session.get(BINANCE_BASE_URL + endpoint, params=params, timeout=30)
            if response.status_code == 200:
                return response.json()
            if response.status_code in (418, 429, 500, 502, 503, 504):
                retry_after = response.headers.get("Retry-After")
                wait = float(retry_after) if retry_after else delay + random.uniform(0, min(1.0, delay))
                logger.warning("Binance HTTP %s; retry %d/%d after %.2fs", response.status_code, attempt + 1, retries, wait)
                self.sleep_fn(wait)
                delay = min(delay * 2, 60.0)
                continue
            raise RuntimeError(f"Binance HTTP {response.status_code}: {response.text[:200]}")
        raise RuntimeError("Binance request retries exhausted")

    def download_klines(self, coin, interval, start_ms, end_ms):
        if interval not in INTERVAL_MS:
            raise ValueError(f"Unsupported interval: {interval}")
        rows = []
        cursor = int(start_ms)
        step = INTERVAL_MS[interval]
        while cursor < end_ms:
            payload = self._get(
                "/api/v3/klines",
                {"symbol": f"{coin.upper()}USDT", "interval": interval, "startTime": cursor, "endTime": int(end_ms), "limit": 1000},
            )
            if not payload:
                break
            batch = [_row_from_binance(item) for item in payload if len(item) >= 7 and int(item[6]) <= end_ms]
            rows.extend(batch)
            last_open = batch[-1]["open_time"] if batch else cursor
            next_cursor = last_open + step
            if next_cursor <= cursor:
                break
            cursor = next_cursor
            if len(payload) < 1000:
                break
        return sorted({row["open_time"]: row for row in rows}.values(), key=lambda row: row["open_time"])

    def load_klines(self, coin, interval, start, end, download=True):
        start_ms, end_ms = to_ms(start), to_ms(end)
        cached = self.load_cached(coin, interval)
        selected = [row for row in cached if start_ms <= row["open_time"] <= end_ms]
        if selected and (not download or selected[0]["open_time"] <= start_ms + INTERVAL_MS[interval]):
            return selected
        if not download:
            return selected
        rows = self.download_klines(coin, interval, start_ms, end_ms)
        self.save_cached(coin, interval, rows)
        return [row for row in rows if start_ms <= row["open_time"] <= end_ms]

    def load_funding(self, coin, start, end, download=True):
        path = self.data_dir / f"{coin.upper()}USDT_funding.csv"
        if path.exists() and not download:
            with path.open(newline="") as handle:
                return [{"timestamp": int(row["timestamp"]), "funding_rate": float(row["funding_rate"])} for row in csv.DictReader(handle)]
        if not download:
            return []
        start_ms, end_ms = to_ms(start), to_ms(end)
        rows = []
        cursor = start_ms
        while cursor < end_ms:
            payload = self._get(
                "/fapi/v1/fundingRate",
                {"symbol": f"{coin.upper()}USDT", "startTime": cursor, "endTime": end_ms, "limit": 1000},
            )
            if not payload:
                break
            rows.extend({"timestamp": int(item["fundingTime"]), "funding_rate": float(item["fundingRate"])} for item in payload)
            last = rows[-1]["timestamp"]
            if last < cursor:
                break
            cursor = last + 1
            if len(payload) < 1000:
                break
        rows = sorted({row["timestamp"]: row for row in rows}.values(), key=lambda row: row["timestamp"])
        with path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["timestamp", "funding_rate"])
            writer.writeheader()
            writer.writerows(rows)
        return rows


def load_coin_dataset(loader, coin, start, end, download=True):
    return {
        interval: loader.load_klines(coin, interval, start, end, download=download)
        for interval in ("4h", "1d", "5m", "1h")
    } | {"funding": loader.load_funding(coin, start, end, download=download)}
