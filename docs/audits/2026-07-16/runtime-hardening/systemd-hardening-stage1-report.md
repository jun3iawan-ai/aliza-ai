# Systemd Hardening Stage 1 Report

Audit date: 2026-07-16 (Asia/Jakarta)
Scope: actual host state for aliza-dashboard.service and /opt/aliza-ai.
Method: host inspection plus the required systemctl daemon-reload. The dashboard was not started, restarted, or enabled.

## 1. Executive Summary

**Verdict: PASS WITH WARNINGS**

Stage-1 hardening is present and effective. The dashboard remains disabled and inactive, port 8001 has no listener, the dedicated account has no supplementary groups, required paths are accessible, forbidden source and sensitive paths are inaccessible for the tested operations, lightweight imports succeed, and the dedicated model cache is present. The actual systemd exposure score is **4.1 OK**, improved from **9.2 UNSAFE**.

No stage-1 blocker was identified. ProtectHome, SystemCallFilter, and MemoryDenyWriteExecute remain intentionally deferred. The first start should be controlled and observed; the service should remain disabled until that validation.

No environment values, credentials, password material, hashes, or private-key contents were read into this report.

## 2. Containment Status

| Check | Result | Status |
|---|---|---|
| Expected repository HEAD | 8a96fa2b2c690c14fd14f83bb85548462d029134 | PASS |
| Working tree before report | Two malformed untracked prior-tooling artifacts were removed; status then clean | PASS WITH NOTE |
| Report path tracking | Ignored by .gitignore rule docs/audit/ | PASS |
| Dashboard enablement | disabled | PASS |
| Dashboard activity | inactive | PASS |
| TCP listener on port 8001 | None | PASS |
| Telegram service | active; untouched | PASS |
| Dashboard start/restart/enable | Not performed | PASS |
| Nginx/UFW changes | None | PASS |

## 3. Repository Status

- HEAD: 8a96fa2b2c690c14fd14f83bb85548462d029134
- Expected HEAD: exact match.
- Tracked source changes made by this audit: none.
- The report is below a Git-ignored path. Final status is revalidated after creation.

## 4. Dedicated Service Account

| Property | Actual | Expected | Status |
|---|---|---|---|
| Account | aliza-dashboard | Dedicated static account | PASS |
| UID | 998 | Non-root | PASS |
| Primary group | aliza-dashboard, GID 999 | Dedicated group | PASS |
| Supplementary groups | None | None | PASS |
| Home | /var/lib/aliza-dashboard | Dedicated state path | PASS |
| Shell | /usr/sbin/nologin | Non-login shell | PASS |
| sudo, docker, lxd, adm, systemd-journal | No membership | No membership | PASS |
| Other groups | Only primary group | No sensitive groups | PASS |

## 5. Environment Allowlist

Only names were extracted from /etc/aliza-dashboard/dashboard.env. Values were not displayed or included.

| Variable Name | Category | Present | Notes |
|---|---|---:|---|
| ALIZA_DASHBOARD_HOST | Dashboard | Yes | Bind setting; must stay loopback-only |
| ALIZA_DASHBOARD_PORT | Dashboard | Yes | Listener port |
| ALIZA_DASHBOARD_DOCS_ENABLED | Dashboard | Yes | Explicit docs/OpenAPI gate |
| ALIZA_CHAT_LLM_TIMEOUT_SECONDS | Execution | Yes | LLM timeout bound |
| ALIZA_CHAT_LLM_MAX_CONCURRENCY | Execution | Yes | LLM concurrency bound |
| FORWARDED_ALLOW_IPS | Proxy trust | Yes | Forwarded-header trust |
| HF_HOME | Cache | Yes | Dedicated model cache |
| XDG_CACHE_HOME | Cache | Yes | Dedicated general cache |
| JWT_SECRET | JWT | Yes | Required by authentication; value uninspected |
| DB_PASSWORD | Database | Yes | Used by core/database.py; other DB fields are fixed in source |
| OPENAI_API_KEY | LLM/API | Yes | Required by the configured provider convention |
| SERPER_API_KEY | LLM/API | Yes | Used by registered search tool |
| COINGECKO_API_KEY | Market API | Yes | Used by market-data business components |

