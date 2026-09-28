#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
VERSION="$(python3 -c 'import tomllib; print(tomllib.load(open("pyproject.toml","rb"))["project"]["version"])')"
LABEL="${VERSION/rc/-rc}"
[[ -d dist ]] || { echo 'ERROR: build dist first' >&2; exit 2; }
WHEEL="$(find dist -maxdepth 1 -name "rackmarshal-${VERSION}-py3-none-any.whl" -print -quit)"
[[ -n "$WHEEL" ]] || { echo "ERROR: wheel missing for $VERSION" >&2; exit 2; }
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
B="$TMP/rackmarshal-installer-$LABEL"; mkdir -p "$B/scripts" "$B/packaging/systemd" "$B/config"
cp "$WHEEL" "$B/"
cp scripts/install.sh scripts/uninstall.sh "$B/scripts/"
cp packaging/systemd/* "$B/packaging/systemd/"
cp config/*.example* "$B/config/" 2>/dev/null || true
cp LICENSE README.md INSTALL.md CONFIGURATION.md UPGRADE.md UNINSTALL.md SECURITY.md CHANGELOG.md "$B/"
tar -C "$TMP" -czf "dist/rackmarshal-installer-$LABEL.tar.gz" "rackmarshal-installer-$LABEL"
echo "dist/rackmarshal-installer-$LABEL.tar.gz"
