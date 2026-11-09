"""Plain-language incident notification text.

Turns an incident notification packet into a short title and a message that
says what is wrong, whether it matters and what to do. The structured
incident record is unchanged: only the Home Assistant notification text is
affected. Anything this module cannot handle falls back to the classic text
(see ``render_safe``), so a notification is never lost because of wording.

Settings (all optional, read from rackmarshal.conf):

- ``NOTIFY_STYLE``: ``plain`` (default) or ``classic``.
- ``NOTIFY_TIMEZONE``: IANA time zone for times in messages (default: the
  system's local time zone).
- ``NOTIFY_HELP_TEXT``: the sentence used when the next step is "get help".
- ``NOTIFY_SERVER_NAME``: what to call the backup server in messages.
- ``NOTIFY_DISPLAY_NAMES``: ``key:Name`` pairs, comma separated, used for
  per-person backup checks (default: the key, capitalised).
"""

from __future__ import annotations

import datetime
import re

STYLE_PLAIN = "plain"
STYLE_CLASSIC = "classic"

DEFAULT_HELP_TEXT = (
    "If it doesn't clear on its own, check the RackMarshal status page."
)
DEFAULT_SERVER_NAME = "the backup server"

_DOMAIN_NAMES = {
    "backup": "backup",
    "pve": "Proxmox",
    "zfs": "ZFS storage",
    "ha": "Home Assistant",
    "hardware": "hardware",
    "mount": "shared folder",
    "notify": "notification",
    "self-watch": "self-check",
    "status": "status page",
}


# ---------------------------------------------------------------- settings


def settings_from_config(config):
    """Build the settings dict from a loaded rackmarshal.conf mapping."""
    config = config or {}

    def get(key):
        value = config.get(key)
        return str(value).strip() if value is not None else ""

    names = {}
    for pair in get("NOTIFY_DISPLAY_NAMES").split(","):
        key, sep, name = pair.partition(":")
        if sep and key.strip() and name.strip():
            names[key.strip().lower()] = name.strip()

    style = get("NOTIFY_STYLE").lower() or STYLE_PLAIN
    if style not in (STYLE_PLAIN, STYLE_CLASSIC):
        style = STYLE_PLAIN

    return {
        "style": style,
        "timezone": get("NOTIFY_TIMEZONE") or None,
        "help": get("NOTIFY_HELP_TEXT") or DEFAULT_HELP_TEXT,
        "server": get("NOTIFY_SERVER_NAME") or DEFAULT_SERVER_NAME,
        "names": names,
    }


def _settings(settings):
    return settings if settings is not None else settings_from_config({})


# ----------------------------------------------------------------- helpers


def _tz(settings):
    name = settings.get("timezone")
    if name:
        try:
            from zoneinfo import ZoneInfo

            return ZoneInfo(name)
        except Exception:
            pass
    return None  # system local time


def _parse_ts(value):
    if not value:
        return None
    try:
        dt = datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt


def _local(value, settings):
    dt = _parse_ts(value)
    if dt is None:
        return None
    loc = dt.astimezone(_tz(settings))
    clock = loc.strftime("%I:%M %p").lstrip("0")
    return f"{loc.strftime('%a %b')} {loc.day}, {clock}"


def _plural(n, word):
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _hours_text(hours):
    try:
        h = float(hours)
    except (TypeError, ValueError):
        return None
    if h >= 48:
        return _plural(int(h / 24.0 + 0.5), "day")
    if h >= 0.95:
        return _plural(int(h + 0.5), "hour")
    return _plural(max(1, int(round(h * 60))), "minute")


def _duration(start, end):
    a, b = _parse_ts(start), _parse_ts(end)
    if a is None or b is None or b < a:
        return None
    return _hours_text((b - a).total_seconds() / 3600.0)


def _missing(value):
    return value is None or str(value).strip().lower() in ("", "none", "null", "unknown")


_DIFF = re.compile(
    r"([A-Za-z0-9_:/.\-]+): expected (.+?), actual (.+?)"
    r"(?=; [A-Za-z0-9_:/.\-]+: expected |$)"
)


