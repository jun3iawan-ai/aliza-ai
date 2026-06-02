# Arsitektur Position Sizing — Aliza-AI

# Terintegrasi dengan risk_manager existing

**Tujuan:** Detail teknis untuk implementasi position sizing berbasis ukuran akun, terintegrasi dengan `engine.risk_manager` yang sudah ada.

**Terakhir diperbarui:** 2026-04-16

---

## 1. Kondisi Saat Ini

### Yang sudah ada di risk_manager:

- `validate_proposed_trade`: risk maks **2% jarak entry–SL**, RR minimum 2, maks 3 posisi terbuka
- Validasi ini bersifat **pass/fail** — sinyal lolos atau ditolak
- **Tidak** menghitung berapa lot/unit yang harus dibeli

### Yang belum ada:

- Input: **total modal** (account balance / equity)
- Kalkulasi: berapa **unit/lot** yang dibeli agar kerugian jika kena SL = X% dari modal
- Output: **position size** dalam unit aset (mis. 0.15 ETH) dan dalam USDT

### Kenapa ini penting untuk swing:

Tanpa position sizing, kamu mungkin:

- Pakai "feeling" untuk tentukan size → inkonsisten
- Over-expose di satu trade → satu SL hit bisa -10% portfolio
- Under-size di trade bagus → cuan kecil meski analisis benar

---

## 2. Formula Position Sizing

### Core formula (Fixed Fractional):

```
Position Size (USDT) = (Account Balance × Risk %) / |Entry - SL|  × Entry
Position Size (Unit)  = (Account Balance × Risk %) / |Entry - SL|
```

### Contoh konkret:

```
Account Balance  = 10,000 USDT
Risk per trade   = 2%
Entry (Long ETH) = 3,245 USDT
Stop Loss        = 3,120 USDT

Risk Amount      = 10,000 × 0.02 = 200 USDT
SL Distance      = |3,245 - 3,120| = 125 USDT
Position Size    = 200 / 125 = 1.6 ETH
Position Value   = 1.6 × 3,245 = 5,192 USDT (51.9% dari akun)
```

### Constraint tambahan:

```
Max position value   = Account Balance × Max Allocation %  (misal 30%)
Max concurrent risk  = Account Balance × Max Total Risk %  (misal 6% → 3 posisi × 2%)
```

Jika `Position Value > Max Allocation`:

```
Position Size (Unit) = (Account Balance × Max Allocation %) / Entry
```

Ambil yang **lebih kecil** dari risk-based size dan allocation-based size.

---

## 3. Arsitektur Integrasi

### 3.1 Alur di pipeline existing

```
scan_for_signals                    ← sudah ada
  └─ filter: RR ≥ 3, conf ≥ 70    ← sudah ada
      └─ candidates                 ← sudah ada

process_signal (gateway)            ← sudah ada
  └─ validate_proposed_trade        ← sudah ada (pass/fail)
      └─ [BARU] calculate_position_size  ← TAMBAH
          └─ attach size ke sinyal
              └─ kirim ke Telegram  ← sudah ada
```

### 3.2 Komponen baru

**File baru: `engine/position_sizer.py`**

