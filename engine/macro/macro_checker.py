"""
Reusable macro event checks for the signal pipeline.

Uses `engine.market.economic_calendar`, which already chains real-time sources
before falling back to the rule-based schedule: FMP (Financial Modeling Prep,
currently disabled via FMP_CALENDAR_ENABLED=false — the configured
FMP_API_KEY has been returning HTTP 403; see BERITA_MITIGASI_REPORT.md) →
Investing.com scrape (currently also failing, HTTP 403) → rule-based schedule
(NFP/CPI/FOMC/etc. approximated from typical release-day patterns) → Serper
search as best-effort enrichment on top. Does not import Telegram or bot code.

get_upcoming_events() fails open: any exception is caught internally and it
returns [] rather than raising, so a total fetch failure looks identical to
"genuinely no events" to callers (is_macro_safe_to_trade, breaking/calendar
alerts). Re-enable FMP once FMP_API_KEY is refreshed; re-check Investing.com
if its scrape starts working again.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def _parse_event_utc(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        s = str(raw).strip().replace("Z", "+00:00")
        return datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def get_upcoming_high_impact_events(window_hours: int = 24) -> list[dict[str, Any]]:
    """
    Return HIGH-impact US macro events within the next `window_hours` hours.

    Each item:
        event, timestamp (ISO UTC), impact ('high'), hours_until, currency
    """
    try:
        from engine.market.economic_calendar import get_upcoming_events

        days = max(2, (int(window_hours) + 23) // 24 + 1)
        raw = get_upcoming_events(days_ahead=days)
    except Exception as e:
        logger.warning("macro_checker: calendar fetch failed: %s", e)
        return []

    now = datetime.now(timezone.utc)
    out: list[dict[str, Any]] = []
    for e in raw or []:
        if str(e.get("impact", "")).upper() != "HIGH":
            continue
        dt = _parse_event_utc(e.get("datetime_utc"))
        if not dt:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        hours_until = (dt - now).total_seconds() / 3600.0
        if hours_until < 0:
            continue
        if hours_until > float(window_hours):
            continue
        cc = e.get("country") or "US"
        cur = "USD" if str(cc).upper() in ("US", "USA") else str(cc)
        out.append(
            {
                "event": str(e.get("name") or "—"),
                "timestamp": str(e.get("datetime_utc") or ""),
                "impact": "high",
                "hours_until": round(hours_until, 2),
                "currency": cur,
            }
        )
    out.sort(key=lambda x: float(x.get("hours_until", 0.0)))
    return out


def is_macro_safe_to_trade(window_hours: int = 4) -> tuple[bool, list[dict[str, Any]]]:
    """
    True if there is no HIGH-impact event in the next `window_hours` hours.
    If False, returns the list of blocking events (same shape as get_upcoming_high_impact_events).
    """
    blocking = get_upcoming_high_impact_events(window_hours=max(1, int(window_hours)))
    return (len(blocking) == 0, blocking)
