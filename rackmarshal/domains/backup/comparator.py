#!/usr/bin/env python3

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from rackmarshal.core.config import state_db


DB_PATH = state_db()

VALID_BASELINE_STATES = {
    "VERIFIED",
    "EXPECTED",
    "KNOWN-ISSUE",
    "FAILED",
    "DECOMMISSIONED",
}



# --- STEP3_BACKUP_EXCLUDE_VMIDS begin ---

# --- STEP4_TIMEMACHINE begin ---

# --- STEP56_PHONES_MESSAGES begin ---
def _conf_csv(key, default=""):
    import os
    from pathlib import Path
    raw = os.environ.get(key, "")
    if not raw:
        conf = Path("/etc/rackmarshal/rackmarshal.conf")
        if conf.is_file():
            for line in conf.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith(key + "="):
                    raw = line.split("=", 1)[1].strip()
                    break
    if not raw:
        raw = default
    return {p.strip() for p in raw.split(",") if p.strip()}


def _conf_float(key, default):
    import os
    from pathlib import Path
    raw = os.environ.get(key, "")
    if not raw:
        conf = Path("/etc/rackmarshal/rackmarshal.conf")
        if conf.is_file():
            for line in conf.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith(key + "="):
                    raw = line.split("=", 1)[1].strip()
                    break
    try:
        return float(raw) if raw else float(default)
    except ValueError:
        return float(default)


def phone_results(pbs_store_probe):
    results = []
    if not isinstance(pbs_store_probe, dict) or pbs_store_probe.get("_error"):
        return results
    phones = pbs_store_probe.get("phones") or {}
    if not isinstance(phones, dict):
        return results
    sla = _conf_float("BACKUP_PHONE_SLA_HOURS", 168.0)
    alert = _conf_csv("BACKUP_PHONE_ALERT_TARGETS", "")
    for who in sorted(alert):
        entry = phones.get(who)
        if not isinstance(entry, dict):
            changes = [{"field": "phone_backup", "expected": "present", "actual": "missing_probe"}]
        else:
            changes = []
            if not entry.get("exists"):
                changes.append({"field": "phone_backup", "expected": "present", "actual": "missing"})
            else:
                age = entry.get("age_hours")
                if age is None or float(age) > sla:
                    changes.append({
                        "field": "phone_age_hours",
                        "expected": f"<= {sla}",
                        "actual": None if age is None else round(float(age), 3),
                    })
        results.append({
            "resource_type": "backup_phone",
            "resource_key": who,
            "display_name": f"Phone backup ({who})",
            "baseline_state": "VERIFIED",
            "outcome": "STATUS-CHANGED" if changes else "MATCH",
            "changes": changes,
        })
    return results


def messages_results(pbs_store_probe):
    results = []
    if not isinstance(pbs_store_probe, dict) or pbs_store_probe.get("_error"):
        return results
    messages = pbs_store_probe.get("messages") or {}
    if not isinstance(messages, dict):
        return results
    sla = _conf_float("BACKUP_MESSAGES_SLA_HOURS", 36.0)
    people = _conf_csv("BACKUP_MESSAGES_ALERT_TARGETS", "")
    kinds = (("pull", "Messages pull"), ("snap", "Messages daily snap"), ("repl", "Messages backupssd repl"))
    for who in sorted(people):
        entry = messages.get(who)
        if not isinstance(entry, dict):
            for kind, label in kinds:
                results.append({
                    "resource_type": "backup_messages",
                    "resource_key": f"{who}:{kind}",
                    "display_name": f"{label} ({who})",
                    "baseline_state": "VERIFIED",
                    "outcome": "STATUS-CHANGED",
                    "changes": [{"field": "messages", "expected": "present", "actual": "missing_probe"}],
                })
            continue
        if entry.get("error"):
            for kind, label in kinds:
                results.append({
                    "resource_type": "backup_messages",
                    "resource_key": f"{who}:{kind}",
                    "display_name": f"{label} ({who})",
                    "baseline_state": "VERIFIED",
                    "outcome": "STATUS-CHANGED",
                    "changes": [{"field": "messages", "expected": "ok", "actual": entry.get("error")}],
                })
            continue
        for kind, label in kinds:
            sub = entry.get(kind) or {}
            changes = []
            age = sub.get("age_hours") if isinstance(sub, dict) else None
            if age is None or float(age) > sla:
                changes.append({
                    "field": f"messages_{kind}_age_hours",
                    "expected": f"<= {sla}",
                    "actual": None if age is None else round(float(age), 3),
                })
            results.append({
                "resource_type": "backup_messages",
                "resource_key": f"{who}:{kind}",
                "display_name": f"{label} ({who})",
                "baseline_state": "VERIFIED",
                "outcome": "STATUS-CHANGED" if changes else "MATCH",
                "changes": changes,
            })
    return results
