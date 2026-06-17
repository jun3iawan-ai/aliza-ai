"""
Economic calendar engine for US macro events (HIGH/MEDIUM impact).
"""

from __future__ import annotations

import calendar
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Cache hasil gabungan (FMP / rule-based + merge) — max ~1 API call/jam untuk FMP
CALENDAR_CACHE_SECONDS = int(os.getenv("ECONOMIC_CALENDAR_CACHE_SEC", "3600"))
TIMEOUT = 20
WIB = timezone(timedelta(hours=7))

_fmp_calendar_cache: dict[str, Any] = {"ts": 0.0, "days": 0, "events": None}

HIGH_IMPACT = [
    "CPI",
    "Core CPI",
    "PCE",
    "Core PCE",
    "NFP",
    "Non-Farm Payroll",
    "Fed Rate",
    "FOMC",
    "Fed Decision",
    "Interest Rate Decision",
]
MEDIUM_IMPACT = [
    "PPI",
    "GDP",
    "Unemployment Rate",
    "Retail Sales",
    "ISM Manufacturing",
    "Consumer Confidence",
    "Initial Jobless Claims",
]

_events_cache: dict[str, Any] = {"ts": 0.0, "days": 0, "events": []}

# Approximate 2026 FOMC decision schedule (UTC 18:00).
_FOMC_DATES_UTC_2026 = [
    "2026-01-28T18:00:00+00:00",
    "2026-03-18T18:00:00+00:00",
    "2026-04-29T18:00:00+00:00",
    "2026-06-17T18:00:00+00:00",
    "2026-07-29T18:00:00+00:00",
    "2026-09-16T18:00:00+00:00",
    "2026-10-28T18:00:00+00:00",
    "2026-12-09T18:00:00+00:00",
]


def _to_wib(dt_utc: datetime) -> datetime:
    return dt_utc.astimezone(WIB)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _impact_level(name: str) -> str | None:
    if name in HIGH_IMPACT:
        return "HIGH"
    if name in MEDIUM_IMPACT:
        return "MEDIUM"
    return None


def _make_event(
    name: str,
    dt_utc: datetime,
    impact: str,
    previous: str = "—",
    forecast: str = "—",
) -> dict[str, str]:
    dt_wib = _to_wib(dt_utc)
    return {
        "name": name,
        "datetime_utc": _iso(dt_utc),
        "datetime_wib": _iso(dt_wib),
        "impact": impact,
        "country": "US",
        "previous": previous,
        "forecast": forecast,
    }


def _month_weekday_occurrence(year: int, month: int, weekday: int, occurrence: int) -> int | None:
    weeks = calendar.monthcalendar(year, month)
    found = [w[weekday] for w in weeks if w[weekday] != 0]
    if len(found) < occurrence:
        return None
    return found[occurrence - 1]


def _last_weekday_of_month(year: int, month: int, weekday: int) -> int:
    weeks = calendar.monthcalendar(year, month)
    for week in reversed(weeks):
        if week[weekday] != 0:
            return week[weekday]
    return 1


