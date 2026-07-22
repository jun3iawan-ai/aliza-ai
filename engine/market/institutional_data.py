"""
Institutional data sources for the evening/morning brief "INSTITUTIONAL" section
(interfaces/telegram_bot.py:_get_institutional_data): Bitcoin spot ETF flow,
aggregated futures liquidation volume, and BTC exchange netflow.

Replaces the previous "proxy via berita" approach (Serper news-search snippet
regex parsing, unreliable -- almost always N/A) with real API/scraping sources,
following the fail-open-but-honest pattern from engine/market/economic_calendar.py:
if a fetch fails, callers get a clear status ("not_configured" vs "fetch_failed")
and message, never silently-stale or fabricated data.

CORRECTION (see INSTITUTIONAL_DATA_REPORT.md, revision section): CoinGlass does
NOT have a free tier -- verified directly against coinglass.com/pricing, cheapest
plan ("Hobbyist") is $29/mo. The original version of this module wrongly assumed
Hobbyist was free (a checkmark in docs.coinglass.com's endpoint-availability table
was misread as "free tier has this endpoint" rather than "this endpoint requires
at least the paid Hobbyist plan"). CoinGlass is kept only as an optional,
paid-tier path for Liquidation (harmless no-op until/unless the user pays for a
plan); it is no longer used for ETF flow at all.

Sources:
  - ETF flow: SoSoValue Demo API (`SOSOVALUE_API_KEY`, primary -- genuinely free
    tier per sosovalue.com/developer FAQ, endpoint verified directly against
    sosovalue-1.gitbook.io/sosovalue-api-doc AND against the live endpoint
    itself, see _fetch_sosovalue_etf_flow docstring) -> Farside Investors
    scraping (farside.co.uk/btc/, fallback, no key needed). NOTE on Farside:
    `curl` and Claude's own WebFetch tool get HTTP 403 (Cloudflare managed
    challenge) against this site, but this module's actual HTTP client
    (Python `requests`) gets a clean HTTP 200 with the real data table every
    time (tested repeatedly) -- almost certainly because Cloudflare's bot
    check here keys off TLS/HTTP client fingerprinting rather than IP
    reputation, and `requests`' fingerprint isn't flagged the way curl's is.
    The scraper/parser has been validated against this real, live response
    (see tests/fixtures/farside_real_success.html) and produces correct
    numbers -- this fallback is confirmed working, not just theoretical.
    Kept the Cloudflare-challenge detector in the fetch path anyway (see
    `_is_cloudflare_challenge`) as a defensive check in case Cloudflare's
    fingerprinting heuristic changes in the future and starts blocking
    `requests` too.
  - Liquidation: CoinGlass aggregated long/short liquidation volume (24h) --
    requires a PAID CoinGlass plan now (see correction above); stays
    "not_configured" (honest gap, not a bug) unless the user decides to pay for
    it. Binance's public REST liquidation-history endpoint
    (`/fapi/v1/allForceOrders`) was checked and confirmed dead
    (`{"code":400,"msg":"The endpoint has been out of maintenance"}`); the only
    remaining Binance option is the `!forceOrder@arr` WebSocket stream, which
    would require a new persistent background component (reconnect logic +
    in-memory rolling 24h aggregation) unlike every other data source in this
    module/project's REST-poll-and-cache-TTL pattern -- deliberately NOT built
    this session per the "don't force a fragile component" guidance; see report.
  - BTC exchange netflow: CoinGlass free tier does NOT cover this
    (`/api/spot/coin/netflow` is Startup-tier+, confirmed against
    docs.coinglass.com). Scraping fallback is implemented (requests + BS4, no
    headless browser) but DISABLED by default (`BTC_NETFLOW_SCRAPE_ENABLED=false`)
    because both researched candidate sites render the number via client-side
    JS (confirmed empirically -- the number isn't in the raw HTML), so the
    scraper as built will legitimately report "gagal parse" against them. See
    the report for the resource/reliability tradeoff and recommended next step.
"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any

import httpx
import requests

logger = logging.getLogger(__name__)

COINGLASS_BASE_URL = "https://open-api-v4.coinglass.com"
# Verified directly against sosovalue-1.gitbook.io/sosovalue-api-doc (base URL +
# path + params + auth header) AND against the live endpoint: an unauthenticated
# request to this base URL's /etfs/summary-history returns HTTP 401
# {"code":400101,"message":"API Key is invalid or does not exist"} -- proof the
# endpoint is real (a wrong path/base would 404, not report a bad key).
SOSOVALUE_BASE_URL = "https://openapi.sosovalue.com/openapi/v1"
# Fallback ETF flow source, no API key needed. `curl` gets HTTP 403 (Cloudflare
# managed challenge, "cf-mitigated: challenge") against this site, but Python
# `requests` -- what this module actually uses -- gets a clean HTTP 200 with
# the real data table (tested repeatedly). Validated end-to-end against a real
# captured response (tests/fixtures/farside_real_success.html); see
# _fetch_farside_etf_flow docstring for detail.
FARSIDE_URL = "https://farside.co.uk/btc/"

TIMEOUT = 15.0

ETF_FLOW_CACHE_SEC = int(os.getenv("ETF_FLOW_CACHE_SEC", "3600"))
LIQUIDATION_CACHE_SEC = int(os.getenv("LIQUIDATION_CACHE_SEC", "1800"))
BTC_NETFLOW_CACHE_SEC = int(os.getenv("BTC_NETFLOW_CACHE_SEC", "3600"))

# Candidate scraping target researched for BTC_NETFLOW_SCRAPE_ENABLED=true.
# Confirmed via plain `requests` (no JS) that the netflow number is NOT present
# in the raw HTML -- the page ships only a skeleton-loader placeholder
# (`id="s-exchange-flow"`) and fills it in client-side. The scraper below is
# still implemented and tested against both a synthetic "value present" HTML
# fixture and the real captured (JS-required) HTML, so it's ready to work
# immediately if the site (or a replacement target) ever ships the number
# server-rendered -- but it will legitimately report "gagal parse" against the
# site as it exists today. See INSTITUTIONAL_DATA_REPORT.md.
BTC_NETFLOW_SCRAPE_URL = "https://btcdash.org"
BTC_NETFLOW_SCRAPE_ELEMENT_ID = "s-exchange-flow"

_etf_cache: dict[str, Any] = {"ts": 0.0, "data": None}
_liq_cache: dict[str, Any] = {"ts": 0.0, "data": None}
_netflow_cache: dict[str, Any] = {"ts": 0.0, "data": None}


def reset_cache_for_tests() -> None:
    """Test-only: clear in-memory caches so tests don't leak into each other."""
    _etf_cache["ts"] = 0.0
    _etf_cache["data"] = None
    _liq_cache["ts"] = 0.0
    _liq_cache["data"] = None
    _netflow_cache["ts"] = 0.0
    _netflow_cache["data"] = None


