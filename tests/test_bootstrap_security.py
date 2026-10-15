"""Exercise offline installation and refusal before executing untrusted inputs."""
import base64
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import venv
import zipfile

ROOT = Path(__file__).resolve().parents[1]
def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value
B = module('bootstrap_security', ROOT / 'scripts/bootstrap-pip.py')


def wheel(extra=None):
    prefix = 'rackmarshal-' + B.VERSION + '.dist-info/'
    files = {'rackmarshal/__init__.py': b'VALUE = 42\n',
             prefix + 'METADATA': ('Metadata-Version: 2.1\nName: rackmarshal\nVersion: ' + B.VERSION + '\n').encode(),
             prefix + 'WHEEL': b'Wheel-Version: 1.0\nGenerator: fixture\nRoot-Is-Purelib: true\nTag: py3-none-any\n'}
    files.update(extra or {})
    files[prefix + 'RECORD'] = ''.join(name + ',sha256=' + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('=') + ',' + str(len(data)) + '\n' for name, data in files.items()).encode() + (prefix + 'RECORD,,\n').encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        for name, data in files.items(): archive.writestr(name, data)
    return output.getvalue()


class BootstrapSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.owner = os.getuid()

    def bundle(self):
        root = self.root / 'bundle'; root.mkdir(mode=0o700)
        payloads = {name: (wheel() if name == B.APP_NAME else (ROOT / name).read_bytes()) for name in B.BUNDLE_FILES}
        for name, data in payloads.items():
            p = root / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data); p.chmod(0o600)
        (root / 'install-manifest.json').write_text(json.dumps({'version': B.VERSION, 'files': {name:B.digest(data) for name,data in payloads.items()}}))
        return root

    def stage(self):
        root = self.bundle()
        return B.prepare(root, root / B.APP_NAME, self.root, self.owner)

    def target(self):
        target = self.root / 'venv'
        venv.EnvBuilder(with_pip=False, symlinks=True).create(target)
        # Homebrew 3.14 adds a non-Linux alias; model the supported Linux layout.
        for entry in (target / 'bin').iterdir():
            if entry.is_symlink() and not entry.name.startswith('python'):
                entry.unlink()
        return target

    def test_real_offline_install_ignores_poisoned_environment_and_working_directory(self):
        stage, target = self.stage(), self.target()
        marker = self.root / 'executed'
        poison = "from pathlib import Path; Path(%r).write_text('BAD')\n" % str(marker)
        (stage / 'sitecustomize.py').write_text(poison)
        (stage / 'pip.py').write_text(poison)
        config = self.root / 'pip.conf'; config.write_text('[global]\nrequire-virtualenv = false\nindex-url = https://invalid.invalid/simple\n[install]\ntarget = /unusable-test-target\n')
        with patch.dict(os.environ, {'PYTHONPATH':str(stage), 'PIP_CONFIG_FILE':str(config), 'PIP_TARGET':str(self.root / 'unexpected'), 'PIP_INDEX_URL':'https://invalid.invalid/simple'}):
            result = B.install(stage, target, self.owner)
        self.assertEqual(result['result'], 'PASS')
        self.assertFalse(marker.exists()); self.assertFalse((self.root / 'unexpected').exists())
        result = subprocess.run([str(target / 'bin/python'), '-I', '-B', '-c', 'import pip,rackmarshal;print(pip.__version__,rackmarshal.VALUE)'], capture_output=True,text=True,check=True)
        self.assertEqual(result.stdout.strip(), '26.2.1 42')
        with patch.object(B.subprocess, 'run', side_effect=AssertionError('must not execute')):
            with self.assertRaisesRegex(ValueError, 'pipless/empty'): B.install(stage, target, self.owner)

    def test_changed_bundle_fails_before_staging(self):
        root = self.bundle(); (root / B.APP_NAME).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'): B.prepare(root, root / B.APP_NAME, self.root, self.owner)
        self.assertEqual(list(self.root.iterdir()), [root])

    def test_missing_bundle_input_fails_before_staging(self):
        root = self.bundle(); (root / 'INSTALL.md').unlink()
        with self.assertRaises(OSError): B.prepare(root, root / B.APP_NAME, self.root, self.owner)
        self.assertEqual(list(self.root.iterdir()), [root])

    def test_untrusted_file_types_and_permissions(self):
        original = self.root / 'input'; original.write_text('safe')
        link = self.root / 'symlink'; link.symlink_to(original)
        hard = self.root / 'hard'; os.link(original, hard)
        fifo = self.root / 'fifo'; os.mkfifo(fifo)
        for path in (original, link, hard, fifo):
            with self.subTest(path=path.name), self.assertRaises((OSError, ValueError)): B.trusted_read(path, self.owner)
        writable = self.root / 'writable'; writable.write_text('safe'); writable.chmod(0o666)
        with self.assertRaises(ValueError): B.trusted_read(writable, self.owner)

    def test_wheel_startup_hooks_traversal_and_wrong_identity(self):
        for name in ('rackmarshal/../../escape', 'rackmarshal/start.pth', 'rackmarshal/sitecustomize.py', '/absolute', 'other/file'):
            with self.subTest(name=name), self.assertRaises(ValueError): B.validate_wheel(wheel({name:b'bad'}), 'rackmarshal', B.VERSION)
        with self.assertRaises((ValueError, KeyError)): B.validate_wheel(wheel(), 'pip', B.PIP_VERSION)

    def test_startup_hook_and_staged_tamper_fail_before_execution(self):
        stage, target = self.stage(), self.target()
        site = next(target.glob('lib/python*/site-packages'))
        hook = site / 'malicious.pth'; hook.write_text('import os\n')
        with patch.object(B.subprocess, 'run', side_effect=AssertionError('must not execute')):
            with self.assertRaisesRegex(ValueError, 'startup hook'): B.install(stage, target, self.owner)
            hook.unlink(); (stage / B.APP_NAME).write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'application changed'): B.install(stage, target, self.owner)
        self.assertFalse((stage / 'bootstrap-receipt.json').exists())

    def test_all_installer_python_invocations_are_isolated(self):
        for line in (ROOT / 'scripts/install.sh').read_text().splitlines():
            if line.startswith(('python3 ', '/opt/rackmarshal/venv/bin/python ')):
                self.assertIn(' -I -B ', line)

    def test_network_is_denied_by_runner(self):
        # Run the actual runner with a synthetic import that attempts networking.
        target = self.target(); fake = self.root / 'fake'; fake.mkdir(); (fake / 'pip').mkdir()
        (fake / 'pip/__init__.py').write_text('import socket; socket.create_connection(("127.0.0.1",9))\n')
        with patch.object(B, 'PIP_SHA256', B.digest(b'')):
            runner = B.RUNNER.replace('assert hashlib.sha256(pathlib.Path(wheel).read_bytes()).hexdigest() == expected', 'pass')
        result = subprocess.run([str(target/'bin/python'), '-I', '-B', '-c', runner, json.dumps([str(fake),'',str(target),[]])],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0); self.assertIn('network prohibited',result.stderr)

    def test_installer_build_without_git_and_canonical_modes(self):
        root = self.bundle(); (root / 'pyproject.toml').write_text('[project]\nversion = "'+B.VERSION+'"\n'); (root / 'dist').mkdir(); (root / 'dist' / B.APP_NAME).write_bytes(wheel())
        builder = module('installer_builder', ROOT / 'scripts/build-installer-bundle.py')
        with patch.dict(os.environ, {'SOURCE_DATE_EPOCH':'42'}), patch.object(builder.subprocess,'check_output',side_effect=AssertionError('git must not run')):
            first = builder.build(root); data = first.read_bytes(); first.unlink()
            for p in root.rglob('*'):
                if p.is_file(): p.chmod(0o700)
            self.assertEqual(builder.build(root).read_bytes(),data)

    def test_existing_and_dangling_paths_are_preserved(self):
        existing = self.root / 'existing'; existing.mkdir(); sentinel = existing / 'state'; sentinel.write_text('retain')
        dangling = self.root / 'dangling'; dangling.symlink_to(self.root / 'absent')
        for path in (existing, dangling):
            with self.assertRaisesRegex(ValueError, 'existing installation'): B.assert_fresh_paths([path], self.owner)
        self.assertEqual(sentinel.read_text(), 'retain'); self.assertTrue(dangling.is_symlink())

    def test_inventory_rejects_extra_files_and_corrupted_record(self):
        stage, target = self.stage(), self.target(); B.install(stage, target, self.owner)
        distributions = [('pip', B.PIP_VERSION, B.validate_wheel((stage / 'packaging/bootstrap' / B.PIP_NAME).read_bytes(),'pip',B.PIP_VERSION)), ('rackmarshal', B.VERSION, B.validate_wheel((stage / B.APP_NAME).read_bytes(),'rackmarshal',B.VERSION))]
        site = next(target.glob('lib/python*/site-packages')); extra = site / 'extra.py'; extra.write_text('BAD')
        with self.assertRaisesRegex(ValueError, 'unexpected or missing'): B.verify_inventory(target, distributions, self.owner)
        extra.unlink(); record = site / ('rackmarshal-' + B.VERSION + '.dist-info/RECORD'); record.write_text(record.read_text().replace('sha256=', 'sha512='))
        with self.assertRaisesRegex(ValueError, 'RECORD mismatch'): B.verify_inventory(target, distributions, self.owner)
