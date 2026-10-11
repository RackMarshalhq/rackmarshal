# BACKUP partial-observation status summaries

This development-only change follows `b4b380c`; it does not change the frozen RC5
candidate or inherit its qualification. It changes summary derivation only.
Collectors, comparison/reconciliation, stored observations and incident state
are unchanged.

An observer can mark unavailable sections through `section_errors`, for example:

```json
{"primary":{"state":"UNKNOWN","reason":"deadline_exceeded"}}
```

The status summary exposes a sanitized copy of this metadata. Section names and
states are validated, known reason codes are preserved, unknown reason strings
become `section_unavailable`, and extra worker details are discarded. Malformed
metadata yields the existing generic `BACKUP_SUMMARY_UNAVAILABLE` / `UNKNOWN`
summary rather than silently treating evidence as complete.

| Failed section | Summary behavior |
| --- | --- |
| `primary` | `primary_count` and `missing_on_secondary` are null |
| `secondary` | `secondary_count`, `max_secondary_age_hours` and `missing_on_secondary` are null |
| Other declared section | Its failed data is excluded; successful sections remain available |

A successful empty store remains a measured count of zero and a successful empty
missing-copy list remains `[]`. Consumers must distinguish these from null,
which means the measurement is unavailable. Valid legacy observations without
`section_errors` keep their previous summary shape and behavior. Stored payloads
are not modified when summaries are derived.

The summary does not turn a partial probe into recovery evidence or change the
BACKUP domain's incident-derived status. A returned successful Messages section
can be displayed independently from a failed phone section; the existing
incident engine remains responsible for lifecycle reconciliation.
