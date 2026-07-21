"""
Notification governor: shared, disk-persisted infrastructure for the "noise"
alert checkers (near support/resistance, RSI extreme, big move, breakout,
volume spike, funding, whale).

Why this exists: every checker used to keep its own cooldown/dedup state in a
plain in-memory module dict. `aliza-telegram.service` is restarted frequently
(manual deploys, systemd `Restart=always`), which wiped those dicts and made
every "4 jam cooldown" reset to zero on each restart — see
NOTIFIKASI_MITIGASI_REPORT.md (Diagnosis) for the incident this fixes.

This module provides four independent pieces that callers opt into:
  - a persisted key/value store for cooldown timestamps and dedup values
    (survives process restart, unlike a module-level dict)
  - a per-coin snapshot freshness check (epoch-float aware — the previous
    per-coin staleness check silently no-op'd for every coin, see report)
  - an in-memory short-lived digest buffer that turns a burst of alerts
    within one flush cycle into a single combined message
  - a persisted per-hour dispatch counter used as a global rate limit

Nothing here talks to Telegram directly — callers still dispatch via
`safe_dispatch`; this module only decides whether/how a message should go out.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from typing import Any, NamedTuple

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore[misc, assignment]

logger = logging.getLogger(__name__)

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STATE_FILE = os.path.join(_ROOT, "data", "alert_cooldown_state.json")

BIG_MOVE_COOLDOWN_SEC = int(os.getenv("BIG_MOVE_COOLDOWN_SEC", "7200"))
ALERT_DIGEST_THRESHOLD = int(os.getenv("ALERT_DIGEST_THRESHOLD", "5"))
MAX_ALERTS_PER_HOUR = int(os.getenv("MAX_ALERTS_PER_HOUR", "15"))
SNAPSHOT_MAX_AGE_SEC = int(os.getenv("SNAPSHOT_MAX_AGE_SEC", "300"))

# ---------------------------------------------------------------------------
# Persisted key/value store (cooldown timestamps, dedup values, rate-limit
# counters). Single small JSON file, namespaced dict-of-dicts, atomic write
# so a SIGKILL mid-write (systemd does this on shutdown timeout — see report)
# can't corrupt it.
# ---------------------------------------------------------------------------

_state_cache: dict[str, Any] | None = None


def _load_state() -> dict[str, Any]:
    global _state_cache
    if _state_cache is not None:
        return _state_cache
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                _state_cache = loaded
                return _state_cache
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(
                "notification_governor: failed to load %s (%s) — starting fresh",
                STATE_FILE,
                e,
            )
    _state_cache = {}
    return _state_cache


def _save_state() -> None:
    if _state_cache is None:
        return
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    tmp_path = f"{STATE_FILE}.tmp"
    with open(tmp_path, "w") as f:
        json.dump(_state_cache, f)
    os.replace(tmp_path, STATE_FILE)


def reset_state_for_tests() -> None:
    """Test-only: clear in-memory + on-disk state (persisted cooldowns, digest
    buffer, stats counters) so tests don't leak into each other."""
    global _state_cache, _pending, _stats
    _state_cache = {}
    _pending = []
    _stats = {}
    if os.path.exists(STATE_FILE):
        try:
            os.remove(STATE_FILE)
        except OSError:
            pass


def get_value(namespace: str, key: str, default: Any = None) -> Any:
    return _load_state().get(namespace, {}).get(key, default)


def set_value(namespace: str, key: str, value: Any) -> None:
    state = _load_state()
    state.setdefault(namespace, {})[key] = value
    _save_state()


# ---------------------------------------------------------------------------
# Persisted cooldown gate — replaces the pattern of a module-level
# `dict[key, datetime]` + manual elapsed-time comparison used previously by
# every checker (near_support/near_resistance/rsi/big_move/whale in
# interfaces/telegram_bot.py, plus breakout_detector.py,
# volume_spike_detector.py and funding_rate_monitor.py).
# ---------------------------------------------------------------------------


