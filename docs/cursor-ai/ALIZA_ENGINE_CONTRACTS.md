# ALIZA AI — ENGINE CONTRACTS

Dokumen ini menjelaskan kontrak data antar modul dalam sistem AlizaAI.

Tujuan:
- Menjamin kompatibilitas antar modul
- Mencegah perubahan struktur data yang merusak sistem
- Membantu AI memahami format data yang digunakan engine

AI yang memodifikasi kode harus mengikuti kontrak ini.

---

# 1. MARKET DATA CONTRACT

Semua modul market menggunakan struktur berikut.

Output dari:

market_analyzer.market_signal(symbol)

```python
{
    "symbol": str,
    "price": float,
    "trend": str,              # BULLISH | BEARISH | SIDEWAYS
    "rsi": float,
    "support": float,
    "resistance": float,

    "fear_greed": int,
    "dominance": float,

    "cycle_phase": str,
    "funding_status": str,
    "whale_activity": str,

    "stablecoin_flow": str,
    "open_interest_level": str,
    "liquidation_risk": str,

    "market_phase_prediction": str,
    "bull_probability": int,
    "market_risk_score": str,

    "trade_setup": dict,
    "timestamp": str
}