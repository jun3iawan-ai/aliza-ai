# Dashboard Controlled Start Retry 3 Report

## 1. Verdict

**PASS WITH WARNINGS**

The dashboard achieved stable startup, used the dedicated account, bound only to 127.0.0.1:8001, passed local/public health, produced no startup/journal security error, preserved unauthorized database row counts, passed Nginx regressions, remained resource-stable, and stopped cleanly.

The corrected authorization criterion distinguishes registered protected routes from unregistered routes. Exact `GET /admin` is not registered and therefore correctly returned fail-closed 404. The three tested registered protected routes returned 401 without JWT. No request returned 200, fell through to the SPA, became 502 while the backend was live, disclosed internals, or demonstrated an authorization bypass.

No secret, credential, environment value, connection URI, raw traceback, or raw database error is included.

## 2. Pre-Start Gates

| Gate | Actual | Result |
|---|---|---|
| Repository HEAD | `935b8b9ebe16616841390ff8c8ffe927493d30ba` | PASS |
| Git working tree | Clean | PASS |
| Dashboard | disabled and inactive | PASS |
| Port 8001 | No listener | PASS |
| Nginx / Telegram / market / PostgreSQL | active / active / active / active | PASS |
| Nginx syntax | Successful | PASS |
| Runtime account | Dedicated UID/GID 998/999; no supplementary groups | PASS |
| Dedicated EnvironmentFile | `0640 root:aliza-dashboard`, readable | PASS |
| Required source files | `0640 ubuntu:aliza-dashboard`, readable | PASS |
| Legacy dotenv | Not readable by dashboard account | PASS |
| User / Group | aliza-dashboard / aliza-dashboard | PASS |
| NoNewPrivileges / ProtectSystem | yes / strict | PASS |
| CapabilityBoundingSet | empty | PASS |

## 3. Pre-Start Database Validation

A collected transient systemd unit ran as the dashboard account with the production EnvironmentFile, `NoNewPrivileges=yes`, and bytecode writing disabled. It used direct psycopg2, a five-second timeout, and only `SELECT 1`, rollback, and close.

Result: **PRESTART_DB_CONNECTION_SUCCESS**.

The checker and transient unit were removed/collected before final containment.

## 4. Runtime Source Readability

The approved `git ls-files` inventory found:

| Total | Readable | Unreadable |
|---:|---:|---:|
| 114 | 114 | 0 |

No permission was changed.

## 5. Startup Stability

| Observation | Actual | Result |
|---|---|---|
| Start command | `systemctl start aliza-dashboard.service` only | PASS |
| Stable PID | 496915 | PASS |
| Stable active window | More than 15 continuous seconds | PASS |
| NRestarts | 0 | PASS |
| ExecMainStatus | 0 | PASS |
| Listener | 127.0.0.1:8001 | PASS |

An initial textual identity check was inconclusive because `ps` truncated the long user/group names. Numeric verification immediately confirmed UID 998 and GID 999, after which the full stability window passed without restarting the service.

## 6. Process and Listener Isolation

The process remained active/running as UID/GID 998/999 with one stable PID. The only port-8001 listener was 127.0.0.1:8001, owned by that PID. No `0.0.0.0:8001` or `[::]:8001` listener appeared. The service remained disabled.

## 7. Journal Review

The final bounded startup/runtime window contained 16 journal lines.

| Indicator | Count |
|---|---:|
| PermissionError | 0 |
| Legacy dotenv reference | 0 |
| Traceback | 0 |
| Database authentication failure | 0 |
| Database initialization failure | 0 |
| Model/cache failure | 0 |
| Bind failure | 0 |
| Environment validation failure | 0 |
| ProtectSystem denial | 0 |
| Restart event | 0 |
| Secret-value pattern | 0 |
| Unauthorized LLM marker | 0 |
| Unauthorized chat/usage write marker | 0 |

## 8. Health Tests

| Test | Result | Body/security validation |
|---|---|---|
| Loopback health | HTTP 200 | Minimal `status=ok`, 15 bytes, no disclosure or wildcard CORS |
| Public health | HTTP 200 | Same minimal body; no-store; HSTS max-age 300; nosniff; frame deny; no-referrer; no wildcard CORS |

Temporary body/header files were removed.

## 9. Authorization Tests

| Request | Route Registered | Expected | Actual | Result |
|---|---|---:|---:|---|
| GET `/api/market/btc` without JWT | Yes | 401 | 401 | PASS |
| POST `/api/chat` without JWT | Yes | 401 | 401 | PASS |
| GET `/admin/stats` without JWT | Yes | 401 | 401 | PASS |
| GET `/admin` without JWT | No | 404 | 404 | EXPECTED / PASS |

