"""RackMarshal read-only API v1 adapters and query service."""
import base64, json, sqlite3
from datetime import datetime, timezone

DOMAINS = ("PVE", "ZFS", "BACKUP", "HA", "HARDWARE", "MOUNT")
INCIDENT_TABLES = {"PVE":"resource_incidents","ZFS":"zfs_incidents","BACKUP":"backup_incidents","HA":"ha_incidents","HARDWARE":"hardware_incidents","MOUNT":"mount_incidents"}
EVENT_TABLES = {"PVE":"resource_events","ZFS":"zfs_events","BACKUP":"backup_events","HA":"ha_events","HARDWARE":"hardware_events","MOUNT":"mount_events"}
OBS_TABLES = {"PVE":"observations","ZFS":"zfs_observations","BACKUP":"observations","HA":"observations","HARDWARE":"hardware_observations","MOUNT":"mount_observations"}
COLLECTORS = {"PVE":"pve_cluster_resources","BACKUP":"backup_domain","HA":"home_assistant"}

def now(): return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
def envelope(data, **meta): return {"api_version":"v1","generated_at":now(),"data":data,"meta":meta}
def error(code, message, status=400): return status,{"api_version":"v1","generated_at":now(),"error":{"code":code,"message":message}}
def canon(domain, local_id): return f"{domain}:{int(local_id)}"
def evidence(kind, domain, local_id): return f"{kind}:{domain}:{int(local_id)}"
def _domain(value):
    d=(value or "").upper()
    if d not in DOMAINS: raise ValueError("DOMAIN_NOT_FOUND")
    return d

def parse_id(value):
    try:
        d,n=value.split(":",1); d=_domain(d); n=int(n)
        if n < 1: raise ValueError
        return d,n
    except Exception as exc:
        raise ValueError("INVALID_ID") from exc

def _table_columns(conn, table): return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
def _json(value):
    if value is None: return None
    try: return json.loads(value)
    except (TypeError,json.JSONDecodeError): return value

def normalize_incident(domain, row):
    x=dict(row); lid=x["id"]
    resource_key=x.get("resource_key") or x.get("serial") or x.get("mount_id")
    display=x.get("display_name") or x.get("pool_name") or resource_key
    return {"id":canon(domain,lid),"local_id":lid,"domain":domain,"resource_type":x.get("resource_type") or ("hardware_device" if domain=="HARDWARE" else "mount" if domain=="MOUNT" else None),"resource_key":resource_key,"display_name":display,"incident_type":x.get("incident_type"),"state":x.get("incident_state"),"severity":x.get("severity"),"baseline_state":x.get("baseline_state"),"opened_at":x.get("opened_at"),"last_abnormal_at":x.get("last_abnormal_at"),"recovered_at":x.get("recovered_at"),"occurrence_count":x.get("occurrence_count"),"authority":"DERIVED","evidence_refs":[evidence("observation",domain,x[k]) for k in ("opened_observation_id","last_abnormal_observation_id","recovered_observation_id") if x.get(k) is not None],"opening_changes":_json(x.get("opening_changes_json")),"latest_changes":_json(x.get("latest_changes_json"))}

def list_incidents(conn, params):
    domains=[_domain(params["domain"])] if params.get("domain") else list(DOMAINS); items=[]
    for d in domains:
        table=INCIDENT_TABLES[d]; cols=_table_columns(conn,table)
        where=[]; vals=[]
        mapping={"state":"incident_state","resource_type":"resource_type","resource_key":"resource_key"}
        for q,c in mapping.items():
            if params.get(q) and c in cols: where.append(f"{c}=?"); vals.append(params[q].upper() if q=="state" else params[q])
        if params.get("opened_after"): where.append("opened_at>=?"); vals.append(params["opened_after"])
        if params.get("opened_before"): where.append("opened_at<?"); vals.append(params["opened_before"])
        sql=f"SELECT * FROM {table}"+(" WHERE "+" AND ".join(where) if where else "")+" ORDER BY opened_at DESC,id DESC"
        items += [normalize_incident(d,r) for r in conn.execute(sql,vals).fetchall()]
    items.sort(key=lambda x:(x.get("opened_at") or "",x["id"]),reverse=True)
    return paginate(items,params)

def get_incident(conn, incident_id):
    d,lid=parse_id(incident_id); row=conn.execute(f"SELECT * FROM {INCIDENT_TABLES[d]} WHERE id=?",(lid,)).fetchone()
    return normalize_incident(d,row) if row else None
def _cursor(offset): return base64.urlsafe_b64encode(str(offset).encode()).decode().rstrip("=")
def _offset(cursor):
    if not cursor: return 0
    try: return int(base64.urlsafe_b64decode(cursor+"="*(-len(cursor)%4)).decode())
    except Exception as exc: raise ValueError("INVALID_CURSOR") from exc

def paginate(items, params):
    try: limit=int(params.get("limit",50))
    except ValueError as exc: raise ValueError("INVALID_LIMIT") from exc
    if limit<1 or limit>200: raise ValueError("INVALID_LIMIT")
    off=_offset(params.get("cursor")); page=items[off:off+limit]
    return page,{"limit":limit,"next_cursor":_cursor(off+limit) if off+limit<len(items) else None,"total":len(items)}

