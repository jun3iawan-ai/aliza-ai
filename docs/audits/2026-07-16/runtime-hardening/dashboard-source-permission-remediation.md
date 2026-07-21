# Dashboard Source Permission Remediation

## 1. Verdict

**PASS WITH WARNINGS**

The dedicated dashboard account can now read all 114 in-scope Git-tracked runtime source/config files while remaining unable to write the remediated source files. The legacy repository dotenv, other source writes, Docker socket, and Ubuntu SSH directory remain inaccessible. The dashboard was not started, restarted, or enabled.

## 2. Root Cause

`core/environment.py` was committed as a normal non-executable Git file but its host filesystem metadata was `ubuntu:ubuntu` mode `0600`. The dedicated `aliza-dashboard` account therefore received PermissionError while importing it.

The inventory found the same host metadata and readability failure on one additional Git-tracked, non-secret Python source file: `engine/monitoring/market_monitor.py`. Git records both files as regular mode `100644`, indicating that the restrictive host mode was not an intentional executable or repository permission policy.

## 3. Runtime Source Readability Inventory

The inventory used `git ls-files` for `main.py`, `api/`, `core/`, `engine/`, `interfaces/`, `scripts/`, `config/`, and `dashboard/`. Environment files, certificates/keys, docs, tests, backups, `.bak`, virtualenv, and data/state paths were excluded without opening their contents.

| Stage | Tracked regular files | Readable | Unreadable |
|---|---:|---:|---:|
| Before remediation | 114 | 112 | 2 |
| After remediation | 114 | 114 | 0 |

Unreadable files before remediation:

| Path | Owner | Group | Mode | Readable |
|---|---|---|---:|---|
| `core/environment.py` | ubuntu | ubuntu | 0600 | no |
| `engine/monitoring/market_monitor.py` | ubuntu | ubuntu | 0600 | no |

No other in-scope runtime source/config file was unreadable after remediation.

## 4. Permission Change

Only the following two files were changed, without recursive chmod or chown:

| Path | Before | After |
|---|---|---|
| `/opt/aliza-ai/core/environment.py` | `0600 ubuntu:ubuntu` | `0640 ubuntu:aliza-dashboard` |
| `/opt/aliza-ai/engine/monitoring/market_monitor.py` | `0600 ubuntu:ubuntu` | `0640 ubuntu:aliza-dashboard` |

Ownership remains with `ubuntu`; the dedicated group receives read-only access; other receives no access; and no executable bit was added.

## 5. Effective Access Tests

| Test as `aliza-dashboard` | Result |
|---|---|
| Read `core/environment.py` | PASS |
| Write `core/environment.py` denied | PASS |
| Read `engine/monitoring/market_monitor.py` | PASS |
| Write `engine/monitoring/market_monitor.py` denied | PASS |
| Import `core.environment` with dotenv disabled | PASS |

The isolated import used `ALIZA_DOTENV_ENABLED=false` and `PYTHONDONTWRITEBYTECODE=1`. It did not import database code, use the network, access dotenv, or create bytecode.

## 6. Sensitive Path Isolation

Effective access tests confirmed that `aliza-dashboard` still cannot:

- read `/opt/aliza-ai/.env`;
- write the two remediated files;
- write `core/database.py` or `api/server.py`;
- read `/var/run/docker.sock`;
- read `/home/ubuntu/.ssh`.

The account has only its dedicated primary group and no supplementary sensitive group.

## 7. Repository and Service Containment

| Check | Final state | Result |
|---|---|---|
| Repository HEAD | `935b8b9ebe16616841390ff8c8ffe927493d30ba` | PASS |
| Git working tree | Clean | PASS |
| Git diff check | Clean | PASS |
| Dashboard enablement | disabled | PASS |
| Dashboard activity | inactive | PASS |
| Port 8001 | No listener | PASS |
| Nginx | active | PASS |
| Telegram | active | PASS |

No source, systemd, Nginx, UFW, environment, database, certificate, dependency, or Git commit was changed.

## 8. Remaining Warnings

- POSIX owner/group changes and non-executable read modes are host state and are not fully represented by Git. Future deployment, checkout, or file-replacement tooling must preserve the dedicated read group and must not recreate runtime source as owner-only `0600`.
- The controlled start has not been repeated after this permission remediation.

## 9. Final Recommendation

Keep `aliza-dashboard.service` disabled and inactive. The source-readability blocker is remediated, and a separately approved controlled-start retry may now verify stable startup, loopback binding, health, authorization, resource behavior, and clean shutdown.
