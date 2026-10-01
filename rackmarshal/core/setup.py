"""Local, read-only setup planning. Never reads credentials or probes targets."""
import os
import stat
from pathlib import Path
from rackmarshal.core.config import ConfigError, load_config

FILE_KEYS = frozenset(("PVE_API_ENV", "PVE_CA_FILE", "PBS_API_ENV", "PBS_CA_FILE",
    "HA_CREDENTIAL_FILE", "ZFS_SSH_KEY", "ZFS_KNOWN_HOSTS", "HARDWARE_SSH_KEY",
    "HARDWARE_KNOWN_HOSTS", "MOUNT_SSH_KEY", "MOUNT_KNOWN_HOSTS", "MOUNT_CATALOG_FILE"))


def file_readiness(value):
    """Match the validator's restrictive file policy without reading file contents."""
    try:
        path = Path(value)
        mode = path.stat().st_mode
        if not stat.S_ISREG(mode):
            return "NOT_A_FILE"
        if not os.access(path, os.R_OK):
            return "UNREADABLE"
        if mode & (stat.S_IRWXG | stat.S_IRWXO):
            return "PERMISSIONS_TOO_BROAD"
        return "PRESENT"
    except FileNotFoundError:
        return "MISSING"
    except OSError:
        return "UNAVAILABLE"


def setup_plan(path):
    # Lazy import shares the existing CLI validator instead of copying requirements.
    from rackmarshal.cli import DOMAINS, DOMAIN_REQUIREMENTS, _enabled, validate
    result = {"authority": "DERIVED", "read_only": True,
              "configuration_status": "INVALID", "domains": [],
              "limitations": ["Configuration is not proof of collection, resource health or recovery.",
                 "File checks do not verify credential validity, certificate trust or target access.",
                 "Domain selection does not establish coverage of every resource in that domain.",
                 "No files are written, services started, collectors invoked or network requests made."]}
    try:
        config = load_config(path)
    except (ConfigError, UnicodeError):
        result["next_steps"] = ["Provide a readable UTF-8 RackMarshal configuration file."]
        return result
    selected = _enabled(config)
    invalid = bool(set(selected) - set(DOMAINS))
    errors = validate(path)
    result["state_database_configured"] = bool(config.get("STATE_DB", "").strip())
    # Expose fixed key names and check results only, never values, paths or serials.
    blocked = False
    for domain in DOMAINS:
        enabled = domain in selected
        missing = [key for key in DOMAIN_REQUIREMENTS[domain]
                   if not config.get(key, "").strip()] if enabled else []
        files = {key: file_readiness(config[key].strip())
                 for key in DOMAIN_REQUIREMENTS[domain]
                 if enabled and key in FILE_KEYS and config.get(key, "").strip()}
        incomplete = bool(missing or any(v != "PRESENT" for v in files.values())
                          or any(e.startswith(domain + ":") for e in errors))
        blocked |= enabled and incomplete
        result["domains"].append({"domain": domain.upper(), "enabled": enabled,
            "setup_state": "DISABLED" if not enabled else
                "NEEDS_CONFIGURATION" if incomplete else "CONFIGURATION_COMPLETE",
            "missing_keys": missing, "file_checks": files})
    result["configuration_status"] = "INVALID" if invalid or errors or blocked else "VALID"
    result["next_steps"] = []
    if invalid:
        result["next_steps"].append("Use only supported domain names in ENABLED_DOMAINS.")
    if errors or blocked:
        result["next_steps"].append("Resolve configuration/file checks; run validate-config locally for details.")
    if not selected:
        result["next_steps"].append("Choose one supported domain and supply its configuration before enabling collection.")
    else:
        result["next_steps"].append("After validation, explicitly enable the selected domain timers using the installation guide.")
    result["next_steps"].append("Verify a recorded observation and current cycle result; inspect freshness and incident evidence independently.")
    result["next_steps"].append("Keep Investigator read-only; configure any hosted connection privately.")
    return result
