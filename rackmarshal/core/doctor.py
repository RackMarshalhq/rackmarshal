"""`rackmarshal doctor`: a read-only first-run health check in plain words.

It changes nothing, reads no credentials and sends nothing anywhere except one
request to the local status page. Each result is PASS, WARN or FAIL with what
to do next. Exit status is 2 only when something FAILed.
"""
from contextlib import closing
from datetime import datetime, timezone
import json
import socket
import sqlite3
import subprocess
from pathlib import Path

from rackmarshal import http
from rackmarshal.core.config import ConfigError, load_config, require

TAILSCALE_RESOLVER = "100.100.100.100"
STALE_AFTER_SECONDS = 2 * 3600
SSH_HOST_KEYS = ("ZFS_SSH_HOST", "HARDWARE_SSH_HOST", "MOUNT_SSH_HOST")


def _systemctl(*args):
    """Return (exit_code, stdout). exit_code None means systemctl cannot be run here."""
    try:
        done = subprocess.run(["/usr/bin/systemctl", *args], capture_output=True, text=True, timeout=15,
                              env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"}, cwd="/")
    except (OSError, subprocess.TimeoutExpired):
        return None, ""
    return done.returncode, done.stdout.strip()


def _fetch_health(url):
    with http.urlopen(url, timeout=3) as response:
        return response.status, json.loads(response.read())


def _read_text(path):
    try:
        return Path(path).read_text()
    except OSError:
        return None


def _result(status, name, message, fix=None):
    return {"status": status, "name": name, "message": message, "fix": fix}


def _age_text(seconds):
    if seconds < 3600:
        return "%d minutes" % max(0, seconds // 60)
    return "%.1f hours" % (seconds / 3600)


def _parse_time(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else None


def check_configuration(path):
    from rackmarshal.cli import validate

    errors = validate(path)
    if errors:
        return _result("FAIL", "Settings file", "The settings file has a problem: " + errors[0],
                       "Run 'rackmarshal validate-config' to see every problem, fix the settings file, and run doctor again.")
    return _result("PASS", "Settings file", "Readable and valid.")


def check_database(database):
    path = Path(database)
    if not path.is_file():
        return _result("FAIL", "Database", "The RackMarshal database file does not exist yet.",
                       "Run 'rackmarshal migrate --apply' as described in INSTALL.md.")
    try:
        with closing(sqlite3.connect("file:%s?mode=ro" % path.resolve(), uri=True, timeout=5)) as conn:
            verdict = conn.execute("PRAGMA quick_check").fetchone()[0]
    except sqlite3.Error as exc:
        return _result("FAIL", "Database", "The database could not be opened: %s." % exc,
                       "Check the file's owner and permissions, then run doctor again.")
    if verdict != "ok":
        return _result("FAIL", "Database", "The database failed its integrity check.",
                       "Restore the newest snapshot (see UPGRADE.md) before continuing.")
    return _result("PASS", "Database", "Opens and passes its integrity check.")


def check_dns(config, resolv_conf, getaddrinfo):
    results = []
    text = _read_text(resolv_conf)
    if text is not None:
        servers = [line.split()[1] for line in text.splitlines() if line.startswith("nameserver") and len(line.split()) > 1]
        if servers and set(servers) == {TAILSCALE_RESOLVER}:
            results.append(_result(
                "FAIL", "Name lookup (DNS)",
                "The only DNS server is Tailscale's (%s), which cannot look up your normal hosts." % TAILSCALE_RESOLVER,
                "On the Proxmox host run: pct set <container number> --nameserver <your router or DNS server>, "
                "then restart the container."))
        elif not servers:
            results.append(_result("FAIL", "Name lookup (DNS)", "No DNS server is configured.",
                                   "Give this machine a DNS server, then run doctor again."))
    for key in SSH_HOST_KEYS:
        host = config.get(key, "").strip()
        if not host:
            continue
        try:
            getaddrinfo(host, None)
        except OSError:
            results.append(_result("FAIL", "Name lookup (DNS)", "%s cannot be looked up." % key.replace("_SSH_HOST", "").title() + " host",
                                   "Check the host name in the settings file, or use its IP address."))
    if not results:
        results.append(_result("PASS", "Name lookup (DNS)", "DNS server configured; configured hosts resolve."))
    return results


def check_credential_files(config, enabled):
    from rackmarshal.cli import DOMAIN_REQUIREMENTS
    from rackmarshal.core.setup import FILE_KEYS, file_readiness

    problems = []
    for domain in enabled:
        for key in DOMAIN_REQUIREMENTS.get(domain, ()):
            if key in FILE_KEYS and config.get(key, "").strip():
                state = file_readiness(config[key].strip())
                if state != "PRESENT":
                    problems.append("%s (%s)" % (key, state.lower().replace("_", " ")))
    if problems:
        return _result("FAIL", "Credential files", "Problem with: " + ", ".join(sorted(set(problems))) + ".",
                       "Make sure each file exists, is readable by the RackMarshal service, and is private (mode 600).")
    return _result("PASS", "Credential files", "Present, readable and private (contents are never read).")


def check_timers(enabled, systemctl):
    names = ["rackmarshal-domain@%s.timer" % domain for domain in enabled] + ["rackmarshal-notify.timer"]
    results = []
    for name in names:
        code, state = systemctl("is-enabled", name)
        if code is None:
            return [_result("WARN", "Scheduled checks", "Could not ask systemd about the timers from here.",
                            "Run doctor on the machine where RackMarshal is installed.")]
        label = name.replace("rackmarshal-", "").replace(".timer", "")
        if code != 0:
            results.append(_result("FAIL", "Scheduled check: " + label, "The timer is not enabled (%s)." % (state or "unknown"),
                                   "Enable it: sudo systemctl enable --now " + name))
            continue
        code, state = systemctl("is-active", name)
        if code != 0:
            results.append(_result("FAIL", "Scheduled check: " + label, "The timer is enabled but not running.",
                                   "Start it: sudo systemctl start " + name))
        else:
            results.append(_result("PASS", "Scheduled check: " + label, "Timer is enabled and running."))
    return results


def check_last_runs(database, enabled, now):
    path = Path(database)
    if not path.is_file():
        return []
    try:
        with closing(sqlite3.connect("file:%s?mode=ro" % path.resolve(), uri=True, timeout=5)) as conn:
            conn.row_factory = sqlite3.Row
            rows = {row["unit_name"]: row for row in conn.execute("SELECT * FROM cycle_health")}
    except sqlite3.Error:
        return []
    results = []
    for domain in enabled:
        unit = "rackmarshal-domain@%s.service" % domain
        row = rows.get(unit)
        label = "Last run: " + domain
        if row is None:
            results.append(_result("WARN", label, "This check has not run yet.",
                                   "Wait for its next scheduled run, or start it once: sudo systemctl start " + unit))
        elif row["health_state"] == "FAILED":
            results.append(_result("FAIL", label, "The last run failed (%s)." % row["last_failure_at"],
                                   "See why: journalctl -u %s -n 50. A failed Proxmox or backup run is most often a "
                                   "permission problem with the API token." % unit))
        else:
            stamp = _parse_time(row["last_success_at"] or row["last_result_at"])
            age = int((now - stamp).total_seconds()) if stamp else None
            if age is None or age > STALE_AFTER_SECONDS:
                results.append(_result("WARN", label, "The last successful run was %s ago." % (
                    _age_text(age) if age is not None else "at an unknown time"),
                    "Check the timer with: systemctl list-timers 'rackmarshal*'"))
            else:
                results.append(_result("PASS", label, "Succeeded %s ago." % _age_text(age)))
    return results


def check_status_page(config, fetch):
    host = config.get("STATUS_API_LISTEN_ADDRESS", "127.0.0.1")
    port = config.get("STATUS_API_LISTEN_PORT", "9110")
    probe = "127.0.0.1" if host in ("0.0.0.0", "") else host
    try:
        status, body = fetch("http://%s:%s/health" % (probe, port))
    except Exception:
        return _result("FAIL", "Status page", "The status page did not answer on port %s." % port,
                       "Start it: sudo systemctl start rackmarshal-status.service")
    if status != 200:
        return _result("FAIL", "Status page", "The status page answered with an error (%s)." % status,
                       "See why: journalctl -u rackmarshal-status.service -n 50")
    return _result("PASS", "Status page", "Answering on port %s." % port)


def run_doctor(path, *, systemctl=_systemctl, getaddrinfo=socket.getaddrinfo, fetch=_fetch_health,
               resolv_conf="/etc/resolv.conf", now=None):
    """Run every check and return {"results": [...], "failed": n, "warned": n}."""
    from rackmarshal.cli import _enabled

    now = now or datetime.now(timezone.utc)
    results = [check_configuration(path)]
    if results[0]["status"] == "PASS":
        config = load_config(path)
        enabled = [d for d in _enabled(config)]
        database = require(config, "STATE_DB")
        results.append(check_database(database))
        results += check_dns(config, resolv_conf, getaddrinfo)
        results.append(check_credential_files(config, enabled))
        results += check_timers(enabled, systemctl)
        results += check_last_runs(database, enabled, now)
        results.append(check_status_page(config, fetch))
    return {"results": results,
            "failed": sum(r["status"] == "FAIL" for r in results),
            "warned": sum(r["status"] == "WARN" for r in results)}


def describe(report):
    lines = []
    for item in report["results"]:
        lines.append("[%s] %s: %s" % (item["status"], item["name"], item["message"]))
        if item["fix"] and item["status"] != "PASS":
            lines.append("       What to do: " + item["fix"])
    lines.append("")
    if report["failed"]:
        lines.append("%d problem(s) need fixing before RackMarshal can be trusted. Fix the first one and run doctor again."
                     % report["failed"])
    elif report["warned"]:
        lines.append("Nothing is broken, but %d item(s) deserve a look." % report["warned"])
    else:
        lines.append("Everything checked looks good. Doctor does not prove your servers are healthy; "
                     "it checks that RackMarshal is set up to watch them.")
    return "\n".join(lines)
