#!/usr/bin/env bash
set -euo pipefail

WHEEL=""
SOURCE_ETC="/etc/homelab-ops"
SOURCE_STATE="/var/lib/homelab-ops/state.db"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALLER="$SCRIPT_DIR/install.sh"

usage() {
  echo "Usage: migrate-from-homelabops.sh --wheel /path/to/rackmarshal.whl"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --wheel) WHEEL="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done
[[ $EUID -eq 0 ]] || { echo "ERROR: run as root" >&2; exit 1; }
[[ -f "$WHEEL" ]] || { echo "ERROR: wheel not found" >&2; exit 2; }
[[ -x "$INSTALLER" ]] || { echo "ERROR: installer not found" >&2; exit 2; }
[[ -f "$SOURCE_ETC/homelabops.conf" ]] || { echo "ERROR: source config missing" >&2; exit 3; }
[[ -f "$SOURCE_STATE" ]] || { echo "ERROR: source state DB missing" >&2; exit 3; }
command -v sqlite3 >/dev/null || { echo "ERROR: sqlite3 required for migration verification" >&2; exit 3; }

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
MIGRATION_DIR="/var/lib/rackmarshal-migration/$STAMP"
mkdir -p "$MIGRATION_DIR"
chmod 0700 "$MIGRATION_DIR"

systemctl list-unit-files 'homelabops-*' --no-legend 2>/dev/null |
  awk '$2=="enabled"{print $1}' > "$MIGRATION_DIR/enabled-units.txt" || true
systemctl list-units 'homelabops-*' --state=active --no-legend 2>/dev/null |
  awk '{print $1}' > "$MIGRATION_DIR/active-units.txt" || true

cp -a "$SOURCE_ETC" "$MIGRATION_DIR/source-etc"
cp -a "$SOURCE_STATE" "$MIGRATION_DIR/source-state.db"
sha256sum "$SOURCE_STATE" > "$MIGRATION_DIR/source-state.sha256"
mapfile -t OLD_TIMERS < <(
  systemctl list-unit-files 'homelabops-*.timer' --no-legend 2>/dev/null |
    awk '{print $1}'
)
for unit in "${OLD_TIMERS[@]}"; do
  systemctl disable --now "$unit" 2>/dev/null || true
done
while IFS= read -r unit; do
  [[ -n "$unit" ]] || continue
  systemctl stop "$unit" 2>/dev/null || true
done < "$MIGRATION_DIR/active-units.txt"

TMP_CONFIG="$(mktemp)"
trap 'rm -f "$TMP_CONFIG"' EXIT
cp "$SOURCE_ETC/homelabops.conf" "$TMP_CONFIG"
sed -i   -e 's#/etc/homelab-ops#/etc/rackmarshal#g'   -e 's#/var/lib/homelab-ops/state.db#/var/lib/rackmarshal/state.db#g'   -e 's#/opt/homelab-ops#/opt/rackmarshal#g'   "$TMP_CONFIG"

domains=()
for d in pve zfs backup ha hardware mount; do
  if grep -qx "homelabops-$d-cycle.timer" "$MIGRATION_DIR/enabled-units.txt"; then
    domains+=("$d")
  fi
done
if ! grep -q '^ENABLED_DOMAINS=' "$TMP_CONFIG"; then
  printf '\nENABLED_DOMAINS=%s\n' "$(IFS=,; echo "${domains[*]}")" >> "$TMP_CONFIG"
fi

"$INSTALLER" --wheel "$WHEEL" --config "$TMP_CONFIG" --no-start

cp -a "$SOURCE_ETC/." /etc/rackmarshal/
mv -f /etc/rackmarshal/homelabops.conf /etc/rackmarshal/rackmarshal.conf
sed -i   -e 's#/etc/homelab-ops#/etc/rackmarshal#g'   -e 's#/var/lib/homelab-ops/state.db#/var/lib/rackmarshal/state.db#g'   -e 's#/opt/homelab-ops#/opt/rackmarshal#g'   /etc/rackmarshal/rackmarshal.conf
if ! grep -q '^ENABLED_DOMAINS=' /etc/rackmarshal/rackmarshal.conf; then
  printf '\nENABLED_DOMAINS=%s\n' "$(IFS=,; echo "${domains[*]}")" >> /etc/rackmarshal/rackmarshal.conf
fi
chown -R root:rackmarshal /etc/rackmarshal
find /etc/rackmarshal -type d -exec chmod 0750 {} +
find /etc/rackmarshal -type f -exec chmod 0640 {} +
install -o rackmarshal -g rackmarshal -m 0640 "$SOURCE_STATE" /var/lib/rackmarshal/state.db
export RACKMARSHAL_CONFIG=/etc/rackmarshal/rackmarshal.conf
export RACKMARSHAL_STATE_DB=/var/lib/rackmarshal/state.db
/opt/rackmarshal/venv/bin/rackmarshal validate-config --config /etc/rackmarshal/rackmarshal.conf
/opt/rackmarshal/venv/bin/python -m rackmarshal.db.migrations.migrate --apply --yes

systemctl daemon-reload
systemctl enable --now rackmarshal-status.service rackmarshal-notify.timer
for d in "${domains[@]}"; do
  systemctl enable --now "rackmarshal-domain@$d.timer"
done
ai="$(sed -n 's/^LOCAL_AI_ENABLED=//p' /etc/rackmarshal/rackmarshal.conf | tail -1 | tr '[:upper:]' '[:lower:]')"
case "$ai" in
  1|true|yes|on) systemctl enable --now rackmarshal-local-ai-explain.timer ;;
esac
systemctl start rackmarshal-notify.service
sleep 1
/opt/rackmarshal/venv/bin/python -c 'import urllib.request; r=urllib.request.urlopen("http://127.0.0.1:9110/health",timeout=5); assert r.status==200'
sqlite3 /var/lib/rackmarshal/state.db 'pragma quick_check;' | grep -qx ok
printf '%s\n' "$MIGRATION_DIR" > /var/lib/rackmarshal-migration/LAST
echo "RACKMARSHAL_HOMELABOPS_MIGRATION_OK backup=$MIGRATION_DIR"
