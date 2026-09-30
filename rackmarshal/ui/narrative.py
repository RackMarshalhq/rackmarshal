"""Deterministic presentation helpers; no clock, network, or model access."""
import html

DOMAIN_NAMES = {
    "PVE": "Proxmox resources", "ZFS": "ZFS storage", "BACKUP": "Backup coverage",
    "HA": "Home Assistant", "HARDWARE": "Hardware", "MOUNT": "Filesystem mounts",
}

def domain_name(domain):
    return DOMAIN_NAMES.get(domain, "Domain context not recorded")

def timestamp(value):
    if not value:
        return "<span class='muted'>Not recorded</span>"
    safe=html.escape(str(value), quote=True)
    return f'<time datetime="{safe}">{safe}</time>'

def occurrences(value):
    if value is None:
        return "Occurrence count not recorded"
    return f"{value} recorded abnormal occurrence" + ("" if value == 1 else "s")

def state_sentence(item):
    if item.get("state") == "OPEN":
        return "Open in the ledger. No recovery is recorded."
    if item.get("state") == "RECOVERED":
        if item.get("recovered_at"):
            return "Recovery recorded. Historical incident."
        return "Marked recovered; recovery time is not recorded."
    return "Lifecycle state is not recognized."