def _coinglass_api_key() -> str:
    return (os.getenv("COINGLASS_API_KEY") or "").strip()


def _sosovalue_api_key() -> str:
    return (os.getenv("SOSOVALUE_API_KEY") or "").strip()


def _btc_netflow_scrape_enabled() -> bool:
    return (os.getenv("BTC_NETFLOW_SCRAPE_ENABLED", "false") or "").strip().lower() == "true"


# ---------------------------------------------------------------------------
# ETF flow -- SoSoValue Demo API primary (genuinely free), Farside Investors
# scraping fallback (no key, but currently Cloudflare-blocked -- see below).
# CoinGlass dropped entirely from this path: it has no free tier (verified
# against coinglass.com/pricing, cheapest plan is $29/mo).
# ---------------------------------------------------------------------------


def _fetch_sosovalue_etf_flow() -> tuple[dict | None, str | None]:
    """GET /etfs/summary-history?symbol=BTC&country_code=US -- verified
    directly against sosovalue-1.gitbook.io/sosovalue-api-doc (base URL, path,
    param names, auth header) and against the live endpoint itself: an
    unauthenticated request returns HTTP 401
    {"code":400101,"message":"API Key is invalid or does not exist"}, which
    confirms the path/params are accepted by the real API (a wrong path would
    404, not complain about the key). Response is a list of dicts with fields
    `date` (YYYY-MM-DD), `total_net_inflow` (raw USD, whole-market aggregate --
    no per-fund breakdown at this endpoint), `total_value_traded`,
    `total_net_assets`, `cum_net_inflow`. Sorted explicitly by date here rather
    than trusted to arrive in a particular order, since the docs don't specify
    a guaranteed sort order."""
    key = _sosovalue_api_key()
    if not key:
        return None, "SOSOVALUE_API_KEY belum dikonfigurasi"
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.get(
                f"{SOSOVALUE_BASE_URL}/etfs/summary-history",
                headers={"x-soso-api-key": key},
                params={"symbol": "BTC", "country_code": "US", "limit": 10},
            )
    except Exception as e:  # noqa: BLE001
        return None, f"SoSoValue ETF flow request error: {e}"
    if resp.status_code == 429:
        return None, "SoSoValue ETF flow: rate limited (HTTP 429)"
    if resp.status_code != 200:
        return None, f"SoSoValue ETF flow HTTP {resp.status_code}"
    try:
        payload = resp.json()
    except Exception:  # noqa: BLE001
        return None, "SoSoValue ETF flow: response bukan JSON valid"
    if not isinstance(payload, list) or not payload:
        return None, "SoSoValue ETF flow: data kosong"
    try:
        rows_sorted = sorted(payload, key=lambda r: r.get("date", ""))
        latest = rows_sorted[-1]
        today_m = round(float(latest.get("total_net_inflow", 0)) / 1_000_000, 2)
        last_7 = rows_sorted[-7:]
        cum_7d_m = round(
            sum(float(r.get("total_net_inflow", 0)) for r in last_7) / 1_000_000, 2
        )
    except (TypeError, ValueError) as e:
        return None, f"SoSoValue ETF flow: gagal parse angka ({e})"
    return {
        "flow_usd_today_m": today_m,
        "flow_usd_7d_m": cum_7d_m,
        "price_usd": None,
        "source": "sosovalue",
    }, None


