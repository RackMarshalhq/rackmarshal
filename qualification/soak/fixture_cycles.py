"""Nine synthetic ZFS cycles run through the INSTALLED package.

This is the behavioural half of a sample: a disposable fixture database is
driven through healthy, degraded, persistent-error, unknown, replaced-pool and
recovered states with the real observation, comparator, event and incident
modules, and the answers are checked. Application code runs in a child process
whose audit hook refuses network, subprocess and any write outside the fixture
directory, so a sample cannot touch the real database or the network.
"""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess

from common import require, sha256

CHILD = r'''
import os, pathlib, runpy, sys
root = pathlib.Path(sys.argv[1]).resolve()
site = pathlib.Path(sys.argv[2]).resolve()
module = sys.argv[3]
sys.argv = sys.argv[3:]
sys.path.insert(0, str(site))
FIXTURE_DB = str(root / "fixture.db")


def inside(path):
    return pathlib.Path(path).resolve().is_relative_to(root)


def audit(event, args):
    if event.startswith(("socket.", "subprocess.", "os.system", "os.exec", "os.spawn")):
        raise RuntimeError("external execution/network forbidden")
    if event in ("os.remove", "os.rmdir", "os.rename", "os.link", "os.symlink", "os.chmod", "os.chown"):
        raise RuntimeError("mutation forbidden: " + event)
    if event == "open":
        path, mode, flags = args
        if not isinstance(path, (str, bytes, os.PathLike)):
            raise RuntimeError("unexpected file descriptor")
        writing = flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
        if writing and not inside(path):
            raise RuntimeError("write outside fixture")
    if event == "os.mkdir" and not inside(args[0]):
        raise RuntimeError("mkdir outside fixture")
    if event == "sqlite3.connect" and str(args[0]) not in (FIXTURE_DB, "file:" + FIXTURE_DB + "?mode=ro"):
        raise RuntimeError("database outside fixture")


sys.addaudithook(audit)
if module == "parser-proof":
    import rackmarshal.domains.zfs.collector as collector
    for value, expected in [(None, None), (0, 0), ("0", 0), (11, 11), ("11", 11)]:
        assert collector.permanent_error_count(value, "fixture") == expected
    for value in (True, False, -1, 0.5, 0.0, "0.5", "-1", "", [], {}):
        try:
            collector.permanent_error_count(value, "fixture")
        except SystemExit:
            pass
        else:
            raise AssertionError("invalid parser value accepted")
    print('{"parser_cases":15}')
elif module == "summary-proof":
    import json
    import sqlite3
    from rackmarshal.api.status import zfs_integrity_summary
    connection = sqlite3.connect(os.environ["RACKMARSHAL_STATE_DB"])
    connection.row_factory = sqlite3.Row
    print(json.dumps(zfs_integrity_summary(connection)))
    connection.close()
else:
    runpy.run_module(module, run_name="__main__")
'''

INVALID_COUNTS = (True, False, -1, 0.5, "0", [], {})


