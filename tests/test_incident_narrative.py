import json
import unittest
from unittest.mock import patch
from rackmarshal.api.v1 import incident_summary
from rackmarshal.ui.dashboard import dashboard_data, render_incident_index, collection_data, render_collection_coverage
from rackmarshal.ui.incidents import render_incident_page
from tests import test_api_v11_timeline as fixtures


class IncidentNarrative(unittest.TestCase):
    def setUp(self):
        self.fx = fixtures.ApiV11Timeline()
        self.fx.setUp()
        self.db = self.fx.db

    def tearDown(self):
        self.fx.tearDown()

    def test_dashboard_reads_all_pages_and_orders_by_recovery(self):
        row = dict(self.db.execute("SELECT * FROM backup_incidents").fetchone())
        columns = list(row)
        sql = "INSERT INTO backup_incidents (" + ",".join(columns) + ") VALUES (" + ",".join("?" for _ in columns) + ")"
        for number in range(2, 207):
            item = dict(row, id=number, opened_at="2026-09-30T00:00:00Z")
            self.db.execute(sql, [item[c] for c in columns])
        self.db.execute("UPDATE backup_incidents SET incident_state='OPEN', recovered_at=NULL WHERE id=1")
        self.db.execute("UPDATE backup_incidents SET opened_at='2020-01-01T00:00:00Z', recovered_at='2026-10-01T00:00:00Z' WHERE id=2")
        data = dashboard_data(self.db)
        self.assertEqual(data["open_count"], 3)
        self.assertEqual(data["open_by_domain"]["BACKUP"], 1)
        self.assertEqual(data["recent_recoveries"][0]["id"], "BACKUP:2")
        self.assertIn("BACKUP:1", [x["id"] for x in data["open_incidents"]])

    def test_all_open_incidents_beyond_page_limit_are_counted(self):
        for number in range(2, 207):
            self.db.execute("INSERT INTO backup_incidents(id,incident_state,opened_at) VALUES (?,'OPEN','2026-09-30T00:00:00Z')", (number,))
        data = dashboard_data(self.db)
        self.assertEqual(data["open_by_domain"]["BACKUP"], 205)
        self.assertEqual(data["open_count"], 207)

    def test_missing_domain_ledger_is_explicit(self):
        page = render_incident_index(self.db)
        self.assertIn("Incident ledgers unavailable: ZFS, HA, MOUNT", page)
        self.assertIn("Counts cover available ledgers only", page)

    def test_collection_freshness_uses_existing_policy_callback_and_latest_ids(self):
        def build(observations, now=None):
            self.assertEqual(observations["BACKUP"]["id"], "BACKUP:3")
            self.assertEqual(observations["PVE"]["id"], "PVE:20")
            self.assertIsNone(observations["MOUNT"])
            self.assertIsNotNone(now.tzinfo)
            return {"BACKUP": {"state": "STALE", "stale_after_seconds": 77}, "PVE": {"state": "OK", "stale_after_seconds": 900}}
        page=render_incident_index(self.db,freshness_builder=build)
        self.assertIn('data-domain="BACKUP" data-observation-id="BACKUP:3" data-freshness="STALE"',page)
        self.assertIn("Stale after 77 seconds",page)
        self.assertIn("Fresh observations do not prove a cycle completed successfully or an incident recovered",page)
        self.assertIn("/v1/evidence/observation:BACKUP:3",page)
        self.assertNotIn("DO-NOT-EXPOSE",page)

    def test_unavailable_collection_metadata_is_explicit(self):
        page=render_incident_index(self.db)
        self.assertIn("Freshness unavailable",page)
        self.assertIn("Observation not recorded",page)
        self.assertIn('data-cycle-state="NOT_RECORDED"',page)
        self.assertNotIn("Recorded success",page)

    def test_historical_cycle_name_is_not_a_current_unit_result(self):
        self.db.execute("CREATE TABLE cycle_health(unit_name TEXT,health_state TEXT,last_result_at TEXT,last_success_at TEXT,last_failure_at TEXT,failure_count INTEGER)")
        self.db.execute("INSERT INTO cycle_health VALUES('fixture-old-backup.service','SUCCESS','2026-09-01T00:00:00Z','2026-09-01T00:00:00Z',NULL,7)")
        data=collection_data(self.db)
        backup=next(row for row in data["domains"] if row["domain"]=="BACKUP")
        self.assertIsNone(backup["cycle"])
        page=render_incident_index(self.db)
        self.assertIn("Other recorded cycle units (historical records)",page)
        self.assertIn("fixture-old-backup.service",page)
        self.assertIn("Cumulative recorded failures: 7",page)
        self.assertIn('data-domain="BACKUP" data-observation-id="BACKUP:3" data-freshness="UNKNOWN" data-cycle-state="NOT_RECORDED"',page)

    def test_current_cycle_failure_and_old_success_remain_distinct(self):
        self.db.execute("CREATE TABLE cycle_health(unit_name TEXT,health_state TEXT,last_result_at TEXT,last_success_at TEXT,last_failure_at TEXT,failure_count INTEGER)")
        self.db.execute("INSERT INTO cycle_health VALUES('rackmarshal-domain@backup.service','FAILED','2026-09-30T01:00:00Z','2026-09-29T01:00:00Z','2026-09-30T01:00:00Z',2)")
        page=render_incident_page(self.db,"BACKUP:1")
        self.assertIn('data-cycle-state="FAILED"',page)
        self.assertIn("Recorded failure",page)
        self.assertIn("Last success:",page)
        self.assertIn("Recovery recorded. Historical incident.",page)
        self.assertEqual(page.count('data-domain='),1)

    def test_collection_values_are_escaped_and_no_detail_payload_is_read(self):
        self.db.execute("CREATE TABLE cycle_health(unit_name TEXT,health_state TEXT,last_result_at TEXT,detail_json TEXT)")
        self.db.execute("INSERT INTO cycle_health VALUES('rackmarshal-domain@backup.service','FAILED',?,?)", ('<script>bad</script>', '{"secret":"DO-NOT-EXPOSE"}'))
        self.db.execute("UPDATE observations SET observed_at=? WHERE id=3", ('<img src=x>',))
        page=render_collection_coverage(self.db,domain="BACKUP")
        self.assertIn("&lt;script&gt;bad&lt;/script&gt;",page)
        self.assertIn("&lt;img src=x&gt;",page)
        for forbidden in ("<script>","<img", "detail_json", "DO-NOT-EXPOSE", "payload_json"):
            self.assertNotIn(forbidden,page)


    def test_summary_additive_fields_match_record(self):
        summary = incident_summary(self.db, "BACKUP:1")
        self.assertEqual(summary["display_name"], "Fictional phone")
        self.assertEqual(summary["occurrence_count"], 2)
        self.assertEqual(summary["opened_at"], "2026-09-29T01:00:00Z")
        self.assertEqual(summary["recovered_at"], "2026-09-29T03:00:00Z")
        self.assertNotIn("DO-NOT-EXPOSE", json.dumps(summary))

    def test_open_and_historical_state_explain_health_boundary(self):
        opened = render_incident_page(self.db, "PVE:2")
        recovered = render_incident_page(self.db, "BACKUP:1")
        self.assertIn("No recovery is recorded.", opened)
        self.assertNotIn("Recovery observed", opened)
        self.assertIn("Recovery recorded. Historical incident.", recovered)
        self.assertIn("Historical recovery does not establish current health", recovered)
        self.assertIn("2 recorded abnormal occurrences", recovered)
        self.assertIn('datetime="2026-09-29T03:00:00Z"', recovered)

    def test_missing_lifecycle_and_occurrence_fields_are_not_invented(self):
        self.db.execute("UPDATE backup_incidents SET opened_at=NULL,last_abnormal_at=NULL,occurrence_count=NULL WHERE id=1")
        summary = incident_summary(self.db, "BACKUP:1")
        page = render_incident_page(self.db, "BACKUP:1")
        self.assertIn("Opening time is not recorded", summary["opened_statement"])
        self.assertIn("Latest abnormal time is not recorded", summary["latest_statement"])
        self.assertIn("Occurrence count not recorded", page)
        self.assertNotIn(" at None", page)

    def test_direct_and_legacy_provenance_and_canonical_links(self):
        direct = render_incident_page(self.db, "BACKUP:1")
        legacy = render_incident_page(self.db, "PVE:2")
        self.assertIn("use stored event IDs", direct)
        self.assertIn("correlated events are not stored direct links", legacy)
        for suffix in ("summary", "timeline", "evidence-bundle"):
            self.assertIn("/v1/incidents/BACKUP:1/" + suffix, direct)
        self.assertIn("/v1/evidence/observation:BACKUP:3", direct)

    def test_new_fields_are_escaped_and_controls_absent(self):
        self.db.execute("UPDATE backup_incidents SET incident_type=?,resource_key=?,opened_at=? WHERE id=1",
                        ('<script>bad</script>', '<img src=x onerror=bad>', '"><svg onload=bad>'))
        for page in (render_incident_index(self.db), render_incident_page(self.db, "BACKUP:1")):
            self.assertNotIn("<script>", page)
            self.assertNotIn("<img", page)
            self.assertNotIn("<svg", page)
            self.assertIn("&lt;script&gt;bad&lt;/script&gt;", page)
            for prohibited in ("<form", "<button", "<input", "payload_json", "DO-NOT-EXPOSE"):
                self.assertNotIn(prohibited, page)

    def test_timeline_repeat_count_is_recorded_not_inferred(self):
        from rackmarshal.api.v1 import incident_timeline
        timeline = incident_timeline(self.db, "BACKUP:1")
        timeline["items"].insert(1, dict(kind="MATERIAL_CHANGE", timestamp="2026-09-29T02:00:00Z",
                                       first_observed_at="2026-09-29T01:30:00Z", repeat_count=7,
                                       changes=[], evidence_refs=[]))
        with patch("rackmarshal.ui.incidents.incident_timeline", return_value=timeline):
            page = render_incident_page(self.db, "BACKUP:1")
        self.assertIn("7 recorded occurrences of this change", page)
        self.assertIn("2026-09-29T01:30:00Z", page)


if __name__ == "__main__":
    unittest.main()