def _diffs(incident):
    """[(field, expected, actual)] parsed from the incident note."""
    note = incident.get("note") or ""
    if "Observed differences:" in note:
        note = note.split("Observed differences:", 1)[1]
    found = []
    for match in _DIFF.finditer(note.strip()):
        found.append(
            (
                match.group(1),
                match.group(2).strip().strip("'"),
                match.group(3).strip().strip("'"),
            )
        )
    return found


def _num(text):
    match = re.search(r"-?\d+(?:\.\d+)?", str(text or ""))
    return float(match.group(0)) if match else None


def _age(incident, field_suffix):
    for field, expected, actual in _diffs(incident):
        if field.endswith(field_suffix):
            return _num(actual), _num(expected)
    actual = incident.get("actual_status") or ""
    if field_suffix in actual:
        return _num(actual.split("=", 1)[-1]), _num(incident.get("expected_status"))
    return None, None


def _person(key, settings):
    k = (key or "").split(":", 1)[0].strip().lower()
    return settings["names"].get(k) or (k[:1].upper() + k[1:]) or "Someone"


def _guest_label(kind_and_id):
    kind, _, vid = kind_and_id.partition("/")
    if not vid:
        return kind_and_id
    return f"VM {vid}" if kind == "vm" else f"container {vid}"


_AGE_LABELS = {
    "snapshot": "the latest backup",
    "verify": "the last verification",
    "log": "the last run",
}

_STATES = {
    "SUSPENDED": "suspended",
    "FAULTED": "failed (faulted)",
    "CANT_OPEN": "failing (can't be opened)",
    "ONLINE": "online",
    "DEGRADED": "degraded",
    "UNAVAIL": "unavailable",
    "OFFLINE": "offline",
    "REMOVED": "removed",
}


def _state(value):
    return _STATES.get(str(value).upper(), str(value))


def _field_text(field, expected, actual):
    f = field.lower()
    base = f.split(":", 1)[0]
    if base == "secondary_verification_metadata":
        return None  # summarised by the caller
    if base == "secondary_copy":
        if str(actual).startswith("missing"):
            return "there is no second copy while the main backup is overdue"
        return f"the second copy is {_hours_text(_num(actual)) or actual} old (limit {_hours_text(_num(expected)) or expected})"
    if base == "secondary_lag":
        return "the second copy is behind the main backup"
    if f.endswith("age_hours"):
        if _missing(actual):
            return "no result was found"
        prefix = f[: -len("age_hours")].rstrip("_")
        what = _AGE_LABELS.get(prefix, "the last success")
        return (
            f"{what} was {_hours_text(_num(actual)) or actual} ago "
            f"(limit {_hours_text(_num(expected)) or expected})"
        )
    if f == "verification_state":
        if _missing(actual):
            return "the backup hasn't been verified yet"
        return f"verification result is '{actual}'"
    if f in ("snapshot_present", "latest_snapshot"):
        if str(actual) in ("0", "None", "") or _missing(actual):
            return "no backup was found"
        return "a backup was found where none was expected"
    if f == "name" and _missing(actual):
        return "it no longer appears in the backup list"
    if f == "finished":
        return "the run hasn't finished"
    if f in ("unit_result", "exec_main_status", "status_json"):
        return "the last run failed"
    if f == "failed_count":
        return f"{_plural(int(_num(actual) or 0), 'check')} failed"
    if f == "failing_checks":
        return f"failing: {actual}"
    if f == "probe_errors":
        return "the check itself reported an error"
    if f in ("status", "state"):
        if _missing(actual):
            return "no status was reported"
        return f"{f} is {_state(actual)} (normally {_state(expected)})"
    if f.endswith("error_count") or f.endswith("errors"):
        return f"{_plural(int(_num(actual) or 0), field.replace('_', ' ').replace('errors', 'error').replace('error count', 'error').strip())} reported"
    if _missing(actual):
        return f"{field.replace('_', ' ')} is missing"
    return f"{field.replace('_', ' ')}: {actual} (expected {expected})"


