#!/usr/bin/env python3
"""Pinned, code-only package promotion. No dependencies, schemas, or config writes."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
from urllib.parse import urlsplit
from urllib.error import HTTPError
from urllib.request import urlopen

ASSETS = {
    "acceptance/prove-incident-narrative.py": "scripts/prove-incident-narrative.py",
    "acceptance/investigator-live-eval.py": "rackmarshal/agent/live_eval.py",
    "acceptance/suite.json": "evals/investigator_v1_1_live.json",
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def child(root, relative):
    root = Path(root).resolve()
    path = Path(relative)
    if path.is_absolute() or not path.parts or any(p in ("..", ".") for p in path.parts):
        raise ValueError("Invalid relative path")
    result = root
    for part in path.parts:
        result = result / part
        if result.is_symlink():
            raise ValueError("Symlink paths are not supported")
    return result


def code_path(path):
    parts = Path(path).parts
    if len(parts) < 2 or parts[0] != "rackmarshal" or not path.endswith(".py"):
        raise ValueError("Select only rackmarshal Python source files")
    if parts[1:3] == ("db", "migrations"):
        raise ValueError("Migrations require the release upgrade procedure")
    child(Path.cwd(), path)
    return str(Path(*parts[1:]))


def write_json(path, data):
    path = Path(path)
    temporary = path.with_name(path.name + ".new")
    with temporary.open("w") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def prepare(repo, revision, files, destination):
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Use an explicit full Git commit SHA")
    def git(*args):
        return subprocess.check_output(["git", "-C", str(repo), *args])
    if git("cat-file", "-t", revision).strip() != b"commit":
        raise ValueError("Revision must be a commit")
    selected = sorted(set(files))
    if not selected:
        raise ValueError("Select at least one source file")
    sources = [("files/" + code_path(p), p) for p in selected] + list(ASSETS.items())
    # Read committed blobs before creating output: the working tree is never input.
    blobs = [(target, git("show", revision + ":" + source)) for target, source in sources]
    destination = Path(destination)
    destination.mkdir(mode=0o700)
    manifest = {"format": 1, "revision": revision, "files": {}, "assets": {}}
    for relative, contents in blobs:
        path = child(destination, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
        if relative.endswith(".py"):
            compile(contents, relative, "exec")
        group = "files" if relative.startswith("files/") else "assets"
        key = relative[6:] if group == "files" else relative
        manifest[group][key] = digest(path)
    write_json(destination / "manifest.json", manifest)
    return validate_bundle(destination)


def validate_bundle(bundle):
    bundle = Path(bundle).resolve()
    manifest = json.loads(child(bundle, "manifest.json").read_text())
    if manifest.get("format") != 1 or not re.fullmatch(r"[0-9a-f]{40}", manifest.get("revision", "")):
        raise ValueError("Unsupported manifest")
    if not manifest.get("files") or set(manifest.get("assets", {})) != set(ASSETS):
        raise ValueError("Incomplete bundle")
    for relative, checksum in manifest["files"].items():
        code_path("rackmarshal/" + relative)
        path = child(bundle, "files/" + relative)
        if digest(path) != checksum:
            raise ValueError("Source checksum mismatch: " + relative)
        compile(path.read_bytes(), relative, "exec")
    for relative, checksum in manifest["assets"].items():
        if digest(child(bundle, relative)) != checksum:
            raise ValueError("Acceptance checksum mismatch: " + relative)
    return manifest


def plan(bundle, roots):
    manifest = validate_bundle(bundle)
    resolved = {name: Path(root).resolve() for name, root in roots.items()}
    if set(resolved) != {"status", "mcp"} or len(set(resolved.values())) != 2:
        raise ValueError("Two distinct installed package roots are required")
    entries = []
    for name, root in resolved.items():
        if not root.is_dir():
            raise ValueError("Installed package root is missing")
        for relative, checksum in manifest["files"].items():
            path = child(root, relative)
            if path.exists() and not path.is_file():
                raise ValueError("Target is not a regular file")
            old = digest(path) if path.exists() else None
            if old != checksum:
                entries.append({"installation": name, "path": relative, "before": old, "after": checksum})
    return manifest, resolved, entries


def replace_file(source, destination, metadata=None):
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".rackmarshal-promote-", dir=destination.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(Path(source).read_bytes())
            handle.flush()
            os.fchmod(handle.fileno(), metadata["mode"] if metadata else 0o644)
            if metadata and os.geteuid() == 0:
                os.fchown(handle.fileno(), metadata["uid"], metadata["gid"])
            os.fsync(handle.fileno())
        temporary.replace(destination)
        # A rollback can occur within the timestamp resolution of .pyc headers.
        # Remove only this module's caches so restored source is always loaded.
        cache = destination.parent / "__pycache__"
        if cache.is_symlink():
            raise ValueError("Symlink bytecode cache is not supported")
        for compiled in cache.glob(destination.stem + ".*.pyc"):
            compiled.unlink()
        descriptor = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        temporary.unlink(missing_ok=True)


def restore_files(transaction, journal):
    for entry in reversed(journal["entries"]):
        target = child(journal["roots"][entry["installation"]], entry["path"])
        current = digest(target) if target.exists() else None
        if current not in (entry["before"], entry["after"]):
            raise RuntimeError("Rollback refused: target changed since promotion")
        if entry["before"] is None:
            target.unlink(missing_ok=True)
        else:
            backup = child(transaction, "originals/" + entry["installation"] + "/" + entry["path"])
            if digest(backup) != entry["before"]:
                raise RuntimeError("Rollback backup checksum mismatch")
            replace_file(backup, target, entry["metadata"])
        restored = digest(target) if target.exists() else None
        if restored != entry["before"]:
            raise RuntimeError("Rollback verification failed")


def promote(bundle, roots, backups, runtime, acceptance):
    manifest, roots, entries = plan(bundle, roots)
    if not entries:
        return {"state": "UNCHANGED", "revision": manifest["revision"], "changed_files": 0}
    backups = Path(backups).resolve()
    if any(backups.is_relative_to(root) for root in roots.values()):
        raise ValueError("Backups must be outside the installed packages")
    backups.mkdir(parents=True, exist_ok=True)
    transaction = Path(tempfile.mkdtemp(prefix=manifest["revision"][:12] + "-", dir=backups))
    journal = {"format": 1, "revision": manifest["revision"], "state": "PREPARED",
               "roots": {name: str(root) for name, root in roots.items()}, "entries": entries,
               "runtime": runtime.snapshot(), "transaction": str(transaction)}
    for entry in entries:
        target = child(roots[entry["installation"]], entry["path"])
        if entry["before"] is not None:
            st = target.stat()
            entry["metadata"] = {"mode": st.st_mode & 0o777, "uid": st.st_uid, "gid": st.st_gid}
            backup = child(transaction, "originals/" + entry["installation"] + "/" + entry["path"])
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup)
            if digest(backup) != entry["before"]:
                raise RuntimeError("Backup verification failed")
    journal_path = transaction / "transaction.json"
    write_json(journal_path, journal)
    try:
        runtime.quiesce(journal["runtime"])
        journal["state"] = "APPLYING"
        write_json(journal_path, journal)
        for entry in entries:
            target = child(roots[entry["installation"]], entry["path"])
            if (digest(target) if target.exists() else None) != entry["before"]:
                raise RuntimeError("Target changed after preflight")
            replace_file(child(bundle, "files/" + entry["path"]), target, entry.get("metadata"))
        for root in roots.values():
            for relative, checksum in manifest["files"].items():
                if digest(child(root, relative)) != checksum:
                    raise RuntimeError("Installed checksum mismatch")
        journal["state"] = "INSTALLED"
        write_json(journal_path, journal)
        runtime.start_apps(journal["runtime"])
        acceptance(transaction)
        runtime.resume(journal["runtime"])
        journal["state"] = "ACCEPTED"
        write_json(journal_path, journal)
    except Exception as exc:
        journal["error"] = str(exc)
        try:
            runtime.quiesce(journal["runtime"])
            restore_files(transaction, journal)
            runtime.start_apps(journal["runtime"])
            runtime.resume(journal["runtime"])
            journal["state"] = "ROLLED_BACK"
        except Exception as rollback_error:
            journal["state"] = "ROLLBACK_FAILED"
            journal["rollback_error"] = str(rollback_error)
        write_json(journal_path, journal)
        raise RuntimeError("Promotion failed; " + journal["state"] + "; journal=" + str(journal_path)) from exc
    return {"state": journal["state"], "revision": manifest["revision"],
            "changed_files": len(entries), "transaction": str(transaction)}


def local_url(url):
    parsed = urlsplit(url)
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "::1") or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Acceptance endpoints must be unauthenticated loopback HTTP URLs")
    return url.rstrip("/")


def wait_ready(urls, timeout, mcp_url=None):
    deadline = time.monotonic() + timeout
    pending = list(dict.fromkeys(list(urls) + ([mcp_url] if mcp_url else [])))
    while pending:
        for url in pending[:]:
            try:
                with urlopen(url, timeout=min(2, max(0.1, deadline - time.monotonic()))) as response:
                    if response.status == 200:
                        pending.remove(url)
            except HTTPError as exc:
                # Streamable HTTP GET may reject the method/Accept header even
                # when the MCP listener is ready. The full protocol eval follows.
                if url == mcp_url and exc.code in (405, 406):
                    pending.remove(url)
                exc.close()
            except (OSError, ValueError):
                pass
        if pending and time.monotonic() >= deadline:
            raise RuntimeError("Readiness timeout: " + ", ".join(pending))
        if pending:
            time.sleep(0.25)


class SystemdRuntime:
    def __init__(self, ready_urls, timeout, mcp_url):
        self.ready_urls, self.timeout, self.mcp_url = ready_urls, timeout, mcp_url

    def command(self, *args):
        return subprocess.check_output(["systemctl", *args], text=True, timeout=30)

    def snapshot(self):
        rows = self.command("list-units", "--all", "--plain", "--no-legend", "rackmarshal*.service", "rackmarshal*.timer")
        names = {line.split()[0] for line in rows.splitlines()}
        for name in list(names):
            if name.endswith(".timer"):
                target = self.command("show", name, "--property=Unit", "--value").strip()
                if not target.startswith("rackmarshal") or not target.endswith(".service"):
                    raise ValueError("Unexpected timer service target")
                names.add(target)
        names.discard("rackmarshal-tunnel.service")
        units = []
        for name in sorted(names):
            info = self.command("show", name, "--property=ActiveState,Type")
            data = dict(item.split("=", 1) for item in info.strip().splitlines())
            units.append({"name": name, "oneshot": data.get("Type") == "oneshot",
                          "active": data["ActiveState"] in ("active", "activating", "reloading")})
        names = {unit["name"] for unit in units if unit["active"]}
        if not {"rackmarshal-status.service", "rackmarshal-mcp.service"}.issubset(names):
            raise RuntimeError("Both existing application services must be active")
        return units

    def quiesce(self, snapshot):
        for timer in (True, False):
            names = [u["name"] for u in snapshot if u["name"].endswith(".timer") == timer]
            if names:
                self.command("stop", *names)

    def start_apps(self, snapshot):
        self.command("start", "rackmarshal-status.service", "rackmarshal-mcp.service")
        wait_ready(self.ready_urls, self.timeout, self.mcp_url)

    def resume(self, snapshot):
        names = [u["name"] for u in snapshot if u["active"] and not u["oneshot"] and u["name"] not in ("rackmarshal-status.service", "rackmarshal-mcp.service")]
        if names:
            self.command("start", *names)


def installed_root(python):
    code = "import importlib.util; s=importlib.util.find_spec('rackmarshal'); print(next(iter(s.submodule_search_locations)))"
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    return Path(subprocess.check_output([python, "-I", "-c", code], env=environment, text=True, timeout=15).strip())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    preparation = sub.add_parser("prepare")
    preparation.add_argument("--repo", required=True)
    preparation.add_argument("--revision", required=True)
    preparation.add_argument("--file", action="append", required=True)
    preparation.add_argument("--output", required=True)
    for action in ("plan", "apply", "rollback"):
        command = sub.add_parser(action)
        command.add_argument("--status-python", default="/opt/rackmarshal/venv/bin/python")
        command.add_argument("--mcp-python", default="/opt/rackmarshal-mcp/venv/bin/python")
        if action == "rollback":
            command.add_argument("--transaction", required=True)
        else:
            command.add_argument("--bundle", required=True)
        if action != "plan":
            command.add_argument("--status-url", default="http://127.0.0.1:9110")
            command.add_argument("--mcp-url", default="http://127.0.0.1:8000/mcp")
            command.add_argument("--ready-url", action="append", default=[])
            command.add_argument("--ready-timeout", type=float, default=60)
        if action == "apply":
            command.add_argument("--backups", required=True)
    args = parser.parse_args()
    if args.action == "prepare":
        result = prepare(args.repo, args.revision, args.file, args.output)
    else:
        roots = {"status": installed_root(args.status_python), "mcp": installed_root(args.mcp_python)}
        if args.action == "plan":
            manifest, _, entries = plan(args.bundle, roots)
            result = {"revision": manifest["revision"], "changed_files": len(entries), "entries": entries}
        else:
            if os.geteuid() != 0:
                raise ValueError("Apply and rollback require root on the installation host")
            status, mcp = local_url(args.status_url), local_url(args.mcp_url)
            if not 0 < args.ready_timeout <= 300:
                raise ValueError("Readiness timeout must be between 0 and 300 seconds")
            ready = [status + "/health"] + [local_url(url) for url in args.ready_url]
            # Serialize all operator invocations on this installation host.
            # The held descriptor is released automatically on process exit.
            deployment_lock = os.open("/run/lock/rackmarshal-code-promotion.lock", os.O_RDWR | os.O_CREAT, 0o600)
            try:
                fcntl.flock(deployment_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                runtime = SystemdRuntime(ready, args.ready_timeout, mcp)
                if args.action == "rollback":
                    transaction = Path(args.transaction).resolve()
                    journal = json.loads((transaction / "transaction.json").read_text())
                    if journal.get("format") != 1 or journal["roots"] != {name: str(root.resolve()) for name, root in roots.items()}:
                        raise ValueError("Rollback installation mismatch")
                    runtime.quiesce(journal["runtime"])
                    restore_files(transaction, journal)
                    runtime.start_apps(journal["runtime"])
                    runtime.resume(journal["runtime"])
                    journal["state"] = "ROLLED_BACK"
                    write_json(transaction / "transaction.json", journal)
                    result = {"state": journal["state"], "transaction": str(transaction)}
                else:
                    def acceptance(transaction):
                        bundle = Path(args.bundle).resolve()
                        validate_bundle(bundle)
                        commands = [
                            [args.status_python, str(bundle / "acceptance/prove-incident-narrative.py"), "--base-url", status, "--output", str(transaction / "http-proof.json")],
                            [args.mcp_python, str(bundle / "acceptance/investigator-live-eval.py"), "--suite", str(bundle / "acceptance/suite.json"), "--server", mcp, "--json-out", str(transaction / "mcp-proof.json")],
                        ]
                        for label, command in zip(("http", "mcp"), commands):
                            with (transaction / (label + "-acceptance.log")).open("w") as log:
                                subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
                    result = promote(args.bundle, roots, args.backups, runtime, acceptance)
            finally:
                os.close(deployment_lock)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
