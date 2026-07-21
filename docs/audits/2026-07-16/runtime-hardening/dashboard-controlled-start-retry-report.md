# Dashboard Controlled Start Retry Report

## 1. Verdict

**FAIL**

The dashboard did not achieve a stable startup. The dotenv remediation prevented access to the legacy `/opt/aliza-ai/.env`, but the dedicated service account could not read the newly committed source file `/opt/aliza-ai/core/environment.py`. The unit entered an automatic restart loop before binding port 8001 and was stopped immediately.

No environment value, credential, token, password, hash, cookie, or private material was read or recorded. Final containment succeeded.

## 2. Pre-Start Gates

| Gate | Actual | Result |
|---|---|---|
| Repository HEAD | `935b8b9ebe16616841390ff8c8ffe927493d30ba` | PASS |
| Git working tree | Clean | PASS |
| Dashboard | disabled and inactive | PASS |
| Port 8001 | No listener | PASS |
| Nginx / Telegram | active / active | PASS |
| Nginx syntax | Successful | PASS |
| Runtime identity | `aliza-dashboard:aliza-dashboard` | PASS |
| Environment source | Required dedicated EnvironmentFile | PASS |
| NoNewPrivileges | yes | PASS |
| ProtectSystem | strict | PASS |
| CapabilityBoundingSet | empty | PASS |
| Address families | AF_INET, AF_INET6, AF_UNIX | PASS |
| KillMode / TimeoutStop | control-group / 60 seconds | PASS |

All mandatory gates passed before the controlled start.

## 3. Database Startup Risk Check

The import-time database initialization contains four `CREATE TABLE IF NOT EXISTS` statements for `users`, `chats`, `usage`, and `documents`.

No DROP, TRUNCATE, unconditional DELETE, destructive ALTER, reset, or non-idempotent migration was found. No query was executed manually. The idempotent table initialization was accepted as a non-blocking warning.

## 4. Startup Stability

| Observation | Actual | Result |
|---|---|---|
| Start command | `systemctl start aliza-dashboard.service` only | Accepted |
| First stability poll | activating | FAIL |
| MainPID | 0 | FAIL |
| ExecMainStatus | 1 | FAIL |
| Peak NRestarts captured | 3 | FAIL |
| Listener | None | FAIL |
| Ten-second stable window | Not achieved | FAIL |

The restart loop was detected at the first poll. No further readiness wait was performed.

## 5. Process and Listener Isolation

No stable process remained for runtime identity inspection. No listener appeared on port 8001, including no wildcard IPv4 or IPv6 listener. After stop, no `run_dashboard`, Uvicorn, or `aliza-chat-llm` orphan was present.

## 6. Dotenv Remediation Verification

The retry journal contained no reference to `/opt/aliza-ai/.env` and no dotenv-related PermissionError. The dedicated EnvironmentFile remained configured, and no environment value was printed.

The new blocker was a PermissionError for `/opt/aliza-ai/core/environment.py`. Its host metadata was `ubuntu:ubuntu` mode `0600`, and an effective `test -r` as `aliza-dashboard` failed. This task did not change permissions.

## 7. Health Tests

Local and public health tests were skipped because the backend never established a listener. Testing health after the critical startup failure would not validate the failed runtime.

## 8. Authorization Tests

Protected-route tests were skipped because the backend never became ready. No JWT, password, login, LLM request, database write, trading action, or external transaction was attempted.

## 9. Nginx Regression Tests

The Nginx-only checks were run after the dashboard had been stopped:

- Stale routes: 5 of 5 returned 404.
- Forbidden methods: 3 of 3 returned 403.

## 10. Filesystem Runtime Writes

Metadata-only checks found zero new or modified regular files since the marker in all inspected locations: source API, scripts, virtualenv, data, memory, vector store, dashboard state, and dashboard cache. No new or modified `.pyc` was found in API or scripts. The Git working tree remained clean.

## 11. Resource Observation

Sustained resource sampling was not performed because no stable PID existed. The service failed before a valid health test or fifteen-second observation window could begin.

Baseline capacity before start was approximately 1.7 GiB available RAM, 3.3 GiB free swap, and 23 GiB available on the root filesystem.

## 12. Journal Review

The bounded retry window contained 104 lines. Sanitized classification found seven traceback markers, seven PermissionError markers, thirteen restart lifecycle indicators, no legacy dotenv path, no database authentication or initialization error, no model/cache error, no bind error, no unexpected DDL, and no secret-value pattern.

The unique failure path was `/opt/aliza-ai/core/environment.py`. Raw journal content is not included.

## 13. Shutdown Result

| Check | Actual | Result |
|---|---|---|
| Stop duration | 0.018 seconds | PASS |
| Dashboard state | inactive/dead | PASS |
| Enabled state | disabled | PASS |
| Port 8001 | Closed | PASS |
| Orphan process | None | PASS |
| SIGKILL or timeout evidence | None observed | PASS |

## 14. Final Containment

| Check | Final actual | Result |
|---|---|---|
| Repository HEAD | `935b8b9ebe16616841390ff8c8ffe927493d30ba` | PASS |
| Git working tree | Clean | PASS |
| Dashboard | disabled and inactive | PASS |
| Port 8001 | No listener | PASS |
| Nginx | active | PASS |
| Telegram | active | PASS |

No source, systemd, Nginx, UFW, environment, certificate, database schema, or permission change was made.

## 15. Blockers and Warnings

### Blocker

The dedicated service account cannot read `/opt/aliza-ai/core/environment.py` because the file is owner-only mode `0600`. This prevents application import and causes a restart loop.

### Warnings

- Import-time `CREATE TABLE IF NOT EXISTS` remains existing behavior and was not changed.
- Health, authorization, and sustained resource behavior remain untested because startup failed before readiness.

## 16. Final Recommendation

Do not start or enable `aliza-dashboard.service` again yet. In a separately approved host-permission remediation, make the committed production source readable by the dedicated service account without granting write access or exposing environment files. Re-audit the resulting source-tree read permissions, keep the service disabled, and then repeat this controlled-start procedure.
