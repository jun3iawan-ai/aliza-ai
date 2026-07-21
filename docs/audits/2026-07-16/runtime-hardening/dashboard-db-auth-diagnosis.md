# Dashboard PostgreSQL Authentication Diagnosis

## 1. Verdict

**PARTIALLY IDENTIFIED**

The dashboard's effective systemd environment contains a present, non-empty `DB_PASSWORD`, and the PostgreSQL database, login role, role password, listener, and applicable localhost authentication rule all exist. The isolated connection did not authenticate or reach `SELECT 1`.

The exact credential-side root cause cannot be distinguished safely in this task because the dedicated raw assignment uses quote syntax and the dedicated-versus-legacy comparison was therefore classified as ambiguous. No credential value, verifier, hash, fingerprint, connection URI, or raw database error was displayed or recorded.

## 2. Containment

| Check | Initial state | Result |
|---|---|---|
| Repository HEAD | `935b8b9ebe16616841390ff8c8ffe927493d30ba` | PASS |
| Git working tree | Clean | PASS |
| Dashboard | disabled and inactive | PASS |
| Port 8001 | No listener | PASS |
| Nginx / Telegram | active / active | PASS |
| PostgreSQL | active; loopback listener on port 5432 | PASS |

The dashboard and PostgreSQL services were not started, restarted, enabled, or modified.

## 3. Application Database Configuration

| Property | Source behavior |
|---|---|
| Driver | psycopg2 |
| Host | localhost |
| Port | Driver default, PostgreSQL 5432 |
| Database | aliza |
| Username | aliza_user |
| Password source | `DB_PASSWORD` environment variable |
| Connect timeout in application source | Not specified |
| SSL mode in application source | Not specified |
| Address path | TCP localhost, not an explicit Unix socket |

Importing `core.database` opens a connection, then runs four `CREATE TABLE IF NOT EXISTS` statements for `users`, `chats`, `usage`, and `documents`, followed by commit. These statements are idempotent table initialization, but the module was not imported and none of its queries was run during diagnosis.

## 4. Environment File Structure

The dedicated EnvironmentFile is `0640 root:aliza-dashboard` and contains 13 lines.

Variable names present:

- ALIZA_CHAT_LLM_MAX_CONCURRENCY
- ALIZA_CHAT_LLM_TIMEOUT_SECONDS
- ALIZA_DASHBOARD_DOCS_ENABLED
- ALIZA_DASHBOARD_HOST
- ALIZA_DASHBOARD_PORT
- COINGECKO_API_KEY
- DB_PASSWORD
- FORWARDED_ALLOW_IPS
- HF_HOME
- JWT_SECRET
- OPENAI_API_KEY
- SERPER_API_KEY
- XDG_CACHE_HOME

| Structural check | Result |
|---|---|
| DB_PASSWORD occurrences | 1 |
| DB_PASSWORD present | yes |
| Raw empty/length category | AMBIGUOUS because quote syntax is present |
| CRLF | no |
| Duplicate variables | none |
| Malformed non-comment lines | no |
| Space around variable name | no |
| Quote syntax on DB_PASSWORD | yes |
| Backslash syntax | no |
| Inline-comment syntax | no |

No right-hand-side value was printed or retained.

## 5. Effective Systemd Environment

A collected transient systemd unit ran as `aliza-dashboard:aliza-dashboard` with the dedicated EnvironmentFile and `NoNewPrivileges=yes`. The root-owned checker was supplied through stdin and removed after use.

| Effective property | Result |
|---|---|
| DB_PASSWORD present | yes |
| DB_PASSWORD non-empty | yes |
| Length category | 8-15 |
| Newline absent | yes |
| NUL absent | yes |
| Database metadata | aliza / aliza_user / localhost |

This rules out a missing or empty effective password and shows that systemd successfully parsed the quoted assignment.

## 6. Dedicated Credential Connection Test

