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
    changes=_json(x.get("changes_json"))
    if changes is None and (x.get("expected_status") is not None or x.get("actual_status") is not None):
        changes=[{"field":"status","expected":x.get("expected_status"),"actual":x.get("actual_status")}]
    return {"id":canon(domain,lid),"local_id":lid,"domain":domain,"observation_id":canon(domain,oid) if oid else None,"resource_type":x.get("resource_type") or ("hardware_device" if domain=="HARDWARE" else "mount" if domain=="MOUNT" else None),"resource_key":x.get("resource_key") or x.get("serial") or x.get("mount_id"),"event_type":x.get("event_type") or x.get("outcome"),"baseline_state":x.get("baseline_state"),"observed_at":x.get("observed_at") or x.get("detected_at"),"changes":changes,"authority":"DERIVED","evidence_refs":[evidence("observation",domain,oid)] if oid else []}

def query_events(conn,params):
    domains=[_domain(params["domain"])] if params.get("domain") else list(DOMAINS); out=[]
    for d in domains:
        table=EVENT_TABLES[d]; cols=_table_columns(conn,table); where=[]; vals=[]
        if params.get("resource_type") and "resource_type" in cols:
            where.append("resource_type=?"); vals.append(params["resource_type"])
        if params.get("resource_key"):
            key_col="resource_key" if "resource_key" in cols else "serial" if "serial" in cols else "mount_id" if "mount_id" in cols else None
            if key_col: where.append(f"{key_col}=?"); vals.append(params["resource_key"])
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

def _compact_events(raw):
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
    return runs

def material_changes(conn,params):
    raw=query_events(conn,params)
    runs=_compact_events(raw)
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

def _incident_record(conn, incident_id):
    domain,local_id=parse_id(incident_id)
    row=conn.execute(f"SELECT * FROM {INCIDENT_TABLES[domain]} WHERE id=?",(local_id,)).fetchone()
    return domain,dict(row) if row else None

def _incident_resource(domain,row):
    return (
        row.get("resource_type") or ("hardware_device" if domain=="HARDWARE" else "mount" if domain=="MOUNT" else None),
        row.get("resource_key") or row.get("serial") or row.get("mount_id"),
    )

def _event_by_id(conn,domain,event_id):
    if event_id is None: return None
    row=conn.execute(f"SELECT * FROM {EVENT_TABLES[domain]} WHERE id=?",(event_id,)).fetchone()
    return normalize_event(domain,row) if row else None

def _event_for_observation(conn,domain,resource_key,observation_id):
    if observation_id is None: return None
    table=EVENT_TABLES[domain]; cols=_table_columns(conn,table)
    key_col="resource_key" if "resource_key" in cols else "serial" if "serial" in cols else "mount_id" if "mount_id" in cols else None
    if not key_col: return None
    row=conn.execute(f"SELECT * FROM {table} WHERE observation_id=? AND {key_col}=? ORDER BY id LIMIT 1",(observation_id,resource_key)).fetchone()
    return normalize_event(domain,row) if row else None

def _incident_events(conn,domain,row):
    resource_type,resource_key=_incident_resource(domain,row)
    params={"domain":domain,"resource_type":resource_type,"resource_key":resource_key,"observed_after":row.get("opened_at")}
    events=query_events(conn,params)
    upper=row.get("recovered_at") or row.get("last_abnormal_at")
    if upper:
        events=[e for e in events if not e.get("observed_at") or e["observed_at"]<=upper]
    return events

def _obs_evidence(conn,domain,observation_id):
    return get_evidence(conn,evidence("observation",domain,observation_id)) if observation_id is not None else None

def _event_evidence(conn,domain,event_item):
    return get_evidence(conn,evidence("event",domain,event_item["local_id"])) if event_item else None

