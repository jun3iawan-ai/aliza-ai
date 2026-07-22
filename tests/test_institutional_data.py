"""
Tests for engine/market/institutional_data.py -- the SoSoValue/Farside-backed
replacement for the old "proxy via berita" (Serper news-snippet regex parsing)
institutional data section. See INSTITUTIONAL_DATA_REPORT.md.

Covers: ETF flow (SoSoValue Demo API primary, Farside Investors scraping
fallback -- CoinGlass dropped, no free tier, see report), liquidation volume
24h (CoinGlass only, paid-tier gap), BTC exchange netflow (scraping fallback,
disabled by default), cache TTL, empty-key handling, and HTML scraping parse
correctness (including on real captured "blocked" pages, proving failures are
reported honestly rather than guessed).
"""

import os
import time
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import pytest

from engine.market import institutional_data as idata

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _read_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text

    def json(self):
        return self._json_data


@pytest.fixture(autouse=True)
def _clean_state():
    idata.reset_cache_for_tests()
    yield
    idata.reset_cache_for_tests()


# ---------------------------------------------------------------------------
# 1. get_etf_flow_data(): SoSoValue primary, Farside fallback, both-fail,
#    no-key-but-farside-attempted
# ---------------------------------------------------------------------------


class TestEtfFlowData:
    def test_sosovalue_success_is_used(self, monkeypatch):
        monkeypatch.setenv("SOSOVALUE_API_KEY", "soso-test-key")
        with patch.object(
            idata,
            "_fetch_sosovalue_etf_flow",
            return_value=(
                {"flow_usd_today_m": 42.0, "flow_usd_7d_m": 300.0, "price_usd": None, "source": "sosovalue"},
                None,
            ),
        ) as mock_soso, patch.object(idata, "_fetch_farside_etf_flow") as mock_farside:
            result = idata.get_etf_flow_data()
        mock_farside.assert_not_called()  # SoSoValue succeeded, no need to fall back
        assert result["status"] == "ok"
        assert result["source"] == "sosovalue"
        assert result["flow_usd_today_m"] == 42.0
        assert result["flow_usd_7d_m"] == 300.0

    def test_sosovalue_fails_farside_succeeds_fallback_works(self, monkeypatch):
        monkeypatch.setenv("SOSOVALUE_API_KEY", "soso-test-key")
        with patch.object(idata, "_fetch_sosovalue_etf_flow", return_value=(None, "SoSoValue HTTP 500")), \
             patch.object(
                 idata,
                 "_fetch_farside_etf_flow",
                 return_value=({"flow_usd_today_m": 26.0, "flow_usd_7d_m": 108.0, "price_usd": None, "source": "farside"}, None),
             ):
            result = idata.get_etf_flow_data()
        assert result["status"] == "ok"
        assert result["source"] == "farside"
        assert result["flow_usd_today_m"] == 26.0

    def test_both_sources_fail_returns_clear_failure_not_fake_data(self, monkeypatch):
        monkeypatch.setenv("SOSOVALUE_API_KEY", "soso-test-key")
        with patch.object(idata, "_fetch_sosovalue_etf_flow", return_value=(None, "SoSoValue HTTP 500")), \
             patch.object(idata, "_fetch_farside_etf_flow", return_value=(None, "Farside: HTTP 403")):
            result = idata.get_etf_flow_data()
        assert result["status"] == "fetch_failed"
        assert result["flow_usd_today_m"] is None
        assert result["flow_usd_7d_m"] is None
        assert result["message"] is not None
        assert "gagal" in result["message"].lower()

    def test_no_sosovalue_key_farside_still_attempted_and_can_succeed(self, monkeypatch):
        """Farside needs no API key, so it should be tried even when
        SOSOVALUE_API_KEY is completely unset -- unlike SoSoValue itself,
        which must be skipped without a key (see TestEmptyKeyHandling)."""
        monkeypatch.delenv("SOSOVALUE_API_KEY", raising=False)
        with patch.object(idata, "_fetch_sosovalue_etf_flow") as mock_soso, \
             patch.object(
                 idata,
                 "_fetch_farside_etf_flow",
                 return_value=({"flow_usd_today_m": 26.0, "flow_usd_7d_m": 108.0, "price_usd": None, "source": "farside"}, None),
             ) as mock_farside:
            result = idata.get_etf_flow_data()
        mock_soso.assert_not_called()
        mock_farside.assert_called_once()
        assert result["status"] == "ok"
        assert result["source"] == "farside"

    def test_no_sosovalue_key_and_farside_fails_reports_not_configured(self, monkeypatch):
        monkeypatch.delenv("SOSOVALUE_API_KEY", raising=False)
        with patch.object(idata, "_fetch_farside_etf_flow", return_value=(None, "Farside: HTTP 403")):
            result = idata.get_etf_flow_data()
        assert result["status"] == "not_configured"
        assert "SOSOVALUE_API_KEY" in result["message"]


