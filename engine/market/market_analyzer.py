"""
ALIZA MARKET ANALYZER

Fetch harga dan indikator per symbol; panggil market_radar dan (jika ada) trading_brain.
Semua resolusi symbol → CoinGecko ID memakai resolve_coin_id (prioritas: dynamic_universe, lalu COINGECKO_IDS).
"""

import logging
import os as _os_cg
import time
import requests

from engine.market.coin_id_resolver import resolve_coin_id
from engine.market.market_universe import MAJOR_COINS
from engine.market.market_radar import market_radar
from engine.market.global_market_cache import get_global_market_data
from engine.market.multi_timeframe_analyzer import analyze_multi_timeframe
from engine.market.klines_cache import get_cached_klines, set_cached_klines
from engine.indicators.constants import MIN_REQUIRED_DATA

HEADERS = {"User-Agent": "AlizaAI"}
logger = logging.getLogger(__name__)


def _get_cg_headers() -> dict:
    h = {"User-Agent": "AlizaAI"}
    key = _os_cg.getenv("COINGECKO_API_KEY", "")
    if key:
        h["x-cg-demo-api-key"] = key
    return h
COINGECKO_CHART_URL = "https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
BINANCE_TICKER_URL = "https://api.binance.com/api/v3/ticker/price"
BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
TIMEOUT = 12
KLINES_LIMIT = 100

# Last known price per symbol when CoinGecko fails (cache fallback)
_last_known_price = {}

# Cache harga CoinGecko yang di-pre-fetch per snapshot cycle
_CG_PRICE_CACHE: dict[str, float] = {}


def set_cg_price_cache(prices: dict[str, float]) -> None:
    """Dipanggil oleh snapshot engine sebelum loop; isi cache harga CoinGecko."""
    global _CG_PRICE_CACHE
    _CG_PRICE_CACHE = dict(prices)


