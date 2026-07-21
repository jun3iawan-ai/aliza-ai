# Dashboard Controlled Start Retry 2 Report

## 1. Verdict

**FAIL**

The source-permission remediation passed all pre-start and runtime-readability checks, but the dashboard did not achieve stable startup. PostgreSQL authentication failed during import-time database connection, the unit entered an automatic restart loop, and no listener was created. The service was stopped immediately.

No environment value, credential, token, password, API key, cookie, hash, or private material was read or recorded. Final containment succeeded.

## 2. Pre-Start Gates

| Gate | Actual | Result |
|---|---|---|
| Repository HEAD | `935b8b9ebe16616841390ff8c8ffe927493d30ba` | PASS |
| Git working tree | Clean | PASS |
| Dashboard | disabled and inactive | PASS |
| Port 8001 | No listener | PASS |
| Nginx / Telegram | active / active | PASS |
| Nginx syntax | Successful | PASS |
| Service account | Dedicated account; no supplementary groups | PASS |
| Source remediation metadata | Both files `0640 ubuntu:aliza-dashboard` | PASS |
| Required source readability | Allowed | PASS |
| Legacy dotenv readability | Denied | PASS |
| Source write access | Denied | PASS |
| User / Group | `aliza-dashboard:aliza-dashboard` | PASS |
| NoNewPrivileges / ProtectSystem | yes / strict | PASS |
| CapabilityBoundingSet | empty | PASS |

All mandatory gates passed before start.

## 3. Runtime Source Readability

The recheck used `git ls-files` for the approved runtime source/config paths and excluded environment files, backups, docs, tests, key/certificate material, virtualenv, and data/state paths.

| Checked | Readable | Unreadable |
|---:|---:|---:|
| 114 | 114 | 0 |

No permission was changed during this controlled-start task.

## 4. Database Startup Risk

The import-time database code contains four idempotent `CREATE TABLE IF NOT EXISTS` statements for `users`, `chats`, `usage`, and `documents`. No DROP, TRUNCATE, unconditional DELETE, destructive ALTER, or reset operation was found. No query was run manually.

## 5. Startup Stability

| Observation | Actual | Result |
|---|---|---|
| Start command | `systemctl start aliza-dashboard.service` only | Accepted |
| First stability poll | activating | FAIL |
| MainPID | 0 | FAIL |
| ExecMainStatus | 1 | FAIL |
| Peak NRestarts captured | 3 | FAIL |
| Listener | None | FAIL |
| Stable ten-second window | Not achieved | FAIL |

The restart loop was detected on the first poll and triggered immediate shutdown.

## 6. Process and Listener Isolation

No stable PID remained for process inspection. No listener appeared on port 8001, including no wildcard IPv4 or IPv6 listener. No dashboard-related orphan remained after stop.

## 7. Dotenv and Permission Verification

The bounded retry journal contained no legacy `/opt/aliza-ai/.env` reference and no PermissionError. Both remediated source files remained `0640 ubuntu:aliza-dashboard`, and all 114 in-scope runtime source/config files remained readable by the service account.

The permission and dotenv blockers from the prior attempts did not recur.

## 8. Health Tests

Local and public health tests were skipped because the backend never established a listener. A health request after the fatal startup failure would not validate the failed runtime.

## 9. Authorization Tests

Protected-route tests were skipped because the backend never became ready. No JWT, login, password, LLM operation, database write, trading action, or external transaction was attempted.

## 10. Nginx Regression Tests

The independent Nginx checks were run after the dashboard was stopped:

- Stale routes: 5 of 5 returned 404.
- Forbidden methods: 3 of 3 returned 403.

## 11. Filesystem Runtime Writes

Metadata-only checks found zero new or modified regular files since the marker in all inspected source, virtualenv, data, state, and cache locations. No new or modified source `.pyc` file was found. Git remained clean.

## 12. Resource Observation

Sustained resource sampling was skipped because no stable PID or successful health test existed. Baseline capacity was approximately 1.7 GiB available RAM, 3.3 GiB free swap, and 23 GiB available on the root filesystem.

## 13. Journal Review

The bounded retry window contained 251 journal lines. Sanitized classification found:

| Indicator | Count |
|---|---:|
| PermissionError | 0 |
| Legacy dotenv reference | 0 |
| Traceback marker | 6 |
| Database authentication failure marker | 12 |
| OperationalError marker | 6 |
| Database initialization failure | 0 |
| Model/cache failure | 0 |
| Bind failure | 0 |
| Environment validation failure | 0 |
| ProtectSystem denial | 0 |
| Restart lifecycle indicator | 11 |
| Secret-value pattern | 0 |

The fatal category was PostgreSQL password authentication failure. Raw logs and connection details are not included.

## 14. Shutdown Result

| Check | Actual | Result |
|---|---|---|
| Stop duration | 0.025 seconds | PASS |
| Dashboard state | inactive/dead | PASS |
| Enablement | disabled | PASS |
| Port 8001 | Closed | PASS |
| Orphan process | None | PASS |
| SIGKILL or shutdown timeout | None observed | PASS |

## 15. Final Containment

| Check | Final actual | Result |
|---|---|---|
| Repository HEAD | `935b8b9ebe16616841390ff8c8ffe927493d30ba` | PASS |
| Git working tree / diff check | Clean | PASS |
| Dashboard | disabled and inactive | PASS |
| Port 8001 | No listener | PASS |
| Nginx | active | PASS |
| Telegram | active | PASS |

No source, permission, systemd, Nginx, UFW, environment, database schema, certificate, dependency, commit, or push change was made.

## 16. Blockers and Warnings

### Blocker

The dashboard's configured PostgreSQL authentication fails before application readiness. This is distinct from the resolved dotenv and source-permission blockers.

### Warnings

- Health, authorization, and sustained resource behavior remain untested because startup failed before listener creation.
- Import-time idempotent table initialization remains existing behavior but was not reached successfully in this retry.

## 17. Final Recommendation

Do not start or enable `aliza-dashboard.service` again yet. Use a separate, explicitly approved database-configuration diagnosis that compares non-secret connection metadata and effective identity without displaying credentials or querying production data. Preserve the dedicated EnvironmentFile and current source isolation. After resolving authentication, repeat this controlled-start procedure.
