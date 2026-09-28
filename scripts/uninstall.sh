#!/usr/bin/env bash
set -euo pipefail

PURGE=0
[[ "${1:-}" == "--purge" ]] && PURGE=1
[[ $EUID -eq 0 ]] || { echo "ERROR: run as root" >&2; exit 1; }

systemctl disable --now rackmarshal-status.service rackmarshal-notify.timer rackmarshal-local-ai-explain.timer rackmarshal-self-watch.timer rackmarshal-db-snapshot.timer rackmarshal-evidence-export.timer rackmarshal-observation-prune.timer 2>/dev/null || true
systemctl stop rackmarshal-local-ai-explain.service rackmarshal-self-watch.service rackmarshal-db-snapshot.service rackmarshal-evidence-export.service rackmarshal-observation-prune.service 2>/dev/null || true
for d in pve zfs backup ha hardware mount; do systemctl disable --now "rackmarshal-domain@${d}.timer" 2>/dev/null || true; systemctl stop "rackmarshal-domain@${d}.service" 2>/dev/null || true; done
systemctl stop rackmarshal-notify.service 2>/dev/null || true
rm -f /etc/systemd/system/rackmarshal-status.service
rm -f /etc/systemd/system/rackmarshal-notify.service
rm -f /etc/systemd/system/rackmarshal-notify.timer
rm -f /etc/systemd/system/rackmarshal-domain@.service /etc/systemd/system/rackmarshal-domain@.timer
rm -f /etc/systemd/system/rackmarshal-local-ai-explain.service /etc/systemd/system/rackmarshal-local-ai-explain.timer
rm -f /etc/systemd/system/rackmarshal-self-watch.service /etc/systemd/system/rackmarshal-self-watch.timer
rm -f /etc/systemd/system/rackmarshal-db-snapshot.service /etc/systemd/system/rackmarshal-db-snapshot.timer
rm -f /etc/systemd/system/rackmarshal-evidence-export.service /etc/systemd/system/rackmarshal-evidence-export.timer
rm -f /etc/systemd/system/rackmarshal-observation-prune.service /etc/systemd/system/rackmarshal-observation-prune.timer
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
