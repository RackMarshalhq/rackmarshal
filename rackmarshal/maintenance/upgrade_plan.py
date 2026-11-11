"""`rackmarshal upgrade-plan`: read-only check of whether an upgrade could be applied safely.

Changes nothing and installs nothing. It answers four questions in plain words:
1. Do the installed program files still match the release they came from?
   (A hand patch, or any edit, shows up here with the file names.)
2. Is the new release file the one you meant? Its SHA-256 is checked against a
   SHA256SUMS file and/or a checksum you copied yourself, and the wheel's own
   RECORD is checked against its contents.
3. Are both versions 1.3.x, with the new one newer?
4. Would the database need changing? Same migrations: supported later by the
   apply step. Extra migrations: not supported yet. Different history: refused.
"""
import base64
import csv
import email.parser
import hashlib
import io
from pathlib import Path, PurePosixPath
import re
import sqlite3
from contextlib import closing
import zipfile

from rackmarshal.maintenance import migration_rehearsal as rehearsal

LIMIT = 32 * 1024 * 1024
SUPPORTED_SERIES = (1, 3)
VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:rc(\d+))?$")
MIGRATIONS = "rackmarshal/db/migrations/"


class PlanError(Exception):
    """A refusal written for the person at the keyboard."""


def parse_version(text):
    match = VERSION.match(str(text))
    if not match:
        raise PlanError("Version '%s' is not one this tool understands (expected like 1.3.0 or 1.3.1rc1)." % text)
    major, minor, patch, rc = match.groups()
    # A release candidate sorts before its final release.
    return (int(major), int(minor), int(patch), float("inf") if rc is None else int(rc))


def _record_hash(data):
    return "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()


def installed_state(site_packages):
    """Return (version, differences) comparing installed files with the installed RECORD."""
    site = Path(site_packages)
    dists = sorted(site.glob("rackmarshal-*.dist-info"))
    if len(dists) != 1:
        raise PlanError("Expected exactly one installed RackMarshal release in %s, found %d." % (site, len(dists)))
    dist = dists[0]
    version = dist.name[len("rackmarshal-"):-len(".dist-info")]
    record = dist / "RECORD"
    if not record.is_file():
        raise PlanError("The installed release has no RECORD file, so its files cannot be verified.")
    modified, missing = [], []
    with record.open(newline="", encoding="utf-8") as stream:
        for row in csv.reader(stream):
            if len(row) != 3 or not row[1]:
                continue  # RECORD itself, bytecode and other unhashed entries
            name, checksum = row[0], row[1]
            path = site / name
            if "__pycache__" in name or name.endswith(".pyc"):
                continue
            try:
                actual = _record_hash(path.read_bytes())
            except FileNotFoundError:
                missing.append(name)
                continue
            if actual != checksum:
                modified.append(name)
    return version, {"modified": sorted(modified), "missing": sorted(missing)}


