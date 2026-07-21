# Aliza AI Remediation Plan

> **Status: SUPERSEDED.** Snapshot pada 2026-07-15. Kondisi sistem terkini ada di `docs/README.md` dan report Fase 1–4 (`docs/reports/` — lihat Bagian 3). Jangan jadikan dokumen ini sebagai acuan status aktif.

## Immediate Containment

- Keep all live trading disabled; explicitly label every signal and quantity as research/uncalibrated.
- Bind the dashboard to loopback/private network or firewall port 8001 until authentication is enforced (ALIZA-008).
- Restrict `.env`, SQLite, JSON state, and logs to the dedicated service user; rotate exposed credentials without displaying them (ALIZA-007).
- Require a Telegram chat allowlist globally; disable state-changing commands until verified (ALIZA-009).
- Stop using signal outcome statistics for confidence adjustment or performance claims (ALIZA-004, ALIZA-011, ALIZA-013).
- Document that SL/TP are advisory and not exchange-side (ALIZA-006).

## P0 — Before Any Live Trading

No P0 was proven in this static audit. This does not authorize live trading: unresolved P1 risk/execution/reconciliation findings remain mandatory blockers.

## P1 — Before Paper-to-Live Promotion

### ALIZA-001 — Closed-candle feature pipeline

- Change: consume timestamped OHLC, exclude open candle, remove ticker append from indicator series, store cutoff/source timestamps.
- Target: `engine/market/market_analyzer.py`, klines cache/schema.
- Acceptance: feature values do not change before next candle close; every signal records cutoff.
- Required tests: 4h/1d boundary replay, intrabar spike, delayed/out-of-order candle.
- Dependency: market-data schema.
- Effort: M.

### ALIZA-002 — Independent timeframe semantics

- Change: prohibit a common unresampled series from masquerading as both 4h and 1d; fail closed or resample correctly.
- Target: `engine/market/market_analyzer.py`, `multi_timeframe_analyzer.py` caller contract.
- Acceptance: missing timeframe returns UNKNOWN; strong alignment requires independent closed candles.
- Required tests: Binance outage, CoinGecko fallback, missing 4h, missing 1d.
- Dependency: ALIZA-001.
- Effort: M.

### ALIZA-003 — Source-level freshness and completeness gate

- Change: validate source timestamps, expected cadence, gaps/duplicates/order, minimum universe, BTC context, and per-field provenance.
- Target: snapshot engine and scanner.
- Acceptance: partial/stale/gapped snapshot cannot enter strategy path; alert reason is observable.
- Required tests: stale source wrapped by fresh local clock, partial universe, missing BTC, clock skew.
- Dependency: ALIZA-001.
- Effort: M.

### ALIZA-004 — Valid historical validation framework

- Change: quarantine tracker-derived metrics; build next-bar, closed-OHLC simulator with explicit side and conservative same-bar ordering.
- Target: new research-only backtest package sharing feature/strategy code with live analysis.
- Acceptance: deterministic replay; fees/spread/slippage/funding/latency/gaps included; train/tune/OOS separated chronologically.
- Required tests: long/short outcomes, gap fills, same-bar SL/TP, precision, walk-forward and parameter sensitivity.
- Dependency: ALIZA-001/002 and versioned data.
- Effort: L.

### ALIZA-005 — Authoritative risk service

- Change: consolidate risk checks and state; fail closed on dependencies; add daily loss, equity drawdown, exposure, margin/leverage, liquidity/spread/slippage and health limits with atomic reservation.
- Target: risk modules, manual entry, future executor.
- Acceptance: no submission path can bypass the same final gate; two concurrent requests cannot exceed limits.
- Required tests: TOCTOU, DB outage, stale balance, daily loss, drawdown, max notional, correlated exposure, NaN/inf.
- Dependency: canonical portfolio ledger and future OMS.
- Effort: L.

### ALIZA-006 — OMS, executor, protection, and reconciliation

- Change: design durable order/fill/position state machine, unique client order IDs, idempotent submission, ambiguous-timeout lookup, partial fills, reduce-only exits, exchange-side SL, startup/periodic reconciliation.
- Target: new isolated execution package and database schema; do not bolt calls onto Telegram handlers.
- Acceptance: every order maps signal→risk reservation→client ID→fills→position; unknown states halt and reconcile; protected position survives process loss.
- Required tests: ACK timeout, duplicate retry, partial/multiple fill, cancel race, restart, orphan order/position, stop failure, hedge/one-way mode.
- Dependency: exchange mock/sandbox, ALIZA-005, ledger/migrations.
- Effort: L.

### ALIZA-007 — Secret and state hardening

