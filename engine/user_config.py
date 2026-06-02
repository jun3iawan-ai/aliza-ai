"""
User config store — simpan preferensi user (balance, risk params) ke SQLite.

Saldo efektif (``get_balance``): Binance auto (jika diaktifkan + kredensial) →
DB manual → .env ``ACCOUNT_BALANCE``.
"""

from __future__ import annotations

import logging
import os
import sqlite3

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("USER_CONFIG_DB", "data/user_config.db")


def _get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    return conn


def set_config(key: str, value: str) -> bool:
    """Set atau update config value."""
    try:
        conn = _get_conn()
        conn.execute(
            """
            INSERT OR REPLACE INTO user_config (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            """,
            (key, value),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error("Failed to set config %s: %s", key, e)
        return False


def get_config(key: str, default: str | None = None) -> str | None:
    """Get config value dari DB."""
    try:
        conn = _get_conn()
        row = conn.execute(
            "SELECT value FROM user_config WHERE key = ?", (key,)
        ).fetchone()
        conn.close()
        return row[0] if row else default
    except Exception:
        return default


def is_auto_balance_enabled() -> bool:
    """True jika user memilih Binance auto-sync via /set_balance auto."""
    return (get_config("auto_balance") or "").strip().lower() == "true"


def get_balance() -> float:
    """
    Prioritas saldo efektif untuk position sizing:

    1. Jika ``auto_balance`` = true: Binance spot USDT (jika kredensial ada) → lalu DB → .env
    2. Jika ``auto_balance`` bukan true: DB manual → .env
    """
    if is_auto_balance_enabled():
        try:
            from engine.binance_balance import fetch_spot_balance

            b = fetch_spot_balance("USDT")
            if b > 0:
                return b
        except ImportError:
            pass
        except Exception as e:
            logger.debug("get_balance: Binance fallback: %s", e)

    db_val = get_config("account_balance")
    if db_val is not None and str(db_val).strip() != "":
        try:
            bal = float(str(db_val).replace(",", ""))
            if bal > 0:
                return bal
        except (ValueError, TypeError):
            pass

    try:
        env_bal = float(os.getenv("ACCOUNT_BALANCE", "0").replace(",", ""))
        if env_bal > 0:
            return env_bal
    except (ValueError, TypeError):
        pass

    return 0.0


def get_balance_source_label() -> str:
    """Label singkat untuk /balance (sumber konfigurasi, bukan audit exchange)."""
    if is_auto_balance_enabled():
        return "Binance auto-sync (aktif)"
    db_val = get_config("account_balance")
    if db_val is not None and str(db_val).strip() != "":
        try:
            bal = float(str(db_val).replace(",", ""))
            if bal > 0:
                return f"manual DB ({bal:,.0f} USDT)"
        except (ValueError, TypeError):
            pass
    try:
        env_bal = float(os.getenv("ACCOUNT_BALANCE", "0").replace(",", ""))
        if env_bal > 0:
            return ".env ACCOUNT_BALANCE"
    except (ValueError, TypeError):
        pass
    return "tidak di-set"
