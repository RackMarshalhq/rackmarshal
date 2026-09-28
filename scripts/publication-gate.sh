#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"
fail=0
patterns='192\.168\.|10\.[0-9]+\.[0-9]+\.[0-9]+|172\.(1[6-9]|2[0-9]|3[01])\.[0-9]+\.[0-9]+|Michael|Olivia|Preston|ms01|/backupssd|/backuppool|/opt/homelab-ops|/etc/homelab-ops|BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY'
paths=(rackmarshal config packaging tests README.md INSTALL.md CONFIGURATION.md UPGRADE.md UNINSTALL.md SECURITY.md CONTRIBUTING.md CHANGELOG.md LICENSE pyproject.toml)
if grep -RIE "$patterns" "${paths[@]}"; then echo 'FAIL: site/private pattern found'; fail=1; fi
if find . -path './.git' -prune -o -path './internal' -prune -o -type f \( -name '*.env' -o -name '*.pem' -o -name '*.key' -o -name '*.db' -o -name '*.sqlite' \) -print | grep .; then echo 'FAIL: forbidden file type'; fail=1; fi
grep -RIE "$patterns" scripts --exclude=publication-gate.sh && { echo 'FAIL: site/private pattern found in scripts'; fail=1; } || true
python3 -m unittest discover -s tests -v
python3 tests/staging_smoke.py
python3 -m compileall -q rackmarshal
[[ $fail -eq 0 ]] || exit 1
echo PUBLICATION_GATE_PASS
