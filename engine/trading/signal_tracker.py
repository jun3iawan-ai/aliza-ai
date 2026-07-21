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

from engine.market.market_snapshot_engine import get_market_snapshot

logger = logging.getLogger(__name__)

WIB = timezone(timedelta(hours=7))
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "aliza.db")

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


def record_signal(signal: dict[str, Any]) -> int | None:
    if not signal or not isinstance(signal, dict):
        return None
    coin = str(signal.get("coin") or "").upper().strip()
    if not coin:
        return None

    setup = str(signal.get("setup") or "").strip()
    side = _normalize_side(signal.get("side"), setup)
    source = str(signal.get("source") or "deterministic").strip().lower()
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
            WHERE coin = ? AND IFNULL(setup, '') = IFNULL(?, '')
              AND signal_time = ? AND IFNULL(source, '') = IFNULL(?, '')
            LIMIT 1
            """,
            (coin, setup, signal_time, source),
        ).fetchone()
        if dup:
            conn.close()
            return None

        # Secondary guard for repeated polling: same coin/setup still open.
        dup_open = conn.execute(
            """
            SELECT id
            FROM signal_tracking
            WHERE status = 'OPEN'
              AND coin = ?
              AND IFNULL(setup, '') = IFNULL(?, '')
              AND IFNULL(source, '') = IFNULL(?, '')
            LIMIT 1
            """,
            (coin, setup, source),
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


def check_open_signals() -> list[dict[str, Any]]:
    closed: list[dict[str, Any]] = []
    try:
        conn = _connect()
        rows = conn.execute(
            """
            SELECT id, coin, setup, side, entry_price, sl_price, tp_price, signal_time
            FROM signal_tracking
            WHERE status = 'OPEN'
            """
        ).fetchall()
        if not rows:
            conn.close()
            return []

        snapshot = get_market_snapshot()
        data_map = snapshot.get("data") or {}
        now_wib = _now_wib()
        now_wib_iso = now_wib.isoformat()

        for r in rows:
            signal_id = int(r["id"])
            coin = str(r["coin"] or "").upper()
            setup = str(r["setup"] or "")
            side = _normalize_side(r["side"], setup)
            entry = _safe_float(r["entry_price"])
            sl = _safe_float(r["sl_price"])
            tp = _safe_float(r["tp_price"])
            signal_time = _parse_iso_time(r["signal_time"])

            status = None
            close_price = None
            pnl_pct = None

            if signal_time is not None and now_wib - signal_time > timedelta(days=7):
                status = "EXPIRED"
            else:
                coin_data = data_map.get(coin)
                if not isinstance(coin_data, dict):
                    continue
                price = _safe_float(coin_data.get("price"))
                if price is None or entry is None or entry == 0:
                    continue
                close_price = price
                is_short = side == "SHORT"
                if is_short:
                    if tp is not None and price <= tp:
                        status = "WIN"
                        pnl_pct = ((entry - price) / entry) * 100.0
                    elif sl is not None and price >= sl:
                        status = "LOSS"
                        pnl_pct = ((entry - price) / entry) * 100.0
                else:
                    if tp is not None and price >= tp:
                        status = "WIN"
                        pnl_pct = ((price - entry) / entry) * 100.0
                    elif sl is not None and price <= sl:
                        status = "LOSS"
                        pnl_pct = ((price - entry) / entry) * 100.0

            if status is None:
                continue

            conn.execute(
                """
                UPDATE signal_tracking
                SET status = ?, close_price = ?, close_time = ?, pnl_pct = ?
                WHERE id = ?
                """,
                (status, close_price, now_wib_iso, pnl_pct, signal_id),
            )
            closed.append(
                {
                    "id": signal_id,
                    "coin": coin,
                    "setup": setup,
                    "side": side,
                    "entry_price": entry,
                    "close_price": close_price,
                    "status": status,
                    "pnl_pct": pnl_pct,
                    "signal_time": r["signal_time"],
                    "close_time": now_wib_iso,
                }
            )

        conn.commit()
        conn.close()
    except Exception as e:  # noqa: BLE001
        logger.warning("signal_tracker: check_open_signals failed: %s", e)
        return []
    return closed


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
    conn: sqlite3.Connection, column: str
) -> list[dict[str, Any]]:
    if column not in {"source", "side", "setup"}:
        raise ValueError("unsupported breakdown column")
    rows = conn.execute(
        f"""
        SELECT IFNULL({column}, 'UNKNOWN') AS label,
               COUNT(*) AS total,
               SUM(CASE WHEN status='WIN' THEN 1 ELSE 0 END) AS win,
               SUM(CASE WHEN status='LOSS' THEN 1 ELSE 0 END) AS loss,
               SUM(CASE WHEN status='OPEN' THEN 1 ELSE 0 END) AS open,
               SUM(CASE WHEN status='EXPIRED' THEN 1 ELSE 0 END) AS expired
        FROM signal_tracking
        GROUP BY IFNULL({column}, 'UNKNOWN')
        ORDER BY label
        """
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
    """Statistik utama terfilter deterministic; breakdown selalu mencakup semua source."""
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
                "by_source": _stats_breakdown(conn, "source"),
                "by_side": _stats_breakdown(conn, "side"),
                "by_setup": _stats_breakdown(conn, "setup"),
            }
        )
        return result
    except Exception as e:  # noqa: BLE001
        logger.warning("signal_tracker: get_signal_stats failed: %s", e)
        return result
    finally:
        if conn is not None:
            conn.close()
