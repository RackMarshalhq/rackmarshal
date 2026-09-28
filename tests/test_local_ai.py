import json, os, sqlite3, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

from rackmarshal.incidents import explain
from rackmarshal.notifications import explain_worker
from rackmarshal.cli import validate

class LocalAITests(unittest.TestCase):
    def test_explainer_import_is_site_independent(self):
        packet={"resource_type":"qemu","resource_key":"9001","display_name":"Fictional VM","incident_type":"STATUS-CHANGED","baseline_state":"VERIFIED","expected_status":"running","actual_status":"stopped","occurrence_count":1}
        validated=explain.validate_packet(packet)
        summary=explain.deterministic_summary(validated)
        self.assertIn("Fictional VM", summary)

    def test_local_ai_enabled_requires_ollama_settings(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"c"; p.write_text("STATE_DB=/tmp/x\nLOCAL_AI_ENABLED=true\n")
            errors=validate(p)
            self.assertTrue(any("OLLAMA_URL" in e for e in errors))
            self.assertTrue(any("OLLAMA_MODEL" in e for e in errors))

    def test_worker_success_never_overwrites_successful_ai(self):
        con=sqlite3.connect(":memory:"); con.row_factory=sqlite3.Row
        con.execute("create table incident_notifications(id integer primary key, packet_json text, explanation_json text, created_at text, delivery_state text)")
        packet=json.dumps({"incident":{"resource_type":"qemu","resource_key":"9001","display_name":"Fictional VM","incident_type":"STATUS-CHANGED","baseline_state":"VERIFIED","expected_status":"running","actual_status":"stopped","occurrence_count":1}})
        con.execute("insert into incident_notifications values(1,?,?,?,?)",(packet,None,"2026-01-01T00:00:00Z","PENDING")); con.commit()
        row=con.execute("select * from incident_notifications where id=1").fetchone()
        with patch.object(explain_worker,"run_explainer",return_value=(True,{"summary":"ok"})):
            self.assertEqual(explain_worker.process_row(con,row,20,False),"succeeded")
        rec=json.loads(con.execute("select explanation_json from incident_notifications where id=1").fetchone()[0])
        self.assertEqual(rec["mode"],"AI"); self.assertTrue(rec["explainer_succeeded"])
        row=con.execute("select * from incident_notifications where id=1").fetchone()
        with patch.object(explain_worker,"run_explainer",side_effect=AssertionError("must not rerun")):
            self.assertEqual(explain_worker.process_row(con,row,20,False),"skipped_ai")

    def test_worker_failure_records_fallback(self):
        con=sqlite3.connect(":memory:"); con.row_factory=sqlite3.Row
        con.execute("create table incident_notifications(id integer primary key, packet_json text, explanation_json text, created_at text, delivery_state text)")
        packet=json.dumps({"incident":{"resource_type":"qemu","resource_key":"9001","display_name":"Fictional VM","incident_type":"STATUS-CHANGED"}})
        con.execute("insert into incident_notifications values(1,?,?,?,?)",(packet,None,"2026-01-01T00:00:00Z","PENDING")); con.commit()
        row=con.execute("select * from incident_notifications where id=1").fetchone()
        with patch.object(explain_worker,"run_explainer",return_value=(False,"fictional outage")):
            self.assertEqual(explain_worker.process_row(con,row,20,False),"failed")
        rec=json.loads(con.execute("select explanation_json from incident_notifications where id=1").fetchone()[0])
        self.assertEqual(rec["mode"],"FALLBACK"); self.assertFalse(rec["explainer_succeeded"])

if __name__ == '__main__': unittest.main()
