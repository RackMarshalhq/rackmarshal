"""Read-only incident index/dashboard rendering."""
import html
from urllib.parse import quote
from datetime import datetime, timezone
from rackmarshal.api.v1 import DOMAINS, INCIDENT_TABLES, OBS_TABLES, COLLECTORS, list_incidents, normalize_observation
from rackmarshal.ui.narrative import timestamp, occurrences, state_sentence, domain_name

def _e(value):
    return html.escape("" if value is None else str(value), quote=True)

def dashboard_data(conn,recent_limit=20):
    tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    incidents=[]
    for domain in DOMAINS:
        if INCIDENT_TABLES[domain] not in tables:
            continue
        params={"domain":domain,"limit":"200"}
        while True:
            items,meta=list_incidents(conn,params)
            incidents.extend(items)
            if not meta.get("next_cursor"):
                break
            params["cursor"]=meta["next_cursor"]
    open_items=[x for x in incidents if x.get("state")=="OPEN"]
    open_items.sort(key=lambda x:(x.get("opened_at") or "",x["id"]),reverse=True)
    recovered=[x for x in incidents if x.get("state")=="RECOVERED" and x.get("recovered_at")]
    recovered.sort(key=lambda x:(x.get("recovered_at") or "",x["id"]),reverse=True)
    return {
        "open_incidents":open_items,
        "recent_recoveries":recovered[:recent_limit],
        "open_count":len(open_items),
        "recent_recovery_count":min(len(recovered),recent_limit),
        "open_by_domain":{d:sum(x["domain"]==d for x in open_items) for d in DOMAINS},
        "available_domains":[d for d in DOMAINS if INCIDENT_TABLES[d] in tables],
        "authority":"DERIVED",
    }


def collection_data(conn, freshness_builder=None):
    """Read bounded observation metadata and stored cycle results; no host probes."""
    tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    observations={}
    for domain in DOMAINS:
        table=OBS_TABLES[domain]
        columns={r[1] for r in conn.execute(f"PRAGMA table_info({table})")} if table in tables else set()
        if not {"id", "observed_at"}.issubset(columns):
            observations[domain]=None
            continue
        wanted=[c for c in ("id", "observed_at", "recorded_at", "source", "collector", "schema_version") if c in columns]
        where=""
        values=()
        if domain in COLLECTORS:
            if "collector" not in columns:
                observations[domain]=None
                continue
            where=" WHERE collector=?"
            values=(COLLECTORS[domain],)
        row=conn.execute(f"SELECT {','.join(wanted)} FROM {table}{where} ORDER BY id DESC LIMIT 1", values).fetchone()
        observations[domain]=normalize_observation(domain,row) if row else None
    evaluated_at=datetime.now(timezone.utc)
    freshness=freshness_builder(observations, now=evaluated_at) if freshness_builder else {}
    cycles={}
    if "cycle_health" in tables:
        columns={r[1] for r in conn.execute("PRAGMA table_info(cycle_health)")}
        if {"unit_name", "health_state", "last_result_at"}.issubset(columns):
            wanted=[c for c in ("unit_name", "health_state", "last_result_at", "last_success_at", "last_failure_at", "failure_count") if c in columns]
            cycles={row["unit_name"]:dict(row) for row in conn.execute("SELECT "+','.join(wanted)+" FROM cycle_health")}
    rows=[]
    current_units=set()
    for domain in DOMAINS:
        unit="rackmarshal-domain@"+domain.lower()+".service"
        current_units.add(unit)
        rows.append({"domain":domain,"observation":observations[domain],"freshness":freshness.get(domain),"unit":unit,"cycle":cycles.get(unit)})
    return {"domains":rows,"evaluated_at":evaluated_at.isoformat().replace('+00:00','Z'),
            "other_cycles":[cycles[key] for key in sorted(cycles) if key not in current_units]}


def _cycle_result(cycle):
    if not cycle:
        return "Not recorded"
    state=cycle.get("health_state")
    label={"SUCCESS":"Recorded success", "FAILED":"Recorded failure"}.get(state,"Unrecognized recorded result")
    result=f"<strong>{_e(label)}</strong><div>Result: {timestamp(cycle.get('last_result_at'))}</div>"
    for field,label in (("last_success_at","Last success"),("last_failure_at","Last failure")):
        if cycle.get(field) is not None:
            result+=f"<div>{label}: {timestamp(cycle[field])}</div>"
    count=cycle.get("failure_count")
    if count is not None:
        result+=f"<div>Cumulative recorded failures: {_e(count)}</div>"
    return result


