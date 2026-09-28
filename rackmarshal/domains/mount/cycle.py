#!/usr/bin/env python3
"""RackMarshal MOUNT cycle (M5): collect → process incidents → enqueue → deliver."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from rackmarshal.core.config import (
    ha_credential_file,
    install_root,
    load_config,
    state_db,
    venv_python,
)

CONFIG = load_config()
DB = str(state_db(CONFIG))
_ROOT = install_root()
PYTHON = str(venv_python())

def module_cmd(name):
    return [str(PYTHON), "-m", name]

COLLECTOR = module_cmd("rackmarshal.domains.mount.collector")
PROCESSOR = module_cmd("rackmarshal.domains.mount.incidents")
ENQUEUER = module_cmd("rackmarshal.notifications.queue")
DELIVERY_WORKER = module_cmd("rackmarshal.notifications.delivery")
HA_CREDENTIAL = str(ha_credential_file())
INCIDENT_EXPLAINER = module_cmd("rackmarshal.incidents.explain")

# Deliver can hang on HA even with 0 pending rows; keep the cycle moving.
DELIVER_TIMEOUT_S = float(
    os.environ.get("MOUNT_DELIVER_TIMEOUT_S")
    or CONFIG.get("MOUNT_DELIVER_TIMEOUT_S")
    or "45"
)


def run(
    cmd: list[str],
    *,
    timeout: float | None = None,
) -> subprocess.CompletedProcess:
    print(f"$ {' '.join(cmd)}", flush=True)
    try:
        return subprocess.run(
            cmd,
            text=True,
            cwd=str(_ROOT),
            check=False,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else (
            exc.stdout.decode(errors="replace") if exc.stdout else ""
        )
        stderr = exc.stderr if isinstance(exc.stderr, str) else (
            exc.stderr.decode(errors="replace") if exc.stderr else ""
        )
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=124,
            stdout=stdout or "",
            stderr=(stderr or "") + f"\nTIMEOUT after {timeout}s\n",
        )


def emit(cp: subprocess.CompletedProcess) -> None:
    if cp.stdout:
        sys.stdout.write(cp.stdout)
        if not cp.stdout.endswith("\n"):
            sys.stdout.write("\n")
    if cp.stderr:
        sys.stderr.write(cp.stderr)
        if not cp.stderr.endswith("\n"):
            sys.stderr.write("\n")


def parse_json_blob(text: str) -> dict:
    text = (text or "").strip()
    if not text:
        raise ValueError("empty process output")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise
        return json.loads(text[start : end + 1])


def main() -> int:
    c = run(COLLECTOR, timeout=180)
    emit(c)
    # collect may exit 0/1 depending on skip/problem policy

    p = run(PROCESSOR + [ "--json"], timeout=60)
    emit(p)
    if p.returncode != 0:
        raise SystemExit(f"process_mount_incidents failed rc={p.returncode}")
    try:
        proc = parse_json_blob(p.stdout or "")
    except Exception as exc:
        raise SystemExit(f"process_mount_incidents JSON parse failed: {exc}") from exc

    e = run(ENQUEUER + [ "--db", DB], timeout=60)
    emit(e)
    if e.returncode != 0:
        raise SystemExit(f"enqueue failed rc={e.returncode}")

    d = run(
        DELIVERY_WORKER + [
            "--db",
            DB,
            "--credential",
            HA_CREDENTIAL,
            "--explainer",
            INCIDENT_EXPLAINER,
            "--notification-prefix",
            "rackmarshal",
        ],
        timeout=DELIVER_TIMEOUT_S,
    )
    emit(d)
    deliver_note = None
    if d.returncode == 124:
        deliver_note = f"timeout_{DELIVER_TIMEOUT_S}s"
        print(
            f"WARN: deliver timed out after {DELIVER_TIMEOUT_S}s (cycle continues)",
            flush=True,
        )
    elif d.returncode != 0:
        deliver_note = f"rc_{d.returncode}"
        print(f"WARN: deliver rc={d.returncode}", flush=True)

    out = {"status": "OK", "cycle": "mount", "process": proc}
    if deliver_note:
        out["deliver"] = deliver_note
    print(json.dumps(out, separators=(",", ":")), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
