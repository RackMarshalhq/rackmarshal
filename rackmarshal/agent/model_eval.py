"""Model-in-the-loop Investigator v1.1 evaluator.

Requires a temporary Responses-capable OPENAI_API_KEY and RACKMARSHAL_TUNNEL_ID.
No credentials are persisted by this runner.
"""
import argparse, json, os, re, sys, time, urllib.error
from pathlib import Path
from rackmarshal.agent.openai_client import run, extract_text
from rackmarshal.mcp.tools import TOOL_NAMES

EVIDENCE_RE=re.compile(r"\b(?:observation|event|incident):(PVE|ZFS|BACKUP|HA|HARDWARE|MOUNT):\d+\b")
UNCERTAINTY=("unknown","cannot determine","does not establish","not establish","insufficient evidence","does not record","does not prove","cannot support")

def tool_trace(response):
    return [x.get("name") for x in response.get("output",[]) if x.get("type")=="mcp_call" and x.get("name")]

def score_case(case,response):
    text=extract_text(response)
    lower=text.lower()
    normalized=re.sub(r"[*_`#]", "", lower)
    used=tool_trace(response)
    failures=[]
    required=set(case.get("required_tools",[]))
    missing=required-set(used)
    if missing: failures.append("missing tools: "+",".join(sorted(missing)))
    unknown=set(used)-set(TOOL_NAMES)
    if unknown: failures.append("unknown tools: "+",".join(sorted(unknown)))
    max_calls=case.get("max_tool_calls",6)
    if len(used)>max_calls: failures.append(f"tool calls {len(used)} > {max_calls}")
    for value in case.get("must_contain",[]):
        if value.lower() not in lower: failures.append("missing text: "+value)
    any_values=case.get("must_contain_any",[])
    if any_values and not any(v.lower() in lower for v in any_values):
        failures.append("missing any-of text: "+",".join(any_values))
    for value in case.get("must_not_contain",[]):
        if value.lower() in lower: failures.append("forbidden text: "+value)
    if case.get("evidence_id_required") and not EVIDENCE_RE.search(text):
        failures.append("no typed evidence ID cited")
    if case.get("uncertainty_required") and not any(v in normalized for v in UNCERTAINTY):
        failures.append("unsupported-cause uncertainty not explicit")
    if case.get("separation_required"):
        if "recorded" not in lower or not ("advisory" in lower or "interpretation" in lower):
            failures.append("recorded/advisory separation missing")
    if "sk-" in text: failures.append("possible credential leakage")
    return {"pass":not failures,"failures":failures,"tools":used,"text":text}

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--suite",default="evals/investigator_v1_1_model.json")
    p.add_argument("--model")
    p.add_argument("--tunnel-id",default=os.getenv("RACKMARSHAL_TUNNEL_ID"))
    p.add_argument("--json-out")
    args=p.parse_args(argv)
    key=os.getenv("OPENAI_API_KEY")
    if not key: p.error("OPENAI_API_KEY is required")
    if not args.tunnel_id: p.error("RACKMARSHAL_TUNNEL_ID or --tunnel-id is required")
    suite=json.loads(Path(args.suite).read_text())
    model=args.model or suite.get("model","gpt-6-luna")
    report={"version":suite["version"],"model":model,"cases":[]}
    for case in suite["cases"]:
        try:
            response=None
            for attempt in range(3):
                try:
                    response=run(case["prompt"],key,args.tunnel_id,model=model,timeout=180)
                    break
                except urllib.error.HTTPError as exc:
                    if exc.code != 429 or attempt == 2:
                        raise
                    retry_after=exc.headers.get("Retry-After") if exc.headers else None
                    try:
                        delay=max(15,int(float(retry_after))) if retry_after else 30*(attempt+1)
                    except (TypeError,ValueError):
                        delay=30*(attempt+1)
                    time.sleep(delay)
            scored=score_case(case,response)
            scored.update({"id":case["id"],"response_id":response.get("id"),"usage":response.get("usage")})
        except Exception as exc:
            scored={"id":case["id"],"pass":False,"failures":[f"{type(exc).__name__}: {exc}"],"tools":[],"text":""}
        report["cases"].append(scored)
        print(("PASS" if scored["pass"] else "FAIL"),case["id"],"tools="+",".join(scored["tools"]))
        for f in scored["failures"]: print(" ",f)
    report["passed_count"]=sum(c["pass"] for c in report["cases"])
    report["case_count"]=len(report["cases"])
    report["passed"]=report["passed_count"]==report["case_count"]
    if args.json_out: Path(args.json_out).write_text(json.dumps(report,indent=2)+"\n")
    print(f"Model eval: {report['passed_count']}/{report['case_count']} passed")
    return 0 if report["passed"] else 1

if __name__=="__main__":
    raise SystemExit(main())
