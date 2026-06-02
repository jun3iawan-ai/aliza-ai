"""
Investing.com economic calendar — cadangan jika FMP kosong/gagal.

PERINGATAN: Endpoint/HTML bisa berubah tanpa notice. Cache + rate limit ketat;
fallback ke rule-based di economic_calendar.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

logger = logging.getLogger(__name__)

CACHE_TTL = int(os.getenv("INVESTING_CALENDAR_CACHE_SEC", "3600"))
MIN_FETCH_INTERVAL = int(os.getenv("INVESTING_MIN_FETCH_INTERVAL_SEC", "3600"))

WIB = timezone(timedelta(hours=7))

_cache: dict[str, Any] = {"data": [], "fetched_at": 0.0}
_last_http_at = 0.0

HIGH_KW = (
    "interest rate decision",
    "fomc",
    "federal funds rate",
    "nonfarm payrolls",
    "non-farm payrolls",
    "cpi",
    "consumer price index",
    "pce price index",
    "pce",
    "core pce",
    "gdp",
    "gross domestic product",
    "unemployment rate",
    "fed chair",
    "powell",
)


def _is_high_name(name: str) -> bool:
    nl = (name or "").lower()
    return any(kw in nl for kw in HIGH_KW)


def _impact_from_name(name: str) -> str:
    return "HIGH" if _is_high_name(name) else "MEDIUM"


def _dt_to_event_dict(
    dt_utc: datetime,
    name: str,
    source: str,
    *,
    impact: str | None = None,
) -> dict[str, str]:
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    else:
        dt_utc = dt_utc.astimezone(timezone.utc)
    dt_wib = dt_utc.astimezone(WIB)
    imp = impact if impact else _impact_from_name(name)
    return {
        "name": name.strip() or "Event",
        "datetime_utc": dt_utc.isoformat(),
        "datetime_wib": dt_wib.isoformat(),
        "impact": imp,
        "country": "US",
        "previous": "—",
        "forecast": "—",
        "source": source,
    }


def _parse_investing_html(html: str, source: str) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        for tr in soup.select("tr[data-event-datetime]"):
            try:
                ts_ms = int(tr.get("data-event-datetime") or 0)
            except (TypeError, ValueError):
                continue
            if ts_ms <= 0:
                continue
            dt_utc = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
            a = tr.select_one("td a, a[data-event-datetime]")
            name = ""
            if a:
                name = a.get_text(strip=True)
            if not name:
                tds = tr.find_all("td")
                if len(tds) >= 4:
                    name = tds[3].get_text(strip=True)
            if not name:
                continue
            events.append(_dt_to_event_dict(dt_utc, name, source, impact="HIGH"))
    except ImportError:
        for m in re.finditer(
            r'data-event-datetime="(\d+)"[^>]*>.*?<td[^>]*>.*?</td>.*?<td[^>]*>.*?</td>.*?<td[^>]*>.*?</td>.*?<td[^>]*>(?:<a[^>]*>)?([^<]+)',
            html,
            re.DOTALL | re.IGNORECASE,
        ):
            try:
                ts_ms = int(m.group(1))
                name = re.sub(r"\s+", " ", m.group(2)).strip()
            except (IndexError, ValueError):
                continue
            if not name or not _is_high_name(name):
                continue
            dt_utc = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
            events.append(_dt_to_event_dict(dt_utc, name, f"{source}_regex", impact="HIGH"))

    return events


def _fetch_via_json_endpoint(days_ahead: int) -> list[dict[str, str]]:
    today = datetime.now(timezone.utc)
    end_date = today + timedelta(days=max(1, days_ahead))
    url = "https://www.investing.com/economic-calendar/Service/getCalendarFilteredData"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Referer": "https://www.investing.com/economic-calendar/",
        "Origin": "https://www.investing.com",
    }
    payload = {
        "dateFrom": today.strftime("%Y-%m-%d"),
        "dateTo": end_date.strftime("%Y-%m-%d"),
        "country[]": "5",
        "importance[]": "3",
        "timeZone": "8",
        "limit_from": "0",
    }
    resp = requests.post(url, headers=headers, data=payload, timeout=20)
    if resp.status_code == 403:
        logger.warning("Investing.com calendar returned 403 — fallback elsewhere")
        return []
    if resp.status_code == 429:
        logger.warning("Investing.com calendar returned 429 — rate limited")
        return []
    if resp.status_code != 200:
        logger.warning("Investing.com calendar HTTP %s", resp.status_code)
        return []

    try:
        data = resp.json()
    except json.JSONDecodeError:
        return _parse_investing_html(resp.text, "investing_com_raw")

    html_fragment = data.get("data")
    if isinstance(html_fragment, str) and html_fragment.strip():
        return _parse_investing_html(html_fragment, "investing_com")

    if isinstance(data, list):
        out: list[dict[str, str]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            name = str(item.get("event") or item.get("name") or item.get("eventName") or "")
            raw_d = item.get("date") or item.get("datetime")
            if not raw_d:
                continue
            dt_utc = _parse_loose_datetime(raw_d)
            if not dt_utc:
                continue
            out.append(_dt_to_event_dict(dt_utc, name, "investing_com_json"))
        return out

    return []


def _parse_loose_datetime(raw: Any) -> datetime | None:
    s = str(raw).strip().replace("Z", "+00:00")
    try:
        if " " in s and "T" not in s:
            s = s.replace(" ", "T", 1)
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def fetch_investing_calendar(days_ahead: int = 7) -> list[dict[str, str]]:
    """
    Ambil event US (prioritas high-impact) dari Investing.com.
    Rate limit: minimal ``MIN_FETCH_INTERVAL`` detik antar request HTTP.
    """
    global _last_http_at
    now = time.time()

    if _cache.get("data") and (now - float(_cache.get("fetched_at", 0))) < CACHE_TTL:
        return list(_cache["data"])

    if _last_http_at > 0 and (now - _last_http_at) < MIN_FETCH_INTERVAL:
        return list(_cache.get("data") or [])

    events: list[dict[str, str]] = []
    try:
        _last_http_at = now
        events = _fetch_via_json_endpoint(days_ahead)
    except requests.RequestException as e:
        logger.warning("Investing.com request failed: %s", e)
    except Exception as e:
        logger.warning("Investing.com calendar error: %s", e)

    dedup: dict[tuple[str, str], dict[str, str]] = {}
    for e in events:
        if e.get("country") != "US":
            continue
        k = (str(e.get("name")), str(e.get("datetime_utc")))
        dedup[k] = e

    out = sorted(dedup.values(), key=lambda x: x.get("datetime_utc", ""))
    if out:
        _cache["data"] = out
        _cache["fetched_at"] = now
        logger.info("Investing.com: %s events (cached %ss)", len(out), CACHE_TTL)
    return out
