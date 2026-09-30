"""Investigator v1 evaluation contract helpers."""
import json
from pathlib import Path
from rackmarshal.mcp.tools import TOOL_NAMES

EVAL_PATH=Path(__file__).resolve().parents[2]/"evals"/"investigator_v1.json"

def load_cases(path=EVAL_PATH):
    return json.loads(Path(path).read_text())["cases"]

def validate_case(case):
    errors=[]
    allowed=set(TOOL_NAMES)
    required=set(case.get("required_tools",[]))
    unknown=required-allowed
    if unknown:
        errors.append(f"unknown required tools: {sorted(unknown)}")
    if case.get("must_separate_advisory") and not required:
        errors.append("advisory case has no evidence-producing tools")
    return errors

def validate_trace(case, tool_names):
    used=set(tool_names)
    missing=set(case.get("required_tools",[]))-used
    forbidden=used-set(TOOL_NAMES)
    return {
        "pass": not missing and not forbidden,
        "missing_tools": sorted(missing),
        "forbidden_tools": sorted(forbidden),
    }
