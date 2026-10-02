"""Release scans must reject hidden identifiers and unsafe nested assets."""
import io
from pathlib import Path
import subprocess
import sqlite3
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

    def test_sqlite_extensions_and_sidecars_fail(self):
        for name in ("state.sqlite3", "state.SQLITE3", "state.sqlite3-wal",
                     "state.sqlite-shm", "state.sqlite-journal", "state.db-wal",
                     "state.db-shm", "state.db-journal"):
            with self.subTest(name=name):
                result = self.check({name: "synthetic retained data"})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("forbidden file type", result.stdout)

    def test_renamed_sqlite_database_fails_without_disclosing_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture"
            with sqlite3.connect(path) as connection:
                connection.execute("CREATE TABLE fixture(value TEXT)")
                connection.execute("INSERT INTO fixture VALUES (?)", ("private-row-do-not-print",))
            connection.close()
            result = self.check({"cache.bin": path.read_bytes()})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SQLite database content", result.stdout)
        self.assertNotIn("private-row-do-not-print", result.stdout + result.stderr)

    def test_nested_sqlite_database_extension_fails(self):
        inner = io.BytesIO()
        with zipfile.ZipFile(inner, "w") as archive:
            archive.writestr("state.sqlite3", "synthetic retained data")
        result = self.check({"package.zip": inner.getvalue()})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("package.zip!state.sqlite3", result.stdout)

    def test_documentation_mentioning_sqlite_header_is_not_a_database(self):
        result = self.check({"README.md": "SQLite format 3 is a database format."})
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_known_public_website_identity_is_narrowly_scoped(self):
        text = 'Mi' + 'chael Poteet; mi' + 'chael@rackmarshal.com'
        for name in ('site/about.html', 'site/docs.html', 'site/index.html', 'site/install.html'):
            with self.subTest(name=name):
                self.assertEqual(self.check({name:text}).returncode, 0)
        self.assertNotEqual(self.check({'notes.txt':text}).returncode, 0)

    def test_public_site_exception_never_hides_bindings_or_secrets(self):
        prefix = 'Mi' + 'chael Poteet '
        for extra in ('asdk_'+'app_'+'a'*32, 'ghp_'+'a'*36, '192.'+'168.1.2'):
            with self.subTest(extra_kind=extra[:3]):
                self.assertNotEqual(self.check({'site/index.html':prefix+extra}).returncode, 0)