# --- STEP56_PHONES_MESSAGES end ---


# --- STEP7_HOST_VERIFY begin ---

def rsync_filebackups_results(pbs_store_probe):
    results = []
    if not isinstance(pbs_store_probe, dict) or pbs_store_probe.get("_error"):
        return results
    rb = pbs_store_probe.get("rsync_filebackups")
    if not isinstance(rb, dict):
        results.append({
            "resource_type": "backup_rsync_filebackups",
            "resource_key": "homelab-rsync-backups",
            "display_name": "Host rsync file-backups",
            "baseline_state": "VERIFIED",
            "outcome": "STATUS-CHANGED",
            "changes": [{"field": "rsync_filebackups", "expected": "present", "actual": "missing_probe"}],
        })
        return results
    sla_h = _conf_float("BACKUP_RSYNC_FILEBACKUPS_SLA_HOURS", 30.0)
    changes = []
    status = rb.get("status")
    if status != "OK":
        changes.append({
            "field": "status",
            "expected": "OK",
            "actual": status,
        })
    if rb.get("log_error"):
        changes.append({
            "field": "log_error",
            "expected": False,
            "actual": True,
        })
    if not rb.get("finished"):
        changes.append({
            "field": "finished",
            "expected": True,
            "actual": rb.get("finished"),
        })
    if not rb.get("dest_exists"):
        changes.append({
            "field": "dest_exists",
            "expected": True,
            "actual": rb.get("dest_exists"),
        })
    if not rb.get("pool_mounted"):
        changes.append({
            "field": "pool_mounted",
            "expected": True,
            "actual": rb.get("pool_mounted"),
        })
    age_s = rb.get("latest_log_age_s")
    age_h = None if age_s is None else float(age_s) / 3600.0
    if age_h is None or age_h > sla_h:
        changes.append({
            "field": "log_age_hours",
            "expected": f"<= {sla_h}",
            "actual": None if age_h is None else round(age_h, 3),
        })
    # Explicitly ignore child-tree emptiness.
    results.append({
        "resource_type": "backup_rsync_filebackups",
        "resource_key": "homelab-rsync-backups",
        "display_name": "Host rsync file-backups",
        "baseline_state": "VERIFIED",
        "outcome": "STATUS-CHANGED" if changes else "MATCH",
        "changes": changes,
    })
    return results


def pbs_native_verify_results(pbs_store_probe):
    if not isinstance(pbs_store_probe, dict) or pbs_store_probe.get("_error"):
        return []
    pv = pbs_store_probe.get("pbs_native_verify")
    changes=[]
    if not isinstance(pv, dict):
        changes.append({"field":"pbs_native_verify","expected":"present","actual":"missing_probe"})
    else:
        if pv.get("status") != "OK": changes.append({"field":"status","expected":"OK","actual":pv.get("status")})
        if pv.get("errors"): changes.append({"field":"probe_errors","expected":"none","actual":"; ".join(map(str,pv.get("errors")[:3]))})
        age=pv.get("age_hours"); sla=_conf_float("BACKUP_PBS_NATIVE_VERIFY_SLA_HOURS", 192.0)
        if age is None or float(age)>sla: changes.append({"field":"age_hours","expected":f"<= {sla}","actual":age})
    return [{"resource_type":"backup_host_verify","resource_key":"pbs-native-weekly","display_name":"PBS native weekly verification","baseline_state":"VERIFIED","outcome":"STATUS-CHANGED" if changes else "MATCH","changes":changes}]


