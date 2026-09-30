"""Goal-oriented read-only RackMarshal MCP v1 tool service."""
from urllib.parse import urlencode
from rackmarshal.api.v1 import route

DOMAINS=("PVE","ZFS","BACKUP","HA","HARDWARE","MOUNT")
V10_TOOL_NAMES=("get_health","get_status","list_incidents","get_incident","get_recent_changes","get_domain_status","get_backup_status","get_evidence","get_recovery_history")
TOOL_NAMES=V10_TOOL_NAMES+("get_incident_timeline","get_incident_evidence_bundle")
V11_CANDIDATE_TOOL_NAMES=TOOL_NAMES

class ToolError(RuntimeError): pass

class RackMarshalTools:
 def __init__(self, conn_factory, status_builder): self.conn_factory=conn_factory; self.status_builder=status_builder
 def _call(self,path,params=None):
  conn=self.conn_factory()
  try: code,payload=route(conn,path,params or {},self.status_builder)
  finally: conn.close()
  if code!=200: raise ToolError(f"{payload['error']['code']}: {payload['error']['message']}")
  return payload
 def get_health(self): return self._call('/v1/health')
 def get_status(self): return self._call('/v1/status')
 def list_incidents(self,domain: str|None=None,state: str|None=None,resource_type: str|None=None,resource_key: str|None=None,limit: int=20,cursor: str|None=None):
  p={k:v for k,v in locals().items() if k not in ('self',) and v is not None}; return self._call('/v1/incidents',p)
 def get_incident(self,incident_id: str): return self._call('/v1/incidents/'+incident_id)
 def get_incident_timeline(self,incident_id: str): return self._call('/v1/incidents/'+incident_id+'/timeline')
 def get_incident_evidence_bundle(self,incident_id: str,limit: int=50): return self._call('/v1/incidents/'+incident_id+'/evidence-bundle',{'limit':limit})
 def get_recent_changes(self,domain: str|None=None,resource_type: str|None=None,resource_key: str|None=None,since: str|None=None,until: str|None=None,limit: int=20,cursor: str|None=None):
  p={'domain':domain,'resource_type':resource_type,'resource_key':resource_key,'observed_after':since,'observed_before':until,'limit':limit,'cursor':cursor}; return self._call('/v1/changes',{k:v for k,v in p.items() if v is not None})
 def get_domain_status(self,domain: str): return self._call('/v1/domains/'+domain)
 def get_backup_status(self): return self._call('/v1/backups/status')
 def get_evidence(self,evidence_ref: str): return self._call('/v1/evidence/'+evidence_ref)
 def get_recovery_history(self,domain: str|None=None,since: str|None=None,limit: int=20,cursor: str|None=None):
  p={'domain':domain,'recovered_after':since,'limit':limit,'cursor':cursor}; return self._call('/v1/recoveries',{k:v for k,v in p.items() if v is not None})
