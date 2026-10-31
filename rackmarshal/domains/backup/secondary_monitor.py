"""Optional second Proxmox Backup Server datastore check for the BACKUP domain.

Off unless ``BACKUP_SECONDARY_STORE`` names a datastore. When on, the collector
reads that datastore's status and snapshot list (read-only, the same PBS token
and verified TLS as the primary collection) and the comparator reports two
results: coverage (copy present, fresh, not lagging, verified) and capacity.

A failure here never stops primary collection: the collector records an error
marker and the comparator turns it into a STATUS-CHANGED result.
"""
import os
import re
import time
from pathlib import Path

CONF_FILE = "/etc/rackmarshal/rackmarshal.conf"

DEFAULTS = {
    "BACKUP_SECONDARY_SNAPSHOT_SLA_HOURS": 36.0,
    "BACKUP_SECONDARY_SOURCE_LAG_GRACE_HOURS": 8.0,
    "BACKUP_SECONDARY_VERIFY_SLA_HOURS": 36.0,
    "BACKUP_SECONDARY_MIN_AVAILABLE_GIB": 64.0,
    "BACKUP_SECONDARY_MAX_UTILIZATION_PERCENT": 90.0,
}
MAX_SNAPSHOT_ROWS = 20000


def _conf(key):
    value = os.environ.get(key, "")
    if value:
        return value
    conf = Path(CONF_FILE)
    if conf.is_file():
        for line in conf.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip()
    return ""


def configured_store(get_conf=_conf):
    """Datastore name, or '' when the check is off."""
    store = get_conf("BACKUP_SECONDARY_STORE").strip()
    if store and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", store):
        return ""
    return store


def load_settings(get_conf=_conf):
    """Thresholds from configuration; a bad or non-positive value uses the default."""
    settings = {}
    for key, default in DEFAULTS.items():
        try:
            value = float(get_conf(key))
        except ValueError:
            value = default
        settings[key] = value if value > 0 else default
    settings["BACKUP_SECONDARY_MAX_UTILIZATION_PERCENT"] = min(
        settings["BACKUP_SECONDARY_MAX_UTILIZATION_PERCENT"], 100.0
    )
    return settings


def _is_count(value):
    return type(value) is int and value >= 0


def _verification_time(upid, store):
    """Epoch of a verify task that ran against this datastore, else None."""
    if not isinstance(upid, str):
        return None
    parts = upid.split(":")
    if (
        len(parts) != 10
        or parts[0] != "UPID"
        or parts[6] not in ("verify", "verify_snapshot", "verificationjob")
    ):
        return None
    identity = re.sub(
        r"\\x([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), parts[7]
    )
    if not identity.startswith(store + ":"):
        return None
    try:
        return int(parts[5], 16)
    except ValueError:
        return None


def collect_secondary(pbs_get, config, store, now=None):
    """Read-only metadata packet for the observation. Never raises."""
    packet = {
        "schema": 1,
        "store": store,
        "collected_at": int(time.time() if now is None else now),
        "tls_verified": True,
    }
    try:
        base = "/api2/json/admin/datastore/" + store
        status = pbs_get(config, base + "/status")
        rows = pbs_get(config, base + "/snapshots")
        if (
            not isinstance(status, dict)
            or not isinstance(rows, list)
            or len(rows) > MAX_SNAPSHOT_ROWS
        ):
            raise ValueError("invalid metadata")
        capacity = {key: status.get(key) for key in ("total", "used", "avail")}
        if not all(_is_count(v) for v in capacity.values()) or capacity["total"] == 0:
            raise ValueError("invalid capacity")
        latest, seen = {}, set()
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("invalid snapshot")
            kind = row.get("backup-type")
            ident = row.get("backup-id")
            stamp = row.get("backup-time")
            if kind not in ("ct", "vm"):
                continue
            if not isinstance(ident, str) or not ident.isdigit() or not _is_count(stamp) or stamp == 0:
                raise ValueError("invalid snapshot identity")
            key = kind + "/" + ident
            if (key, stamp) in seen:
                raise ValueError("duplicate snapshot")
            seen.add((key, stamp))
            verification = row.get("verification")
            if not isinstance(verification, dict):
                verification = {}
            if key not in latest or latest[key]["backup_time"] < stamp:
                latest[key] = {
                    "backup_time": stamp,
                    "verification_state": verification.get("state"),
                    "verification_upid": verification.get("upid"),
                }
        packet.update(capacity=capacity, snapshot_count=len(rows), latest=latest)
    except Exception as exc:  # noqa: BLE001 - isolated; never log tokens or raw text
        packet.update(
            error="secondary_metadata_collection_failed",
            error_kind=type(exc).__name__,
        )
        match = re.search(r"HTTP error ([0-9]{3})", str(exc))
        if match:
            packet["http_status"] = int(match.group(1))
    return packet


def _change(field, expected, actual):
    return {"field": field, "expected": expected, "actual": actual}


