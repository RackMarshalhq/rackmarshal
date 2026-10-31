"""The docs checker runs as part of the normal suite, so a broken link fails locally too."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DocsCheckTests(unittest.TestCase):
    def run_checker(self, root=ROOT):
        return subprocess.run([sys.executable, "-B", str(ROOT / "scripts" / "check-docs.py")],
                              capture_output=True, text=True, cwd=root)

    def test_docs_match_the_code(self):
        done = self.run_checker()
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertIn("DOCS CHECK PASSED", done.stdout)

    def test_every_documented_file_is_covered(self):
        text = (ROOT / "scripts" / "check-docs.py").read_text()
        for name in ("README.md", "INSTALL.md", "CONFIGURATION.md", "SOAK.md", "docs/QUICKSTART.md"):
            self.assertIn(name, text)


if __name__ == "__main__":
    unittest.main()