def incident_timeline(conn,incident_id):
    domain,row=_incident_record(conn,incident_id)
    if not row: return None
    incident=normalize_incident(domain,row)
    _,resource_key=_incident_resource(domain,row)
    direct="opened_event_id" in row
    linkage_mode="DIRECT_EVENT_IDS" if direct else "LEGACY_RESOURCE_TIME_CORRELATION"
    opened_event=_event_by_id(conn,domain,row.get("opened_event_id")) if direct else _event_for_observation(conn,domain,resource_key,row.get("opened_observation_id"))
    last_event=_event_by_id(conn,domain,row.get("last_event_id")) if direct else _event_for_observation(conn,domain,resource_key,row.get("last_abnormal_observation_id"))
    recovered_event=_event_for_observation(conn,domain,resource_key,row.get("recovered_observation_id"))
    items=[]
    items.append({"kind":"INCIDENT_OPENED","timestamp":row.get("opened_at"),"authority":"DERIVED","event_id":opened_event.get("id") if opened_event else None,"observation_id":canon(domain,row["opened_observation_id"]) if row.get("opened_observation_id") else None,"changes":incident.get("opening_changes") or (opened_event.get("changes") if opened_event else None),"evidence_refs":[r for r in [evidence("event",domain,opened_event["local_id"]) if opened_event else None,evidence("observation",domain,row["opened_observation_id"]) if row.get("opened_observation_id") else None] if r]})
    lifecycle_ids={x.get("id") for x in (opened_event,last_event,recovered_event) if x}
    for run in reversed(_compact_events(_incident_events(conn,domain,row))):
        if run.get("first_event_id") in lifecycle_ids and run.get("latest_event_id") in lifecycle_ids: continue
        items.append({"kind":"MATERIAL_CHANGE","timestamp":run.get("last_observed_at"),"authority":"DERIVED","event_id":run.get("latest_event_id"),"observation_id":((run.get("latest_evidence_refs") or [None])[0].split(":",1)[1] if (run.get("latest_evidence_refs") or [None])[0] else None),"changes":run.get("latest_changes"),"repeat_count":run.get("repeat_count"),"first_observed_at":run.get("first_observed_at"),"evidence_refs":list(dict.fromkeys((run.get("first_evidence_refs") or [])+(run.get("latest_evidence_refs") or [])))})
    if row.get("last_abnormal_observation_id")!=row.get("opened_observation_id") or row.get("last_abnormal_at")!=row.get("opened_at"):
        items.append({"kind":"LAST_ABNORMAL","timestamp":row.get("last_abnormal_at"),"authority":"DERIVED","event_id":last_event.get("id") if last_event else None,"observation_id":canon(domain,row["last_abnormal_observation_id"]) if row.get("last_abnormal_observation_id") else None,"changes":incident.get("latest_changes") or (last_event.get("changes") if last_event else None),"evidence_refs":[r for r in [evidence("event",domain,last_event["local_id"]) if last_event else None,evidence("observation",domain,row["last_abnormal_observation_id"]) if row.get("last_abnormal_observation_id") else None] if r]})
    if row.get("recovered_observation_id") is not None and row.get("recovered_at") is not None:
        items.append({"kind":"INCIDENT_RECOVERED","timestamp":row.get("recovered_at"),"authority":"DERIVED","event_id":recovered_event.get("id") if recovered_event else None,"observation_id":canon(domain,row["recovered_observation_id"]),"changes":recovered_event.get("changes") if recovered_event else None,"evidence_refs":[r for r in [evidence("event",domain,recovered_event["local_id"]) if recovered_event else None,evidence("observation",domain,row["recovered_observation_id"])] if r]})
    order={"INCIDENT_OPENED":0,"MATERIAL_CHANGE":1,"LAST_ABNORMAL":2,"INCIDENT_RECOVERED":3}
    items.sort(key=lambda x:(x.get("timestamp") or "",order.get(x["kind"],9),x.get("event_id") or "",x.get("observation_id") or ""))
    return {"incident_id":incident["id"],"domain":domain,"resource_type":incident["resource_type"],"resource_key":incident["resource_key"],"state":incident["state"],"opened_at":incident["opened_at"],"last_abnormal_at":incident["last_abnormal_at"],"recovered_at":incident["recovered_at"],"items":items,"authority":"DERIVED","provenance":{"linkage_mode":linkage_mode,"direct_event_linkage":direct}}
def _evidence_pair(conn,domain,resource_key,observation_id,event_id=None):
    event_item=_event_by_id(conn,domain,event_id) if event_id is not None else _event_for_observation(conn,domain,resource_key,observation_id)
    return {"observation":_obs_evidence(conn,domain,observation_id),"event":_event_evidence(conn,domain,event_item)}

