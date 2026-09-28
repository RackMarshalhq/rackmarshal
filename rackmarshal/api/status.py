#!/usr/bin/env python3

import json
import subprocess
import sqlite3
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from rackmarshal.core.config import (
    domains_dir,
    load_config,
    require,
    require_int,
    sqlite_ro_uri,
    state_db,
)


CONFIG = load_config()

DB_URI = sqlite_ro_uri(state_db(CONFIG))

LISTEN_ADDRESS = require(
    CONFIG,
    "STATUS_API_LISTEN_ADDRESS",
)

LISTEN_PORT = require_int(
    CONFIG,
    "STATUS_API_LISTEN_PORT",
)



# --- STEP3_PBS_STORE_STATUS begin ---
def pbs_store_summary(payload):
    """Build /status BACKUP.pbs_store from observation payload dict."""
    if not isinstance(payload, dict):
        return None
    probe = payload.get("pbs_store_probe")
    if not isinstance(probe, dict):
        return None
    if probe.get("_error"):
        return {
            "policy": "alert_only_when_primary_stale",
            "error": probe.get("_error"),
        }
    primary = probe.get("primary") or {}
    secondary = probe.get("secondary") or {}
    ages = [
        float(v["age_hours"])
        for v in secondary.values()
        if isinstance(v, dict) and v.get("age_hours") is not None
    ]
    tm = probe.get("timemachine") or {}
    tm_out = {}
    for who, entry in tm.items() if isinstance(tm, dict) else []:
        if not isinstance(entry, dict):
            continue
        tm_out[who] = {
            "age_hours": entry.get("age_hours"),
            "used": entry.get("used"),
            "exists": entry.get("exists"),
        }
    return {
        "policy": "alert_only_when_primary_stale",
        "primary_count": len(primary),
        "secondary_count": len(secondary),
        "missing_on_secondary": list(probe.get("missing_on_secondary") or []),
        "max_secondary_age_hours": max(ages) if ages else None,
        "observed_at": probe.get("observed_at"),
        "timemachine": tm_out,
        "phones": {
            who: {
                "age_hours": (entry or {}).get("age_hours"),
                "exists": (entry or {}).get("exists"),
            }
            for who, entry in (probe.get("phones") or {}).items()
            if isinstance(entry, dict) or entry is None
        },
        "messages": probe.get("messages") if isinstance(probe.get("messages"), dict) else {},
        "host_verify": {
            "result": (probe.get("host_verify") or {}).get("result") if isinstance(probe.get("host_verify"), dict) else None,
            "status": (probe.get("host_verify") or {}).get("status") if isinstance(probe.get("host_verify"), dict) else None,
            "failed_count": (probe.get("host_verify") or {}).get("failed_count") if isinstance(probe.get("host_verify"), dict) else None,
            "checked_at": (probe.get("host_verify") or {}).get("checked_at") if isinstance(probe.get("host_verify"), dict) else None,
            "age_hours": (probe.get("host_verify") or {}).get("age_hours") if isinstance(probe.get("host_verify"), dict) else None,
            "failing_checks": (probe.get("host_verify") or {}).get("failing_checks") if isinstance(probe.get("host_verify"), dict) else [],
            "diagnosis": (probe.get("host_verify") or {}).get("diagnosis") if isinstance(probe.get("host_verify"), dict) else None,
        },
        "rsync_filebackups": {
            "status": rb.get("status") if False else ((probe.get("rsync_filebackups") or {}).get("status") if isinstance(probe.get("rsync_filebackups"), dict) else None),
            "reason": (probe.get("rsync_filebackups") or {}).get("reason") if isinstance(probe.get("rsync_filebackups"), dict) else None,
            "latest_log_age_s": (probe.get("rsync_filebackups") or {}).get("latest_log_age_s") if isinstance(probe.get("rsync_filebackups"), dict) else None,
            "finished": (probe.get("rsync_filebackups") or {}).get("finished") if isinstance(probe.get("rsync_filebackups"), dict) else None,
            "dest_exists": (probe.get("rsync_filebackups") or {}).get("dest_exists") if isinstance(probe.get("rsync_filebackups"), dict) else None,
            "alert_on_empty_children": False,
        },
    }


