#!/usr/bin/env python3
"""RackMarshal notification policy gate (Phase 3 Step 3).

Defaults match today's behavior: allow all OPENED/RECOVERED enqueues.
Optional conf keys (see packaging/NOTIFY_POLICY.md / rackmarshal.conf.example)
only change behavior when explicitly set.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from rackmarshal.core.config import load_config

# Local wall clock for quiet hours (site-local timezone).
_LOCAL_TZ = ZoneInfo("America/New_York")

_SEVERITY_RANK = {
    "info": 10,
    "warning": 20,
    "critical": 30,
    "urgent": 40,
}


@dataclass(frozen=True)
class NotifyDecision:
    allow: bool
    reason: str
    severity: str


def _optional_int(config, key):
    raw = (config or {}).get(key)
    if raw is None or str(raw).strip() == "":
        return None
    return int(str(raw).strip())


def _optional_str(config, key):
    raw = (config or {}).get(key)
    if raw is None:
        return None
    value = str(raw).strip()
    return value or None


def default_severity(notification_type: str) -> str:
    if notification_type == "OPENED":
        return "warning"
    if notification_type == "RECOVERED":
        return "info"
    if notification_type == "REMINDER":
        return "warning"
    return "warning"


def _in_quiet_hours(now_local: datetime, start_hour: int, end_hour: int) -> bool:
    """True if local hour is inside [start, end) wrapping midnight if needed."""
    hour = now_local.hour
    if start_hour == end_hour:
        return False
    if start_hour < end_hour:
        return start_hour <= hour < end_hour
    # wraps midnight, e.g. 22 -> 7
    return hour >= start_hour or hour < end_hour


def evaluate(
    notification_type: str,
    *,
    severity: str | None = None,
    config=None,
    now: datetime | None = None,
) -> NotifyDecision:
    """Return whether a notification should be enqueued.

    When NOTIFY_* keys are absent, always allow (today's behavior).
    """
    if config is None:
        config = load_config()

    sev = (severity or default_severity(notification_type)).lower()
    if sev not in _SEVERITY_RANK:
        sev = default_severity(notification_type)

    # Reminders are opt-in; today's pipeline never emits REMINDER.
    reminders = _optional_str(config, "NOTIFY_REMINDERS")
    if notification_type == "REMINDER":
        if reminders in (None, "", "0", "false", "False", "no", "off"):
            return NotifyDecision(False, "reminders_disabled", sev)

    min_sev = _optional_str(config, "NOTIFY_MIN_SEVERITY")
    if min_sev:
        min_sev = min_sev.lower()
        if min_sev in _SEVERITY_RANK and _SEVERITY_RANK[sev] < _SEVERITY_RANK[min_sev]:
            return NotifyDecision(False, f"below_min_severity:{min_sev}", sev)

    quiet_start = _optional_int(config, "NOTIFY_QUIET_HOURS_START")
    quiet_end = _optional_int(config, "NOTIFY_QUIET_HOURS_END")
    if quiet_start is not None and quiet_end is not None:
        allow_recovered = _optional_str(config, "NOTIFY_ALLOW_RECOVERED_IN_QUIET")
        if allow_recovered is None:
            allow_recovered = "1"
        now_local = now.astimezone(_LOCAL_TZ) if now else datetime.now(_LOCAL_TZ)
        if _in_quiet_hours(now_local, quiet_start, quiet_end):
            if notification_type == "RECOVERED" and allow_recovered not in (
                "0",
                "false",
                "False",
                "no",
                "off",
            ):
                return NotifyDecision(True, "recovered_allowed_in_quiet", sev)
            if sev in ("critical", "urgent"):
                return NotifyDecision(True, "severity_bypasses_quiet", sev)
            return NotifyDecision(False, "quiet_hours", sev)

    return NotifyDecision(True, "default_allow", sev)


def should_enqueue(notification_type: str, **kwargs) -> NotifyDecision:
    """Alias used by enqueue_incident_notifications."""
    return evaluate(notification_type, **kwargs)
