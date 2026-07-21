#!/usr/bin/env bash

set -euo pipefail

readonly REPO_DIR="/opt/aliza-ai"
readonly SERVICE="aliza-telegram.service"

log() {
    printf '[deploy] %s\n' "$*"
}

fail() {
    printf '[deploy] ERROR: %s\n' "$*" >&2
    exit 1
}

cd "$REPO_DIR" || fail "Cannot access repository: $REPO_DIR"

if [[ -n "$(git status --porcelain)" ]]; then
    git status --short
    fail "Working tree is not clean; commit, stash, or remove local changes before deploying."
fi

current_branch="$(git branch --show-current)"
if [[ "$current_branch" != "main" ]]; then
    fail "Deployment must run from main; current branch is '$current_branch'."
fi

before_commit="$(git rev-parse HEAD)"
log "Commit before pull: $before_commit"

log "Pulling origin/main with fast-forward only..."
git pull --ff-only origin main

after_commit="$(git rev-parse HEAD)"
log "Commit after pull:  $after_commit"

log "Restarting $SERVICE..."
sudo systemctl restart "$SERVICE"

service_state="$(systemctl is-active "$SERVICE" || true)"
log "Service state after restart: $service_state"
if [[ "$service_state" != "active" ]]; then
    systemctl status "$SERVICE" --no-pager || true
    fail "$SERVICE did not become active after restart."
fi

log "Deploy completed successfully: $before_commit -> $after_commit"
log "Run the manual smoke test in docs/runbooks/smoke-test.md."
