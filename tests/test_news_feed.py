"""Feed berita RSS (pengganti NewsAPI yang tertunda 24 jam)."""
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

from engine.market import news_feed as nf


def _rss(items):
    body = "".join(
        f"<item><title>{t}</title><description><![CDATA[<p>{d}</p>]]></description>"
        f"<link>https://x/{i}</link><pubDate>{format_datetime(p)}</pubDate></item>"
        for i, (t, d, p) in enumerate(items)
    )
    return f"<?xml version='1.0'?><rss><channel>{body}</channel></rss>".encode()


def test_parse_rss_cleans_html_and_formats_time():
    now = datetime(2026, 10, 9, 8, 0, tzinfo=timezone.utc)
    out = nf.parse_rss(_rss([("Bitcoin &amp; ETF outflows", "ETF <b>flows</b> turun", now)]), "Src")
    assert out == [{"title": "Bitcoin & ETF outflows", "snippet": "ETF flows turun", "source": "Src",
                    "link": "https://x/0", "time": "2026-10-09T08:00:00Z"}]


def test_collect_filters_age_keyword_dedup_and_sorts_newest_first():
    now = datetime.now(timezone.utc)
    feeds = {
        "A": [("Fed holds rates", "", now - timedelta(hours=1)), ("Old Fed news", "", now - timedelta(hours=30))],
        "B": [("Fed holds rates!", "", now - timedelta(hours=2)), ("Celebrity gossip", "", now),
              ("CPI hotter than expected", "", now - timedelta(minutes=10))],
    }
    fetch = lambda source, url: nf.parse_rss(_rss(feeds[source]), source)
    out = nf.collect({"A": "u", "B": "u"}, max_age_hours=24, limit=10,
                     keyword_filter=nf.MACRO_KEYWORDS, fetch=fetch)
    assert [o["title"] for o in out] == ["CPI hotter than expected", "Fed holds rates"]


def test_breaking_job_time_format_compatible():
    t = nf.parse_rss(_rss([("x", "", datetime.now(timezone.utc))]), "S")[0]["time"]
    parsed = datetime.fromisoformat(t.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
