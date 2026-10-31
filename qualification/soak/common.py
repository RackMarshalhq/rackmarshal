"""Small helpers shared by the soak launcher, driver and checks.

Everything here is deliberately plain: evidence files are written exactly once
(O_EXCL), fsynced, and read back with checks that refuse links and growth.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import time


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    """The one byte representation used for every receipt and hash."""
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return text.encode() + b"\n"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def fsync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def save(path, value):
    """Write canonical JSON to a NEW file and make it durable."""
    path = Path(path)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(canonical(value))
        handle.flush()
        os.fsync(handle.fileno())
    fsync_directory(path.parent)


def read_bytes(path, max_bytes=16 * 2**20):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode), "not a regular file: %s" % path)
        require(info.st_nlink == 1, "hard-linked evidence: %s" % path)
        require(info.st_size <= max_bytes, "evidence too large: %s" % path)
        with os.fdopen(fd, "rb", closefd=False) as handle:
            data = handle.read(max_bytes + 1)
        require(len(data) == info.st_size, "evidence changed while reading: %s" % path)
        return data
    finally:
        os.close(fd)


def _no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key: %s" % key)
        result[key] = value
    return result


def decode(data):
    return json.loads(data, object_pairs_hook=_no_duplicates)


def load(path):
    return decode(read_bytes(path))


def clock():
    return {"utc_ns": time.time_ns(), "monotonic_ns": time.monotonic_ns()}


def check_interval(earlier, later, maximum_gap_seconds=None):
    """Both clocks must advance together; optionally bound the gap between samples."""
    mono = later["monotonic_ns"] - earlier["monotonic_ns"]
    utc = later["utc_ns"] - earlier["utc_ns"]
    require(mono > 0 and utc > 0 and abs(mono - utc) <= 2 * 10**9, "clock discontinuity")
    if maximum_gap_seconds is not None:
        require(mono <= maximum_gap_seconds * 10**9, "sample gap exceeded")
