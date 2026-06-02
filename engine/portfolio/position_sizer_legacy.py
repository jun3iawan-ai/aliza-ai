# DEPRECATED — gunakan engine.position_sizer. File ini dipertahankan untuk referensi.
# Portfolio AI memakai API lama (balance, risk_pct, entry, sl) → calculate_position_size di bawah.
"""
ALIZA POSITION SIZER (legacy)

Menghitung ukuran posisi berdasarkan balance, risk %, entry, dan SL.
"""

import logging


def calculate_position_size(balance, risk_pct, entry, sl):
    """
    Hitung size posisi (dalam unit coin/contract).

    risk_amount = balance * risk_pct
    size = risk_amount / abs(entry - sl)

    Return: float size, atau 0.0 jika invalid.
    """
    try:
        balance = float(balance) if balance is not None else 0.0
        risk_pct = float(risk_pct) if risk_pct is not None else 0.0
        entry = float(entry) if entry is not None else 0.0
        sl = float(sl) if sl is not None else 0.0
        if balance <= 0 or risk_pct <= 0 or entry <= 0:
            return 0.0
        risk_per_unit = abs(entry - sl)
        if risk_per_unit <= 0:
            return 0.0
        risk_amount = balance * risk_pct
        size = risk_amount / risk_per_unit
        return round(size, 8)
    except (TypeError, ValueError) as e:
        logging.debug("position_sizer: %s", e)
        return 0.0
