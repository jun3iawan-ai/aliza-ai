# Dashboard Controlled Start Report

## 1. Verdict

**FAIL**

The service did not achieve a stable startup. It briefly reported active during polling, then entered an automatic restart loop. Startup validation captured MainPID=0, ExecMainStatus=1, NRestarts=8, no port 8001 listener, and no stable process to test. The controlled run was stopped immediately.

The sanitized journal identifies the blocker as repeated PermissionError while the application attempted to open the legacy /opt/aliza-ai/.env file. The hardened service correctly cannot read that file. No environment value or database credential was read or recorded.

Final containment succeeded: stop completed in 0.023 seconds without SIGKILL, timeout, or orphan; the dashboard is disabled and inactive; Nginx and Telegram remain active; port 8001 is closed; and the repository is clean at the expected HEAD.

## 2. Pre-Start Gates

| Gate | Actual | Result |
|---|---|---|
| Gate timestamp | 2026-07-16T09:33:33+07:00 | Recorded |
| Start-window timestamp | 2026-07-16T09:34:21+07:00 | Recorded |
| Repository HEAD | 8a96fa2b2c690c14fd14f83bb85548462d029134 | PASS |
| Git working tree | Clean | PASS |
| Dashboard before start | disabled, inactive, MainPID 0 | PASS |
| Nginx | active; nginx -t successful | PASS |
| Telegram | active | PASS |
| Port 8001 before start | No listener | PASS |
| Runtime identity | aliza-dashboard:aliza-dashboard | PASS |
| EnvironmentFiles | Dedicated dashboard environment file only; content not read | PASS |
| NoNewPrivileges | yes | PASS |
| ProtectSystem | strict | PASS |
| CapabilityBoundingSet | empty | PASS |
| PrivateTmp / PrivateDevices | yes / yes | PASS |
| ProtectHome | no, intentionally deferred | Recorded |
| RestrictAddressFamilies | AF_UNIX, AF_INET, AF_INET6 | PASS |
| ReadWritePaths | data, memory, vector store, state, cache | PASS |
| KillMode / TimeoutStop | control-group / 60 seconds | PASS |

Baseline resources:

- RAM: 3.6 GiB total, approximately 1.5 GiB available.
- Swap: 4.0 GiB total, approximately 3.6 GiB free.
- Root filesystem: 60% used, approximately 23 GiB available.
- /, /opt, and /var reside on the same filesystem.
- Dashboard PID: none.

The previous 50 journal lines contained five historical database-authentication error indicators from 2026-07-15. They were outside this controlled-start window and no secret-value shape was detected. They were not attributed to this run.

All mandatory pre-start gates passed.

## 3. Startup Result

The only start command used was:

~~~text
sudo systemctl start aliza-dashboard.service
~~~

| Observation | Actual | Result |
|---|---|---|
| Start command | Exit 0 | Command accepted |
| Poll interval | 2 seconds | As required |
| Polls 1-11 | activating | Startup in progress |
| Poll 12 | active | Transient only |
| Immediate validation state | activating / auto-restart | FAIL |
| MainPID | 0 | FAIL |
| ExecMainStatus | 1 | FAIL |
| NRestarts | 8 | FAIL |
| Stable active process | None | FAIL |
| Stable startup time | Not achieved | FAIL |

The transient active sample did not represent a ready service. Immediate validation proved that the process had already exited and systemd was restarting it.

## 4. Process and Listener Isolation

| Check | Expected | Actual | Result |
|---|---|---|---|
| Stable process identity | aliza-dashboard:aliza-dashboard | No stable PID remained for ps inspection | NOT TESTABLE |
| Listener | 127.0.0.1:8001 only | No listener appeared | FAIL |
| Wildcard IPv4 listener | None | None | PASS |
| Wildcard IPv6 listener | None | None | PASS |
| Other listener owned by dashboard PID | None | No stable PID/listener | PASS |
| Restart count | 0 | 8 at failure capture | FAIL |
| Service enabled state | disabled | disabled | PASS |

There was no evidence of a wildcard listener or process running as root/ubuntu, but stable identity could not be verified because the process exited before inspection.

## 5. Health Tests

| Test | Expected | Actual | Result |
|---|---|---|---|
| Loopback /health | HTTP 200 with minimal body | Not run; no listener | SKIPPED |
| Public /health through Nginx | HTTP 200 with hardened headers | Not run; backend never became ready | SKIPPED |

Health requests were intentionally not sent after critical startup failure. A request could not validate a runtime that never established its listener.

## 6. Authorization Tests

| Protected route | Expected | Actual | Result |
|---|---|---|---|
| GET /api/market/btc | 401 | Not run | SKIPPED |
| POST /api/chat without authorization | 401 and no LLM/database work | Not run | SKIPPED |
| GET /admin | 401 | Not run | SKIPPED |
| GET /admin/stats | 401 | Not run | SKIPPED |

No login, synthetic authorization material, LLM request, market operation, trading action, or external transaction was performed.

## 7. Nginx Regression Tests

| Test group | Expected | Actual | Result |
|---|---|---|---|
| Five stale routes | 5 of 5 return 404 | Not rerun after dashboard failure | SKIPPED |
| Three forbidden methods | 3 of 3 return 403 | Not rerun after dashboard failure | SKIPPED |
| Nginx runtime containment | active | active | PASS |

The Nginx configuration was not changed in this task. Its pre-start syntax check succeeded, and Nginx remained active after the dashboard failure. Runtime route regressions were skipped because the controlled-start verdict was already FAIL and they would not validate the failed backend runtime.

