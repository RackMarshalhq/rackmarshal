"""Release scans must reject hidden identifiers and unsafe nested assets."""
import io
from pathlib import Path
import subprocess
import sqlite3
import stat
import tarfile
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
    def test_literal_bang_does_not_hide_private_paths(self):
        for name in ('internal/evidence!notes.txt', '.git/object!notes.txt',
                     'chatgpt-business/binding!notes.txt', '../outside!notes.txt'):
            with self.subTest(name=name):
                self.assertNotEqual(self.check({name: 'generic fixture'}).returncode, 0)

    def test_renamed_and_uppercase_zip_contents_are_scanned(self):
        for name in ('nested.ZIP', 'cache.bin'):
            for member, content in (('cache.bin', b'SQLite format 3\x00fixture'),
                                    ('binding.txt', ('asdk_'+'app_'+'a'*32).encode())):
                inner = io.BytesIO()
                with zipfile.ZipFile(inner, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                    archive.writestr(member, content)
                with self.subTest(name=name, member=member):
                    self.assertNotEqual(self.check({name: inner.getvalue()}).returncode, 0)

    def test_zip_symlinks_fail_including_directory_named_links(self):
        for name in ('link', 'link/'):
            inner = io.BytesIO()
            with zipfile.ZipFile(inner, 'w') as archive:
                entry = zipfile.ZipInfo(name)
                entry.create_system = 3
                entry.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(entry, '../../outside')
            result = self.check({'nested.bin': inner.getvalue()})
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('archive link', result.stdout)

    def test_tar_links_remain_rejected(self):
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
            inner = io.BytesIO()
            with tarfile.open(fileobj=inner, mode='w:gz') as archive:
                entry = tarfile.TarInfo('link')
                entry.type = kind
                entry.linkname = '../../outside'
                archive.addfile(entry)
            result = self.check({'nested.tgz': inner.getvalue()})
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('archive link', result.stdout)

    def test_corrupt_archive_fails_without_traceback(self):
        result = self.check({'nested.ZIP': b'PK\x03\x04broken'})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('unreadable archive', result.stdout)
        self.assertNotIn('Traceback', result.stderr)

    def test_generic_renamed_zip_passes(self):
        inner = io.BytesIO()
        with zipfile.ZipFile(inner, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('README.md', 'generic fictional installation')
        self.assertEqual(self.check({'cache.bin': inner.getvalue()}).returncode, 0)

    def test_literal_bang_never_grants_website_exception(self):
        text = 'Mi' + 'chael Poteet'
        self.assertNotEqual(self.check({'notes!site/about.html': text}).returncode, 0)

    def test_source_archive_root_allows_only_exact_site_pages(self):
        text = 'Mi' + 'chael Poteet'
        for kind in ('zip', 'tgz'):
            members = {'rackmarshal-ref/pyproject.toml': 'generic metadata',
                       'rackmarshal-ref/site/about.html': text}
            inner = io.BytesIO()
            if kind == 'zip':
                with zipfile.ZipFile(inner, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                    for name, content in members.items(): archive.writestr(name, content)
            else:
                with tarfile.open(fileobj=inner, mode='w:gz') as archive:
                    for name, content in members.items():
                        entry = tarfile.TarInfo(name)
                        data = content.encode()
                        entry.size = len(data)
                        archive.addfile(entry, io.BytesIO(data))
            with self.subTest(kind=kind):
                result = self.check({'source.' + kind: inner.getvalue()})
                self.assertEqual(result.returncode, 0, result.stdout)
        for name in ('rackmarshal-ref/notes.txt', 'rackmarshal-ref/notes!site/about.html',
                     'rackmarshal-ref/internal/site/about.html'):
            result = self.check({'rackmarshal-ref/pyproject.toml': 'generic metadata', name: text})
            self.assertNotEqual(result.returncode, 0)

    def test_unvalidated_or_multiple_archive_roots_do_not_grant_exception(self):
        text = 'Mi' + 'chael Poteet'
        for members in ({'wrapper/site/about.html': text},
                        {'wrapper/pyproject.toml': '', 'wrapper/site/about.html': text, 'other/file': ''}):
            self.assertNotEqual(self.check(members).returncode, 0)

    def test_prefixed_site_exception_still_rejects_secrets_and_bindings(self):
        for content in ('asdk_'+'app_'+'a'*32, 'ghp_'+'a'*36):
            result = self.check({'root/pyproject.toml': '', 'root/site/about.html': content})
            self.assertNotEqual(result.returncode, 0)

    def test_corrupt_compressed_payload_fails_without_traceback(self):
        for compression, extra_offset, corrupt_byte in ((zipfile.ZIP_DEFLATED, 0, 6),
                                                        (zipfile.ZIP_LZMA, 4, 255)):
            inner = io.BytesIO()
            with zipfile.ZipFile(inner, 'w', compression=compression) as archive:
                archive.writestr('fixture.txt', 'generic fixture content')
            data = bytearray(inner.getvalue())
            offset = 30 + int.from_bytes(data[26:28], 'little') + int.from_bytes(data[28:30], 'little')
            data[offset + extra_offset] = corrupt_byte  # Leave the central directory valid.
            result = self.check({'nested.bin': bytes(data)})
            with self.subTest(compression=compression):
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('unreadable archive', result.stdout)
                self.assertNotIn('Traceback', result.stderr)