def is_cooldown_allowed(namespace: str, key: str, cooldown_sec: float, now: float | None = None) -> bool:
    """True if `key` has not fired within `cooldown_sec`. Does not record a hit —
    call `record_cooldown` once the caller actually decides to send."""
    now = time.time() if now is None else now
    last = get_value(f"cooldown:{namespace}", key)
    if last is None:
        return True
    try:
        return (now - float(last)) >= cooldown_sec
    except (TypeError, ValueError):
        return True


def record_cooldown(namespace: str, key: str, now: float | None = None) -> None:
    now = time.time() if now is None else now
    set_value(f"cooldown:{namespace}", key, now)


def is_duplicate_value(namespace: str, key: str, value: float, epsilon: float = 0.01) -> bool:
    """True if `value` is (near-)identical to the last recorded value for `key`."""
    last = get_value(f"dedup:{namespace}", key)
    if last is None:
        return False
    try:
        return abs(float(value) - float(last)) < epsilon
    except (TypeError, ValueError):
        return False


def record_value(namespace: str, key: str, value: Any) -> None:
    set_value(f"dedup:{namespace}", key, value)


# ---------------------------------------------------------------------------
# Per-coin snapshot freshness. market_analyzer.py stores per-coin
# `timestamp` as `time.time()` (epoch float). The freshness check that used
# to live in big_move_checker compared it with `hasattr(ts, "timestamp")`
# (always False for a float) then `datetime.fromisoformat(str(ts))` (always
# raises on an epoch string) inside a bare `except Exception: pass` — so it
# silently never ran, for any coin, in any checker. This is the fixed
# version; every checker should call it before building an alert message.
# ---------------------------------------------------------------------------


def coin_snapshot_age_sec(coin_data: dict, now: float | None = None) -> float | None:
    if not isinstance(coin_data, dict):
        return None
    ts = coin_data.get("timestamp")
    if ts is None:
        ts = coin_data.get("last_updated")
    if ts is None:
        return None
    now = time.time() if now is None else now
    try:
        if isinstance(ts, (int, float)):
            return max(0.0, now - float(ts))
        if hasattr(ts, "timestamp"):
            return max(0.0, now - ts.timestamp())
        return max(0.0, now - datetime.fromisoformat(str(ts)).timestamp())
    except (TypeError, ValueError):
        return None


def is_coin_snapshot_fresh(coin_data: dict, max_age_sec: int | None = None, now: float | None = None) -> bool:
    """True if fresh OR age is unknown (missing timestamp isn't proof of staleness —
    it just means we can't check, so we don't block on it)."""
    age = coin_snapshot_age_sec(coin_data, now)
    if age is None:
        return True
    return age <= (SNAPSHOT_MAX_AGE_SEC if max_age_sec is None else max_age_sec)


# ---------------------------------------------------------------------------
# Digest buffer — collects alerts that passed cooldown+freshness during a
# flush cycle (~60s, see alert_digest_flush_job) and, if enough piled up,
# returns one combined message instead of one Telegram message per alert.
# In-memory only: losing a partially-filled buffer on a restart just drops a
# couple of messages rather than causing any spam risk, so persistence isn't
# worth the complexity here (unlike the cooldown store above).
# ---------------------------------------------------------------------------


class PendingAlert(NamedTuple):
    alert_type: str
    group_label: str
    line: str
    full_message: str


_pending: list[PendingAlert] = []

# Observability counters (in-memory; reset on restart — acceptable for a
# "last N hours" debug view, see /alert_stats).
_stats: dict[str, dict[str, int]] = {}


def _bump_stat(alert_type: str, field: str, by: int = 1) -> None:
    bucket = _stats.setdefault(alert_type, {})
    bucket[field] = bucket.get(field, 0) + by


def queue_alert(alert_type: str, group_label: str, line: str, full_message: str) -> None:
    _pending.append(PendingAlert(alert_type, group_label, line, full_message))
    _bump_stat(alert_type, "queued")


def pending_count() -> int:
    return len(_pending)


def _wib_now_label() -> str:
    if ZoneInfo is not None:
        try:
            return datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%Y-%m-%d %H:%M WIB")
        except Exception:
            pass
    from datetime import timedelta

    return (datetime.utcnow() + timedelta(hours=7)).strftime("%Y-%m-%d %H:%M WIB")


