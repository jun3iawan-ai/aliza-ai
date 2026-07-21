# Database Credential Consumer Impact Audit

## 1. Verdict

**SAFE WITH WARNINGS**

The rotated `aliza_user` credential is used by the dashboard database path and succeeds through the dedicated dashboard EnvironmentFile. The legacy EnvironmentFile still contains a non-empty but now invalid `DB_PASSWORD`; however, the active Telegram and market entrypoints do not import `core.database`, call psycopg2, or otherwise use that database role.

No active non-dashboard consumer of `aliza_user` was identified. No service was started, stopped, restarted, reloaded, or enabled, and no credential or configuration was changed.

## 2. Containment

| Check | Initial and final state | Result |
|---|---|---|
| Repository HEAD | `935b8b9ebe16616841390ff8c8ffe927493d30ba` | PASS |
| Git working tree | Clean | PASS |
| Dashboard | disabled and inactive | PASS |
| Port 8001 | No listener | PASS |
| Nginx / Telegram / PostgreSQL | active / active / active | PASS |

## 3. Database Consumer Inventory

The active-source scan covered direct database imports, psycopg2 connections, `DB_PASSWORD`, fixed database/user metadata, and centralized dotenv loading. Modules were not imported or executed.

| Entrypoint/class | Environment behavior | Database chain | Classification |
|---|---|---|---|
| Dashboard runner and API | Dedicated systemd environment; dotenv forced off | `api.server` and `api.auth` import `core.database`, which connects as `aliza_user` | Dashboard consumer |
| Telegram bot | Loads legacy project dotenv | No `core.database` import or psycopg2 connection anywhere in its active source chain | No database dependency |
| Market bot | Loads legacy project dotenv plus market environment from systemd | No `core.database` import or psycopg2 connection | No database dependency |
| Market monitor | Loads legacy project dotenv when run directly | No `core.database` import or psycopg2 connection | Manual/inactive, no database dependency |
| Main application | Loads legacy project dotenv | Imports agent/tool code, not `core.database` | Manual entrypoint, no database dependency |
| API auth/server | Uses `core.database` | Fixed `aliza` database and `aliza_user` role | Dashboard-only production path |
| Root-level tests | Contain static/remediation references | Test-only | Excluded as production consumer |

The only active production source call to `psycopg2.connect` in `/opt/aliza-ai` is in `core/database.py`, reached by the dashboard API path.

## 4. Systemd Service Mapping

| Unit | State | User/group | EnvironmentFile | Entrypoint | `aliza_user` impact |
|---|---|---|---|---|---|
| aliza-dashboard.service | inactive, disabled | aliza-dashboard/aliza-dashboard | `/etc/aliza-dashboard/dashboard.env` | `scripts/run_dashboard.py` | Confirmed dashboard consumer |
| aliza-telegram.service | active | ubuntu/default | `/opt/aliza-ai/.env` | `interfaces/telegram_bot.py` | No database dependency |
| aliza-market.service | active | ubuntu/default | `/opt/aliza-ai/.env`, `.env.market` | `interfaces/market_bot.py` | No database dependency |
| gmail-telegram-bot.service | active | ubuntu/default | `/opt/gmail-agent/.env` | Separate Gmail bot | No DB_PASSWORD in its environment file |
| aliza-api.service | inactive | ubuntu/default | none declared | Missing/stale separate source path | Not an active consumer; unverifiable source |
| aliza-api-staging.service | inactive | ubuntu/default | Missing separate staging path | Missing/stale separate source path | Not an active consumer |
| aliza-bot.service | inactive | ubuntu/default | Missing separate production path | Missing/stale separate source path | Not an active consumer |
| aliza-bot-staging.service | inactive | ubuntu/default | Missing separate staging path | Missing/stale separate source path | Not an active consumer |
| aliza-meeting.service | inactive | ubuntu/default | Missing separate path | Separate missing source path | Not an active consumer |
| aliza-stock.service | inactive | ubuntu/default | none declared | Separate stock application | No matching database indicators found |
| aliza-assistant.service / aliza.service | masked, inactive | none effective | none | none active | No active consumer |

The effective dashboard drop-in resets the legacy EnvironmentFile and uses only the dedicated dashboard file, despite the base unit's historical legacy declaration.

