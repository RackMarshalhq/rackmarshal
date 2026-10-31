"""First-run starting marker for the incident processors that need one.

The Proxmox and backup incident processors handle observations strictly in
order, so each needs a checkpoint row ("count from here"). On an installation
that has never processed anything, the first run creates that row itself.

Rules:
* Only when the processing ledger is completely empty.
* If an earlier observation of the same kind exists (for example one carried
  over from an older site), the marker goes at the newest earlier one, so the
  observation being processed is next in line and is processed normally: a
  difference from the baseline opens an incident straight away.
* If there is no earlier observation there is nothing to mark.
* If the ledger is empty but incidents already exist, something is wrong (a
  restored or damaged database). Refuse; the operator decides.
The table names below are fixed constants chosen by the callers, never input.
"""
import sys

_DOMAINS = {
    "pve": ("incident_processing", "resource_incidents", "pve_cluster_resources"),
    "backup": ("backup_incident_processing", "backup_incidents", "backup_domain"),
}


class StartMarkerRefused(Exception):
    pass


def resolve_checkpoint(conn, domain, observation_id, apply):
    """Checkpoint to use when the ledger is empty; None when the ledger is not empty.

    With apply=True and an earlier observation present, the BOOTSTRAP row is
    written inside the caller's open transaction.
    """
    ledger, incidents, collector = _DOMAINS[domain]
    if conn.execute("SELECT 1 FROM %s LIMIT 1" % ledger).fetchone() is not None:
        return None
    if conn.execute("SELECT 1 FROM %s LIMIT 1" % incidents).fetchone() is not None:
        raise StartMarkerRefused(
            "processing ledger is empty but incidents exist; refusing to create a "
            "starting marker automatically (restored or damaged database?)"
        )
    row = conn.execute(
        "SELECT MAX(id) FROM observations WHERE collector = ? AND id < ?",
        (collector, observation_id),
    ).fetchone()
    prior = row[0]
    if prior is None:
        return 0
    if apply:
        conn.execute(
            "INSERT INTO %s (observation_id, processing_kind, differences_detected, "
            "incidents_opened, incidents_ongoing, incidents_recovered, note) "
            "VALUES (?, 'BOOTSTRAP', 0, 0, 0, 0, ?)" % ledger,
            (prior, "First run: starting marker created automatically"),
        )
        print(
            "first run: %s starting marker created at observation %d" % (domain, prior),
            file=sys.stderr,
        )
    return prior
