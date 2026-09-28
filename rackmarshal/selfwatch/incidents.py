#!/usr/bin/env python3
"""RackMarshal self-incident signal evaluator stub (Phase 3 Step 4.4).

Design: packaging/SELF_INCIDENTS.md

This module is intentionally NOT imported by status_api.py or run_*_cycle.py
in Step 4.4a. It only maps self_watch-shaped inputs to desired open signals
in memory — no state.db writes, no notifications.
"""

from __future__ import annotations

from typing import Any


def freshness_signal_key(domain: str) -> str:
    return f"freshness:{domain}"


def unit_signal_key(unit_name: str) -> str:
    return f"unit:{unit_name}"


def evaluate_self_signals(
    freshness: dict[str, dict[str, Any]] | None,
    units: dict[str, str] | None,
    notifications: dict[str, Any] | None,
    cycle_health: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return desired OPEN self-incident descriptors (not persisted).

    Each item: signal_key, incident_type, severity, detail (dict).
    """
    desired: list[dict[str, Any]] = []
    freshness = freshness or {}
    units = units or {}
    notifications = notifications or {}
    cycle_health = cycle_health or {}

    for domain, row in sorted(freshness.items()):
        state = (row or {}).get("state")
        if state == "STALE":
            desired.append(
                {
                    "signal_key": freshness_signal_key(domain),
                    "incident_type": "FRESHNESS_STALE",
                    "severity": "warning",
                    "detail": {
                        "domain": domain,
                        "age_seconds": row.get("age_seconds"),
                        "stale_after_seconds": row.get(
                            "stale_after_seconds"
                        ),
                    },
                }
            )
        elif state == "MISSING":
            desired.append(
                {
                    "signal_key": freshness_signal_key(domain),
                    "incident_type": "FRESHNESS_MISSING",
                    "severity": "warning",
                    "detail": {"domain": domain},
                }
            )

    for name, state in sorted(units.items()):
        if state == "failed":
            desired.append(
                {
                    "signal_key": unit_signal_key(name),
                    "incident_type": "UNIT_FAILED",
                    "severity": "critical",
                    "detail": {"unit": name, "active_state": state},
                }
            )
        elif name == "rackmarshal-status.service" and state != "active":
            desired.append(
                {
                    "signal_key": unit_signal_key(name),
                    "incident_type": "UNIT_INACTIVE",
                    "severity": "critical",
                    "detail": {"unit": name, "active_state": state},
                }
            )
        elif name.endswith(".timer") and state != "active":
            desired.append(
                {
                    "signal_key": unit_signal_key(name),
                    "incident_type": "UNIT_INACTIVE",
                    "severity": "warning",
                    "detail": {"unit": name, "active_state": state},
                }
            )

    for name, row in sorted(cycle_health.items()):
        row = row or {}
        if row.get("health_state") != "FAILED":
            continue
        desired.append(
            {
                "signal_key": f"cycle:{name}",
                "incident_type": "CYCLE_FAILED",
                "severity": "critical",
                "detail": {
                    "unit": name,
                    "health_state": row.get("health_state"),
                    "failure_count": row.get("failure_count"),
                    "last_result_at": row.get("last_result_at"),
                    "last_success_at": row.get("last_success_at"),
                    "last_failure_at": row.get("last_failure_at"),
                    "last_exit_code": row.get("last_exit_code"),
                    "last_exit_status": row.get("last_exit_status"),
                },
            }
        )

    failed = int(notifications.get("failed") or 0)
    pending_older = int(
        notifications.get("pending_older_than_seconds") or 0
    )
    if failed > 0:
        desired.append(
            {
                "signal_key": "notify:FAILED",
                "incident_type": "NOTIFY_FAILED",
                "severity": "warning",
                "detail": {"failed": failed},
            }
        )
    if pending_older > 0:
        desired.append(
            {
                "signal_key": "notify:PENDING_STALE",
                "incident_type": "NOTIFY_BACKLOG",
                "severity": "warning",
                "detail": {
                    "pending_older_than_seconds": pending_older,
                    "pending_max_age_seconds": notifications.get(
                        "pending_max_age_seconds"
                    ),
                },
            }
        )

    return desired


def list_desired_open_keys(
    freshness=None,
    units=None,
    notifications=None,
) -> list[str]:
    return [
        item["signal_key"]
        for item in evaluate_self_signals(
            freshness, units, notifications
        )
    ]


if __name__ == "__main__":
    # Tiny self-check (no DB).
    sample = evaluate_self_signals(
        {"PVE": {"state": "STALE", "age_seconds": 1200, "stale_after_seconds": 900}},
        {"rackmarshal-status.service": "active"},
        {"pending": 0, "failed": 0, "pending_older_than_seconds": 0},
    )
    assert any(i["signal_key"] == "freshness:PVE" for i in sample)
    assert list_desired_open_keys(
        {"PVE": {"state": "OK"}},
        {"rackmarshal-status.service": "active"},
        {},
    ) == []
    print("SELF_INCIDENTS_STUB_OK", sample)