## 8. Filesystem Runtime Writes

A metadata-only find used a marker created immediately before start. File contents were not opened.

| Path group | New or modified since marker | Result |
|---|---:|---|
| /opt/aliza-ai/api | 0 | PASS |
| /opt/aliza-ai/scripts | 0 | PASS |
| /opt/aliza-ai/venv | 0 | PASS |
| New .pyc in api/scripts | 0 | PASS |
| /opt/aliza-ai/data | 0 | PASS |
| /opt/aliza-ai/memory | 0 | PASS |
| /opt/aliza-ai/knowledge/vector_store | 0 | PASS |
| /var/lib/aliza-dashboard | 0 | PASS |
| /var/cache/aliza-dashboard | 0 | PASS |
| Remaining private service tmp directory after stop | 0 | PASS |

The repository source did not change. The failed startup produced no persistent state/cache write in the inspected allowlist.

## 9. Resource Observation

| Metric | Actual | Result |
|---|---|---|
| MemoryCurrent | Not set after process exit | NOT AVAILABLE |
| TasksCurrent | Not set after process exit | NOT AVAILABLE |
| CPUUsageNSec | Not set after controlled stop | NOT AVAILABLE |
| Stable PID for CPU sample | None | NOT AVAILABLE |
| Thread count | Not measurable without stable PID | NOT AVAILABLE |
| Open file count | Not measurable without stable PID | NOT AVAILABLE |
| Restart count at failure capture | 8 | FAIL |
| Listener count | 0 | FAIL for startup readiness |

Resource stability could not be evaluated because no process remained stable long enough for observation. The restart count alone was a critical failure signal.

## 10. Journal Review

The review window began at 2026-07-16T09:34:21+07:00. Logs were classified and summarized; raw logs and values were not copied.

| Indicator | Count |
|---|---:|
| Journal lines in bounded review window | 794 |
| Traceback markers | 15 |
| Permission-denied markers | 15 |
| Model failure markers | 0 |
| Cache failure markers | 0 |
| Environment validation markers | 0 |
| Bind error markers | 0 |
| Error indicators | 45 |
| Warning indicators | 0 |
| Secret-value shapes detected | 0 |
| Restart lifecycle events | 74 |

Unique sanitized root-cause signature:

- PermissionError opening /opt/aliza-ai/.env, repeated across restart attempts.

Interpretation:

- The dedicated systemd environment file was configured, but application import code still attempted to discover/open the legacy repository dotenv file.
- POSIX permissions and stage-1 isolation correctly denied that access.
- The failure occurred before a stable database connection, model/cache load, or bind.
- No secret value was observed in the controlled-start log review.

## 11. Shutdown Result

The dashboard was stopped immediately after the restart loop was confirmed.

| Check | Expected | Actual | Result |
|---|---|---|---|
| Stop command | Successful | Exit 0 | PASS |
| Stop duration | Less than 60 seconds | 0.023 seconds | PASS |
| Final ActiveState/SubState | inactive/dead | inactive/dead | PASS |
| Enabled state | disabled | disabled | PASS |
| Listener 8001 after stop | None | None | PASS |
| SIGKILL evidence | None | 0 indicators | PASS |
| Shutdown timeout evidence | None | 0 indicators | PASS |
| Orphan evidence | None | 0 indicators and no matching process | PASS |
| run_dashboard/uvicorn/aliza-chat-llm process | None | None | PASS |

The post-stop unit result reports success because the explicit stop completed normally; this does not erase the startup capture showing ExecMainStatus=1 and NRestarts=8.

## 12. Final Containment

Final check timestamp: 2026-07-16T09:38:11+07:00.

| Check | Final Actual | Result |
|---|---|---|
| Dashboard enablement | disabled | PASS |
| Dashboard activity | inactive | PASS |
| Dashboard MainPID | 0 | PASS |
| Port 8001 | No listener | PASS |
| Orphan dashboard process | None | PASS |
| Nginx | active | PASS |
| Telegram | active | PASS |
| Git working tree | Clean | PASS |
| Repository HEAD | 8a96fa2b2c690c14fd14f83bb85548462d029134 | PASS |
| Source/systemd/Nginx/UFW/environment/certificate/permission changes | None | PASS |

## 13. Blockers and Warnings

### Blocker

Application startup attempts to open the legacy /opt/aliza-ai/.env file even though systemd supplies a dedicated environment file. Access is correctly denied to the dedicated account, causing a PermissionError and restart loop before listener initialization.

Do not make the legacy file readable to the dashboard account; doing so would weaken the allowlist and expose unrelated service credentials.

### Warnings

- Restart=on-failure caused rapid repeated attempts before the failure was captured and stopped.
- Stable resource, health, and authorization behavior remains untested.
- Historical database-authentication failures exist outside this run and should be re-evaluated only after the dotenv access blocker is fixed without exposing credentials.

## 14. Final Recommendation

Do not start or enable aliza-dashboard.service again yet.

Use a separate, reviewed source-remediation task to prevent production dashboard imports from discovering or opening the legacy repository .env file. The service should consume only the already configured dedicated systemd environment. Preserve fail-closed permissions on the legacy file.

After source remediation:

1. Run isolated unit/import tests without a production database or network.
2. Confirm imports do not open legacy dotenv files.
3. Keep the service disabled and repeat this controlled-start procedure.
4. Require stable NRestarts=0, dedicated process identity, loopback-only listener, local/public health 200, protected routes 401, clean filesystem behavior, and graceful stop before changing the verdict.