The transient checker used the application's fixed database metadata with `connect_timeout=5`. It attempted one connection and would have run only `SELECT 1`, rollback, and close after successful authentication.

Result: **OTHER_DATABASE_ERROR, SQLSTATE unavailable**.

Authentication did not complete and `SELECT 1` was not reached. The driver exposed no SQLSTATE to the checker for this connection-stage failure. This result is consistent with, but does not independently refine, the sanitized password-authentication category captured during the immediately preceding controlled-start report.

## 7. PostgreSQL Role and Database Metadata

| Property | Result |
|---|---|
| PostgreSQL version | 14.22 |
| listen_addresses | localhost |
| Port | 5432 |
| password_encryption | scram-sha-256 |
| Target database exists | yes |
| Target role exists | yes |
| Role can login | yes |
| Role is superuser | no |
| Role password configured | yes |
| Role valid-until expired | no |
| Current connections for role | 0 |

Only boolean/metadata fields were queried. The password verifier and application tables were not read.

## 8. pg_hba and Localhost Resolution

As the dashboard account, `localhost` resolved to `127.0.0.1` only for this check. The first applicable pg_hba rule for that path uses `scram-sha-256` on `127.0.0.1/32`.

An IPv6 loopback rule also uses `scram-sha-256`, but `::1` was not returned by the effective localhost resolution. A later broad IPv4 rule does not supersede the earlier exact loopback rule because pg_hba uses first-match ordering.

No external address was resolved or contacted.

## 9. Legacy Credential Comparison

Equality category: **AMBIGUOUS_FORMAT**.

The dedicated assignment uses quote syntax. Under the task's fail-closed comparison rule, no value was guessed, normalized, printed, hashed, fingerprinted, or written to temporary storage.

Optional legacy connection category: **NOT_RUN**. The format precondition was not met, and the dedicated checker did not produce the explicit `INVALID_PASSWORD` category required to authorize that optional comparison.

## 10. Decision Matrix Result

**OTHER**

The diagnosis establishes that:

- systemd supplies a present and non-empty password;
- the database and login role exist;
- the role has a configured, non-expired password;
- the actual localhost path reaches a compatible SCRAM rule;
- the isolated connection still fails before `SELECT 1`.

This narrows the likely fault to credential mismatch/staleness or an equivalent connection-stage authentication issue, but the approved comparisons cannot distinguish the dedicated file from the server-side role credential without an unambiguous comparison or separately approved credential remediation.

## 11. Recommended Remediation

Do not change pg_hba, database identity, source, or service hardening based on this evidence: those structures match the application's intended path.

In a separately approved credential-remediation task, establish one canonical password for `aliza_user` and atomically update only the role password and the dedicated `DB_PASSWORD` assignment, preserving `0640 root:aliza-dashboard`, the remaining allowlisted environment entries, and the disabled dashboard state. Validate formatting through a transient unit before another controlled start. Do not copy the legacy password merely because it exists; its validity was not established here.

## 12. Final Containment

| Check | Final state | Result |
|---|---|---|
| Dashboard | disabled and inactive | PASS |
| Port 8001 | No listener | PASS |
| Nginx / Telegram | active / active | PASS |
| Repository HEAD | `935b8b9ebe16616841390ff8c8ffe927493d30ba` | PASS |
| Git working tree | Clean | PASS |
| Transient unit/checker | Collected and removed | PASS |

No source, credential, database, role, pg_hba, service, permission, systemd, Nginx, UFW, certificate, dependency, commit, or push change was made.

## 13. Next Step

Keep `aliza-dashboard.service` disabled and inactive. Obtain explicit approval for a narrowly scoped credential synchronization task, back up only the dedicated environment file metadata/content securely, rotate or set the role credential without displaying it, atomically replace only `DB_PASSWORD`, validate with the same isolated transient `SELECT 1`, and then repeat the controlled-start smoke test.