Static route inspection found no exact `GET /admin`. The registered admin routes are `GET /admin/stats` and `GET /admin/users`; both use `Depends(require_admin)`. That dependency uses `Depends(get_current_user)`, returns 401 for missing or invalid bearer credentials, and returns 403 for an authenticated non-admin. The observed `/admin/stats` response therefore confirms the registered admin surface remains protected without JWT. Exact `/admin` correctly remained a backend 404 rather than a SPA fallback.

All four tested responses were JSON rather than SPA, carried no-store and all four security headers, and contained no internal disclosure. No request returned 200 or 502, and no authorization bypass was observed.

## 10. Database Side-Effect Check

Count-only snapshots for `users`, `chats`, `usage`, and `documents` were taken as the local PostgreSQL administrator immediately before and after a repeated set of unauthorized requests.

Result: **all before/after counts equal**.

No row content was read. The unauthorized chat produced no database count change and no LLM/write journal marker.

## 11. Nginx Regression Tests

- Stale routes: 5 of 5 returned 404.
- Forbidden methods: 3 of 3 returned 403.

## 12. Filesystem Runtime Writes

Metadata-only checks found no changed file in source, interfaces, scripts, virtualenv, memory, vector store, state, or cache paths, and no new or modified source `.pyc`.

Two files changed in the explicitly allowlisted `/opt/aliza-ai/data` runtime path. Their contents were not opened. Git and tracked source remained clean.

| Relative path | File type | Owner | Group | Mode | Size | Modification time | Git state | Static source reference | Classification |
|---|---|---|---|---:|---:|---|---|---|---|
| `data/aliza.db` | Regular file; SQLite/database state by name and source reference | ubuntu | aliza-dashboard | 0660 | 36,864 bytes | 2026-07-16 12:31:36.636617834 +0700 | Not tracked; ignored by `data/` | `engine/trading/trade_manager.py`; `engine/trading/signal_tracker.py` | `EXPECTED_RUNTIME_STATE` |
| `data/signal_state.json` | Regular file; JSON signal state by name and source reference | ubuntu | aliza-dashboard | 0660 | 708 bytes | 2026-07-16 12:31:37.512618115 +0700 | Not tracked; ignored by `data/` | `engine/state_store.py` | `EXPECTED_RUNTIME_STATE` |

The database/state classification is based only on path names and static source references. Neither file was opened, queried, hashed, or otherwise read.

## 13. Resource Observation

Three samples were taken 15 seconds apart.

| Metric | Sample 1 | Sample 2 | Sample 3 | Assessment |
|---|---:|---:|---:|---|
| MainPID | 496915 | 496915 | 496915 | Stable |
| MemoryCurrent | 49,655,808 | 49,655,808 | 49,655,808 | Stable |
| TasksCurrent | 8 | 8 | 8 | Stable |
| Threads | 8 | 8 | 8 | Stable |
| Open file descriptors | 16 | 16 | 16 | Stable |
| NRestarts | 0 | 0 | 0 | Stable |
| Listener | 127.0.0.1:8001 | same | same | Stable |

CPU usage increased only by small amounts consistent with observation overhead. Resource warning: **none**.

## 14. Shutdown Result

| Check | Actual | Result |
|---|---|---|
| Stop duration | 0.179 seconds | PASS |
| Dashboard state | inactive/dead | PASS |
| Enablement | disabled | PASS |
| Port 8001 | Closed | PASS |
| Orphan process | None | PASS |
| SIGKILL / shutdown timeout | None | PASS |

## 15. Final Containment

| Check | Final state | Result |
|---|---|---|
| Repository HEAD | `935b8b9ebe16616841390ff8c8ffe927493d30ba` | PASS |
| Git working tree / diff check | Clean | PASS |
| Dashboard | disabled and inactive | PASS |
| Port 8001 | No listener | PASS |
| Nginx / Telegram / market / PostgreSQL | active / active / active / active | PASS |
| Temporary checker, responses, counts, markers, transient unit | Removed/collected | PASS |

No source, permission, systemd, Nginx, UFW, environment, database, pg_hba, certificate, dependency, commit, or push change was made.

## 16. Warnings

- Exact `/admin` has no landing endpoint. Its 404 is expected fail-closed behavior, not an authorization bypass or SPA exposure.
- `data/aliza.db` changed and is classified `EXPECTED_RUNTIME_STATE` from metadata and static source references only.
- `data/signal_state.json` changed and is classified `EXPECTED_RUNTIME_STATE` from metadata and static source references only.
- All other runtime, security, resource, database-side-effect, and shutdown checks passed.

## 17. Final Recommendation

The controlled-start security/runtime test passed with the warnings above. Keep `aliza-dashboard.service` disabled and inactive. The deployment is ready to proceed to an authenticated functional test, but is not ready for permanent enablement. Retain fail-closed 404 for unregistered exact `/admin` and 401/403 enforcement on registered protected routes; do not add an `/admin` landing route or weaken Nginx routing to transform the 404.
