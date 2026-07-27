"""
Signal tracking for SQLite accuracy stats (WIN/LOSS/EXPIRED).
"""

from __future__ import annotations

import logging
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

logger = logging.getLogger(__name__)

WIB = timezone(timedelta(hours=7))
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "aliza.db")
BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
OUTCOME_INTERVAL = "5m"
ROUND_TRIP_FEE_PCT = 0.2
KLINE_LIMIT = 1000
MAX_KLINE_PAGES = 4

SETUP_SIDE = {
    "OVERSOLD BOUNCE": "LONG",
    "PULLBACK LONG": "LONG",
    "LONG": "LONG",
    "OVERBOUGHT REJECTION": "SHORT",
    "PULLBACK SHORT": "SHORT",
    "SHORT": "SHORT",
}


def _now_wib() -> datetime:
    return datetime.now(WIB)


def _now_wib_iso() -> str:
    return _now_wib().isoformat()


def _safe_float(v: Any) -> float | None:
    try:
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _normalize_side(side: Any, setup: Any = None) -> str | None:
    normalized = str(side or "").strip().upper()
    if normalized in {"LONG", "SHORT"}:
        return normalized
    return SETUP_SIDE.get(str(setup or "").strip().upper())


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_signal_tracking_db() -> bool:
    try:
        conn = _connect()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS signal_tracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                coin TEXT NOT NULL,
                setup TEXT,
                side TEXT,
                source TEXT DEFAULT 'deterministic',
                signal_id TEXT,
                dispatch_status TEXT DEFAULT 'UNKNOWN',
                entry_price REAL,
                sl_price REAL,
                tp_price REAL,
                confidence REAL,
                rr REAL,
                signal_time TEXT,
                status TEXT DEFAULT 'OPEN',
                close_price REAL,
                close_time TEXT,
                pnl_pct REAL,
                market_score INTEGER,
                regime TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        cur = conn.execute("PRAGMA table_info(signal_tracking)")
        _cols = [r[1] for r in cur.fetchall()]
        migrations = {
            "regime": "TEXT",
            "side": "TEXT",
            "source": "TEXT",
            "signal_id": "TEXT",
            "dispatch_status": "TEXT",
        }
        for column, definition in migrations.items():
            if column not in _cols:
                conn.execute(
                    f"ALTER TABLE signal_tracking ADD COLUMN {column} {definition}"
                )

        conn.execute(
            """
            UPDATE signal_tracking
            SET side = CASE UPPER(TRIM(IFNULL(setup, '')))
                WHEN 'OVERSOLD BOUNCE' THEN 'LONG'
                WHEN 'PULLBACK LONG' THEN 'LONG'
                WHEN 'LONG' THEN 'LONG'
                WHEN 'OVERBOUGHT REJECTION' THEN 'SHORT'
                WHEN 'PULLBACK SHORT' THEN 'SHORT'
                WHEN 'SHORT' THEN 'SHORT'
                ELSE side
            END
            WHERE side IS NULL OR TRIM(side) = ''
            """
        )
        conn.execute(
            "UPDATE signal_tracking SET source='legacy' "
            "WHERE source IS NULL OR TRIM(source)=''"
        )
        conn.execute(
            "UPDATE signal_tracking SET dispatch_status='UNKNOWN' "
            "WHERE dispatch_status IS NULL OR TRIM(dispatch_status)=''"
        )
        missing_ids = conn.execute(
            "SELECT id FROM signal_tracking "
            "WHERE signal_id IS NULL OR TRIM(signal_id)=''"
        ).fetchall()
        for row in missing_ids:
            conn.execute(
                "UPDATE signal_tracking SET signal_id=? WHERE id=?",
                (str(uuid.uuid4()), int(row[0])),
            )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS "
            "idx_signal_tracking_signal_id ON signal_tracking(signal_id)"
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("signal_tracker: init db failed: %s", e)
        return False


def _episode_parts(coin: Any, setup: Any, side: Any, source: Any) -> tuple[str, str, str, str]:
    normalized_coin = str(coin or "").upper().replace("USDT", "").strip()
    normalized_setup = str(setup or "").upper().strip()
    normalized_side = _normalize_side(side, normalized_setup) or ""
    normalized_source = str(source or "deterministic").lower().strip()
    return normalized_coin, normalized_setup, normalized_side, normalized_source