- Change: dedicated service user, owner-only permissions, secret manager/environment-file hardening, credential rotation, log redaction.
- Target: deployment/systemd/filesystem.
- Acceptance: no non-service account can read secrets/state; rotated keys have no withdrawal and are IP-restricted.
- Required tests: permission scan and redaction test.
- Dependency: operations access/manual exchange verification.
- Effort: S.

### ALIZA-008 — API authentication and authorization

- Change: private bind until fixed; Argon2/bcrypt, mandatory high-entropy JWT secret, JWT verification, RBAC on admin/dashboard/chat, rate limiting and audit log.
- Target: `api/auth.py`, `api/server.py`, deployment proxy.
- Acceptance: anonymous/admin-role tests enforce least privilege; no literal secret fallback.
- Required tests: unauthorized access, token expiry/tampering, role escalation, brute force, rate limits.
- Dependency: user/session design and TLS perimeter.
- Effort: M.

### ALIZA-009 — Telegram authorization

- Change: global handler guard using immutable allowlist; production fails closed if not configured; authorize every mutating command.
- Target: `interfaces/telegram_bot.py`.
- Acceptance: unknown chat cannot start, set balance, entry, close, or invoke privileged diagnostics.
- Required tests: allowed/denied group/private chat and missing-config cases.
- Dependency: operator chat-ID registry.
- Effort: S.

## P2 — Reliability and Quality Improvements

### ALIZA-010 / ALIZA-011 — Durable signal/trade lifecycle

- Introduce unique signal/trade IDs, explicit generated→validated→sent/rejected→expired lifecycle, atomic transactions, unique idempotency constraints, absolute DB paths, and post-send tracking.
- Acceptance: crash/concurrent replay produces one durable state and no phantom signal.
- Tests: concurrent writers, disk-full, crash between send and record, restart replay.
- Effort: M.

### ALIZA-012 — Instrument-aware sizing

- Use Decimal and exchange metadata; validate finite ranges; account for fees, slippage, gap risk, contract multiplier, leverage and conservative rounding.
- Acceptance: quantity passes venue filters and worst-case risk remains within budget.
- Tests: property/boundary cases for each market type.
- Effort: M.

### ALIZA-013 — Honest confidence semantics

- Rename existing field to heuristic score until calibrated; version formula and data; expose sample size and uncertainty.
- Acceptance: probability wording only appears after OOS calibration thresholds are met.
- Tests: Brier/log loss, reliability curve, regime/drift monitoring.
- Effort: M.

### ALIZA-014 — Score contract

- Define score range once and make alert thresholds valid/config-checked.
- Acceptance: startup rejects impossible threshold; max fixture alerts exactly once.
- Tests: boundary table and config validation.
- Effort: S.

### ALIZA-015 — Database lifecycle/readiness

- Remove connection/DDL side effects from imports; use explicit versioned migration and pooled/request-scoped connections; make readiness check DB and snapshot age.
- Acceptance: importing modules causes no network/write; unhealthy dependency makes readiness fail.
- Tests: import-no-write, DB restart/stale pool, migration rollback, readiness.
- Effort: M.

### ALIZA-016 — Test and observability baseline

- Add CI with unit, integration, historical replay and failure-injection suites; replace broad silent catches in risk/data paths; emit structured reason codes and metrics.
- Acceptance: critical fallback is observable and tested; zero silent fail-open in risk/execution.
- Tests: contract, dependency failure, stale data, concurrency, resource exhaustion.
- Effort: L.

## P3 — Maintainability Improvements

### ALIZA-017 — Canonical deployment

- Consolidate `/opt` vs `/home` paths, put dashboard under a real unit, remove stray worktree artifacts, expose commit/version, and enforce clean immutable releases.
- Acceptance: process CWD and version endpoint match deployment manifest; rollback is documented and tested.
- Tests: deploy/rollback smoke test in non-production.
- Effort: S.

## Recommended Rollout

1. Static fixes and immediate containment.
2. Unit tests for market data, risk, sizing, auth, and lifecycle.
3. Integration tests with an exchange mock; no production credentials.
4. Historical replay with versioned closed-candle data.
5. Shadow mode with immutable audit records and acceptance thresholds.
6. Realistic paper trading with fill/cost/accounting simulation.
7. Failure injection: exchange timeout, DB outage, restart, disk full, clock skew, duplicate events.
8. Micro-live only after all P1 blockers and go-live checklist items are independently verified, using minimal capital and no-withdrawal/IP-restricted keys.
9. Controlled scaling based on exposure, drawdown, reconciliation and operational SLOs—not confidence labels.
10. Automatic rollback/halt criteria: stale data, reconciliation mismatch, unprotected position, daily loss/drawdown breach, repeated order ambiguity, or dependency health failure.

