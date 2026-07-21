# Dashboard Dotenv Remediation

## 1. Root Cause

The controlled-start failure was traced conclusively to the pre-remediation module-scope call in:

- Module: core.database
- File: /opt/aliza-ai/core/database.py
- Pre-remediation source line: 4
- Call: load_dotenv()

The sanitized systemd journal showed that this call entered python-dotenv and attempted to open /opt/aliza-ai/.env. The dedicated dashboard account correctly lacked permission, producing PermissionError before the application could connect to the database or bind port 8001.

No environment value or credential was read during diagnosis or remediation.

## 2. Dotenv Call Sites Before Remediation

Active production Python call sites before the change were:

| File | Pre-Remediation Behavior |
|---|---|
| core/database.py | Module-scope implicit load_dotenv |
| main.py | Entrypoint implicit load_dotenv |
| interfaces/telegram_bot.py | Entrypoint implicit load_dotenv |
| interfaces/market_bot.py | Entrypoint implicit load_dotenv |
| engine/monitoring/market_monitor.py | Entrypoint implicit load_dotenv |

The dashboard import chain reached core.database through api.server and api.auth.

Historical interfaces/*.bak files also contain older direct calls. They are inactive archive files, are not Python modules in the active import chain, and were not modified.

## 3. Centralized Policy

A new helper was added at core/environment.py.

Policy variable:

- ALIZA_DOTENV_ENABLED

Accepted true values, case-insensitive with surrounding whitespace ignored:

- 1, true, yes, on

Accepted false values:

- 0, false, no, off

Security behavior:

- Missing policy defaults to enabled only for backward-compatible legacy entrypoints.
- Empty or invalid policy raises RuntimeError.
- Invalid policy never falls back to enabled and never accesses a file.
- Disabled policy returns before importing python-dotenv, computing the project dotenv path, or performing discovery/file access.
- Enabled policy computes one explicit project path only after policy approval.
- Enabled policy calls load_dotenv with dotenv_path set explicitly and override=False.
- find_dotenv is never called.
- No parent-directory search, alternate-file fallback, value logging, chmod, or chown workaround was added.

## 4. Dashboard Behavior

scripts/run_dashboard.py now sets ALIZA_DOTENV_ENABLED to false with setdefault before importing Uvicorn or any application module. It then validates the policy through the centralized helper before calling uvicorn.run.

api/server.py independently sets the same fail-closed default before importing core.database. This protects direct dashboard imports that bypass the normal runner.

Consequences:

- The dedicated systemd EnvironmentFile remains the dashboard configuration source.
- The runner does not overwrite an explicit false value.
- The runner and api.server do not overwrite an explicit invalid value.
- An explicit invalid value raises RuntimeError before Uvicorn starts the application.
- Dashboard-disabled policy does not open, stat, discover, or read a dotenv file.
- Existing host, port, loopback validation, docs policy, proxy trust, workers, auth, rate limits, and business routes were not changed.

## 5. Telegram and Legacy Behavior

The five former direct call sites now call load_project_dotenv().

When ALIZA_DOTENV_ENABLED is absent, legacy behavior remains enabled, but is safer:

- Only the explicit project .env path can be loaded.
- Existing process environment values are preserved by override=False.
- No find_dotenv or parent search is used.
- An operator can explicitly disable dotenv or receive fail-closed rejection for an invalid value.

The direct market-monitor entrypoint now inserts the project root before importing the centralized helper, preserving its ability to run as a script.

Telegram was not restarted or modified at runtime. Its existing authorization tests passed with the dotenv loader patched; no live bot or credential was used by the new isolation tests.

## 6. Tests and Validation

| Validation | Result |
|---|---|
| py_compile for all changed Python files | PASS |
| New test_dashboard_dotenv_isolation | 11/11 PASS |
| Required dashboard suite including new module | 99/99 PASS |
| Existing Telegram authorization tests | 6/6 PASS |
| pip check | PASS; no broken requirements |
| git diff --check | PASS |
| Static active-source dotenv inspection | PASS |
| find_dotenv in active production source | None |
| override=True in active production source | None |
| Service start/restart/enable | Not performed |

New tests cover:

- Disabled policy with mocked load_dotenv/find_dotenv and guards against open, stat, and Path.read_text for .env.
- All accepted boolean values.
- Empty and invalid values failing before file access.
- Enabled explicit-path loading with override=False and existing environment preservation.
- Legacy default compatibility using only a temporary dotenv file.
- Runner marker ordering before Uvicorn/application import.
- Preservation of explicit false and invalid values.
- Dashboard import with fake database/heavy modules and a network-connect guard.
- Static enforcement that direct dotenv calls exist only in the helper or tests.
- Central-helper usage by expected legacy call sites.

The new tests use temporary files and fake modules. They do not access the production database, network, model, Nginx, systemd, or production environment files.

## 7. Source Files Changed

Modified:

- api/server.py
- core/database.py
- engine/monitoring/market_monitor.py
- interfaces/market_bot.py
- interfaces/telegram_bot.py
- main.py
- scripts/run_dashboard.py

Added:

- core/environment.py
- test_dashboard_dotenv_isolation.py

Not changed:

- requirements.txt
- systemd
- Nginx
- UFW
- database schema/query logic
- host environment files
- legacy .env permissions
- Telegram runtime service

## 8. Remaining Risks

- The dashboard service was deliberately not started in this remediation task, so database authentication, listener readiness, health, authorization, resource use, and shutdown still require a repeated controlled-start.
- Legacy entrypoints intentionally retain default dotenv loading when the policy is absent. This is backward-compatible but should remain limited to processes that actually need legacy behavior.
- Inactive .bak source archives contain historical direct-load text. They do not affect execution but can create noise in unrestricted recursive grep output.
- core.database still opens a database connection and runs its existing initialization queries at import. That behavior was not changed and must be observed in the controlled-start retry.
- The required dashboard suite emitted existing NumPy reload warnings and expected LLM fallback log messages; all tests still passed.

## 9. Recommendation

Keep aliza-dashboard.service disabled and inactive.

The dotenv blocker is remediated at source and the isolated test suite is green. The next approved action should repeat the controlled-start procedure using the existing dedicated account and environment file. Require:

1. Stable active state with NRestarts=0.
2. Process identity aliza-dashboard:aliza-dashboard.
3. Listener only on 127.0.0.1:8001.
4. Local and public health HTTP 200.
5. Protected routes return 401 without authorization.
6. Nginx stale-route and method regressions remain correct.
7. No source writes or new .pyc files.
8. Clean stop without SIGKILL, timeout, or orphan.
9. Final return to disabled/inactive with port 8001 closed.
