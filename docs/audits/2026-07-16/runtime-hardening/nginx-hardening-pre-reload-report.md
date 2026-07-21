# Nginx Hardening Pre-Reload Report

Audit date: 2026-07-16 (Asia/Jakarta)
Domain: juniawan.web.id
Scope: saved Nginx configuration only. Nginx was not reloaded or restarted.

## 1. Verdict

**READY FOR RELOAD**

The saved configuration passes candidate and production syntax checks. Route boundaries, stale-route closures, loopback proxy targets, security headers, rate limits, TLS policy, request-body limit, method restrictions, cache policy, and timeouts match the requested hardening. No reload has occurred, so existing Nginx workers are still serving the previously loaded configuration.

There are no blockers for a separately approved reload. Compatibility warnings are listed in section 10.

## 2. Initial State and Active Server Block

| Check | Result | Status |
|---|---|---|
| Repository HEAD | 8a96fa2b2c690c14fd14f83bb85548462d029134 | PASS |
| Git working tree | Clean | PASS |
| Dashboard | disabled and inactive | PASS |
| Listener 8001 | None | PASS |
| Nginx runtime | active | PASS |
| Telegram | active and untouched | PASS |
| Initial nginx -t | Successful | PASS |
| Active server file | /etc/nginx/sites-available/aliza | Confirmed |
| Enabled symlink | /etc/nginx/sites-enabled/aliza -> /etc/nginx/sites-available/aliza | Confirmed |
| Global include path | /etc/nginx/conf.d/*.conf and /etc/nginx/sites-enabled/* from nginx.conf | Confirmed |

Only the exact juniawan.web.id server blocks in the active aliza file were changed. Other domain files were not modified.

## 3. Backup

Backup directory:

/home/ubuntu/aliza-ai-security-backups/nginx-dashboard-20260716

Directory mode is 0700. Every backup file is owned by ubuntu:ubuntu and mode 0600.

| Backup file | Purpose |
|---|---|
| aliza | Original active server block |
| nginx.conf | Original global configuration affecting includes and the existing health zone |
| sites-enabled-aliza-symlink.txt | Symlink target information |
| nginx-test-before.txt | Successful syntax test before changes |
| nginx-test-after.txt | Successful syntax test after changes |
| involved-files.txt | Configuration involvement inventory |
| new-files-before.txt | Evidence that both new include files were absent |

No TLS private key was copied.

## 4. Files Created or Changed

| Path | Action | Final owner | Final mode |
|---|---|---|---|
| /etc/nginx/sites-available/aliza | Replaced from syntax-tested candidate | root:root | 0644 |
| /etc/nginx/conf.d/aliza-dashboard-rate-limits.conf | Created | root:root | 0644 |
| /etc/nginx/snippets/aliza-security-headers.conf | Created | root:root | 0644 |
| /etc/nginx/sites-enabled/aliza | Unchanged symlink | root:root | Symlink |
| /etc/nginx/nginx.conf | Unchanged | Existing | Existing |

Certificate paths were not changed. Nginx, systemd hardening, UFW, repository source, and environment files were not changed beyond the three Nginx configuration files listed above.

## 5. Route Before and After

| Public route | Before | Saved configuration after hardening |
|---|---|---|
| /openapi.json | Proxied to backend schema | Exact route and slash subtree return 404 |
| /docs | SPA fallback | Exact route and slash subtree return 404 |
| /redoc | SPA fallback | Exact route and slash subtree return 404 |
| /api/docs | Rewritten to backend /docs | Exact route and slash subtree return 404 |
| /upload | Broad prefix proxied to backend | Exact route and slash subtree return 404 |
| /api/ | Broad prefix proxy, no Nginx rate/method/timeout policy | Boundary uses ^~, keeps full URI, GET/POST only, rate limited, bounded timeouts |
| /admin | Broad prefix also capable of matching unrelated names | Separate exact /admin and ^~ /admin/ proxies, GET/POST only |
| /health | Exact proxy without rate/method/timeout policy | Exact GET-only proxy with health rate limit and five-second I/O timeouts |
| / | Static SPA | Static root and try_files preserved; GET/HEAD only |

The stale closures use exact plus slash-boundary locations. They do not deliberately block /documentation, /uploads-public, or /api/docs-example.

Backend mappings retained:

- /api/... -> http://127.0.0.1:8001 with the full /api/... URI preserved.
- /admin and /admin/... -> http://127.0.0.1:8001 with the original URI preserved.
- /health -> http://127.0.0.1:8001/health.

Four proxy locations set Host, X-Real-IP, X-Forwarded-For, and X-Forwarded-Proto. No WebSocket upgrade header was added.

## 6. Security Headers

The new snippet defines:

- X-Content-Type-Options: nosniff
- X-Frame-Options: DENY
- Referrer-Policy: no-referrer

The HTTPS server defines Strict-Transport-Security with max-age=300, without preload and without includeSubDomains.

The snippet and HSTS are repeated inside /api/, both admin locations, and /health because those locations add Cache-Control and would otherwise override add_header inheritance. Each sensitive proxy location adds Cache-Control: no-store.

No Content-Security-Policy was introduced. No wildcard CORS header was found.

## 7. Rate Limits

| Scope | Zone | Zone definition | Location policy |
|---|---|---|---|
| API | aliza_api | New, 10 MiB, 60 requests/minute | burst=20, nodelay |
| Health | aliza_dashboard_health | New dedicated, 1 MiB, 60 requests/minute | burst=10, nodelay |

limit_req_status is 429 on the HTTPS server.

Effective configuration contains exactly one aliza_api zone and exactly one aliza_dashboard_health zone. The legacy aliza_health zone remains defined once and unchanged for the other virtual host.

## 8. TLS, Body, Methods, and Timeouts

| Control | Saved value |
|---|---|
| Aliza HTTPS protocols | TLSv1.2 and TLSv1.3 only |
| server_tokens | off on both Aliza HTTP and HTTPS servers |
| client_max_body_size | 32k on Aliza HTTPS |
| HTTP redirect | Literal https://juniawan.web.id$request_uri |
| Static methods | GET and HEAD |
| API/admin methods | GET and POST |
| Health methods | GET |

The global nginx.conf still lists older TLS protocols for unrelated virtual hosts. The explicit Aliza server setting overrides that global value; other domains were intentionally untouched.

| Route | Connect | Send | Read | Request buffering | Response buffering | Proxy cache |
|---|---:|---:|---:|---|---|---|
| /api/ | 3s | 10s | 55s | on | on | off |
| /admin exact and subtree | 3s | 10s | 15s | on | on | off |
| /health | 3s | 5s | 5s | inherited/default | on | off |

All backend proxy locations hide the upstream Server header.

## 9. Validation Results

- Candidate rate-limit and header harness: nginx -t successful.
- Candidate full server harness: nginx -t successful.
- Production configuration after installing new includes: nginx -t successful.
- Production configuration after installing the server block: nginx -t successful.
- Final effective inspection: successful.
- Duplicate aliza_api/aliza_dashboard_health definitions: none; legacy aliza_health remains unchanged.
- Location conflicts: none; final nginx -t succeeded.
- Stale route boundary definitions: ten, covering exact and slash subtree for five route families.
- Proxy targets to 127.0.0.1:8001: four.
- Security snippet includes in Aliza server file: five.
- HSTS additions in Aliza server file: five.
- Cache-Control no-store additions: four.
- Wildcard CORS, WebSocket upgrade, or proxy_cache on in the Aliza file: none.
- Static root remains /opt/aliza-ai/web with the original SPA fallback.

## 10. Compatibility Risks and Warnings

1. The saved configuration is not active until a separately approved reload.
2. The dashboard now uses dedicated aliza_dashboard_health, eliminating cross-virtual-host health-rate sharing; legacy aliza_health remains unchanged for the other virtual host.
3. OPTIONS and other non-GET/POST API/admin methods are denied. Same-origin dashboard behavior should be unaffected, but any future cross-origin preflight or PUT/PATCH/DELETE contract would need an explicit review.
4. The 32k server body limit is intentionally strict. Current chat and authentication payloads fit, but future larger JSON or upload endpoints must use a separately reviewed route/server.
5. The API read timeout is 55 seconds, allowing the backend 45-second LLM timeout plus overhead. Requests exceeding it will terminate at Nginx.
6. Initial HSTS max-age is deliberately short and should only be increased after HTTPS behavior is observed.
7. Nginx rate limiting uses the address Nginx sees as the client. If a CDN or external proxy is introduced later, real-IP trust must be separately configured and audited.
8. The dashboard backend is currently inactive, so proxy behavior could not and should not be live-tested in this task.

## 11. Rollback Commands

These commands are documentation only and were not run.

Before any reload, rollback is:

~~~bash
sudo install -o root -g root -m 0644 \
  /home/ubuntu/aliza-ai-security-backups/nginx-dashboard-20260716/aliza \
  /etc/nginx/sites-available/aliza
sudo rm -f /etc/nginx/conf.d/aliza-dashboard-rate-limits.conf
sudo rm -f /etc/nginx/snippets/aliza-security-headers.conf
sudo nginx -t
~~~

If a future approved reload has already occurred, restore and validate as above, then reload only after explicit approval:

~~~bash
sudo systemctl reload nginx
sudo systemctl is-active nginx
~~~

The symlink does not need restoration because it was not changed.

## 12. Containment Status

| Check | Final result | Status |
|---|---|---|
| Nginx saved syntax | Successful | PASS |
| Nginx runtime | Active | PASS |
| Nginx reload/restart during task | Not performed | PASS |
| Dashboard enablement | disabled | PASS |
| Dashboard activity | inactive | PASS |
| Port 8001 listener | None | PASS |
| Telegram service | active and untouched | PASS |
| Repository HEAD | 8a96fa2b2c690c14fd14f83bb85548462d029134 | PASS |
| Git working tree | Clean | PASS |
| Nginx private key/credential handling | No key copied or displayed | PASS |

## 13. Final Recommendation

**READY FOR RELOAD**

The saved configuration is ready for human review and a separately approved Nginx reload. Before reload, retain the backup and re-run nginx -t. After reload, verify HTTPS redirect, static assets and SPA fallback, security headers, 404 stale routes, API/admin/health method behavior, 429 rate-limit behavior, and Nginx error/access logs. Keep the dashboard disabled until its own controlled-start procedure is separately approved.

## 14. Pre-Reload Corrections

Two targeted corrections were applied after the initial hardening review:

1. Dashboard health now uses the dedicated zone aliza_dashboard_health, defined once with 1 MiB shared memory and 60 requests/minute. The legacy aliza_health definition and its use by the other virtual host were not changed.
2. Both location = /admin and location ^~ /admin/ now apply aliza_api with burst=20 and nodelay before proxying. Their GET/POST restriction, original URI forwarding, loopback backend, no-store headers, security headers, existing timeouts, buffering, and proxy_cache off remain intact.

Candidate syntax and final production nginx -t both succeeded. Effective inspection confirmed one dedicated-zone definition, one health use, and rate limiting in both admin locations. Nginx has **not** been reloaded or restarted.