def _detail_sentence(incident, limit=4):
    lines = []
    for field, expected, actual in _diffs(incident):
        text = _field_text(field, expected, actual)
        if text and text not in lines:
            lines.append(text)
    if not lines:
        return ""
    extra = len(lines) - limit
    if extra > 0:
        lines = lines[:limit] + [f"and {extra} more"]
    text = "; ".join(lines)
    return text[0].upper() + text[1:] + "."


def _sentence(text):
    return text[0].upper() + text[1:] if text else text


# --------------------------------------------------------------- templates
# Each returns a dict with: subject (what it is about, used for recovery),
# problem (one line), why (does it matter), todo (what to do) and optionally
# severity ("urgent", "info"; default warning).


def _probe_problem(i):
    for field, _e, actual in _diffs(i):
        if field in ("phone_backup", "messages"):
            return "unreadable" if "probe" in str(actual) else "missing"
    return None


def _t_phone(i, s):
    who = _person(i.get("resource_key"), s)
    age, limit = _age(i, "phone_age_hours")
    probe = _probe_problem(i)
    if probe:
        return dict(
            subject=f"{who}'s phone backup",
            problem=(f"{who}'s phone backup status couldn't be read" if probe == "unreadable"
                     else f"No backup found for {who}'s phone"),
            why="RackMarshal can't confirm the phone is backed up.",
            todo=s["help"] if probe == "unreadable"
            else f"Back up the phone from its computer. The backup is saved to {s['server']}.",
        )
    return dict(
        subject=f"{who}'s phone backup",
        problem=f"{who}'s phone hasn't backed up in {_hours_text(age) or 'a while'}",
        why="New photos and data on the phone aren't protected until it backs up"
        + (f" (limit {_hours_text(limit)})." if limit else "."),
        todo=f"Back up the phone from its computer. The backup is saved to {s['server']}.",
    )


def _t_timemachine(i, s):
    who = _person(i.get("resource_key"), s)
    age, limit = _age(i, "timemachine_age_hours")
    return dict(
        subject=f"{who}'s Time Machine backup",
        problem=f"{who}'s Mac hasn't finished a Time Machine backup in {_hours_text(age) or 'a while'}",
        why="Recent changes on that Mac aren't backed up"
        + (f" (limit {_hours_text(limit)})." if limit else "."),
        todo="Make sure the Mac is on and on the home network, then choose Back Up Now in Time Machine.",
    )


_MESSAGES = {
    "pull": (
        "Messages archive",
        "{who}'s Messages haven't been copied from the Mac",
        "New messages aren't being archived or made searchable.",
        "Check that {who}'s Mac is on, on the home network and not asleep overnight.",
    ),
    "snap": (
        "Messages daily snapshot",
        "The daily snapshot of {who}'s Messages archive is overdue",
        "The archive itself is fine; the daily restore point is missing.",
        None,
    ),
    "repl": (
        "Messages backup copy",
        "The backup copy of {who}'s Messages archive is overdue",
        "The main archive is fine; the second copy is behind.",
        None,
    ),
    "search": (
        "message search",
        "{who}'s message search hasn't been refreshed",
        "Search still works but won't show the newest messages.",
        None,
    ),
}


def _t_messages(i, s):
    key = i.get("resource_key") or ""
    who = _person(key, s)
    kind = key.split(":", 1)[1] if ":" in key else "pull"
    label, problem, why, todo = _MESSAGES.get(kind, _MESSAGES["pull"])
    problem = problem.format(who=who)
    failed = False
    age = None
    for field, _expected, actual in _diffs(i):
        if field.endswith("_result"):
            failed = True
        elif field.endswith("_age_hours"):
            age = _num(actual)
    if _probe_problem(i) == "unreadable":
        problem = f"{who}'s Messages backup status couldn't be read"
        why, todo = "RackMarshal can't confirm the Messages archive is up to date.", None
    elif failed:
        problem = f"{who}'s nightly message-search rebuild failed"
    elif age is not None:
        problem += f" for {_hours_text(age)}"
    return dict(
        subject=f"{who}'s {label}",
        problem=problem,
        why=why,
        todo=(todo or s["help"]).format(who=who),
    )