```python
"""
Position Sizing Calculator — Aliza-AI

Menghitung ukuran posisi berdasarkan:
- Account balance (dari config atau input user)
- Risk per trade (default 2%)
- Entry price dan Stop Loss dari sinyal
- Max allocation per posisi (default 30%)
- Total risk exposure dari posisi terbuka
"""

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# === KONFIGURASI DEFAULT ===
DEFAULT_RISK_PER_TRADE = 0.02      # 2% per trade
DEFAULT_MAX_ALLOCATION = 0.30      # 30% max per posisi
DEFAULT_MAX_TOTAL_RISK = 0.06      # 6% total (3 × 2%)
DEFAULT_ACCOUNT_BALANCE = None     # Wajib di-set oleh user


@dataclass
class PositionSizeResult:
    """Hasil kalkulasi position sizing."""
    size_units: float           # Jumlah unit aset (mis. 1.6 ETH)
    size_usdt: float            # Nilai dalam USDT
    risk_amount_usdt: float     # Jumlah USDT yang dirisiko-kan
    risk_percent: float         # % dari akun yang dirisiko-kan
    allocation_percent: float   # % dari akun yang dialokasikan
    limited_by: str             # "risk" atau "allocation" — mana yang membatasi
    warnings: list[str]         # Peringatan jika ada


def calculate_position_size(
    entry_price: float,
    stop_loss: float,
    account_balance: float,
    risk_per_trade: float = DEFAULT_RISK_PER_TRADE,
    max_allocation: float = DEFAULT_MAX_ALLOCATION,
    current_open_risk_usdt: float = 0.0,
    max_total_risk: float = DEFAULT_MAX_TOTAL_RISK,
) -> Optional[PositionSizeResult]:
    """
    Hitung position size optimal.

    Args:
        entry_price: Harga entry yang direncanakan
        stop_loss: Harga stop loss
        account_balance: Total modal akun dalam USDT
        risk_per_trade: Fraksi risiko per trade (default 0.02 = 2%)
        max_allocation: Fraksi max alokasi per posisi (default 0.30 = 30%)
        current_open_risk_usdt: Total risk USDT dari posisi yang sudah terbuka
        max_total_risk: Fraksi max total risk portfolio (default 0.06 = 6%)

    Returns:
        PositionSizeResult atau None jika input invalid
    """
    warnings = []

    # === VALIDASI INPUT ===
    if account_balance <= 0:
        logger.error("Account balance harus > 0")
        return None

    if entry_price <= 0 or stop_loss <= 0:
        logger.error("Entry dan SL harus > 0")
        return None

    sl_distance = abs(entry_price - stop_loss)
    if sl_distance == 0:
        logger.error("Entry dan SL tidak boleh sama")
        return None

    # === HITUNG RISK BUDGET TERSISA ===
    max_risk_usdt = account_balance * max_total_risk
    remaining_risk_usdt = max_risk_usdt - current_open_risk_usdt

    if remaining_risk_usdt <= 0:
        logger.warning("Risk budget habis — tidak bisa buka posisi baru")
        warnings.append("Risk budget portfolio sudah penuh")
        return PositionSizeResult(
            size_units=0, size_usdt=0, risk_amount_usdt=0,
            risk_percent=0, allocation_percent=0,
            limited_by="total_risk_exceeded", warnings=warnings
        )

    # === HITUNG BERDASARKAN RISK ===
    risk_amount = min(account_balance * risk_per_trade, remaining_risk_usdt)
    size_by_risk = risk_amount / sl_distance  # dalam unit aset
    value_by_risk = size_by_risk * entry_price

    # === HITUNG BERDASARKAN MAX ALLOCATION ===
    max_value = account_balance * max_allocation
    size_by_alloc = max_value / entry_price

    # === AMBIL YANG LEBIH KECIL ===
    if value_by_risk <= max_value:
        final_size = size_by_risk
        limited_by = "risk"
    else:
        final_size = size_by_alloc
        risk_amount = final_size * sl_distance  # recalculate actual risk
        limited_by = "allocation"
        warnings.append(
            f"Size dikurangi oleh max allocation ({max_allocation*100:.0f}%)"
        )

    final_value = final_size * entry_price
    actual_risk_pct = (final_size * sl_distance) / account_balance
    alloc_pct = final_value / account_balance

    return PositionSizeResult(
        size_units=round(final_size, 6),
        size_usdt=round(final_value, 2),
        risk_amount_usdt=round(risk_amount, 2),
        risk_percent=round(actual_risk_pct * 100, 2),
        allocation_percent=round(alloc_pct * 100, 2),
        limited_by=limited_by,
        warnings=warnings,
    )
```

### 3.3 Integrasi ke gateway sinyal

**Di `engine/signal_engine.py` (process_signal):**

