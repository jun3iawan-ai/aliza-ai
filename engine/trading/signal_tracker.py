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
            WHERE coin = ? AND IFNULL(setup, '') = IFNULL(?, '') AND signal_time = ?
            LIMIT 1
            """,
            (coin, setup, signal_time),
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
            LIMIT 1
            """,
            (coin, setup),
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


def get_signal_stats() -> dict[str, Any]:
    try:
        conn = _connect()
        total = int(conn.execute("SELECT COUNT(*) FROM signal_tracking").fetchone()[0])
        if total == 0:
            conn.close()
            return {
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
            }

        win = int(conn.execute("SELECT COUNT(*) FROM signal_tracking WHERE status='WIN'").fetchone()[0])
        loss = int(conn.execute("SELECT COUNT(*) FROM signal_tracking WHERE status='LOSS'").fetchone()[0])
        expired = int(conn.execute("SELECT COUNT(*) FROM signal_tracking WHERE status='EXPIRED'").fetchone()[0])
        open_n = int(conn.execute("SELECT COUNT(*) FROM signal_tracking WHERE status='OPEN'").fetchone()[0])

        closed_base = win + loss
        win_rate = (win / closed_base * 100.0) if closed_base > 0 else 0.0
        avg_row = conn.execute(
            "SELECT AVG(pnl_pct) FROM signal_tracking WHERE status IN ('WIN','LOSS') AND pnl_pct IS NOT NULL"
        ).fetchone()
        avg_pnl = float(avg_row[0]) if avg_row and avg_row[0] is not None else 0.0

        best = conn.execute(
            """
            SELECT coin, setup, pnl_pct
            FROM signal_tracking
            WHERE status IN ('WIN','LOSS') AND pnl_pct IS NOT NULL
            ORDER BY pnl_pct DESC
            LIMIT 1
            """
        ).fetchone()
        worst = conn.execute(
            """
            SELECT coin, setup, pnl_pct
            FROM signal_tracking
            WHERE status IN ('WIN','LOSS') AND pnl_pct IS NOT NULL
            ORDER BY pnl_pct ASC
            LIMIT 1
            """
        ).fetchone()

        by_coin_rows = conn.execute(
            """
            SELECT
                coin,
                SUM(CASE WHEN status='WIN' THEN 1 ELSE 0 END) AS win,
                SUM(CASE WHEN status='LOSS' THEN 1 ELSE 0 END) AS loss
            FROM signal_tracking
            GROUP BY coin
            ORDER BY coin
            """
        ).fetchall()
        conn.close()

        by_coin = []
        for r in by_coin_rows:
            c_win = int(r["win"] or 0)
            c_loss = int(r["loss"] or 0)
            base = c_win + c_loss
            c_wr = (c_win / base * 100.0) if base > 0 else 0.0
            by_coin.append({"coin": r["coin"], "win": c_win, "loss": c_loss, "win_rate": c_wr})

        return {
            "total_signals": total,
            "win": win,
            "loss": loss,
            "expired": expired,
            "open": open_n,
            "win_rate": win_rate,
            "avg_pnl": avg_pnl,
            "best_trade": dict(best) if best else None,
            "worst_trade": dict(worst) if worst else None,
            "by_coin": by_coin,
        }
    except Exception as e:  # noqa: BLE001
        logger.warning("signal_tracker: get_signal_stats failed: %s", e)
        return {
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
        }