def _t_guest_backup(i, s):
    name = i.get("display_name") or i.get("resource_key")
    vid = i.get("resource_key")
    label = f"{name} ({vid})" if vid and str(vid) != str(name) else str(name)
    detail = _detail_sentence(i)
    if i.get("incident_type") == "NEW":
        return dict(
            subject=f"backup of {label}",
            problem=f"New backup noticed: {label}",
            why="This machine's backups aren't on RackMarshal's expected list yet.",
            todo="If you added this backup on purpose, nothing is wrong; add it to the backup baseline. " + s["help"],
            severity="info",
        )
    return dict(
        subject=f"backup of {label}",
        problem=f"Backup issue: {label}",
        why="Only this machine's backup is affected." + (" " + detail if detail else ""),
        todo="This usually clears after the next backup or verify run. " + s["help"],
    )


def _t_host_verify(i, s):
    key = i.get("resource_key") or ""
    if key == "pbs-secondary-coverage":
        guests = [
            field.split(":", 1)[1]
            for field, _e, _a in _diffs(i)
            if field.startswith("secondary_verification_metadata:")
        ]
        named = ", ".join(_guest_label(g) for g in guests[:3])
        if len(guests) > 3:
            named += f" and {len(guests) - 3} more"
        return dict(
            subject="second copy of server backups",
            problem="Second copy of server backups not verified"
            + (f" ({_plural(len(guests), 'machine')})" if guests else ""),
            why="The second backup datastore is missing its verification record"
            + (f" for {named}" if named else "")
            + ". Your main backups are fine; this is the backup of the backup.",
            todo="Usually nothing; it normally clears after the next verify run. " + s["help"],
        )
    if key == "pbs-native-weekly":
        return dict(
            subject="weekly backup verification",
            problem="Weekly backup verification is overdue or failed",
            why="The backups exist, but their regular integrity check hasn't confirmed them.",
            todo=s["help"],
        )
    name = i.get("display_name") or key or "host backup check"
    return dict(
        subject=name,
        problem=f"Backup check problem: {name}",
        why=_detail_sentence(i) or "A host backup check didn't pass.",
        todo=s["help"],
    )


def _t_rsync(i, s):
    unfinished = any(f == "finished" for f, _e, _a in _diffs(i)) or "INCOMPLETE" in str(
        i.get("actual_status") or ""
    )
    return dict(
        subject="file backup",
        problem="File backup hasn't finished" if unfinished else "File backup problem",
        why="The scheduled file copy "
        + ("is still running or stopped early." if unfinished else "reported a problem."),
        todo="It often clears when the run finishes. " + s["help"],
    )


def _t_pve_guest(i, s):
    kind = "VM" if i.get("resource_type") == "qemu" else "container"
    name = i.get("display_name") or ""
    vid = i.get("resource_key")
    label = f"{name} ({vid})" if name else f"{kind} {vid}"
    if i.get("incident_type") == "NEW":
        return dict(
            subject=f"new {kind} {label}",
            problem=f"New {kind} noticed: {label}",
            why="It isn't on RackMarshal's list of expected machines yet.",
            todo="If you created it on purpose, nothing is wrong; add it to the Proxmox baseline. "
            "If it's a leftover, remove it.",
            severity="info",
        )
    actual = i.get("actual_status")
    expected = i.get("expected_status")
    if str(actual or "").strip().lower() == "unknown":
        problem = f"Status of {kind} {label} can't be read (should be {expected})"
        why = "RackMarshal couldn't read its status from Proxmox. It may be fine, or Proxmox may be unreachable."
        todo = "Check the Proxmox web page. " + s["help"]
    elif i.get("incident_type") == "MISSING" or _missing(actual):
        problem = f"{_sentence(kind)} {label} has disappeared from Proxmox"
        why = "RackMarshal expected it to exist" + (
            f" ({expected})." if not _missing(expected) else "."
        )
        todo = "If you deleted it on purpose, retire its baseline. Otherwise check Proxmox. " + s["help"]
    else:
        problem = f"{_sentence(kind)} {label} is {actual} (should be {expected})"
        why = f"Whatever runs on {name or label} may be unavailable."
        todo = (
            "Start it in Proxmox if it should be running. " + s["help"]
            if str(expected).lower() == "running"
            else s["help"]
        )
    return dict(subject=f"{kind} {label}", problem=problem, why=why, todo=todo)


