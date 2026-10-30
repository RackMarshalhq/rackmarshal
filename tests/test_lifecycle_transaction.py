"""Real SQLite/filesystem transactions with inert runtime; no system actions."""
import json, os, sqlite3, tempfile, unittest
from contextlib import closing
from pathlib import Path
from rackmarshal.maintenance.lifecycle import Lifecycle, Refused, inventory, database_snapshot

_ORIGINAL_UMASK = None


def setUpModule():
    """Make these tests independent of the machine's umask.

    The code under test refuses group-writable inputs, so the tests must
    create their files with a known umask instead of inheriting one.
    """
    global _ORIGINAL_UMASK
    _ORIGINAL_UMASK = os.umask(0o022)


def tearDownModule():
    os.umask(_ORIGINAL_UMASK)


class Runtime:
    def __init__(self): self.calls=[]; self.guarded=False; self.fail_accept=False
    def snapshot(self):return {'active':['status'],'enabled':[]}
    def guard(self,*args):self.calls.append('guard');self.guarded=True
    def quiesce(self,*args):self.calls.append('quiesce')
    def accept(self,*args):
        self.calls.append('accept')
        if self.fail_accept:raise RuntimeError('acceptance failed')
    def resume(self,transaction,snapshot,authorize):authorize();self.calls.append('resume');self.guarded=False
    def hold(self,*args):self.calls.append('hold');self.guarded=True

