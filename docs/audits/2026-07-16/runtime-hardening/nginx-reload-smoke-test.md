# Nginx Reload and Smoke Test

## 1. Verdict

**PASS**

Nginx reloaded successfully without restart. The master PID stayed constant, worker PIDs changed, syntax remained valid, static and SPA routes stayed available, all stale routes returned 404, method restrictions were enforced by Nginx, security headers were present, and backend proxy routes returned the expected 502 while the dashboard remained inactive. No rollback condition was met.

## 2. Pre-Reload State

| Check | Actual | Result |
|---|---|---|
| Timestamp | 2026-07-16T09:25:28+07:00 | Recorded |
| Repository HEAD | 8a96fa2b2c690c14fd14f83bb85548462d029134 | PASS |
| Git working tree | Clean | PASS |
| Nginx | active | PASS |
| nginx -t | Successful | PASS |
| Nginx master PID | 2642904 | Recorded |
| Nginx worker PIDs | 1451160, 1451161 | Recorded |
| Dashboard | disabled and inactive | PASS |
| Port 8001 | No listener | PASS |
| Telegram | active | PASS |
| Backup | Available, owner ubuntu:ubuntu, mode 0700; base server backup mode 0600 | PASS |

All mandatory gates passed before reload. No TLS configuration content, private material, request credential, or environment value is included.

## 3. Reload Result

The only activation command used was:

~~~text
sudo systemctl reload nginx
~~~

| Check | Actual | Result |
|---|---|---|
| Reload command | Exit 0 | PASS |
| Post-reload timestamp | 2026-07-16T09:26:42+07:00 | Recorded |
| ActiveState | active | PASS |
| SubState | running | PASS |
| Result | success | PASS |
| Post-reload nginx -t | Successful | PASS |
| Restart used | No | PASS |

## 4. Worker PID Verification

| Process | Before | After | Expected | Result |
|---|---|---|---|---|
| Master | 2642904 | 2642904 | Unchanged | PASS |
| Workers | 1451160, 1451161 | 438395, 438396 | New generation | PASS |

The unchanged master and replaced workers confirm that a reload occurred rather than a restart.

## 5. HTTP and HTTPS Tests

| Test | Expected | Actual Status | Result |
|---|---|---:|---|
| HTTP root redirect | 301 or 308 to literal HTTPS domain | 301 to https://juniawan.web.id/ | PASS |
| HTTPS static root | 200 or valid static/cache status | 200 | PASS |
| SPA fallback /dashboard-smoke-test | Usually 200 | 200 | PASS |

The HTTP redirect used the literal domain. Static and SPA responses carried all four required security headers. The Server header exposed only nginx without a version.

## 6. Stale Route Tests

| Path | Expected | Actual Status | Security Headers | Result |
|---|---:|---:|---:|---|
| /openapi.json | 404 | 404 | 4/4 | PASS |
| /openapi.json/test | 404 | 404 | 4/4 | PASS |
| /docs | 404 | 404 | 4/4 | PASS |
| /docs/test | 404 | 404 | 4/4 | PASS |
| /redoc | 404 | 404 | 4/4 | PASS |
| /redoc/test | 404 | 404 | 4/4 | PASS |
| /api/docs | 404 | 404 | 4/4 | PASS |
| /api/docs/test | 404 | 404 | 4/4 | PASS |
| /upload | 404 | 404 | 4/4 | PASS |
| /upload/test | 404 | 404 | 4/4 | PASS |

All ten routes returned Nginx 404 responses rather than SPA 200 or backend proxy responses. None exposed a server version or wildcard CORS header.

## 7. Method Restriction Tests

| Test | Expected | Actual Status | Result |
|---|---|---:|---|
| POST static root | Nginx rejection | 403 | PASS |
| OPTIONS /api/chat | Nginx rejection | 403 | PASS |
| PUT /admin | Nginx rejection | 403 | PASS |
| POST /health | Nginx rejection | 403 | PASS |

A 403 from each route confirms the request was rejected at Nginx. The three sensitive route responses included Cache-Control no-store and all four security headers. The static response inherited all four security headers.

## 8. Backend-Off Behavior

The dashboard intentionally remained disabled and inactive with no listener on port 8001. A 502 from the hardened proxy locations is therefore expected and is not a reload failure.

| Route | Expected While Backend Is Off | Actual Status | No-Store | Security Headers | Result |
|---|---|---:|---|---:|---|
| GET /health | 502 | 502 | Present | 4/4 | PASS |
| GET /api/market/btc | 502 | 502 | Present | 4/4 | PASS |
| GET /admin | 502 | 502 | Present | 4/4 | PASS |
| POST /api/chat with minimal non-sensitive JSON | 502 | 502 | Present | 4/4 | PASS |

Each body was 150 bytes and was not copied into this report. Automated inspection found no loopback address, upstream port, filesystem path, credential marker, or private-key marker. These routes did not fall through to SPA 200.

## 9. Security Header Results

| Header or Policy | Static HTTPS | SPA | Stale Routes | Backend-Off Proxy | Result |
|---|---|---|---|---|---|
| Strict-Transport-Security: max-age=300 | Present | Present | Present | Present | PASS |
| X-Content-Type-Options: nosniff | Present | Present | Present | Present | PASS |
| X-Frame-Options: DENY | Present | Present | Present | Present | PASS |
| Referrer-Policy: no-referrer | Present | Present | Present | Present | PASS |
| Cache-Control: no-store | Not required | Not required | Not required | Present | PASS |
| Wildcard Access-Control-Allow-Origin | Absent | Absent | Absent | Absent | PASS |
| Server version disclosure | Absent | Absent | Absent | Absent | PASS |

## 10. Nginx Log Review

The systemd journal was reviewed from 2026-07-16 09:25 WIB onward and summarized without copying access logs.

- Two reload lifecycle entries were present: reload started and reload completed.
- No failure, error, emergency, alert, or critical entry was found for the Nginx unit in the review window.
- Expected 502 responses occurred only because the deliberately inactive dashboard had no loopback listener.
- No repeated configuration error or service failure was observed.

## 11. Containment Status

Final check timestamp: 2026-07-16T09:28:44+07:00.

| Check | Final Actual | Result |
|---|---|---|
| Nginx | active, running, Result=success | PASS |
| Final nginx -t | Successful | PASS |
| Master PID | 2642904 | PASS |
| Worker PIDs | 438395, 438396 | PASS |
| Dashboard enablement | disabled | PASS |
| Dashboard activity | inactive | PASS |
| Listener 8001 | None | PASS |
| Telegram | active | PASS |
| Repository HEAD | 8a96fa2b2c690c14fd14f83bb85548462d029134 | PASS |
| Git working tree | Clean | PASS |
| Systemd/UFW/environment/certificate/source changes | None | PASS |

## 12. Rollback Status

**Rollback was not performed.**

None of the rollback conditions occurred:

- Nginx remained active.
- Static frontend and SPA fallback returned 200.
- HTTP redirect was correct.
- Syntax stayed valid.
- Worker generation changed normally.
- Security configuration matched the pre-reload report.
- No reload failure or repeated unit error appeared.

The existing backup remains available at:

/home/ubuntu/aliza-ai-security-backups/nginx-dashboard-20260716

## 13. Final Recommendation

The Nginx hardening is active and passed the controlled reload smoke test. Keep aliza-dashboard.service disabled and inactive until its separate controlled-start procedure is explicitly approved. When that occurs, verify authenticated API behavior, health response, upstream timing, and logs without weakening the Nginx route, header, method, body-size, timeout, and rate-limit controls.
