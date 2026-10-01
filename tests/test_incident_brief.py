import copy
import unittest
from unittest.mock import patch
from rackmarshal.ui.narrative import incident_brief
from rackmarshal.ui.incidents import render_incident_page
from rackmarshal.api.v1 import incident_summary, incident_timeline
from tests import test_api_v11_timeline as fixtures


class IncidentBriefTests(unittest.TestCase):
    def setUp(self):
        self.fx=fixtures.ApiV11Timeline(); self.fx.setUp(); self.db=self.fx.db
    def tearDown(self):
        self.fx.tearDown()
    def test_trigger_and_recovery_reference_are_recorded_not_cause_or_live_health(self):
        summary=incident_summary(self.db,"BACKUP:1"); timeline=incident_timeline(self.db,"BACKUP:1")
        brief=incident_brief(summary,timeline)
        self.assertEqual(brief["opening"]["changes"][0]["actual"],170)
        self.assertEqual(brief["last_abnormal"]["changes"][0]["actual"],171)
        self.assertIn("observation:BACKUP:3",brief["recovery"]["evidence_refs"])
        self.assertEqual(brief["conflicts"],[])
        page=render_incident_page(self.db,"BACKUP:1")
        for label in ("What the records establish","Opening condition","Latest abnormal condition","What remains unknown","do not establish root cause","does not establish current resource health"):
            self.assertIn(label,page)
        self.assertNotIn("DO-NOT-EXPOSE",page)
    def test_missing_latest_condition_never_substitutes_opening(self):
        self.db.execute("UPDATE backup_incidents SET latest_changes_json=NULL,last_event_id=NULL WHERE id=1")
        self.db.execute("DELETE FROM backup_events WHERE id=11")
        brief=incident_brief(incident_summary(self.db,"BACKUP:1"),incident_timeline(self.db,"BACKUP:1"))
        self.assertTrue(brief["opening"]["changes"])
        self.assertFalse((brief["last_abnormal"] or {}).get("changes"))
        self.assertTrue(any("opening condition is not substituted" in gap for gap in brief["gaps"]))
    def test_open_with_recovery_pointer_is_explicit_conflict(self):
        self.db.execute("UPDATE backup_incidents SET incident_state='OPEN' WHERE id=1")
        page=render_incident_page(self.db,"BACKUP:1")
        self.assertIn("Conflicting records",page)
        self.assertIn("OPEN state conflicts",page)
        self.assertIn("Recovery interpretation is withheld",page)
        self.assertNotIn("No recovery is recorded.",page)
    def test_recovery_before_abnormal_requires_review(self):
        self.db.execute("UPDATE backup_incidents SET recovered_at='2026-09-29T00:00:00Z' WHERE id=1")
        brief=incident_brief(incident_summary(self.db,"BACKUP:1"),incident_timeline(self.db,"BACKUP:1"))
        self.assertTrue(any("out of order" in x for x in brief["conflicts"]))
    def test_missing_recovery_time_and_refs_are_gaps_not_invented(self):
        summary=incident_summary(self.db,"BACKUP:1"); summary["recovered_at"]=None
        timeline=incident_timeline(self.db,"BACKUP:1")
        timeline["items"]=[x for x in timeline["items"] if x["kind"]!="INCIDENT_RECOVERED"]
        brief=incident_brief(summary,timeline)
        self.assertTrue(any("recovery time is not recorded" in x for x in brief["gaps"]))
        self.assertTrue(any("Recovery supporting references" in x for x in brief["gaps"]))
    def test_timezone_unknown_does_not_invent_order(self):
        summary=incident_summary(self.db,"BACKUP:1"); summary["recovered_at"]="2020-01-01T00:00:00"
        brief=incident_brief(summary,incident_timeline(self.db,"BACKUP:1"))
        self.assertFalse(brief["conflicts"])
        self.assertTrue(any("valid timezone" in x for x in brief["gaps"]))
    def test_timezone_offsets_compare_instants_not_strings(self):
        summary=incident_summary(self.db,"BACKUP:1"); summary["recovered_at"]="2026-09-29T04:00:00+02:00"
        timeline=incident_timeline(self.db,"BACKUP:1")
        next(x for x in timeline["items"] if x["kind"]=="INCIDENT_RECOVERED")["timestamp"]="2026-09-29T02:00:00Z"
        brief=incident_brief(summary,timeline)
        self.assertFalse(brief["conflicts"])
        summary["recovered_at"]="2026-09-29T03:00:00Z"
        brief=incident_brief(summary,timeline)
        self.assertTrue(any("timestamps disagree" in x for x in brief["conflicts"]))
        summary["recovered_at"]="2026-09-29T03:30:00+02:00"
        self.assertTrue(incident_brief(summary,incident_timeline(self.db,"BACKUP:1"))["conflicts"])
    def test_malicious_changes_escaped_and_absent_expected_is_labeled(self):
        timeline=incident_timeline(self.db,"BACKUP:1"); opening=timeline["items"][0]
        opening["changes"]=[{"field":"<svg onload=bad>","actual":"<script>bad</script>","expected":None}]
        with patch("rackmarshal.ui.incidents.incident_timeline",return_value=timeline):
            page=render_incident_page(self.db,"BACKUP:1")
        self.assertIn("&lt;svg",page); self.assertIn("expected Not recorded",page)
        self.assertNotIn("<svg",page); self.assertNotIn("<script>",page)
    def test_brief_is_deterministic_and_does_not_modify_inputs(self):
        summary=incident_summary(self.db,"BACKUP:1"); timeline=incident_timeline(self.db,"BACKUP:1")
        before=copy.deepcopy((summary,timeline))
        self.assertEqual(incident_brief(summary,timeline),incident_brief(summary,timeline))
        self.assertEqual((summary,timeline),before)

if __name__=="__main__": unittest.main()