## 5. Environment File Structure

Only structure and metadata were inspected; no right-hand-side value was printed.

| Path | Metadata | DB_PASSWORD | State/syntax | DB metadata names |
|---|---|---:|---|---|
| `/etc/aliza-dashboard/dashboard.env` | `0640 root:aliza-dashboard` | 1 | non-empty, simple | DB_PASSWORD |
| `/opt/aliza-ai/.env` | `0600 ubuntu:ubuntu` | 1 | non-empty, simple | DB_PASSWORD |
| `/opt/aliza-ai/.env.market` | `0664 ubuntu:ubuntu` | 0 | not applicable | none |
| `/opt/gmail-agent/.env` | `0600 ubuntu:ubuntu` | 0 | not applicable | none |
| Separate ETPP staging/production paths | unavailable | unknown | unavailable | unknown |
| Separate meeting path | unavailable | unknown | unavailable | unknown |

No duplicate or malformed assignment was found in the available files. The broad mode on `.env.market` is an existing non-database warning and was not changed.

## 6. Isolated Connection Tests

Both tests used collected transient systemd units, the same user/group and EnvironmentFile semantics as the associated service, direct psycopg2, a five-second timeout, bytecode writing disabled, and only `SELECT 1`, rollback, and close.

| Environment | Runtime identity | Result |
|---|---|---|
| Dedicated dashboard | aliza-dashboard/aliza-dashboard | CONNECTION_SUCCESS |
| Legacy project | ubuntu/ubuntu | INVALID_PASSWORD |

No raw database exception or environment value was displayed.

## 7. Telegram and Other Service Risk

### Telegram

- State: active/running.
- MainPID was stable with NRestarts=0.
- Process uptime was approximately 19 hours during inspection.
- Source loads the legacy dotenv but has no database import or connection code.
- It does not hold an `aliza_user` database session and does not need the stale legacy password on restart.

Risk classification: **NO_DATABASE_DEPENDENCY**.

### Market bot

- State: active/running with NRestarts=0.
- Process uptime exceeded 43 days during inspection.
- Source has no database import or connection code.

Risk classification: **NO_DATABASE_DEPENDENCY**.

No active service was identified that would fail database authentication solely because of the rotated role. The inactive units pointing to unavailable separate application paths remain an inventory warning, not an active credential consumer.

## 8. PostgreSQL Active Connection Metadata

After the transient tests were collected, `pg_stat_activity` showed zero active connections for `aliza_user`. Therefore there was no long-lived session masking an active consumer's stale credential.

No query text, application data, or session was terminated.

## 9. Decision Matrix Result

**DASHBOARD_ONLY_ROLE**

Within the inspected active production source and services, the dashboard is the only consumer of the `aliza_user` database path. The legacy file contains a stale credential, but the active services that load that file do not use the database role.

## 10. Required Remediation

No remediation is required before a controlled dashboard start. Do not copy the dashboard credential into the legacy `.env` automatically.

Recommended follow-up hygiene in a separately approved task:

- remove the unused stale `DB_PASSWORD` assignment from the legacy file only after confirming no external manual workflow depends on it;
- preserve a dedicated role and EnvironmentFile per future database consumer;
- review or remove inactive systemd units whose source/environment paths no longer exist;
- separately review the existing broad permissions on `.env.market`.

## 11. Final Containment

| Check | Final state | Result |
|---|---|---|
| Dashboard | disabled and inactive | PASS |
| Port 8001 | No listener | PASS |
| Nginx / Telegram / PostgreSQL | active / active / active | PASS |
| Repository HEAD | `935b8b9ebe16616841390ff8c8ffe927493d30ba` | PASS |
| Git working tree / diff check | Clean | PASS |
| Temporary checker and transient units | Removed/collected | PASS |

No source, environment, database, systemd, Nginx, UFW, permission, certificate, schema, service state, commit, or push change was made.

## 12. Next Step

It is safe to proceed with a separately approved controlled dashboard start. Keep all other services running and leave the legacy environment unchanged during that test. Require stable NRestarts=0, loopback-only binding, local/public health 200, protected-route 401 behavior, and a clean controlled stop.