def _result(key, title, changes):
    return {
        "resource_type": "backup_host_verify",
        "resource_key": key,
        "display_name": title,
        "baseline_state": "EXPECTED",
        "outcome": "STATUS-CHANGED" if changes else "MATCH",
        "changes": changes,
    }


def secondary_results(packet, resources, observed_epoch, store, settings=None):
    """Two comparison results, or [] when the check is off (store is '')."""
    if not store:
        return []
    cfg = settings or load_settings()
    snapshot_sla = cfg["BACKUP_SECONDARY_SNAPSHOT_SLA_HOURS"] * 3600
    lag_grace = cfg["BACKUP_SECONDARY_SOURCE_LAG_GRACE_HOURS"] * 3600
    verify_sla = cfg["BACKUP_SECONDARY_VERIFY_SLA_HOURS"] * 3600
    min_avail = cfg["BACKUP_SECONDARY_MIN_AVAILABLE_GIB"] * 1024**3
    max_util = cfg["BACKUP_SECONDARY_MAX_UTILIZATION_PERCENT"] / 100.0

    coverage, capacity_changes = [], []
    valid = (
        isinstance(packet, dict)
        and packet.get("schema") == 1
        and packet.get("store") == store
        and packet.get("tls_verified") is True
    )
    if valid:
        stamp = packet.get("collected_at")
        valid = _is_count(stamp) and -120 <= observed_epoch - stamp <= 300

    if not valid:
        coverage.append(
            _change("secondary_metadata", "complete fresh verified-TLS packet", "missing_invalid_or_stale")
        )
        capacity_changes.append(_change("secondary_capacity", "fresh metadata", "unavailable"))
    elif packet.get("error"):
        coverage.append(_change("secondary_metadata", "readable", packet.get("error")))
        capacity_changes.append(_change("secondary_capacity", "fresh metadata", "collection_failed"))
    else:
        latest = packet.get("latest")
        if not isinstance(latest, dict):
            coverage.append(_change("secondary_latest", "valid listing", "invalid"))
            latest = {}
        if not isinstance(resources, list) or not resources:
            coverage.append(
                _change("primary_enrollment", "nonempty valid enrolled resources", "invalid")
            )
            resources = []
        seen = set()
        for resource in resources:
            vmid = resource.get("vmid")
            kind = resource.get("guest_type")
            if type(vmid) is not int or vmid <= 0 or kind not in ("ct", "vm") or vmid in seen:
                coverage.append(_change("primary_enrollment", "unique typed guest", "invalid"))
                continue
            seen.add(vmid)
            key = kind + "/" + str(vmid)
            row = latest.get(key)
            if not isinstance(row, dict):
                coverage.append(_change("secondary_copy:" + key, "present", "missing"))
                continue
            stamp = row.get("backup_time")
            if not _is_count(stamp) or stamp > observed_epoch + 120:
                coverage.append(_change("secondary_time:" + key, "valid past snapshot", "invalid"))
                continue
            if observed_epoch - stamp > snapshot_sla:
                coverage.append(_change("secondary_age:" + key, "within SLA", "stale"))
            source = resource.get("latest_snapshot")
            source_stamp = source.get("backup_time") if isinstance(source, dict) else None
            if not _is_count(source_stamp):
                coverage.append(
                    _change("secondary_comparison:" + key, "valid primary timestamp", "uncomparable")
                )
            elif stamp < source_stamp and observed_epoch - source_stamp > lag_grace:
                coverage.append(
                    _change("secondary_lag:" + key, "latest primary copied in time", "behind_primary")
                )
            verified = _verification_time(row.get("verification_upid"), store)
            if row.get("verification_state") != "ok" or verified is None:
                coverage.append(
                    _change(
                        "secondary_verification_metadata:" + key,
                        "ok with target-store reference",
                        "missing_invalid_or_source_reference",
                    )
                )
            elif verified > observed_epoch + 120 or observed_epoch - verified > verify_sla:
                coverage.append(
                    _change(
                        "secondary_verification_metadata:" + key,
                        "target metadata within SLA",
                        "stale_or_future",
                    )
                )
        cap = packet.get("capacity")
        if (
            not isinstance(cap, dict)
            or not all(_is_count(cap.get(k)) for k in ("total", "used", "avail"))
            or cap["total"] == 0
        ):
            capacity_changes.append(_change("secondary_capacity", "valid numeric metadata", "invalid"))
        else:
            if cap["avail"] < min_avail:
                capacity_changes.append(_change("secondary_available", "above minimum", "low"))
            if cap["used"] / cap["total"] >= max_util:
                capacity_changes.append(_change("secondary_utilization", "below maximum", "high"))

    return [
        _result("pbs-secondary-coverage", "PBS secondary coverage and metadata", coverage),
        _result("pbs-secondary-capacity", "PBS secondary capacity", capacity_changes),
    ]