# ---------------------------------------------------------------------------
# 2. Cache TTL
# ---------------------------------------------------------------------------


class TestCacheTtl:
    def test_two_calls_within_window_hit_http_once(self, monkeypatch):
        monkeypatch.setenv("SOSOVALUE_API_KEY", "soso-test-key")
        data = {"flow_usd_today_m": 10.0, "flow_usd_7d_m": 10.0, "price_usd": None, "source": "sosovalue"}
        with patch.object(idata, "_fetch_sosovalue_etf_flow", return_value=(data, None)) as mock_fetch:
            t0 = time.time()
            idata.get_etf_flow_data(now=t0)
            idata.get_etf_flow_data(now=t0 + 10)  # well within ETF_FLOW_CACHE_SEC (3600s)
        assert mock_fetch.call_count == 1

    def test_call_after_ttl_expiry_refetches(self, monkeypatch):
        monkeypatch.setenv("SOSOVALUE_API_KEY", "soso-test-key")
        data = {"flow_usd_today_m": 10.0, "flow_usd_7d_m": 10.0, "price_usd": None, "source": "sosovalue"}
        with patch.object(idata, "_fetch_sosovalue_etf_flow", return_value=(data, None)) as mock_fetch:
            t0 = time.time()
            idata.get_etf_flow_data(now=t0)
            idata.get_etf_flow_data(now=t0 + idata.ETF_FLOW_CACHE_SEC + 10)
        assert mock_fetch.call_count == 2

    def test_liquidation_cache_ttl(self, monkeypatch):
        monkeypatch.setenv("COINGLASS_API_KEY", "cg-test-key")
        data = {"long_usd_m": 10.0, "short_usd_m": 20.0, "source": "coinglass"}
        with patch.object(idata, "_fetch_coinglass_liquidation_volume", return_value=(data, None)) as mock_fetch:
            t0 = time.time()
            idata.get_liquidation_volume_24h(now=t0)
            idata.get_liquidation_volume_24h(now=t0 + 60)
        assert mock_fetch.call_count == 1


# ---------------------------------------------------------------------------
# 3. Empty key -> "not_configured" without exception, without any HTTP attempt
# ---------------------------------------------------------------------------


class TestEmptyKeyHandling:
    def test_etf_flow_no_sosovalue_key_skips_sosovalue_http_but_still_tries_farside(self, monkeypatch):
        """SoSoValue needs a key so it must be skipped entirely with none set;
        Farside needs no key at all so it's still attempted -- if that also
        fails (e.g. mocked HTTP untouched/blocked), status is 'not_configured'
        since the actionable next step is still 'add a free SoSoValue key'."""
        monkeypatch.delenv("SOSOVALUE_API_KEY", raising=False)
        with patch.object(idata, "_fetch_sosovalue_etf_flow") as mock_soso, \
             patch("requests.get", return_value=FakeResponse(403, text="Just a moment...")):
            result = idata.get_etf_flow_data()
        mock_soso.assert_not_called()
        assert result["status"] == "not_configured"
        assert result["message"] is not None

    def test_liquidation_no_key_returns_not_configured_without_http(self, monkeypatch):
        monkeypatch.delenv("COINGLASS_API_KEY", raising=False)
        with patch.object(idata, "_fetch_coinglass_liquidation_volume") as mock_cg:
            result = idata.get_liquidation_volume_24h()
        mock_cg.assert_not_called()
        assert result["status"] == "not_configured"

    def test_low_level_sosovalue_fetch_returns_none_when_key_empty(self, monkeypatch):
        """Even the low-level fetch function itself refuses to make an HTTP
        call with no key -- defense in depth beyond the public function's own
        short-circuit."""
        monkeypatch.delenv("SOSOVALUE_API_KEY", raising=False)
        with patch("httpx.Client") as mock_client:
            data, err = idata._fetch_sosovalue_etf_flow()
        mock_client.assert_not_called()
        assert data is None
        assert "belum dikonfigurasi" in err