def _t_node(i, s):
    name = i.get("display_name") or i.get("resource_key")
    actual = i.get("actual_status")
    state = "can't be reached" if _missing(actual) else f"is {actual}"
    return dict(
        subject=f"server {name}",
        problem=f"Server {name} {state} (should be {i.get('expected_status')})",
        why="RackMarshal can't confirm the Proxmox host is healthy. Everything on it could be affected.",
        todo=f"Check that {name} is on and its Proxmox web page loads. " + s["help"],
        severity="urgent",
    )


def _t_storage(i, s):
    name = i.get("display_name") or i.get("resource_key")
    actual = i.get("actual_status")
    state = "can't be reached" if _missing(actual) else f"is {actual}"
    return dict(
        subject=f"storage '{name}'",
        problem=f"Storage '{name}' {state} (should be {i.get('expected_status')})",
        why="Anything that saves to this storage, such as backups, may fail.",
        todo=s["help"],
    )


def _t_zfs(i, s):
    rtype = i.get("resource_type") or ""
    name = i.get("display_name") or i.get("resource_key")
    key = str(i.get("resource_key") or "")
    pool = key.split("/", 1)[0] if "/" in key else None
    what = "Storage pool" if rtype == "zfs_pool" else "Storage device"
    label = f"{name} (pool {pool})" if pool and rtype != "zfs_pool" else str(name)
    if i.get("incident_type") == "NEW":
        return dict(
            subject=f"{what.lower()} {label}",
            problem=f"New {what.lower()} noticed: {label}",
            why="It isn't on RackMarshal's expected list yet.",
            todo="This is expected after a storage change; add it to the ZFS baseline. " + s["help"],
            severity="info",
        )
    actual = i.get("actual_status")
    expected = i.get("expected_status")
    if i.get("incident_type") == "MISSING" or _missing(actual):
        problem = f"{what} {label} is missing"
    else:
        problem = f"{what} {label} is {_state(actual)}" + (
            f" (should be {_state(expected)})" if not _missing(expected) else ""
        )
    detail = _detail_sentence(i)
    return dict(
        subject=f"{what.lower()} {label}",
        problem=problem,
        why="Data on this storage may be at risk or unavailable." + (" " + detail if detail else ""),
        todo="Get it checked right away. Don't unplug drives or restart until it has been looked at. "
        + s["help"],
        severity="urgent",
    )


def _t_mount(i, s):
    mountpoint = i.get("mountpoint") or i.get("display_name")
    where = i.get("guest_id") or "the host"
    source = (i.get("detail") or {}).get("expected_source") or ""
    return dict(
        subject=f"shared folder {mountpoint} on {where}",
        problem=f"Shared folder {mountpoint} on {where} isn't reachable",
        why="Anything that reads or writes there may fail." + (f" Source: {source}." if source else ""),
        todo="Check that the file server is on and reachable. " + s["help"],
    )


def _t_home_assistant(i, s):
    name = i.get("display_name") or "Home Assistant"
    actual = str(i.get("actual_status") or "down").replace("_", " ").lower()
    return dict(
        subject=name,
        problem=f"{name} is {actual}",
        why="Automations and notifications may not work.",
        todo="It usually restarts on its own. " + s["help"],
    )


_SELF_UNIT = re.compile(
    r"(?:@|rackmarshal-|homelabops-)([a-z][a-z\-]*?)(?:-cycle)?\.(?:service|timer)"
)


def _self_domain(incident):
    detail = incident.get("detail") or {}
    raw = str(detail.get("unit") or incident.get("resource_key") or "")
    match = re.search(r"freshness:([A-Za-z\-]+)", raw)
    if match:
        key = match.group(1).lower()
    else:
        match = _SELF_UNIT.search(raw)
        key = match.group(1) if match else ""
    return _DOMAIN_NAMES.get(key, key or "monitoring")


