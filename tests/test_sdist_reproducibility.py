"""Rebuilding source distributions must not encode host or wall-clock metadata."""
import gzip
import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("backend", Path(__file__).resolve().parents[1] / "build_support" / "_build_backend.py")
BACKEND = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BACKEND)


class SourceDistributionTests(unittest.TestCase):
    def archive(self, path, stamp, reverse=False, link=False):
        names = ["fixture/", "fixture/README.md", "fixture/scripts/install.sh"]
        with path.open("wb") as output, gzip.GzipFile(filename=path.name, fileobj=output, mode="wb", mtime=stamp) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
                for name in reversed(names) if reverse else names:
                    entry = tarfile.TarInfo(name)
                    entry.mtime = stamp + 0.5
                    entry.uid = entry.gid = stamp
                    entry.uname = entry.gname = "builder-" + str(stamp)
                    entry.mode = 0o775 if name.endswith(("/", ".sh")) else 0o664
                    entry.pax_headers = {"atime": str(stamp), "ctime": str(stamp)}
                    if name.endswith("/"):
                        entry.type = tarfile.DIRTYPE
                        archive.addfile(entry)
                    elif link:
                        entry.type = tarfile.SYMTYPE
                        entry.linkname = "README.md"
                        archive.addfile(entry)
                    else:
                        payload = ("payload for " + name).encode()
                        entry.size = len(payload)
                        archive.addfile(entry, io.BytesIO(payload))

    def test_different_metadata_and_order_produce_identical_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            a, b = [Path(directory) / name for name in ("first.tar.gz", "second.tar.gz")]
            self.archive(a, 100)
            self.archive(b, 200, reverse=True)
            self.assertNotEqual(a.read_bytes(), b.read_bytes())
            BACKEND.normalize_sdist(a, 42)
            BACKEND.normalize_sdist(b, 42)
            self.assertEqual(a.read_bytes(), b.read_bytes())
            with tarfile.open(a) as archive:
                for entry in archive:
                    self.assertEqual((entry.uid, entry.gid, entry.mtime), (0, 0, 42))
                    self.assertEqual((entry.uname, entry.gname, entry.pax_headers), ("", "", {}))
                    self.assertEqual(entry.mode, 0o755 if entry.isdir() or entry.name.endswith('.sh') else 0o644)
                    if entry.isfile():
                        with archive.extractfile(entry) as payload:
                            self.assertEqual(payload.read(), ("payload for " + entry.name).encode())

    def test_rejected_input_preserves_original_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.tar.gz"
            self.archive(path, 100, link=True)
            before = path.read_bytes()
            for epoch in (-1, 2**32, 42):
                with self.assertRaises(ValueError): BACKEND.normalize_sdist(path, epoch)
                self.assertEqual(path.read_bytes(), before)
                self.assertEqual(list(Path(directory).iterdir()), [path])
