"""Forget a Proxmox guest you deleted: `rackmarshal retire-guest 123`.

Friendly front end for the same safety rules as scripts/retire-pve-baseline.py:
* It finds the newest recorded PVE observation itself (it must be under 900
  seconds old with verified TLS) instead of asking for an observation number.
* Every named guest must be ABSENT from that observation. A guest that still
  exists is refused, so this cannot switch off monitoring of a live guest.
* A plan is shown by default. Nothing is written without --apply, which needs
  root and an approval note, and which first saves a copy of the database.
* Only the guest's baseline row is removed, in one transaction. Incidents,
  events and observations stay as history.
"""
from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import tempfile

MAX_AGE_SECONDS = 900


class RetireError(Exception):
    """A refusal with a message written for the person at the keyboard."""


def _fresh_observation(conn, now):
    row = conn.execute(
        "SELECT id, observed_at, tls_verified, payload_json FROM observations "
        "WHERE collector='pve_cluster_resources' ORDER BY id DESC LIMIT 1").fetchone()
    if row is None:
        raise RetireError("RackMarshal has no Proxmox observation yet. Run the Proxmox check once "
                          "(or wait for its next scheduled run), then try again.")
    try:
        observed = datetime.fromisoformat(row["observed_at"].replace("Z", "+00:00"))
    except ValueError:
        observed = None
    if observed is None or observed.tzinfo is None:
        raise RetireError("The newest Proxmox observation has no usable time, so it cannot be trusted.")
    age = (now - observed).total_seconds()
    if age < -60 or age > MAX_AGE_SECONDS:
        raise RetireError("The newest Proxmox observation is %d minutes old. Run the Proxmox check "
                          "once to get a fresh one, then try again right away." % max(0, int(age // 60)))
    if not row["tls_verified"]:
        raise RetireError("The newest Proxmox observation did not verify Proxmox's certificate, "
                          "so it cannot be used to prove a guest is gone.")
    present = set()
    for item in json.loads(row["payload_json"]).get("resources", []):
        if item.get("type") in ("lxc", "qemu"):
            present.add(str(item.get("vmid")))
    return row["id"], present


def _parse_ids(values):
    ids = []
    for value in values:
        text = str(value).strip()
        if text.startswith(("lxc:", "qemu:")):
            text = text.partition(":")[2]
        if not text.isascii() or not text.isdecimal():
            raise RetireError("'%s' is not a guest number. Use the number shown in Proxmox, such as 123." % value)
        if text not in ids:
            ids.append(text)
    if not ids:
        raise RetireError("Name at least one guest number, for example: rackmarshal retire-guest 123")
    return ids


def plan(conn, ids, now):
    """Return (observation_id, entries). Each entry says what would happen to one guest."""
    observation_id, present = _fresh_observation(conn, now)
    entries = []
    for key in ids:
        rows = conn.execute(
            "SELECT id, resource_type, resource_key, display_name, expected_status "
            "FROM resource_baseline WHERE resource_key=? AND resource_type IN ('lxc','qemu') "
            "ORDER BY resource_type", (key,)).fetchall()
        if key in present:
            action, reason = "REFUSED", "Proxmox still lists this guest, so it is not gone."
        elif not rows:
            action, reason = "SKIPPED", "RackMarshal has no baseline row for it (already forgotten)."
        else:
            action, reason = "RETIRE", "Gone from Proxmox; its baseline row will be removed."
        entries.append({"guest": key, "action": action, "reason": reason,
                        "rows": [dict(r) for r in rows] if action == "RETIRE" else []})
    return observation_id, entries


def retire(db, vmids, note="", apply=False, backup_dir=None, now=None):
    """Plan, or with apply=True carry out, the retirement. Returns a result dict."""
    now = now or datetime.now(timezone.utc)
    ids = _parse_ids(vmids)
    if apply and not note.strip():
        raise RetireError("Say why with --note, for example --note \"deleted test container\".")
    resolved = Path(db).resolve()
    if not resolved.is_file():
        raise RetireError("The RackMarshal database was not found.")
    mode = "rw" if apply else "ro"
    with closing(sqlite3.connect("file:%s?mode=%s" % (resolved, mode), uri=True, timeout=30)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        observation_id, entries = plan(conn, ids, now)
        result = {"state": "PLANNED", "observation_id": observation_id, "guests": entries, "note": note}
        if any(e["action"] == "REFUSED" for e in entries):
            result["state"] = "REFUSED"
            return result
        if not apply:
            return result
        if not any(e["action"] == "RETIRE" for e in entries):
            result["state"] = "NOTHING_TO_DO"
            return result
        backup_root = Path(backup_dir) if backup_dir else resolved.parent / "baseline-backups"
        backup_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        directory = Path(tempfile.mkdtemp(prefix="retire-guest-", dir=backup_root))
        directory.chmod(0o700)
        backup = directory / "state-before.db"
        with closing(sqlite3.connect(backup)) as destination:
            conn.backup(destination)
        backup.chmod(0o600)
        result["backup"] = str(backup)
        try:
            conn.execute("BEGIN IMMEDIATE")
            # Plan again inside the write transaction so nothing changed in between.
            _, entries = plan(conn, ids, now)
            if any(e["action"] == "REFUSED" for e in entries):
                raise RetireError("Proxmox listed a guest again while retiring; nothing was changed.")
            rows = [row for e in entries for row in e["rows"]]
            before = conn.execute("SELECT COUNT(*) FROM resource_baseline").fetchone()[0]
            for row in rows:
                deleted = conn.execute(
                    "DELETE FROM resource_baseline WHERE id=? AND resource_type=? AND resource_key=?",
                    (row["id"], row["resource_type"], row["resource_key"])).rowcount
                if deleted != 1:
                    raise RuntimeError("A baseline row was not deleted as expected; rolled back.")
            after = conn.execute("SELECT COUNT(*) FROM resource_baseline").fetchone()[0]
            if after != before - len(rows):
                raise RuntimeError("Baseline row count changed unexpectedly; rolled back.")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        result.update(state="APPLIED", guests=entries, before_count=before, after_count=after)
    (directory / "receipt.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def describe(result):
    """Plain-language report for a retire() result."""
    lines = []
    for entry in result["guests"]:
        names = ", ".join("%s %s (%s)" % (r["resource_type"], r["resource_key"], r["display_name"])
                          for r in entry["rows"]) or "guest " + entry["guest"]
        verb = {"RETIRE": "Will forget" if result["state"] == "PLANNED" else "Forgot",
                "SKIPPED": "Skipped", "REFUSED": "Refused"}[entry["action"]]
        lines.append("%s %s. %s" % (verb, names, entry["reason"] if entry["action"] != "RETIRE" else ""))
    lines = [line.rstrip() for line in lines]
    state = result["state"]
    if state == "PLANNED":
        lines.append("")
        lines.append("Nothing has been changed. To go ahead, run the same command as root with "
                     "--apply and --note \"why\".")
    elif state == "REFUSED":
        lines.append("")
        lines.append("Nothing was changed. Fix the guest numbers above and try again.")
    elif state == "NOTHING_TO_DO":
        lines.append("")
        lines.append("Nothing needed to change.")
    elif state == "APPLIED":
        lines.append("")
        lines.append("Done. A copy of the database from before the change is at %s." % result["backup"])
        lines.append("Open 'missing guest' alerts for these guests close on the next Proxmox check.")
    return "\n".join(lines)