def _is_cloudflare_challenge(status_code: int, text: str) -> bool:
    return status_code in (403, 503) and (
        "Just a moment" in text or "challenge-platform" in text or "cf-chl" in text
    )


def _parse_farside_etf_table(html: str) -> tuple[float | None, float | None, str | None]:
    """Parser for farside.co.uk/btc/'s daily BTC ETF flow table
    (`<table class="etf">`).

    VERIFIED against a real captured response
    (tests/fixtures/farside_real_success.html, fetched live via `requests`
    during this session): row 0 is a header row whose cells are blank except
    the last, which reads "Total"; per-fund ticker names live in row 1 and are
    not needed here; each daily data row starts with a "DD Mon YYYY" date and
    ends with that day's aggregate net flow in US$ millions (the same column
    index as "Total" in row 0); trailing summary rows ("Total", "Average",
    "Maximum", "Minimum" over the whole table's history) are correctly skipped
    because their first cell doesn't match the date pattern. Rows appear in
    ascending chronological order (oldest first) -- confirmed against the real
    fixture -- so the last matched date row is "today". Negative values appear
    parenthesized, e.g. "(12.3)" -- handled by the paren-to-minus-sign
    replacement below.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.warning("institutional_data: BeautifulSoup4 tidak terpasang")
        return None, None, "BeautifulSoup4 tidak terpasang"
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="etf") or soup.find("table")
    if table is None:
        return None, None, "tidak ada <table> di HTML (kemungkinan halaman blocked/challenge)"
    rows = table.find_all("tr")
    if len(rows) < 2:
        return None, None, "struktur tabel tidak dikenali (baris terlalu sedikit)"
    header_cells = [c.get_text(strip=True) for c in rows[0].find_all(["th", "td"])]
    try:
        total_idx = next(
            i for i, h in enumerate(header_cells) if h.strip().lower() == "total"
        )
    except StopIteration:
        return None, None, "kolom 'Total' tidak ditemukan di header"

    date_re = re.compile(r"^\d{1,2}\s+[A-Za-z]{3}\s+\d{4}$")

    def _row_value(tr) -> tuple[str, float] | None:
        cells = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
        if not cells or not date_re.match(cells[0]):
            return None
        if total_idx >= len(cells):
            return None
        raw = cells[total_idx].replace(",", "").replace("(", "-").replace(")", "")
        if raw in ("", "-", "—"):
            return None
        try:
            return cells[0], float(raw)
        except ValueError:
            return None

    data_rows = [r for r in (_row_value(tr) for tr in rows[1:]) if r is not None]
    if not data_rows:
        return None, None, "tidak ada baris tanggal dengan angka Total yang valid"

    today_m = data_rows[-1][1]
    cum_7d_m = round(sum(v for _, v in data_rows[-7:]), 2)
    return today_m, cum_7d_m, None


def _fetch_farside_etf_flow() -> tuple[dict | None, str | None]:
    try:
        resp = requests.get(
            FARSIDE_URL,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                )
            },
            timeout=TIMEOUT,
        )
    except requests.Timeout:
        return None, "Farside: timeout saat fetch halaman"
    except requests.RequestException as e:
        return None, f"Farside: gagal fetch halaman ({e})"
    if _is_cloudflare_challenge(resp.status_code, resp.text):
        return None, (
            "Farside: diblokir Cloudflare managed challenge (bot protection "
            "situs-lebar, bukan render-JS pada datanya) -- fallback ini tidak "
            "berfungsi dari IP VPS ini saat ini, lihat INSTITUTIONAL_DATA_REPORT.md"
        )
    if resp.status_code != 200:
        return None, f"Farside: HTTP {resp.status_code}"
    today_m, cum_7d_m, parse_err = _parse_farside_etf_table(resp.text)
    if parse_err:
        return None, f"Farside: {parse_err}"
    return {
        "flow_usd_today_m": today_m,
        "flow_usd_7d_m": cum_7d_m,
        "price_usd": None,
        "source": "farside",
    }, None


def get_etf_flow_data(now: float | None = None) -> dict[str, Any]:
    """
    Return:
      status: "ok" | "not_configured" | "fetch_failed"
      flow_usd_today_m, flow_usd_7d_m: float | None (juta USD)
      price_usd: float | None
      source: "sosovalue" | "farside" | None
      message: str | None (selalu diisi kalau status != "ok")

    SoSoValue (needs SOSOVALUE_API_KEY, free Demo tier) is tried first. Farside
    scraping needs no key at all, so it's attempted as a fallback even when
    SOSOVALUE_API_KEY is unset -- but see _fetch_farside_etf_flow: it is
    currently blocked by Cloudflare from this VPS, so in practice today it
    will not succeed either way. "not_configured" is reported only when
    SOSOVALUE_API_KEY is unset AND Farside also failed (the actionable next
    step is still "add a free SoSoValue key"); "fetch_failed" is reported when
    a key IS configured but both sources still failed.
    """
    now = time.time() if now is None else now
    if _etf_cache["data"] is not None and (now - _etf_cache["ts"]) < ETF_FLOW_CACHE_SEC:
        return _etf_cache["data"]

    soso_key_present = bool(_sosovalue_api_key())
    soso_data, soso_err = (None, None)
    if soso_key_present:
        soso_data, soso_err = _fetch_sosovalue_etf_flow()
        if soso_err:
            logger.warning("institutional_data: %s", soso_err)

    if soso_data is not None:
        result = {"status": "ok", "message": None, **soso_data}
        _etf_cache["ts"] = now
        _etf_cache["data"] = result
        return result

    farside_data, farside_err = _fetch_farside_etf_flow()
    if farside_err:
        logger.warning("institutional_data: %s", farside_err)

    if farside_data is not None:
        result = {"status": "ok", "message": None, **farside_data}
    elif not soso_key_present:
        result = {
            "status": "not_configured",
            "flow_usd_today_m": None,
            "flow_usd_7d_m": None,
            "price_usd": None,
            "source": None,
            "message": (
                "ETF Flow: SOSOVALUE_API_KEY belum dikonfigurasi (gratis, "
                "sosovalue.com/developer) -- fallback Farside juga gagal saat "
                f"ini ({farside_err or 'unknown'})"
            ),
        }
    else:
        result = {
            "status": "fetch_failed",
            "flow_usd_today_m": None,
            "flow_usd_7d_m": None,
            "price_usd": None,
            "source": None,
            "message": (
                f"ETF Flow: gagal fetch dari SoSoValue ({soso_err or 'unknown'}) "
                f"dan Farside ({farside_err or 'unknown'}) -- coba lagi siklus berikutnya"
            ),
        }
    _etf_cache["ts"] = now
    _etf_cache["data"] = result
    return result


# ---------------------------------------------------------------------------
# Liquidation volume (24h aggregated long/short) -- CoinGlass only.
# NOT price-level "zones"/heatmap -- that requires Professional-tier+ ON TOP OF
# a paid plan to begin with. CoinGlass has no free tier at all (cheapest,
# "Hobbyist", is $29/mo, verified against coinglass.com/pricing) -- so
# COINGLASS_API_KEY being unset is now the expected default (not a "sign up
# free" nudge but an optional paid upgrade), and this stays "not_configured"
# unless the user decides to pay for it. No free/keyless alternative was
# found this session: Binance's public liquidation-history REST endpoint
# (/fapi/v1/allForceOrders) is dead ("out of maintenance"), and the only
# remaining option (the !forceOrder@arr WebSocket stream) would need a new
# persistent background component foreign to this module's REST-poll pattern
# -- deliberately not built, see INSTITUTIONAL_DATA_REPORT.md.
# ---------------------------------------------------------------------------


def _fetch_coinglass_liquidation_volume() -> tuple[dict | None, str | None]:
    key = _coinglass_api_key()
    if not key:
        return None, "COINGLASS_API_KEY belum dikonfigurasi"
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.get(
                f"{COINGLASS_BASE_URL}/api/futures/liquidation/aggregated-history",
                headers={"CG-API-KEY": key},
                params={
                    "exchange_list": "Binance,OKX,Bybit",
                    "symbol": "BTC",
                    "interval": "1d",
                    "limit": 2,
                },
            )
    except Exception as e:  # noqa: BLE001
        return None, f"CoinGlass liquidation request error: {e}"
    if resp.status_code != 200:
        return None, f"CoinGlass liquidation HTTP {resp.status_code}"
    try:
        payload = resp.json()
    except Exception:  # noqa: BLE001
        return None, "CoinGlass liquidation: response bukan JSON valid"
    if not isinstance(payload, dict) or str(payload.get("code")) != "0":
        msg = payload.get("msg") if isinstance(payload, dict) else None
        return None, f"CoinGlass liquidation API error: {msg or 'unknown'}"
    rows = payload.get("data")
    if not isinstance(rows, list) or not rows:
        return None, "CoinGlass liquidation: data kosong"
    latest = rows[-1]
    try:
        long_m = round(float(latest.get("aggregated_long_liquidation_usd", 0)) / 1_000_000, 2)
        short_m = round(float(latest.get("aggregated_short_liquidation_usd", 0)) / 1_000_000, 2)
    except (TypeError, ValueError) as e:
        return None, f"CoinGlass liquidation: gagal parse angka ({e})"
    return {"long_usd_m": long_m, "short_usd_m": short_m, "source": "coinglass"}, None


def get_liquidation_volume_24h(now: float | None = None) -> dict[str, Any]:
    """
    Aggregated 24h long vs short futures liquidation volume (BTC, Binance+OKX+Bybit) --
    NOT price-level zones (see module docstring).

    Return:
      status: "ok" | "not_configured" | "fetch_failed"
      long_usd_m, short_usd_m: float | None (juta USD)
      source: "coinglass" | None
      message: str | None
    """
    now = time.time() if now is None else now
    if _liq_cache["data"] is not None and (now - _liq_cache["ts"]) < LIQUIDATION_CACHE_SEC:
        return _liq_cache["data"]

    if not _coinglass_api_key():
        result = {
            "status": "not_configured",
            "long_usd_m": None,
            "short_usd_m": None,
            "source": None,
            "message": (
                "Liquidation 24h: belum ada sumber gratis yang diimplementasikan -- "
                "endpoint publik Binance untuk data ini sudah dimatikan, dan "
                "satu-satunya API alternatif yang diriset butuh langganan berbayar "
                "yang tidak dipilih -- lihat INSTITUTIONAL_DATA_REPORT.md"
            ),
        }
        _liq_cache["ts"] = now
        _liq_cache["data"] = result
        return result

    data, err = _fetch_coinglass_liquidation_volume()
    if data is not None:
        result = {"status": "ok", "message": None, **data}
    else:
        if err:
            logger.warning("institutional_data: %s", err)
        result = {
            "status": "fetch_failed",
            "long_usd_m": None,
            "short_usd_m": None,
            "source": None,
            "message": "Liquidation 24h: gagal fetch dari CoinGlass -- coba lagi siklus berikutnya",
        }
    _liq_cache["ts"] = now
    _liq_cache["data"] = result
    return result


# ---------------------------------------------------------------------------
# BTC exchange netflow -- CoinGlass free tier doesn't cover this; scraping
# fallback, disabled by default (see module docstring + report).
# ---------------------------------------------------------------------------


def _parse_btcdash_netflow_html(html: str) -> float | None:
    """Parse angka netflow BTC dari HTML btcdash.org. Return None kalau elemen
    tidak ditemukan, atau tidak mengandung angka yang valid (mis. skeleton
    loader placeholder karena halaman butuh render JS untuk mengisi datanya) --
    TIDAK menebak/mengembalikan angka kalau tidak yakin."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.warning("institutional_data: BeautifulSoup4 tidak terpasang")
        return None
    soup = BeautifulSoup(html, "html.parser")
    el = soup.find(id=BTC_NETFLOW_SCRAPE_ELEMENT_ID)
    if el is None:
        return None
    text = el.get_text(" ", strip=True)
    m = re.search(r"([+\-−]?[\d,]+\.?\d*)\s*BTC", text, re.IGNORECASE)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "").replace("−", "-"))
    except ValueError:
        return None


