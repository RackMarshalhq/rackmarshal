import unittest

from rackmarshal.domains.backup import secondary_monitor as sm

STORE = "second"
NOW = 1_800_000_000
H = 3600
GIB = 1024**3


def upid(store=STORE, at=NOW - H, kind="verify"):
    return f"UPID:node:0001:0002:00000003:{at:08X}:{kind}:{store}\\x3avm-100:root@pam:"


def packet(**over):
    base = {
        "schema": 1, "store": STORE, "collected_at": NOW, "tls_verified": True,
        "capacity": {"total": 1000 * GIB, "used": 100 * GIB, "avail": 900 * GIB},
        "snapshot_count": 2,
        "latest": {
            "vm/100": {"backup_time": NOW - 2 * H, "verification_state": "ok",
                       "verification_upid": upid()},
        },
    }
    base.update(over)
    return base


def guests(source_time=NOW - 2 * H):
    return [{"vmid": 100, "guest_type": "vm", "latest_snapshot": {"backup_time": source_time}}]


def run(pkt, res=None, store=STORE, now=NOW):
    return sm.secondary_results(pkt, guests() if res is None else res, now, store,
                                sm.load_settings(lambda k: ""))


def changes(results):
    return {r["resource_key"]: [c["field"] for c in r["changes"]] for r in results}


class Settings(unittest.TestCase):
    def test_off_unless_store_named(self):
        self.assertEqual(sm.configured_store(lambda k: ""), "")
        self.assertEqual(sm.configured_store(lambda k: " second "), "second")
        self.assertEqual(sm.configured_store(lambda k: "bad store;rm"), "")

    def test_off_returns_nothing(self):
        self.assertEqual(run(None, store=""), [])
        self.assertEqual(run(packet(), store=""), [])

    def test_bad_values_use_defaults(self):
        s = sm.load_settings(lambda k: "abc" if "SLA" in k else "-5")
        self.assertEqual(s, sm.DEFAULTS)
        s = sm.load_settings(lambda k: "500" if "PERCENT" in k else "")
        self.assertEqual(s["BACKUP_SECONDARY_MAX_UTILIZATION_PERCENT"], 100.0)


class Comparison(unittest.TestCase):
    def test_healthy(self):
        out = run(packet())
        self.assertEqual([r["outcome"] for r in out], ["MATCH", "MATCH"])
        self.assertEqual({r["resource_key"] for r in out},
                         {"pbs-secondary-coverage", "pbs-secondary-capacity"})

    def test_missing_packet_when_configured_is_a_finding(self):
        c = changes(run(None))
        self.assertEqual(c["pbs-secondary-coverage"], ["secondary_metadata"])
        self.assertEqual(c["pbs-secondary-capacity"], ["secondary_capacity"])

    def test_stale_packet_wrong_store_or_no_tls(self):
        for pkt in (packet(collected_at=NOW - 1000), packet(store="other"),
                    packet(tls_verified=False), packet(schema=2), "x"):
            self.assertEqual(changes(run(pkt))["pbs-secondary-coverage"], ["secondary_metadata"])

    def test_collection_error(self):
        c = changes(run({"schema": 1, "store": STORE, "collected_at": NOW, "tls_verified": True,
                         "error": "secondary_metadata_collection_failed"}))
        self.assertEqual(c["pbs-secondary-capacity"], ["secondary_capacity"])

    def test_copy_missing(self):
        c = changes(run(packet(latest={})))
        self.assertEqual(c["pbs-secondary-coverage"], ["secondary_copy:vm/100"])

    def test_copy_stale(self):
        old = NOW - 40 * H
        pkt = packet(latest={"vm/100": {"backup_time": old, "verification_state": "ok",
                                        "verification_upid": upid()}})
        self.assertIn("secondary_age:vm/100", changes(run(pkt, guests(old)))["pbs-secondary-coverage"])

    def test_lag_only_after_grace(self):
        pkt = packet()
        newer_recent = guests(NOW - 1 * H)          # primary newer but within grace
        self.assertEqual(changes(run(pkt, newer_recent))["pbs-secondary-coverage"], [])
        newer_old = guests(NOW - 10 * H)            # copy at -2h is NEWER than this: no lag
        self.assertEqual(changes(run(pkt, newer_old))["pbs-secondary-coverage"], [])
        pkt = packet(latest={"vm/100": {"backup_time": NOW - 20 * H, "verification_state": "ok",
                                        "verification_upid": upid()}})
        out = changes(run(pkt, guests(NOW - 10 * H)))["pbs-secondary-coverage"]
        self.assertIn("secondary_lag:vm/100", out)

    def test_verification_rules(self):
        def one(state, u):
            return changes(run(packet(latest={"vm/100": {
                "backup_time": NOW - 2 * H, "verification_state": state,
                "verification_upid": u}})))["pbs-secondary-coverage"]
        self.assertEqual(one("ok", upid()), [])
        self.assertTrue(one("failed", upid()))
        self.assertTrue(one("ok", None))
        self.assertTrue(one("ok", upid(store="elsewhere")))   # verified a different store
        self.assertTrue(one("ok", upid(kind="backup")))       # not a verify task
        self.assertTrue(one("ok", upid(at=NOW - 40 * H)))     # too old
        self.assertTrue(one("ok", upid(at=NOW + 3600)))       # in the future

    def test_capacity_thresholds(self):
        low = packet(capacity={"total": 1000 * GIB, "used": 960 * GIB, "avail": 40 * GIB})
        self.assertEqual(changes(run(low))["pbs-secondary-capacity"],
                         ["secondary_available", "secondary_utilization"])
        self.assertEqual(changes(run(packet(capacity={"total": 0, "used": 0, "avail": 0})))
                         ["pbs-secondary-capacity"], ["secondary_capacity"])

    def test_thresholds_are_configurable(self):
        low = packet(capacity={"total": 1000 * GIB, "used": 500 * GIB, "avail": 500 * GIB})
        s = sm.load_settings(lambda k: "600" if "MIN_AVAILABLE" in k else "")
        out = sm.secondary_results(low, guests(), NOW, STORE, s)
        self.assertEqual(changes(out)["pbs-secondary-capacity"], ["secondary_available"])

    def test_bad_enrollment(self):
        c = changes(run(packet(), []))
        self.assertEqual(c["pbs-secondary-coverage"], ["primary_enrollment"])
        dup = guests() + guests()
        self.assertIn("primary_enrollment", changes(run(packet(), dup))["pbs-secondary-coverage"])