def _generate_rule_events(days_ahead: int) -> list[dict[str, str]]:
    now_utc = datetime.now(timezone.utc)
    end_utc = now_utc + timedelta(days=max(1, days_ahead))
    events: list[dict[str, str]] = []

    for i in range(max(1, days_ahead) + 1):
        d = (now_utc + timedelta(days=i)).date()
        year, month, day = d.year, d.month, d.day
        weekday = d.weekday()  # Mon=0

        # Weekly claim data, usually Thu 12:30 UTC.
        if weekday == 3:
            events.append(
                _make_event(
                    "Initial Jobless Claims",
                    datetime(year, month, day, 12, 30, tzinfo=timezone.utc),
                    "MEDIUM",
                )
            )

        # NFP + unemployment, first Friday 12:30 UTC.
        first_friday = _month_weekday_occurrence(year, month, weekday=4, occurrence=1)
        if first_friday and day == first_friday:
            dt = datetime(year, month, day, 12, 30, tzinfo=timezone.utc)
            events.append(_make_event("NFP", dt, "HIGH"))
            events.append(_make_event("Unemployment Rate", dt, "MEDIUM"))

        # CPI/PPI around second week.
        second_wed = _month_weekday_occurrence(year, month, weekday=2, occurrence=2)
        second_thu = _month_weekday_occurrence(year, month, weekday=3, occurrence=2)
        if second_wed and day == second_wed:
            events.append(
                _make_event("CPI", datetime(year, month, day, 12, 30, tzinfo=timezone.utc), "HIGH")
            )
            events.append(
                _make_event("Core CPI", datetime(year, month, day, 12, 30, tzinfo=timezone.utc), "HIGH")
            )
        if second_thu and day == second_thu:
            events.append(
                _make_event("PPI", datetime(year, month, day, 12, 30, tzinfo=timezone.utc), "MEDIUM")
            )

        # Retail Sales around middle month.
        if day == 15:
            events.append(
                _make_event("Retail Sales", datetime(year, month, day, 12, 30, tzinfo=timezone.utc), "MEDIUM")
            )

        # ISM Manufacturing near first business day.
        if day in (1, 2, 3):
            events.append(
                _make_event(
                    "ISM Manufacturing",
                    datetime(year, month, day, 14, 0, tzinfo=timezone.utc),
                    "MEDIUM",
                )
            )

        # Consumer confidence around end of month.
        if day >= 25 and weekday == 1:
            events.append(
                _make_event(
                    "Consumer Confidence",
                    datetime(year, month, day, 14, 0, tzinfo=timezone.utc),
                    "MEDIUM",
                )
            )

        # GDP and PCE around month-end.
        if day == _last_weekday_of_month(year, month, weekday=3):
            events.append(_make_event("GDP", datetime(year, month, day, 12, 30, tzinfo=timezone.utc), "MEDIUM"))
            events.append(_make_event("PCE", datetime(year, month, day, 12, 30, tzinfo=timezone.utc), "HIGH"))
            events.append(_make_event("Core PCE", datetime(year, month, day, 12, 30, tzinfo=timezone.utc), "HIGH"))

    for raw in _FOMC_DATES_UTC_2026:
        dt = datetime.fromisoformat(raw)
        if now_utc <= dt <= end_utc:
            events.append(_make_event("FOMC / Fed Rate Decision", dt, "HIGH"))

    dedup: dict[tuple[str, str], dict[str, str]] = {}
    for e in events:
        dt = datetime.fromisoformat(e["datetime_utc"])
        if dt < now_utc or dt > end_utc:
            continue
        dedup[(e["name"], e["datetime_utc"])] = e
    return sorted(dedup.values(), key=lambda x: x["datetime_utc"])


def _classify_fmp_event_impact(event_name: str) -> str | None:
    """Tentukan HIGH/MEDIUM dari nama event FMP."""
    n = (event_name or "").strip()
    if not n:
        return None
    nl = n.lower()
    for h in HIGH_IMPACT:
        if h.lower() in nl:
            return "HIGH"
    for m in MEDIUM_IMPACT:
        if m.lower() in nl:
            return "MEDIUM"
    if any(k in nl for k in ("fomc", "fed rate", "interest rate decision", "powell")):
        return "HIGH"
    return None


def _parse_fmp_datetime(raw_date: Any) -> datetime | None:
    if raw_date is None:
        return None
    s = str(raw_date).strip().replace("Z", "+00:00")
    try:
        if "T" in s or re.match(r"^\d{4}-\d{2}-\d{2} ", s):
            dt = datetime.fromisoformat(s.replace(" ", "T", 1) if " " in s and "T" not in s else s)
        else:
            dt = datetime.fromisoformat(s[:10] + "T12:30:00")
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _fetch_from_fmp(days_ahead: int, api_key: str) -> list[dict[str, str]]:
    """Ambil kalender ekonomi US dari Financial Modeling Prep (perlu FMP_API_KEY)."""
    now_utc = datetime.now(timezone.utc)
    end_utc = now_utc + timedelta(days=max(1, days_ahead))
    from_str = now_utc.strftime("%Y-%m-%d")
    to_str = end_utc.strftime("%Y-%m-%d")
    url = (
        "https://financialmodelingprep.com/api/v3/economic_calendar"
        f"?from={from_str}&to={to_str}&apikey={api_key}"
    )
    try:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
            resp = client.get(url)
        if resp.status_code != 200:
            logger.warning("economic_calendar: FMP HTTP %s", resp.status_code)
            return []
        data = resp.json()
    except Exception as e:  # noqa: BLE001
        logger.warning("economic_calendar: FMP fetch failed: %s", e)
        return []
    if not isinstance(data, list):
        return []
    out: list[dict[str, str]] = []
    for item in data:
        country = str(item.get("country") or "").upper()
        if country not in ("US", "USA"):
            continue
        event_name = str(item.get("event") or item.get("eventName") or "").strip()
        impact = _classify_fmp_event_impact(event_name)
        if not impact:
            continue
        raw_d = item.get("date") or item.get("releaseDate") or item.get("time")
        dt_utc = _parse_fmp_datetime(raw_d)
        if not dt_utc:
            continue
        prev = item.get("previous")
        fore = item.get("estimate") or item.get("forecast")
        out.append(
            _make_event(
                event_name,
                dt_utc,
                impact,
                previous=str(prev) if prev is not None else "—",
                forecast=str(fore) if fore is not None else "—",
            )
        )
    if out:
        logger.info("economic_calendar: FMP returned %s US HIGH/MEDIUM rows", len(out))
    return out


