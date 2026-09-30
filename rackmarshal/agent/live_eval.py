"""Live Investigator v1.1 production-MCP acceptance runner."""
import argparse, asyncio, json, sys
from pathlib import Path

EXPECTED_TOOLS={
 "get_health","get_status","list_incidents","get_incident","get_recent_changes",
 "get_domain_status","get_backup_status","get_evidence","get_recovery_history",
 "get_incident_timeline","get_incident_evidence_bundle",
}

def _path_get(obj,path):
    cur=obj
    for part in path.split("."):
        cur=cur[int(part)] if isinstance(cur,list) else cur[part]
    return cur

def _resolve(value,results):
    if isinstance(value,str) and value.startswith("$result."):
        _,idx,path=value.split(".",2)
        return _path_get(results[int(idx)],path)
    if isinstance(value,dict):
        return {k:_resolve(v,results) for k,v in value.items()}
    if isinstance(value,list):
        return [_resolve(v,results) for v in value]
    return value

def _contains_raw_payload(obj):
    return "payload_json" in json.dumps(obj,sort_keys=True)
def _timeline_and_bundle(results):
    timeline=next((r["data"] for r in results if isinstance(r,dict) and isinstance(r.get("data"),dict) and "items" in r["data"] and "incident_id" in r["data"]),None)
    bundle=next((r["data"] for r in results if isinstance(r,dict) and isinstance(r.get("data"),dict) and "timeline" in r["data"] and "material_changes" in r["data"]),None)
    return timeline,bundle

def assert_case(name,results,assertions):
    failures=[]
    timeline,bundle=_timeline_and_bundle(results)
    for a in assertions:
        try:
            if a=="health_ok":
                assert results[0]["data"]["status"]=="OK" and results[0]["data"]["database_readable"] is True
            elif a=="status_open_count_matches":
                assert results[0]["data"]["open_incident_count"]==len(results[1]["data"])
                assert all(x["state"]=="OPEN" for x in results[1]["data"])
            elif a=="backup_open_incidents_consistent":
                assert results[0]["data"]["open_incidents"]==len(results[1]["data"])
                assert all(x["domain"]=="BACKUP" and x["state"]=="OPEN" for x in results[1]["data"])
            elif a=="discovered_open_incident":
                assert results[0]["data"] and results[0]["data"][0]["state"]=="OPEN"
            elif a=="open_no_recovery":
                assert timeline and timeline["state"]=="OPEN"
                assert all(x["kind"]!="INCIDENT_RECOVERED" for x in timeline["items"])
                assert bundle is None or bundle["recovery_evidence"] is None
            elif a=="recovered_proven":
                assert timeline and timeline["state"]=="RECOVERED"
                assert any(x["kind"]=="INCIDENT_RECOVERED" for x in timeline["items"])
                assert bundle and bundle["recovery_evidence"] is not None
            elif a=="direct_linkage":
                target=bundle or timeline; assert target["provenance"]["linkage_mode"]=="DIRECT_EVENT_IDS"
            elif a=="legacy_linkage":
                target=bundle or timeline; assert target["provenance"]["linkage_mode"]=="LEGACY_RESOURCE_TIME_CORRELATION"
            elif a=="sanitized":
                assert not any(_contains_raw_payload(r) for r in results)
            elif a=="bounded_bundle":
                assert bundle and len(bundle["material_changes"])<=50
            elif a=="material_compacted":
                assert bundle and len(bundle["material_changes"])<=5
            elif a=="has_material_change":
                assert timeline and any(x["kind"]=="MATERIAL_CHANGE" for x in timeline["items"])
            elif a=="changes_compacted":
                meta=results[0]["meta"]; assert meta["collapsed_event_count"]>0
                assert meta["material_change_count"]<meta["raw_event_count"]
            elif a=="contains_backup_33":
                assert any(x["incident_id"]=="BACKUP:33" for x in results[0]["data"])
            elif a=="domain_pve":
                assert results[0]["data"]["domain"]=="PVE" and results[0]["data"]["authority"]=="DERIVED"
            elif a=="evidence_roundtrip":
                ref=results[0]["data"]["opening_evidence"]["observation"]["id"]
                assert results[1]["data"]["id"]==ref
            elif a=="same_data":
                assert results[0]["data"]==results[1]["data"]
            else:
                failures.append(f"unknown assertion {a}")
        except (AssertionError,KeyError,TypeError,IndexError) as exc:
            failures.append(f"{a}: {exc or 'assertion failed'}")
    return failures
async def run_suite(path,server=None):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    suite=json.loads(Path(path).read_text())
    server=server or suite["server"]
    report={"version":suite["version"],"server":server,"cases":[],"failures":[]}
    async with streamable_http_client(server) as (read,write,*_):
        async with ClientSession(read,write) as session:
            await session.initialize()
            tools=(await session.list_tools()).tools
            names={t.name for t in tools}
            if names!=EXPECTED_TOOLS:
                report["failures"].append({"surface":{"missing":sorted(EXPECTED_TOOLS-names),"extra":sorted(names-EXPECTED_TOOLS)}})
            for tool in tools:
                ann=tool.annotations
                if not (ann and ann.readOnlyHint is True and ann.destructiveHint is False and ann.openWorldHint is False):
                    report["failures"].append({"annotations":tool.name})
            for case in suite["cases"]:
                results=[]; calls=[]; call_error=None
                for name,args in case["calls"]:
                    resolved=_resolve(args,results)
                    res=await session.call_tool(name,resolved)
                    calls.append({"tool":name,"args":resolved,"is_error":bool(res.isError)})
                    if res.isError:
                        call_error=res.content[0].text if res.content else "tool error"
                        break
                    results.append(json.loads(res.content[0].text))
                expected_error=bool(case.get("expect_error"))
                if expected_error:
                    passed=call_error is not None
                    failures=[] if passed else ["expected tool error but call succeeded"]
                else:
                    failures=[]
                    if call_error is not None: failures.append(call_error)
                    else: failures=assert_case(case["id"],results,case.get("assertions",[]))
                    passed=not failures
                item={"id":case["id"],"goal":case["goal"],"pass":passed,"calls":calls,"failures":failures}
                report["cases"].append(item)
                if not passed: report["failures"].append({case["id"]:failures})
    report["passed"]=not report["failures"]
    report["case_count"]=len(report["cases"])
    report["passed_count"]=sum(1 for c in report["cases"] if c["pass"])
    return report

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--suite",default="evals/investigator_v1_1_live.json")
    p.add_argument("--server")
    p.add_argument("--json-out")
    args=p.parse_args(argv)
    report=asyncio.run(run_suite(args.suite,args.server))
    text=json.dumps(report,indent=2)
    if args.json_out: Path(args.json_out).write_text(text+"\n")
    print(f"Investigator live eval: {report['passed_count']}/{report['case_count']} cases passed")
    for c in report["cases"]:
        print(("PASS" if c["pass"] else "FAIL"),c["id"])
        if c["failures"]: print(" ",c["failures"])
    if report["failures"]: print("FAILURES",json.dumps(report["failures"],indent=2))
    return 0 if report["passed"] else 1

if __name__=="__main__":
    raise SystemExit(main())
