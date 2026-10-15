"""Exercise the exact embedded installer policy on disposable, owned fixtures."""
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=(ROOT/'scripts/install.sh').read_text()
POLICY=SCRIPT.split("python3 - <<'PY_VENV_PERMISSIONS'\n",1)[1].split('\nPY_VENV_PERMISSIONS',1)[0]
ns={'__name__':'test_policy'}
exec(compile(POLICY,'installer-policy','exec'),ns)


class InstallerPermissions(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)/'venv';self.root.mkdir(mode=0o700)
        (self.root/'bin').mkdir(mode=0o700)
        (self.root/'lib/package').mkdir(parents=True)
        self.code=self.root/'lib/package/api.py';self.code.write_text('pass\n');self.code.chmod(0o600)
        self.exe=self.root/'bin/entry';self.exe.write_text('#!/bin/sh\n');self.exe.chmod(0o700)
    def plan(self):return ns['permission_plan'](self.root,os.getgid(),os.getuid())
    def test_nested_owner_only_tree_becomes_group_readable_not_writable(self):
        ns['apply_plan'](self.plan())
        for p in [self.root,*self.root.rglob('*')]:
            expected=0o750 if p.is_dir() or p==self.exe else 0o640
            self.assertEqual(stat.S_IMODE(p.stat().st_mode),expected)
        self.assertEqual(self.code.read_bytes(),b'pass\n')
    def test_external_symlink_target_and_internal_alias_unchanged(self):
        target=self.root.parent/'external';target.write_text('external');target.chmod(0o600)
        (self.root/'bin/python').symlink_to(target)
        (self.root/'lib64').symlink_to('lib')
        ns['apply_plan'](self.plan())
        self.assertEqual(stat.S_IMODE(target.stat().st_mode),0o600)
        self.assertEqual(os.readlink(self.root/'lib64'),'lib')
    def test_symlink_root_rejected(self):
        alias=self.root.parent/'alias';alias.symlink_to(self.root)
        with self.assertRaises(ValueError):ns['permission_plan'](alias,os.getgid(),os.getuid())
    def test_hardlink_rejected_before_any_application(self):
        os.link(self.code,self.root/'linked')
        with self.assertRaises(ValueError):self.plan()
        self.assertEqual(stat.S_IMODE(self.root.stat().st_mode),0o700)
    def test_foreign_owner_rejected(self):
        with self.assertRaises(ValueError):ns['permission_plan'](self.root,os.getgid(),os.getuid()+1)
    def test_special_file_rejected(self):
        os.mkfifo(self.root/'fifo')
        with self.assertRaises(ValueError):self.plan()
    def test_public_group_writable_modes_are_restricted(self):
        self.code.chmod(0o666);self.exe.chmod(0o777)
        ns['apply_plan'](self.plan())
        self.assertEqual(stat.S_IMODE(self.code.stat().st_mode),0o640)
        self.assertEqual(stat.S_IMODE(self.exe.stat().st_mode),0o750)
    def test_policy_idempotent(self):
        ns['apply_plan'](self.plan());before={str(p):p.stat().st_mode for p in [self.root,*self.root.rglob('*')]}
        ns['apply_plan'](self.plan());self.assertEqual(before,{str(p):p.stat().st_mode for p in [self.root,*self.root.rglob('*')]})
    def test_invoker_umask_is_overridden_before_install(self):
        prefix=SCRIPT.split('WHEEL=""',1)[0]
        result=subprocess.run(['bash','-c','umask 077\n'+prefix+'umask'],capture_output=True,text=True,check=True)
        self.assertEqual(result.stdout.strip(),'0027')
    def test_service_probe_is_after_policy_and_before_config_validation(self):
        self.assertLess(SCRIPT.index('PY_VENV_PERMISSIONS'),SCRIPT.index('PY_SERVICE_ACCESS'))
        self.assertLess(SCRIPT.index('PY_SERVICE_ACCESS'),SCRIPT.index('rackmarshal validate-config'))
        self.assertIn('extra_groups=[]',SCRIPT)
        self.assertIn("'-I', '-B'",SCRIPT)

    def test_walk_failure_is_not_silently_skipped(self):
        def walk(root, **kwargs):
            kwargs['onerror'](PermissionError('fixture traversal error'))
            return iter(())
        with patch.object(ns['os'], 'walk', walk), self.assertRaises(PermissionError):
            self.plan()
