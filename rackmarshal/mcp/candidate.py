"""Isolated RackMarshal MCP v1.1 promotion candidate.

This module is never used by the production rackmarshal-mcp entry point.
"""
from rackmarshal.api.status import connect_db, build_status
from rackmarshal.mcp.tools import RackMarshalTools

ANNOTATIONS={"readOnlyHint":True,"destructiveHint":False,"openWorldHint":False}

def create_candidate_server(host="127.0.0.1",port=18001):
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError("RackMarshal MCP requires optional dependency") from exc
    api=RackMarshalTools(connect_db,build_status)
    mcp=FastMCP("RackMarshal Candidate v1.1",host=host,port=port)
    def reg(name,title,description,fn):
        mcp.tool(name=name,title=title,description=description,annotations=ANNOTATIONS)(fn)
    reg("get_health","Check RackMarshal health","Use when the user asks whether RackMarshal itself and its operational database are reachable and readable.",api.get_health)
    reg("get_status","Get infrastructure status","Use for an overall operational summary: current domain states and open incident count. This reports RackMarshal's deterministic recorded state, not an AI assessment.",api.get_status)
    reg("list_incidents","Find incidents","Use when the user wants current or historical failures/problems, optionally narrowed by domain, state, or resource. Returns stable incident IDs for follow-up investigation.",api.list_incidents)
    reg("get_incident","Investigate an incident","Use after an incident ID is known and the user wants its lifecycle, affected resource, recorded changes, and evidence references.",api.get_incident)
    reg("get_recent_changes","Review recent changes","Use when the user asks what changed, especially before or around a failure. Optionally narrow by domain/resource and an explicit UTC since/until window. Repeated polling observations of the same condition are collapsed into material change runs.",api.get_recent_changes)
    reg("get_domain_status","Check one operational domain","Use when the user asks about one RackMarshal domain such as ZFS, backups, Proxmox, Home Assistant, hardware, or mounts.",api.get_domain_status)
    reg("get_backup_status","Check backup status","Use when the user asks whether backups are healthy or wants the current deterministic BACKUP domain summary.",api.get_backup_status)
    reg("get_evidence","Inspect recorded evidence","Use when an evidence reference from another RackMarshal result is known and the user needs the underlying sanitized recorded evidence.",api.get_evidence)
    reg("get_recovery_history","Review recovery history","Use when the user asks what recovered, when recovery was independently observed, or wants historical recoveries, optionally by domain or since-time.",api.get_recovery_history)
    reg("get_incident_timeline","Review an incident timeline","Use when a canonical RackMarshal incident ID is known and the user needs its ordered lifecycle: opening, material transitions, latest abnormal state, and independently recorded recovery when present. Returns deterministic RackMarshal state; do not infer cause, severity, or recovery.",api.get_incident_timeline)
    reg("get_incident_evidence_bundle","Get an incident evidence bundle","Use when a canonical RackMarshal incident ID is known and the user needs one compact, bounded, sanitized evidence package for investigation. Prefer this over many separate evidence calls when the whole incident context is needed.",api.get_incident_evidence_bundle)
    # FastMCP/Pydantic ignores unknown top-level arguments by default. The v1.1
    # contract explicitly forbids arbitrary inputs, so harden only the candidate
    # tools and expose that strictness in their advertised JSON schemas.
    for name in ("get_incident_timeline","get_incident_evidence_bundle"):
        tool=mcp._tool_manager._tools[name]
        model=tool.fn_metadata.arg_model
        model.model_config["extra"]="forbid"
        model.model_rebuild(force=True)
        tool.parameters=model.model_json_schema()
    return mcp

def main():
    create_candidate_server().run(transport="streamable-http")

if __name__=="__main__":
    main()
