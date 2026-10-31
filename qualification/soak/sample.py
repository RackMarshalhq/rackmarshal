"""One sample: run every check once and write one evidence file per check.

Run by the driver as a child process so that a hang or crash in a check can be
killed and recorded without taking the driver down.
"""
import argparse
from pathlib import Path
import signal
import sys

# Isolated mode (-I) does not put the script's directory on the path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import checks
import fixture_cycles
from common import load, require, save, sha256

CHECKS = ("installed_files", "units", "status_api", "database", "snapshots",
          "journal_errors", "resources", "fixture_cycles")
DEADLINE_SECONDS = 110


def run_checks(config, out, since):
    venv = Path(config["venv"])
    site = next(venv.glob("lib/python*/site-packages"))
    results = {
        "installed_files": lambda: checks.installed_files(site / "rackmarshal", config["package_hashes"]),
        "units": lambda: checks.units(),
        "status_api": lambda: checks.status_api(),
        "database": lambda: checks.database(config["state_db"], config["migrations"]),
        "snapshots": lambda: checks.snapshots(config["snapshot_dir"]),
        "journal_errors": lambda: checks.journal_errors(since),
        "resources": lambda: checks.resources(Path(config["state_db"]).parent),
        "fixture_cycles": lambda: _fixture(venv, site, out),
    }
    require(tuple(results) == CHECKS, "check list differs from CHECKS")
    summary = {}
    failure = None
    for name in CHECKS:
        try:
            body = results[name]()
        except Exception as error:  # record every failure, then stop after the loop
            body = {"result": "FAIL", "error": repr(error)}
            failure = failure or error
        save(out / (name + ".json"), body)
        summary[name] = {"result": body["result"], "execution_receipt": name + ".json",
                         "execution_receipt_sha256": sha256((out / (name + ".json")).read_bytes())}
    return summary, failure


def _fixture(venv, site, out):
    work = out / "fixture"
    work.mkdir(mode=0o700)
    receipt = fixture_cycles.run_cycles(venv / "bin" / "python", site, work)
    return {"result": "PASS", "cycles": receipt["cycle_count"], "invalid_cases": receipt["invalid_ingestion_cases"],
            "database_sha256": receipt["database_sha256"]}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--since", required=True, help="journal window start, e.g. '2026-01-01 00:00:00 UTC'")
    args = parser.parse_args(argv)

    def deadline(signum, frame):
        raise TimeoutError("sample total deadline")

    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(DEADLINE_SECONDS)
    config = load(args.config)
    args.output.mkdir(mode=0o700)
    summary, failure = run_checks(config, args.output, args.since)
    save(args.output / "SAMPLE.json", {"result": "FAIL" if failure else "CHECKS_PASS", "checks": summary})
    signal.alarm(0)
    if failure:
        raise failure


if __name__ == "__main__":
    main()
