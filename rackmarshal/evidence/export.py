#!/usr/bin/env python3
"""Export RackMarshal evidence for SoT review.

Reads GET /status (rank 1) and optional state.db extras (rank 2).
Writes a dated bundle under STATE_DIR/evidence/. Never writes SoT markdown.

See packaging/SOT_EVIDENCE.md.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from rackmarshal.core.config import load_config, state_db, state_dir

EXPORTER_VERSION = "1.1.1"
DEFAULT_STATUS_URL = "http://127.0.0.1:9110/status"
ET = ZoneInfo("America/New_York")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def stamp_et(now: datetime | None = None) -> str:
    """Filesystem-safe stamp in America/New_York, e.g. 2026-09-16T111500-0400."""
    local = (now or utcnow()).astimezone(ET)
    return local.strftime("%Y-%m-%dT%H%M%S%z")


def fetch_status(url: str, timeout: float = 10.0) -> dict[str, Any]:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            ctype = resp.headers.get("Content-Type", "")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"status fetch failed: {exc}") from exc

    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"status returned non-JSON ({ctype}): {exc}") from exc

    if not isinstance(data, dict):
        raise RuntimeError("status JSON root must be an object")
    return data


def schema_summary(status: dict[str, Any]) -> dict[str, Any]:
    domains_out: dict[str, Any] = {}
    for name, domain in sorted((status.get("domains") or {}).items()):
        if not isinstance(domain, dict):
            domains_out[name] = {"type": type(domain).__name__}
            continue
        lo = domain.get("last_observation")
        domains_out[name] = {
            "keys": sorted(domain.keys()),
            "status": domain.get("status"),
            "open_incidents": domain.get("open_incidents"),
            "last_observation_keys": (
                sorted(lo.keys()) if isinstance(lo, dict) else None
            ),
        }

    sw = status.get("self_watch") or {}
    sw_out: dict[str, Any] = {
        "keys": sorted(sw.keys()) if isinstance(sw, dict) else [],
        "status": sw.get("status") if isinstance(sw, dict) else None,
        "open_self_incidents": (
            sw.get("open_self_incidents") if isinstance(sw, dict) else None
        ),
    }
    if isinstance(sw, dict):
        for part in ("freshness", "units", "notifications", "cycle_health"):
            p = sw.get(part)
            if isinstance(p, dict):
                sample = next(iter(p.values()), None)
                sw_out[part] = {
                    "entry_keys": sorted(p.keys()),
                    "sample_value_keys": (
                        sorted(sample.keys()) if isinstance(sample, dict) else None
                    ),
                }
            else:
                sw_out[part] = p

    return {
        "top_keys": sorted(status.keys()),
        "schema_version": status.get("schema_version"),
        "overall_status": status.get("overall_status"),
        "open_incident_count": status.get("open_incident_count"),
        "generated_at": status.get("generated_at"),
        "domains": domains_out,
        "self_watch": sw_out,
    }


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return row is not None


def collect_db_extras(db_path: Path) -> dict[str, Any]:
    """Rank-2 supporting facts. Read-only; best-effort."""
    extras: dict[str, Any] = {
        "state_db": str(db_path),
        "open_incidents_by_table": {},
        "notes": [],
    }
    uri = f"file:{db_path}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=10)
    except sqlite3.Error as exc:
        extras["error"] = f"open failed: {exc}"
        return extras

    try:
        conn.row_factory = sqlite3.Row
        table_specs = [
            ("resource_incidents", "incident_state"),
            ("zfs_incidents", "incident_state"),
            ("backup_incidents", "incident_state"),
            ("ha_incidents", "incident_state"),
            ("self_incidents", "incident_state"),
            ("hardware_temperature_state", "incident_state"),
        ]
        for table, state_col in table_specs:
            if not _table_exists(conn, table):
                extras["notes"].append(f"missing table {table}")
                continue
            try:
                n = conn.execute(
                    f"SELECT COUNT(*) AS c FROM {table} WHERE {state_col} = 'OPEN'"
                ).fetchone()["c"]
                extras["open_incidents_by_table"][table] = int(n)
            except sqlite3.Error as exc:
                extras["notes"].append(f"{table}: {exc}")

        if _table_exists(conn, "hardware_observations"):
            row = conn.execute(
                """
                SELECT MAX(observed_at) AS observed_at, COUNT(*) AS n
                FROM hardware_observations
                WHERE observed_at = (
                    SELECT MAX(observed_at) FROM hardware_observations
                )
                """
            ).fetchone()
            extras["hardware_latest_batch"] = {
                "observed_at": row["observed_at"],
                "device_count": int(row["n"] or 0),
            }
    finally:
        conn.close()

    return extras


def render_evidence_md(
    *,
    status: dict[str, Any],
    extras: dict[str, Any] | None,
    meta: dict[str, Any],
) -> str:
    lines: list[str] = []
    lines.append("# RackMarshal SoT Evidence Bundle")
    lines.append("")
    lines.append(f"- **Exported (ET):** {meta['exported_at_et']}")
    lines.append(f"- **Exported (UTC):** {meta['exported_at_utc']}")
    lines.append(f"- **Exporter:** {meta['exporter']} {meta['exporter_version']}")
    lines.append(f"- **Status URL:** `{meta['status_url']}`")
    lines.append(f"- **Bundle id:** `{meta['bundle_id']}`")
    lines.append("")
    lines.append("## Overall")
    lines.append("")
    lines.append(f"- overall_status: **{status.get('overall_status')}**")
    lines.append(f"- open_incident_count: **{status.get('open_incident_count')}**")
    lines.append(f"- schema_version: {status.get('schema_version')}")
    lines.append(f"- generated_at: {status.get('generated_at')}")
    lines.append("")
    lines.append("## Domains")
    lines.append("")

    domains = status.get("domains") or {}
    for name in ("PVE", "ZFS", "BACKUP", "HA", "HARDWARE"):
        d = domains.get(name)
        if not isinstance(d, dict):
            lines.append(f"- **{name}:** MISSING from /status")
            continue
        lo = d.get("last_observation") or {}
        observed = lo.get("observed_at") if isinstance(lo, dict) else None
        lines.append(
            f"- **{name}:** status={d.get('status')} "
            f"open_incidents={d.get('open_incidents')} "
            f"last_observation={observed}"
        )
    for name in sorted(set(domains) - {"PVE", "ZFS", "BACKUP", "HA", "HARDWARE"}):
        d = domains.get(name) or {}
        lines.append(
            f"- **{name}:** status={d.get('status')} "
            f"open_incidents={d.get('open_incidents')}"
        )

    lines.append("")
    lines.append("## self_watch")
    lines.append("")
    sw = status.get("self_watch") or {}
    lines.append(f"- status: **{sw.get('status')}**")
    lines.append(f"- open_self_incidents: **{sw.get('open_self_incidents')}**")

    cycle_health = sw.get("cycle_health") or {}
    if isinstance(cycle_health, dict) and cycle_health:
        lines.append("")
        lines.append("### Cycle Health")
        lines.append("")
        for unit, row in sorted(cycle_health.items()):
            if not isinstance(row, dict):
                lines.append(f"- {unit}: {row}")
                continue

            flag = ""
            if row.get("health_state") == "FAILED":
                flag = " **← FAILED**"

            lines.append(
                f"- **{unit}:** "
                f"state={row.get('health_state')} "
                f"failure_count={row.get('failure_count')} "
                f"last_result={row.get('last_result_at')} "
                f"last_success={row.get('last_success_at')} "
                f"last_failure={row.get('last_failure_at')} "
                f"exit_code={row.get('last_exit_code')} "
                f"exit_status={row.get('last_exit_status')}"
                f"{flag}"
            )

    freshness = sw.get("freshness") or {}
    if isinstance(freshness, dict) and freshness:
        lines.append("")
        lines.append("### Freshness")
        lines.append("")
        for dom, fr in sorted(freshness.items()):
            if not isinstance(fr, dict):
                lines.append(f"- {dom}: {fr}")
                continue
            flag = ""
            if fr.get("state") in ("STALE", "MISSING"):
                flag = " **← STALE/MISSING**"
            lines.append(
                f"- **{dom}:** state={fr.get('state')} "
                f"age_seconds={fr.get('age_seconds')} "
                f"stale_after={fr.get('stale_after_seconds')} "
                f"observed_at={fr.get('observed_at')}{flag}"
            )

    units = sw.get("units") or {}
    if isinstance(units, dict) and units:
        lines.append("")
        lines.append("### Units")
        lines.append("")
        for unit, info in sorted(units.items()):
            if isinstance(info, dict):
                lines.append(
                    f"- `{unit}`: {json.dumps(info, sort_keys=True, separators=(',', ':'))}"
                )
            else:
                lines.append(f"- `{unit}`: {info}")

    notes = sw.get("notifications")
    if notes is not None:
        lines.append("")
        lines.append("### Notifications")
        lines.append("")
        lines.append(f"```json\n{json.dumps(notes, indent=2, sort_keys=True)}\n```")

    if extras is not None:
        lines.append("")
        lines.append("## Rank-2 DB extras")
        lines.append("")
        lines.append(
            f"```json\n{json.dumps(extras, indent=2, sort_keys=True)}\n```"
        )

    lines.append("")
    lines.append("## CROSS_CHECK")
    lines.append("")
    lines.append(
        "_Left empty by RackMarshal. Consumers (Grok / human) may add "
        "primary-node daily audit, PBS, HA observer, or Grok monitor results here "
        "in a review copy — never overwrite rank-1 fields._"
    )
    lines.append("")
    lines.append("## Non-goals reminder")
    lines.append("")
    lines.append("- This bundle does **not** write or patch SoT markdown.")
    lines.append("- Narrative claim changes require operator approval.")
    lines.append("")
    return "\n".join(lines)


def bundle_age_timestamp(name: str) -> float | None:
    """Parse bundle dir stamp like 2026-09-16T111718-0400 to epoch seconds (ET-aware)."""
    m = re.match(
        r"^(?P<y>\d{4})-(?P<mo>\d{2})-(?P<d>\d{2})T"
        r"(?P<h>\d{2})(?P<mi>\d{2})(?P<s>\d{2})"
        r"(?P<off>[+-]\d{4})$",
        name,
    )
    if not m:
        return None
    off = m.group("off")
    iso = (
        f"{m.group('y')}-{m.group('mo')}-{m.group('d')}T"
        f"{m.group('h')}:{m.group('mi')}:{m.group('s')}{off}"
    )
    try:
        return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%S%z").timestamp()
    except ValueError:
        return None


def prune_evidence(out_root: Path, retain_days: int, keep_ids: set[str] | None = None) -> list[str]:
    """Remove dated bundle dirs older than retain_days.

    Age is taken from the directory stamp (2026-09-16T111718-0400), not mtime,
    so freshly copied old stamps still prune. Keeps `latest` target and keep_ids.
    """
    if retain_days <= 0:
        return []
    keep_ids = set(keep_ids or ())
    latest = out_root / "latest"
    if latest.is_symlink():
        try:
            keep_ids.add(latest.resolve().name)
        except FileNotFoundError:
            pass
    elif latest.is_dir():
        keep_ids.add(latest.name)

    cutoff = utcnow().timestamp() - (retain_days * 86400)
    removed: list[str] = []
    for child in sorted(out_root.iterdir()):
        if child.name == "latest":
            continue
        if not child.is_dir():
            continue
        if child.name in keep_ids:
            continue
        stamp_ts = bundle_age_timestamp(child.name)
        if stamp_ts is None:
            # Unknown naming — leave alone
            continue
        if stamp_ts >= cutoff:
            continue
        shutil.rmtree(child)
        removed.append(child.name)
    return removed


def write_bundle(
    *,
    out_root: Path,
    status: dict[str, Any],
    extras: dict[str, Any] | None,
    status_url: str,
    update_latest: bool,
    retention_class: str = "on_demand",
) -> Path:
    now = utcnow()
    bundle_id = stamp_et(now)
    bundle_dir = out_root / bundle_id
    bundle_dir.mkdir(parents=True, exist_ok=False)

    schema = schema_summary(status)
    meta = {
        "bundle_id": bundle_id,
        "exported_at_utc": now.isoformat().replace("+00:00", "Z"),
        "exported_at_et": now.astimezone(ET).isoformat(),
        "exporter": "export_sot_evidence.py",
        "exporter_version": EXPORTER_VERSION,
        "status_url": status_url,
        "hostname": os.uname().nodename,
        "retention_class": retention_class,
        "includes_db_extras": extras is not None,
        "sot_write": False,
    }

    (bundle_dir / "status.json").write_text(
        json.dumps(status, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (bundle_dir / "status.schema.json").write_text(
        json.dumps(schema, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if extras is not None:
        (bundle_dir / "db_extras.json").write_text(
            json.dumps(extras, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    (bundle_dir / "META.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (bundle_dir / "EVIDENCE.md").write_text(
        render_evidence_md(status=status, extras=extras, meta=meta),
        encoding="utf-8",
    )

    if update_latest:
        latest = out_root / "latest"
        if latest.is_symlink() or latest.exists():
            latest.unlink()
        latest.symlink_to(bundle_id)

    return bundle_dir


def main(argv: list[str] | None = None) -> int:
    config = load_config()
    default_root = state_dir(config) / "evidence"

    parser = argparse.ArgumentParser(
        description="Export RackMarshal /status evidence bundle for SoT review."
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=default_root,
        help=f"Evidence root directory (default: {default_root})",
    )
    parser.add_argument(
        "--status-url",
        default=os.environ.get("RACKMARSHAL_STATUS_URL", DEFAULT_STATUS_URL),
        help=f"Status API URL (default: {DEFAULT_STATUS_URL})",
    )
    parser.add_argument(
        "--no-db",
        action="store_true",
        help="Skip rank-2 state.db extras",
    )
    parser.add_argument(
        "--no-latest",
        action="store_true",
        help="Do not update the evidence/latest symlink",
    )
    parser.add_argument(
        "--retain-days",
        type=int,
        default=int(os.environ.get("RACKMARSHAL_EVIDENCE_RETAIN_DAYS", "35")),
        help="Delete dated bundles older than N days (0=disable). Default 35.",
    )
    parser.add_argument(
        "--retention-class",
        default=os.environ.get("RACKMARSHAL_EVIDENCE_RETENTION_CLASS", "on_demand"),
        help="META.retention_class label (on_demand|daily).",
    )
    args = parser.parse_args(argv)

    status = fetch_status(args.status_url)
    extras = None
    if not args.no_db:
        extras = collect_db_extras(state_db(config))

    args.out.mkdir(parents=True, exist_ok=True)
    bundle_dir = write_bundle(
        out_root=args.out,
        status=status,
        extras=extras,
        status_url=args.status_url,
        update_latest=not args.no_latest,
        retention_class=args.retention_class,
    )
    pruned = prune_evidence(
        args.out,
        args.retain_days,
        keep_ids={bundle_dir.name},
    )

    result = {
        "status": "OK",
        "bundle_dir": str(bundle_dir),
        "overall_status": status.get("overall_status"),
        "open_incident_count": status.get("open_incident_count"),
        "domains": sorted((status.get("domains") or {}).keys()),
        "includes_db_extras": extras is not None,
        "retain_days": args.retain_days,
        "pruned": pruned,
        "retention_class": args.retention_class,
    }
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 — CLI surface
        print(
            json.dumps(
                {"status": "ERROR", "error": str(exc)},
                separators=(",", ":"),
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
