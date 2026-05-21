import logging
import os
import sqlite3
from datetime import datetime

logger = logging.getLogger(__name__)

DB_PATH = "data/aliza.db"


def _direction_from_setup(setup):
    """Derive direction from setup string (untuk backward compat / baris lama tanpa direction)."""
    if not setup:
        return "SHORT"
    s = (setup or "").upper()
    if "LONG" in s or setup == "OVERSOLD BOUNCE":
        return "LONG"
    return "SHORT"


def _table_columns(cursor):
    cursor.execute("PRAGMA table_info(trades)")
    return [row[1] for row in cursor.fetchall()]


def _ensure_direction_column(conn):
    """Tambahkan kolom direction jika belum ada (kompatibel dengan database lama)."""
    cursor = conn.cursor()
    columns = _table_columns(cursor)
    if "direction" not in columns:
        cursor.execute("ALTER TABLE trades ADD COLUMN direction TEXT")
        conn.commit()


def _ensure_position_columns(conn):
    """Tambah kolom position sizing jika belum ada."""
    cursor = conn.cursor()
    columns = _table_columns(cursor)
    for col_sql in (
        "quantity REAL DEFAULT 0",
        "position_value_usdt REAL DEFAULT 0",
        "risk_usdt REAL DEFAULT 0",
    ):
        col_name = col_sql.split()[0]
        if col_name in columns:
            continue
        try:
            cursor.execute(f"ALTER TABLE trades ADD COLUMN {col_sql}")
            conn.commit()
            logger.info("Migrasi: kolom %s ditambahkan ke trades", col_name)
        except sqlite3.OperationalError as e:
            logger.debug("Migrasi kolom %s: %s", col_name, e)


def init_trade_db():
    os.makedirs("data", exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        coin TEXT,
        setup TEXT,
        entry REAL,
        stop_loss REAL,
        tp1 REAL,
        tp2 REAL,
        status TEXT,
        created_at TEXT
    )
    """)
    conn.commit()

    _ensure_direction_column(conn)
    _ensure_position_columns(conn)
    conn.close()


def create_trade(
    coin,
    setup,
    entry,
    sl,
    tp1,
    tp2,
    quantity=None,
    position_value_usdt=None,
    risk_usdt=None,
):
    """
    Simpan trade. Direction dihitung dari setup.
    quantity, position_value_usdt, risk_usdt opsional (default 0) untuk position sizing.
    """
    direction = _direction_from_setup(setup)
    qty = float(quantity) if quantity is not None else 0.0
    pv = float(position_value_usdt) if position_value_usdt is not None else 0.0
    rk = float(risk_usdt) if risk_usdt is not None else 0.0

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    columns = _table_columns(cursor)

    if "direction" in columns and "quantity" in columns:
        cursor.execute(
            """
            INSERT INTO trades
            (coin, direction, setup, entry, stop_loss, tp1, tp2, status, created_at,
             quantity, position_value_usdt, risk_usdt)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                coin,
                direction,
                setup,
                entry,
                sl,
                tp1,
                tp2,
                "OPEN",
                datetime.utcnow().isoformat(),
                qty,
                pv,
                rk,
            ),
        )
    elif "direction" in columns:
        cursor.execute(
            """
            INSERT INTO trades
            (coin, direction, setup, entry, stop_loss, tp1, tp2, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (coin, direction, setup, entry, sl, tp1, tp2, "OPEN", datetime.utcnow().isoformat()),
        )
    else:
        cursor.execute(
            """
            INSERT INTO trades
            (coin, setup, entry, stop_loss, tp1, tp2, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (coin, setup, entry, sl, tp1, tp2, "OPEN", datetime.utcnow().isoformat()),
        )

    conn.commit()
    conn.close()


def get_active_trades():
    """
    Return list of tuples:
    (coin, direction, setup, entry, stop_loss, tp1, tp2 [, quantity, position_value_usdt, risk_usdt])
    Versi lama 6/7 elemen tetap didukung saat baca DB tanpa kolom baru.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    columns = _table_columns(cursor)

    has_dir = "direction" in columns
    has_pos = "quantity" in columns and "position_value_usdt" in columns and "risk_usdt" in columns

    if has_dir and has_pos:
        cursor.execute(
            """
            SELECT coin, direction, setup, entry, stop_loss, tp1, tp2,
                   quantity, position_value_usdt, risk_usdt
            FROM trades
            WHERE status = 'OPEN'
            """
        )
        rows = cursor.fetchall()
        out = []
        for r in rows:
            (
                coin,
                direction,
                setup,
                entry,
                stop_loss,
                tp1,
                tp2,
                quantity,
                position_value_usdt,
                risk_usdt,
            ) = r
            if not direction:
                direction = _direction_from_setup(setup)
            out.append(
                (
                    coin,
                    direction,
                    setup,
                    entry,
                    stop_loss,
                    tp1,
                    tp2,
                    float(quantity or 0),
                    float(position_value_usdt or 0),
                    float(risk_usdt or 0),
                )
            )
        conn.close()
        return out

    if has_dir:
        cursor.execute(
            """
            SELECT coin, direction, setup, entry, stop_loss, tp1, tp2
            FROM trades
            WHERE status = 'OPEN'
            """
        )
        rows = cursor.fetchall()
        out = []
        for r in rows:
            coin, direction, setup, entry, stop_loss, tp1, tp2 = r
            if not direction:
                direction = _direction_from_setup(setup)
            out.append((coin, direction, setup, entry, stop_loss, tp1, tp2))
        conn.close()
        return out

    cursor.execute(
        """
        SELECT coin, setup, entry, stop_loss, tp1, tp2
        FROM trades
        WHERE status = 'OPEN'
        """
    )
    rows = cursor.fetchall()
    out = [(r[0], _direction_from_setup(r[1]), r[1], r[2], r[3], r[4], r[5]) for r in rows]
    conn.close()
    return out


def trade_direction(trade):
    """
    Ambil direction dari tuple trade. Kompatibel dengan format 7–10 elemen atau 6-elemen lama.
    """
    if not trade or len(trade) < 2:
        return _direction_from_setup(trade[2] if trade and len(trade) > 2 else None)
    if trade[1] in ("LONG", "SHORT"):
        return trade[1]
    setup = trade[2] if len(trade) > 2 else trade[1]
    return _direction_from_setup(setup)


def close_trade(coin):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE trades
        SET status='CLOSED'
        WHERE coin=? AND status='OPEN'
        """,
        (coin,),
    )

    affected = cursor.rowcount
    conn.commit()
    conn.close()

    return affected > 0