def incident_evidence_bundle(conn,incident_id,limit=50):
    try: limit=int(limit)
    except (TypeError,ValueError) as exc: raise ValueError("INVALID_LIMIT") from exc
    if limit<1 or limit>50: raise ValueError("INVALID_LIMIT")
    domain,row=_incident_record(conn,incident_id)
    if not row: return None
    incident=normalize_incident(domain,row)
    timeline=incident_timeline(conn,incident_id)
    _,resource_key=_incident_resource(domain,row)
    events=_incident_events(conn,domain,row)
    changes=_compact_events(events)[:limit]
    direct="opened_event_id" in row
    provenance={"linkage_mode":"DIRECT_EVENT_IDS" if direct else "LEGACY_RESOURCE_TIME_CORRELATION","authoritative_ids":{"opened_observation_id":row.get("opened_observation_id"),"last_abnormal_observation_id":row.get("last_abnormal_observation_id"),"recovered_observation_id":row.get("recovered_observation_id"),"opened_event_id":row.get("opened_event_id"),"last_event_id":row.get("last_event_id")},"limitations":[] if direct else ["PVE legacy incident rows do not store opened_event_id/last_event_id; event correlation uses resource identity, lifecycle bounds, and authoritative observation IDs."]}
    opening=_evidence_pair(conn,domain,resource_key,row.get("opened_observation_id"),row.get("opened_event_id") if direct else None)
    latest=_evidence_pair(conn,domain,resource_key,row.get("last_abnormal_observation_id"),row.get("last_event_id") if direct else None)
    recovery=_evidence_pair(conn,domain,resource_key,row.get("recovered_observation_id")) if row.get("recovered_observation_id") is not None and row.get("recovered_at") is not None else None
    return {"incident":incident,"timeline":timeline,"opening_evidence":opening,"latest_abnormal_evidence":latest,"recovery_evidence":recovery,"material_changes":changes,"provenance":provenance,"authority":"DERIVED"}

def _format_change(change):
    if not isinstance(change,dict): return str(change)
    field=change.get("field") or "state"
    actual=change.get("actual")
    expected=change.get("expected")
    if expected is None: return f"{field}={actual}"
    return f"{field}={actual} (expected {expected})"

def _change_sentence(changes):
    if not changes: return None
    return "; ".join(_format_change(c) for c in changes)

def incident_summary(conn,incident_id):
    timeline=incident_timeline(conn,incident_id)
    if not timeline: return None
    bundle=incident_evidence_bundle(conn,incident_id)
    incident=bundle["incident"]
    opened=next((x for x in timeline["items"] if x["kind"]=="INCIDENT_OPENED"),None)
    latest=next((x for x in reversed(timeline["items"]) if x["kind"] in ("LAST_ABNORMAL","INCIDENT_OPENED")),opened)
    recovery=next((x for x in timeline["items"] if x["kind"]=="INCIDENT_RECOVERED"),None)
    resource=incident.get("display_name") or incident.get("resource_key") or "unknown resource"
    headline=f"{incident_id} is {incident['state']} for {resource}."
    opened_detail=_change_sentence((opened or {}).get("changes"))
    opened_statement=f"Opened at {incident.get('opened_at')}" + (f" with {opened_detail}." if opened_detail else ".")
    latest_detail=_change_sentence((latest or {}).get("changes"))
    latest_statement=f"Latest abnormal state was recorded at {incident.get('last_abnormal_at')}" + (f" with {latest_detail}." if latest_detail else ".")
    if incident.get("state")=="RECOVERED" and incident.get("recovered_at"):
        recovery_statement=f"Recovery was recorded at {incident['recovered_at']}."
    else:
        recovery_statement="No recovery is recorded."
    refs=[]
    for item in timeline["items"]:
        for ref in item.get("evidence_refs") or []:
            if ref not in refs: refs.append(ref)
    return {"incident_id":incident_id,"domain":incident.get("domain"),"resource_type":incident.get("resource_type"),"resource_key":incident.get("resource_key"),"state":incident.get("state"),"headline":headline,"opened_statement":opened_statement,"latest_statement":latest_statement,"recovery_statement":recovery_statement,"cause_statement":"RackMarshal does not establish root cause from the recorded incident evidence.","evidence_refs":refs,"provenance":bundle.get("provenance"),"authority":"DERIVED"}

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
        if path.startswith("/v1/incidents/") and path.endswith("/timeline"):
            incident_id=path[len("/v1/incidents/"):-len("/timeline")].rstrip("/")
            item=incident_timeline(conn,incident_id); return (200,envelope(item)) if item else error("INCIDENT_NOT_FOUND","incident not found",404)
        if path.startswith("/v1/incidents/") and path.endswith("/evidence-bundle"):
            incident_id=path[len("/v1/incidents/"):-len("/evidence-bundle")].rstrip("/")
            item=incident_evidence_bundle(conn,incident_id,params.get("limit",50)); return (200,envelope(item)) if item else error("INCIDENT_NOT_FOUND","incident not found",404)
        if path.startswith("/v1/incidents/") and path.endswith("/summary"):
            incident_id=path[len("/v1/incidents/"):-len("/summary")].rstrip("/")
            item=incident_summary(conn,incident_id); return (200,envelope(item)) if item else error("INCIDENT_NOT_FOUND","incident not found",404)
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
