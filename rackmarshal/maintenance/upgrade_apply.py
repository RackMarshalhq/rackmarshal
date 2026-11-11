"""`rackmarshal upgrade`: plan first, then hand over to the new release's own lifecycle script.

The command never upgrades anything itself. It runs the read-only `upgrade-plan` checks against the
wheel inside an extracted installer bundle and, only with --apply, runs that bundle's
scripts/lifecycle.py with the trusted system interpreter. That script takes a database backup,
pauses the checks, switches the program folder, proves health and rolls back by itself on failure.
"""
from pathlib import Path
import subprocess

from rackmarshal.maintenance import upgrade_plan

TRUSTED_PYTHON = "/usr/bin/python3"
DEFAULT_VERIFY_TIMEOUT = 1800


class UpgradeRefused(Exception):
    """A refusal written for the person at the keyboard."""


def bundle_parts(bundle):
    root = Path(bundle)
    script = root / "scripts" / "lifecycle.py"
    if not root.is_dir() or not script.is_file() or script.is_symlink():
        raise UpgradeRefused("%s is not an extracted RackMarshal installer bundle (scripts/lifecycle.py not found)." % bundle)
    wheels = sorted(root.glob("rackmarshal-*-py3-none-any.whl"))
    if len(wheels) != 1 or wheels[0].is_symlink():
        raise UpgradeRefused("Expected exactly one rackmarshal wheel in the bundle, found %d." % len(wheels))
    return script, wheels[0]


def build_command(script, previous_wheel, previous_sha256, verify_timeout):
    return [TRUSTED_PYTHON, "-I", "-B", "-S", str(script), "upgrade",
            "--previous-wheel", str(Path(previous_wheel).absolute()),
            "--previous-sha256", previous_sha256,
            "--verify-timeout", str(int(verify_timeout))]


def run(site_packages, database, bundle, previous_wheel, previous_sha256, wheel_sha256,
        apply=False, note="", is_root=False, verify_timeout=DEFAULT_VERIFY_TIMEOUT,
        runner=subprocess.run, out=print):
    """Return a process exit status (0 ok, 2 refused)."""
    script, wheel = bundle_parts(bundle)
    if not Path(previous_wheel).is_file():
        raise UpgradeRefused("The previous release's wheel was not found; download it from its release page.")
    result = upgrade_plan.plan(site_packages, database, wheel, None, wheel_sha256)
    out(upgrade_plan.describe(result, can_apply=True))
    if result["status"] != "READY":
        return 2
    command = build_command(script, previous_wheel, previous_sha256, verify_timeout)
    out("")
    if not apply:
        out("Nothing was changed. To go ahead, run this again as root with --apply and --note \"why\".")
        out("That will run: " + " ".join(command))
        return 0
    if not is_root:
        raise UpgradeRefused("Applying an upgrade changes the installation, so run this as root (for example with sudo).")
    if not note.strip():
        raise UpgradeRefused("Say why with --note, for example --note \"fix for secondary check\".")
    out("Starting the upgrade (note: %s). This pauses the scheduled checks, then waits up to %d seconds for "
        "every check to run successfully on the new version." % (note.strip(), int(verify_timeout)))
    status = runner(command).returncode
    if status == 0:
        out("The upgrade script finished. Confirm the result line above says COMMITTED, then run: rackmarshal doctor")
    else:
        out("The upgrade did not complete. If the output says HEALTH CHECK FAILED it rolled back by itself; "
            "otherwise read the STOP message above and do not retry until you understand it.")
    return status