def read_candidate(wheel_path, sums_path=None, expected_sha256=None):
    """Verify the new release file and return its facts."""
    wheel = Path(wheel_path)
    if not wheel.is_file():
        raise PlanError("The release file %s was not found." % wheel.name)
    data = wheel.read_bytes()
    if len(data) > LIMIT:
        raise PlanError("The release file is larger than the safety limit.")
    actual = hashlib.sha256(data).hexdigest()
    checked = []
    if sums_path:
        found = None
        for line in Path(sums_path).read_text().splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1].lstrip("*") == wheel.name:
                found = parts[0].lower()
        if found is None:
            raise PlanError("%s is not listed in the checksum file." % wheel.name)
        if found != actual:
            raise PlanError("The release file does not match the checksum file. Do not use it.")
        checked.append("the SHA256SUMS file")
    if expected_sha256:
        if expected_sha256.strip().lower() != actual:
            raise PlanError("The release file does not match the checksum you supplied. Do not use it.")
        checked.append("the checksum you supplied")
    if not checked:
        raise PlanError("Give --sums (the release's SHA256SUMS file) or --sha256 so the file can be verified.")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise PlanError("The release file is not a valid wheel.") from exc
    payloads = {}
    with archive:
        entries = archive.infolist()
        if not 0 < len(entries) <= 5000:
            raise PlanError("The release file has an unexpected number of entries.")
        total = 0
        for entry in entries:
            path = PurePosixPath(entry.filename)
            if (not entry.filename or path.is_absolute() or "\\" in entry.filename
                    or any(part in ("", ".", "..") for part in entry.filename.rstrip("/").split("/"))):
                raise PlanError("The release file contains an unsafe path.")
            if entry.is_dir():
                continue
            total += entry.file_size
            if total > LIMIT:
                raise PlanError("The release file expands beyond the safety limit.")
            payloads[entry.filename] = archive.read(entry)
    metas = [name for name in payloads if name.endswith(".dist-info/METADATA") and name.count("/") == 1]
    if len(metas) != 1:
        raise PlanError("The release file has no single METADATA entry.")
    meta = email.parser.BytesParser().parsebytes(payloads[metas[0]])
    if meta.get("Name") != "rackmarshal":
        raise PlanError("The release file is not a RackMarshal wheel.")
    version = meta.get("Version")
    record_name = metas[0].rsplit("/", 1)[0] + "/RECORD"
    if record_name not in payloads:
        raise PlanError("The release file has no RECORD.")
    for row in csv.reader(io.StringIO(payloads[record_name].decode("utf-8"))):
        if len(row) == 3 and row[1] and row[0] != record_name:
            if row[0] not in payloads or _record_hash(payloads[row[0]]) != row[1]:
                raise PlanError("The release file's contents do not match its own RECORD (%s)." % row[0])
    sql = {PurePosixPath(name).stem: body for name, body in payloads.items()
           if name.startswith(MIGRATIONS) and name.endswith(".sql")}
    migrations = {name: hashlib.sha256(body).hexdigest() for name, body in sql.items()}
    return {"version": version, "sha256": actual, "verified_by": checked, "migrations": migrations,
            "migration_sql": sql}


def ledger(database):
    path = Path(database)
    if not path.is_file():
        raise PlanError("The RackMarshal database was not found.")
    try:
        with closing(sqlite3.connect("file:%s?mode=ro" % path.resolve(), uri=True, timeout=5)) as conn:
            return {row[0]: row[1] for row in conn.execute("SELECT id, checksum FROM schema_migrations")}
    except sqlite3.Error as exc:
        raise PlanError("The database's migration history could not be read: %s." % exc) from exc


def compare_migrations(current, candidate):
    """Return ("SAME", []) | ("EXTRA", [ids]) | ("DIFFERENT", [ids])."""
    changed = sorted(i for i in current if i in candidate and candidate[i] != current[i])
    dropped = sorted(i for i in current if i not in candidate)
    if changed or dropped:
        return "DIFFERENT", changed + dropped
    extra = sorted(i for i in candidate if i not in current)
    return ("EXTRA", extra) if extra else ("SAME", [])