def render_collection_coverage(conn, freshness_builder=None, domain=None):
    data=collection_data(conn,freshness_builder)
    rows=[]
    for item in data["domains"]:
        if domain and item["domain"]!=domain:
            continue
        observation=item["observation"] or {}
        fresh=item["freshness"] or {}
        state=fresh.get("state")
        label={"OK":"Fresh observation", "STALE":"Stale observation", "MISSING":"No usable observation time"}.get(state,"Freshness unavailable")
        cycle_state=(item["cycle"] or {}).get("health_state", "NOT_RECORDED")
        reference=observation.get("evidence_ref")
        evidence_html=(f'<a href="/v1/evidence/{_e(quote(reference,safe=":"))}">{_e(reference)}</a>' if reference else "Observation not recorded")
        threshold=fresh.get("stale_after_seconds")
        policy=(f"<div>Stale after {_e(threshold)} seconds</div>" if threshold is not None else "<div>Freshness policy unavailable</div>")
        rows.append(f'<tr data-domain="{_e(item["domain"])}" data-observation-id="{_e(observation.get("id"))}" data-freshness="{_e(state or "UNKNOWN")}" data-cycle-state="{_e(cycle_state)}"><td><strong>{_e(item["domain"])}</strong><div>{_e(domain_name(item["domain"]))}</div></td><td><strong>{_e(label)}</strong><div>Observed: {timestamp(observation.get("observed_at"))}</div>{policy}<div>{evidence_html}</div><a href="/v1/domains/{_e(item["domain"])}">Domain record (JSON)</a></td><td>{_cycle_result(item["cycle"])}<div><code>{_e(item["unit"])}</code></div></td></tr>')
    other=""
    if not domain and data["other_cycles"]:
        other='<details><summary>Other recorded cycle units (historical records)</summary><ul>'+''.join(f'<li><code>{_e(c["unit_name"])}</code>: {_cycle_result(c)}</li>' for c in data["other_cycles"])+"</ul></details>"
    return '<section aria-label="Collection coverage"><h2>Observation freshness and recorded cycle results</h2><p class="muted">Freshness evaluated at '+timestamp(data["evaluated_at"])+'. Fresh observations do not prove a cycle completed successfully or an incident recovered. Cycle results are stored historical records, not a live service probe; absent current-unit results are not inferred from older unit names.</p><div class="table-wrap"><table><thead><tr><th>Domain</th><th>Latest recorded observation</th><th>Recorded cycle result</th></tr></thead><tbody>'+''.join(rows)+"</tbody></table></div>"+other+'<p><a href="/status">Collection and self-watch record (JSON)</a></p></section>'


def _incident_row(item,time_field,label):
    href="/incidents/"+quote(item["id"],safe=":")
    resource=item.get("display_name") or item.get("resource_key") or "Unknown resource"
    state_class=item.get("state") if item.get("state") in ("OPEN","RECOVERED") else ""
    lifecycle=f"<div>Opened: {timestamp(item.get('opened_at'))}</div>"
    lifecycle+=f"<div>Last abnormal: {timestamp(item.get('last_abnormal_at'))}</div>"
    if item.get("state")=="RECOVERED":
        lifecycle+=f"<div>Recovered: {timestamp(item.get('recovered_at'))}</div>"
    return (
        "<tr>"
        f"<td><a class='incident-id' href='{_e(href)}'>{_e(item['id'])}</a>"
        f"<div class='muted'>{_e(item.get('incident_type') or 'Incident type not recorded')}</div></td>"
        f"<td>{_e(item.get('domain'))}<div class='muted'>{_e(domain_name(item.get('domain')))}</div></td>"
        f"<td>{_e(resource)}<div class='muted'>Type: <code>{_e(item.get('resource_type') or 'Not recorded')}</code>"
        f"<br>Key: <code>{_e(item.get('resource_key') or 'Not recorded')}</code></div></td>"
        f"<td><span class='badge {state_class}'>{_e(item.get('state'))}</span>"
        f"<div class='muted'>{_e(state_sentence(item))}</div>"
        f"<div>{_e(occurrences(item.get('occurrence_count')))}</div></td>"
        f"<td>{lifecycle}</td>"
        "</tr>"
    )

