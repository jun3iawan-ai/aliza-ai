# Dashboard Authenticated Functional Test Report

## 1. Verdict

**NEED_INTERACTIVE_OPERATOR**

The live test was stopped before dashboard start. Credentials are permitted only through an operator-controlled interactive TTY, and no such operator input channel was available. No credential was requested through Codex/chat, and no live authenticated request was attempted.

## 2. Pre-Test Containment

| Gate | Actual | Result |
|---|---|---|
| Repository HEAD | `935b8b9ebe16616841390ff8c8ffe927493d30ba` | PASS |
| Git working tree | Clean | PASS |
| Dashboard | disabled and inactive | PASS |
| Port 8001 | No listener | PASS |
| Nginx / Telegram / market / PostgreSQL | active / active / active / active | PASS |
| Nginx syntax | Valid | PASS |

## 3. Route and Authentication Contract

Static source review was performed without importing `api.server` or opening a database.

| Item | Source contract |
|---|---|
| Login | `POST /api/auth/auth/login` |
| Login request | JSON fields `username` and `password` |
| Login token field | `token` |
| Profile/current-user | No route registered |
| Logout | No route registered |
| Protected market | `GET /api/market/btc`, `Depends(get_current_user)` |
| Protected chat | `POST /api/chat`, `Depends(get_current_user)` |
| Admin stats | `GET /admin/stats`, `Depends(require_admin)` |
| Admin role behavior | Missing/invalid bearer token: 401; authenticated non-admin: 403; admin: handler permitted |
| Token lifetime | 24 hours by source configuration |
| Token claims | `sub`, `user_id`, `role`, `iat`, `exp`; optional `username` |

Login reads the matching user record and may update the stored password hash only when the existing hash requires upgrade; it does not add a user row. The market route has no explicit PostgreSQL write. A successful non-fallback chat attempts one insert into `chats` and one into `usage`; controlled fallback paths return without those inserts. No logout write exists because no logout route is implemented.

Existing unit tests cover valid decoding, required claims, malformed and expired token rejection, bearer enforcement, non-admin rejection, admin acceptance, protected endpoint access, and the login token response field.

## 4. Startup Stability

Not run. The dashboard was not started because interactive operator input was unavailable.

## 5. Valid Login

Not run. Status: `NEED_INTERACTIVE_OPERATOR`.

## 6. Invalid Login and Token

Not run. No invalid credential or malformed-token request was sent.

## 7. Authenticated Identity

`NOT_IMPLEMENTED` by static route review; no profile/current-user route is registered. No live request was made.

## 8. Market Endpoint

Not run. No market request or external transaction was performed.

## 9. Admin Authorization

Not run live. Static contract: `/admin/stats` requires `require_admin`, which returns 401 for missing/invalid authentication and 403 for an authenticated non-admin.

## 10. Controlled Chat Test

`CHAT_TEST_NOT_REACHED`. No approval prompt was issued because the test stopped before dashboard start, and no chat request was sent.

## 11. Database Persistence

No database was opened and no count snapshot was taken. Deltas are unavailable because no live request was performed. Source review predicts no row-count change from login, invalid authentication, malformed token, or market access; a successful non-fallback chat may add one `chats` row and one `usage` row.

## 12. Logout and Token Expiry

`STATELESS_JWT_NO_LOGOUT_ROUTE`. Live expiry was not tested. Source sets `exp` to 24 hours by default and requires `sub`, `user_id`, `role`, and `exp` during decode; existing unit tests cover expired-token rejection.

## 13. Journal and Secret Review

No test startup window existed, so no runtime journal was collected. No credential, token, secret value, password, response body, raw exception, or environment value was captured or written to this report.

## 14. Resource Stability

Not run because the dashboard remained inactive. No PID, restart, listener, memory, task, thread, or open-file sample was created.

## 15. Shutdown

Not applicable. The dashboard was never started and therefore required no stop operation.

## 16. Final Containment

| Check | Final state | Result |
|---|---|---|
| Repository HEAD | `935b8b9ebe16616841390ff8c8ffe927493d30ba` | PASS |
| Git working tree | Clean | PASS |
| Dashboard | disabled and inactive | PASS |
| Port 8001 | No listener | PASS |
| Nginx / Telegram / market / PostgreSQL | active / active / active / active | PASS |

## 17. Warnings and Remaining Risks

- An operator-controlled interactive TTY was unavailable, so availability of an approved test account could not be established safely.
- Valid login, token claims from a live token, protected market access, admin authorization, invalid controls, persistence deltas, and runtime stability remain untested in this run.
- Logout is not implemented; JWT handling is stateless until expiry.

## 18. Recommendation

Keep `aliza-dashboard.service` disabled and inactive. Repeat the authenticated functional test from a terminal directly controlled by an approved operator with an approved test account. Do not transmit credentials through Codex/chat or store them in commands, environment, logs, files, or the report.