def has_open_episode(*, coin: Any, setup: Any, side: Any, source: Any = "deterministic") -> bool:
    """Whether the exact production episode identity still has an OPEN row."""
    coin_n, setup_n, side_n, source_n = _episode_parts(coin, setup, side, source)
    if not coin_n or not setup_n or not side_n or not source_n:
        return False
    conn: sqlite3.Connection | None = None
    try:
        conn = _connect()
        row = conn.execute(
            """
            SELECT id FROM signal_tracking
            WHERE status = 'OPEN'
              AND UPPER(TRIM(coin)) = ?
              AND UPPER(TRIM(IFNULL(setup, ''))) = ?
              AND UPPER(TRIM(IFNULL(side, ''))) = ?
              AND LOWER(TRIM(IFNULL(source, ''))) = ?
            LIMIT 1
            """,
            (coin_n, setup_n, side_n, source_n),
        ).fetchone()
        return row is not None
    finally:
        if conn is not None:
            conn.close()


def _sync_edge_episode(signal: dict[str, Any], active: bool) -> None:
    """Avoid a module-import cycle while keeping tracker transitions synchronous."""
    if str(signal.get("source") or "").lower() != "deterministic":
        return
    try:
        from engine.trading import signal_engine
        if active:
            signal_engine.mark_tracking_episode_open(signal)
        else:
            signal_engine.mark_tracking_episode_closed(signal)
    except Exception as exc:  # noqa: BLE001
        logger.warning("signal_tracker: edge episode sync failed: %s", exc)


def record_signal(signal: dict[str, Any]) -> int | None:
    if not signal or not isinstance(signal, dict):
        return None
    coin, setup, side, source = _episode_parts(
        signal.get("coin"), signal.get("setup"), signal.get("side"),
        signal.get("source") or "deterministic",
    )
    if not coin:
        return None
    signal_uuid = str(signal.get("signal_id") or uuid.uuid4())
    dispatch_status = str(signal.get("dispatch_status") or "UNKNOWN").strip().upper()
    entry = _safe_float(signal.get("entry"))
    sl = _safe_float(signal.get("sl") or signal.get("stop_loss"))
    tp = _safe_float(signal.get("tp") or signal.get("take_profit") or signal.get("tp1"))
    confidence = _safe_float(signal.get("confidence"))
    rr = _safe_float(signal.get("rr"))
    signal_time = str(signal.get("signal_time") or _now_wib_iso())
    regime = str(signal.get("regime") or "UNKNOWN")

    market_score = signal.get("market_score")
    try:
        market_score_i = int(market_score) if market_score is not None else None
    except (TypeError, ValueError):
        market_score_i = None

    try:
        conn = _connect()
        dup = conn.execute(
            """
            SELECT id
            FROM signal_tracking
            WHERE UPPER(TRIM(coin)) = ?
              AND UPPER(TRIM(IFNULL(setup, ''))) = ?
              AND UPPER(TRIM(IFNULL(side, ''))) = ?
              AND signal_time = ?
              AND LOWER(TRIM(IFNULL(source, ''))) = ?
            LIMIT 1
            """,
            (coin, setup, side, signal_time, source),
        ).fetchone()
        if dup:
            conn.close()
            return None

        # Secondary guard for repeated polling: exact episode identity still OPEN.
        dup_open = conn.execute(
            """
            SELECT id
            FROM signal_tracking
            WHERE status = 'OPEN'
              AND UPPER(TRIM(coin)) = ?
              AND UPPER(TRIM(IFNULL(setup, ''))) = ?
              AND UPPER(TRIM(IFNULL(side, ''))) = ?
              AND LOWER(TRIM(IFNULL(source, ''))) = ?
            LIMIT 1
            """,
            (coin, setup, side, source),
        ).fetchone()
        if dup_open:
            conn.close()
            return None

        cur = conn.execute(
            """
            INSERT INTO signal_tracking
            (coin, setup, side, source, signal_id, dispatch_status,
             entry_price, sl_price, tp_price, confidence, rr, signal_time,
             status, market_score, regime)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?)
            """,
            (
                coin, setup, side, source, signal_uuid, dispatch_status,
                entry, sl, tp, confidence, rr, signal_time,
                market_score_i, regime,
            ),
        )
        conn.commit()
        new_id = int(cur.lastrowid)
        conn.close()
        _sync_edge_episode(
            {"coin": coin, "setup": setup, "side": side, "source": source},
            True,
        )
        return new_id
    except Exception as e:  # noqa: BLE001
        logger.warning("signal_tracker: record_signal failed: %s", e)
        return None


