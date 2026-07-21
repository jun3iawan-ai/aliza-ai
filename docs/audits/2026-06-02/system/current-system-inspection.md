# ALIZA AI — CURRENT SYSTEM INSPECTION REPORT

> **Status: SUPERSEDED.** Snapshot pada 2025-03-13. Kondisi sistem terkini ada di `docs/README.md` dan report Fase 1–4 (`docs/reports/` — lihat Bagian 3). Jangan jadikan dokumen ini sebagai acuan status aktif.

**Date:** 2025-03-13  
**Scope:** Full system inspection (analysis only, no code modifications)  
**Reference docs:** ALIZA_SYSTEM_PROMPT, ALIZA_ARCHITECTURE_MAP, ALIZA_DEVELOPMENT_RULES, ALIZA_ENGINE_CONTRACTS, ALIZA_AI_BEHAVIOR_RULES, ALIZA_DEBUG_PLAYBOOK, ALIZA_TEST_SYSTEM, ALIZA_SYSTEM_HEALTH_CHECK

---

## 1. Repository Structure

### Major folders and important files

| Folder / path | Status | Notes |
|---------------|--------|-------|
| **engine/** | ✅ Present | Core logic for market, trading, brain, intelligence, detectors, utils, monitoring |
| **interfaces/** | ✅ Present | `telegram_bot.py`, `market_bot.py` |
| **api/** | ✅ Present | `market.py`, `auth.py` only; no `dashboard_api.py` in tree |
| **core/** | ✅ Present | `agent.py`, `database.py`, `knowledge_base.py`, `rag_engine.py`, `skill_loader.py`, `tool_router.py`, `tools.py` |
| **scripts/** | ✅ Present | `server-monitor/`, `deploy/`, `backup_aliza.sh` |
| **docs/** | ✅ Present | `docs/cursor-ai/` with all ALIZA_*.md; `docs/ALIZA_SISTEM_PASCA_UPDATE.md` |
| **dashboard/** | ⚠️ Present but empty of Python | Directory exists; dashboard API endpoints referenced in test doc not under `api/` |
| **data/** | ✅ Present | Intended for `data/aliza.db` (SQLite) |
| **config/** | ✅ Present | Config directory |
| **web/** | ✅ Present | e.g. `web/btc` |
| **memory/** | ✅ Present | `active_document.py`, `document_registry.py`, `memory_manager.py` |
| **knowledge/** | ✅ Present | `vector_store/`, `uploads/`, `documents/` |
| **project/** | ✅ Present | `cleanup_documents.py` |
| **main.py** | ✅ Present | CrewAI CLI loop (not Telegram); no scheduler |

### Engine submodules

| Module | Present | Files (representative) |
|--------|---------|-------------------------|
| **engine/brain/** | ✅ | `trading_brain.py`, `aliza_engine.py` |
| **engine/market/** | ✅ | `market_analyzer.py`, `market_radar.py`, `market_radar_pro.py`, `market_radar_pro_analyzer.py`, `market_snapshot_engine.py`, `market_report_formatter.py`, `market_universe.py`, `dynamic_universe.py`, `coin_id_resolver.py` |
| **engine/trading/** | ✅ | `opportunity_scanner.py`, `signal_engine.py`, `trade_manager.py` |
| **engine/intelligence/** | ✅ Partial | `market_ai_predictor.py`, `market_state_engine.py`, `crypto_intelligence.py`, `document_analyzer.py` |
| **engine/detectors/** | ✅ | `smart_money_tracker.py`, `liquidation_monitor.py` |
| **engine/utils/** | ✅ | `market_cache.py`, `market_cache_updater.py` |
| **engine/monitoring/** | ✅ | `market_monitor.py` |

### Missing or absent relative to docs

- **engine/intelligence/predictive_market_ai.py** — **MISSING**. Referenced by `telegram_bot.py` and `market_state_engine.py`; imports wrapped in try/except, so `/predict` and predictive part of market state degrade gracefully.
- **engine/intelligence/quant_market_model.py** — **MISSING**. Referenced by `telegram_bot.py` and `market_state_engine.py`; same try/except pattern; `/quant` and quant part of market state degrade gracefully.
- **engine/trading/position_manager.py** — **MISSING**. Mentioned in `trade_manager.py` comment only; no file.
- **engine/trading/portfolio_engine.py** — **MISSING**. Same as above; portfolio is implemented inline in Telegram `/portfolio` via `get_active_trades()`.
- **api/dashboard_api.py** or equivalent — **NOT FOUND**. Test doc expects `/health`, `/api/dashboard/market`, etc.; only `api/market.py` and `api/auth.py` exist. Dashboard routes may live elsewhere or be unimplemented.

---

## 2. Telegram Bot Implementation

**File:** `interfaces/telegram_bot.py`

### Command handlers

| Command | Handler | Uses snapshot |
|---------|---------|----------------|
| `/start` | `start` | No (only stores `chat_id`) |
| `/help` | `help_command` | No |
| `/market` | `market` | Yes — `get_market_snapshot()` |
| `/radar` | `radar` | Yes — via `generate_radar_pro()` which uses snapshot |
| `/radarpro` | `radarpro_command` | Yes — same |
| `/setfutures` | `setfutures` | Yes — `scan_opportunities()` → snapshot or cache |
| `/entry` | `entry` | Yes — snapshot for fallback setup when not in `last_opportunities` |
| `/close` | `close` | No (DB only) |
| `/portfolio` | `portfolio` | Yes — `get_market_snapshot()` for price/PnL |
| `/predict` | `predict` | Yes — `get_market_snapshot()` for BTC; needs `predict_market` (missing module) |
| `/quant` | `quant` | Yes — snapshot for BTC; needs `calculate_market_score` (missing module) |
| `/marketstate` | `marketstate_command` | Yes — via `calculate_market_state()` |
| `/status` | `status` | No |
| `/testalert` | `testalert` | No |
| `/marketdebug` | `marketdebug` | Prefers `market_signal("BTC")` if available, else snapshot |

### Commands documented vs implemented

- **Documented (ALIZA_SYSTEM_PROMPT):** `/start`, `/market`, `/radar`, `/radarpro`, `/setfutures`, `/entry`, `/close`, `/portfolio`, `/predict`, `/quant`, `/status`.
- **Implemented:** All of the above, plus `/help`, `/marketstate`, `/testalert`, `/marketdebug`. No documented command is missing.

### Polling

- **Polling:** Yes. `app.run_polling()` is called in `main()` at the end of `telegram_bot.py`. No webhook setup in this file.

### Background jobs

- **Scheduled jobs:** **None.** There is no `BackgroundScheduler`, no `add_job`, and no call to `update_market_snapshot()` anywhere in the codebase. The bot runs only the polling loop.
- **Documented jobs (ALIZA_SYSTEM_PROMPT):** market_snapshot_job, trade_guardian_job, position_management_job, crash_detector_job, whale_tracker_job, altseason_detector_job, signal_engine_job, market_intelligence_job — **none of these are implemented in the current repo.**

**Conclusion:** Telegram bot is command-only; no background jobs, and no automatic snapshot refresh.

---

## 3. Market Data Pipeline

**Intended flow (docs):**  
External APIs → market_analyzer → market_radar → TradingBrain → trade_setup.

### Actual flow

1. **market_cache** (`engine/utils/market_cache.py`)
   - `get_market_data(symbol)` / `get_all_market_data()` call `market_signal(symbol)` and cache for 180s.
   - Used by `opportunity_scanner` when snapshot is stale (>90s).

2. **market_analyzer** (`engine/market/market_analyzer.py`)
   - `market_signal(symbol)`: CoinGecko chart, Fear & Greed, dominance → price, trend, RSI, support/resistance.
   - Calls `market_radar(fear, dominance)` for radar fields.
   - Builds `market_data` and calls `TradingBrain().analyze(market_data)` to attach `trade_setup`.
   - Returns full market_data dict (contract shape).

3. **market_radar** (`engine/market/market_radar.py`)
   - Inputs: fear, dominance from analyzer.
   - Uses: `crypto_intelligence` (funding, altseason), `smart_money_tracker`, `liquidation_monitor`, `market_ai_predictor` (phase, bull_probability, market_risk_score), whale API.
   - Returns cycle_phase, funding_status, whale_activity, stablecoin_flow, open_interest_level, liquidation_risk, market_phase_prediction, bull_probability, market_risk_score, etc.

4. **TradingBrain** (`engine/brain/trading_brain.py`)
   - Consumes market_data (price, trend, rsi, support, resistance).
   - Produces trade_setup: setup, entry, sl, tp1, tp2, risk_reward, confidence, risk_quality (TP capped ±8%).

5. **market_snapshot_engine** (`engine/market/market_snapshot_engine.py`)
   - `update_market_snapshot()`: for each tradable coin calls `market_signal(symbol)`, validates, optional radar retry, retry failed after 30s; writes to global `market_snapshot`.
   - **Not called by any job or entrypoint** in the repo — snapshot is only updated if something explicitly calls `update_market_snapshot()`.
   - `get_market_snapshot()`: returns current `{"data": {...}, "timestamp": ...}`.

### Snapshot usage by Telegram commands

- **Yes.** `/market`, `/radar`, `/radarpro`, `/setfutures`, `/entry` (fallback), `/portfolio`, `/predict`, `/quant`, `/marketstate` use snapshot or code paths that prefer snapshot (e.g. opportunity_scanner uses snapshot when age ≤ 90s). `/marketdebug` may call `market_signal("BTC")` if the import succeeds, which bypasses snapshot for that one command.

---

## 4. Trading Engine

**Location:** `engine/trading/`

### opportunity_scanner

- **File:** `opportunity_scanner.py`.
- **Role:** Build list of opportunities from market data. Uses `get_market_snapshot()` first; if snapshot older than 90s and `get_all_market_data` available, uses cache.
- **Logic:** For each coin, requires `trade_setup`, `risk_reward` ≥ 1.3; builds list with coin, setup, entry, sl, tp1, tp2, rr, trend, confidence, risk_quality; sorted by rr descending.
- **Output:** List of opportunity dicts; used by `/setfutures` and `/entry` (via `last_opportunities`).

### signal_engine

- **File:** `signal_engine.py`.
- **Role:** High-quality signals for alerts. Uses `get_market_snapshot()` (or `get_all_market_data()` if no snapshot).
- **Logic:** Filters by RR ≥ 3 and confidence ≥ 70; picks best by rr; adds `btc_trend` and `market_risk` from snapshot.
- **Output:** Single best signal dict or None. Exposes `format_signal_message`, `can_send_signal`, `record_signal_sent` (no-op). **No job calls this** in the repo, so no automatic signal alerts are sent.

### trade_manager

- **File:** `trade_manager.py`.
- **Role:** Single point of write to SQLite for trades. Implements create_trade, get_active_trades, close_trade, trade_direction; schema and behavior described in §8 below.

### position_manager

- **Missing.** No `position_manager.py`. Comment in `trade_manager` references it; position monitoring is not implemented as a separate module.

### portfolio_engine

- **Missing.** No `portfolio_engine.py`. Portfolio display is implemented inside the Telegram `/portfolio` handler using `get_active_trades()` and `get_market_snapshot()`.

### Trade setup generation and usage

- **Generation:** Trade setups are produced by `TradingBrain.analyze(market_data)` inside `market_analyzer.market_signal(symbol)` and stored in `market_data["trade_setup"]`.
- **Usage:** Snapshot (when updated) and cache hold per-coin market_data including trade_setup. `opportunity_scanner` filters by RR ≥ 1.3; `signal_engine` filters by RR ≥ 3 and confidence ≥ 70. `/setfutures` shows top opportunities; `/entry` creates a trade from selected opportunity or from snapshot trade_setup for that coin.

---

## 5. Intelligence Modules

**Location:** `engine/intelligence/`

| Module | Exists | Purpose (current) |
|--------|--------|--------------------|
| **market_ai_predictor** | ✅ | Pure functions: `market_phase()`, `bull_probability()`, `market_risk_score()`. Used by `market_radar` to fill radar dict. No LLM; rule-based. |
| **market_state_engine** | ✅ | Aggregates BTC snapshot with optional predictive and quant results; outputs market_bias, market_risk, crash_probability, bull_probability, trend, whale_activity. Used by `/marketstate`. Tries to import `predictive_market_ai` and `quant_market_model`; if missing, continues with snapshot-only. |
| **crypto_intelligence** | ✅ | Funding rate (Binance), funding analysis, altseason index/status. Used by `market_radar`. |
| **document_analyzer** | ✅ | Present; not inspected in detail for this report. |
| **predictive_market_ai** | ❌ | **Missing.** Expected: `predict_market`, `format_prediction_report`, `calculate_market_predictions`. Bot and market_state_engine use try/except; `/predict` shows “Modul prediksi belum tersedia” when missing. |
| **quant_market_model** | ❌ | **Missing.** Expected: `calculate_market_score`, `format_quant_report`. Same pattern; `/quant` shows “Modul quant belum tersedia” when missing. |
| **market_intelligence** | ❌ | **Not present** as a module. Architecture map lists “Market Intelligence” as a component; no dedicated file.

---

## 6. Data Contracts

### market_data structure

- **Source:** Output of `market_analyzer.market_signal(symbol)`.
- **Checked:** `market_analyzer.py` return dict includes: symbol, price, trend, rsi, support, resistance, fear_greed, dominance, cycle_phase, funding_status, whale_activity, stablecoin_flow, open_interest_level, liquidation_risk, market_phase_prediction, bull_probability, market_risk_score, trade_setup, timestamp.
- **Contract (ALIZA_ENGINE_CONTRACTS):** Same set of fields; type and semantics match. **Compliant.**

### trade_setup structure

- **Source:** `TradingBrain.analyze()` in `trading_brain.py`.
- **Fields:** setup, entry, sl, tp1, tp2, risk_reward, confidence, risk_quality. (coin/symbol is on the parent market_data.)
- **Contract (ALIZA_DEVELOPMENT_RULES):** coin, setup, entry, sl, tp1, tp2, risk_reward, confidence, risk_quality. “coin” is at market_data level; trade_setup itself has the rest. **Compliant.**

### opportunity structure

- **Source:** `opportunity_scanner.scan_opportunities_from_data()`.
- **Fields:** coin, setup, entry, sl, tp1, tp2, rr, trend, confidence, risk_quality. Matches usage in `/setfutures` and `/entry`. Contract not explicitly spelled in ENGINE_CONTRACTS; structure is consistent. **Compliant in practice.**

### signal structure

- **Source:** `signal_engine.scan_for_signals()`.
- **Fields:** coin, setup, entry, sl, tp1, tp2, rr, confidence, trend, btc_trend, market_risk. Used by `format_signal_message`. **Consistent.**

**Summary:** market_data and trade_setup match the documented contracts; opportunity and signal are consistent with usage and expectations.

---

## 7. Snapshot System

**File:** `engine/market/market_snapshot_engine.py`

### How snapshot is generated

- **Function:** `update_market_snapshot()`.
- **Steps:** Gets coin list from `get_tradable_coins()` (fallback `MAJOR_COINS`). For each symbol calls `_fetch_with_radar_retry(symbol)` which uses `market_signal(symbol)`. Validates (price, trend, rsi, support/resistance present; no error). If cycle_phase or whale_activity is UNKNOWN, retries once after 2s. Failed symbols retried once after 30s. Valid results stored in global `market_snapshot["data"]`; `market_snapshot["timestamp"]` set to `datetime.utcnow()`.

### Refresh interval

- **Designed:** Doc says “Snapshot diupdate setiap 60 detik” — but there is **no scheduler or job** calling `update_market_snapshot()`. Constant `MAX_AGE_SEC = 300` exists but no automatic 60s (or any) refresh is implemented. Snapshot only updates when some code path calls `update_market_snapshot()`; in the current codebase **no such caller exists**.

### Which modules use snapshot

- **Read-only usage:** `get_market_snapshot()` is used by:
  - `interfaces/telegram_bot.py` (market, radar, radarpro, setfutures, entry fallback, portfolio, predict, quant, marketstate; marketdebug fallback).
  - `engine/trading/opportunity_scanner.py` (primary data when age ≤ 90s).
  - `engine/trading/signal_engine.py` (source of market data and BTC context).
  - `engine/market/market_radar_pro_analyzer.py` (radar pro from snapshot).
  - `engine/intelligence/market_state_engine.py` (BTC and state aggregation).

---

## 8. Database

**File:** `engine/trading/trade_manager.py`  
**DB path:** `data/aliza.db`

### SQLite schema

- **Table:** `trades`.
- **Columns:** id (INTEGER PRIMARY KEY AUTOINCREMENT), coin (TEXT), setup (TEXT), entry (REAL), stop_loss (REAL), tp1 (REAL), tp2 (REAL), status (TEXT), created_at (TEXT). Optional migration adds `direction` (TEXT) if missing.
- **Initialization:** `init_trade_db()` creates table if not exists and ensures `direction` column.

### create_trade(coin, setup, entry, sl, tp1, tp2)

- Derives `direction` from setup (LONG if "LONG" in setup or setup == "OVERSOLD BOUNCE", else SHORT). Inserts one row with status `OPEN` and `created_at` in ISO format. Uses direction column if present.

### get_active_trades()

- Returns list of tuples: (coin, direction, setup, entry, stop_loss, tp1, tp2) for rows with status = 'OPEN'. Direction from DB or derived from setup for older rows.

### close_trade(coin)

- Updates rows with given coin and status 'OPEN' to status 'CLOSED'. Returns True if at least one row updated.

**Conclusion:** Single module for DB writes; schema and APIs are clear and match doc intent.

---

## 9. Potential Problems

| Issue | Severity | Description |
|------|----------|-------------|
| **Snapshot never updated** | **Critical** | No job or startup code calls `update_market_snapshot()`. Snapshot stays empty or stale; all snapshot-dependent commands may show no or old data unless something else populates it. |
| **No background jobs** | **Critical** | No scheduler; no market_snapshot_job, no signal_engine_job, no trade_guardian, position_management, etc. Doc’s “Background Jobs” section does not match implementation. |
| **Missing predictive_market_ai** | High | `/predict` and part of market_state use optional import; they work but with “Modul prediksi belum tersedia” or reduced state. |
| **Missing quant_market_model** | High | Same for `/quant` and quant part of market_state. |
| **/marketdebug can bypass snapshot** | Medium | If `market_signal` is imported, handler calls `market_signal("BTC")` directly, against “Telegram jangan panggil API langsung” for that command. |
| **API uses live API** | Medium | `api/market.py` uses `btc_signal()` (i.e. `market_analyzer`), not snapshot. Doc restricts “no direct API” to Telegram; API behavior is consistent with that but worth noting. |
| **position_manager / portfolio_engine missing** | Low | Referenced in comments; behavior covered by trade_manager + inline portfolio in Telegram. |
| **Dashboard API endpoints** | Low | Test doc lists `/health`, `/api/dashboard/market`, etc.; no such routes under `api/` in this tree. May be in another service or not implemented. |
| **Signal engine never run on schedule** | High | No automatic signals to Telegram; `scan_for_signals()` and `format_signal_message` exist but are never invoked by the bot. |
| **Dead or optional code** | Low | `record_signal_sent` is no-op; `market_signal` optional in telegram_bot for marketdebug; dynamic_universe optional for tradable coins. |