def load_backup_payload_json(conn):
    row = conn.execute(
        """
        SELECT payload_json
        FROM observations
        WHERE collector = 'backup_domain'
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    if not row:
        return None
    raw = row["payload_json"] if hasattr(row, "keys") else row[0]
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None
# --- STEP3_PBS_STORE_STATUS end ---


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def connect_db():
    conn = sqlite3.connect(
        DB_URI,
        uri=True,
        timeout=5.0,
    )
    conn.row_factory = sqlite3.Row
    return conn


def latest_generic_observation(conn, collector):
    row = conn.execute(
        """
        SELECT
            id,
            observed_at,
            source,
            schema_version,
            tls_verified,
            resource_count
        FROM observations
        WHERE collector = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (collector,),
    ).fetchone()

    return dict(row) if row else None


def latest_zfs_observation(conn):
    columns = {
        row["name"]
        for row in conn.execute(
            "PRAGMA table_info(zfs_observations)"
        ).fetchall()
    }

    if "id" not in columns:
        return None

    wanted = ["id"]

    for name in (
        "observed_at",
        "recorded_at",
        "source",
        "schema_version",
        "resource_count",
    ):
        if name in columns:
            wanted.append(name)

    sql = (
        "SELECT "
        + ", ".join(wanted)
        + " FROM zfs_observations ORDER BY id DESC LIMIT 1"
    )

    row = conn.execute(sql).fetchone()
    return dict(row) if row else None



def latest_hardware_observation(conn):
    """Latest HARDWARE sample batch from hardware_observations."""
    row = conn.execute(
        """
        SELECT
            MAX(id) AS id,
            MAX(observed_at) AS observed_at,
            COUNT(*) AS device_count,
            SUM(CASE WHEN status = 'OK' THEN 1 ELSE 0 END) AS ok_count,
            SUM(CASE WHEN status = 'HOT' THEN 1 ELSE 0 END) AS hot_count,
            SUM(CASE WHEN status = 'URGENT' THEN 1 ELSE 0 END) AS urgent_count,
            SUM(CASE WHEN status = 'MISSING' THEN 1 ELSE 0 END) AS missing_count
        FROM hardware_observations
        WHERE observed_at = (
            SELECT MAX(observed_at) FROM hardware_observations
        )
        """
    ).fetchone()

    if row is None or row["observed_at"] is None:
        return None

    return {
        "id": row["id"],
        "observed_at": row["observed_at"],
        "source": "hardware_observations",
        "collector": "hardware_temperature",
        "device_count": int(row["device_count"] or 0),
        "resource_count": int(row["device_count"] or 0),
        "statuses": {
            "OK": int(row["ok_count"] or 0),
            "HOT": int(row["hot_count"] or 0),
            "URGENT": int(row["urgent_count"] or 0),
            "MISSING": int(row["missing_count"] or 0),
        },
    }


def hardware_incidents(conn):
    """Open HARDWARE incidents from hardware_incidents (ledger parity Step G)."""
    rows = conn.execute(
        """
        SELECT
            id,
            serial,
            model,
            role,
            incident_type,
            severity,
            incident_state,
            opened_at,
            last_abnormal_at,
            occurrence_count,
            note
        FROM hardware_incidents
        WHERE incident_state = 'OPEN'
        ORDER BY opened_at
        """
    ).fetchall()

    incidents = []
    for row in rows:
        incidents.append(
            {
                "id": row["id"],
                "serial": row["serial"],
                "model": row["model"],
                "role": row["role"],
                "severity": row["severity"],
                "opened_at": row["opened_at"],
                "last_abnormal_at": row["last_abnormal_at"],
                "occurrence_count": row["occurrence_count"],
                "note": row["note"],
                "incident_type": row["incident_type"],
                "display_name": (
                    f"{row['role']} ({row['serial']})"
                ),
            }
        )
    return incidents