All requested names are present. Tracked Python reads only DB_PASSWORD for database configuration. The OpenAI and Serper names are relevant to chat. The CoinGecko name is relevant to market business functionality. No Telegram credential name or obviously unrelated name appears in this 13-name allowlist.

## 6. Filesystem Permissions

getfacl is not installed; extended ACLs could not be enumerated. Results use POSIX metadata and effective account tests.

| Path | Owner | Group | Mode/ACL | Required Access | Test Result |
|---|---|---|---|---|---|
| /etc/aliza-dashboard | root | aliza-dashboard | 0750; ACL unavailable | Traverse | PASS |
| /etc/aliza-dashboard/dashboard.env | root | aliza-dashboard | 0640; ACL unavailable | Read | PASS |
| /var/lib/aliza-dashboard | aliza-dashboard | aliza-dashboard | 0700; ACL unavailable | Read/write | PASS |
| /var/cache/aliza-dashboard | aliza-dashboard | aliza-dashboard | 0700; ACL unavailable | Read/write | PASS |
| /var/cache/aliza-dashboard/huggingface | aliza-dashboard | aliza-dashboard | 0700; ACL unavailable | Read/write | PASS |
| /etc/systemd/system/aliza-dashboard.service | root | root | 0644; ACL unavailable | systemd read | PASS |
| /etc/systemd/system/aliza-dashboard.service.d | root | root | 0755; ACL unavailable | systemd read | PASS |
| /etc/systemd/system/aliza-dashboard.service.d/security.conf | root | root | 0644; ACL unavailable | systemd read | PASS |
| /opt/aliza-ai/data | ubuntu | aliza-dashboard | 2770; ACL unavailable | Read/write | PASS |
| /opt/aliza-ai/memory | ubuntu | aliza-dashboard | 2770; ACL unavailable | Read/write | PASS |
| /opt/aliza-ai/knowledge/vector_store | ubuntu | aliza-dashboard | 2770; ACL unavailable | Read/write | PASS |
| /opt/aliza-ai/api | ubuntu | ubuntu | POSIX; ACL unavailable | No write | PASS: denied |
| /opt/aliza-ai/scripts | ubuntu | ubuntu | POSIX; ACL unavailable | Read/execute, no write | PASS |
| /opt/aliza-ai/venv | ubuntu | ubuntu | POSIX; ACL unavailable | Read/execute, no write | PASS |

## 7. Effective Systemd Directives

Values are from systemctl show after daemon reload. Environment values were not requested.

