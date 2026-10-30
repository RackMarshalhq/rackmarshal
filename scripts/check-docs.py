#!/usr/bin/env python3
"""Fail if the user-facing docs promise something the code does not provide.

Checks, for README.md, TESTING.md, INSTALL.md, CONFIGURATION.md and docs/QUICKSTART.md:
  1. relative Markdown links resolve to files in the repository;
  2. every `rackmarshal <subcommand>` shown in the docs is a real CLI subcommand;
  3. every rackmarshal-domain@<name> unit names a real domain;
  4. every config KEY=value line in the quickstart is documented in CONFIGURATION.md
     or the example config.
Run from anywhere: python3 scripts/check-docs.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ["README.md", "TESTING.md", "INSTALL.md", "CONFIGURATION.md", "docs/QUICKSTART.md"]
GITHUB_RELATIVE = ("../../issues", "../../security", "../../pulls")


def cli_subcommands():
    text = (ROOT / "rackmarshal" / "cli.py").read_text(encoding="utf-8")
    return set(re.findall(r'add_parser\("([a-z][a-z-]*)"', text))


def domains():
    text = (ROOT / "rackmarshal" / "cli.py").read_text(encoding="utf-8")
    m = re.search(r"DOMAINS\s*=\s*[\(\[]([^\)\]]*)[\)\]]", text)
    return set(re.findall(r'"([a-z]+)"', m.group(1))) if m else set()


def main():
    errors = []
    subs, doms = cli_subcommands(), domains()
    if not subs:
        errors.append("could not read CLI subcommands from rackmarshal/cli.py")
    if not doms:
        errors.append("could not read DOMAINS from rackmarshal/cli.py")
    documented_keys = (ROOT / "CONFIGURATION.md").read_text(encoding="utf-8")
    example = ROOT / "config" / "rackmarshal.conf.example"
    if example.exists():
        documented_keys += example.read_text(encoding="utf-8")
    for rel in DOCS:
        path = ROOT / rel
        if not path.exists():
            errors.append(f"{rel}: file missing")
            continue
        text = path.read_text(encoding="utf-8")
        for target in re.findall(r"\]\(([^)\s]+)\)", text):
            if re.match(r"[a-z]+:", target) or target.startswith("#"):
                continue
            if target.startswith(GITHUB_RELATIVE):
                continue
            dest = (path.parent / target.split("#")[0]).resolve()
            if not dest.exists():
                errors.append(f"{rel}: broken link -> {target}")
        for sub in re.findall(r"(?:^|`|\$\s|sudo\s)rackmarshal\s+([a-z][a-z-]+)\b", text, flags=re.M):
            if sub not in subs:
                errors.append(f"{rel}: documents `rackmarshal {sub}`, which is not a CLI subcommand")
        for name in re.findall(r"rackmarshal-domain@([a-z]+)", text):
            if name not in doms:
                errors.append(f"{rel}: unit rackmarshal-domain@{name} names an unknown domain")
    quick = (ROOT / "docs" / "QUICKSTART.md").read_text(encoding="utf-8") if (ROOT / "docs" / "QUICKSTART.md").exists() else ""
    for key in re.findall(r"^\s*([A-Z][A-Z0-9_]{2,})=", quick, flags=re.M):
        if key not in documented_keys:
            errors.append(f"docs/QUICKSTART.md: config key {key} is not documented in CONFIGURATION.md or the example config")
    if errors:
        print("DOCS CHECK FAILED")
        for e in errors:
            print(" -", e)
        return 1
    print(f"DOCS CHECK PASSED ({len(DOCS)} files, {len(subs)} CLI subcommands, {len(doms)} domains)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
