import unittest

from rackmarshal.notifications import delivery, plain_language


def packet(domain, **incident):
    return {"source_domain": domain, "incident": incident}


class PlainLanguageAlertTests(unittest.TestCase):
    def test_missing_guest_explains_and_names_the_retire_command(self):
        text = delivery.deterministic_opened(packet(
            "PVE", resource_type="lxc", resource_key="123", display_name="Test CT",
            incident_type="MISSING", expected_status="running", occurrence_count=1))
        self.assertIn("What happened: RackMarshal expected the container Test CT but could not find it.", text)
        self.assertIn("Does it matter:", text)
        self.assertIn("rackmarshal retire-guest 123", text)
        self.assertIn("Technical details: Incident opened for Test CT. Type: MISSING.", text)

    def test_retire_hint_is_only_for_proxmox_guests(self):
        text = delivery.deterministic_opened(packet(
            "BACKUP", resource_type="backup_job", resource_key="job-1", display_name="Job",
            incident_type="MISSING"))
        self.assertNotIn("retire-guest", text)

    def test_new_item_is_not_alarming(self):
        what, matter, todo = plain_language.opened_lines("BACKUP", {
            "resource_type": "backup_guest", "resource_key": "9", "display_name": "x", "incident_type": "NEW"})
        self.assertIn("not told about", what)
        self.assertIn("harmless", matter)

    def test_status_change_states_both_values(self):
        what, _, _ = plain_language.opened_lines("PVE", {
            "resource_type": "qemu", "resource_key": "5", "display_name": "VM", "incident_type": "STATUS-CHANGED",
            "expected_status": "running", "actual_status": "stopped"})
        self.assertIn("It is stopped; normal is running.", what)

    def test_secondary_coverage_has_its_own_wording(self):
        text = delivery.deterministic_opened(packet(
            "BACKUP", resource_type="backup_host_verify", resource_key="pbs-secondary-coverage",
            display_name="PBS secondary coverage and metadata", incident_type="STATUS-CHANGED"))
        self.assertIn("second copy of your backups", text)

    def test_unknown_type_falls_back_without_guessing(self):
        what, matter, _ = plain_language.opened_lines("ZFS", {"display_name": "tank", "incident_type": "ODD"})
        self.assertIn("noticed a problem with tank", what)
        self.assertIn("cannot tell", matter)

    def test_recovery_is_plain_and_does_not_overclaim(self):
        text = delivery.deterministic_recovery({
            "source_domain": "PVE", "incident": {"resource_type": "lxc", "display_name": "Test CT",
                                                 "incident_type": "MISSING", "occurrence_count": 3},
            "recovery": {"recovered_at": "2026-01-01T00:00:00Z"}})
        self.assertIn("Test CT (container) is back to normal.", text)
        self.assertIn("does not prove it stays that way", text)
        self.assertIn("Recovered at 2026-01-01T00:00:00Z.", text)


if __name__ == "__main__":
    unittest.main()