| Directive | Effective Value | Expected | Status | Compatibility Note |
|---|---|---|---|---|
| User | aliza-dashboard | Dedicated account | PASS | No execution as ubuntu |
| Group | aliza-dashboard | Dedicated group | PASS | No supplementary groups |
| WorkingDirectory | /opt/aliza-ai | Repository root | PASS | Current imports and relative paths |
| ExecStart | venv Python with scripts/run_dashboard.py | Existing launcher | PASS | Inspected, not run |
| EnvironmentFiles | /etc/aliza-dashboard/dashboard.env, required | Dedicated allowlist only | PASS | Base .env reset |
| UMask | 0077 | 0077 | PASS | Private new files |
| Restart / RestartUSec | on-failure / 5s | on-failure / 5s | PASS | Bounded retry |
| TimeoutStartUSec | 1min 30s | 90s | PASS | Initialization allowance |
| TimeoutStopUSec | 1min | 60s | PASS | Executor unwind allowance |
| KillMode | control-group | control-group | PASS | Covers descendants |
| KillSignal / FinalKillSignal | SIGTERM / SIGKILL | SIGTERM / SIGKILL | PASS | Graceful then final |
| SendSIGKILL | yes | yes | PASS | No indefinite stop |
| NoNewPrivileges | yes | yes | PASS | Prevents privilege gain |
| PrivateTmp / PrivateDevices | yes / yes | yes / yes | PASS | Isolated temp and devices |
| ProtectSystem | strict | strict | PASS | Write allowlist works |
| ProtectHome | no | Deferred | WARNING | Stage-2 compatibility test |
| ProtectKernelTunables | yes | yes | PASS | Protected |
| ProtectKernelModules | yes | yes | PASS | Protected |
| ProtectKernelLogs | yes | yes | PASS | Protected |
| ProtectControlGroups | yes | yes | PASS | Protected |
| RestrictSUIDSGID | yes | yes | PASS | Restricted |
| LockPersonality | yes | yes | PASS | Locked |
| RestrictAddressFamilies | AF_UNIX AF_INET AF_INET6 | Required local IPC and IP | PASS | DB/listener and outbound APIs |
| SystemCallArchitectures | native | native | PASS | Native ABI only |
| CapabilityBoundingSet | Empty | Empty | PASS | No retained capabilities |
| AmbientCapabilities | Empty | Empty | PASS | No ambient capabilities |
| ReadWritePaths | data, memory, vector store, state, cache | Exact runtime writes | PASS | Access tests pass |
| ReadOnlyPaths | Empty | No stage-1 requirement | PASS | ProtectSystem supplies policy |
| InaccessiblePaths | Empty | Deferred/optional | WARNING | POSIX denials passed |
| MemoryDenyWriteExecute | no | Deferred | WARNING | Native/ML compatibility risk |
| SystemCallFilter | None, shown as ~ | Deferred | WARNING | Derive from workload |

## 8. Permission Isolation Tests

All checks used test -r, test -w, or test -x as aliza-dashboard; no sensitive content was opened.

| Test | Expected | Result | Status |
|---|---|---|---|
| Read scripts/run_dashboard.py | Allowed | Allowed | PASS |
| Execute venv/bin/python | Allowed | Allowed | PASS |
| Read dedicated environment | Allowed | Allowed | PASS |
| Write data, memory, vector store | Allowed | Allowed | PASS |
| Write state and cache | Allowed | Allowed | PASS |
| Read /home/ubuntu/.ssh | Denied | Denied | PASS |
| Read conventional RSA/Ed25519 private-key paths | Denied | Denied | PASS |
| Read Docker socket | Denied | Denied | PASS |
| Write api, scripts, or venv | Denied | Denied | PASS |
| Read legacy /opt/aliza-ai/.env used by Telegram | Denied | Denied | PASS |

Telegram environment-file metadata points to the legacy repository .env; the dashboard account cannot read it. Telegram itself was not changed, reloaded, restarted, or otherwise acted upon.

## 9. Dependency and Cache Readiness

- Imports as aliza-dashboard succeeded for fastapi, uvicorn, jwt, and argon2.
- PYTHONDONTWRITEBYTECODE=1 and dedicated XDG_CACHE_HOME and HF_HOME were used.
- api.server was not imported; no database, model, network, or socket was used.
- Dedicated cache owner/group is aliza-dashboard:aliza-dashboard and root mode is 0700.
- models--sentence-transformers--all-MiniLM-L6-v2 is present with blobs, refs, snapshots, and .no_exist structure.
- Cache size is approximately 88 MiB.
- This proves on-disk readiness, not model-load compatibility.

## 10. Systemd Security Score

- Before: **9.2 UNSAFE**
- After: **4.1 OK**
- Change: **5.1 points lower exposure**, approximately **55.4%** relative reduction.

Improvements include non-root identity, empty capabilities, strict filesystem policy, private temp/devices, kernel/cgroup protection, restricted address families, native syscall architecture, locked personality, and restrictive umask.

Remaining contributors include host networking, no IP allow/deny policy, no ProtectHome/ProtectProc/ProcSubset/PrivateUsers, unrestricted namespace creation and realtime scheduling, no syscall filter, no MemoryDenyWriteExecute, and candidates ProtectClock, ProtectHostname, and RemoveIPC.

