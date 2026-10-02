#!/usr/bin/env python3
"""Build deterministic local marketplace or private hosted Investigator packages."""
import argparse
import json
import os
import re
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def build(surface, output, app_id=None):
    output = Path(output).resolve()
    if surface == "cloud":
        if not app_id or not re.fullmatch(r"asdk_app_[a-z0-9]{32}", app_id):
            raise ValueError("Cloud builds require a registered app ID.")
        if output.is_relative_to(ROOT):
            raise ValueError("Private cloud packages must be written outside the public repository.")
    elif app_id:
        raise ValueError("Local packages cannot include a private app binding.")
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    manifest = json.loads((ROOT / ".codex-plugin/plugin.json").read_text())
    manifest["version"] = version.replace("rc", "-rc")
    files = {"skills/rackmarshal-investigator/SKILL.md":
             (ROOT / "skills/rackmarshal-investigator/SKILL.md").read_bytes()}
    if surface == "cloud":
        manifest.pop("mcpServers", None)
        manifest["apps"] = "./.app.json"
        files["skills/rackmarshal-investigator/SKILL.md"] += ("\n## Business connection binding\n\nUse the existing RackMarshal Investigator app (" + app_id + ") for all RackMarshal tool calls. If that app is unavailable, report the missing connection; do not substitute other infrastructure tools or direct access.\n").encode()
        files["skills/rackmarshal-investigator/agents/openai.yaml"] = ("dependencies:\n  tools:\n    - type: \"mcp\"\n      value: \"" + app_id + "\"\n      description: \"Existing read-only RackMarshal connection\"\n").encode()
        files[".app.json"] = json.dumps({"apps": {"rackmarshal": {"id": app_id, "required": True}}}, indent=2).encode()
    else:
        files[".mcp.json"] = (ROOT / ".mcp.json").read_bytes()
    files[".codex-plugin/plugin.json"] = json.dumps(manifest, indent=2).encode()
    if surface == "local":
        prefix = "plugins/rackmarshal-investigator/"
        files = {prefix + key: value for key, value in files.items()}
        files[".agents/plugins/marketplace.json"] = json.dumps({
            "name": "rackmarshal-local",
            "interface": {"displayName": "RackMarshal"},
            "plugins": [{"name": "rackmarshal-investigator",
                "source": {"source": "local", "path": "./plugins/rackmarshal-investigator"},
                "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                "category": "Productivity"}]}, indent=2).encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    # Never follow an existing output symlink or overwrite an artifact.
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600 if surface == "cloud" else 0o644)
    with os.fdopen(fd, "wb") as stream, zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            entry = zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, data)
    return len(files)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--surface", choices=("local", "cloud"), required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--app-id")
    args = parser.parse_args()
    try:
        count = build(args.surface, args.output, args.app_id)
    except (ValueError, OSError):
        parser.exit(2, "Build refused: check surface, private output location and registered binding.\n")
    print(json.dumps({"result": "PASS", "surface": args.surface, "files": count}))
if __name__ == "__main__":
    main()