def build_digest_message(items: list[PendingAlert]) -> str:
    groups: dict[str, list[str]] = {}
    for it in items:
        groups.setdefault(it.group_label, []).append(it.line)
    lines = [f"🔔 RINGKASAN ALERT ({len(items)} sinyal dalam 1 siklus)", ""]
    for label, group_lines in groups.items():
        lines.append(f"• {label} ({len(group_lines)}):")
        for gl in group_lines:
            lines.append(f"   - {gl}")
    lines.append("")
    lines.append("💡 Terlalu banyak sinyal sekaligus dirangkum jadi satu pesan agar tidak membanjiri chat.")
    lines.append(f"⏰ {_wib_now_label()}")
    lines.append("——")
    lines.append("Aliza Engine • Digest")
    return "\n".join(lines)


def flush_pending(threshold: int | None = None) -> list[str]:
    """Drain the buffer and return the Telegram message(s) that should be sent:
    either the individual messages (if under threshold) or one combined digest."""
    global _pending
    items = _pending
    _pending = []
    if not items:
        return []
    threshold = ALERT_DIGEST_THRESHOLD if threshold is None else threshold
    if len(items) < threshold:
        for it in items:
            _bump_stat(it.alert_type, "sent_individual")
        return [it.full_message for it in items]
    for it in items:
        _bump_stat(it.alert_type, "sent_digested")
    return [build_digest_message(items)]


def record_skipped_stale(alert_type: str) -> None:
    _bump_stat(alert_type, "skipped_stale")


def get_stats_snapshot() -> dict[str, dict[str, int]]:
    snapshot: dict[str, dict[str, int]] = {k: dict(v) for k, v in _stats.items()}
    now = time.time()
    snapshot["_rate_limit"] = {
        "sent_this_hour": get_value("rate_limit_sent", _hour_bucket(now), 0),
        "suppressed_this_hour": get_value("rate_limit_suppressed", _hour_bucket(now), 0),
        "max_per_hour": MAX_ALERTS_PER_HOUR,
    }
    return snapshot


# ---------------------------------------------------------------------------
# Global per-hour rate limit — a safety net independent of per-checker
# cooldowns: even if a future bug lets alerts through, no more than
# MAX_ALERTS_PER_HOUR "noise" alerts go out in any given clock hour.
# Persisted so it isn't reset by the same restarts that caused the incident
# this whole module exists to prevent.
# ---------------------------------------------------------------------------


def _hour_bucket(now: float) -> str:
    return datetime.utcfromtimestamp(now).strftime("%Y%m%d%H")


def allow_rate_limited_dispatch(now: float | None = None) -> bool:
    """True if the message may be sent under the hourly cap. If False, the
    caller must not send it — this function has already recorded it as
    suppressed so it can be summarized later."""
    now = time.time() if now is None else now
    bucket = _hour_bucket(now)
    sent = get_value("rate_limit_sent", bucket, 0)
    if sent >= MAX_ALERTS_PER_HOUR:
        suppressed = get_value("rate_limit_suppressed", bucket, 0)
        set_value("rate_limit_suppressed", bucket, suppressed + 1)
        return False
    set_value("rate_limit_sent", bucket, sent + 1)
    return True


def pop_previous_hour_summary(now: float | None = None) -> str | None:
    """Called once per flush tick. If the clock hour just rolled over and the
    hour that just ended had suppressed alerts, return a one-line summary to
    send; otherwise None. Idempotent per hour (uses a separate 'notified'
    marker so the summary is only produced once)."""
    now = time.time() if now is None else now
    bucket = _hour_bucket(now)
    prev_bucket = _hour_bucket(now - 3600)
    if prev_bucket == bucket:
        return None
    suppressed = get_value("rate_limit_suppressed", prev_bucket, 0)
    if not suppressed:
        return None
    if get_value("rate_limit_summary_sent", prev_bucket, False):
        return None
    set_value("rate_limit_summary_sent", prev_bucket, True)
    hour_label = f"{prev_bucket[8:10]}:00-{bucket[8:10]}:00 UTC"
    return f"⏳ +{suppressed} alert lain tersaring pada jam {hour_label} (rate limit {MAX_ALERTS_PER_HOUR}/jam) — lihat log untuk detail."