# ---------------------------------------------------------------------------
# 4. get_btc_exchange_netflow(): success, failure, timeout -- no crash, distinct messages
# ---------------------------------------------------------------------------


class TestBtcExchangeNetflow:
    def test_disabled_by_default_no_http_attempt(self, monkeypatch):
        monkeypatch.delenv("BTC_NETFLOW_SCRAPE_ENABLED", raising=False)
        with patch("requests.get") as mock_get:
            result = idata.get_btc_exchange_netflow()
        mock_get.assert_not_called()
        assert result["status"] == "not_configured"
        assert "Startup" in result["message"] or "BTC_NETFLOW_SCRAPE_ENABLED" in result["message"]

    def test_enabled_scrape_success(self, monkeypatch):
        monkeypatch.setenv("BTC_NETFLOW_SCRAPE_ENABLED", "true")
        html = _read_fixture("btcdash_netflow_synthetic_ok.html")
        with patch("requests.get", return_value=FakeResponse(200, text=html)):
            result = idata.get_btc_exchange_netflow()
        assert result["status"] == "ok"
        assert result["netflow_btc"] == -3250.0

    def test_enabled_scrape_http_failure(self, monkeypatch):
        monkeypatch.setenv("BTC_NETFLOW_SCRAPE_ENABLED", "true")
        with patch("requests.get", return_value=FakeResponse(503, text="")):
            result = idata.get_btc_exchange_netflow()
        assert result["status"] == "fetch_failed"
        assert "503" in result["message"]

    def test_enabled_scrape_timeout(self, monkeypatch):
        monkeypatch.setenv("BTC_NETFLOW_SCRAPE_ENABLED", "true")
        import requests as real_requests

        with patch("requests.get", side_effect=real_requests.Timeout("timed out")):
            result = idata.get_btc_exchange_netflow()
        assert result["status"] == "fetch_failed"
        assert "timeout" in result["message"].lower()

    def test_enabled_scrape_against_real_js_required_page_reports_failure(self, monkeypatch):
        """The actual btcdash.org HTML (captured during research) never
        contains the number -- it's filled in by client-side JS. Confirms the
        scraper degrades honestly instead of guessing."""
        monkeypatch.setenv("BTC_NETFLOW_SCRAPE_ENABLED", "true")
        html = _read_fixture("btcdash_netflow_js_required.html")
        with patch("requests.get", return_value=FakeResponse(200, text=html)):
            result = idata.get_btc_exchange_netflow()
        assert result["status"] == "fetch_failed"
        assert result["netflow_btc"] is None
        assert "gagal parse" in result["message"].lower() or "render js" in result["message"].lower()

    def test_three_distinct_log_messages_for_success_failure_timeout(self, monkeypatch, caplog):
        """Success/failure/timeout should each be distinguishable from the log
        messages -- not the same generic error for all three."""
        monkeypatch.setenv("BTC_NETFLOW_SCRAPE_ENABLED", "true")
        import logging
        caplog.set_level(logging.WARNING, logger="engine.market.institutional_data")

        idata.reset_cache_for_tests()
        with patch("requests.get", return_value=FakeResponse(503, text="")):
            idata.get_btc_exchange_netflow(now=1000.0)
        http_fail_log = caplog.text
        caplog.clear()

        idata.reset_cache_for_tests()
        import requests as real_requests
        with patch("requests.get", side_effect=real_requests.Timeout("timed out")):
            idata.get_btc_exchange_netflow(now=2000.0)
        timeout_log = caplog.text

        assert http_fail_log != timeout_log
        assert "503" in http_fail_log
        assert "timeout" in timeout_log.lower()


# ---------------------------------------------------------------------------
# 5. HTML scraping parse correctness (static fixtures)
# ---------------------------------------------------------------------------


