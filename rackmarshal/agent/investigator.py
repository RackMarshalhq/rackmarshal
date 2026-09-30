"""Read-only RackMarshal Investigator policy and tool plan."""
from rackmarshal.mcp.tools import TOOL_NAMES
ALLOWED_TOOLS=frozenset(TOOL_NAMES)
SYSTEM_INSTRUCTIONS="""You are the RackMarshal Investigator. Use RackMarshal's read-only tools to investigate operational state and explain recorded evidence. Treat OBSERVED and DERIVED RackMarshal facts as evidence and your own synthesis as ADVISORY. Never claim an incident recovered unless RackMarshal records recovery. Never invent severity, causes, events, or evidence. State when evidence is UNKNOWN or insufficient. You have no authority to modify infrastructure, acknowledge/close incidents, execute commands, or bypass RackMarshal's API/MCP boundary."""

def investigation_plan(question_kind):
 plans={
  "current_failures":("get_status","list_incidents"),
  "incident":("get_incident_timeline","get_incident_evidence_bundle","get_recent_changes"),
  "recovery":("get_recovery_history","get_incident_timeline","get_incident_evidence_bundle"),
  "overnight":("get_recent_changes","list_incidents","get_recovery_history"),
  "backups":("get_backup_status","list_incidents"),
  "domain":("get_domain_status","list_incidents","get_recent_changes"),
  "health":("get_health",),
 }
 return plans.get(question_kind,("get_status",))
