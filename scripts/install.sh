#!/usr/bin/env bash
set -euo pipefail
# Never inherit an invoking shell's public or owner-only installation policy.
umask 0027

WHEEL=""
CONFIG_SOURCE=""
NO_START=0

usage() {
  echo "Usage: install.sh --wheel /path/to/rackmarshal.whl [--config /path/to/rackmarshal.conf] [--no-start]"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --wheel) WHEEL="${2:-}"; shift 2 ;;
    --config) CONFIG_SOURCE="${2:-}"; shift 2 ;;
    --no-start) NO_START=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ $EUID -eq 0 ]] || { echo "ERROR: run as root" >&2; exit 1; }
[[ -n "$WHEEL" && -f "$WHEEL" ]] || { echo "ERROR: --wheel must name an existing wheel" >&2; exit 2; }

if command -v apt-get >/dev/null 2>&1; then
  need_pkg=0
  command -v python3 >/dev/null 2>&1 || need_pkg=1
  if [[ "$need_pkg" -eq 0 ]]; then
    probe_dir="$(mktemp -d)"
    if ! python3 -m venv "$probe_dir" >/dev/null 2>&1 || [[ ! -x "$probe_dir/bin/pip" ]]; then
      need_pkg=1
    fi
    rm -rf "$probe_dir"
  fi
  if [[ "$need_pkg" -eq 1 ]]; then
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-venv
  fi
fi

for cmd in python3 systemctl systemd-analyze install getent; do
  command -v "$cmd" >/dev/null || { echo "ERROR: missing prerequisite: $cmd" >&2; exit 3; }
done
python3 -m venv --help >/dev/null 2>&1 || { echo "ERROR: python3-venv is required" >&2; exit 3; }

getent group rackmarshal >/dev/null || groupadd --system rackmarshal
getent passwd rackmarshal >/dev/null || useradd --system --gid rackmarshal --home-dir /var/lib/rackmarshal --shell /usr/sbin/nologin rackmarshal

install -d -o root -g root -m 0755 /opt/rackmarshal
install -d -o root -g rackmarshal -m 0750 /etc/rackmarshal
install -d -o rackmarshal -g rackmarshal -m 0750 /var/lib/rackmarshal /var/log/rackmarshal

if [[ ! -x /opt/rackmarshal/venv/bin/pip ]]; then
  rm -rf /opt/rackmarshal/venv
  python3 -m venv /opt/rackmarshal/venv
fi
/opt/rackmarshal/venv/bin/pip install --no-index --upgrade --force-reinstall "$WHEEL"

# Runtime code is root-owned and service-group readable, never group-writable.
# Normalize existing entries too: umask alone cannot repair an existing venv.
python3 - <<'PY_VENV_PERMISSIONS'
import grp
import os
from pathlib import Path
import stat


def raise_walk_error(error):
    raise error


def permission_plan(root, gid, owner=0):
    """Validate the entire private venv before granting the service group access."""
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('virtualenv root must be a real directory')
    paths = [root]
    for directory, dirs, files in os.walk(root, followlinks=False, onerror=raise_walk_error):
        paths.extend(Path(directory) / name for name in dirs + files)
    plan = []
    for path in sorted(paths):
        info = path.lstat()
        if info.st_uid != owner:
            raise ValueError('virtualenv entry is not owned by installer: ' + str(path))
        if stat.S_ISLNK(info.st_mode):
            # Python executables and lib64 commonly link outside/inside the venv.
            # Never chmod/chown a link or follow it into a system interpreter.
            continue
        if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
            raise ValueError('special file in virtualenv: ' + str(path))
        if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
            raise ValueError('hard-linked file in virtualenv: ' + str(path))
        mode = 0o750 if stat.S_ISDIR(info.st_mode) or info.st_mode & stat.S_IXUSR else 0o640
        plan.append((path, gid, mode))
    return plan


def apply_plan(plan):
    for path, gid, mode in plan:
        os.chown(path, -1, gid, follow_symlinks=False)
        os.chmod(path, mode, follow_symlinks=False)


if __name__ == '__main__':
    apply_plan(permission_plan('/opt/rackmarshal/venv', grp.getgrnam('rackmarshal').gr_gid))
PY_VENV_PERMISSIONS