def latest_mount_observation(conn):
    """Latest MOUNT catalog observation from mount_observations."""
    row = conn.execute(
        """
        SELECT
            id,
            observed_at,
            source,
            schema_version,
            catalog_version,
            checked_count,
            ok_count,
            problem_count
        FROM mount_observations
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        return None
    return {
        "id": row["id"],
        "observed_at": row["observed_at"],
        "source": row["source"],
        "collector": "mount_catalog",
        "schema_version": row["schema_version"],
        "catalog_version": row["catalog_version"],
        "checked_count": int(row["checked_count"] or 0),
        "ok_count": int(row["ok_count"] or 0),
        "problem_count": int(row["problem_count"] or 0),
        "resource_count": int(row["checked_count"] or 0),
    }


def mount_incidents(conn):
    """Open mount incidents from mount_incidents."""
    rows = conn.execute(
        """
        SELECT
            id,
            mount_id,
            guest_kind,
            guest_id,
            mountpoint,
            display_name,
            incident_type,
            severity,
            incident_state,
            opened_at,
            last_abnormal_at,
            occurrence_count,
            note
        FROM mount_incidents
        WHERE incident_state = 'OPEN'
        ORDER BY opened_at
        """
    ).fetchall()
    return [dict(row) for row in rows]


def pve_incidents(conn):

    rows = conn.execute(
        """
        SELECT
            id,
            resource_type,
            resource_key,
            COALESCE(display_name, resource_key) AS display_name,
            incident_type,
            incident_state,
            baseline_state,
            abnormal_status,
            opened_at,
            last_abnormal_at,
            occurrence_count,
            note
        FROM resource_incidents
        WHERE incident_state = 'OPEN'
        ORDER BY opened_at
        """
    ).fetchall()

    return [dict(row) for row in rows]


def zfs_incidents(conn):
    rows = conn.execute(
        """
        SELECT
            id,
            resource_type,
            resource_key,
            pool_name,
            vdev_name,
            incident_type,
            incident_state,
            baseline_state,
            opened_at,
            last_abnormal_at,
            occurrence_count,
            note
        FROM zfs_incidents
        WHERE incident_state = 'OPEN'
        ORDER BY opened_at
        """
    ).fetchall()

    result = []

    for row in rows:
        item = dict(row)

        if item.get("vdev_name"):
            item["display_name"] = (
                f"{item['pool_name']} / {item['vdev_name']}"
            )
        else:
            item["display_name"] = item["pool_name"]

        result.append(item)

    return result


def backup_incidents(conn):
    rows = conn.execute(
        """
        SELECT
            id,
            resource_type,
            resource_key,
            display_name,
            incident_type,
            incident_state,
            baseline_state,
            opened_at,
            last_abnormal_at,
            occurrence_count,
            note
        FROM backup_incidents
        WHERE incident_state = 'OPEN'
        ORDER BY opened_at
        """
    ).fetchall()

    return [dict(row) for row in rows]


def ha_incidents(conn):
    rows = conn.execute(
        """
        SELECT
            id,
            resource_type,
            resource_key,
            display_name,
            incident_type,
            incident_state,
            baseline_state,
            opened_at,
            last_abnormal_at,
            occurrence_count,
            note
        FROM ha_incidents
        WHERE incident_state = 'OPEN'
        ORDER BY opened_at
        """
    ).fetchall()

    return [dict(row) for row in rows]



# Domains currently emitted by /status (MOUNT added M6 2026-09-17).
STATUS_DOMAINS = ("PVE", "ZFS", "BACKUP", "HA", "HARDWARE", "MOUNT")

# plugin.toml id → /status domain key
_PLUGIN_DOMAIN_KEYS = {
    "pve": "PVE",
    "zfs": "ZFS",
    "backup": "BACKUP",
    "ha": "HA",
    "hardware": "HARDWARE",
    "mount": "MOUNT",
}


def parse_observed_at(value):
    if not value:
        return None
    text_value = str(value).strip()
    if text_value.endswith("Z"):
        text_value = text_value[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text_value)
    except ValueError:
        return None


def load_stale_after_seconds():
    """Read stale_after_seconds from domains/*/plugin.toml (defaults 900)."""
    thresholds = {domain: 900 for domain in STATUS_DOMAINS}
    root = domains_dir(CONFIG)
    try:
        import tomllib
    except ImportError:  # pragma: no cover
        import tomli as tomllib  # type: ignore

    if not root.is_dir():
        return thresholds

    for path in sorted(root.glob("*/plugin.toml")):
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        plugin_id = str(data.get("id") or path.parent.name).lower()
        domain = _PLUGIN_DOMAIN_KEYS.get(plugin_id)
        if not domain:
            continue
        status = data.get("status") or {}
        raw = status.get("stale_after_seconds")
        if raw is None:
            continue
        try:
            thresholds[domain] = int(raw)
        except (TypeError, ValueError):
            continue
    return thresholds


def build_freshness(observations, now=None):
    """Phase 3 Step 4.2: read-only observation freshness for self_watch."""
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    thresholds = load_stale_after_seconds()
    freshness = {}

    for domain in STATUS_DOMAINS:
        obs = observations.get(domain)
        stale_after = thresholds.get(domain, 900)
        if not obs or not obs.get("observed_at"):
            freshness[domain] = {
                "age_seconds": None,
                "stale_after_seconds": stale_after,
                "state": "MISSING",
                "observed_at": None,
            }
            continue

        observed = parse_observed_at(obs.get("observed_at"))
        if observed is None:
            freshness[domain] = {
                "age_seconds": None,
                "stale_after_seconds": stale_after,
                "state": "MISSING",
                "observed_at": obs.get("observed_at"),
            }
            continue

        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=timezone.utc)

        age = max(0, int((now - observed).total_seconds()))
        state = "STALE" if age > stale_after else "OK"
        freshness[domain] = {
            "age_seconds": age,
            "stale_after_seconds": stale_after,
            "state": state,
            "observed_at": obs.get("observed_at"),
        }

    return freshness


