"""
ALIZA ALERT MANAGER (NON-SPAM)

Menyimpan last signal per key dan memutuskan apakah alert perlu dikirim.
Hanya digunakan untuk layer alert (read-only), bukan untuk trading pipeline.
"""

from __future__ import annotations

from typing import Dict


LAST_SIGNALS: Dict[str, str] = {}


def should_send_alert(key: str, new_signal: str) -> bool:
    """
    Return True jika signal baru berbeda dari yang terakhir dikirim untuk key.
    """
    old = LAST_SIGNALS.get(key)
    if old == new_signal:
        return False
    LAST_SIGNALS[key] = new_signal
    return True