def run_cycles(python, site, work):
    """Run all nine cycles in `work` (a NEW directory). Returns the receipt dict."""
    python, site, work = Path(python), Path(site).resolve(), Path(work).resolve()
    database, config = work / "fixture.db", work / "fixture.conf"
    require(not database.exists() and not config.exists(), "fixture must be new")
    config.write_text(
        "STATE_DB=%s\nSITE_NAME=fixture\nSTATUS_API_LISTEN_ADDRESS=127.0.0.1\n"
        "STATUS_API_LISTEN_PORT=9110\nZFS_SSH_HOST=invalid\nZFS_SSH_USER=fixture\n"
        "ZFS_SSH_KEY=/nonexistent\nZFS_KNOWN_HOSTS=/nonexistent\n" % database
    )
    env = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C",
           "RACKMARSHAL_CONFIG": str(config), "RACKMARSHAL_STATE_DB": str(database)}
    receipt = {"result": "IN_PROGRESS", "commands": [], "cycles": []}

    def run(module, args=(), payload=None, expect_success=True, decode_output=True):
        command = [str(python), "-I", "-B", "-S", "-c", CHILD, str(work), str(site), module, *args]
        done = subprocess.run(command, input=json.dumps(payload) if payload is not None else None,
                              env=env, cwd=work, text=True, capture_output=True, timeout=20)
        receipt["commands"].append({"module": module, "args": list(args), "returncode": done.returncode,
                                    "stdout": done.stdout, "stderr": done.stderr})
        require((done.returncode == 0) == expect_success, "unexpected result: " + module)
        if decode_output and expect_success:
            return json.loads(done.stdout)
        return done.stdout

    run("rackmarshal.db.migrations.migrate", ["--db", str(database), "--apply", "--yes"], decode_output=False)
    sequence = [0]

    def observation(state, count, guid="1", missing=False):
        sequence[0] += 1
        pool = {"name": "fixture", "pool_guid": guid, "state": state, "error_count": count, "vdevs": []}
        if missing:
            del pool["error_count"]
        return {"schema_version": 1, "collector": "zfs_status",
                "observed_at": "2026-01-01T00:%02d:00Z" % sequence[0], "source": "synthetic",
                "host_key_verified": True, "pool_count": 1, "pools": [pool]}

    first = run("rackmarshal.domains.zfs.observation", payload=observation("ONLINE", 0))["observation_id"]
    with closing(sqlite3.connect(database)) as connection:
        connection.execute(
            "INSERT INTO zfs_pool_baseline(pool_name,pool_guid,baseline_state,expected_state,"
            "expected_error_count,source_observation_id) VALUES('fixture','1','VERIFIED','ONLINE',0,?)", (first,))
        connection.commit()

    def cycle(state, count, integrity, open_count, recovered=0, guid="1", missing=False):
        payload = observation(state, count, guid, missing)
        observation_id = run("rackmarshal.domains.zfs.observation", payload=payload)["observation_id"]
        args = ["--database", str(database)]
        comparison = run("rackmarshal.domains.zfs.comparator", args + ["--observation-id", str(observation_id)])
        run("rackmarshal.domains.zfs.events", args, comparison)
        incidents = run("rackmarshal.domains.zfs.incidents", args, comparison)
        summary = run("summary-proof")
        with closing(sqlite3.connect(database)) as connection:
            rows = connection.execute("SELECT incident_state,occurrence_count FROM zfs_incidents").fetchall()
        require(comparison["results"][0]["integrity_state"] == integrity, "comparator integrity")
        require(summary["state"] == integrity, "status integrity")
        require(sum(row[0] == "OPEN" for row in rows) == open_count, "open incident count")
        require(incidents["incidents_recovered"] == recovered, "recovery count")
        receipt["cycles"].append({"input": payload, "comparison": comparison, "incidents": incidents,
                                  "summary": summary, "ledger_rows": rows})
        return rows

    cycle("DEGRADED", 0, "CLEAN", 1)
    cycle("ONLINE", 11, "PROBLEM", 1)
    rows = cycle("ONLINE", 11, "PROBLEM", 1)
    require(rows == [("OPEN", 3)], "persistent count must be three")
    cycle("ONLINE", None, "UNKNOWN", 1)
    cycle("ONLINE", None, "UNKNOWN", 1, missing=True)
    cycle("ONLINE", 0, "CLEAN", 1, guid="2")
    cycle("DEGRADED", 0, "CLEAN", 1)
    cycle("ONLINE", 0, "CLEAN", 0, recovered=1)
    cycle("ONLINE", None, "UNKNOWN", 0, missing=True)
    for value in INVALID_COUNTS:
        with closing(sqlite3.connect(database)) as connection:
            before = connection.execute("SELECT COUNT(*) FROM zfs_observations").fetchone()[0]
        run("rackmarshal.domains.zfs.observation", payload=observation("ONLINE", value),
            expect_success=False, decode_output=False)
        with closing(sqlite3.connect(database)) as connection:
            after = connection.execute("SELECT COUNT(*) FROM zfs_observations").fetchone()[0]
        require(after == before, "invalid ingestion changed observations")
    receipt["parser"] = run("parser-proof")
    receipt.update(result="FIXTURE_ASSERTIONS_PASS", cycle_count=len(receipt["cycles"]),
                   invalid_ingestion_cases=len(INVALID_COUNTS), database_sha256=sha256(database.read_bytes()))
    require(receipt["cycle_count"] == 9, "cycle count")
    return receipt