def host_verify_results(pbs_store_probe):
    results = []
    if not isinstance(pbs_store_probe, dict) or pbs_store_probe.get("_error"):
        return results
    hv = pbs_store_probe.get("host_verify")
    if not isinstance(hv, dict):
        results.append({
            "resource_type": "backup_host_verify",
            "resource_key": "homelab-backup-verification",
            "display_name": "Host backup verification",
            "baseline_state": "VERIFIED",
            "outcome": "STATUS-CHANGED",
            "changes": [{"field": "host_verify", "expected": "present", "actual": "missing_probe"}],
        })
        return results

    sla = _conf_float("BACKUP_HOST_VERIFY_SLA_HOURS", 24.0)
    changes = []
    unit_result = hv.get("result")
    if unit_result not in (None, "success"):
        changes.append({
            "field": "unit_result",
            "expected": "success",
            "actual": unit_result,
        })
    exec_status = hv.get("exec_main_status")
    if exec_status not in (None, 0, "0"):
        changes.append({
            "field": "exec_main_status",
            "expected": 0,
            "actual": exec_status,
        })
    status = hv.get("status")
    if status not in (None, "ok"):
        changes.append({
            "field": "status_json",
            "expected": "ok",
            "actual": status,
        })
    failed_count = hv.get("failed_count")
    if failed_count not in (None, 0):
        changes.append({
            "field": "failed_count",
            "expected": 0,
            "actual": failed_count,
        })
    failing = hv.get("failing_checks") or []
    if failing:
        names = ", ".join(
            (c.get("name") if isinstance(c, dict) else str(c)) for c in failing[:8]
        )
        changes.append({
            "field": "failing_checks",
            "expected": "none",
            "actual": names or str(len(failing)),
        })
    age = hv.get("age_hours")
    if age is None or float(age) > sla:
        changes.append({
            "field": "verify_age_hours",
            "expected": f"<= {sla}",
            "actual": None if age is None else round(float(age), 3),
        })
    # Hard errors reading probe (ACL / missing) when we also lack unit success
    errs = hv.get("errors") or []
    if errs and unit_result is None and status is None:
        changes.append({
            "field": "host_verify_probe",
            "expected": "readable",
            "actual": "; ".join(str(e) for e in errs[:3]),
        })

    results.append({
        "resource_type": "backup_host_verify",
        "resource_key": "homelab-backup-verification",
        "display_name": "Host backup verification",
        "baseline_state": "VERIFIED",
        "outcome": "STATUS-CHANGED" if changes else "MATCH",
        "changes": changes,
    })
    return results
# --- STEP7_HOST_VERIFY end ---



def backup_tm_sla_hours():
    import os
    from pathlib import Path
    raw = os.environ.get("BACKUP_TM_SLA_HOURS", "")
    if not raw:
        conf = Path("/etc/rackmarshal/rackmarshal.conf")
        if conf.is_file():
            for line in conf.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("BACKUP_TM_SLA_HOURS="):
                    raw = line.split("=", 1)[1].strip()
                    break
    try:
        return float(raw) if raw else 72.0
    except ValueError:
        return 72.0


def backup_tm_alert_targets():
    """Targets that open incidents when stale. Optional targets are status-only."""
    import os
    from pathlib import Path
    raw = os.environ.get("BACKUP_TM_ALERT_TARGETS", "")
    if not raw:
        conf = Path("/etc/rackmarshal/rackmarshal.conf")
        if conf.is_file():
            for line in conf.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("BACKUP_TM_ALERT_TARGETS="):
                    raw = line.split("=", 1)[1].strip()
                    break
    if not raw:
        raw = ""
    return {p.strip() for p in raw.split(",") if p.strip()}


def timemachine_results(pbs_store_probe):
    """Compare TM share freshness. Optional targets skipped for incidents."""
    results = []
    if not isinstance(pbs_store_probe, dict) or pbs_store_probe.get("_error"):
        return results
    tm = pbs_store_probe.get("timemachine") or {}
    if not isinstance(tm, dict):
        return results
    sla = backup_tm_sla_hours()
    alert = backup_tm_alert_targets()
    for who, entry in sorted(tm.items()):
        if who not in alert:
            continue
        if not isinstance(entry, dict):
            continue
        changes = []
        if not entry.get("exists"):
            changes.append({
                "field": "timemachine_share",
                "expected": "present",
                "actual": "missing",
            })
        else:
            age = entry.get("age_hours")
            if age is None:
                changes.append({
                    "field": "timemachine_age_hours",
                    "expected": f"<= {sla}",
                    "actual": None,
                })
            elif float(age) > float(sla):
                changes.append({
                    "field": "timemachine_age_hours",
                    "expected": f"<= {sla}",
                    "actual": round(float(age), 3),
                })
        results.append({
            "resource_type": "backup_timemachine",
            "resource_key": who,
            "display_name": f"Time Machine ({who})",
            "baseline_state": "VERIFIED",
            "outcome": "STATUS-CHANGED" if changes else "MATCH",
            "changes": changes,
        })
    return results
