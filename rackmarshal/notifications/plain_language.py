"""Plain-language wording for alerts: what happened, does it matter, what to do.

Deterministic text from fixed templates. It reads only fields already in the
notification packet; it never guesses a cause and never claims current health.
"""

RESOURCE_WORDS = {
    "lxc": "container", "qemu": "virtual machine", "storage": "storage", "node": "Proxmox server",
    "backup_job": "backup job", "backup_guest": "backed-up guest", "backup_scheduled_run": "scheduled backup run",
    "backup_host_verify": "backup check", "zfs_pool": "ZFS pool", "zfs_vdev": "ZFS drive group",
}

DOMAIN_WORDS = {
    "PVE": "Proxmox", "ZFS": "ZFS storage", "BACKUP": "backups", "HA": "Home Assistant",
    "HARDWARE": "hardware", "MOUNT": "a network mount", "SELF": "RackMarshal itself",
}

# Backup checks that deserve their own sentence, keyed by resource_key.
BACKUP_CHECKS = {
    "pbs-secondary-coverage": (
        "The second copy of your backups is missing a recent backup or has not been verified.",
        "Your main backups may be fine; this is about the extra copy on the second datastore. "
        "It often clears by itself while the second copy finishes verifying.",
        "Check again later today. If it is still open tomorrow, look at the second datastore's "
        "latest sync and verify tasks."),
    "pbs-secondary-capacity": (
        "The second backup datastore is running low on space.",
        "Matters soon: when it fills, the extra copy stops updating.",
        "Free space or add capacity on the second datastore."),
}


def _name(incident):
    return incident.get("display_name") or incident.get("resource_key") or "an unnamed item"


def _kind(incident):
    return RESOURCE_WORDS.get(incident.get("resource_type"), "item")


def _retire_hint(incident):
    if incident.get("resource_type") in ("lxc", "qemu") and str(incident.get("resource_key", "")).isdecimal():
        return " If you deleted it on purpose, run: rackmarshal retire-guest %s" % incident["resource_key"]
    return ""


def opened_lines(domain, incident):
    """Return (what_happened, does_it_matter, what_to_do) for an opened incident."""
    if domain == "BACKUP" and incident.get("resource_key") in BACKUP_CHECKS:
        return BACKUP_CHECKS[incident["resource_key"]]
    name, kind = _name(incident), _kind(incident)
    kind_type = incident.get("incident_type")
    area = DOMAIN_WORDS.get(domain, "your homelab")
    if kind_type == "NEW":
        return (
            "RackMarshal found a %s it was not told about: %s." % (kind, name),
            "Usually harmless if you added it on purpose. It does not mean anything is broken.",
            "If you added it, you can leave it or add it to what RackMarshal watches. "
            "If you did not add it, find out what created it.")
    if kind_type == "MISSING":
        return (
            "RackMarshal expected the %s %s but could not find it." % (kind, name),
            "Expected if you deleted it on purpose. Otherwise something in %s may be gone or unreachable." % area,
            "Check that it still exists and is reachable." + _retire_hint(incident))
    if kind_type == "STATUS-CHANGED":
        expected, actual = incident.get("expected_status"), incident.get("actual_status")
        detail = " It is %s; normal is %s." % (actual, expected) if expected and actual else ""
        return (
            "The %s %s is not in its normal state.%s" % (kind, name, detail),
            "It matters if you did not change it on purpose, since something in %s may need attention." % area,
            "Check it. If the new state is intended, tell RackMarshal it is the new normal.")
    return (
        "RackMarshal noticed a problem with %s in %s." % (name, area),
        "RackMarshal cannot tell from this alert alone how serious it is.",
        "Open the status page for the recorded details.")


def opened_text(domain, incident, details):
    what, matter, todo = opened_lines(domain, incident)
    return "\n".join(("What happened: " + what, "Does it matter: " + matter, "What to do: " + todo,
                      "", "Technical details: " + details))


def recovery_text(domain, incident, details):
    if domain == "BACKUP" and incident.get("resource_key") in BACKUP_CHECKS:
        what = "The check '%s' is back to normal." % incident["resource_key"]
    else:
        what = "%s (%s) is back to normal." % (_name(incident), _kind(incident))
    return "\n".join(("What happened: " + what, "What to do: Nothing. RackMarshal's latest check found it normal; "
                      "this does not prove it stays that way.", "", "Technical details: " + details))
