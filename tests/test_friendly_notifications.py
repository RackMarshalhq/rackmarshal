import atexit
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_td = tempfile.TemporaryDirectory()
atexit.register(_td.cleanup)
_conf = Path(_td.name) / "rackmarshal.conf"
_conf.write_text(
    f"STATE_DB={_td.name}/x.db\nLOCAL_AI_ENABLED=false\nNOTIFY_TIMEZONE=UTC\n"
)
os.environ["RACKMARSHAL_CONFIG"] = str(_conf)

from rackmarshal.notifications import delivery  # noqa: E402
from rackmarshal.notifications.friendly import (  # noqa: E402
    TEMPLATES,
    render,
    render_safe,
    settings_from_config,
)

UTC = settings_from_config({"NOTIFY_TIMEZONE": "UTC"})

# Synthetic incidents, one per supported shape (fictional names only).
CASES = {
    "phone": {
        "resource_type": "backup_phone", "resource_key": "alex",
        "display_name": "Phone backup (alex)", "incident_type": "STATUS-CHANGED",
        "expected_status": "phone_age_hours='<= 168.0'", "actual_status": "phone_age_hours=176.4",
        "note": "Observed differences: phone_age_hours: expected '<= 168.0', actual 176.4",
    },
    "timemachine": {
        "resource_type": "backup_timemachine", "resource_key": "alex",
        "incident_type": "STATUS-CHANGED",
        "note": "Observed differences: timemachine_age_hours: expected '<= 72.0', actual 80.1",
    },
    "messages_pull": {
        "resource_type": "backup_messages", "resource_key": "alex:pull",
        "incident_type": "STATUS-CHANGED",
        "note": "Observed differences: messages_pull_age_hours: expected '<= 36.0', actual 60.2",
    },
    "messages_search_failed": {
        "resource_type": "backup_messages", "resource_key": "sam:search",
        "incident_type": "STATUS-CHANGED",
        "note": "Observed differences: messages_search_result: expected 'ok', actual 'failed'",
    },
    "guest_backup": {
        "resource_type": "backup_guest", "resource_key": "100", "display_name": "example-vm",
        "incident_type": "STATUS-CHANGED",
        "note": "Observed differences: verification_state: expected 'ok', actual None",
    },
    "secondary_one": {
        "resource_type": "backup_host_verify", "resource_key": "pbs-secondary-coverage",
        "incident_type": "STATUS-CHANGED",
        "note": "Observed differences: secondary_verification_metadata:vm/201: expected "
        "'ok with target-store reference', actual 'missing_invalid_or_source_reference'",
    },
    "secondary_many": {
        "resource_type": "backup_host_verify", "resource_key": "pbs-secondary-coverage",
        "incident_type": "STATUS-CHANGED",
        "note": "Observed differences: "
        + "; ".join(
            f"secondary_verification_metadata:{g}: expected 'ok with target-store reference', "
            "actual 'missing_invalid_or_source_reference'"
            for g in ("vm/100", "vm/101", "ct/102", "ct/103", "ct/105")
        ),
    },
    "rsync": {
        "resource_type": "backup_rsync_filebackups", "resource_key": "file-backups",
        "incident_type": "STATUS-CHANGED", "actual_status": "status='INCOMPLETE'",
        "note": "Observed differences: status: expected 'OK', actual 'INCOMPLETE'; finished: expected True, actual False",
    },
    "vm_stopped": {
        "resource_type": "qemu", "resource_key": "201", "display_name": "downloads",
        "incident_type": "STATUS-CHANGED", "expected_status": "running", "actual_status": "stopped",
    },
    "vm_unknown": {
        "resource_type": "qemu", "resource_key": "201", "display_name": "downloads",
        "incident_type": "STATUS-CHANGED", "expected_status": "running", "actual_status": "unknown",
    },
    "ct_missing": {
        "resource_type": "lxc", "resource_key": "126", "display_name": "old-test",
        "incident_type": "MISSING", "expected_status": "stopped", "actual_status": None,
    },
    "ct_new": {
        "resource_type": "lxc", "resource_key": "143", "display_name": "new-thing",
        "incident_type": "NEW", "actual_status": "running", "expected_status": None,
    },
    "node": {
        "resource_type": "node", "resource_key": "pve1", "display_name": "pve1",
        "incident_type": "STATUS-CHANGED", "expected_status": "online", "actual_status": "unknown",
    },
    "storage": {
        "resource_type": "storage", "resource_key": "pbs", "display_name": "pbs",
        "incident_type": "STATUS-CHANGED", "expected_status": "available", "actual_status": "unknown",
    },
    "pool_suspended": {
        "resource_type": "zfs_pool", "resource_key": "tank", "display_name": "tank",
        "incident_type": "STATUS-CHANGED", "expected_status": "ONLINE", "actual_status": "SUSPENDED",
        "note": "Opened automatically by ZFS incident processor. Observed differences: state: "
        "expected 'ONLINE', actual 'SUSPENDED'; error_count: expected 0, actual 5",
    },
    "vdev_new": {
        "resource_type": "zfs_vdev", "resource_key": "tank/mirror-0", "display_name": "mirror-0",
        "incident_type": "NEW",
    },
    "pool_missing": {
        "resource_type": "zfs_pool", "resource_key": "tank", "display_name": "tank",
        "incident_type": "MISSING", "expected_status": "ONLINE", "actual_status": None,
    },
    "mount": {
        "resource_type": "mount", "resource_key": "host:pve1:/mnt/files",
        "display_name": "host:pve1:/mnt/files", "incident_type": "MOUNT_MISSING",
        "mountpoint": "/mnt/files", "guest_id": "pve1",
        "detail": {"expected_source": "//192.0.2.10/files"},
    },
    "home_assistant": {
        "resource_type": "ha_core", "resource_key": "home_assistant_core",
        "display_name": "Home Assistant Core", "incident_type": "STATUS-CHANGED",
        "expected_status": "RUNNING", "actual_status": "NOT_RUNNING",
    },
    "self_unit": {
        "resource_type": "rackmarshal_self", "resource_key": "cycle:rackmarshal-domain@zfs.service",
        "incident_type": "CYCLE_FAILED", "severity": "critical",
        "detail": {"unit": "rackmarshal-domain@zfs.service"},
    },
    "self_freshness": {
        "resource_type": "rackmarshal_self", "resource_key": "freshness:MOUNT",
        "incident_type": "FRESHNESS_STALE",
    },
    "self_timer": {
        "resource_type": "rackmarshal_self", "resource_key": "unit:rackmarshal-zfs-cycle.timer",
        "incident_type": "UNIT_INACTIVE",
    },
    "unknown_type": {
        "resource_type": "something_new", "resource_key": "x", "display_name": "widget",
        "incident_type": "STATUS-CHANGED", "expected_status": "green", "actual_status": "red",
    },
}

