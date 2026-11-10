"""The lifecycle script accepts any 1.3.x predecessor verified by a supplied checksum."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("lifecycle_generalized", ROOT / "scripts/lifecycle.py")
C = importlib.util.module_from_spec(spec)
spec.loader.exec_module(C)


def write_wheel(path, name="rackmarshal", version="1.3.0rc1"):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("%s-%s.dist-info/METADATA" % (name, version),
                   "Metadata-Version: 2.1\nName: %s\nVersion: %s\n" % (name, version))
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class GeneralizedPredecessorTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        # trusted_read insists on root-owned inputs; the checks under test are the content rules.
        patcher = patch.object(C.B, "trusted_read", lambda path, owner=0: Path(path).read_bytes())
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_any_13x_predecessor_is_identified_by_its_checksum(self):
        wheel = self.root / "p.whl"
        sha = write_wheel(wheel, version="1.3.1")
        self.assertEqual(C.previous_identity(wheel, sha), ("1.3.1", sha))

    def test_wrong_checksum_is_refused(self):
        wheel = self.root / "p.whl"
        write_wheel(wheel)
        with self.assertRaisesRegex(ValueError, "differs from the supplied checksum"):
            C.previous_identity(wheel, "1" * 64)

    def test_malformed_checksum_is_refused(self):
        wheel = self.root / "p.whl"
        write_wheel(wheel)
        for bad in ("", "ABC", "G" * 64, None):
            with self.assertRaisesRegex(ValueError, "64 lowercase hex"):
                C.previous_identity(wheel, bad)

    def test_other_series_and_other_projects_are_refused(self):
        wheel = self.root / "p.whl"
        sha = write_wheel(wheel, version="1.2.0rc6.dev2")
        with self.assertRaisesRegex(ValueError, "unsupported version format"):
            C.previous_identity(wheel, sha)
        sha = write_wheel(wheel, version="1.0.0")
        with self.assertRaisesRegex(ValueError, "outside the 1.3 series"):
            C.previous_identity(wheel, sha)
        sha = write_wheel(wheel, name="other")
        with self.assertRaisesRegex(ValueError, "not a RackMarshal wheel|no single METADATA"):
            C.previous_identity(wheel, sha)

    def test_version_order(self):
        self.assertLess(C.version_key("1.3.0rc1"), C.version_key("1.3.0"))
        self.assertLess(C.version_key("1.3.0"), C.version_key("1.3.1rc1"))
        self.assertLess(C.version_key("1.3.9"), C.version_key("1.3.10"))
        with self.assertRaises(ValueError):
            C.version_key("1.3.0.dev3")

    def test_old_pinned_dev_chain_constants_are_gone(self):
        self.assertFalse(hasattr(C, "DEV2"))
        self.assertFalse(hasattr(C, "DEV2_SHA"))


if __name__ == "__main__":
    unittest.main()