# --- STEP4_TIMEMACHINE end ---


def backup_exclude_vmids():
    """Comma-separated BACKUP_EXCLUDE_VMIDS from conf/env."""
    import os
    from pathlib import Path
    raw = os.environ.get("BACKUP_EXCLUDE_VMIDS", "")
    if not raw:
        conf = Path("/etc/rackmarshal/rackmarshal.conf")
        if conf.is_file():
            for line in conf.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("BACKUP_EXCLUDE_VMIDS="):
                    raw = line.split("=", 1)[1].strip()
                    break
    out = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            out.add(int(part))
    return out
# --- STEP3_BACKUP_EXCLUDE_VMIDS end ---

# --- STEP3_SECONDARY_WHEN_PRIMARY_STALE begin ---
def secondary_copy_change(pbs_store_probe, guest_type, vmid, max_age_hours):
    """When primary is already stale, note if secondary is missing/stale too.
    Never used alone for lag-only paging.
    """
    if not isinstance(pbs_store_probe, dict) or pbs_store_probe.get("_error"):
        return None
    secondary = pbs_store_probe.get("secondary") or {}
    kind = "vm" if guest_type == "vm" else "ct"
    key = f"{kind}/{int(vmid)}"
    entry = secondary.get(key)
    if entry is None:
        # try alternate kind
        alt = f"{'ct' if kind == 'vm' else 'vm'}/{int(vmid)}"
        entry = secondary.get(alt)
        key = alt if entry is not None else key
    if entry is None:
        return {
            "field": "secondary_copy",
            "expected": "present_when_primary_stale",
            "actual": f"missing:{key}",
        }
    age = entry.get("age_hours")
    if age is None or float(age) > float(max_age_hours):
        return {
            "field": "secondary_copy",
            "expected": f"<= {max_age_hours}",
            "actual": age,
        }
    return None
# --- STEP3_SECONDARY_WHEN_PRIMARY_STALE end ---


def fail(message, rc=1):
    print(
        json.dumps(
            {
                "schema_version": 1,
                "comparator": "backup_baseline",
                "error": message,
            },
            separators=(",", ":"),
            sort_keys=True,
        ),
        file=sys.stderr,
    )
    raise SystemExit(rc)


def parse_iso8601(value):
    if not isinstance(value, str) or not value:
        fail("invalid observation timestamp")

    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"

        result = datetime.fromisoformat(value)

        if result.tzinfo is None:
            fail("observation timestamp lacks timezone")

        return result.astimezone(timezone.utc)

    except ValueError as exc:
        fail(f"invalid observation timestamp: {exc}")


def normalize_bool(value):
    if value is True:
        return 1

    if value is False:
        return 0

    return value


def compare_field(
    changes,
    field,
    expected,
    actual,
):
    if actual != expected:
        changes.append(
            {
                "field": field,
                "expected": expected,
                "actual": actual,
            }
        )