def _t_self(i, s):
    domain = _self_domain(i)
    itype = str(i.get("incident_type") or "")
    if itype.startswith("FRESHNESS"):
        problem = f"RackMarshal's {domain} data is out of date"
    elif itype == "UNIT_INACTIVE":
        problem = f"RackMarshal's {domain} check isn't scheduled"
    else:
        problem = f"RackMarshal's {domain} check failed to run"
    return dict(
        subject=f"RackMarshal's {domain} check",
        problem=problem,
        why=f"Monitoring of {domain} is paused until it runs again. Nothing else is known to be wrong.",
        todo="It usually recovers on the next run, within a few minutes. " + s["help"],
    )


def _t_generic(i, s):
    name = i.get("display_name") or i.get("resource_key") or "a monitored item"
    detail = _detail_sentence(i)
    if not detail and not _missing(i.get("actual_status")):
        detail = f"It's {i.get('actual_status')}" + (
            f" (expected {i.get('expected_status')})." if not _missing(i.get("expected_status")) else "."
        )
    return dict(
        subject=str(name),
        problem=f"Problem detected: {name}",
        why=detail or "Something changed from what RackMarshal expects.",
        todo=s["help"],
    )


TEMPLATES = {
    "backup_phone": _t_phone,
    "backup_timemachine": _t_timemachine,
    "backup_messages": _t_messages,
    "backup_guest": _t_guest_backup,
    "backup_host_verify": _t_host_verify,
    "backup_rsync_filebackups": _t_rsync,
    "lxc": _t_pve_guest,
    "qemu": _t_pve_guest,
    "node": _t_node,
    "storage": _t_storage,
    "zfs_pool": _t_zfs,
    "zfs_vdev": _t_zfs,
    "mount": _t_mount,
    "rackmarshal_self": _t_self,
    "homelabops_self": _t_self,
}


def _template(incident, settings):
    rtype = str(incident.get("resource_type") or "")
    fn = TEMPLATES.get(rtype)
    if fn is None and rtype.startswith("ha"):
        fn = _t_home_assistant
    return (fn or _t_generic)(incident, settings)


# ------------------------------------------------------------------ public


def render(packet, notification_type, settings=None):
    """Return (title, message) in plain language. May raise on bad input."""
    s = _settings(settings)
    incident = packet["incident"]
    ref = f"RackMarshal {packet.get('source_domain') or ''} #{packet.get('incident_id')}"
    t = _template(incident, s)
    problem = _sentence(t["problem"])

    if notification_type == "OPENED":
        severity = t.get("severity")
        if severity is None and incident.get("severity") == "critical" and not str(
            incident.get("resource_type") or ""
        ).endswith("_self"):
            severity = "urgent"
        icon = {"urgent": "🔴", "info": "ℹ️"}.get(severity, "⚠️")
        since = _local(incident.get("opened_at"), s)
        lines = [
            f"**What's wrong:** {problem}.",
            f"**Does it matter?** {_sentence(t['why'])}",
            f"**What to do:** {_sentence(t['todo'])}",
            f"_{ref} · since {since}_" if since else f"_{ref}_",
        ]
        return f"{icon} {problem}", "\n\n".join(lines)

    if notification_type == "RECOVERED":
        recovered_at = (packet.get("recovery") or {}).get("recovered_at")
        body = f"Earlier alert: {problem}."
        lasted = _duration(incident.get("opened_at"), recovered_at)
        if lasted:
            body += f" It lasted about {lasted}."
        cleared = _local(recovered_at, s)
        lines = [
            body,
            "Nothing to do.",
            f"_{ref} · cleared {cleared}_" if cleared else f"_{ref}_",
        ]
        return f"✅ Back to normal: {_sentence(t['subject'])}", "\n\n".join(lines)

    raise ValueError(f"unsupported notification type {notification_type!r}")


def render_safe(packet, notification_type, title, message, settings=None):
    """Plain-language text, or the given classic title/message.

    Returns the classic text when NOTIFY_STYLE=classic or on any error, so
    wording can never stop a notification from being delivered.
    """
    s = _settings(settings)
    if s.get("style") == STYLE_CLASSIC:
        return title, message
    try:
        new_title, new_message = render(packet, notification_type, s)
    except Exception:
        return title, message
    if not new_title or not new_message:
        return title, message
    return new_title[:250], new_message