```python
from engine.position_sizer import calculate_position_size
from engine.trading.trade_manager import get_active_trades

def process_signal(signal_data, account_balance=None):
    # ... existing validation ...

    # === POSITION SIZING (opsional, butuh account_balance) ===
    if account_balance and account_balance > 0:
        # Hitung current open risk dari posisi aktif
        active_trades = get_active_trades()
        current_risk = sum(
            abs(t.entry_price - t.stop_loss) * t.quantity
            for t in active_trades
            if hasattr(t, 'quantity') and t.stop_loss
        )

        size_result = calculate_position_size(
            entry_price=signal_data["entry"],
            stop_loss=signal_data["sl"],
            account_balance=account_balance,
            current_open_risk_usdt=current_risk,
        )

        if size_result:
            signal_data["position_size"] = {
                "units": size_result.size_units,
                "usdt": size_result.size_usdt,
                "risk_usdt": size_result.risk_amount_usdt,
                "risk_pct": size_result.risk_percent,
                "alloc_pct": size_result.allocation_percent,
                "limited_by": size_result.limited_by,
                "warnings": size_result.warnings,
            }

    # ... existing send to Telegram ...
```

### 3.4 Format Telegram (tambahan di sinyal)

```
📊 TRADE SIGNAL — ETH/USDT LONG

Entry: 3,245.00 USDT
SL: 3,120.00 USDT
TP: 3,580.00 USDT
RR: 2.68

💰 Position Size (akun 10,000 USDT):
• Size: 1.6 ETH (~5,192 USDT)
• Risk: 200 USDT (2.0% akun)
• Alokasi: 51.9% akun
• Dibatasi oleh: risk management

⚠️ Macro Context:
• Tidak ada high-impact event dalam 4 jam ✅

⚠️ Ini bukan saran investasi — data dari sistem Aliza. Keputusan dan risiko di kamu.
```

---

## 4. Sumber Account Balance

### Opsi (pilih satu atau kombinasi):

**Opsi A — Config statis (.env / config file)**

```
ACCOUNT_BALANCE=10000
RISK_PER_TRADE=0.02
MAX_ALLOCATION=0.30
```

- Pro: Simpel, cepat implement
- Con: Harus manual update jika balance berubah
- **Cocok untuk MVP**

**Opsi B — Binance API (real-time)**

```python
# Ambil balance dari Binance spot account
from binance.client import Client
balance = client.get_asset_balance(asset='USDT')
account_balance = float(balance['free'])
```

- Pro: Selalu akurat
- Con: Butuh API permission "read balance", tambah dependency
- **Cocok untuk fase 2**

**Opsi C — Telegram command manual**

```
/set_balance 10000
```

- Pro: Fleksibel, user kontrol
- Con: Bisa outdated
- **Cocok sebagai tambahan Opsi A/B**

### Rekomendasi: Mulai dengan Opsi A + C

Set default di `.env`, user bisa override via Telegram command. Fase 2 bisa tambah Opsi B untuk auto-sync.

---

## 5. Edge Cases & Safety

| Case | Handling |
|------|----------|
| Account balance tidak di-set | Skip position sizing, sinyal tetap dikirim tanpa size info |
| SL distance sangat kecil (< 0.5%) | Warning: "SL terlalu dekat, size besar — review manual" |
| Position value > 50% akun | Warning: "Alokasi > 50%, pertimbangkan kurangi size" |
| Semua 3 slot posisi terisi | Risk budget = 0, size = 0, pesan "portfolio penuh" |
| Short trade (entry < SL konseptual) | Formula tetap pakai `abs(entry - sl)` — direction agnostic |
| Leverage | Di luar scope saat ini — Aliza fokus spot swing. Jika ditambah, multiply risk accordingly |

---

## 6. Roadmap Implementasi

| Fase | Scope | Effort |
|------|-------|--------|
| **Fase 1 (MVP)** | `position_sizer.py` + integrasi di gateway + balance dari .env + format Telegram | 1-2 hari |
| **Fase 2** | Telegram command `/set_balance` + persist ke SQLite/config | 0.5 hari |
| **Fase 3** | Binance API auto-balance + recalculate saat scan | 1 hari |
| **Fase 4** | Portfolio-level risk dashboard (total exposure, correlation check) | 2-3 hari |

---

## 7. Cursor AI Prompt (saat siap implement)

Ketika mau mulai implementasi, bilang — saya buatkan prompt Cursor AI yang lengkap dengan SOP template, SAFETY CHECK, dan TEST CASE spesifik untuk Fase 1.

---

*Dokumen ini adalah referensi arsitektur. Implementasi kode dilakukan lewat task terpisah; lihat roadmap §6.*