FORBIDDEN = (
    "None", "null", "STATUS-CHANGED", "_age_hours", "expected '", " 1 minutes", " 1 hours",
    " 1 machines", " 1 days", "(1 machines", "Vm ", "freshness:", ".service", ".timer",
)


def packet(name, notification_type="OPENED"):
    incident = dict(CASES[name])
    incident.setdefault("opened_at", "2026-01-02T03:04:05Z")
    incident.setdefault("occurrence_count", 1)
    p = {
        "schema_version": 1,
        "builder": "incident_notification_packet",
        "source_domain": "TEST",
        "incident_id": 7,
        "notification_type": notification_type,
        "incident": incident,
    }
    if notification_type == "RECOVERED":
        p["recovery"] = {"recovered_at": "2026-01-02T04:05:05Z"}
    return p


class FriendlyRenderTests(unittest.TestCase):
    def test_every_case_renders_without_machine_wording(self):
        for name in CASES:
            for kind in ("OPENED", "RECOVERED"):
                with self.subTest(case=name, kind=kind):
                    title, message = render(packet(name, kind), kind, UTC)
                    self.assertTrue(title and message)
                    for token in FORBIDDEN:
                        self.assertNotIn(token, title + "\n" + message)

    def test_all_registered_types_have_a_case(self):
        covered = {c["resource_type"] for c in CASES.values()}
        self.assertLessEqual(set(TEMPLATES) - {"homelabops_self"}, covered)

    def test_opened_layout(self):
        title, message = render(packet("phone"), "OPENED", UTC)
        self.assertEqual(title, "⚠️ Alex's phone hasn't backed up in 7 days")
        self.assertIn("**What's wrong:**", message)
        self.assertIn("**Does it matter?**", message)
        self.assertIn("**What to do:**", message)
        self.assertIn("RackMarshal TEST #7 · since Fri Jan 2, 3:04 AM", message)

    def test_recovered_layout(self):
        title, message = render(packet("phone", "RECOVERED"), "RECOVERED", UTC)
        self.assertEqual(title, "✅ Back to normal: Alex's phone backup")
        self.assertIn("It lasted about 1 hour.", message)
        self.assertIn("Nothing to do.", message)

    def test_severity_icons(self):
        self.assertTrue(render(packet("pool_suspended"), "OPENED", UTC)[0].startswith("🔴"))
        self.assertTrue(render(packet("ct_new"), "OPENED", UTC)[0].startswith("ℹ️"))
        self.assertTrue(render(packet("self_unit"), "OPENED", UTC)[0].startswith("⚠️"))

    def test_specific_wording(self):
        self.assertIn("has disappeared from Proxmox", render(packet("ct_missing"), "OPENED", UTC)[0])
        self.assertIn("Status of VM downloads (201) can't be read", render(packet("vm_unknown"), "OPENED", UTC)[0])
        self.assertIn("(1 machine)", render(packet("secondary_one"), "OPENED", UTC)[0])
        _, msg = render(packet("secondary_many"), "OPENED", UTC)
        self.assertIn("VM 100, VM 101, container 102 and 2 more", msg)
        self.assertIn("RackMarshal's shared folder data is out of date", render(packet("self_freshness"), "OPENED", UTC)[0])
        self.assertIn("RackMarshal's ZFS storage check isn't scheduled", render(packet("self_timer"), "OPENED", UTC)[0])
        self.assertIn("RackMarshal's ZFS storage check failed to run", render(packet("self_unit"), "OPENED", UTC)[0])
        self.assertIn("rebuild failed", render(packet("messages_search_failed"), "OPENED", UTC)[0])

    def test_settings(self):
        s = settings_from_config({
            "NOTIFY_DISPLAY_NAMES": "alex:Alexandra",
            "NOTIFY_HELP_TEXT": "Call the helpdesk.",
            "NOTIFY_SERVER_NAME": "nas1",
            "NOTIFY_TIMEZONE": "America/New_York",
        })
        title, message = render(packet("phone"), "OPENED", s)
        self.assertIn("Alexandra's phone", title)
        self.assertIn("saved to nas1", message)
        self.assertIn("since Thu Jan 1, 10:04 PM", message)
        self.assertIn("Call the helpdesk.", render(packet("storage"), "OPENED", s)[1])

    def test_defaults(self):
        s = settings_from_config({})
        self.assertEqual(s["style"], "plain")
        self.assertIn("status page", s["help"])
        self.assertEqual(settings_from_config({"NOTIFY_STYLE": "bogus"})["style"], "plain")

    def test_classic_style_keeps_original_text(self):
        s = settings_from_config({"NOTIFY_STYLE": "classic"})
        self.assertEqual(render_safe(packet("phone"), "OPENED", "T", "M", s), ("T", "M"))

    def test_errors_fall_back_to_original_text(self):
        self.assertEqual(render_safe({"incident": None}, "OPENED", "T", "M", UTC), ("T", "M"))
        self.assertEqual(render_safe(packet("phone"), "SOMETHING", "T", "M", UTC), ("T", "M"))


