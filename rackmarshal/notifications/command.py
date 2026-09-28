"""Command construction shared by RackMarshal notification-producing cycles."""
from __future__ import annotations

from os import PathLike


def build_delivery_command(worker_cmd, db, credential, explainer, prefix="rackmarshal"):
    """Return a flat argv list for the notification delivery worker.

    The delivery worker's ``--explainer`` option is a single executable path,
    not a nested module argv list. Reject nested/list values here so this
    interface cannot silently regress during package reorganization.
    """
    worker = [str(x) for x in worker_cmd]
    if not worker:
        raise ValueError("notification delivery worker command is empty")
    if isinstance(explainer, (list, tuple)):
        raise TypeError("explainer must be one executable path, not an argv list")
    if not isinstance(explainer, (str, PathLike)):
        raise TypeError("explainer must be a string or path-like executable")
    return worker + [
        "--db", str(db),
        "--credential", str(credential),
        "--explainer", str(explainer),
        "--notification-prefix", str(prefix),
    ]