def _table(items,time_field,label,empty_text):
    if not items:
        return f"<p class='empty'>{_e(empty_text)}</p>"
    rows="".join(_incident_row(x,time_field,label) for x in items)
    return (
        "<div class='table-wrap'><table><thead><tr>"
        "<th>Incident</th><th>Domain</th><th>Resource</th><th>State</th><th>Recorded lifecycle</th>"
        f"</tr></thead><tbody>{rows}</tbody></table></div>"
    )

def render_incident_index(conn,recent_limit=20,freshness_builder=None):
    data=dashboard_data(conn,recent_limit)
    collection_html=render_collection_coverage(conn,freshness_builder)
    open_html=_table(data["open_incidents"],"opened_at","Opened","No open incidents.")
    recovered_html=_table(data["recent_recoveries"],"recovered_at","Recovered","No recorded recoveries.")
    domain_html="".join(
        f"<li><strong>{_e(d)}</strong> · {_e(domain_name(d))}: {data['open_by_domain'][d]} open</li>"
        for d in data["available_domains"])
    missing=[d for d in DOMAINS if d not in data["available_domains"]]
    coverage_html=("<p class='muted'>Incident ledgers unavailable: "+_e(", ".join(missing))+". Counts cover available ledgers only.</p>") if missing else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Incidents · RackMarshal</title>
<style>
:root{{color-scheme:dark;background:#0b1016;color:#e9eef5;font:16px/1.5 system-ui,sans-serif}}body{{margin:0}}main{{max-width:1180px;margin:auto;padding:40px 24px 80px}}a{{color:#9fc4ff}}h1{{font-size:2.2rem;margin:.1em 0}}.muted{{color:#a8b4c0}}.stats{{display:flex;gap:14px;flex-wrap:wrap;margin:26px 0}}.stat{{border:1px solid #27313d;border-radius:14px;background:#111923;padding:16px 20px;min-width:160px}}.number{{font-size:1.8rem;font-weight:750}}section{{margin-top:30px}}.table-wrap{{overflow-x:auto;border:1px solid #27313d;border-radius:14px}}table{{width:100%;border-collapse:collapse;background:#111923}}th,td{{padding:14px 16px;text-align:left;border-bottom:1px solid #27313d;vertical-align:top}}th{{font-size:.82rem;text-transform:uppercase;letter-spacing:.06em;color:#a8b4c0}}tr:last-child td{{border-bottom:0}}.incident-id{{font-family:ui-monospace,monospace;font-weight:700}}code{{font-family:ui-monospace,monospace}}.badge{{display:inline-block;padding:3px 9px;border:1px solid #516171;border-radius:999px;font-size:.8rem;font-weight:700}}.OPEN{{border-color:#d39842}}.RECOVERED{{border-color:#55a477}}.empty{{padding:22px;border:1px solid #27313d;border-radius:14px;background:#111923}}</style>
</head><body><main>
<div class="muted">RackMarshal · read-only incident ledger</div>
<h1>Incidents</h1>
<p class="muted">Recorded OPEN incidents have no recovery recorded. Recent recoveries are historical lifecycle records; they do not establish current resource health. Select an incident for its summary, timeline, evidence, and provenance.</p>
<div class="stats"><div class="stat"><div class="number">{data['open_count']}</div><div class="muted">Open incidents</div></div><div class="stat"><div class="number">{data['recent_recovery_count']}</div><div class="muted">Recent recoveries shown</div></div></div>
<section aria-label="Domain summary"><h2>Open incidents by domain</h2><ul>{domain_html}</ul>{coverage_html}</section>
{collection_html}
<section><h2>Open incidents</h2>{open_html}</section>
<section><h2>Recent recoveries</h2><p class="muted">Showing up to {recent_limit} most recent recorded recoveries, newest first. Occurrences count recorded abnormal occurrences within one incident, not separate incidents.</p>{recovered_html}</section>
<p class="muted">Authority: {data['authority']} — presentation derived from authoritative RackMarshal incident ledgers. Lifecycle times are shown exactly as recorded, including their timezone; missing values are labeled. OPEN is a recorded lifecycle state, not a live probe. This dashboard is deterministic and read-only; it does not invoke an AI model. <a href="/v1/incidents">Incident records (JSON)</a> · <a href="/v1/status">Recorded domain status (JSON)</a>.</p>
</main></body></html>"""
