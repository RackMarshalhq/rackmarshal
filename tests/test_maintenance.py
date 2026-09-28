import sqlite3, tempfile, unittest
from datetime import datetime, timezone
from pathlib import Path
from rackmarshal.maintenance.snapshot import create_snapshot
from rackmarshal.maintenance.prune import prune

class MaintenanceTests(unittest.TestCase):
 def test_snapshot_is_valid_and_retained(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td); db=root/'state.db'; out=root/'snaps'
   c=sqlite3.connect(db); c.execute('create table x(v text)'); c.execute("insert into x values('ok')"); c.commit(); c.close()
   dest=create_snapshot(db,out,2)
   self.assertTrue(dest.is_file()); self.assertTrue((out/'state.db.latest').is_file())
   c=sqlite3.connect(dest); self.assertEqual(c.execute('pragma quick_check').fetchone()[0],'ok'); c.close()
 def test_prune_preserves_referenced_observation(self):
  with tempfile.TemporaryDirectory() as td:
   db=Path(td)/'state.db'; c=sqlite3.connect(db)
   c.executescript('create table observations(id integer primary key, observed_at text); create table refs(id integer primary key, observation_id integer references observations(id));')
   c.execute("insert into observations values(1,'2020-01-01T00:00:00')"); c.execute("insert into observations values(2,'2020-01-01T00:00:00')"); c.execute('insert into refs values(1,1)'); c.commit(); c.close()
   result=prune(db,35,datetime(2026,1,1,tzinfo=timezone.utc)); self.assertEqual(result['observations'],1)
   c=sqlite3.connect(db); self.assertEqual(c.execute('select id from observations').fetchall(),[(1,)]); c.close()
if __name__=='__main__': unittest.main()
