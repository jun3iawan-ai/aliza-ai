"""Formatter bersama untuk tampilan angka di pesan Telegram.

Satu sumber kebenaran untuk presisi desimal — lihat ai-rules §9.4 (satu nama, satu makna).
JANGAN menyalin logika ini ke modul lain; impor dari sini.
"""


def format_price(v):
    """Format harga koin dengan presisi mengikuti magnitudo.

    >=1000  -> '62,288.23'   (koma + 2 desimal)
    >=10    -> '566.29'      (2 desimal)
    >=0.01  -> '0.5570'      (4 desimal)
    <0.01   -> '0.00000272'  (8 desimal, untuk koin mikro seperti PEPE)
    None    -> '—'
    non-numeric -> dikembalikan apa adanya
    """
    if v is None:
        return "—"
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return v
    av = abs(fv)
    if av >= 1000:
        return f"{fv:,.2f}"
    if av >= 10:
        return f"{fv:.2f}"
    if av >= 0.01:
        return f"{fv:.4f}"
    return f"{fv:.8f}"


def format_ratio(v):
    """Format rasio (RR, dsb) — 1 desimal. Rasio bukan harga: 4 desimal cuma noise.

    None -> '—'; non-numeric -> dikembalikan apa adanya.
    """
    if v is None:
        return "—"
    try:
        return f"{float(v):.1f}"
    except (TypeError, ValueError):
        return v
