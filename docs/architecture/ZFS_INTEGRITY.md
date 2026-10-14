# ZFS permanent data integrity evidence

Pool availability and data integrity are separate facts. An ONLINE pool can
still contain permanent data errors. The pool `error_count` is an absolute
integrity measurement, not an advisory historical vdev I/O counter.

- A positive permanent error count produces STATUS-CHANGED and retains an open
  incident on every sample, including when a baseline contains that same count.
- Explicit integer zero is CLEAN integrity evidence. Missing or null counts
  remain UNKNOWN through collection and ingestion; they are never coerced to zero.
  Malformed, fractional, boolean and negative counts are rejected. The source
  collector accepts nonnegative decimal integer strings and normalizes them to
  integers; the normalized ingestion contract accepts integers or null only.
- A pool incident recovers only when the recorded observation identifies the
  baseline pool GUID, reports ONLINE matching the expected state, and explicitly
  reports zero permanent errors. A comparator MATCH alone cannot authorize it.
- Changing from one abnormal classification to another retains the original
  episode. The latest event describes the current abnormality; it does not create
  fictitious recovery evidence.

Historical vdev read/write/checksum counters retain their existing advisory
semantics. Permanent pool errors use the existing STATUS-CHANGED event/incident
vocabulary; no migration or rewrite of prior ledger records is required.

`/status`, `/v1/status`, `/v1/domains`, and `/v1/domains/ZFS` expose additive ZFS
`integrity` evidence with aggregate state CLEAN, PROBLEM, or UNKNOWN, observation
identity/time, and per-pool availability, integrity, and permanent error count.
PROBLEM dominates UNKNOWN across pools. Missing, empty or malformed observations
cannot establish CLEAN integrity. Existing `status` and `overall_status` remain
incident-ledger projections: OK means no open incident, not proof of complete
integrity evidence. Consumers must inspect integrity and freshness before claiming
health. `/v1/health` remains API/database liveness only.

This fix does not retroactively repair incidents incorrectly recovered by older
code. A subsequent positive sample opens an incident under the corrected policy.
Deployments and historical ledger repair require separately authorized work.

Regression tests use synthetic observations and disposable databases; they do not
contact ZFS hosts or replace exact-artifact lifecycle and sustained-operation
qualification.
