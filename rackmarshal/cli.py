"""RackMarshal administrative CLI."""
import argparse
import importlib
import importlib.util
import json
import os
import stat
import sys
import tomllib
from pathlib import Path

from rackmarshal import __version__, http
from rackmarshal.core.config import ConfigError, load_config, require

DOMAINS = ("pve", "zfs", "backup", "ha", "hardware", "mount")
ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = "/etc/rackmarshal/rackmarshal.conf"
DEFAULT_INVESTIGATOR_URL = "http://127.0.0.1:8000/mcp"

# Site settings each domain needs before it can collect anything.
DOMAIN_REQUIREMENTS = {
    "pve": ("PVE_API_ENV", "PVE_CA_FILE"),
    "backup": ("PVE_API_ENV", "PVE_CA_FILE", "PBS_API_ENV", "PBS_CA_FILE", "PVE_NODE"),
    "ha": ("HA_CREDENTIAL_FILE",),
    "zfs": ("SITE_NAME", "ZFS_SSH_HOST", "ZFS_SSH_USER", "ZFS_SSH_KEY", "ZFS_KNOWN_HOSTS"),
    "hardware": (
        "SITE_NAME",
        "HARDWARE_SSH_HOST",
        "HARDWARE_SSH_USER",
        "HARDWARE_SSH_KEY",
        "HARDWARE_KNOWN_HOSTS",
        "HARDWARE_NVME_SERIALS",
        "HARDWARE_HOT_THRESHOLD_C",
        "HARDWARE_HOT_REQUIRED_SAMPLES",
        "HARDWARE_URGENT_THRESHOLD_C",
        "HARDWARE_RECOVERY_THRESHOLD_C",
        "HARDWARE_RECOVERY_REQUIRED_SAMPLES",
    ),
    "mount": (
        "PVE_API_ENV",
        "PVE_CA_FILE",
        "PVE_NODE",
        "MOUNT_CATALOG_FILE",
        "MOUNT_SSH_HOST",
        "MOUNT_SSH_USER",
        "MOUNT_SSH_KEY",
        "MOUNT_KNOWN_HOSTS",
    ),
}

# Settings that name credential, key or certificate files. If the file exists,
# only its owner may have any access to it.
CREDENTIAL_FILE_KEYS = (
    "PVE_API_ENV",
    "PBS_API_ENV",
    "HA_CREDENTIAL_FILE",
    "ZFS_SSH_KEY",
    "HARDWARE_SSH_KEY",
    "MOUNT_SSH_KEY",
    "PVE_CA_FILE",
    "PBS_CA_FILE",
    "ZFS_KNOWN_HOSTS",
    "HARDWARE_KNOWN_HOSTS",
    "MOUNT_KNOWN_HOSTS",
    "MOUNT_CATALOG_FILE",
)


def _enabled(config):
    """Domains listed in ENABLED_DOMAINS, lower-cased, in the order given."""
    raw = config.get("ENABLED_DOMAINS", "").strip()
    if not raw:
        return []
    return [name.strip().lower() for name in raw.split(",") if name.strip()]


def _missing_domain_keys(config, enabled):
    errors = []
    for domain in enabled:
        for key in DOMAIN_REQUIREMENTS.get(domain, ()):
            if not config.get(key, "").strip():
                errors.append(f"{domain}: missing {key}")
    return errors


def _broad_permission_errors(config):
    errors = []
    too_open = stat.S_IRWXG | stat.S_IRWXO
    for key in CREDENTIAL_FILE_KEYS:
        value = config.get(key, "").strip()
        if value and Path(value).exists() and (Path(value).stat().st_mode & too_open):
            errors.append(f"{key}: credential/key file permissions are too broad")
    return errors


def _hardware_inventory_errors(config, enabled):
    """Every listed NVMe serial needs a MODEL and a ROLE setting."""
    serials_raw = config.get("HARDWARE_NVME_SERIALS", "").strip()
    if "hardware" not in enabled or not serials_raw:
        return []
    errors = []
    for serial in [item.strip() for item in config["HARDWARE_NVME_SERIALS"].split(",") if item.strip()]:
        for suffix in ("MODEL", "ROLE"):
            key = f"HARDWARE_NVME_{serial}_{suffix}"
            if not config.get(key, "").strip():
                errors.append(f"hardware: missing {key}")
    return errors


