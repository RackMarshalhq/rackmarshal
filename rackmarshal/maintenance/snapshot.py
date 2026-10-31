"""Online, integrity-checked snapshots of the RackMarshal ledger."""
from __future__ import annotations
import argparse
from contextlib import closing
from datetime import datetime, timezone
import fcntl
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
import time

DEFAULT_RETENTION = 7
SPACE_MARGIN = 64 * 1024 * 1024
SNAPSHOT_NAME = re.compile(r"state\.db\.\d{8}-\d{6}(?:-\d{6})?Z")


def _quick_check(connection):
    return connection.execute("PRAGMA quick_check").fetchall()


def create_snapshot(state_db, snapshot_dir, retention=DEFAULT_RETENTION):
    source = Path(state_db).resolve()
    directory = Path(snapshot_dir)
    if not source.is_file():
        raise FileNotFoundError("state database does not exist")
    if retention < 1:
        raise ValueError("retention must be positive")
    directory.mkdir(mode=0o750, parents=True, exist_ok=True)
    with (directory / ".snapshot.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # A snapshot briefly needs two extra copies (the new snapshot and the
        # replacement "latest" copy). Refuse instead of filling the disk.
        needed = 2 * source.stat().st_size + SPACE_MARGIN
        free = shutil.disk_usage(directory).free
        if free < needed:
            raise OSError("not enough free space for a snapshot: need %d bytes, have %d" % (needed, free))
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%fZ")
        destination = directory / ("state.db." + stamp)
        temporary = None
        latest_tmp = None
        try:
            fd, name = tempfile.mkstemp(prefix=".snapshot-", dir=directory)
            os.close(fd)
            temporary = Path(name)
            deadline = time.monotonic() + 60

            def progress(status, remaining, total):
                if time.monotonic() > deadline:
                    raise TimeoutError("snapshot exceeded 60 seconds")

            with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=60)) as src:
                with closing(sqlite3.connect(temporary)) as dst:
                    src.backup(dst, pages=256, progress=progress, sleep=0.25)
                    if _quick_check(dst) != [("ok",)]:
                        raise RuntimeError("snapshot integrity check failed")
            temporary.chmod(0o640)
            with temporary.open("rb") as handle:
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
            temporary = None
            fd, name = tempfile.mkstemp(prefix=".latest-", dir=directory)
            os.close(fd)
            latest_tmp = Path(name)
            shutil.copyfile(destination, latest_tmp)
            latest_tmp.chmod(0o640)
            with latest_tmp.open("rb") as handle:
                os.fsync(handle.fileno())
            os.replace(latest_tmp, directory / "state.db.latest")
            latest_tmp = None
            dirfd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(dirfd)
            finally:
                os.close(dirfd)
            snapshots = sorted(
                (p for p in directory.iterdir() if SNAPSHOT_NAME.fullmatch(p.name) and p.is_file() and not p.is_symlink()),
                key=lambda p: p.name, reverse=True,
            )
            for old in snapshots[retention:]:
                old.unlink()
            return destination
        finally:
            for candidate in (temporary, latest_tmp):
                if candidate is not None:
                    candidate.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-db", help="default: STATE_DB from the configuration")
    parser.add_argument("--snapshot-dir", help="default: db-snapshots under the state directory")
    parser.add_argument("--retention", type=int, help="snapshots to keep (default %d)" % DEFAULT_RETENTION)
    args = parser.parse_args(argv)
    state_db = args.state_db or os.environ.get("RACKMARSHAL_STATE_DB")
    snapshot_dir = args.snapshot_dir or os.environ.get("RACKMARSHAL_DB_SNAPSHOT_DIR")
    retention = args.retention if args.retention is not None else int(os.environ.get("RACKMARSHAL_DB_SNAPSHOT_RETENTION", DEFAULT_RETENTION))
    if state_db is None or snapshot_dir is None:
        from rackmarshal.core import config
        state_db = state_db or config.state_db()
        snapshot_dir = snapshot_dir or config.state_dir() / "db-snapshots"
    result = create_snapshot(state_db, snapshot_dir, retention)
    print("RACKMARSHAL_DB_SNAPSHOT_OK path=" + str(result), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
