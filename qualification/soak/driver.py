"""The timer-driven soak driver: one sample per run, recorded in a hash-chained ledger.

Rules (kept from the first qualification harness):
  * each receipt names the hash of the one before it, so a gap or edit is visible;
  * one failed sample is quarantined under glitches/ and retried once; at most
    MAX_GLITCHES in a window; a second failure of the same sample stops the run;
  * any stop writes STOP.json, which permanently refuses further samples;
  * the window completes (COMPLETE.json) only after 24 hours AND MIN_SAMPLES samples.
"""
import fcntl
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

# Isolated mode (-I) does not put the script's directory on the path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import canonical, check_interval, clock, decode, load, read_bytes, require, save, sha256

WINDOW_NS = 86400 * 10**9
MIN_SAMPLES = 280
MAX_GLITCHES = 2
MAX_GAP_SECONDS = 420
PERSIST_MAX_NS = 270 * 10**9
SAMPLER_TIMEOUT_SECONDS = 125
LOG_TAIL = 4000
CHECKS = ("installed_files", "units", "status_api", "database", "snapshots",
          "journal_errors", "resources", "fixture_cycles")


def journal_since(utc_ns):
    return time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(utc_ns // 10**9))


def verify_kit(kit, config):
    """The driver and checks must be byte-identical to what the launcher pinned."""
    for name, expected in config["kit_hashes"].items():
        require(".." not in Path(name).parts and not Path(name).is_absolute(), "unsafe kit path")
        require(sha256(read_bytes(kit / name)) == expected, "kit file changed: " + name)


def validate_chain(work, config):
    work = Path(work)
    receipts = work / "receipts"
    require(all(p.is_file() and p.name.endswith(".json") for p in receipts.iterdir()), "unexpected receipt member")
    head = sha256(canonical(config))
    rows = []
    for index, path in enumerate(sorted(receipts.glob("*.json"))):
        require(path.name == "%08d.json" % index, "receipt gap")
        raw = read_bytes(path)
        row = decode(raw)
        require(raw == canonical(row) and row["index"] == index and row["previous_sha256"] == head
                and row["result"] == "PASS", "receipt chain/failure")
        require(row["source_commit"] == config["source_commit"] and row["boot_id"] == config["boot_id"],
                "receipt binding")
        require(set(row["checks"]) == set(CHECKS) and all(v["result"] == "PASS" for v in row["checks"].values()),
                "checks missing or failed")
        check_interval(row["start"], row["finish"])
        require(row["finish"]["monotonic_ns"] - row["start"]["monotonic_ns"] <= PERSIST_MAX_NS, "sample too long")
        if rows:
            check_interval(rows[-1]["start"], row["start"], MAX_GAP_SECONDS)
        sample_dir = work / "samples" / ("%08d" % index)
        require(row["evidence"], "empty evidence")
        for name, digest in row["evidence"].items():
            require(".." not in Path(name).parts and not Path(name).is_absolute()
                    and sha256(read_bytes(sample_dir / name)) == digest, "sample evidence changed")
        listed = {str(p.relative_to(sample_dir)) for p in sample_dir.rglob("*") if p.is_file()}
        require(set(row["evidence"]) == listed, "unlisted sample evidence")
        intent = load(sample_dir / "INTENT.json")
        require(intent == {"index": index, "source_commit": config["source_commit"], "start": row["start"],
                           "previous_sha256": head, "boot_id": config["boot_id"]}, "intent differs")
        for check in row["checks"].values():
            require(row["evidence"].get(check["execution_receipt"]) == check["execution_receipt_sha256"],
                    "check evidence binding")
        require(row.get("attempts") in (1, 2), "attempts missing")
        head = sha256(raw)
        rows.append(row)
    names = {p.name for p in (work / "samples").iterdir()}
    require(names == {"%08d" % i for i in range(len(rows))}, "pending or unexpected sample")
    glitches = sorted(p.name for p in (work / "glitches").iterdir()) if (work / "glitches").exists() else []
    require(len(glitches) <= MAX_GLITCHES and all(re.fullmatch(r"\d{8}-attempt1", n) for n in glitches),
            "glitch budget or unexpected glitch record")
    retried = {row["index"] for row in rows if row["attempts"] == 2}
    require({int(n[:8]) for n in glitches if int(n[:8]) < len(rows)} == retried, "glitch records do not match retries")
    for name in glitches:
        require((work / "glitches" / name / "GLITCH.json").is_file(), "glitch record incomplete")
    if rows:
        expected = {"start": rows[0]["start"], "receipt_sha256": sha256(canonical(rows[0])),
                    "source_commit": config["source_commit"], "boot_id": config["boot_id"]}
        require(load(work / "START.json") == expected, "start record missing or changed")
    else:
        require(not (work / "START.json").exists(), "start without sample")
    return rows, head


def log_tail(path):
    try:
        return Path(path).read_bytes()[-LOG_TAIL:].decode("utf-8", "replace")
    except OSError:
        return ""


def run_sampler(kit, work, out, since):
    """Run sample.py in a child process. Returns its exit code, or 'driver-timeout'."""
    command = [sys.executable, "-I", "-B", "-S", str(kit / "sample.py"), "--config", str(work / "config.json"),
               "--output", str(out / "checks"), "--since", since]
    with (out / "sampler.log").open("xb") as log:
        child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                 env={"PATH": "/usr/bin:/bin", "LC_ALL": "C", "PYTHONPATH": str(kit)}, cwd="/")
        try:
            code = child.wait(timeout=SAMPLER_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=3)
            code = "driver-timeout"
        except BaseException:
            child.kill()
            child.wait(timeout=3)
            raise
        log.flush()
        os.fsync(log.fileno())
    return code


