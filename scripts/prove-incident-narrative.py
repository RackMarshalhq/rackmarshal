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

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
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
    assert get("/", True) == dashboard
    links = Links()
    links.feed(dashboard)
    expected = {"/incidents/" + item["id"] for item in opened + recovered[:20]}
    assert set(x for x in links.links if x.startswith("/incidents/")) == expected
    assert "historical lifecycle records" in dashboard
    assert "not a live probe" in dashboard
    assert not {"script", "form", "button", "input"} & set(links.tags)
    assert "payload_json" not in dashboard

    selected = [
        next(item for item in opened if item["domain"] == "BACKUP"),
        next(item for item in recovered if item["domain"] == "BACKUP"),
        next(item for item in incidents if item["domain"] == "PVE"),
        next(item for item in opened if item["domain"] == "MOUNT"),
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
              "representative_incidents": verified}
    Path(args.output).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
