#!/usr/bin/env bash
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "ERROR: run as root" >&2; exit 1; }
LAST_FILE="/var/lib/rackmarshal-migration/LAST"
[[ -f "$LAST_FILE" ]] || { echo "ERROR: no migration checkpoint" >&2; exit 2; }
MIGRATION_DIR="$(cat "$LAST_FILE")"
[[ -d "$MIGRATION_DIR" ]] || { echo "ERROR: checkpoint missing" >&2; exit 2; }

systemctl disable --now rackmarshal-status.service rackmarshal-notify.timer rackmarshal-local-ai-explain.timer rackmarshal-self-watch.timer rackmarshal-db-snapshot.timer rackmarshal-evidence-export.timer rackmarshal-observation-prune.timer 2>/dev/null || true
for d in pve zfs backup ha hardware mount; do
  systemctl disable --now "rackmarshal-domain@$d.timer" 2>/dev/null || true
  systemctl stop "rackmarshal-domain@$d.service" 2>/dev/null || true
done
systemctl stop rackmarshal-notify.service rackmarshal-local-ai-explain.service rackmarshal-self-watch.service rackmarshal-db-snapshot.service rackmarshal-evidence-export.service rackmarshal-observation-prune.service 2>/dev/null || true

while IFS= read -r unit; do
  [[ -n "$unit" ]] || continue
  systemctl enable "$unit" 2>/dev/null || true
done < "$MIGRATION_DIR/enabled-units.txt"

if [[ -f "$MIGRATION_DIR/enabled-services.txt" ]]; then
  while IFS= read -r unit; do
    [[ -n "$unit" ]] || continue
    systemctl enable "$unit" 2>/dev/null || true
    # Start normally first. On an intentionally network-isolated recovery host, an
    # enabled legacy service can remain queued behind network-online.target forever.
    # If so, cancel only that queued job and launch its recorded ExecStart transiently.
    # The installed unit is not edited, so normal production boot semantics remain.
    systemctl start --no-block "$unit" 2>/dev/null || true
    sleep 0.25
    if ! systemctl is-active --quiet "$unit"; then
      systemctl cancel "$unit" 2>/dev/null || true
      cmd="$(systemctl show "$unit" -p ExecStart --value | sed -n 's/.*argv\[\]=\([^;]*\) ;.*/\1/p')"
      [[ -n "$cmd" ]] && systemd-run --unit="rackmarshal-rollback-${unit%.service}" --collect /bin/sh -c "exec $cmd" >/dev/null
    fi
  done < "$MIGRATION_DIR/enabled-services.txt"
fi

while IFS= read -r unit; do
  [[ -n "$unit" ]] || continue
  systemctl start --no-block "$unit" 2>/dev/null || true
done < "$MIGRATION_DIR/active-units.txt"

if systemctl list-unit-files homelabops-status-api.service --no-legend 2>/dev/null | grep -q homelabops-status-api; then
  for _ in {1..20}; do
    systemctl is-active --quiet homelabops-status-api.service && break
    sleep 0.25
  done
  systemctl is-active --quiet homelabops-status-api.service
fi

if [[ -f /var/lib/homelab-ops/state.db ]]; then
  sqlite3 /var/lib/homelab-ops/state.db 'pragma quick_check;' | grep -qx ok
fi

echo "RACKMARSHAL_HOMELABOPS_ROLLBACK_OK checkpoint=$MIGRATION_DIR"