def _plugin_errors():
    """Every supported domain must ship a cycle module and a valid plugin manifest."""
    errors = []
    for domain in DOMAINS:
        if importlib.util.find_spec(f"rackmarshal.domains.{domain}.cycle") is None:
            errors.append(f"{domain}: cycle module unavailable")
        manifest = ROOT / "domains" / domain / "plugin.toml"
        try:
            data = tomllib.loads(manifest.read_text(encoding="utf-8"))
            if data.get("id", "").lower() != domain:
                errors.append(f"{domain}: plugin manifest id mismatch")
            if int(data.get("schema_version", 0)) != 1:
                errors.append(f"{domain}: unsupported plugin manifest schema")
            for name, module in data.get("entrypoints", {}).items():
                if importlib.util.find_spec(module) is None:
                    errors.append(f"{domain}: entrypoint {name} unavailable: {module}")
        except Exception as exc:
            errors.append(f"{domain}: invalid plugin manifest: {exc}")
    return errors


def validate(path):
    """Return a list of problems with the configuration at path (empty means valid)."""
    try:
        config = load_config(path)
    except ConfigError as exc:
        return [str(exc)]
    errors = []
    try:
        require(config, "STATE_DB")
    except ConfigError as exc:
        errors.append(str(exc))
    enabled = _enabled(config)
    unknown = sorted(set(enabled) - set(DOMAINS))
    if unknown:
        errors.append("unknown enabled domains: " + ", ".join(unknown))
    errors += _missing_domain_keys(config, enabled)
    errors += _broad_permission_errors(config)
    errors += _hardware_inventory_errors(config, enabled)
    errors += _plugin_errors()
    return errors


def diagnostic(path):
    """Non-secret summary of the installation, including a local health probe."""
    config = load_config(path)
    database = Path(require(config, "STATE_DB"))
    report = {
        "config": str(path),
        "state_db": str(database),
        "state_db_exists": database.exists(),
        "enabled_domains": _enabled(config),
    }
    host = config.get("STATUS_API_LISTEN_ADDRESS", "127.0.0.1")
    port = config.get("STATUS_API_LISTEN_PORT", "9110")
    try:
        with http.urlopen(f"http://{host}:{port}/health", timeout=2) as response:
            report["health"] = {"status": response.status, "body": json.loads(response.read())}
    except Exception as exc:
        report["health"] = {"error": f"{type(exc).__name__}: {exc}"}
    return report


def _print_json(value):
    print(json.dumps(value, indent=2))


# One function per subcommand. Each returns the process exit code.

def _cmd_domains(args):
    print("\n".join(DOMAINS))
    return 0


def _cmd_validate_config(args):
    errors = validate(args.config)
    _print_json({"status": "PASS" if not errors else "FAIL", "errors": errors})
    return 0 if not errors else 2


def _cmd_setup_plan(args):
    from rackmarshal.core.setup import setup_plan

    report = setup_plan(args.config)
    _print_json(report)
    return 2 if report["configuration_status"] == "INVALID" else 0


def _cmd_investigator_check(args):
    from rackmarshal.mcp.check import connection_check

    report = connection_check(args.url)
    _print_json(report)
    return 0 if report["result"] == "PASS" else 2


def _cmd_diagnostic(args):
    try:
        report = diagnostic(args.config)
    except ConfigError as exc:
        # Same shape and exit code as validate-config, instead of a traceback.
        _print_json({"status": "FAIL", "errors": [str(exc)]})
        return 2
    _print_json(report)
    return 0


def _cmd_migrate(args):
    from rackmarshal.db.migrations.migrate import main as migration_main

    # The migration tool reads its own argv and the config path from the environment.
    migration_argv = ["rackmarshal-migrate", "--apply" if args.apply else "--plan"]
    if args.apply:
        migration_argv.append("--yes")
    saved_argv = sys.argv
    sys.argv = migration_argv
    os.environ["RACKMARSHAL_CONFIG"] = args.config
    try:
        return migration_main() or 0
    finally:
        sys.argv = saved_argv


COMMANDS = {
    "validate-config": _cmd_validate_config,
    "domains": _cmd_domains,
    "setup-plan": _cmd_setup_plan,
    "investigator-check": _cmd_investigator_check,
    "diagnostic": _cmd_diagnostic,
    "migrate": _cmd_migrate,
}


def _build_parser():
    default_config = os.getenv("RACKMARSHAL_CONFIG", DEFAULT_CONFIG)

    def add_config_option(subparser):
        subparser.add_argument("--config", default=default_config)

    parser = argparse.ArgumentParser(prog="rackmarshal")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="cmd", required=True)

    add_config_option(commands.add_parser("validate-config"))
    commands.add_parser("domains")
    add_config_option(
        commands.add_parser("setup-plan", help="Read-only setup guidance; does not enable collection")
    )
    check = commands.add_parser("investigator-check", help="Read-only MCP connection and authority check")
    check.add_argument("--url", default=DEFAULT_INVESTIGATOR_URL)
    add_config_option(commands.add_parser("diagnostic"))
    migrate = commands.add_parser("migrate")
    add_config_option(migrate)
    migrate.add_argument("--apply", action="store_true")
    return parser


def main(argv=None):
    args = _build_parser().parse_args(argv)
    return COMMANDS[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