def normalize_event(domain,row):
    x=dict(row); lid=x["id"]; oid=x.get("observation_id")
    return {"id":canon(domain,lid),"local_id":lid,"domain":domain,"observation_id":canon(domain,oid) if oid else None,"resource_type":x.get("resource_type") or ("hardware_device" if domain=="HARDWARE" else "mount" if domain=="MOUNT" else None),"resource_key":x.get("resource_key") or x.get("serial") or x.get("mount_id"),"event_type":x.get("event_type") or x.get("outcome"),"baseline_state":x.get("baseline_state"),"observed_at":x.get("observed_at") or x.get("detected_at"),"changes":_json(x.get("changes_json")),"authority":"DERIVED","evidence_refs":[evidence("observation",domain,oid)] if oid else []}

def query_events(conn,params):
    domains=[_domain(params["domain"])] if params.get("domain") else list(DOMAINS); out=[]
    for d in domains:
        table=EVENT_TABLES[d]; cols=_table_columns(conn,table); where=[]; vals=[]
        for q,c in (("resource_type","resource_type"),("resource_key","resource_key")):
            if params.get(q) and c in cols: where.append(f"{c}=?"); vals.append(params[q])
        tcol="observed_at" if "observed_at" in cols else "detected_at"
        if params.get("observed_after"): where.append(f"{tcol}>=?"); vals.append(params["observed_after"])
        if params.get("observed_before"): where.append(f"{tcol}<?"); vals.append(params["observed_before"])
        sql=f"SELECT * FROM {table}"+(" WHERE "+" AND ".join(where) if where else "")+f" ORDER BY {tcol} DESC,id DESC"
        out += [normalize_event(d,r) for r in conn.execute(sql,vals)]
    out.sort(key=lambda x:(x.get("observed_at") or "",x["id"]),reverse=True)
    return out

def list_events(conn,params):
    return paginate(query_events(conn,params),params)

def _change_signature(item):
    fields=[]
    for change in item.get("changes") or []:
        if isinstance(change,dict): fields.append((change.get("field"),json.dumps(change.get("expected"),sort_keys=True,default=str)))
        else: fields.append((None,json.dumps(change,sort_keys=True,default=str)))
    return (item.get("domain"),item.get("resource_type"),item.get("resource_key"),item.get("event_type"),item.get("baseline_state"),tuple(fields))

def material_changes(conn,params):
    raw=query_events(conn,params)
    # Collapse repeated polling per resource while preserving genuine transitions for that resource.
    runs=[]; current={}
    for item in reversed(raw):
        sig=_change_signature(item)
        resource=(item.get("domain"),item.get("resource_type"),item.get("resource_key"))
        run=current.get(resource)
        if run is not None and run["_signature"]==sig:
            run["last_observed_at"]=item.get("observed_at"); run["latest_event_id"]=item.get("id"); run["latest_changes"]=item.get("changes"); run["repeat_count"]+=1
            run["latest_evidence_refs"]=item.get("evidence_refs") or []
        else:
            run={"_signature":sig,"domain":item.get("domain"),"resource_type":item.get("resource_type"),"resource_key":item.get("resource_key"),"event_type":item.get("event_type"),"baseline_state":item.get("baseline_state"),"first_observed_at":item.get("observed_at"),"last_observed_at":item.get("observed_at"),"first_event_id":item.get("id"),"latest_event_id":item.get("id"),"first_changes":item.get("changes"),"latest_changes":item.get("changes"),"repeat_count":1,"first_evidence_refs":item.get("evidence_refs") or [],"latest_evidence_refs":item.get("evidence_refs") or [],"authority":"DERIVED"}
            runs.append(run); current[resource]=run
    for run in runs: run.pop("_signature",None)
    runs.sort(key=lambda x:(x.get("last_observed_at") or "",x.get("latest_event_id") or ""),reverse=True)
    items,meta=paginate(runs,params)
    meta["raw_event_count"]=len(raw); meta["material_change_count"]=len(runs); meta["collapsed_event_count"]=len(raw)-len(runs)
    return items,meta

def normalize_observation(domain,row):
    x=dict(row); lid=x["id"]
    return {"id":canon(domain,lid),"local_id":lid,"domain":domain,"collector":x.get("collector") or {"ZFS":"zfs","HARDWARE":"hardware_temperature","MOUNT":"mount_catalog"}.get(domain),"observed_at":x.get("observed_at"),"recorded_at":x.get("recorded_at"),"source":x.get("source") or x.get("host"),"schema_version":x.get("schema_version"),"authority":"OBSERVED","evidence_ref":evidence("observation",domain,lid)}