NOTIFY_PENDING_MAX_AGE_SECONDS = 900

SELF_WATCH_UNITS = (
    "rackmarshal-status.service",
    "rackmarshal-domain@pve.timer",
    "rackmarshal-domain@pve.service",
    "rackmarshal-domain@zfs.timer",
    "rackmarshal-domain@zfs.service",
    "rackmarshal-domain@ha.timer",
    "rackmarshal-domain@ha.service",
    "rackmarshal-domain@backup.timer",
    "rackmarshal-domain@backup.service",
    "rackmarshal-domain@hardware.timer",
    "rackmarshal-domain@hardware.service",
    "rackmarshal-domain@mount.timer",
    "rackmarshal-domain@mount.service",
    "rackmarshal-self-watch.timer",
)


def unit_active_state(unit_name):
    """Return systemd ActiveState for a RackMarshal unit (read-only)."""
    try:
        result = subprocess.run(
            [
                "systemctl",
                "show",
                unit_name,
                "-p",
                "ActiveState",
                "--value",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"

    value = (result.stdout or "").strip()
    if result.returncode != 0 or not value:
        return "unknown"
    return value


def build_self_watch_units():
    return {name: unit_active_state(name) for name in SELF_WATCH_UNITS}


def build_self_watch_notifications(conn, now=None):
    """Counts from incident_notifications (PENDING/FAILED backlog)."""
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    pending = conn.execute(
        """
        SELECT COUNT(*)
        FROM incident_notifications
        WHERE delivery_state = 'PENDING'
        """
    ).fetchone()[0]

    failed = conn.execute(
        """
        SELECT COUNT(*)
        FROM incident_notifications
        WHERE delivery_state = 'FAILED'
        """
    ).fetchone()[0]

    pending_rows = conn.execute(
        """
        SELECT created_at
        FROM incident_notifications
        WHERE delivery_state = 'PENDING'
        """
    ).fetchall()

    pending_older = 0
    for row in pending_rows:
        created_raw = row[0]
        created = parse_observed_at(created_raw)
        if created is None:
            continue
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age = (now - created).total_seconds()
        if age > NOTIFY_PENDING_MAX_AGE_SECONDS:
            pending_older += 1

    return {
        "pending": int(pending),
        "failed": int(failed),
        "pending_older_than_seconds": int(pending_older),
        "pending_max_age_seconds": NOTIFY_PENDING_MAX_AGE_SECONDS,
    }


def self_watch_status_from_parts(freshness, units, notifications):
    """Combine freshness + units + notify backlog into self_watch.status."""
    states = {item["state"] for item in freshness.values()}
    if "MISSING" in states or "STALE" in states:
        return "DEGRADED"

    status_api = units.get("rackmarshal-status.service")
    if status_api not in (None, "active"):
        return "CRITICAL"

    for name, state in units.items():
        if state == "failed":
            return "CRITICAL"
        if state == "unknown":
            return "DEGRADED"
        if name.endswith(".timer") and state != "active":
            return "DEGRADED"

    if notifications.get("failed", 0) > 0:
        return "DEGRADED"
    if notifications.get("pending_older_than_seconds", 0) > 0:
        return "DEGRADED"

    return "OK"



def latest_ai_explanations(conn):
    """Map (domain, incident_id) → redacted AI explanation from OPENED notifications.

    Local-AI 5.6: explain-only; never authoritative. Only mode=AI successes.
    """
    rows = conn.execute(
        """
        SELECT
            id,
            source_domain,
            incident_id,
            explanation_json
        FROM incident_notifications
        WHERE notification_type = 'OPENED'
          AND explanation_json IS NOT NULL
          AND length(explanation_json) > 2
        ORDER BY id DESC
        """
    ).fetchall()

    out = {}
    for row in rows:
        domain = row["source_domain"]
        try:
            iid = int(row["incident_id"])
        except (TypeError, ValueError):
            continue
        key = (domain, iid)
        if key in out:
            continue  # newest first
        try:
            payload = json.loads(row["explanation_json"])
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        if payload.get("mode") != "AI":
            continue
        if not payload.get("explainer_succeeded"):
            continue
        envelope = payload.get("explanation")
        if not isinstance(envelope, dict):
            continue
        advisory = envelope.get("explanation")
        if not isinstance(advisory, dict):
            advisory = envelope
        summary = advisory.get("summary")
        impact = advisory.get("impact")
        causes = advisory.get("possible_causes")
        checks = advisory.get("recommended_checks")
        confidence = advisory.get("confidence")
        model = envelope.get("model") or advisory.get("model")
        if not isinstance(summary, str) or not summary.strip():
            continue
        out[key] = {
            "summary": summary.strip(),
            "impact": impact.strip() if isinstance(impact, str) else None,
            "possible_causes": causes if isinstance(causes, list) else [],
            "recommended_checks": checks if isinstance(checks, list) else [],
            "confidence": confidence if isinstance(confidence, str) else None,
            "model": model if isinstance(model, str) else None,
            "notification_id": int(row["id"]),
        }
    return out


def build_status():

    backup_payload = None
    with connect_db() as conn:
        incidents = {
            "PVE": pve_incidents(conn),
            "ZFS": zfs_incidents(conn),
            "BACKUP": backup_incidents(conn),
            "HA": ha_incidents(conn),
            "HARDWARE": hardware_incidents(conn),
            "MOUNT": mount_incidents(conn),
        }

        observations = {
            "PVE": latest_generic_observation(
                conn,
                "pve_cluster_resources",
            ),
            "ZFS": latest_zfs_observation(conn),
            "BACKUP": latest_generic_observation(
                conn,
                "backup_domain",
            ),
            "HA": latest_generic_observation(
                conn,
                "home_assistant",
            ),
            "HARDWARE": latest_hardware_observation(conn),
            "MOUNT": latest_mount_observation(conn),
        }

        backup_payload = load_backup_payload_json(conn)

        # Phase 3 Step 4.3: notify backlog snapshot while DB is open.
        notifications = build_self_watch_notifications(conn)

        # Phase 3 Step 4.4f: open SELF incident count.
        open_self_incidents = conn.execute(
            """
            SELECT COUNT(*)
            FROM self_incidents
            WHERE incident_state = 'OPEN'
            """
        ).fetchone()[0]

        # Phase 3 Step 4B2F: read-only cycle execution health.
        cycle_health_rows = conn.execute(
            """
            SELECT
                unit_name,
                health_state,
                last_result_at,
                last_success_at,
                last_failure_at,
                failure_count,
                last_exit_code,
                last_exit_status
            FROM cycle_health
            ORDER BY unit_name
            """
        ).fetchall()

        cycle_health = {
            row["unit_name"]: {
                "health_state": row["health_state"],
                "last_result_at": row["last_result_at"],
                "last_success_at": row["last_success_at"],
                "last_failure_at": row["last_failure_at"],
                "failure_count": row["failure_count"],
                "last_exit_code": row["last_exit_code"],
                "last_exit_status": row["last_exit_status"],
            }
            for row in cycle_health_rows
            if str(row["unit_name"]).startswith("rackmarshal-")
        }

        open_mount_incidents = conn.execute(
            """
            SELECT COUNT(*)
            FROM mount_incidents
            WHERE incident_state = 'OPEN'
            """
        ).fetchone()[0]

    domains = {}

    for domain in STATUS_DOMAINS:
        open_count = len(incidents[domain])

        domains[domain] = {
            "status": "OK" if open_count == 0 else "PROBLEM",
            "open_incidents": open_count,
            "last_observation": observations[domain],
        }

    # --- STEP3_PBS_STORE_STATUS attach ---
    try:
        _sum = pbs_store_summary(backup_payload) if backup_payload else None
        if _sum is not None:
            domains["BACKUP"]["pbs_store"] = _sum
            if isinstance(_sum.get("timemachine"), dict):
                domains["BACKUP"]["timemachine"] = _sum["timemachine"]
            if isinstance(_sum.get("phones"), dict):
                domains["BACKUP"]["phones"] = _sum["phones"]
            if isinstance(_sum.get("messages"), dict):
                domains["BACKUP"]["messages"] = _sum["messages"]
            if isinstance(_sum.get("host_verify"), dict):
                domains["BACKUP"]["host_verify"] = _sum["host_verify"]
            if isinstance(_sum.get("rsync_filebackups"), dict):
                domains["BACKUP"]["rsync_filebackups"] = _sum["rsync_filebackups"]
    except Exception:
        pass
    # --- STEP3_PBS_STORE_STATUS attach end ---

    ai_by_incident = latest_ai_explanations(conn)

    active_incidents = []

    for domain in STATUS_DOMAINS:
        for incident in incidents[domain]:
            item = {
                "domain": domain,
                **incident,
            }
            try:
                iid = int(incident.get("id"))
            except (TypeError, ValueError):
                iid = None
            expl = ai_by_incident.get((domain, iid)) if iid is not None else None
            if expl is not None:
                item["ai_explanation"] = expl
            active_incidents.append(item)

    total_open = len(active_incidents)

    # Phase 3 Step 4.3: freshness + units + notify backlog (still additive).
    # overall_status remains incident-based (unchanged); coupling later.
    freshness = build_freshness(observations)
    units = build_self_watch_units()
    self_watch = {
        "status": self_watch_status_from_parts(
            freshness,
            units,
            notifications,
        ),
        "freshness": freshness,
        "units": units,
        "notifications": notifications,
        "cycle_health": cycle_health,
        "open_self_incidents": int(open_self_incidents),
        "open_mount_incidents": int(open_mount_incidents),
    }

    return {
        "schema_version": 2,
        "generated_at": utc_now(),
        "overall_status": (
            "OK" if total_open == 0 else "PROBLEM"
        ),
        "open_incident_count": total_open,
        "open_mount_incidents": int(open_mount_incidents),
        "domains": domains,
        "active_incidents": active_incidents,
        "self_watch": self_watch,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "RackMarshalStatus/1"

    def send_json(self, status_code, payload):
        body = json.dumps(
            payload,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")

        self.send_response(status_code)
        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8",
        )
        self.send_header(
            "Content-Length",
            str(len(body)),
        )
        self.send_header(
            "Cache-Control",
            "no-store",
        )
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/health":
            self.send_json(
                200,
                {
                    "status": "OK",
                    "generated_at": utc_now(),
                },
            )
            return

        if path != "/status":
            self.send_json(
                404,
                {
                    "status": "NOT_FOUND",
                },
            )
            return

        try:
            payload = build_status()
            self.send_json(200, payload)
        except Exception as exc:
            self.send_json(
                500,
                {
                    "status": "ERROR",
                    "generated_at": utc_now(),
                    "error": str(exc),
                },
            )

    def log_message(self, fmt, *args):
        print(
            "%s - %s"
            % (
                self.address_string(),
                fmt % args,
            ),
            flush=True,
        )


def main():
    server = ThreadingHTTPServer(
        (LISTEN_ADDRESS, LISTEN_PORT),
        Handler,
    )

    print(
        f"RackMarshal status API listening on "
        f"{LISTEN_ADDRESS}:{LISTEN_PORT}",
        flush=True,
    )

    server.serve_forever()


if __name__ == "__main__":
    main()
