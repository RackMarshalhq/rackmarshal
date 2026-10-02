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


def incident_brief(summary, timeline):
    """Explain existing sanitized records without inferring causes or recovery."""
    from datetime import datetime
    items = timeline.get("items") or []
    opening = next((x for x in items if x.get("kind") == "INCIDENT_OPENED"), None)
    abnormal = next((x for x in reversed(items) if x.get("kind") == "LAST_ABNORMAL"), None)
    recovery = next((x for x in items if x.get("kind") == "INCIDENT_RECOVERED"), None)
    conflicts = []
    gaps = []
    state = summary.get("state")
    recovered_at = summary.get("recovered_at")
    if state == "OPEN" and (recovered_at or recovery):
        conflicts.append("OPEN state conflicts with a recorded recovery timestamp or timeline entry.")
    if state not in ("OPEN", "RECOVERED"):
        conflicts.append("The recorded lifecycle state is not recognized.")
    def parsed(value):
        try:
            d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return d if d.tzinfo is not None else None
        except (ValueError, TypeError):
            return None
    dates = {key: parsed(summary.get(key)) for key in ("opened_at", "last_abnormal_at", "recovered_at")}
    for key, item in (("opened_at", opening), ("last_abnormal_at", abnormal), ("recovered_at", recovery)):
        entry_time = parsed((item or {}).get("timestamp"))
        if dates[key] is not None and entry_time is not None and dates[key] != entry_time:
            conflicts.append("Incident and timeline timestamps disagree for " + key + ".")
    for earlier, later in (("opened_at", "last_abnormal_at"), ("opened_at", "recovered_at"), ("last_abnormal_at", "recovered_at")):
        if dates[earlier] is not None and dates[later] is not None and dates[later] < dates[earlier]:
            conflicts.append("Lifecycle timestamps are out of order: " + later + " precedes " + earlier + ".")
    for key, label in (("opened_at", "Opening"), ("last_abnormal_at", "Last abnormal")):
        if not summary.get(key):
            gaps.append(label + " time is not recorded.")
        elif dates[key] is None:
            gaps.append(label + " timestamp cannot establish ordering without a valid timezone.")
    if not (opening or {}).get("changes"):
        gaps.append("The opening condition is not present in the returned timeline.")
    if not (abnormal or {}).get("changes"):
        gaps.append("The latest abnormal condition is not present in the returned timeline; the opening condition is not substituted.")
    refs = list(dict.fromkeys(ref for item in items for ref in (item.get("evidence_refs") or [])))
    if not refs:
        gaps.append("No supporting evidence references are present in the returned timeline.")
    if state == "RECOVERED":
        if not recovered_at:
            gaps.append("The ledger is marked RECOVERED but a recovery time is not recorded.")
        elif dates["recovered_at"] is None:
            gaps.append("Recovery timestamp cannot establish ordering without a valid timezone.")
        if not recovery or not recovery.get("evidence_refs"):
            gaps.append("Recovery supporting references are not present in the returned timeline.")
    if conflicts:
        state_statement = "Conflicting lifecycle records require review; no consistent recovery conclusion is presented."
        recovery_statement = "Recovery interpretation is withheld because the lifecycle records conflict."
    elif state == "RECOVERED":
        state_statement = state_sentence(summary)
        recovery_statement = "The ledger records recovery. Historical recovery does not establish current resource health." if recovered_at else "Marked RECOVERED, but no recovery timestamp is recorded. Recovery evidence is incomplete."
    elif state == "OPEN":
        state_statement = state_sentence(summary)
        recovery_statement = "No recovery is recorded for this OPEN incident."
    else:
        state_statement = "Lifecycle state is not recognized."
        recovery_statement = "Recovery cannot be interpreted from an unrecognized lifecycle state."
    return {"authority": "DERIVED", "state_statement": state_statement,
            "recovery_statement": recovery_statement, "opening": opening,
            "last_abnormal": abnormal, "recovery": recovery,
            "evidence_refs": refs, "conflicts": conflicts, "gaps": gaps,
            "unknowns": ["Recorded triggering conditions do not establish root cause.",
                "This incident history does not establish current resource health.",
                "Evidence references identify records; their presence does not guarantee availability or expose full observation payloads."]}