def sample_with_retry(work, index, out, source_commit, run_once):
    """Quarantine (never delete) one failed attempt and retry once. Returns the attempt count."""
    code = run_once(out)
    if code == 0:
        return 1
    glitches = work / "glitches"
    glitches.mkdir(mode=0o700, exist_ok=True)
    require(len(list(glitches.iterdir())) < MAX_GLITCHES, "glitch budget exhausted (rc=%r)" % (code,))
    target = glitches / ("%08d-attempt1" % index)
    target.mkdir(mode=0o700)
    tail = log_tail(out / "sampler.log")
    if (out / "checks").exists():
        os.rename(out / "checks", target / "checks")
    os.rename(out / "sampler.log", target / "sampler.log")
    save(target / "GLITCH.json", {"index": index, "attempt": 1, "rc": code, "at": clock(),
                                  "log_tail": tail, "source_commit": source_commit})
    code = run_once(out)
    require(code == 0, "sampler failed twice (rc=%r)" % (code,))
    return 2


def take_sample(work, kit, run_once=None):
    """One driver run. Raises on any problem; the caller records STOP.json."""
    work, kit = Path(work), Path(kit)
    config = load(work / "config.json")
    verify_kit(kit, config)
    require(not (work / "STOP.json").exists() and not (work / "COMPLETE.json").exists(), "stopped or completed run")
    boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    require(boot == config["boot_id"], "boot changed")
    rows, head = validate_chain(work, config)
    start = clock()
    if rows:
        check_interval(rows[-1]["start"], start, MAX_GAP_SECONDS)
    require(os.statvfs(work).f_bavail * os.statvfs(work).f_frsize > 256 * 2**20, "low evidence space")
    index = len(rows)
    out = work / "samples" / ("%08d" % index)
    out.mkdir(mode=0o700)
    save(out / "INTENT.json", {"index": index, "source_commit": config["source_commit"], "start": start,
                               "previous_sha256": head, "boot_id": boot})
    since = journal_since(rows[-1]["start"]["utc_ns"] if rows else config["launched_utc_ns"])
    if run_once is None:
        def run_once(path):
            return run_sampler(kit, work, path, since)
    attempts = sample_with_retry(work, index, out, config["source_commit"], run_once)
    summary = load(out / "checks" / "SAMPLE.json")
    require(summary["result"] == "CHECKS_PASS" and set(summary["checks"]) == set(CHECKS), "sample result")
    require(Path("/proc/sys/kernel/random/boot_id").read_text().strip() == boot, "boot changed during sample")
    finish = clock()
    check_interval(start, finish)
    require(finish["monotonic_ns"] - start["monotonic_ns"] <= PERSIST_MAX_NS, "sample too long")
    evidence = {str(p.relative_to(out)): sha256(read_bytes(p)) for p in sorted(out.rglob("*")) if p.is_file()}
    checks = {name: {"result": value["result"],
                     "execution_receipt": "checks/" + value["execution_receipt"],
                     "execution_receipt_sha256": value["execution_receipt_sha256"]}
              for name, value in summary["checks"].items()}
    row = {"index": index, "result": "PASS", "source_commit": config["source_commit"], "boot_id": boot,
           "start": start, "finish": finish, "previous_sha256": head, "checks": checks, "attempts": attempts,
           "evidence": evidence, "scope": "disposable container; synthetic data only"}
    save(work / "receipts" / ("%08d.json" % index), row)
    if index == 0:
        save(work / "START.json", {"start": start, "receipt_sha256": sha256(canonical(row)),
                                   "source_commit": config["source_commit"], "boot_id": boot})
    first = rows[0] if rows else row
    if rows and start["monotonic_ns"] - first["start"]["monotonic_ns"] >= WINDOW_NS:
        require(start["utc_ns"] - first["start"]["utc_ns"] >= WINDOW_NS, "UTC span insufficient")
        require(index + 1 >= MIN_SAMPLES, "too few samples for window")
        save(work / "COMPLETE.json", {"result": "SOAK_WINDOW_COMPLETE", "first": first["start"], "last": start,
                                      "samples": index + 1, "head_sha256": sha256(canonical(row)),
                                      "source_commit": config["source_commit"]})
    return row


def main(work, kit):
    os.umask(0o077)
    require(sys.platform == "linux" and sys.version_info >= (3, 11), "wrong runtime")
    require("/rmq-soak.service" in Path("/proc/self/cgroup").read_text(), "must run in the dedicated systemd cgroup")
    fd = os.open(Path(work) / "writer.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        row = take_sample(work, kit)
        print('{"result":"PASS","index":%d}' % row["index"])
    except BaseException as error:
        stop = Path(work) / "STOP.json"
        if not stop.exists():
            save(stop, {"result": "FAIL_STOP", "at": clock(), "error": repr(error)})
        raise
    finally:
        os.close(fd)


if __name__ == "__main__":
    def interrupted(signum, frame):
        raise RuntimeError("interrupted %s" % signum)

    for number in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(number, interrupted)
    main(sys.argv[1], Path(__file__).resolve().parent)
