"""Read-only human incident detail rendering."""
import html
from urllib.parse import quote
from rackmarshal.api.v1 import incident_summary, incident_timeline

def _e(value):
    return html.escape("" if value is None else str(value), quote=True)

def _ref_link(ref):
    href="/v1/evidence/"+quote(ref,safe=":")
    return f'<a class="evidence" href="{_e(href)}">{_e(ref)}</a>'

def _changes(changes):
    if not changes:
        return ""
    rows=[]
    for c in changes:
        if isinstance(c,dict):
            field=_e(c.get("field") or "state")
            actual=_e(c.get("actual"))
            expected=_e(c.get("expected"))
            rows.append(f"<li><strong>{field}</strong>: {actual} <span class='expected'>(expected {expected})</span></li>")
        else:
            rows.append(f"<li>{_e(c)}</li>")
    return "<ul class='changes'>"+"".join(rows)+"</ul>"

def render_incident_page(conn,incident_id):
    summary=incident_summary(conn,incident_id)
    if summary is None:
        return None
    timeline=incident_timeline(conn,incident_id)
    state=summary["state"]
    timeline_html=[]
    for item in timeline["items"]:
        refs=" ".join(_ref_link(r) for r in item.get("evidence_refs") or [])
        timeline_html.append(
            "<article class='timeline-item'>"
            f"<div class='timeline-kind'>{_e(item['kind'].replace('_',' '))}</div>"
            f"<time>{_e(item.get('timestamp'))}</time>"
            f"{_changes(item.get('changes'))}"
            f"<div class='refs'>{refs}</div>"
            "</article>"
        )
    all_refs=" ".join(_ref_link(r) for r in summary.get("evidence_refs") or [])
    provenance=summary.get("provenance") or {}
    limitations=provenance.get("limitations") or []
    limitation_html="".join(f"<li>{_e(x)}</li>" for x in limitations)
    body=f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(incident_id)} · RackMarshal</title>
<style>
:root{{color-scheme:dark;background:#0b1016;color:#e9eef5;font:16px/1.5 system-ui,sans-serif}}body{{margin:0}}main{{max-width:980px;margin:auto;padding:40px 24px 80px}}a{{color:#9fc4ff}}.top{{display:flex;justify-content:space-between;gap:24px;align-items:flex-start}}h1{{margin:.1em 0;font-size:2rem}}.badge{{padding:6px 12px;border:1px solid #516171;border-radius:999px;font-weight:700}}.OPEN{{border-color:#d39842}}.RECOVERED{{border-color:#55a477}}section{{margin-top:30px;padding:22px;border:1px solid #27313d;border-radius:14px;background:#111923}}h2{{margin-top:0;font-size:1.1rem}}.summary p{{margin:.5em 0}}.timeline-item{{border-left:3px solid #516171;padding:0 0 20px 18px;margin-left:8px}}.timeline-kind{{font-weight:700}}time,.expected,.muted{{color:#a8b4c0}}.refs{{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px}}.evidence{{font-family:ui-monospace,monospace;font-size:.85rem}}.changes{{margin:.5em 0}}code{{font-family:ui-monospace,monospace}}</style></head><body><main>
"""
    body+=f"""<div class="top"><div><div class="muted">RackMarshal incident</div><h1>{_e(incident_id)}</h1><div>{_e(summary['domain'])} · <code>{_e(summary['resource_type'])}</code> · <code>{_e(summary['resource_key'])}</code></div></div><div class="badge {_e(state)}">{_e(state)}</div></div>
<section class="summary"><h2>Recorded summary</h2><p><strong>{_e(summary['headline'])}</strong></p><p>{_e(summary['opened_statement'])}</p><p>{_e(summary['latest_statement'])}</p><p>{_e(summary['recovery_statement'])}</p><p class="muted">{_e(summary['cause_statement'])}</p></section>
<section><h2>Timeline</h2>{''.join(timeline_html)}</section>
<section><h2>Evidence</h2><div class="refs">{all_refs or '<span class="muted">No evidence references recorded.</span>'}</div></section>
<section><h2>Provenance</h2><p>Linkage: <code>{_e(provenance.get('linkage_mode'))}</code></p><ul>{limitation_html}</ul><p class="muted">Authority: {_e(summary['authority'])}. This page is read-only and contains no remediation controls.</p></section>
</main></body></html>"""
    return body
