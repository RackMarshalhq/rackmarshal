"""Setuptools backend with deterministic source-archive metadata."""
import copy
import gzip
import os
from pathlib import Path
import tarfile
import tempfile


EXECUTABLES = frozenset(['packaging/observers/pbs-native-verify-cache', 'scripts/bootstrap-pip.py', 'scripts/build-installer-bundle.py', 'scripts/build-installer-bundle.sh', 'scripts/install.sh', 'scripts/publication-gate.sh', 'scripts/uninstall.sh', 'tests/fixture_comparator.py', 'tests/staging_smoke.py'])


def __getattr__(name):
    from setuptools import build_meta
    return getattr(build_meta, name)


def normalize_sdist(path, epoch):
    """Preserve payloads, declare modes, and remove host/time archive metadata."""
    if not 0 <= epoch <= 0xffffffff:
        raise ValueError("SOURCE_DATE_EPOCH must fit an unsigned 32-bit timestamp")
    path = Path(path)
    temporary = None
    try:
        with tarfile.open(path, "r:gz") as source:
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as output:
                temporary = Path(output.name)
                with gzip.GzipFile(filename="", fileobj=output, mode="wb", mtime=epoch) as compressed:
                    with tarfile.open(fileobj=compressed, mode="w", format=tarfile.GNU_FORMAT) as target:
                        for member in sorted(source.getmembers(), key=lambda entry: entry.name):
                            if not (member.isfile() or member.isdir()):
                                raise ValueError("Source archives must contain regular files and directories")
                            entry = copy.copy(member)
                            entry.uid = entry.gid = 0
                            entry.uname = entry.gname = ""
                            entry.mtime = epoch
                            entry.pax_headers = {}
                            relative = '/'.join(Path(entry.name).parts[1:])
                            entry.mode = 0o755 if entry.isdir() or relative in EXECUTABLES else 0o644
                            if entry.isfile():
                                with source.extractfile(member) as payload:
                                    target.addfile(entry, payload)
                            else:
                                target.addfile(entry)
        temporary.chmod(0o644)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def build_sdist(sdist_directory, config_settings=None):
    from setuptools.build_meta import build_sdist as setuptools_sdist
    name = setuptools_sdist(sdist_directory, config_settings)
    normalize_sdist(Path(sdist_directory) / name, int(os.environ.get("SOURCE_DATE_EPOCH", "0")))
    return name
