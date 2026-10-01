# Deterministic incident explanations (1.2 development)

The incident detail page presents the opening condition, latest abnormal condition, recovery record and evidence gaps from the existing sanitized timeline and summary. It invokes no model, collector or live target probe and changes no ledger records or API/MCP contracts.

Opening changes are not substituted when the latest abnormal changes are missing. Typed references link to evidence records; a reference does not guarantee availability or reveal an observation payload. Direct and legacy correlated linkage remain distinguished in provenance. Triggering conditions do not establish root cause, and historical recovery does not establish current health.

OPEN with a recovery timestamp/entry, recovery preceding abnormal/opening time, or disagreement between incident and timeline timestamps is flagged for review. The page withholds a consistent recovery interpretation when records conflict. Missing timestamps and timezone information are explicit gaps; ordering is compared only for valid timezone-aware times. Missing expected/actual change values are labeled Not recorded.

This is development version 1.2.0.dev2; no stable promotion or production deployment is implied.
