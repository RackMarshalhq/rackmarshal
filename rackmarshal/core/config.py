#!/usr/bin/env python3
"""RackMarshal shared configuration helpers.

Phase 2 Step 2: path helpers default to today's install layout so callers
can migrate off hard-coded strings without changing live conf yet.
Keys from config/rackmarshal.conf.example are honored when present.
"""

from pathlib import Path
import os


DEFAULT_CONFIG_FILE = Path(os.environ.get("RACKMARSHAL_CONFIG", "/etc/rackmarshal/rackmarshal.conf"))

# Portability defaults (match this site's layout / conf.example)
DEFAULT_INSTALL_ROOT = Path("/opt/rackmarshal")
DEFAULT_CONFIG_DIR = Path("/etc/rackmarshal")
DEFAULT_STATE_DIR = Path("/var/lib/rackmarshal")
DEFAULT_STATE_DB = DEFAULT_STATE_DIR / "state.db"
DEFAULT_DOMAINS_DIR = DEFAULT_INSTALL_ROOT / "domains"
DEFAULT_VENV_PYTHON = DEFAULT_INSTALL_ROOT / "venv" / "bin" / "python"

DEFAULT_HA_CREDENTIAL_FILE = DEFAULT_CONFIG_DIR / "home-assistant-api.env"
DEFAULT_PVE_API_ENV = DEFAULT_CONFIG_DIR / "pve-api.env"
DEFAULT_PBS_API_ENV = DEFAULT_CONFIG_DIR / "pbs-api.env"
DEFAULT_PVE_CA_FILE = DEFAULT_CONFIG_DIR / "pve-root-ca.pem"
DEFAULT_PBS_CA_FILE = DEFAULT_CONFIG_DIR / "pbs-proxy.pem"


class ConfigError(RuntimeError):
    pass


def load_config(path=DEFAULT_CONFIG_FILE):
    config = {}

    try:
        with Path(path).open(
            "r",
            encoding="utf-8",
        ) as handle:
            for raw_line in handle:
                line = raw_line.strip()

                if (
                    not line
                    or line.startswith("#")
                    or "=" not in line
                ):
                    continue

                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()

                if (
                    len(value) >= 2
                    and value[0] == value[-1]
                    and value[0] in ('"', "'")
                ):
                    value = value[1:-1]

                config[key] = value

    except OSError as exc:
        raise ConfigError(
            f"unable to read config {path}: {exc}"
        ) from exc

    return config


def require(config, key):
    value = config.get(key)

    if value is None or not str(value).strip():
        raise ConfigError(
            f"required configuration key missing: {key}"
        )

    return str(value).strip()


def require_int(config, key):
    value = require(config, key)

    try:
        return int(value)
    except ValueError as exc:
        raise ConfigError(
            f"configuration key {key} must be an integer"
        ) from exc


def _optional_path(config, key, default):
    """Return Path from conf key if set, else default Path."""
    if config is None:
        config = {}
    value = config.get(key)
    if value is None or not str(value).strip():
        return Path(default)
    return Path(str(value).strip())


def _ensure_config(config):
    if config is None:
        return load_config()
    return config


def install_root(config=None):
    config = _ensure_config(config)
    return _optional_path(config, "INSTALL_ROOT", DEFAULT_INSTALL_ROOT)


def config_dir(config=None):
    config = _ensure_config(config)
    return _optional_path(config, "CONFIG_DIR", DEFAULT_CONFIG_DIR)


def state_dir(config=None):
    config = _ensure_config(config)
    return _optional_path(config, "STATE_DIR", DEFAULT_STATE_DIR)


def domains_dir(config=None):
    config = _ensure_config(config)
    value = config.get("DOMAINS_DIR")
    if value is not None and str(value).strip():
        return Path(str(value).strip())
    return install_root(config) / "domains"


def venv_python(config=None):
    config = _ensure_config(config)
    explicit = config.get("VENV_PYTHON")
    if explicit is not None and str(explicit).strip():
        return Path(str(explicit).strip())
    return install_root(config) / "venv" / "bin" / "python"


def ha_credential_file(config=None):
    config = _ensure_config(config)
    return _optional_path(
        config, "HA_CREDENTIAL_FILE", DEFAULT_HA_CREDENTIAL_FILE
    )


def pve_api_env(config=None):
    config = _ensure_config(config)
    return _optional_path(config, "PVE_API_ENV", DEFAULT_PVE_API_ENV)


def pbs_api_env(config=None):
    config = _ensure_config(config)
    return _optional_path(config, "PBS_API_ENV", DEFAULT_PBS_API_ENV)


def pve_ca_file(config=None):
    config = _ensure_config(config)
    return _optional_path(config, "PVE_CA_FILE", DEFAULT_PVE_CA_FILE)


def pbs_ca_file(config=None):
    config = _ensure_config(config)
    return _optional_path(config, "PBS_CA_FILE", DEFAULT_PBS_CA_FILE)


def state_db(config=None):
    if config is None:
        config = load_config()

    # Unchanged contract: STATE_DB remains required in conf.
    return Path(
        require(
            config,
            "STATE_DB",
        )
    )


def sqlite_ro_uri(path):
    return "file:" + str(path) + "?mode=ro"



def optional_bool(config, key, default=False):
    """Parse true/false/1/0/yes/no; missing key → default."""
    config = _ensure_config(config)
    value = config.get(key)
    if value is None or not str(value).strip():
        return bool(default)
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(
        f"configuration key {key} must be a boolean "
        f"(got {value!r})"
    )


def optional_int(config, key, default):
    """Integer conf key with default when missing/blank."""
    config = _ensure_config(config)
    value = config.get(key)
    if value is None or not str(value).strip():
        return int(default)
    try:
        return int(str(value).strip())
    except ValueError as exc:
        raise ConfigError(
            f"configuration key {key} must be an integer"
        ) from exc


def local_ai_enabled(config=None):
    """Phase 5.4: gate Ollama explain on OPENED deliver. Default True preserves CT 110 behavior."""
    return optional_bool(config, "LOCAL_AI_ENABLED", True)


def local_ai_timeout_seconds(config=None):
    """Subprocess timeout for explain_incident.py (deliver path)."""
    return optional_int(config, "LOCAL_AI_TIMEOUT_SECONDS", 20)

def local_ai_attach_to_notify(config=None):
    """If true, OPENED notify body may include AI text when already explained."""
    return optional_bool(config, "LOCAL_AI_ATTACH_TO_NOTIFY", False)


CONFIG = load_config()