def job_result(
    baseline,
    observed,
):
    job_id = baseline["job_id"]

    if observed is None:
        return {
            "resource_type": "backup_job",
            "resource_key": job_id,
            "display_name": job_id,
            "baseline_state":
                baseline["baseline_state"],
            "outcome": "MISSING",
            "changes": [],
        }

    changes = []

    compare_field(
        changes,
        "enabled",
        baseline["expected_enabled"],
        normalize_bool(observed.get("enabled")),
    )

    compare_field(
        changes,
        "node",
        baseline["expected_node"],
        observed.get("node"),
    )

    compare_field(
        changes,
        "mode",
        baseline["expected_mode"],
        observed.get("mode"),
    )

    compare_field(
        changes,
        "storage",
        baseline["expected_storage"],
        observed.get("storage"),
    )

    compare_field(
        changes,
        "schedule",
        baseline["expected_schedule"],
        observed.get("schedule"),
    )

    compare_field(
        changes,
        "notes_template",
        baseline["expected_notes_template"],
        observed.get("notes_template"),
    )

    prune = observed.get("prune", {})

    if not isinstance(prune, dict):
        prune = {}

    prune_fields = (
        ("keep_daily", "expected_keep_daily"),
        ("keep_last", "expected_keep_last"),
        ("keep_weekly", "expected_keep_weekly"),
        ("keep_monthly", "expected_keep_monthly"),
        ("keep_yearly", "expected_keep_yearly"),
    )

    for observed_field, baseline_field in prune_fields:
        actual = prune.get(observed_field)

        if actual is not None:
            actual = str(actual)

        compare_field(
            changes,
            f"prune.{observed_field}",
            baseline[baseline_field],
            actual,
        )

    return {
        "resource_type": "backup_job",
        "resource_key": job_id,
        "display_name": job_id,
        "baseline_state":
            baseline["baseline_state"],
        "outcome":
            "STATUS-CHANGED" if changes else "MATCH",
        "changes": changes,
    }


def guest_result(
    baseline,
    observed,
    observation_time,
    pbs_store_probe=None,
):
    vmid = baseline["vmid"]
    key = str(vmid)

    if observed is None:
        return {
            "resource_type": "backup_guest",
            "resource_key": key,
            "display_name":
                baseline["display_name"],
            "baseline_state":
                baseline["baseline_state"],
            "outcome": "MISSING",
            "changes": [],
        }

    changes = []

    compare_field(
        changes,
        "name",
        baseline["display_name"],
        observed.get("name"),
    )

    compare_field(
        changes,
        "guest_type",
        baseline["guest_type"],
        observed.get("guest_type"),
    )

    compare_field(
        changes,
        "policy_included",
        baseline[
            "expected_policy_included"
        ],
        normalize_bool(
            observed.get("policy_included")
        ),
    )

    compare_field(
        changes,
        "snapshot_present",
        baseline[
            "expected_snapshot_present"
        ],
        normalize_bool(
            observed.get("snapshot_present")
        ),
    )

    snapshot = observed.get("latest_snapshot")

    if baseline["expected_snapshot_present"] == 1:
        if not isinstance(snapshot, dict):
            changes.append(
                {
                    "field": "latest_snapshot",
                    "expected": "present",
                    "actual": None,
                }
            )

        else:
            compare_field(
                changes,
                "verification_state",
                baseline[
                    "expected_verification_state"
                ],
                snapshot.get(
                    "verification_state"
                ),
            )

            backup_time = snapshot.get(
                "backup_time"
            )

            if (
                isinstance(backup_time, bool)
                or not isinstance(
                    backup_time,
                    (int, float),
                )
            ):
                changes.append(
                    {
                        "field": "backup_time",
                        "expected":
                            "valid Unix timestamp",
                        "actual": backup_time,
                    }
                )

            else:
                snapshot_time = datetime.fromtimestamp(
                    backup_time,
                    tz=timezone.utc,
                )

                age_hours = (
                    observation_time
                    - snapshot_time
                ).total_seconds() / 3600.0

                max_age = baseline[
                    "max_snapshot_age_hours"
                ]

                if age_hours < 0:
                    changes.append(
                        {
                            "field":
                                "snapshot_age_hours",
                            "expected":
                                ">= 0",
                            "actual":
                                round(age_hours, 3),
                        }
                    )

                elif age_hours > max_age:
                    changes.append(
                        {
                            "field":
                                "snapshot_age_hours",
                            "expected":
                                f"<= {max_age}",
                            "actual":
                                round(age_hours, 3),
                        }
                    )
                    # STEP3: document secondary only when primary already stale
                    _sec = secondary_copy_change(
                        pbs_store_probe,
                        baseline.get("guest_type"),
                        baseline.get("vmid"),
                        max_age,
                    )
                    if _sec is not None:
                        changes.append(_sec)

    return {
        "resource_type": "backup_guest",
        "resource_key": key,
        "display_name":
            baseline["display_name"],
        "baseline_state":
            baseline["baseline_state"],
        "outcome":
            "STATUS-CHANGED" if changes else "MATCH",
        "changes": changes,
    }