def plan(site_packages, database, wheel_path, sums_path=None, expected_sha256=None):
    """Return a result dict. result['status'] is READY, READY_WITH_DATABASE_CHANGE or REFUSED."""
    findings, refusals = [], []
    installed, differences = installed_state(site_packages)
    candidate = read_candidate(wheel_path, sums_path, expected_sha256)
    findings.append("Installed release: %s. New release file: %s (verified by %s)."
                    % (installed, candidate["version"], " and ".join(candidate["verified_by"])))
    if differences["modified"] or differences["missing"]:
        parts = []
        if differences["modified"]:
            parts.append("changed: " + ", ".join(differences["modified"]))
        if differences["missing"]:
            parts.append("missing: " + ", ".join(differences["missing"]))
        refusals.append("The installed files no longer match release %s (%s). Restore them from that release "
                        "first; a hand patch has to be undone before an upgrade." % (installed, "; ".join(parts)))
    else:
        findings.append("Installed files match release %s exactly." % installed)
    old_v, new_v = parse_version(installed), parse_version(candidate["version"])
    for label, value in (("installed", old_v), ("new", new_v)):
        if value[:2] != SUPPORTED_SERIES:
            refusals.append("The %s release is outside the 1.3 series; upgrades are only for 1.3.x to 1.3.y." % label)
    if new_v <= old_v:
        refusals.append("The new release (%s) is not newer than the installed one (%s)." % (candidate["version"], installed))
    current = ledger(database)
    state, ids = compare_migrations(current, candidate["migrations"])
    extra = {}
    if state == "SAME":
        findings.append("The database needs no changes for this release.")
    elif state == "EXTRA":
        extra = judge_database_changes(database, current, ids, candidate, findings, refusals)
    else:
        refusals.append("The database history differs from this release (%s). It cannot be upgraded." % ", ".join(ids))
    if refusals:
        status = "REFUSED"
    else:
        status = "READY_WITH_DATABASE_CHANGE" if state == "EXTRA" else "READY"
    return dict({"status": status, "installed": installed, "candidate": candidate["version"], "findings": findings,
                 "refusals": refusals, "candidate_sha256": candidate["sha256"], "changes_made": False}, **extra)


def judge_database_changes(database, current, ids, candidate, findings, refusals):
    """Rules for applying a release's new migrations. Returns the facts the apply step needs, or {}."""
    try:
        newest = max((rehearsal.migration_order_key(i) for i in current), default=None)
        misplaced = [i for i in ids if newest is not None and rehearsal.migration_order_key(i) <= newest]
    except rehearsal.RehearsalError as exc:
        refusals.append(str(exc))
        return {}
    if misplaced:
        refusals.append("The new database change(s) %s would slot in before ones you already have. "
                        "Changes must only be added after the newest applied one." % ", ".join(misplaced))
        return {}
    ordered = sorted(ids, key=rehearsal.migration_order_key)
    triples = [(i, candidate["migration_sql"][i].decode("utf-8"), candidate["migrations"][i]) for i in ordered]
    try:
        result = rehearsal.rehearse(database, triples)
    except rehearsal.RehearsalError as exc:
        refusals.append("The database changes (%s) cannot be applied safely: %s" % (", ".join(ordered), exc))
        return {}
    if result["problems"]:
        refusals.append("The database changes (%s) would not keep your data intact: %s."
                        % (", ".join(ordered), "; ".join(result["problems"])))
        return {}
    findings.append("This release adds database changes (%s). They were rehearsed on a private copy of your "
                    "database: every table, column and row was kept%s."
                    % (", ".join(ordered), "; new tables: " + ", ".join(result["added_tables"]) if result["added_tables"] else ""))
    findings.append("Not yet checked here: that the program you have now still runs on the changed database. "
                    "The apply step proves that before it changes anything.")
    return {"migrations": ordered, "expected_schema_sha256": result["schema_sha256"],
            "expected_ledger": result["ledger"]}


def describe(result, can_apply=False):
    lines = list(result["findings"]) + ["Refused: " + text for text in result["refusals"]]
    lines.append("")
    ready = ("Result: this upgrade can be applied." if can_apply else
             "Result: this upgrade could be applied. This command only checks; nothing was done.")
    verdict = {"READY": ready,
               "READY_WITH_DATABASE_CHANGE": ready.replace("could be applied", "could be applied, including its database changes")
               if not can_apply else "Result: this upgrade can be applied, including its database changes.",
               "REFUSED": "Result: refused. See the reasons above."}[result["status"]]
    lines.append(verdict)
    lines.append("This check is read-only: nothing has been installed, changed or restarted yet." if can_apply else
                 "This command is read-only: nothing was installed, changed or restarted.")
    return "\n".join(lines)
