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
cp -R packaging/systemd/* "$B/packaging/systemd/"
cp config/*.example* "$B/config/" 2>/dev/null || true
cp LICENSE README.md INSTALL.md CONFIGURATION.md UPGRADE.md UNINSTALL.md SECURITY.md CHANGELOG.md "$B/"
SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-$(git log -1 --format=%ct)}"
tar --sort=name --mtime="@$SOURCE_DATE_EPOCH" --owner=0 --group=0 --numeric-owner -C "$TMP" -cf - "rackmarshal-installer-$LABEL" | gzip -n > "dist/rackmarshal-installer-$LABEL.tar.gz"
echo "dist/rackmarshal-installer-$LABEL.tar.gz"
