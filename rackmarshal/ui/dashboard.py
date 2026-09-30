"""Read-only incident index/dashboard rendering."""
import html
from urllib.parse import quote
from rackmarshal.api.v1 import DOMAINS, INCIDENT_TABLES, list_incidents

def _e(value):
    return html.escape("" if value is None else str(value), quote=True)

def dashboard_data(conn,recent_limit=20):
    tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    incidents=[]
    for domain in DOMAINS:
        if INCIDENT_TABLES[domain] not in tables:
            continue
        items,_=list_incidents(conn,{"domain":domain,"limit":"200"})
        incidents.extend(items)
    open_items=[x for x in incidents if x.get("state")=="OPEN"]
    open_items.sort(key=lambda x:(x.get("opened_at") or "",x["id"]),reverse=True)
    recovered=[x for x in incidents if x.get("state")=="RECOVERED" and x.get("recovered_at")]
    recovered.sort(key=lambda x:(x.get("recovered_at") or "",x["id"]),reverse=True)
    return {
        "open_incidents":open_items,
        "recent_recoveries":recovered[:recent_limit],
        "open_count":len(open_items),
        "recent_recovery_count":min(len(recovered),recent_limit),
        "authority":"DERIVED",
    }

def _incident_row(item,time_field,label):
    iid=_e(item["id"])
    href="/incidents/"+quote(item["id"],safe=":")
    resource=item.get("display_name") or item.get("resource_key") or "unknown resource"
    return (
        "<tr>"
        f"<td><a class='incident-id' href='{_e(href)}'>{iid}</a></td>"
        f"<td>{_e(item.get('domain'))}</td>"
        f"<td><code>{_e(item.get('resource_type'))}</code><br>{_e(resource)}</td>"
        f"<td><span class='badge {_e(item.get('state'))}'>{_e(item.get('state'))}</span></td>"
        f"<td><span class='muted'>{_e(label)}</span><br><time>{_e(item.get(time_field))}</time></td>"
        "</tr>"
    )

def _table(items,time_field,label,empty_text):
    if not items:
        return f"<p class='empty'>{_e(empty_text)}</p>"
    rows="".join(_incident_row(x,time_field,label) for x in items)
    return (
        "<div class='table-wrap'><table><thead><tr>"
        "<th>Incident</th><th>Domain</th><th>Resource</th><th>State</th><th>Time</th>"
        f"</tr></thead><tbody>{rows}</tbody></table></div>"
    )

def render_incident_index(conn,recent_limit=20):
    data=dashboard_data(conn,recent_limit)
    open_html=_table(data["open_incidents"],"opened_at","Opened","No open incidents.")
    recovered_html=_table(data["recent_recoveries"],"recovered_at","Recovered","No recorded recoveries.")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Incidents · RackMarshal</title>
<style>
:root{{color-scheme:dark;background:#0b1016;color:#e9eef5;font:16px/1.5 system-ui,sans-serif}}body{{margin:0}}main{{max-width:1180px;margin:auto;padding:40px 24px 80px}}a{{color:#9fc4ff}}h1{{font-size:2.2rem;margin:.1em 0}}.muted{{color:#a8b4c0}}.stats{{display:flex;gap:14px;flex-wrap:wrap;margin:26px 0}}.stat{{border:1px solid #27313d;border-radius:14px;background:#111923;padding:16px 20px;min-width:160px}}.number{{font-size:1.8rem;font-weight:750}}section{{margin-top:30px}}.table-wrap{{overflow-x:auto;border:1px solid #27313d;border-radius:14px}}table{{width:100%;border-collapse:collapse;background:#111923}}th,td{{padding:14px 16px;text-align:left;border-bottom:1px solid #27313d;vertical-align:top}}th{{font-size:.82rem;text-transform:uppercase;letter-spacing:.06em;color:#a8b4c0}}tr:last-child td{{border-bottom:0}}.incident-id{{font-family:ui-monospace,monospace;font-weight:700}}code{{font-family:ui-monospace,monospace}}.badge{{display:inline-block;padding:3px 9px;border:1px solid #516171;border-radius:999px;font-size:.8rem;font-weight:700}}.OPEN{{border-color:#d39842}}.RECOVERED{{border-color:#55a477}}.empty{{padding:22px;border:1px solid #27313d;border-radius:14px;background:#111923}}</style>
</head><body><main>
<div class="muted">RackMarshal · read-only incident ledger</div>
<h1>Incidents</h1>
<p class="muted">Open incidents are shown first. Recent recovery history is ordered by recorded recovery time. Select an incident for its deterministic summary, timeline, evidence, and provenance.</p>
<div class="stats"><div class="stat"><div class="number">{data['open_count']}</div><div class="muted">Open incidents</div></div><div class="stat"><div class="number">{data['recent_recovery_count']}</div><div class="muted">Recent recoveries shown</div></div></div>
<section><h2>Open incidents</h2>{open_html}</section>
<section><h2>Recent recoveries</h2>{recovered_html}</section>
<p class="muted">Authority: {data['authority']}. This dashboard is deterministic and read-only; it does not invoke an AI model.</p>
</main></body></html>"""
