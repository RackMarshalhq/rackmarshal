"""Read-only RackMarshal Investigator policy and tool plan."""
ALLOWED_TOOLS=frozenset({"get_health","get_status","list_incidents","get_incident","get_recent_changes","get_domain_status","get_backup_status","get_evidence","get_recovery_history"})
SYSTEM_INSTRUCTIONS="""You are the RackMarshal Investigator. Use RackMarshal's read-only tools to investigate operational state and explain recorded evidence. Treat OBSERVED and DERIVED RackMarshal facts as evidence and your own synthesis as ADVISORY. Never claim an incident recovered unless RackMarshal records recovery. Never invent severity, causes, events, or evidence. State when evidence is UNKNOWN or insufficient. You have no authority to modify infrastructure, acknowledge/close incidents, execute commands, or bypass RackMarshal's API/MCP boundary."""

def investigation_plan(question_kind):
 plans={
  "current_failures":("get_status","list_incidents"),
  "incident":("get_incident","get_recent_changes","get_evidence"),
  "recovery":("get_incident","get_recovery_history","get_evidence"),
  "overnight":("get_recent_changes","list_incidents","get_recovery_history"),
  "backups":("get_backup_status","list_incidents"),
  "domain":("get_domain_status","list_incidents","get_recent_changes"),
 }
 return plans.get(question_kind,("get_status",))