def _scrape_btc_netflow() -> tuple[float | None, str | None]:
    try:
        resp = requests.get(
            BTC_NETFLOW_SCRAPE_URL,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                )
            },
            timeout=TIMEOUT,
        )
    except requests.Timeout:
        return None, "timeout saat fetch halaman scraping"
    except requests.RequestException as e:
        return None, f"gagal fetch halaman scraping: {e}"
    if resp.status_code != 200:
        return None, f"scraping HTTP {resp.status_code}"
    value = _parse_btcdash_netflow_html(resp.text)
    if value is None:
        return None, (
            "gagal parse angka netflow dari HTML (elemen tidak ditemukan atau "
            "berisi placeholder -- situs kemungkinan butuh render JS untuk "
            "mengisi datanya, lihat INSTITUTIONAL_DATA_REPORT.md)"
        )
    return value, None


def get_btc_exchange_netflow(now: float | None = None) -> dict[str, Any]:
    """
    Return:
      status: "ok" | "not_configured" | "fetch_failed"
      netflow_btc: float | None
      source: "scrape:btcdash" | None
      message: str | None

    "not_configured" di sini berarti dua hal sekaligus (lihat message): CoinGlass
    butuh langganan berbayar yang tidak dipilih, DAN scraping fallback
    dinonaktifkan default (BTC_NETFLOW_SCRAPE_ENABLED=false) karena kandidat
    situs yang diriset butuh render JS (lihat INSTITUTIONAL_DATA_REPORT.md).
    """
    now = time.time() if now is None else now
    if _netflow_cache["data"] is not None and (now - _netflow_cache["ts"]) < BTC_NETFLOW_CACHE_SEC:
        return _netflow_cache["data"]

    if not _btc_netflow_scrape_enabled():
        result = {
            "status": "not_configured",
            "netflow_btc": None,
            "source": None,
            "message": (
                "BTC Netflow: belum ada sumber gratis yang stabil -- API berbayar "
                "yang diriset tidak dipilih, dan scraping alternatif "
                "(BTC_NETFLOW_SCRAPE_ENABLED) butuh render JavaScript yang berisiko "
                "menambah beban resource VPS -- lihat INSTITUTIONAL_DATA_REPORT.md"
            ),
        }
        _netflow_cache["ts"] = now
        _netflow_cache["data"] = result
        return result

    value, err = _scrape_btc_netflow()
    if value is not None:
        result = {"status": "ok", "netflow_btc": value, "source": "scrape:btcdash", "message": None}
    else:
        if err:
            logger.warning("institutional_data: BTC netflow scrape: %s", err)
        result = {
            "status": "fetch_failed",
            "netflow_btc": None,
            "source": None,
            "message": f"BTC Netflow: {err or 'scraping gagal'}",
        }
    _netflow_cache["ts"] = now
    _netflow_cache["data"] = result
    return result