def _merge_fomc_events(events: list[dict[str, str]], days_ahead: int) -> list[dict[str, str]]:
    """Tambahkan FOMC hardcoded jika belum ada di hasil API (safety net)."""
    now_utc = datetime.now(timezone.utc)
    end_utc = now_utc + timedelta(days=max(1, days_ahead))
    covered_dates: set[str] = set()
    for e in events:
        nl = str(e.get("name", "")).lower()
        if any(x in nl for x in ("fomc", "fed decision", "fed rate")):
            covered_dates.add(str(e.get("datetime_utc", ""))[:10])
    out = list(events)
    for raw in _FOMC_DATES_UTC_2026:
        dt = datetime.fromisoformat(raw)
        if not (now_utc <= dt <= end_utc):
            continue
        dkey = dt.strftime("%Y-%m-%d")
        if dkey in covered_dates:
            continue
        out.append(_make_event("Fed Decision", dt, "HIGH"))
        out.append(_make_event("Fed Rate", dt, "HIGH"))
        out.append(_make_event("FOMC", dt, "HIGH"))
    return out


def _parse_serper_datetime(text: str, now_utc: datetime) -> datetime | None:
    # Format ISO: 2026-04-17
    m = re.search(r"(20\d{2})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?", text)
    if m:
        year = int(m.group(1))
        month = int(m.group(2))
        day = int(m.group(3))
        hour = int(m.group(4) or 12)
        minute = int(m.group(5) or 30)
        return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
    # Format natural: "April 17, 2026" atau "April 17"
    months = {"january":1,"february":2,"march":3,"april":4,"may":5,"june":6,
              "july":7,"august":8,"september":9,"october":10,"november":11,"december":12}
    m2 = re.search(r"(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})(?:,?\s*(20\d{2}))?", text, re.IGNORECASE)
    if m2:
        month = months[m2.group(1).lower()]
        day = int(m2.group(2))
        year = int(m2.group(3)) if m2.group(3) else now_utc.year
        try:
            return datetime(year, month, day, 12, 30, tzinfo=timezone.utc)
        except ValueError:
            pass
    # Format: "Apr 17" atau "Apr 17, 2026"
    short_months = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
                    "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}
    m3 = re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\.?\s+(\d{1,2})(?:,?\s*(20\d{2}))?", text, re.IGNORECASE)
    if m3:
        month = short_months[m3.group(1).lower()[:3]]
        day = int(m3.group(2))
        year = int(m3.group(3)) if m3.group(3) else now_utc.year
        try:
            return datetime(year, month, day, 12, 30, tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def _fetch_serper_events(days_ahead: int) -> list[dict[str, str]]:
    api_key = os.getenv("SERPER_API_KEY")
    if not api_key:
        return []

    now_utc = datetime.now(timezone.utc)
    query = (
        f"US economic calendar next {days_ahead} days CPI PCE NFP FOMC "
        "Fed Decision GDP PPI Unemployment Rate Retail Sales ISM Manufacturing "
        "Consumer Confidence Initial Jobless Claims"
    )
    try:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
            resp = client.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                content=json.dumps({"q": query, "num": 20}),
            )
        if resp.status_code != 200:
            logger.warning("economic_calendar: Serper HTTP %s", resp.status_code)
            return []
        payload = resp.json()
    except Exception as e:  # noqa: BLE001
        logger.warning("economic_calendar: Serper fetch failed: %s", e)
        return []

    rows = (payload.get("organic") or []) if isinstance(payload, dict) else []
    out: list[dict[str, str]] = []
    for row in rows:
        text = " ".join(
            [
                str(row.get("title", "")),
                str(row.get("snippet", "")),
            ]
        )
        dt = _parse_serper_datetime(text, now_utc)
        if not dt:
            continue
        for name in HIGH_IMPACT + MEDIUM_IMPACT:
            if name.lower() in text.lower():
                impact = _impact_level(name)
                if not impact:
                    continue
                out.append(_make_event(name, dt, impact))
                break
    return out


