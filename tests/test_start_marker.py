"""First-run starting marker for the Proxmox and backup incident processors (synthetic data only)."""
import importlib
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from rackmarshal.domains.start_marker import StartMarkerRefused, resolve_checkpoint


def difference(status='stopped'):
    return {'resource_type': 'qemu', 'resource_key': '9001', 'display_name': 'Fictional VM', 'result': 'STATUS-CHANGED',
            'baseline_state': 'VERIFIED', 'expected_status': 'running', 'actual_status': status, 'note': ''}


class StartMarkerTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.db = self.root / 'state.db'
        conf = self.root / 'rackmarshal.conf'
        conf.write_text(f'STATE_DB={self.db}\nSITE_NAME=fictional\n')
        os.environ['RACKMARSHAL_CONFIG'] = str(conf)
        os.environ['RACKMARSHAL_STATE_DB'] = str(self.db)
        import rackmarshal.core.config as cfg
        self.old_default = cfg.DEFAULT_CONFIG_FILE
        cfg.DEFAULT_CONFIG_FILE = conf
        cfg.state_db.__defaults__ = (None,)
        from rackmarshal.db.migrations import migrate
        argv = sys.argv
        sys.argv = ['migrate', '--db', str(self.db), '--apply', '--yes']
        try:
            migrate.main()
        finally:
            sys.argv = argv

    def tearDown(self):
        import rackmarshal.core.config as cfg
        cfg.DEFAULT_CONFIG_FILE = self.old_default
        for name in list(sys.modules):
            if name.startswith('rackmarshal.domains.') and name.endswith('.incidents'):
                sys.modules.pop(name, None)
        self.td.cleanup()

    def obs(self, collector, minute):
        with closing(sqlite3.connect(self.db)) as c:
            c.execute('insert into observations(collector,observed_at,source,schema_version,tls_verified,resource_count,payload_json) values(?,?,?,?,?,?,?)',
                      (collector, f'2026-01-01T03:{minute:02d}:00Z', 'fictional', 1, 1, 1, '{}'))
            oid = c.execute('select last_insert_rowid()').fetchone()[0]
            c.commit()
        return oid

    def conn(self):
        c = sqlite3.connect(self.db)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON')
        return c

    def markers(self, table='incident_processing'):
        with closing(self.conn()) as c:
            return [tuple(r) for r in c.execute(f'select observation_id, processing_kind from {table} order by 1')]

    # ---- the helper
    def test_no_earlier_observation_means_nothing_to_mark(self):
        first = self.obs('pve_cluster_resources', 0)
        with closing(self.conn()) as c:
            self.assertEqual(resolve_checkpoint(c, 'pve', first, True), 0)
        self.assertEqual(self.markers(), [])

    def test_marker_goes_at_the_newest_earlier_observation_of_the_same_kind_only(self):
        older = self.obs('pve_cluster_resources', 0)
        newest_earlier = self.obs('pve_cluster_resources', 1)
        self.obs('home_assistant', 2)
        current = self.obs('pve_cluster_resources', 3)
        later = self.obs('pve_cluster_resources', 4)
        with closing(self.conn()) as c:
            self.assertEqual(resolve_checkpoint(c, 'pve', current, True), newest_earlier)
            c.commit()
        self.assertEqual(self.markers(), [(newest_earlier, 'BOOTSTRAP')])
        self.assertNotIn(older, [m[0] for m in self.markers()])
        self.assertNotIn(later, [m[0] for m in self.markers()])

    def test_plan_only_writes_nothing(self):
        earlier = self.obs('pve_cluster_resources', 0)
        current = self.obs('pve_cluster_resources', 1)
        with closing(self.conn()) as c:
            self.assertEqual(resolve_checkpoint(c, 'pve', current, False), earlier)
            c.commit()
        self.assertEqual(self.markers(), [])

    def test_a_ledger_with_rows_is_left_alone(self):
        earlier = self.obs('pve_cluster_resources', 0)
        current = self.obs('pve_cluster_resources', 1)
        with closing(self.conn()) as c:
            c.execute("insert into incident_processing(observation_id,processing_kind,note) values(?,'BOOTSTRAP','fixture')", (earlier,))
            c.commit()
            self.assertIsNone(resolve_checkpoint(c, 'pve', current, True))
            c.commit()
        self.assertEqual(self.markers(), [(earlier, 'BOOTSTRAP')])

    def test_empty_ledger_with_existing_incidents_is_refused(self):
        self.obs('pve_cluster_resources', 0)
        current = self.obs('pve_cluster_resources', 1)
        with closing(self.conn()) as c:
            c.execute("insert into resource_incidents(resource_type,resource_key,display_name,incident_type,incident_state,baseline_state,expected_status,abnormal_status,opened_observation_id,last_abnormal_observation_id,opened_at,last_abnormal_at) values('qemu','1','x','STATUS-CHANGED','OPEN','VERIFIED','running','stopped',1,1,'2026-01-01T00:00:00Z','2026-01-01T00:00:00Z')")
            c.commit()
            with self.assertRaises(StartMarkerRefused):
                resolve_checkpoint(c, 'pve', current, True)
        self.assertEqual(self.markers(), [])

    def test_backup_uses_its_own_tables_and_collector(self):
        earlier = self.obs('backup_domain', 0)
        self.obs('pve_cluster_resources', 1)
        current = self.obs('backup_domain', 2)
        with closing(self.conn()) as c:
            self.assertEqual(resolve_checkpoint(c, 'backup', current, True), earlier)
            c.commit()
        self.assertEqual(self.markers('backup_incident_processing'), [(earlier, 'BOOTSTRAP')])
        self.assertEqual(self.markers(), [])

    # ---- the Proxmox processor end to end
    def processor(self, diffs):
        p = importlib.import_module('rackmarshal.domains.pve.incidents')
        p.run_comparator = lambda x: {'schema_version': 1, 'comparator': 'pve_resource_baseline', 'observation_id': x, 'differences': diffs}
        return p

    def test_first_run_with_carried_history_processes_the_new_observation_and_opens_the_incident(self):
        self.obs('pve_cluster_resources', 0)
        self.obs('pve_cluster_resources', 1)
        current = self.obs('pve_cluster_resources', 2)
        p = self.processor([difference()])
        result = p.process(current)
        self.assertEqual(result['incidents_opened'], 1)
        kinds = dict(self.markers())
        self.assertEqual(kinds[current], 'PROCESSED')
        self.assertEqual(sorted(kinds.values()), ['BOOTSTRAP', 'PROCESSED'])
        # the next observation follows on normally
        nxt = self.obs('pve_cluster_resources', 3)
        p = self.processor([])
        self.assertEqual(p.process(nxt)['incidents_recovered'], 1)

    def test_the_read_only_preflight_does_not_fail_or_write_on_a_first_run(self):
        self.obs('pve_cluster_resources', 0)
        current = self.obs('pve_cluster_resources', 1)
        p = importlib.import_module('rackmarshal.domains.pve.incidents')
        p.DB_FILE = str(self.db)
        import contextlib
        import io
        captured = io.StringIO()
        with contextlib.redirect_stderr(captured):
            self.assertIsNone(p.preflight_processing_order(current))
        self.assertNotIn('starting marker created', captured.getvalue())
        self.assertEqual(self.markers(), [])
        # once the ledger has a row, a skipped observation is still caught by the preflight
        with closing(self.conn()) as c:
            c.execute("insert into incident_processing(observation_id,processing_kind,note) values(?,'BOOTSTRAP','fixture')", (current,))
            c.commit()
        self.obs('pve_cluster_resources', 2)
        third = self.obs('pve_cluster_resources', 3)
        with self.assertRaisesRegex(Exception, 'observation gap'):
            p.preflight_processing_order(third)

    def test_first_run_with_no_history_processes_the_first_observation(self):
        first = self.obs('pve_cluster_resources', 0)
        p = self.processor([difference()])
        self.assertEqual(p.process(first)['incidents_opened'], 1)
        self.assertEqual(self.markers(), [(first, 'PROCESSED')])

    def test_after_the_first_run_a_skipped_observation_is_still_a_gap(self):
        self.obs('pve_cluster_resources', 0)
        first = self.obs('pve_cluster_resources', 1)
        self.processor([]).process(first)
        self.obs('pve_cluster_resources', 2)  # never processed
        third = self.obs('pve_cluster_resources', 3)
        with self.assertRaisesRegex(Exception, 'observation gap'):
            self.processor([]).process(third)

    def test_refusal_reaches_the_processor_error(self):
        self.obs('pve_cluster_resources', 0)
        current = self.obs('pve_cluster_resources', 1)
        with closing(self.conn()) as c:
            c.execute("insert into resource_incidents(resource_type,resource_key,display_name,incident_type,incident_state,baseline_state,expected_status,abnormal_status,opened_observation_id,last_abnormal_observation_id,opened_at,last_abnormal_at) values('qemu','1','x','STATUS-CHANGED','OPEN','VERIFIED','running','stopped',1,1,'2026-01-01T00:00:00Z','2026-01-01T00:00:00Z')")
            c.commit()
        with self.assertRaisesRegex(Exception, 'refusing to create a starting marker'):
            self.processor([]).process(current)
        self.assertEqual(self.markers(), [])
    # ---- the backup processor end to end (command line, like the cycle runs it)
    def run_backup(self, observation_id, minute):
        import json
        import subprocess
        payload = {'schema_version': 1, 'comparator': 'backup_baseline', 'observation_id': observation_id,
                   'observed_at': f'2026-01-01T03:{minute:02d}:00Z',
                   'results': [{'resource_type': 'backup_guest', 'resource_key': 'fictional-guest', 'display_name': 'Fictional Guest',
                                'outcome': 'MATCH', 'baseline_state': 'VERIFIED', 'changes': []}]}
        return subprocess.run([sys.executable, '-m', 'rackmarshal.domains.backup.incidents', '--database', str(self.db)],
                              input=json.dumps(payload), text=True, capture_output=True)

    def test_backup_first_run_creates_its_marker_and_processes(self):
        self.obs('backup_domain', 0)
        current = self.obs('backup_domain', 1)
        result = self.run_backup(current, 1)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('starting marker created', result.stderr)
        self.assertEqual(sorted(k for _, k in self.markers('backup_incident_processing')), ['BOOTSTRAP', 'PROCESSED'])
        self.assertEqual(self.run_backup(self.obs('backup_domain', 2), 2).returncode, 0)

    def test_backup_skipped_observation_is_still_a_gap_after_the_first_run(self):
        self.obs('backup_domain', 0)
        first = self.obs('backup_domain', 1)
        self.assertEqual(self.run_backup(first, 1).returncode, 0)
        self.obs('backup_domain', 2)
        third = self.obs('backup_domain', 3)
        result = self.run_backup(third, 3)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('gap', result.stderr + result.stdout)


if __name__ == '__main__':
    unittest.main()
