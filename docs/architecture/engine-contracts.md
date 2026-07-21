# ALIZA AI — ENGINE CONTRACTS

Dokumen ini menjelaskan kontrak data antar modul dalam sistem AlizaAI.

Tujuan:
- Menjamin kompatibilitas antar modul
- Mencegah perubahan struktur data yang merusak sistem
- Membantu AI memahami format data yang digunakan engine

AI yang memodifikasi kode harus mengikuti kontrak ini.

---

# 1. MARKET DATA CONTRACT

`engine.market.market_analyzer.market_signal(symbol)` mengembalikan `dict` ketika data valid, atau `None` ketika input indikator wajib tidak valid.

```python
{
    "symbol": str,
    "price": float,
    "trend": str,                 # BULLISH | BEARISH | SIDEWAYS
    "rsi": float,
    "support": float,
    "resistance": float,

    "fear_greed": int | float | None,
    "dominance": float | None,
    "trend_4h": str,
    "trend_1d": str,
    "trend_alignment": str,

    "cycle_phase": str,
    "funding_status": str,
    "whale_activity": str,

    "stablecoin_flow": str,
    "open_interest_level": str,
    "liquidation_risk": str,

    "market_phase_prediction": str,
    "bull_probability": int | float | None,
    "market_risk_score": str | int | float,

    "trade_setup": dict | None,
    "data_coverage": dict,
    "timestamp": float,            # epoch seconds
}
```

Field tambahan khusus coin, misalnya enrichment BTC, boleh ada. Consumer tidak boleh menganggap field opsional selalu tersedia.

---

# 2. SNAPSHOT CONTRACT

`engine.market.market_snapshot_engine.get_market_snapshot()` mengembalikan salinan:

```python
{
    "data": dict[str, dict],
    "timestamp": datetime | None,
    "market_intelligence": dict | None,
    "data_coverage": dict,
}
```

Opportunity scanner hanya memakai snapshot valid/fresh. Snapshot stale atau invalid menghasilkan abort tanpa fallback ke market cache.

---

# 3. DATABASE WRITE OWNERSHIP

`data/aliza.db` mempunyai dua penulis yang sah:

- `engine/trading/trade_manager.py` untuk tabel `trades`
- `engine/trading/signal_tracker.py` untuk pembuatan/migrasi dan row `signal_tracking`

`engine/user_config.py` menulis database terpisah (`data/user_config.db` secara default). Penulis atau perubahan schema baru memerlukan migrasi, test, dan persetujuan eksplisit.

---

# 4. SIGNAL DISPATCH CONTRACT

`snapshot_job` memanggil `scan_for_signals()`. Kandidat produksi melewati unified gateway (risk, macro, dedup, dispatch) dan baru dicatat oleh signal tracker setelah dispatch berhasil. E3 shadow adalah source terpisah dan tidak boleh tercampur dengan statistik produksi default.

<!-- Diverifikasi akurat per 2026-07-21, commit f38ab55 -->
