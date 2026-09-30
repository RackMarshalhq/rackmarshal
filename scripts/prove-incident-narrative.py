#!/usr/bin/env python3
"""Read-only HTTP acceptance proof. Stores metadata, never raw ledger evidence."""
import argparse
import html
import json
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.tags = []
        self.coverage = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        if tag == "tr" and "data-domain" in dict(attrs):
            self.coverage.append(dict(attrs))
        if tag == "a":
            self.links.append(dict(attrs).get("href", ""))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    checks = 0

    def get(path, markup=False):
        nonlocal checks
        with urlopen(base + path, timeout=15) as response:
            assert response.status == 200, path
            body = response.read().decode()
            if markup:
                assert response.headers["Cache-Control"] == "no-store"
                assert response.headers["X-Content-Type-Options"] == "nosniff"
                assert response.headers["Content-Security-Policy"] == "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'"
                assert response.headers["Content-Type"].startswith("text/html")
            checks += 1
            return body if markup else json.loads(body)["data"]

    incidents = []
    cursor = None
    while True:
        path = "/v1/incidents?limit=200"
        if cursor:
            path += "&cursor=" + quote(cursor, safe="")
        with urlopen(base + path, timeout=15) as response:
            payload = json.load(response)
        checks += 1
        incidents.extend(payload["data"])
        cursor = payload["meta"].get("next_cursor")
        if not cursor:
            break
    opened = [item for item in incidents if item["state"] == "OPEN"]
    recovered = sorted((item for item in incidents if item["state"] == "RECOVERED" and item["recovered_at"]),
                       key=lambda item: (item["recovered_at"], item["id"]), reverse=True)
    dashboard = get("/incidents", True)
    root_page = get("/", True)
    assert "Observation freshness and recorded cycle results" in root_page
    links = Links()
    links.feed(dashboard)
    expected = {"/incidents/" + item["id"] for item in opened + recovered[:20]}
    assert set(x for x in links.links if x.startswith("/incidents/")) == expected
    assert "historical lifecycle records" in dashboard
    assert "not a live probe" in dashboard
    assert not {"script", "form", "button", "input"} & set(links.tags)
    assert "payload_json" not in dashboard

    domains = get("/v1/domains")
    with urlopen(base + "/status", timeout=15) as response:
        stored_cycles = json.load(response)["self_watch"]["cycle_health"]
    checks += 1
    coverage = {row["data-domain"]: row for row in links.coverage}
    assert len(coverage) == 6
    for domain in domains:
        code = domain["domain"]
        row = coverage[code]
        observation = domain.get("last_observation") or {}
        assert row["data-observation-id"] == (code + ":" + str(observation["id"]) if observation else "")
        assert row["data-freshness"] == (domain.get("freshness") or {}).get("state", "UNKNOWN")
        unit = "rackmarshal-domain@" + code.lower() + ".service"
        assert row["data-cycle-state"] == stored_cycles.get(unit, {}).get("health_state", "NOT_RECORDED")
        if observation:
            ref = "observation:" + code + ":" + str(observation["id"])
            assert "/v1/evidence/" + ref in links.links
            assert get("/v1/evidence/" + ref)["id"] == ref
    assert "absent current-unit results are not inferred from older unit names" in dashboard

    selected = [
        next(item for item in opened if item["domain"] == "BACKUP"),
        next(item for item in recovered if item["domain"] == "BACKUP"),
        next(item for item in incidents if item["domain"] == "PVE"),
        next(item for item in incidents if item["domain"] == "MOUNT"),
    ]
    verified = []
    for item in selected:
        iid = item["id"]
        page = get("/incidents/" + iid, True)
        summary = get("/v1/incidents/" + iid + "/summary")
        timeline = get("/v1/incidents/" + iid + "/timeline")
        bundle = get("/v1/incidents/" + iid + "/evidence-bundle")
        for field in ("opened_at", "last_abnormal_at", "recovered_at", "occurrence_count"):
            assert summary[field] == item[field], (iid, field)
            if item[field] is not None:
                assert html.escape(str(item[field]), quote=True) in page
        assert summary["authority"] == "DERIVED"
        assert summary["state"] == item["state"]
        assert summary["provenance"]["linkage_mode"] == timeline["provenance"]["linkage_mode"]
        if item["state"] == "OPEN":
            assert summary["recovery_statement"] == "No recovery is recorded."
            assert "No recovery is recorded." in page
        else:
            assert "Recovery recorded. Historical incident." in page
            assert bundle["recovery_evidence"]["observation"]
        assert "Historical recovery does not establish current health" in page
        assert "does not establish root cause" in page
        assert "payload_json" not in page
        parsed = Links()
        parsed.feed(page)
        assert [row["data-domain"] for row in parsed.coverage] == [item["domain"]]
        assert not {"script", "form", "button", "input"} & set(parsed.tags)
        for ref in summary["evidence_refs"]:
            path = "/v1/evidence/" + quote(ref, safe=":")
            assert path in parsed.links
            evidence = get(path)
            assert evidence["id"] == ref
        for suffix in ("summary", "timeline", "evidence-bundle"):
            assert "/v1/incidents/" + iid + "/" + suffix in parsed.links
        verified.append({"incident_id": iid, "state": item["state"],
                         "linkage_mode": summary["provenance"]["linkage_mode"],
                         "evidence_link_count": len(summary["evidence_refs"])})
    result = {"checked_at": datetime.now(timezone.utc).isoformat(),
              "base_url": base, "result": "PASS", "http_checks": checks,
              "open_incident_count": len(opened), "recent_recoveries_shown": min(20, len(recovered)),
              "open_by_domain": {domain: sum(item["domain"] == domain for item in opened)
                                 for domain in sorted({item["domain"] for item in incidents})},
              "representative_incidents": verified,
              "collection_coverage": [{"domain": domain, "observation_id": row["data-observation-id"], "freshness": row["data-freshness"], "cycle_state": row["data-cycle-state"]} for domain, row in sorted(coverage.items())]}
    Path(args.output).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