class FriendlyDeliveryTests(unittest.TestCase):
    def _deliver(self, conf_text):
        _conf.write_text(f"STATE_DB={_td.name}/x.db\nLOCAL_AI_ENABLED=false\n" + conf_text)
        con = sqlite3.connect(":memory:")
        con.row_factory = sqlite3.Row
        con.execute(
            "create table incident_notifications(id integer primary key,source_domain text,"
            "incident_id integer,notification_type text,delivery_state text,attempt_count integer default 0,"
            "last_attempt_at text,updated_at text,packet_json text,explanation_json text,"
            "delivered_at text,last_error text)"
        )
        p = packet("vm_stopped")
        p["source_domain"] = "PVE"
        con.execute(
            "insert into incident_notifications(id,source_domain,incident_id,notification_type,"
            "delivery_state,packet_json) values(1,'PVE',7,'OPENED','PENDING',?)",
            (json.dumps(p),),
        )
        con.commit()
        row = con.execute("select * from incident_notifications where id=1").fetchone()
        with mock.patch.dict(os.environ, {"RACKMARSHAL_CONFIG": str(_conf)}), mock.patch.object(
            delivery, "send_ha"
        ) as send:
            result = delivery.deliver_one(con, row, "http://127.0.0.1:1", "t", "unused", "test")
        con.close()
        self.assertEqual(result["result"], "SENT")
        return send.call_args[0][3], send.call_args[0][4]

    def tearDown(self):
        _conf.write_text(f"STATE_DB={_td.name}/x.db\nLOCAL_AI_ENABLED=false\nNOTIFY_TIMEZONE=UTC\n")

    def test_delivery_sends_plain_text_by_default(self):
        title, message = self._deliver("NOTIFY_TIMEZONE=UTC\n")
        self.assertEqual(title, "⚠️ VM downloads (201) is stopped (should be running)")
        self.assertIn("Start it in Proxmox", message)

    def test_delivery_classic_style(self):
        title, message = self._deliver("NOTIFY_STYLE=classic\n")
        self.assertEqual(title, "RackMarshal Incident OPENED [PVE]")
        self.assertIn("Incident opened for downloads.", message)


if __name__ == "__main__":
    unittest.main()