def get_upcoming_events(days_ahead: int = 2) -> list[dict[str, str]]:
    """
    Ambil event ekonomi US HIGH/MEDIUM impact untuk N hari ke depan.

    Urutan: FMP (jika ``FMP_API_KEY``) → Investing.com (cadangan) → rule-based;
    lalu merge FOMC hardcoded bila sumber bukan rule-based; + Serper opsional.
    Cache hasil gabungan ~1 jam.
    """
    now = time.time()
    days = max(1, int(days_ahead))
    try:
        if (
            float(_fmp_calendar_cache.get("ts", 0)) > 0
            and _fmp_calendar_cache.get("events") is not None
            and now - float(_fmp_calendar_cache["ts"]) < CALENDAR_CACHE_SECONDS
            and int(_fmp_calendar_cache.get("days", 0)) >= days
        ):
            return list(_fmp_calendar_cache["events"])

        events: list[dict[str, str]] = []
        source_used = "none"
        fmp_key = (os.getenv("FMP_API_KEY") or "").strip()
        if fmp_key:
            events = _fetch_from_fmp(days, fmp_key)
            if events:
                source_used = "fmp"

        if not events:
            try:
                from engine.market.investing_calendar import fetch_investing_calendar

                events = fetch_investing_calendar(days)
                if events:
                    source_used = "investing_com"
            except ImportError:
                logger.debug("economic_calendar: investing_calendar not available")
            except Exception as e:
                logger.warning("economic_calendar: Investing.com failed: %s", e)

        if not events:
            events = _generate_rule_events(days)
            source_used = "rule_based"
            logger.info("economic_calendar: using rule-based calendar (FMP/Investing empty)")
        else:
            events = _merge_fomc_events(events, days)

        events.extend(_fetch_serper_events(days))

        dedup: dict[tuple[str, str], dict[str, str]] = {}
        for e in events:
            if e.get("country") != "US":
                continue
            if e.get("impact") not in {"HIGH", "MEDIUM"}:
                continue
            dedup[(str(e.get("name")), str(e.get("datetime_utc")))] = e

        merged = sorted(dedup.values(), key=lambda x: x["datetime_utc"])
        logger.info(
            "economic_calendar: source=%s, merged_events=%s",
            source_used,
            len(merged),
        )
        _fmp_calendar_cache["ts"] = now
        _fmp_calendar_cache["days"] = days
        _fmp_calendar_cache["events"] = merged
        _events_cache["ts"] = now
        _events_cache["days"] = days
        _events_cache["events"] = merged
        return merged
    except Exception as e:  # noqa: BLE001
        logger.warning("economic_calendar: get_upcoming_events failed: %s", e)
        return []


def get_events_tomorrow() -> list[dict[str, str]]:
    """Event untuk tanggal besok berdasarkan zona WIB."""
    try:
        now_wib = datetime.now(WIB)
        tomorrow = (now_wib + timedelta(days=1)).date()
        events = get_upcoming_events(days_ahead=2)
        out = []
        for e in events:
            dt_wib = datetime.fromisoformat(e["datetime_wib"])
            if dt_wib.date() == tomorrow:
                out.append(e)
        return sorted(out, key=lambda x: x["datetime_wib"])
    except Exception as e:  # noqa: BLE001
        logger.warning("economic_calendar: get_events_tomorrow failed: %s", e)
        return []


def get_events_next_hour() -> list[dict[str, str]]:
    """Event yang akan terjadi dalam 60 menit ke depan (berdasarkan WIB)."""
    try:
        now_wib = datetime.now(WIB)
        limit_wib = now_wib + timedelta(hours=1)
        events = get_upcoming_events(days_ahead=2)
        out = []
        for e in events:
            dt_wib = datetime.fromisoformat(e["datetime_wib"])
            if now_wib <= dt_wib <= limit_wib:
                out.append(e)
        return sorted(out, key=lambda x: x["datetime_wib"])
    except Exception as e:  # noqa: BLE001
        logger.warning("economic_calendar: get_events_next_hour failed: %s", e)
        return []
