#!/usr/bin/env bash
set -euo pipefail

PURGE=0
[[ "${1:-}" == "--purge" ]] && PURGE=1
[[ $EUID -eq 0 ]] || { echo "ERROR: run as root" >&2; exit 1; }

systemctl disable --now rackmarshal-status.service rackmarshal-notify.timer 2>/dev/null || true
systemctl stop rackmarshal-notify.service 2>/dev/null || true
rm -f /etc/systemd/system/rackmarshal-status.service
rm -f /etc/systemd/system/rackmarshal-notify.service
rm -f /etc/systemd/system/rackmarshal-notify.timer
systemctl daemon-reload
rm -rf /opt/rackmarshal

if [[ "$PURGE" -eq 1 ]]; then
  rm -rf /etc/rackmarshal /var/lib/rackmarshal /var/log/rackmarshal
  userdel rackmarshal 2>/dev/null || true
  groupdel rackmarshal 2>/dev/null || true
  echo "RACKMARSHAL_PURGE_OK"
else
  echo "RACKMARSHAL_UNINSTALL_OK state_and_config_preserved"
fi
