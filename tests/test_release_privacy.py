"""Release scans must reject hidden identifiers and unsafe nested assets."""
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

SCRIPT=Path(__file__).resolve().parents[1]/"scripts/release-privacy-gate.py"

class ReleasePrivacyTests(unittest.TestCase):
    def check(self, members):
        with tempfile.TemporaryDirectory() as d:
            archive=Path(d)/"fixture.zip"
            with zipfile.ZipFile(archive,"w") as z:
                for name,data in members.items(): z.writestr(name,data)
            return subprocess.run([sys.executable,str(SCRIPT),str(archive)],capture_output=True,text=True)

    def test_generic_archive_passes(self):
        self.assertEqual(self.check({"README.md":"generic fictional installation"}).returncode,0)

    def test_nested_workspace_binding_fails(self):
        inner=io.BytesIO()
        with zipfile.ZipFile(inner,"w") as z:
            z.writestr("binding.json",'asdk_'+'app_'+'a'*32)
        result=self.check({"plugin.zip":inner.getvalue()})
        self.assertNotEqual(result.returncode,0)
        self.assertIn("site/workspace pattern",result.stdout)

    def test_archive_traversal_fails(self):
        self.assertNotEqual(self.check({"../outside.txt":"fixture"}).returncode,0)

    def test_private_database_and_token_fail(self):
        result=self.check({"state.db":"fixture", "token.txt":"ghp_"+"a"*36})
        self.assertNotEqual(result.returncode,0)
        self.assertIn("secret pattern",result.stdout)
        self.assertIn("forbidden file type",result.stdout)