def list_observations(conn,params):
    domains=[_domain(params["domain"])] if params.get("domain") else list(DOMAINS); out=[]
    for d in domains:
        table=OBS_TABLES[d]; cols=_table_columns(conn,table); where=[]; vals=[]
        if d in COLLECTORS: where.append("collector=?"); vals.append(COLLECTORS[d])
        if params.get("collector") and "collector" in cols: where.append("collector=?"); vals.append(params["collector"])
        if params.get("observed_after"): where.append("observed_at>=?"); vals.append(params["observed_after"])
        if params.get("observed_before"): where.append("observed_at<?"); vals.append(params["observed_before"])
        sql=f"SELECT * FROM {table}"+(" WHERE "+" AND ".join(where) if where else "")+" ORDER BY observed_at DESC,id DESC"
        out += [normalize_observation(d,r) for r in conn.execute(sql,vals)]
    out.sort(key=lambda x:(x.get("observed_at") or "",x["id"]),reverse=True)
    return paginate(out,params)
def recoveries(conn,params):
    p=dict(params); p["state"]="RECOVERED"; items,meta=list_incidents(conn,p)
    items=[{"incident_id":x["id"],"domain":x["domain"],"resource_type":x["resource_type"],"resource_key":x["resource_key"],"recovered_at":x["recovered_at"],"authority":"DERIVED","evidence_refs":[r for r in x["evidence_refs"] if r.startswith("observation:")][-1:]} for x in items]
    after=params.get("recovered_after"); before=params.get("recovered_before")
    if after: items=[x for x in items if x["recovered_at"] and x["recovered_at"]>=after]
    if before: items=[x for x in items if x["recovered_at"] and x["recovered_at"]<before]
    return items,meta

def get_evidence(conn,ref):
    try: kind,d,lid=ref.split(":",2); d=_domain(d); lid=int(lid)
    except Exception as exc: raise ValueError("INVALID_ID") from exc
    if kind=="incident": return get_incident(conn,f"{d}:{lid}")
    table=(OBS_TABLES if kind=="observation" else EVENT_TABLES if kind=="event" else {}).get(d)
    if not table: raise ValueError("INVALID_ID")
    row=conn.execute(f"SELECT * FROM {table} WHERE id=?",(lid,)).fetchone()
    if not row: return None
    item=normalize_observation(d,row) if kind=="observation" else normalize_event(d,row)
    # Deliberately no payload_json: public evidence is sanitized metadata/structured ledger evidence.
    return {"id":ref,"kind":kind,"domain":d,"authority":item.get("authority"),"content":item}

def route(conn,path,params,status_builder=None):
    try:
        if path=="/v1/health":
            conn.execute("SELECT 1").fetchone(); return 200,envelope({"status":"OK","database_readable":True,"api_version":"v1"})
        if path=="/v1/status":
            if not status_builder: return error("SERVICE_UNAVAILABLE","status builder unavailable",503)
            s=status_builder(); data={"overall_status":s["overall_status"],"domains":[{"domain":d,"status":v["status"],"open_incident_count":v["open_incidents"],"last_observation":v["last_observation"],"authority":"DERIVED"} for d,v in s["domains"].items()],"open_incident_count":s["open_incident_count"],"generated_from":"rackmarshal-ledgers"}; return 200,envelope(data)
        if path=="/v1/domains" or path.startswith("/v1/domains/"):
            if not status_builder: return error("SERVICE_UNAVAILABLE","status builder unavailable",503)
            s=status_builder(); domains=[{"domain":d,"status":v["status"],"last_observation":v["last_observation"],"freshness":s.get("self_watch",{}).get("freshness",{}).get(d),"open_incident_count":v["open_incidents"],"authority":"DERIVED"} for d,v in s["domains"].items()]
            if path!="/v1/domains":
                d=_domain(path.rsplit("/",1)[1]); item=next((x for x in domains if x["domain"]==d),None); return (200,envelope(item)) if item else error("DOMAIN_NOT_FOUND","unknown domain",404)
            return 200,envelope(domains)
        if path=="/v1/incidents": items,meta=list_incidents(conn,params); return 200,envelope(items,**meta)
        if path.startswith("/v1/incidents/"):
            item=get_incident(conn,path.rsplit("/",1)[1]); return (200,envelope(item)) if item else error("INCIDENT_NOT_FOUND","incident not found",404)
        if path=="/v1/observations": items,meta=list_observations(conn,params); return 200,envelope(items,**meta)
        if path=="/v1/events": items,meta=list_events(conn,params); return 200,envelope(items,**meta)
        if path=="/v1/changes": items,meta=material_changes(conn,params); return 200,envelope(items,**meta)
        if path=="/v1/recoveries": items,meta=recoveries(conn,params); return 200,envelope(items,**meta)
        if path.startswith("/v1/evidence/"):
            item=get_evidence(conn,path[len("/v1/evidence/"):]); return (200,envelope(item)) if item else error("EVIDENCE_NOT_FOUND","evidence not found",404)
        if path=="/v1/backups/status":
            if not status_builder: return error("SERVICE_UNAVAILABLE","status builder unavailable",503)
            s=status_builder(); return 200,envelope(s["domains"]["BACKUP"])
        return error("NOT_FOUND","endpoint not found",404)
    except ValueError as exc:
        code=str(exc); return error(code,code.replace("_"," ").lower(),404 if code=="DOMAIN_NOT_FOUND" else 400)