def _safe_float(val, default=None):
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _get_price_from_binance(symbol):
    """Fetch current price from Binance ticker. Returns float or None."""
    if not symbol:
        return None
    try:
        sym = (symbol or "").upper().strip()
        r = requests.get(
            BINANCE_TICKER_URL,
            params={"symbol": f"{sym}USDT"},
            headers=HEADERS,
            timeout=10,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        if isinstance(data, dict) and "price" in data:
            return _safe_float(data["price"])
    except Exception:
        pass
    return None


def _extract_closed_kline_closes(data, now_ms=None):
    """Ekstrak close hanya dari candle Binance yang closeTime-nya sudah lewat."""
    cutoff_ms = int(now_ms if now_ms is not None else time.time() * 1000)
    closes = []
    for candle in data if isinstance(data, list) else []:
        if not isinstance(candle, (list, tuple)) or len(candle) < 7:
            continue
        try:
            close_time = int(candle[6])
            close_price = float(candle[4])
        except (TypeError, ValueError):
            continue
        if close_time > cutoff_ms:
            continue
        if close_price > 0:
            closes.append(close_price)
    return closes


def _get_binance_klines(symbol_usdt, interval, limit=100):
    """
    Fetch OHLCV klines from Binance. symbol_usdt must be e.g. BTCUSDT, ETHUSDT.
    Returns list of closed-candle prices (oldest to newest), or [] on failure.
    Uses klines cache to reduce API requests; TTL 4h=300s, 1d=600s.
    """
    if not symbol_usdt or not isinstance(symbol_usdt, str):
        return []
    sym = (symbol_usdt or "").upper().strip()
    if not sym.endswith("USDT"):
        sym = f"{sym}USDT"

    cached = get_cached_klines(sym, interval)
    if cached:
        logging.debug("Using cached klines %s %s", sym, interval)
        return cached

    def _do_request():
        r = requests.get(
            BINANCE_KLINES_URL,
            params={"symbol": sym, "interval": interval, "limit": min(limit, 1000)},
            headers=HEADERS,
            timeout=TIMEOUT,
        )
        return r

    logging.debug("Fetching klines from Binance %s %s", sym, interval)
    try:
        r = _do_request()
        if r.status_code == 429:
            logging.warning("Binance rate limit hit, retrying %s %s", sym, interval)
            time.sleep(5)
            r = _do_request()
        if r.status_code != 200:
            return []
        data = r.json()
        if not isinstance(data, list):
            return []
        closes = _extract_closed_kline_closes(data)
        if closes:
            set_cached_klines(sym, interval, closes)
            return closes
        return []
    except Exception as e:
        logging.warning("market_analyzer klines failed %s %s: %s", sym, interval, e)
        return []


def get_coin_market_chart(symbol, vs_currency="usd", days=90):
    """
    Ambil data market chart dari CoinGecko untuk symbol.
    coin_id diperoleh via resolve_coin_id(symbol) agar dynamic universe dan statis sama-sama didukung.
    Return dict dengan prices, market_caps, total_volumes; atau {} jika gagal.
    """
    coin_id = resolve_coin_id(symbol)
    if not coin_id:
        logging.warning("market_analyzer: no coin_id for symbol %s", symbol)
        return {}
    url = COINGECKO_CHART_URL.format(coin_id=coin_id)
    try:
        r = requests.get(
            url,
            params={"vs_currency": vs_currency, "days": days},
            headers=_get_cg_headers(),
            timeout=TIMEOUT,
        )
        if r.status_code != 200:
            return {}
        data = r.json()
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logging.warning("market_analyzer get_coin_market_chart %s: %s", symbol, e)
        return {}


def _get_prices_from_chart(chart_data):
    """List harga (oldest to newest) dari chart data."""
    raw = (chart_data or {}).get("prices") or []
    if not isinstance(raw, list):
        return []
    out = []
    for p in raw:
        try:
            out.append((int(p[0]), float(p[1])))
        except (IndexError, TypeError, ValueError):
            continue
    out.sort(key=lambda x: x[0])
    return [pr for _, pr in out]


def _moving_average(prices, period):
    if not prices or len(prices) < period:
        return None
    return sum(prices[-period:]) / period


def _calculate_rsi(prices, period=14):
    if not prices or len(prices) < period + 1:
        return None
    # Wilder's Smoothed RSI
    # Step 1: hitung initial avg gain/loss dari period pertama
    gains = []
    losses = []
    for i in range(1, len(prices)):
        ch = prices[i] - prices[i - 1]
        gains.append(max(ch, 0.0))
        losses.append(max(-ch, 0.0))
    if len(gains) < period:
        return None
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    # Step 2: smoothing untuk candle berikutnya
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def _support_resistance(prices):
    if not prices or len(prices) < 20:
        return None, None
    recent = prices[-20:]
    return min(recent), max(recent)


def _trend_from_ma(price, ma50, ma200):
    if ma50 is None or ma200 is None:
        return "SIDEWAYS"
    if price > ma50 > ma200:
        return "BULLISH"
    if price < ma50 < ma200:
        return "BEARISH"
    return "SIDEWAYS"


def market_signal(symbol, radar_data=None):
    """
    Analisis market untuk satu symbol. Binance primary untuk price; CoinGecko chart untuk historical.
    radar_data: optional result of market_radar(fear, dominance); jika ada, dipakai agar radar tidak dipanggil per coin.
    Return dict: symbol, price, trend, rsi, support, resistance, + radar fields, trade_setup (jika ada).
    """
    symbol = (symbol or "").strip().upper() or "BTC"

    # 1. Binance as primary price source; CoinGecko fallback for non-Binance coins
    price = _get_price_from_binance(symbol)
    if price is None or price <= 0:
        # Cek cache pre-fetch dulu
        cached_cg = _CG_PRICE_CACHE.get(symbol)
        if cached_cg and cached_cg > 0:
            price = cached_cg
            logging.info("market_analyzer: CoinGecko cache hit %s = %s", symbol, price)
        else:
            # fallback individual (tetap ada sebagai safety net)
            try:
                _cg_id = resolve_coin_id(symbol)
                if _cg_id:
                    _r = requests.get(
                        f"https://api.coingecko.com/api/v3/simple/price"
                        f"?ids={_cg_id}&vs_currencies=usd",
                        headers=_get_cg_headers(),
                        timeout=8,
                    )
                    if _r.status_code == 200:
                        _cg_data = _r.json()
                        if _cg_id in _cg_data:
                            price = float(_cg_data[_cg_id]["usd"])
                            logging.info("market_analyzer: CoinGecko fallback price %s = %s", symbol, price)
            except Exception as _e:
                logging.warning("market_analyzer: CoinGecko price fallback failed %s: %s", symbol, _e)
    if price is not None and isinstance(price, (int, float)) and price > 0:
        price = float(price)
        _last_known_price[symbol] = price

    # 2. Candle data: Binance klines (4h and 1d) for indicators; fallback to CoinGecko
    symbol_usdt = f"{symbol}USDT"
    closes_4h = _get_binance_klines(symbol_usdt, "4h", KLINES_LIMIT)
    closes_1d = _get_binance_klines(symbol_usdt, "1d", KLINES_LIMIT)

    # Primary price series: 4h if enough candles, else 1d, else CoinGecko chart
    if closes_4h and len(closes_4h) >= 20:
        prices = list(closes_4h)
    elif closes_1d and len(closes_1d) >= 20:
        prices = list(closes_1d)
    else:
        chart = get_coin_market_chart(symbol, vs_currency="usd", days=90)
        prices = _get_prices_from_chart(chart)

    # 3. Resolve final price: Binance -> last known cache -> chart fallback.
    # Ticker tidak ditambahkan ke seri indikator karena bukan candle yang sudah close.
    def _is_valid_price(p):
        return p is not None and isinstance(p, (int, float)) and p > 0

    if not _is_valid_price(price):
        price = _last_known_price.get(symbol)
    if not _is_valid_price(price) and prices:
        price = prices[-1]
    if _is_valid_price(price):
        price = float(price)
        _last_known_price[symbol] = price
    else:
        logging.error("Price unavailable for %s", symbol)
        logger.warning("Invalid data — skipping signal")
        return None

    if not prices or len(prices) < MIN_REQUIRED_DATA:
        logger.warning("Invalid data — skipping signal")
        return None

    # Setiap timeframe harus berasal dari seri aslinya. Data kurang ditandai
    # unavailable agar analyzer menghasilkan UNKNOWN, bukan false alignment.
    _closes_4h_mtf = closes_4h if len(closes_4h) >= 30 else []
    _closes_1d_mtf = closes_1d if len(closes_1d) >= 50 else []
    mtf = analyze_multi_timeframe(_closes_4h_mtf, _closes_1d_mtf)
    trend_4h = mtf.get("trend_4h")
    trend_1d = mtf.get("trend_1d")
    alignment = mtf.get("alignment")

    ma20 = _moving_average(prices, 20)
    ma50 = _moving_average(prices, 50)
    ma200 = _moving_average(prices, 200)

    # Trend: prefer ma50/ma200; fallback to ma20/ma50 if ma200 not available
    if ma50 and ma200:
        trend = _trend_from_ma(price, ma50, ma200)
    elif ma20 and ma50:
        trend = _trend_from_ma(price, ma20, ma50)
    else:
        trend = "SIDEWAYS"

    # RSI from close prices: prefer 4h lalu 1d lalu series utama; tanpa RSI valid → NO SIGNAL
    rsi_prices = closes_4h if (closes_4h and len(closes_4h) >= 15) else (closes_1d if (closes_1d and len(closes_1d) >= 15) else prices)
    rsi = _calculate_rsi(rsi_prices)
    if rsi is None:
        logger.warning("Invalid data — skipping signal")
        return None
    try:
        rsi = float(rsi)
    except (TypeError, ValueError):
        logger.warning("Invalid data — skipping signal")
        return None
    if rsi < 0 or rsi > 100:
        logger.warning("Invalid data — skipping signal")
        return None
    support, resistance = _support_resistance(prices)

    global_data = get_global_market_data()
    fear = global_data["fear_greed"]
    dominance = global_data["btc_dominance"]
    if radar_data is not None and isinstance(radar_data, dict):
        radar = radar_data
    else:
        radar = {}
        try:
            radar = market_radar(fear, dominance) or {}
        except Exception as e:
            logging.warning("market_analyzer market_radar: %s", e)

    trade_setup = None
    try:
        from engine.brain.trading_brain import TradingBrain
        brain = TradingBrain()
        market_data = {
            "symbol": symbol,
            "price": price,
            "trend": trend,
            "rsi": rsi,
            "support": support,
            "resistance": resistance,
            "trend_alignment": alignment,
        }
        trade_setup = brain.analyze(market_data)
    except Exception:
        pass

    # Safety fallback: ensure market_data is always valid
    if trend is None or str(trend).strip() not in ("BULLISH", "BEARISH", "SIDEWAYS"):
        logging.warning("Trend fallback SIDEWAYS for %s", symbol)
        trend = "SIDEWAYS"
    if support is None:
        support = price * 0.98 if price is not None else 0
    if resistance is None:
        resistance = price * 1.02 if price is not None else 0

    # Normalize market_data fields before return
    try:
        price = float(price)
    except (TypeError, ValueError):
        price = 0.0
    try:
        rsi = float(rsi)
    except (TypeError, ValueError):
        logger.warning("Invalid data — skipping signal")
        return None
    trend = str(trend).strip().upper()
    if trend not in ("BULLISH", "BEARISH", "SIDEWAYS"):
        trend = "SIDEWAYS"
    try:
        support = float(support) if support is not None else price * 0.98
    except (TypeError, ValueError):
        support = price * 0.98
    try:
        resistance = float(resistance) if resistance is not None else price * 1.02
    except (TypeError, ValueError):
        resistance = price * 1.02

    result = {
        "symbol": symbol,
        "price": price,
        "trend": trend,
        "rsi": rsi,
        "support": support,
        "resistance": resistance,
        "fear_greed": fear,
        "dominance": dominance,
        "trend_4h": trend_4h,
        "trend_1d": trend_1d,
        "trend_alignment": alignment,
        "cycle_phase": radar.get("cycle_phase", "UNKNOWN"),
        "funding_status": radar.get("funding_status", "UNKNOWN"),
        "whale_activity": radar.get("whale_activity", "UNKNOWN"),
        "stablecoin_flow": radar.get("stablecoin_flow", "UNKNOWN"),
        "open_interest_level": radar.get("open_interest_level", "UNKNOWN"),
        "liquidation_risk": radar.get("liquidation_risk", "UNKNOWN"),
        "market_phase_prediction": radar.get("market_phase_prediction", "UNKNOWN"),
        "bull_probability": radar.get("bull_probability"),
        "market_risk_score": radar.get("market_risk_score", "UNKNOWN"),
        "trade_setup": trade_setup,
        "timestamp": time.time(),
    }
    if symbol == "BTC":
        try:
            from engine.alerts.btc_smart_alert import enrich_btc_market_row
            result.update(enrich_btc_market_row(result))
        except Exception:
            pass
    return result


def _fallback_market_data(symbol, error_msg="error"):
    return {
        "symbol": (symbol or "UNKNOWN").upper(),
        "price": None,
        "trend": "DATA ERROR",
        "rsi": None,
        "support": None,
        "resistance": None,
        "fear_greed": None,
        "dominance": None,
        "cycle_phase": "UNKNOWN",
        "funding_status": "UNKNOWN",
        "whale_activity": "UNKNOWN",
        "stablecoin_flow": "UNKNOWN",
        "open_interest_level": "UNKNOWN",
        "liquidation_risk": "UNKNOWN",
        "market_phase_prediction": "UNKNOWN",
        "bull_probability": None,
        "market_risk_score": "UNKNOWN",
        "trade_setup": None,
        "error": error_msg,
        "timestamp": time.time(),
    }


def btc_signal():
    return market_signal("BTC")