---

## 10. System Health Summary

| Area | Status | Notes |
|------|--------|-------|
| **System architecture** | ⚠️ Partial | engine/, interfaces/, api/, core/, scripts/, docs/ present. Missing: predictive_market_ai, quant_market_model, position_manager, portfolio_engine; no scheduler. |
| **Telegram bot** | ⚠️ Partial | All documented commands implemented; polling works; **no background jobs**; snapshot-dependent commands depend on snapshot never being updated. |
| **Market pipeline** | ✅ OK | market_cache → market_analyzer → market_radar → TradingBrain → trade_setup chain is implemented and used. Snapshot *consumer* side is correct; *producer* (update) is never called. |
| **Trading engine** | ✅ OK | opportunity_scanner, signal_engine, trade_manager work as designed. position_manager/portfolio_engine absent but behavior covered elsewhere. |
| **Snapshot engine** | ❌ Broken | Logic and contracts are correct, but **nothing calls `update_market_snapshot()`**, so snapshot is never refreshed. |
| **Database** | ✅ OK | SQLite schema, create_trade, get_active_trades, close_trade implemented and used correctly. |

### Classification: **CRITICAL ISSUES**

**Reasons:**

1. **Snapshot never updated** — Core design (Telegram uses snapshot, updated every 60s) is not implemented; snapshot stays empty/stale.
2. **No background jobs** — All documented jobs (market_snapshot_job, signal_engine_job, etc.) are absent; no periodic snapshot refresh, no automatic signals, no guardians.
3. **Missing intelligence modules** — predictive_market_ai and quant_market_model are referenced but missing; /predict and /quant and part of market state are degraded.

**Recommendations (for future work, no code change in this inspection):**

- Add a scheduler (e.g. APScheduler) next to the Telegram app and schedule at least `update_market_snapshot()` every 60s (or as per doc).
- Optionally schedule signal_engine job and other documented jobs if desired.
- Implement or restore `predictive_market_ai` and `quant_market_model` if /predict and /quant and full market_state are required.
- Ensure a single entrypoint (e.g. bot startup) calls `update_market_snapshot()` at least once so first user sees data even before first scheduled run.

---

*End of report.*
