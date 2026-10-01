"""Read-only human incident detail rendering."""
import html
from urllib.parse import quote
from rackmarshal.api.v1 import incident_summary, incident_timeline
from rackmarshal.ui.dashboard import render_collection_coverage
from rackmarshal.ui.narrative import timestamp, occurrences, state_sentence, domain_name, incident_brief

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
            actual=_e(c.get("actual") if c.get("actual") is not None else "Not recorded")
            expected=_e(c.get("expected") if c.get("expected") is not None else "Not recorded")
            rows.append(f"<li><strong>{field}</strong>: {actual} <span class='expected'>(expected {expected})</span></li>")
        else:
            rows.append(f"<li>{_e(c)}</li>")
    return "<ul class='changes'>"+"".join(rows)+"</ul>"

def render_incident_page(conn,incident_id,freshness_builder=None,enabled_domains=None):
    summary=incident_summary(conn,incident_id)
    if summary is None:
        return None
    timeline=incident_timeline(conn,incident_id)
    brief=incident_brief(summary,timeline)
    state=summary["state"]
    state_class=state if state in ("OPEN","RECOVERED") else ""
    labels={"INCIDENT_OPENED":"Incident opened", "LAST_ABNORMAL":"Last recorded abnormal state",
            "MATERIAL_CHANGE":"Recorded material change", "INCIDENT_RECOVERED":"Recorded recovery entry"}
    timeline_html=[]
    for item in timeline["items"]:
        refs=" ".join(_ref_link(r) for r in item.get("evidence_refs") or [])
        repeat=item.get("repeat_count")
        repeat_html=(
            f"<p>{_e(repeat)} recorded occurrences of this change; first observed {timestamp(item.get('first_observed_at'))}.</p>"
            if repeat is not None else "")
        timeline_html.append(
            "<article class='timeline-item'>"
            f"<div class='timeline-kind'>{_e(labels.get(item['kind'], item['kind'].replace('_',' ')))}</div>"
            f"{timestamp(item.get('timestamp'))}{repeat_html}"
            f"{_changes(item.get('changes'))}"
            f"<div class='refs'>{refs}</div>"
            "</article>"
        )
    def condition(item, empty):
        if not item or not item.get("changes"):
            return "<p class='muted'>"+_e(empty)+"</p>"
        refs=" ".join(_ref_link(ref) for ref in item.get("evidence_refs") or [])
        return _changes(item["changes"])+"<p>Recorded: "+timestamp(item.get("timestamp"))+"</p><div class='refs'>"+refs+"</div>"
    unknown_html="".join("<li>"+_e(x)+"</li>" for x in brief["unknowns"]+brief["gaps"])
    conflict_html=("<div role='note'><h3>Conflicting records</h3><ul>"+"".join("<li>"+_e(x)+"</li>" for x in brief["conflicts"])+"</ul></div>") if brief["conflicts"] else ""
    brief_html=("<section class='summary' aria-label='Incident explanation'><h2>What the records establish</h2>"
        +conflict_html+"<h3>Opening condition</h3>"+condition(brief["opening"],"Opening condition not recorded in the returned timeline.")
        +"<h3>Latest abnormal condition</h3>"+condition(brief["last_abnormal"],"Latest abnormal condition not recorded; opening evidence is not substituted.")
        +"<h3>Recovery record</h3><p>"+_e(brief["recovery_statement"])+"</p>"
        +("<p>Recorded: "+timestamp((brief["recovery"] or {}).get("timestamp"))+"</p><div class='refs'>"+" ".join(_ref_link(ref) for ref in (brief["recovery"] or {}).get("evidence_refs") or [])+"</div>" if brief["recovery"] else "")
        +"<h3>What remains unknown</h3><ul>"+unknown_html+"</ul><p class='muted'>Deterministic interpretation of returned lifecycle records; no AI model or live target probe is used.</p></section>")
    collection_html=render_collection_coverage(conn,freshness_builder,summary["domain"],enabled_domains=enabled_domains)
    all_refs=" ".join(_ref_link(r) for r in summary.get("evidence_refs") or [])
    provenance=summary.get("provenance") or {}
    limitations=provenance.get("limitations") or []
    limitation_html="".join(f"<li>{_e(x)}</li>" for x in limitations)
    resource=summary.get("display_name") or summary.get("resource_key") or "Unknown resource"
    linkage=provenance.get("linkage_mode")
    linkage_text=(
        "Opening event links use stored event IDs. Latest abnormal and recovery events are paired with their recorded observation IDs."
        if linkage=="DIRECT_EVENT_IDS" else
        "Legacy event links are correlated by resource identity and lifecycle bounds. Stored observation IDs anchor the recorded lifecycle; correlated events are not stored direct links."
        if linkage=="LEGACY_RESOURCE_TIME_CORRELATION" else "Linkage provenance is not recorded.")
    path="/v1/incidents/"+quote(summary["incident_id"],safe=":")
    lifecycle_html="".join(
        f"<dt>{label}</dt><dd>{timestamp(summary.get(field))}</dd>"
        for field,label in (("opened_at","Opened"),("last_abnormal_at","Last abnormal"),("recovered_at","Recovered")))
    body=f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(incident_id)} · RackMarshal</title>
