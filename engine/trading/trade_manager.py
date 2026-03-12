import sqlite3
import os
from datetime import datetime

DB_PATH = "data/aliza.db"


# =========================
# CREATE TABLE
# =========================

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
    conn.close()


# =========================
# CREATE TRADE
# =========================

def create_trade(coin, setup, entry, sl, tp1, tp2):

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""

    INSERT INTO trades
    (coin, setup, entry, stop_loss, tp1, tp2, status, created_at)

    VALUES (?, ?, ?, ?, ?, ?, ?, ?)

    """, (

        coin,
        setup,
        entry,
        sl,
        tp1,
        tp2,
        "OPEN",
        datetime.utcnow().isoformat()

    ))

    conn.commit()
    conn.close()


# =========================
# GET ACTIVE TRADES
# =========================

def get_active_trades():

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""

    SELECT coin, setup, entry, stop_loss, tp1, tp2
    FROM trades
    WHERE status = 'OPEN'

    """)

    rows = cursor.fetchall()

    conn.close()

    return rows


# =========================
# CLOSE TRADE
# =========================

def close_trade(coin):

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""

    UPDATE trades
    SET status='CLOSED'
    WHERE coin=? AND status='OPEN'

    """, (coin,))

    affected = cursor.rowcount

    conn.commit()
    conn.close()

    return affected > 0