class Collect(unittest.TestCase):
    def fake(self, status, rows):
        calls = []

        def get(config, endpoint):
            calls.append(endpoint)
            return status if endpoint.endswith("/status") else rows
        return get, calls

    def test_latest_per_guest_and_endpoints(self):
        rows = [
            {"backup-type": "vm", "backup-id": "100", "backup-time": 10,
             "verification": {"state": "ok", "upid": "u1"}},
            {"backup-type": "vm", "backup-id": "100", "backup-time": 20},
            {"backup-type": "host", "backup-id": "x", "backup-time": 5},
        ]
        get, calls = self.fake({"total": 10, "used": 1, "avail": 9}, rows)
        p = sm.collect_secondary(get, {}, STORE, now=NOW)
        self.assertEqual(calls, ["/api2/json/admin/datastore/second/status",
                                 "/api2/json/admin/datastore/second/snapshots"])
        self.assertEqual(p["latest"]["vm/100"]["backup_time"], 20)
        self.assertNotIn("host/x", p["latest"])
        self.assertNotIn("error", p)

    def test_failures_are_isolated_and_leak_nothing(self):
        def boom(config, endpoint):
            raise RuntimeError("HTTP error 403 token=SECRET")
        p = sm.collect_secondary(boom, {}, STORE, now=NOW)
        self.assertEqual(p["error"], "secondary_metadata_collection_failed")
        self.assertEqual(p["http_status"], 403)
        self.assertNotIn("SECRET", repr(p))

    def test_invalid_data_is_an_error(self):
        for status, rows in (
            ({"total": 0, "used": 0, "avail": 0}, []),
            ({"total": 10, "used": 1, "avail": 9},
             [{"backup-type": "vm", "backup-id": "1", "backup-time": 1}] * 2),
            ({"total": 10, "used": 1, "avail": 9},
             [{"backup-type": "vm", "backup-id": "abc", "backup-time": 1}]),
            ({"total": 10, "used": 1, "avail": 9}, "nope"),
        ):
            get, _ = self.fake(status, rows)
            self.assertIn("error", sm.collect_secondary(get, {}, STORE, now=NOW))


if __name__ == "__main__":
    unittest.main()