def _parse_iso_time(v: Any) -> datetime | None:
    if not v:
        return None
    try:
        value = str(v).strip()
        if value.lower().endswith(" wib"):
            value = value[:-4].rstrip()
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=WIB)
    except Exception:  # noqa: BLE001
        return None


def _parse_created_at(v: Any) -> datetime | None:
    if not v:
        return None
    try:
        parsed = datetime.fromisoformat(str(v).strip())
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _fetch_5m_klines(
    coin: str, created_at: datetime, now: datetime
) -> list[dict[str, float | int]]:
    """Ambil candle 5m kronologis sejak signal dibuat, dengan pagination terbatas 7 hari."""
    symbol = str(coin or "").strip().upper()
    if not symbol:
        return []
    if not symbol.endswith("USDT"):
        symbol = f"{symbol}USDT"
    cursor_ms = int(created_at.timestamp() * 1000)
    end_ms = int(now.astimezone(timezone.utc).timestamp() * 1000)
    candles: list[dict[str, float | int]] = []

    for _ in range(MAX_KLINE_PAGES):
        try:
            response = requests.get(
                BINANCE_KLINES_URL,
                params={
                    "symbol": symbol,
                    "interval": OUTCOME_INTERVAL,
                    "startTime": cursor_ms,
                    "endTime": end_ms,
                    "limit": KLINE_LIMIT,
                },
                timeout=12,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("signal_tracker: kline fetch failed %s: %s", symbol, exc)
            return []
        if response.status_code != 200:
            logger.warning(
                "signal_tracker: kline fetch HTTP %s for %s",
                response.status_code,
                symbol,
            )
            return []
        payload = response.json()
        if not isinstance(payload, list) or not payload:
            break

        last_close_time = None
        for candle in payload:
            if not isinstance(candle, (list, tuple)) or len(candle) < 7:
                continue
            try:
                item = {
                    "open_time": int(candle[0]),
                    "high": float(candle[2]),
                    "low": float(candle[3]),
                    "close": float(candle[4]),
                    "close_time": int(candle[6]),
                }
            except (TypeError, ValueError):
                continue
            if item["open_time"] < cursor_ms or item["open_time"] > end_ms:
                continue
            candles.append(item)
            last_close_time = int(item["close_time"])

        if len(payload) < KLINE_LIMIT or last_close_time is None:
            break
        next_cursor = last_close_time + 1
        if next_cursor <= cursor_ms or next_cursor > end_ms:
            break
        cursor_ms = next_cursor

    return candles


def _net_pnl_pct(side: str, entry: float, close_price: float) -> float:
    if side == "SHORT":
        gross = ((entry - close_price) / entry) * 100.0
    else:
        gross = ((close_price - entry) / entry) * 100.0
    return round(gross - ROUND_TRIP_FEE_PCT, 6)


def _evaluate_outcome(
    *,
    side: str,
    entry: float,
    sl: float,
    tp: float,
    candles: list[dict[str, float | int]],
) -> tuple[str | None, float | None, float | None]:
    for candle in candles:
        high = float(candle["high"])
        low = float(candle["low"])
        if side == "SHORT":
            tp_hit = low <= tp
            sl_hit = high >= sl
        else:
            tp_hit = high >= tp
            sl_hit = low <= sl

        # Jika dua level tersentuh dalam candle yang sama, urutan tidak diketahui:
        # hasil konservatif selalu LOSS pada harga stop.
        if tp_hit and sl_hit:
            return "LOSS", sl, _net_pnl_pct(side, entry, sl)
        if sl_hit:
            return "LOSS", sl, _net_pnl_pct(side, entry, sl)
        if tp_hit:
            return "WIN", tp, _net_pnl_pct(side, entry, tp)
    return None, None, None


def check_open_signals() -> list[dict[str, Any]]:
    closed: list[dict[str, Any]] = []
    conn: sqlite3.Connection | None = None
    try:
        conn = _connect()
        rows = conn.execute(
            """
            SELECT id, coin, setup, side, source, entry_price, sl_price, tp_price,
                   signal_time, created_at
            FROM signal_tracking
            WHERE status = 'OPEN'
            """
        ).fetchall()
        if not rows:
            return []

        now_utc = datetime.now(timezone.utc)
        now_wib_iso = now_utc.astimezone(WIB).isoformat()
        for row in rows:
            row_id = int(row["id"])
            coin = str(row["coin"] or "").upper()
            setup = str(row["setup"] or "")
            side = _normalize_side(row["side"], setup)
            entry = _safe_float(row["entry_price"])
            sl = _safe_float(row["sl_price"])
            tp = _safe_float(row["tp_price"])
            created_at = _parse_created_at(row["created_at"])
            signal_time = _parse_iso_time(row["signal_time"])

            if (
                side not in {"LONG", "SHORT"}
                or entry is None
                or entry <= 0
                or sl is None
                or tp is None
                or created_at is None
            ):
                continue

            candles = _fetch_5m_klines(coin, created_at, now_utc)
            status, close_price, pnl_pct = _evaluate_outcome(
                side=side, entry=entry, sl=sl, tp=tp, candles=candles
            )
            if status is None:
                expiry_reference = signal_time or created_at
                if now_utc - expiry_reference.astimezone(timezone.utc) > timedelta(days=7):
                    status = "EXPIRED"
                else:
                    continue

            conn.execute(
                """
                UPDATE signal_tracking
                SET status = ?, close_price = ?, close_time = ?, pnl_pct = ?
                WHERE id = ?
                """,
                (status, close_price, now_wib_iso, pnl_pct, row_id),
            )
            closed.append(
                {
                    "id": row_id,
                    "coin": coin,
                    "setup": setup,
                    "side": side,
                    "source": row["source"],
                    "entry_price": entry,
                    "close_price": close_price,
                    "status": status,
                    "pnl_pct": pnl_pct,
                    "signal_time": row["signal_time"],
                    "close_time": now_wib_iso,
                }
            )

        conn.commit()
        for item in closed:
            _sync_edge_episode(item, False)
        return closed
    except Exception as exc:  # noqa: BLE001
        logger.warning("signal_tracker: check_open_signals failed: %s", exc)
        return []
    finally:
        if conn is not None:
            conn.close()


def _empty_stats() -> dict[str, Any]:
    return {
        "source_filter": "deterministic",
        "total_signals": 0,
        "win": 0,
        "loss": 0,
        "expired": 0,
        "open": 0,
        "win_rate": 0.0,
        "avg_pnl": 0.0,
        "best_trade": None,
        "worst_trade": None,
        "by_coin": [],
        "by_source": [],
        "by_side": [],
        "by_setup": [],
    }


def _stats_breakdown(
    conn: sqlite3.Connection, column: str, source_filter: str | None = None
) -> list[dict[str, Any]]:
    if column not in {"source", "side", "setup"}:
        raise ValueError("unsupported breakdown column")
    if source_filter is None:
        source_clause = ""
        source_params: tuple[Any, ...] = ()
    elif source_filter == "deterministic":
        # Legacy/LLM tetap terlihat pada breakdown historis Fase 1, tetapi
        # shadow tidak boleh mencemari statistik produksi default.
        source_clause = "WHERE IFNULL(source, '') != 'shadow_e3'"
        source_params = ()
    else:
        source_clause = "WHERE source = ?"
        source_params = (source_filter,)
    rows = conn.execute(
        f"""
        SELECT IFNULL({column}, 'UNKNOWN') AS label,
               COUNT(*) AS total,
               SUM(CASE WHEN status='WIN' THEN 1 ELSE 0 END) AS win,
               SUM(CASE WHEN status='LOSS' THEN 1 ELSE 0 END) AS loss,
               SUM(CASE WHEN status='OPEN' THEN 1 ELSE 0 END) AS open,
               SUM(CASE WHEN status='EXPIRED' THEN 1 ELSE 0 END) AS expired
        FROM signal_tracking {source_clause}
        GROUP BY IFNULL({column}, 'UNKNOWN')
        ORDER BY label
        """,
        source_params,
    ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        win = int(row["win"] or 0)
        loss = int(row["loss"] or 0)
        closed = win + loss
        result.append(
            {
                column: row["label"],
                "total": int(row["total"] or 0),
                "win": win,
                "loss": loss,
                "open": int(row["open"] or 0),
                "expired": int(row["expired"] or 0),
                "win_rate": (win / closed * 100.0) if closed else 0.0,
            }
        )
    return result


def get_signal_stats(source: str | None = "deterministic") -> dict[str, Any]:
    """Statistik terfilter source; default produksi mengecualikan shadow_e3."""
    result = _empty_stats()
    result["source_filter"] = source
    conn: sqlite3.Connection | None = None
    try:
        conn = _connect()
        where = "" if source is None else "WHERE source = ?"
        params: tuple[Any, ...] = () if source is None else (source,)
        totals = conn.execute(
            f"""
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN status='WIN' THEN 1 ELSE 0 END) AS win,
                   SUM(CASE WHEN status='LOSS' THEN 1 ELSE 0 END) AS loss,
                   SUM(CASE WHEN status='EXPIRED' THEN 1 ELSE 0 END) AS expired,
                   SUM(CASE WHEN status='OPEN' THEN 1 ELSE 0 END) AS open,
                   AVG(CASE WHEN status IN ('WIN','LOSS') THEN pnl_pct END) AS avg_pnl
            FROM signal_tracking {where}
            """,
            params,
        ).fetchone()
        total = int(totals["total"] or 0)
        win = int(totals["win"] or 0)
        loss = int(totals["loss"] or 0)
        closed = win + loss

        closed_where = (
            "WHERE status IN ('WIN','LOSS') AND pnl_pct IS NOT NULL"
            if source is None
            else "WHERE source = ? AND status IN ('WIN','LOSS') "
                 "AND pnl_pct IS NOT NULL"
        )
        best = conn.execute(
            f"""
            SELECT coin, setup, side, source, pnl_pct
            FROM signal_tracking {closed_where}
            ORDER BY pnl_pct DESC LIMIT 1
            """,
            params,
        ).fetchone()
        worst = conn.execute(
            f"""
            SELECT coin, setup, side, source, pnl_pct
            FROM signal_tracking {closed_where}
            ORDER BY pnl_pct ASC LIMIT 1
            """,
            params,
        ).fetchone()
        by_coin = conn.execute(
            f"""
            SELECT coin,
                   COUNT(*) AS total,
                   SUM(CASE WHEN status='WIN' THEN 1 ELSE 0 END) AS win,
                   SUM(CASE WHEN status='LOSS' THEN 1 ELSE 0 END) AS loss
            FROM signal_tracking {where}
            GROUP BY coin ORDER BY coin
            """,
            params,
        ).fetchall()

        result.update(
            {
                "total_signals": total,
                "win": win,
                "loss": loss,
                "expired": int(totals["expired"] or 0),
                "open": int(totals["open"] or 0),
                "win_rate": (win / closed * 100.0) if closed else 0.0,
                "avg_pnl": float(totals["avg_pnl"] or 0.0),
                "best_trade": dict(best) if best else None,
                "worst_trade": dict(worst) if worst else None,
                "by_coin": [
                    {
                        "coin": row["coin"],
                        "total": int(row["total"] or 0),
                        "win": int(row["win"] or 0),
                        "loss": int(row["loss"] or 0),
                        "win_rate": (
                            int(row["win"] or 0)
                            / (int(row["win"] or 0) + int(row["loss"] or 0))
                            * 100.0
                        )
                        if (int(row["win"] or 0) + int(row["loss"] or 0))
                        else 0.0,
                    }
                    for row in by_coin
                ],
                "by_source": _stats_breakdown(conn, "source", source),
                "by_side": _stats_breakdown(conn, "side", source),
                "by_setup": _stats_breakdown(conn, "setup", source),
            }
        )
        return result
    except Exception as e:  # noqa: BLE001
        logger.warning("signal_tracker: get_signal_stats failed: %s", e)
        return result
    finally:
        if conn is not None:
            conn.close()
