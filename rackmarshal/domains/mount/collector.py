#!/usr/bin/env python3
"""RackMarshal MOUNT collector (Step M4 / M4.2).

Collects expected mounts from mounts.catalog.toml and compares:
  - LXC bind mounts via PVE API (mp*)
  - Host CIFS / export-meta via MOUNT_SSH_* observer
  - QEMU NFS via PVE guest-agent findmnt (needs VM.GuestAgent.Unrestricted)

Writes one row to mount_observations unless --dry-run.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import ssl
import subprocess
import time
import tomllib
import urllib.parse
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from rackmarshal.domains.pve.collector import api_get, load_config
from rackmarshal.core.config import pve_api_env, pve_ca_file

COLLECTOR_SCHEMA = 1

def apply_conf_env() -> None:
    """Populate MOUNT_SSH_* from rackmarshal.conf when not already in environ."""
    conf = Path("/etc/rackmarshal/rackmarshal.conf")
    if not conf.is_file():
        return
    keys = (
        "MOUNT_SSH_HOST",
        "MOUNT_SSH_USER",
        "MOUNT_SSH_KEY",
        "MOUNT_KNOWN_HOSTS",
        "MOUNT_CATALOG_FILE",
    )
    for line in conf.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip()
        if k in keys and k not in os.environ:
            os.environ[k] = v


DEFAULT_CATALOG = Path("/opt/rackmarshal/packaging/mounts.catalog.toml")
LIVE_CATALOG = Path("/etc/rackmarshal/mounts.catalog.toml")
DEFAULT_DB = Path("/var/lib/rackmarshal/state.db")
PVE_NODE = os.environ.get("PVE_NODE", "")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def resolve_catalog() -> Path:
    env = os.environ.get("MOUNT_CATALOG_FILE")
    if env:
        return Path(env)
    if LIVE_CATALOG.is_file():
        return LIVE_CATALOG
    return DEFAULT_CATALOG


def load_catalog(path: Path) -> dict:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    if int(data.get("schema_version", 0)) < 1:
        raise RuntimeError(f"catalog schema_version missing/invalid: {path}")
    return data


def parse_mp_value(raw: str) -> dict:
    """Parse PVE mp value like '/srv/example,mp=/srv/example,ro=1'."""
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    host_path = parts[0] if parts else ""
    guest_mp = None
    readonly = False
    for p in parts[1:]:
        if p.startswith("mp="):
            guest_mp = p[3:]
        elif p == "ro=1" or p == "ro":
            readonly = True
    return {
        "host_path": host_path,
        "guest_mp": guest_mp or host_path,
        "readonly": readonly,
        "raw": raw,
    }


def fetch_lxc_mps(config: dict, vmid: str) -> dict[str, dict]:
    data = api_get(config, f"/nodes/{PVE_NODE}/lxc/{vmid}/config")
    out = {}
    for key, val in data.items():
        if not str(key).startswith("mp"):
            continue
        parsed = parse_mp_value(str(val))
        out[str(key)] = parsed
        out[parsed["guest_mp"]] = parsed  # also index by guest path
    return out


def api_request(config: dict, method: str, endpoint: str, form=None) -> dict:
    """PVE API GET/POST; returns decoded JSON body (includes data/message)."""
    url = config["PVE_API_URL"].rstrip("/") + endpoint
    headers = {
        "Authorization": (
            "PVEAPIToken="
            + config["PVE_TOKEN_ID"]
            + "="
            + config["PVE_TOKEN_SECRET"]
        ),
        "Accept": "application/json",
        "User-Agent": "RackMarshal/1.0",
    }
    body = None
    if form is not None:
        body = urllib.parse.urlencode(form, doseq=True).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    context = ssl.create_default_context(cafile=str(pve_ca_file()))
    try:
        with urllib.request.urlopen(request, context=context, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode(errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"raw": raw}
        raise RuntimeError(
            f"PVE API HTTP {exc.code}: {payload.get('message') or payload}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"PVE API connection error: {exc.reason}") from exc


def flatten_findmnt(tree: dict) -> dict[str, dict]:
    """Map mount target -> findmnt node from findmnt -J output."""
    out: dict[str, dict] = {}

    def walk(nodes):
        for n in nodes or []:
            target = n.get("target")
            if target:
                out[target] = n
            walk(n.get("children") or [])

    walk((tree or {}).get("filesystems") or [])
    return out


def fetch_qemu_findmnt(config: dict, vmid: str, timeout_s: float = 25.0) -> dict:
    """Run findmnt -J via QGA; return {targets: {...}} or {_error: ...}."""
    try:
        started = api_request(
            config,
            "POST",
            f"/nodes/{PVE_NODE}/qemu/{vmid}/agent/exec",
            form=[("command", "findmnt"), ("command", "-J")],
        )
    except Exception as exc:  # noqa: BLE001
        return {"_error": str(exc)}
    pid = (started.get("data") or {}).get("pid")
    if pid is None:
        return {"_error": f"no_pid:{started}"}
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        try:
            last = api_request(
                config,
                "GET",
                f"/nodes/{PVE_NODE}/qemu/{vmid}/agent/exec-status?pid={pid}",
            )
        except Exception as exc:  # noqa: BLE001
            return {"_error": str(exc)}
        data = last.get("data") or {}
        if data.get("exited"):
            ec = data.get("exitcode")
            if ec is None:
                exitcode = 1
            else:
                exitcode = int(ec)
            if exitcode != 0:
                err = (data.get("err-data") or "").strip()
                return {"_error": f"findmnt_exit={exitcode}:{err[:200]}"}
            raw = data.get("out-data") or ""
            try:
                tree = json.loads(raw)
            except json.JSONDecodeError as exc:
                return {"_error": f"findmnt_json:{exc}"}
            return {"targets": flatten_findmnt(tree)}
        time.sleep(0.25)
    return {"_error": "findmnt_timeout"}


def check_qemu_nfs(row: dict, qga_cache: dict[str, dict]) -> dict:
    vmid = str(row["guest_id"])
    snap = qga_cache.get(vmid)
    if snap is None:
        return {
            **base_result(row),
            "state": "guest_unreachable",
            "detail": "qga_cache_missing",
        }
    if snap.get("_error"):
        return {
            **base_result(row),
            "state": "guest_unreachable",
            "detail": snap["_error"],
        }
    targets = snap.get("targets") or {}
    mountpoint = row.get("mountpoint") or ""
    expected = row.get("expected_source") or ""
    hit = targets.get(mountpoint)
    if not hit:
        return {
            **base_result(row),
            "state": "missing",
            "observed_source": None,
            "detail": "not_in_qga_findmnt",
        }
    source = hit.get("source") or ""
    fstype = hit.get("fstype") or ""
    if expected and source and not sources_match(expected, source):
        return {
            **base_result(row),
            "state": "wrong_source",
            "observed_source": source,
            "fstype_observed": fstype,
        }
    # expect nfs/nfs4 for catalog nfs rows
    want = (row.get("fstype") or "").lower()
    if want.startswith("nfs") and fstype and not str(fstype).lower().startswith("nfs"):
        return {
            **base_result(row),
            "state": "wrong_source",
            "observed_source": source,
            "fstype_observed": fstype,
            "detail": f"fstype_mismatch want={want}",
        }
    return {
        **base_result(row),
        "state": "ok",
        "observed_source": source,
        "fstype_observed": fstype,
        "detail": "qga_findmnt",
    }


def mount_ssh_configured() -> bool:
    return bool(
        os.environ.get("MOUNT_SSH_HOST")
        and os.environ.get("MOUNT_SSH_USER")
        and os.environ.get("MOUNT_SSH_KEY")
    )


def fetch_host_snapshot() -> dict | None:
    """Call configured ForceCommand observer; returns parsed JSON or None."""
    if not mount_ssh_configured():
        return None
    host = os.environ["MOUNT_SSH_HOST"]
    user = os.environ["MOUNT_SSH_USER"]
    key = os.environ["MOUNT_SSH_KEY"]
    kh = os.environ.get(
        "MOUNT_KNOWN_HOSTS",
        os.environ.get("HARDWARE_KNOWN_HOSTS", "/etc/rackmarshal/ssh/known_hosts"),
    )
    # Prefer conf file if present
    conf_kh = Path("/etc/rackmarshal/rackmarshal.conf")
    if "MOUNT_KNOWN_HOSTS" not in os.environ and conf_kh.is_file():
        for line in conf_kh.read_text().splitlines():
            if line.startswith("MOUNT_KNOWN_HOSTS="):
                kh = line.split("=", 1)[1].strip()
            if line.startswith("MOUNT_SSH_HOST="):
                host = line.split("=", 1)[1].strip()
            if line.startswith("MOUNT_SSH_USER="):
                user = line.split("=", 1)[1].strip()
            if line.startswith("MOUNT_SSH_KEY="):
                key = line.split("=", 1)[1].strip()
    proc = subprocess.run(
        [
            "/usr/bin/ssh",
            "-i",
            key,
            "-o",
            "BatchMode=yes",
            "-o",
            f"UserKnownHostsFile={kh}",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "ConnectTimeout=10",
            f"{user}@{host}",
            "ignored",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    if proc.returncode != 0:
        return {
            "_error": f"ssh_exit={proc.returncode}:{proc.stderr.strip()}",
        }
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except json.JSONDecodeError as exc:
        return {"_error": f"bad_json:{exc}", "_raw": proc.stdout[:500]}


def check_host_cifs(row: dict, snap: dict | None) -> dict:
    mountpoint = row["mountpoint"]
    expected = row.get("expected_source", "")
    if snap is None:
        return {
            **base_result(row),
            "state": "skipped",
            "detail": "no_mount_observer_ssh",
        }
    if snap.get("_error"):
        return {
            **base_result(row),
            "state": "guest_unreachable",
            "detail": snap["_error"],
        }
    hit = None
    for m in snap.get("mounts") or []:
        if m.get("mountpoint") == mountpoint:
            hit = m
            break
    if not hit:
        return {
            **base_result(row),
            "state": "missing",
            "detail": "not_in_observer_snapshot",
        }
    source = hit.get("source") or ""
    fstype = hit.get("fstype") or ""
    # autofs only without real cifs underneath counts as missing/unreadable
    if not source or fstype == "autofs" or hit.get("readable") is False:
        if hit.get("unit_failed") == "failed" or hit.get("readable") is False or fstype == "autofs":
            return {
                **base_result(row),
                "state": "missing",
                "observed_source": source or None,
                "fstype_observed": fstype or None,
                "detail": (
                    f"active={hit.get('unit_active')} failed={hit.get('unit_failed')} "
                    f"readable={hit.get('readable')}"
                ),
            }
    if expected and source and not sources_match(expected, source):
        # CIFS source may be //host/share — compare
        if not sources_match(expected, source):
            return {
                **base_result(row),
                "state": "wrong_source",
                "observed_source": source,
                "fstype_observed": fstype,
            }
    if hit.get("unit_active") == "active" and fstype and fstype != "autofs":
        return {
            **base_result(row),
            "state": "ok",
            "observed_source": source,
            "fstype_observed": fstype,
            "detail": f"readable={hit.get('readable')}",
        }
    # fallback: source looks like cifs share
    if source.startswith("//") or fstype == "cifs":
        return {
            **base_result(row),
            "state": "ok",
            "observed_source": source,
            "fstype_observed": fstype,
        }
    return {
        **base_result(row),
        "state": "missing",
        "observed_source": source or None,
        "detail": f"active={hit.get('unit_active')} fstype={fstype}",
    }


def sources_match(expected: str, observed: str) -> bool:
    e = expected.rstrip("/")
    o = observed.rstrip("/")
    if e == o:
        return True
    # CIFS sometimes shows //host/share vs //host/share
    return e.lower() == o.lower()


def base_result(row: dict) -> dict:
    return {
        "id": row["id"],
        "guest_kind": row.get("guest_kind"),
        "guest_id": str(row.get("guest_id", "")),
        "name": row.get("name"),
        "mountpoint": row.get("mountpoint") or "",
        "expected_source": row.get("expected_source"),
        "fstype": row.get("fstype"),
        "severity_missing": row.get("severity_missing", "warning"),
        "optional": bool(row.get("optional", False)),
    }


def check_lxc_bind(row: dict, mp_cache: dict[str, dict[str, dict]]) -> dict:
    vmid = str(row["guest_id"])
    mps = mp_cache.get(vmid)
    if mps is None:
        return {
            **base_result(row),
            "state": "guest_unreachable",
            "detail": "lxc_config_fetch_failed",
        }
    mp_key = row.get("mp_key")
    guest_mp = row.get("mountpoint")
    expected_host = row.get("expected_source")
    hit = None
    if mp_key and mp_key in mps:
        hit = mps[mp_key]
    elif guest_mp and guest_mp in mps:
        hit = mps[guest_mp]
    else:
        # search by guest path
        for parsed in mps.values():
            if isinstance(parsed, dict) and parsed.get("guest_mp") == guest_mp:
                hit = parsed
                break
    if not hit:
        return {
            **base_result(row),
            "state": "missing",
            "observed_source": None,
            "detail": "mp_not_in_pve_config",
        }
    observed_host = hit.get("host_path")
    if expected_host and observed_host and not sources_match(expected_host, observed_host):
        return {
            **base_result(row),
            "state": "wrong_source",
            "observed_source": observed_host,
            "detail": f"pve_mp={hit.get('raw')}",
        }
    # also verify guest mountpoint matches catalog
    if guest_mp and hit.get("guest_mp") and hit["guest_mp"] != guest_mp:
        return {
            **base_result(row),
            "state": "wrong_source",
            "observed_source": observed_host,
            "detail": f"guest_mp_mismatch have={hit.get('guest_mp')}",
        }
    return {
        **base_result(row),
        "state": "ok",
        "observed_source": observed_host,
        "detail": f"pve_mp={hit.get('raw')}",
    }


def check_export_stale(row: dict, snap: dict | None) -> dict:
    if snap is None:
        return {
            **base_result(row),
            "state": "skipped",
            "detail": "no_mount_observer_ssh",
        }
    if snap.get("_error"):
        return {
            **base_result(row),
            "state": "guest_unreachable",
            "detail": snap["_error"],
        }
    client = (row.get("expected_source") or "").replace("export-client:", "")
    clients = snap.get("exports_clients") or []
    present = client in clients
    if present:
        return {
            **base_result(row),
            "state": "export_stale",
            "observed_source": f"export-client:{client}",
            "detail": "client_still_in_exports",
        }
    return {
        **base_result(row),
        "state": "ok",
        "observed_source": None,
        "detail": "stale_client_absent",
    }


def evaluate(catalog: dict, pve_config: dict) -> list[dict]:
    results: list[dict] = []
    mounts = catalog.get("mounts") or []
    host_snap = fetch_host_snapshot() if mount_ssh_configured() else None
    lxc_ids = sorted(
        {
            str(m["guest_id"])
            for m in mounts
            if m.get("guest_kind") == "lxc" and m.get("fstype") == "bind"
        }
    )
    mp_cache: dict[str, dict[str, dict]] = {}
    for vmid in lxc_ids:
        try:
            mp_cache[vmid] = fetch_lxc_mps(pve_config, vmid)
        except Exception as exc:  # noqa: BLE001 — record per-guest failure
            mp_cache[vmid] = None  # type: ignore[assignment]
            # stash error on a synthetic note via empty dict marker
            mp_cache[f"err:{vmid}"] = {"error": str(exc)}  # type: ignore[assignment]

    qemu_ids = sorted(
        {
            str(m["guest_id"])
            for m in mounts
            if m.get("guest_kind") == "qemu"
            and (m.get("runtime") in (None, "qga_or_ssh", "qga") or m.get("fstype") == "nfs")
        }
    )
    qga_cache: dict[str, dict] = {}
    for vmid in qemu_ids:
        qga_cache[vmid] = fetch_qemu_findmnt(pve_config, vmid)

    for row in mounts:
        kind = row.get("guest_kind")
        fstype = row.get("fstype")
        check = row.get("check")
        if check == "stale_export_client" or fstype == "nfs-export-meta":
            results.append(check_export_stale(row, host_snap))
            continue
        if kind == "lxc" and fstype == "bind":
            vmid = str(row["guest_id"])
            if mp_cache.get(vmid) is None and f"err:{vmid}" in mp_cache:
                results.append(
                    {
                        **base_result(row),
                        "state": "guest_unreachable",
                        "detail": mp_cache[f"err:{vmid}"].get("error"),
                    }
                )
            else:
                results.append(check_lxc_bind(row, mp_cache))
            continue
        if kind == "host" and fstype == "cifs":
            results.append(check_host_cifs(row, host_snap))
            continue
        if kind == "qemu":
            results.append(check_qemu_nfs(row, qga_cache))
            continue
        results.append(
            {
                **base_result(row),
                "state": "skipped",
                "detail": f"unsupported_kind={kind}/{fstype}",
            }
        )
    return results


def summarize(results: list[dict]) -> dict:
    checked = len(results)
    ok = sum(1 for r in results if r.get("state") == "ok")
    skipped = sum(1 for r in results if r.get("state") == "skipped")
    problems = [
        r
        for r in results
        if r.get("state")
        in ("missing", "wrong_source", "unreadable", "export_stale", "guest_unreachable")
        and not r.get("optional")
    ]
    return {
        "checked": checked,
        "ok": ok,
        "skipped": skipped,
        "problem_count": len(problems),
        "problems": problems,
    }


def write_observation(db_path: Path, payload: dict, summary: dict) -> int:
    con = sqlite3.connect(str(db_path))
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO mount_observations (
            observed_at, source, schema_version, catalog_version,
            checked_count, ok_count, problem_count, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload["observed_at"],
            payload["source"],
            COLLECTOR_SCHEMA,
            payload.get("catalog_version"),
            summary["checked"],
            summary["ok"],
            summary["problem_count"],
            json.dumps(payload, separators=(",", ":"), sort_keys=True),
        ),
    )
    oid = cur.lastrowid
    con.commit()
    con.close()
    return int(oid)


def main() -> int:
    parser = argparse.ArgumentParser(description="RackMarshal MOUNT collector (M4.2)")
    parser.add_argument("--dry-run", action="store_true", help="Do not write state.db")
    parser.add_argument("--catalog", type=Path, default=None)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--json", action="store_true", help="Print full JSON payload")
    args = parser.parse_args()

    apply_conf_env()
    catalog_path = args.catalog or resolve_catalog()
    catalog = load_catalog(catalog_path)
    pve_config = load_config(Path(str(pve_api_env())))
    # silence unused import side effect of CA path resolve
    _ = pve_ca_file()

    observed_at = utc_now()
    results = evaluate(catalog, pve_config)
    summary = summarize(results)
    payload = {
        "collector": "mount_catalog",
        "schema_version": COLLECTOR_SCHEMA,
        "observed_at": observed_at,
        "source": "rackmarshal-mount-m4.2",
        "catalog_path": str(catalog_path),
        "catalog_version": str(catalog.get("updated") or catalog.get("schema_version")),
        "mount_ssh_configured": mount_ssh_configured(),
        "summary": {
            "checked": summary["checked"],
            "ok": summary["ok"],
            "skipped": summary["skipped"],
            "problem_count": summary["problem_count"],
        },
        "results": results,
    }

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(
            f"MOUNT collect {observed_at}: checked={summary['checked']} "
            f"ok={summary['ok']} skipped={summary['skipped']} "
            f"problems={summary['problem_count']} "
            f"mount_ssh={mount_ssh_configured()}"
        )
        for p in summary["problems"]:
            print(
                f"  PROBLEM {p.get('state')}: {p.get('id')} "
                f"({p.get('detail')})"
            )
        for r in results:
            if r.get("state") == "skipped":
                print(f"  skip {r.get('id')}: {r.get('detail')}")

    if args.dry_run:
        print("dry-run: no DB write")
        return 0 if summary["problem_count"] == 0 else 1

    oid = write_observation(args.db, payload, summary)
    print(f"wrote mount_observations id={oid}")
    return 0 if summary["problem_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