class TestHtmlParsing:
    def test_parses_correct_value_from_known_structure(self):
        html = _read_fixture("btcdash_netflow_synthetic_ok.html")
        value = idata._parse_btcdash_netflow_html(html)
        assert value == -3250.0

    def test_real_captured_page_yields_none_not_a_guess(self):
        html = _read_fixture("btcdash_netflow_js_required.html")
        value = idata._parse_btcdash_netflow_html(html)
        assert value is None

    def test_unknown_changed_structure_yields_none_not_wrong_number(self):
        """Site renamed/removed the element id -- must not silently pick up
        an unrelated number from elsewhere on the page (e.g. from a footer)."""
        html = _read_fixture("btcdash_netflow_unknown_structure.html")
        value = idata._parse_btcdash_netflow_html(html)
        assert value is None


# ---------------------------------------------------------------------------
# 6. Farside Investors: table parsing + real-world Cloudflare block detection
# ---------------------------------------------------------------------------


class TestFarsideEtfFlow:
    def test_parses_correct_totals_from_synthetic_table(self):
        html = _read_fixture("farside_synthetic_table.html")
        today_m, cum_7d_m, err = idata._parse_farside_etf_table(html)
        assert err is None
        assert today_m == 26.0
        assert cum_7d_m == 108.0  # 75.0 + 7.0 + 26.0

    def test_unknown_structure_no_total_column_yields_none_not_wrong_number(self):
        """Table has a differently-named aggregate column ("Sum" instead of
        "Total") -- must fail cleanly instead of guessing which column to
        sum."""
        html = _read_fixture("farside_unknown_structure.html")
        today_m, cum_7d_m, err = idata._parse_farside_etf_table(html)
        assert today_m is None
        assert cum_7d_m is None
        assert err is not None
        assert "total" in err.lower()

    def test_real_captured_cloudflare_challenge_page_detected_not_misparsed(self):
        """Real HTML captured from farside.co.uk/btc/ during this session's
        verification -- a Cloudflare managed-challenge page, not the ETF flow
        table. Confirms the fetch layer recognizes this as a block (distinct
        message) rather than the parser silently returning no error on a page
        with no table."""
        html = _read_fixture("farside_cloudflare_challenge.html")
        assert idata._is_cloudflare_challenge(403, html) is True
        today_m, cum_7d_m, err = idata._parse_farside_etf_table(html)
        assert today_m is None
        assert cum_7d_m is None
        assert err is not None

    def test_fetch_detects_cloudflare_block_with_distinct_message(self, monkeypatch):
        monkeypatch.setenv("SOSOVALUE_API_KEY", "soso-test-key")
        html = _read_fixture("farside_cloudflare_challenge.html")
        with patch.object(idata, "_fetch_sosovalue_etf_flow", return_value=(None, "SoSoValue HTTP 500")), \
             patch("requests.get", return_value=FakeResponse(403, text=html)):
            result = idata.get_etf_flow_data()
        assert result["status"] == "fetch_failed"
        assert "cloudflare" in result["message"].lower()

    def test_fetch_http_failure_not_confused_with_cloudflare_block(self, monkeypatch):
        monkeypatch.setenv("SOSOVALUE_API_KEY", "soso-test-key")
        with patch.object(idata, "_fetch_sosovalue_etf_flow", return_value=(None, "SoSoValue HTTP 500")), \
             patch("requests.get", return_value=FakeResponse(500, text="Internal Server Error")):
            result = idata.get_etf_flow_data()
        assert result["status"] == "fetch_failed"
        assert "cloudflare" not in result["message"].lower()
        assert "500" in result["message"]

    def test_real_captured_success_page_parses_correctly(self):
        """Real farside.co.uk/btc/ HTML, fetched live via `requests` during
        this session's verification (curl/WebFetch get blocked by Cloudflare
        here, but this project's actual HTTP client doesn't -- see module
        docstring). Locks in that the parser's assumptions (table
        class="etf", "Total" as last header column, ascending chronological
        date-row order, parenthesized negatives) match the real page, not
        just a hand-built synthetic fixture."""
        html = _read_fixture("farside_real_success.html")
        today_m, cum_7d_m, err = idata._parse_farside_etf_table(html)
        assert err is None
        assert today_m == 39.3
        assert cum_7d_m == 341.6