## 11. Warnings and Blockers

### Blockers before service may be run

None identified by stage-1 checks. This does not authorize unattended enablement; first run requires explicit approval, observation, and rollback readiness.

### Non-blocking warnings

1. systemd-analyze verify exited 0 but reported unrelated warnings: tat_agent.service uses a legacy /var/run PID path, and installed snapd.service has RestartMode unsupported by this systemd. Neither refers to the dashboard.
2. Extended ACLs could not be enumerated because getfacl is unavailable; POSIX and effective access checks passed.
3. Cache presence was verified without model loading.
4. Required IP networking remains and systemd does not constrain egress.
5. Two malformed untracked prior-tooling files were found and removed to restore the mandated clean repository.

### Hardening intentionally deferred

- ProtectHome: test all cache/home assumptions under dedicated paths.
- SystemCallFilter: test Python, database, DNS/TLS, model, and executor behavior.
- MemoryDenyWriteExecute: test native Python, Argon2, numerical, tokenizer, and ML compatibility.

## 12. Files Changed on Host

The following are evidenced hardening components by current metadata, effective-unit inclusion, or the discovered backup. This is not a claim that each changed during this audit.

- Dedicated user and group aliza-dashboard.
- /etc/aliza-dashboard and dashboard.env.
- /etc/systemd/system/aliza-dashboard.service.d/security.conf.
- /var/lib/aliza-dashboard.
- /var/cache/aliza-dashboard and dedicated Hugging Face model cache.
- Group/mode state on data, memory, and knowledge/vector_store.
- Backup /home/ubuntu/aliza-ai-security-backups/systemd-dashboard-20260716 with original unit, original drop-in, combined capture, and permissions record.
- This ignored report and its private runtime directory.

During this audit, the only persistent requested addition is this report directory/file. The required daemon-reload was performed. No source, Nginx, UFW, Telegram unit, or service runtime state was changed.

## 13. Rollback Commands

Documentation only; **not executed**. The referenced backup was actually found.

~~~bash
sudo systemctl stop aliza-dashboard.service
sudo systemctl disable aliza-dashboard.service
sudo install -o root -g root -m 0644 \
  /home/ubuntu/aliza-ai-security-backups/systemd-dashboard-20260716/aliza-dashboard.service \
  /etc/systemd/system/aliza-dashboard.service
sudo install -d -o root -g root -m 0755 \
  /etc/systemd/system/aliza-dashboard.service.d
sudo install -o root -g root -m 0644 \
  /home/ubuntu/aliza-ai-security-backups/systemd-dashboard-20260716/aliza-dashboard.service.d/security.conf \
  /etc/systemd/system/aliza-dashboard.service.d/security.conf
sudo systemctl daemon-reload
sudo systemd-analyze verify /etc/systemd/system/aliza-dashboard.service
systemctl is-enabled aliza-dashboard.service
systemctl is-active aliza-dashboard.service
~~~

Filesystem rollback must be reviewed against pre-hardening-permissions.txt because historical ownership/modes would remove dedicated runtime access and could affect current data. Account, environment, and cache removal need separate approval and dependency review.

## 14. Final Recommendation

The dashboard is **suitable for an explicitly approved controlled start** based on stage-1 containment, account isolation, permissions, imports, and cache readiness. It is **not ready for unattended enablement**. Keep it **disabled** until a maintenance window permits a monitored smoke test covering import, local PostgreSQL, loopback binding, authentication, LLM timeout/shutdown, model loading, and clean stop within 60 seconds.

Next steps:

1. Keep disabled and inactive until the controlled test is approved.
2. Recheck containment and preserve backup before the test.
3. Confirm only loopback port 8001 opens, no home fallback occurs, and shutdown is clean.
4. Then evaluate ProtectHome, ProtectProc, ProcSubset, namespace restrictions, RestrictRealtime, IP egress policy, tested SystemCallFilter, and MemoryDenyWriteExecute.
5. Address Nginx hardening independently before public re-exposure; Nginx was unchanged here.