class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.active=self.root/'active';self.candidate=self.root/'candidate';self.store=self.root/'store'
        for p in (self.active,self.candidate,self.store):p.mkdir(mode=0o700)
        (self.active/'app.py').write_text('old');(self.candidate/'app.py').write_text('new')
        self.conf=self.root/'config';self.conf.write_text('secret unchanged');self.conf.chmod(0o600)
        self.db=self.root/'state.sqlite'
        with closing(sqlite3.connect(self.db)) as c, c:
            c.executescript("CREATE TABLE schema_migrations(id TEXT,checksum TEXT);INSERT INTO schema_migrations VALUES('001','abc');CREATE TABLE incidents(id INTEGER PRIMARY KEY,state TEXT,payload TEXT);INSERT INTO incidents VALUES(1,'OPEN','positive errors');")
        self.rt=Runtime();self.engine=Lifecycle(self.active,self.store,self.db,[self.conf],self.rt)
        self.before=inventory(self.active,os.getuid());self.schema=database_snapshot(self.db)
    def apply(self):return self.engine.upgrade(self.candidate,{'version':'fixture'},self.before,self.schema,True)
    def test_upgrade_rollback_reupgrade_preserves_newer_history(self):
        tx=self.apply()
        with closing(sqlite3.connect(self.db)) as c, c:c.execute("INSERT INTO incidents VALUES(2,'OPEN','newer evidence')")
        newer=database_snapshot(self.db)
        self.engine.rollback(tx,True)
        self.assertEqual(database_snapshot(self.db),newer)
        self.assertEqual((self.active/'app.py').read_text(),'old')
        second=self.apply();self.assertNotEqual(second,tx)
        self.assertEqual(database_snapshot(self.db),newer)
        self.assertEqual(self.rt.calls[:4],['guard','quiesce','accept','resume'])
    def test_unqualified_semantics_refuse_without_mutation(self):
        with self.assertRaises(Refused):self.engine.upgrade(self.candidate,{},self.before,self.schema,False)
        self.assertEqual(self.rt.calls,[])
    def test_schema_change_refuses_before_guard(self):
        self.schema['schema_sha256']='wrong'
        with self.assertRaises(Refused):self.apply()
        self.assertEqual(self.rt.calls,[])
    def test_conflicting_legacy_bytes_refuse(self):
        (self.active/'app.py').write_text('unexpected')
        with self.assertRaises(Refused):self.apply()
        self.assertEqual(self.rt.calls,[])
    def test_failure_holds_then_explicit_recovery(self):
        self.rt.fail_accept=True
        with self.assertRaises(RuntimeError):self.apply()
        tx=next(self.store.glob('transaction-*'));self.assertTrue(self.rt.guarded)
        self.assertEqual(json.loads((tx/'transaction.json').read_text())['phase'],'RECOVERY_REQUIRED')
        self.rt.fail_accept=False;self.engine.rollback(tx,True)
        self.assertEqual((self.active/'app.py').read_text(),'old')
    def test_phase_interruptions_recover_original_bytes(self):
        for phase in ('STAGING','STAGED','GUARD_INTENT','GUARDED','QUIESCED','OLD_RENAME_INTENT','OLD_RETAINED','ACTIVATED','ACCEPTED','RESUME_AUTHORIZED'):
            with self.subTest(phase=phase):
                def interrupt(value):
                    if value==phase:raise KeyboardInterrupt(phase)
                self.engine.fault=interrupt
                with self.assertRaises(KeyboardInterrupt):self.apply()
                tx=next(p for p in self.store.glob('transaction-*') if json.loads((p/'transaction.json').read_text())['phase']!='ROLLED_BACK')
                self.engine.fault=lambda p:None
                self.engine.rollback(tx,True)
                self.assertEqual(inventory(self.active,os.getuid()),self.before)
    def test_concurrent_operation_refused(self):
        with self.engine.lock():
            with self.assertRaises(Refused):self.apply()
    def test_corrupt_backup_refuses_rollback(self):
        tx=self.apply();(tx/'previous/app.py').write_text('corruption')
        with self.assertRaises(Refused):self.engine.rollback(tx,True)
        self.assertEqual((self.active/'app.py').read_text(),'new')
    def test_rollback_schema_change_refused(self):
        tx=self.apply()
        with closing(sqlite3.connect(self.db)) as c, c:c.execute('CREATE TABLE unexpected(x)')
        with self.assertRaises(Refused):self.engine.rollback(tx,True)
    def test_writable_code_refused(self):
        (self.candidate/'app.py').chmod(0o666)
        with self.assertRaises(Refused):self.apply()
    def test_foreign_link_refused(self):
        (self.candidate/'escape').symlink_to(self.conf)
        with self.assertRaises(Refused):self.apply()
    def test_protected_change_blocks_rollback(self):
        tx=self.apply();self.conf.write_text('later legitimate change')
        with self.assertRaises(Refused):self.engine.rollback(tx,True)
    def test_wal_backup_restoration(self):
        c=sqlite3.connect(self.db);self.addCleanup(c.close)
        c.execute('PRAGMA journal_mode=WAL');c.execute("INSERT INTO incidents VALUES(3,'OPEN','WAL')");c.commit()
        tx=self.apply()
        self.assertEqual(database_snapshot(tx/'state-backup.sqlite'),database_snapshot(self.db))
        self.assertEqual(database_snapshot(tx/'restore-proof.sqlite'),database_snapshot(self.db))
    def test_table_row_transfer_changes_logical_digest(self):
        with closing(sqlite3.connect(self.db)) as c,c:
            c.executescript("CREATE TABLE a(x);CREATE TABLE b(x);INSERT INTO a VALUES(1)")
        before=database_snapshot(self.db)
        with closing(sqlite3.connect(self.db)) as c,c:c.executescript("DELETE FROM a;INSERT INTO b VALUES(1)")
        self.assertNotEqual(before['logical_sha256'],database_snapshot(self.db)['logical_sha256'])
    def test_other_pending_transaction_blocks_rollback(self):
        tx=self.apply();other=self.store/'transaction-other';other.mkdir(mode=0o700)
        (other/'transaction.json').write_text(json.dumps({'phase':'STAGED'}))
        with self.assertRaises(Refused):self.engine.rollback(tx,True)
    def test_rollback_guard_failure_is_recovery_required(self):
        tx=self.apply()
        def fail(*args):raise RuntimeError('guard failure')
        self.rt.guard=fail
        with self.assertRaises(RuntimeError):self.engine.rollback(tx,True)
        self.assertEqual(json.loads((tx/'transaction.json').read_text())['phase'],'RECOVERY_REQUIRED')
    def test_schema_change_while_quiescing_refused(self):
        def change(*args):
            with closing(sqlite3.connect(self.db)) as c,c:c.execute('CREATE TABLE changed(x)')
        self.rt.quiesce=change
        with self.assertRaises(Refused):self.apply()
        self.assertEqual((self.active/'app.py').read_text(),'old')
    @unittest.skipUnless(hasattr(os,'fork'),'requires POSIX fork')
    def test_actual_process_exit_recovery(self):
        for phase in ('STAGED','GUARDED','OLD_RENAME_INTENT','OLD_RETAINED','ACTIVATED','ACCEPTED','RESUME_AUTHORIZED'):
            with self.subTest(phase=phase):
                pid=os.fork()
                if pid==0:
                    self.engine.fault=lambda p:os._exit(77) if p==phase else None
                    try:self.apply()
                    except BaseException:os._exit(78)
                    os._exit(79)
                _,status=os.waitpid(pid,0);self.assertEqual(os.waitstatus_to_exitcode(status),77)
                tx=next(p for p in self.store.glob('transaction-*') if json.loads((p/'transaction.json').read_text())['phase']!='ROLLED_BACK')
                self.engine.rollback(tx,True)
                self.assertEqual(inventory(self.active,os.getuid()),self.before)
if __name__=='__main__':unittest.main()
