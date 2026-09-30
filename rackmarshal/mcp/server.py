"""RackMarshal MCP v1 server. Requires the optional `mcp` Python package."""
from rackmarshal.api.status import connect_db, build_status
from rackmarshal.mcp.tools import RackMarshalTools

def create_server():
 try: from mcp.server.fastmcp import FastMCP
 except ImportError as exc: raise RuntimeError("RackMarshal MCP requires optional dependency: pip install 'rackmarshal[mcp]'") from exc
 api=RackMarshalTools(connect_db,build_status); mcp=FastMCP("RackMarshal")
 annotations={"readOnlyHint":True,"destructiveHint":False,"openWorldHint":False}
 def reg(name,title,description,fn): mcp.tool(name=name,title=title,description=description,annotations=annotations)(fn)
 reg("get_health","Check RackMarshal health","Use when the user asks whether RackMarshal itself and its operational database are reachable and readable.",api.get_health)
 reg("get_status","Get infrastructure status","Use for an overall operational summary: current domain states and open incident count. This reports RackMarshal's deterministic recorded state, not an AI assessment.",api.get_status)
 reg("list_incidents","Find incidents","Use when the user wants current or historical failures/problems, optionally narrowed by domain, state, or resource. Returns stable incident IDs for follow-up investigation.",api.list_incidents)
 reg("get_incident","Investigate an incident","Use after an incident ID is known and the user wants its lifecycle, affected resource, recorded changes, and evidence references.",api.get_incident)
 reg("get_recent_changes","Review recent changes","Use when the user asks what changed, especially before or around a failure. Optionally narrow by domain/resource or a UTC since-time.",api.get_recent_changes)
 reg("get_domain_status","Check one operational domain","Use when the user asks about one RackMarshal domain such as ZFS, backups, Proxmox, Home Assistant, hardware, or mounts.",api.get_domain_status)
 reg("get_backup_status","Check backup status","Use when the user asks whether backups are healthy or wants the current deterministic BACKUP domain summary.",api.get_backup_status)
 reg("get_evidence","Inspect recorded evidence","Use when an evidence reference from another RackMarshal result is known and the user needs the underlying sanitized recorded evidence.",api.get_evidence)
 reg("get_recovery_history","Review recovery history","Use when the user asks what recovered, when recovery was independently observed, or wants historical recoveries, optionally by domain or since-time.",api.get_recovery_history)
 return mcp

def main(): create_server().run(transport="streamable-http")
if __name__=="__main__": main()