<style>
:root{{color-scheme:dark;background:#0b1016;color:#e9eef5;font:16px/1.5 system-ui,sans-serif}}body{{margin:0}}main{{max-width:980px;margin:auto;padding:40px 24px 80px}}a{{color:#9fc4ff}}.top{{display:flex;justify-content:space-between;gap:24px;align-items:flex-start}}h1{{margin:.1em 0;font-size:2rem}}.badge{{padding:6px 12px;border:1px solid #516171;border-radius:999px;font-weight:700}}.OPEN{{border-color:#d39842}}.RECOVERED{{border-color:#55a477}}section{{margin-top:30px;padding:22px;border:1px solid #27313d;border-radius:14px;background:#111923}}h2{{margin-top:0;font-size:1.1rem}}.summary p{{margin:.5em 0}}.timeline-item{{border-left:3px solid #516171;padding:0 0 20px 18px;margin-left:8px}}.timeline-kind{{font-weight:700}}time,.expected,.muted{{color:#a8b4c0}}.refs{{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px}}.evidence{{font-family:ui-monospace,monospace;font-size:.85rem}}.changes{{margin:.5em 0}}dl{{display:grid;grid-template-columns:auto 1fr;gap:8px 20px}}dd{{margin:0;overflow-wrap:anywhere}}.refs a,code{{overflow-wrap:anywhere}}.table-wrap{{overflow-x:auto}}table{{width:100%;border-collapse:collapse}}th,td{{padding:12px;text-align:left;vertical-align:top;border-bottom:1px solid #27313d}}@media(max-width:600px){{.top{{flex-wrap:wrap}}dl{{grid-template-columns:1fr}}}}code{{font-family:ui-monospace,monospace}}</style></head><body><main>
"""
    body+=f"""<nav><a href="/incidents">← All incidents</a></nav>
<div class="top"><div><div class="muted">RackMarshal · recorded incident</div><h1>{_e(incident_id)}</h1><div>{_e(resource)}</div><div class="muted">{_e(summary['domain'])} · {_e(domain_name(summary['domain']))} · Type: <code>{_e(summary['resource_type'] or 'Not recorded')}</code> · Key: <code>{_e(summary['resource_key'] or 'Not recorded')}</code></div></div><div class="badge {state_class}">{_e(state)}</div></div>
<section><h2>At a glance</h2><p><strong>{_e(brief["state_statement"])}</strong></p><p>Recorded incident type: <code>{_e(summary.get('incident_type') or 'Not recorded')}</code></p><dl>{lifecycle_html}</dl><p>{_e(occurrences(summary.get('occurrence_count')))} within this incident. This count does not represent separate incidents.</p><p class="muted">Lifecycle times are shown exactly as recorded, including their timezone. These are ledger facts, not a live resource probe. Historical recovery does not establish current health.</p></section>
{brief_html}
{collection_html}
<section class="summary"><h2>Recorded summary</h2><p><strong>{_e(summary['headline'])}</strong></p><p>{_e(summary['opened_statement'])}</p><p>{_e(summary['latest_statement'])}</p><p>{_e(brief['recovery_statement'])}</p><p class="muted">{_e(summary['cause_statement'])}</p></section>
<section><h2>Timeline</h2><p class="muted">Recorded lifecycle and material changes, oldest first. Repeated changes show recorded counts when available.</p>{''.join(timeline_html)}</section>
<section><h2>Evidence</h2><p><a href="{_e(path)}">Incident record (JSON)</a> · <a href="{_e(path)}/summary">Deterministic summary (JSON)</a> · <a href="{_e(path)}/timeline">Timeline (JSON)</a> · <a href="{_e(path)}/evidence-bundle">Evidence bundle (JSON)</a></p><div class="refs">{all_refs or '<span class="muted">No evidence references recorded.</span>'}</div></section>
<section><h2>Provenance and authority</h2><p>Linkage: <code>{_e(linkage or 'Not recorded')}</code></p><p>{_e(linkage_text)}</p><ul>{limitation_html}</ul><p class="muted">Authority: {_e(summary['authority'])} — deterministic presentation derived from authoritative RackMarshal incident, event, and observation ledgers. Recorded changes describe observed triggers; they do not establish root cause. This page is read-only and contains no remediation controls. No AI model is invoked.</p></section>
</main></body></html>"""

    return body
