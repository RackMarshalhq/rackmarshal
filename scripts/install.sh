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

# Fresh installs only: do not execute or repair code in an existing installation.
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
unset PYTHONPATH PYTHONHOME VIRTUAL_ENV BASH_ENV ENV
for cmd in python3 systemctl systemd-analyze install getent groupadd useradd; do
  command -v "$cmd" >/dev/null || { echo "ERROR: missing prerequisite: $cmd; provision it separately" >&2; exit 3; }
done
python3 -I -B -c 'import sys, venv; sys.exit(0 if sys.version_info >= (3,11) else 1)' || { echo 'ERROR: Python >=3.11 with venv is required; provision it separately' >&2; exit 3; }
for path in /opt/rackmarshal /etc/rackmarshal /var/lib/rackmarshal /var/log/rackmarshal; do
  [[ ! -e "$path" && ! -L "$path" ]] || { echo "ERROR: existing installation is unsupported; preserve and review: $path" >&2; exit 3; }
done
if getent passwd rackmarshal >/dev/null || getent group rackmarshal >/dev/null; then
  echo 'ERROR: existing service account/group; upgrade/rollback is not qualified' >&2; exit 3
fi
for listing in list-unit-files list-units; do
  output="$(systemctl "$listing" --all --plain --no-legend --no-pager)" || { echo 'ERROR: unit inventory unavailable' >&2; exit 3; }
  while read -r unit rest; do
    [[ "$unit" != rackmarshal* ]] || { echo 'ERROR: existing RackMarshal unit; preserve and review' >&2; exit 3; }
  done <<< "$output"
done
shopt -s nullglob dotglob
existing_units=(/etc/systemd/system/rackmarshal* /run/systemd/system/rackmarshal* /usr/lib/systemd/system/rackmarshal* /lib/systemd/system/rackmarshal*)
[[ ${#existing_units[@]} == 0 ]] || { echo 'ERROR: existing RackMarshal unit/drop-in paths' >&2; exit 3; }
shopt -u nullglob dotglob
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLE_ROOT="${SCRIPT_DIR%/scripts}"
prepare_args=(--bundle "$BUNDLE_ROOT" --wheel "$WHEEL")
[[ -z "$CONFIG_SOURCE" ]] || prepare_args+=(--config "$CONFIG_SOURCE")
# Validate/copy all bundle inputs before accounts, install paths or database writes.
STAGE="$(python3 -I -B "$SCRIPT_DIR/bootstrap-wheel.py" prepare "${prepare_args[@]}")"
echo "Private installation evidence: $STAGE"
finish() {
  rc=$?
  trap - EXIT
  printf 'exit_code=%s\n' "$rc" > "$STAGE/installer-exit.txt"
  if [[ $rc -ne 0 ]]; then echo 'STOP: partial fresh installation retained; no automatic retry, recreation or rollback' >&2; fi
  exit "$rc"
}
trap finish EXIT
# Probe only pip-less venv support. No ensurepip, pip, APT or network operation.
python3 -I -B -m venv --without-pip "$STAGE/prerequisite-venv"
"$STAGE/prerequisite-venv/bin/python" -I -B -c 'import sys; assert sys.prefix != sys.base_prefix'
groupadd --system rackmarshal
useradd --system --gid rackmarshal --home-dir /var/lib/rackmarshal --shell /usr/sbin/nologin rackmarshal
install -d -o root -g root -m 0755 /opt/rackmarshal
install -d -o root -g rackmarshal -m 0750 /etc/rackmarshal
install -d -o rackmarshal -g rackmarshal -m 0750 /var/lib/rackmarshal /var/log/rackmarshal
python3 -I -B -m venv --without-pip /opt/rackmarshal/venv
# Some Python builds ship venv helper scripts as 0777; the installer refuses group/other-writable entries.
# The venv was created a moment ago by root, so removing those bits here is safe.
chmod -R go-w /opt/rackmarshal/venv
python3 -I -B "$STAGE/scripts/bootstrap-wheel.py" install --stage "$STAGE"
[[ -z "$CONFIG_SOURCE" ]] || CONFIG_SOURCE="$STAGE/supplied.conf"
SCRIPT_DIR="$STAGE/scripts"

# Runtime code is root-owned and service-group readable, never group-writable.
# Normalize existing entries too: umask alone cannot repair an existing venv.
python3 -I -B - <<'PY_VENV_PERMISSIONS'
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
python3 -I -B - <<'PY_SERVICE_ACCESS'
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
/opt/rackmarshal/venv/bin/python -I -B -m rackmarshal.cli validate-config --config /etc/rackmarshal/rackmarshal.conf
/opt/rackmarshal/venv/bin/python -I -B -m rackmarshal.db.migrations.migrate --apply --yes
chown rackmarshal:rackmarshal /var/lib/rackmarshal/state.db
chmod 0640 /var/lib/rackmarshal/state.db

UNIT_DIR="${SCRIPT_DIR%/scripts}/packaging/systemd"
for unit in rackmarshal-status.service rackmarshal-notify.service rackmarshal-notify.timer rackmarshal-db-snapshot.service rackmarshal-db-snapshot.timer rackmarshal-observation-prune.service rackmarshal-observation-prune.timer rackmarshal-domain@.service rackmarshal-domain@.timer; do
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
systemd-analyze verify /etc/systemd/system/rackmarshal-status.service /etc/systemd/system/rackmarshal-notify.service /etc/systemd/system/rackmarshal-notify.timer /etc/systemd/system/rackmarshal-db-snapshot.service /etc/systemd/system/rackmarshal-db-snapshot.timer /etc/systemd/system/rackmarshal-observation-prune.service /etc/systemd/system/rackmarshal-observation-prune.timer

if [[ "$NO_START" -eq 0 ]]; then
  systemctl enable --now rackmarshal-status.service rackmarshal-notify.timer rackmarshal-db-snapshot.timer rackmarshal-observation-prune.timer
  ENABLED_DOMAINS="$(sed -n 's/^ENABLED_DOMAINS=//p' /etc/rackmarshal/rackmarshal.conf | tail -1 | tr ',' ' ')"
  for domain in $ENABLED_DOMAINS; do
    case "$domain" in pve|zfs|backup|ha|hardware|mount) systemctl enable --now "rackmarshal-domain@${domain}.timer" ;; *) echo "ERROR: unknown ENABLED_DOMAINS entry: $domain" >&2; exit 5 ;; esac
  done
  systemctl start rackmarshal-notify.service
  systemctl start rackmarshal-db-snapshot.service
  sleep 1
  systemctl is-active --quiet rackmarshal-status.service
  systemctl is-active --quiet rackmarshal-notify.timer
  systemctl is-active --quiet rackmarshal-db-snapshot.timer
  systemctl is-active --quiet rackmarshal-observation-prune.timer
  [[ "$(systemctl show rackmarshal-notify.service -p Result --value)" == "success" ]]
  [[ "$(systemctl show rackmarshal-db-snapshot.service -p Result --value)" == "success" ]]
  /opt/rackmarshal/venv/bin/python -I -B -c 'import urllib.request; r=urllib.request.urlopen("http://127.0.0.1:9110/health",timeout=5); assert r.status==200'
fi

echo "RACKMARSHAL_INSTALL_OK"
