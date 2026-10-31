import atexit
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_td = tempfile.TemporaryDirectory()
atexit.register(_td.cleanup)
_conf = Path(_td.name) / "c"
_conf.write_text("STATE_DB=%s/x.db\nLOCAL_AI_ENABLED=false\nSTATUS_API_LISTEN_ADDRESS=127.0.0.1\n"
                 "STATUS_API_LISTEN_PORT=9110\nENABLED_DOMAINS=zfs\n" % _td.name)
os.environ["RACKMARSHAL_CONFIG"] = str(_conf)

from rackmarshal.api import status  # noqa: E402
from rackmarshal.selfwatch import incidents  # noqa: E402

NOW = None


class EnabledDomains(unittest.TestCase):
    def test_only_named_domains_in_status_order(self):
        self.assertEqual(status.enabled_status_domains({"ENABLED_DOMAINS": "zfs, PVE"}), ("PVE", "ZFS"))

    def test_empty_means_none_absent_means_all(self):
        self.assertEqual(status.enabled_status_domains({"ENABLED_DOMAINS": ""}), ())
        self.assertEqual(status.enabled_status_domains({"ENABLED_DOMAINS": " , "}), ())
        self.assertEqual(status.enabled_status_domains({}), status.STATUS_DOMAINS)

    def test_unknown_names_are_ignored(self):
        self.assertEqual(status.enabled_status_domains({"ENABLED_DOMAINS": "zfs,bogus"}), ("ZFS",))


class UnitNames(unittest.TestCase):
    def test_real_1_3_unit_names(self):
        names = status.self_watch_unit_names(("PVE", "ZFS"), exists=lambda n: False)
        self.assertEqual(names, ("rackmarshal-status.service",
                                 "rackmarshal-domain@pve.timer", "rackmarshal-domain@pve.service",
                                 "rackmarshal-domain@zfs.timer", "rackmarshal-domain@zfs.service"))

    def test_no_domains_still_watches_the_status_service(self):
        self.assertEqual(status.self_watch_unit_names((), exists=lambda n: False), ("rackmarshal-status.service",))

    def test_self_watch_timer_only_when_installed(self):
        self.assertIn("rackmarshal-self-watch.timer", status.self_watch_unit_names((), exists=lambda n: True))
        self.assertNotIn("rackmarshal-self-watch.timer", status.self_watch_unit_names((), exists=lambda n: False))

    def test_no_pre_1_3_names_are_watched(self):
        names = status.self_watch_unit_names(status.STATUS_DOMAINS, exists=lambda n: True)
        self.assertFalse([n for n in names if "-cycle." in n or "status-api" in n])

    def test_build_uses_active_state_of_each_name(self):
        with mock.patch.object(status, "unit_active_state", side_effect=lambda n: "active"), \
                mock.patch.object(status, "unit_exists", return_value=False):
            self.assertEqual(status.build_self_watch_units(("ZFS",)),
                             {"rackmarshal-status.service": "active", "rackmarshal-domain@zfs.timer": "active",
                              "rackmarshal-domain@zfs.service": "active"})


class Freshness(unittest.TestCase):
    def test_only_requested_domains(self):
        self.assertEqual(set(status.build_freshness({}, domains=("ZFS",))), {"ZFS"})
        self.assertEqual(set(status.build_freshness({}, domains=())), set())

    def test_default_is_still_every_domain(self):
        self.assertEqual(set(status.build_freshness({})), set(status.STATUS_DOMAINS))


class CleanInstallIsQuiet(unittest.TestCase):
    """A healthy install with one domain must not open incidents for domains it never enabled."""

    def test_no_false_incidents(self):
        units = {n: "active" for n in status.self_watch_unit_names(("ZFS",), exists=lambda n: True)}
        fresh = {"ZFS": {"state": "OK"}}
        desired = incidents.evaluate_self_signals(fresh, units, {"failed": 0, "pending_older_than_seconds": 0})
        self.assertEqual(desired, [])

    def test_status_service_down_is_critical(self):
        units = {"rackmarshal-status.service": "inactive"}
        desired = incidents.evaluate_self_signals({}, units, {})
        self.assertEqual([(d["signal_key"], d["severity"]) for d in desired],
                         [("unit:rackmarshal-status.service", "critical")])
        self.assertEqual(status.self_watch_status_from_parts({}, units, {}), "CRITICAL")

    def test_old_status_service_name_is_still_recognised(self):
        units = {"rackmarshal-status-api.service": "failed"}
        self.assertEqual(status.self_watch_status_from_parts({}, units, {}), "CRITICAL")

    def test_domain_timer_down_is_a_warning(self):
        units = {"rackmarshal-status.service": "active", "rackmarshal-domain@zfs.timer": "inactive"}
        desired = incidents.evaluate_self_signals({}, units, {})
        self.assertEqual([(d["signal_key"], d["severity"]) for d in desired],
                         [("unit:rackmarshal-domain@zfs.timer", "warning")])
        self.assertEqual(status.self_watch_status_from_parts({}, units, {}), "DEGRADED")

    def test_missing_data_for_an_enabled_domain_is_reported(self):
        desired = incidents.evaluate_self_signals({"ZFS": {"state": "MISSING"}}, {}, {})
        self.assertEqual(desired[0]["incident_type"], "FRESHNESS_MISSING")


if __name__ == "__main__":
    unittest.main()
