"""Feed berita real-time via RSS (pengganti NewsAPI, 9 Okt 2026).

NewsAPI paket gratis menahan artikel 24 jam, sedangkan Aliza hanya memakai
berita ≤3 jam → selama ini selalu 0 artikel. RSS media berikut gratis & real-time.
Output memakai format lama: {title, snippet, source, link, time(ISO Z)}.
"""
from __future__ import annotations

import html
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)

CRYPTO_FEEDS = {
    "Cointelegraph": "https://cointelegraph.com/rss",
    "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "The Block": "https://www.theblock.co/rss.xml",
    "Decrypt": "https://decrypt.co/feed",
}
MACRO_FEEDS = {
    "CNBC Economy": "https://www.cnbc.com/id/20910258/device/rss/rss.html",
    "CNBC Finance": "https://www.cnbc.com/id/10000664/device/rss/rss.html",
    "Federal Reserve": "https://www.federalreserve.gov/feeds/press_all.xml",
    "MarketWatch": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
}
MACRO_KEYWORDS = re.compile(
    r"\b(fed|fomc|powell|interest rates?|rate (cut|cuts|hike|hikes|decision)|inflation|"
    r"cpi|pce|payrolls?|jobs report|nonfarm|unemployment|treasury|yields?|tariffs?|"
    r"recession|gdp|central bank)\b",
    re.I,
)
_TAG = re.compile(r"<[^>]+>")


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAG.sub(" ", text or ""))).strip()


def _parse_time(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError, IndexError):
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_rss(content: bytes, source: str) -> list[dict[str, Any]]:
    out = []
    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        logger.warning("news_feed: XML %s tidak valid: %s", source, e)
        return out
    for it in root.findall(".//item"):
        title = _clean(it.findtext("title") or "")
        dt = _parse_time(it.findtext("pubDate") or it.findtext("{http://purl.org/dc/elements/1.1/}date") or "")
        if not title or dt is None:
            continue
        out.append({
            "title": title,
            "snippet": _clean(it.findtext("description") or "")[:300],
            "source": source,
            "link": (it.findtext("link") or "").strip(),
            "time": dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
    return out


def _fetch_feed(source: str, url: str) -> list[dict[str, Any]]:
    try:
        r = httpx.get(url, headers={"User-Agent": "Mozilla/5.0 (AlizaAI)"}, timeout=8.0, follow_redirects=True)
        if r.status_code != 200:
            logger.warning("news_feed: %s HTTP %s", source, r.status_code)
            return []
        return parse_rss(r.content, source)
    except Exception as e:  # noqa: BLE001
        logger.warning("news_feed: %s gagal: %s", source, e)
        return []


def collect(feeds: dict[str, str], *, max_age_hours: float, limit: int,
            keyword_filter: re.Pattern | None = None, fetch=_fetch_feed) -> list[dict[str, Any]]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    items, seen = [], set()
    for source, url in feeds.items():
        for it in fetch(source, url):
            if _parse_time(it["time"]) < cutoff:
                continue
            if keyword_filter is not None and not keyword_filter.search(it["title"]):
                continue
            key = re.sub(r"[^a-z0-9]", "", it["title"].lower())[:80]
            if key in seen:
                continue
            seen.add(key)
            items.append(it)
    items.sort(key=lambda x: x["time"], reverse=True)
    return items[:limit]


def fetch_crypto_news(max_age_hours: float = 12, limit: int = 10) -> list[dict[str, Any]]:
    return collect(CRYPTO_FEEDS, max_age_hours=max_age_hours, limit=limit)


def fetch_macro_news(max_age_hours: float = 24, limit: int = 5) -> list[dict[str, Any]]:
    return collect(MACRO_FEEDS, max_age_hours=max_age_hours, limit=limit, keyword_filter=MACRO_KEYWORDS)