# Exercise interpreter traversal and module imports with the actual service IDs.
python3 - <<'PY_SERVICE_ACCESS'
import grp, os, pwd, subprocess
account = pwd.getpwnam('rackmarshal')
subprocess.run(
    ['/opt/rackmarshal/venv/bin/python', '-I', '-B', '-c',
     'import rackmarshal, rackmarshal.api.v1, rackmarshal.domains.zfs.integrity'],
    check=True, timeout=30, user=account.pw_uid, group=grp.getgrnam('rackmarshal').gr_gid,
    extra_groups=[], env={'PATH': '/usr/bin:/bin'}, cwd='/',
)
PY_SERVICE_ACCESS

if [[ ! -f /etc/rackmarshal/rackmarshal.conf ]]; then
  if [[ -n "$CONFIG_SOURCE" ]]; then
    install -o root -g rackmarshal -m 0640 "$CONFIG_SOURCE" /etc/rackmarshal/rackmarshal.conf
  else
    printf '%s\n' 'SITE_NAME=rackmarshal' 'STATE_DB=/var/lib/rackmarshal/state.db' 'INSTALL_ROOT=/opt/rackmarshal' 'VENV_PYTHON=/opt/rackmarshal/venv/bin/python' 'STATUS_API_LISTEN_ADDRESS=127.0.0.1' 'STATUS_API_LISTEN_PORT=9110' > /etc/rackmarshal/rackmarshal.conf
    chown root:rackmarshal /etc/rackmarshal/rackmarshal.conf
    chmod 0640 /etc/rackmarshal/rackmarshal.conf
  fi
else
  echo "PRESERVE /etc/rackmarshal/rackmarshal.conf"
fi

export RACKMARSHAL_CONFIG=/etc/rackmarshal/rackmarshal.conf
export RACKMARSHAL_STATE_DB=/var/lib/rackmarshal/state.db
/opt/rackmarshal/venv/bin/rackmarshal validate-config --config /etc/rackmarshal/rackmarshal.conf
/opt/rackmarshal/venv/bin/python -m rackmarshal.db.migrations.migrate --apply --yes
chown rackmarshal:rackmarshal /var/lib/rackmarshal/state.db
chmod 0640 /var/lib/rackmarshal/state.db

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT_DIR="${SCRIPT_DIR%/scripts}/packaging/systemd"
for unit in rackmarshal-status.service rackmarshal-notify.service rackmarshal-notify.timer rackmarshal-domain@.service rackmarshal-domain@.timer; do
  [[ -f "$UNIT_DIR/$unit" ]] || { echo "ERROR: missing unit template $UNIT_DIR/$unit" >&2; exit 4; }
  install -o root -g root -m 0644 "$UNIT_DIR/$unit" "/etc/systemd/system/$unit"
done

# Attach result recording without enabling or replacing an optional self-watch unit.
for unit in rackmarshal-domain@.service rackmarshal-self-watch.service; do
  if [[ "$unit" == rackmarshal-self-watch.service ]] && ! systemctl cat "$unit" >/dev/null 2>&1; then
    continue
  fi
  install -d -o root -g root -m 0755 "/etc/systemd/system/$unit.d"
  install -o root -g root -m 0644 "$UNIT_DIR/$unit.d/20-cycle-health.conf" "/etc/systemd/system/$unit.d/20-cycle-health.conf"
done

systemctl daemon-reload
systemd-analyze verify /etc/systemd/system/rackmarshal-status.service /etc/systemd/system/rackmarshal-notify.service /etc/systemd/system/rackmarshal-notify.timer

if [[ "$NO_START" -eq 0 ]]; then
  systemctl enable --now rackmarshal-status.service rackmarshal-notify.timer
  ENABLED_DOMAINS="$(sed -n 's/^ENABLED_DOMAINS=//p' /etc/rackmarshal/rackmarshal.conf | tail -1 | tr ',' ' ')"
  for domain in $ENABLED_DOMAINS; do
    case "$domain" in pve|zfs|backup|ha|hardware|mount) systemctl enable --now "rackmarshal-domain@${domain}.timer" ;; *) echo "ERROR: unknown ENABLED_DOMAINS entry: $domain" >&2; exit 5 ;; esac
  done
  systemctl start rackmarshal-notify.service
  sleep 1
  systemctl is-active --quiet rackmarshal-status.service
  systemctl is-active --quiet rackmarshal-notify.timer
  [[ "$(systemctl show rackmarshal-notify.service -p Result --value)" == "success" ]]
  /opt/rackmarshal/venv/bin/python -c 'import urllib.request; r=urllib.request.urlopen("http://127.0.0.1:9110/health",timeout=5); assert r.status==200'
fi

echo "RACKMARSHAL_INSTALL_OK"