def scheduled_run_result(
    tasks,
    job_baseline,
):
    #
    # PVE scheduled whole-job vzdump tasks have
    # an empty task id. Manual guest-specific
    # vzdump tasks contain the VMID/CTID.
    #
    scheduled = []

    for task in tasks:
        if not isinstance(task, dict):
            continue

        if task.get("type") != "vzdump":
            continue

        if task.get("id") not in ("", None):
            continue

        scheduled.append(task)

    if not scheduled:
        return {
            "resource_type":
                "backup_scheduled_run",
            "resource_key":
                job_baseline["job_id"],
            "display_name":
                "Nightly PBS backup run",
            "baseline_state":
                job_baseline["baseline_state"],
            "outcome": "MISSING",
            "changes": [],
        }

    def start_time(task):
        value = task.get("starttime")

        if isinstance(value, bool):
            return -1

        if isinstance(value, (int, float)):
            return value

        return -1

    latest = max(
        scheduled,
        key=start_time,
    )

    status = latest.get("status")

    changes = []

    if status != "OK":
        changes.append(
            {
                "field": "status",
                "expected": "OK",
                "actual": status,
            }
        )

    return {
        "resource_type":
            "backup_scheduled_run",
        "resource_key":
            job_baseline["job_id"],
        "display_name":
            "Nightly PBS backup run",
        "baseline_state":
            job_baseline["baseline_state"],
        "outcome":
            "STATUS-CHANGED"
            if changes
            else "MATCH",
        "changes": changes,
        "latest_task": {
            "upid": latest.get("upid"),
            "starttime":
                latest.get("starttime"),
            "endtime":
                latest.get("endtime"),
            "status": status,
        },
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--observation-id",
        type=int,
        required=True,
    )

    parser.add_argument(
        "--database",
        type=Path,
        default=DB_PATH,
    )

    args = parser.parse_args()

    if args.observation_id < 1:
        fail(
            "observation id must be positive"
        )

    try:
        connection = sqlite3.connect(
            f"file:{args.database}?mode=ro",
            uri=True,
        )

        connection.row_factory = sqlite3.Row

    except sqlite3.Error as exc:
        fail(
            f"unable to open database "
            f"read-only: {exc}"
        )

    try:
        observation = connection.execute(
            """
            SELECT
                id,
                collector,
                observed_at,
                payload_json
            FROM observations
            WHERE id = ?
            """,
            (args.observation_id,),
        ).fetchone()

        if observation is None:
            fail(
                f"observation "
                f"{args.observation_id} "
                "not found"
            )

        if observation["collector"] != (
            "backup_domain"
        ):
            fail(
                "observation is not "
                "backup_domain"
            )

        job_rows = connection.execute(
            """
            SELECT *
            FROM backup_job_baseline
            ORDER BY job_id
            """
        ).fetchall()

        guest_rows = connection.execute(
            """
            SELECT *
            FROM backup_guest_baseline
            ORDER BY vmid
            """
        ).fetchall()

    except sqlite3.Error as exc:
        fail(
            f"database read failed: {exc}"
        )

    finally:
        connection.close()

    if len(job_rows) != 1:
        fail(
            "exactly one backup job baseline "
            "is required"
        )

    job_baseline = dict(job_rows[0])

    if (
        job_baseline["baseline_state"]
        not in VALID_BASELINE_STATES
    ):
        fail("invalid job baseline state")

    for row in guest_rows:
        if (
            row["baseline_state"]
            not in VALID_BASELINE_STATES
        ):
            fail(
                "invalid guest baseline state"
            )

    try:
        payload = json.loads(
            observation["payload_json"]
        )
    except json.JSONDecodeError as exc:
        fail(
            "stored backup observation "
            f"contains invalid JSON: {exc}"
        )

    observation_time = parse_iso8601(
        observation["observed_at"]
    )

    pbs_store_probe = payload.get("pbs_store_probe")

    jobs = payload.get("backup_jobs")

    resources = payload.get("resources")

    tasks = payload.get(
        "recent_vzdump_tasks"
    )

    if not isinstance(jobs, list):
        fail(
            "stored observation has "
            "invalid backup_jobs"
        )

    if not isinstance(resources, list):
        fail(
            "stored observation has "
            "invalid resources"
        )

    if not isinstance(tasks, list):
        fail(
            "stored observation has "
            "invalid recent_vzdump_tasks"
        )

    observed_jobs = {}

    for job in jobs:
        if not isinstance(job, dict):
            fail("invalid observed backup job")

        job_id = job.get("id")

        if (
            not isinstance(job_id, str)
            or not job_id
        ):
            fail(
                "observed backup job "
                "missing id"
            )

        if job_id in observed_jobs:
            fail(
                f"duplicate observed job "
                f"{job_id}"
            )

        observed_jobs[job_id] = job

    observed_guests = {}

    for resource in resources:
        if not isinstance(resource, dict):
            fail(
                "invalid observed "
                "backup resource"
            )

        vmid = resource.get("vmid")

        if (
            isinstance(vmid, bool)
            or not isinstance(vmid, int)
            or vmid < 1
        ):
            fail(
                "observed backup resource "
                "has invalid vmid"
            )

        if vmid in observed_guests:
            fail(
                f"duplicate observed "
                f"backup guest {vmid}"
            )

        observed_guests[vmid] = resource

    results = []

    #
    # Expected production job.
    #
    results.append(
        job_result(
            job_baseline,
            observed_jobs.get(
                job_baseline["job_id"]
            ),
        )
    )

    #
    # Unexpected backup jobs.
    #
    for job_id in sorted(
        set(observed_jobs)
        - {job_baseline["job_id"]}
    ):
        results.append(
            {
                "resource_type":
                    "backup_job",
                "resource_key":
                    job_id,
                "display_name":
                    job_id,
                "baseline_state":
                    None,
                "outcome": "NEW",
                "changes": [],
            }
        )

    #
    # Expected protected guests.
    #
    baseline_guest_ids = set()

    for row in guest_rows:
        baseline = dict(row)

        vmid = baseline["vmid"]

        baseline_guest_ids.add(vmid)

        results.append(
            guest_result(
                baseline,
                observed_guests.get(vmid),
                observation_time,
                pbs_store_probe=pbs_store_probe,
            )
        )

    #
    # Unexpected protected guests.
    #
    exclude_vmids = backup_exclude_vmids()

    for vmid in sorted(
        set(observed_guests)
        - baseline_guest_ids
    ):
        if vmid in exclude_vmids:
            continue
        resource = observed_guests[vmid]

        results.append(
            {
                "resource_type":
                    "backup_guest",
                "resource_key":
                    str(vmid),
                "display_name":
                    resource.get(
                        "name",
                        str(vmid),
                    ),
                "baseline_state":
                    None,
                "outcome": "NEW",
                "changes": [],
            }
        )

    #
    # Scheduled whole-job health is independent
    # from individual/manual recovery points.
    #
    results.append(
        scheduled_run_result(
            tasks,
            job_baseline,
        )
    )

    # --- STEP4_TIMEMACHINE results ---
    results.extend(timemachine_results(pbs_store_probe))
    # --- STEP4_TIMEMACHINE results end ---

    # --- STEP56_PHONES_MESSAGES results ---
    results.extend(phone_results(pbs_store_probe))
    results.extend(messages_results(pbs_store_probe))
    # --- STEP56_PHONES_MESSAGES results end ---

    # --- STEP7_HOST_VERIFY results ---
    results.extend(host_verify_results(pbs_store_probe))
    results.extend(pbs_native_verify_results(pbs_store_probe))
    results.extend(rsync_filebackups_results(pbs_store_probe))
    # --- STEP7_HOST_VERIFY results end ---


    counts = {
        "MATCH": 0,
        "STATUS-CHANGED": 0,
        "MISSING": 0,
        "NEW": 0,
    }

    for result in results:
        outcome = result["outcome"]

        if outcome not in counts:
            fail(
                f"unexpected outcome: "
                f"{outcome}"
            )

        counts[outcome] += 1

    output = {
        "schema_version": 1,
        "comparator": "backup_baseline",
        "observation_id":
            observation["id"],
        "observed_at":
            observation["observed_at"],
        "result_count": len(results),
        "counts": counts,
        "results": results,
    }

    print(
        json.dumps(
            output,
            separators=(",", ":"),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
