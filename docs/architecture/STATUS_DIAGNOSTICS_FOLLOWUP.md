# Status diagnostics follow-up

This isolated source change addresses two static-review findings after `95a3bc8`. It does not change frozen RC5 artifacts, qualification evidence, running services or incident records.

## Invalid freshness policy

Previously, unreadable/malformed domain metadata or an invalid explicit threshold silently selected 900 seconds. This could report an observation as fresh against a fallback rather than the intended policy. A malformed non-table `status` value could also raise from the status builder. Valid policies and documented defaults for absent optional metadata (including an absent domains directory) remain unchanged. Absence alone is not newly diagnosed as corruption.

When an identified domain's existing metadata cannot be read/parsed, its known domain folder declares a mismatched/invalid domain ID, its status block is invalid, or its explicit threshold is not a positive integer, freshness now uses the existing `MISSING` state with `reason=FRESHNESS_POLICY_UNAVAILABLE`. The observed timestamp and computed age remain recorded facts. `stale_after_seconds` is null because no validated policy is available. Additive `threshold_configuration` metadata identifies `ERROR`, a stable error code, the documented fallback value, and that the fallback was **not** used to classify freshness. It does not publish source file paths, invalid configuration values or raw exceptions.

The existing self-watch status becomes degraded for this missing policy. Its existing `freshness:<domain>` signal remains desired/open, rather than disappearing and allowing unsupported recovery. The incident detail carries the policy-gap reason. No new state or incident type was introduced, and this is a collection-policy gap, not evidence of a resource failure. The dashboard says “Freshness policy unavailable”, preserves the observation timestamp and does not label the observation fresh or claim the timestamp is absent.

## Backup summary derivation

Previously, an exception deriving the optional PBS-store summary (for example a nonnumeric secondary age or malformed phones shape) silently omitted it. Now `/status` includes a `pbs_store` object with the existing `error` convention, stable `code=BACKUP_SUMMARY_UNAVAILABLE`, and `evidence_state=UNKNOWN`. Raw exceptions and payload values are not included in this diagnostic. Existing valid summaries, explicit collector errors and absent optional summaries retain their previous representation. The domain's existing incident-count-derived `status` is not rewritten; clients must distinguish this from the explicit summary evidence gap.

This helper does not validate every possible malformed payload, repair collectors or establish current resource health. Raw collector-provided error handling predates this change and was not broadly redesigned.

## Validation

Seven focused tests pass, covering valid/default thresholds; malformed TOML/status blocks and six invalid threshold types/values; read permission errors without detail leakage; retained timestamps and age; degraded self-watch classification; real synthetic SQLite self-watch synchronization preserving an existing OPEN freshness signal without recovery; dashboard wording; malformed backup summary diagnostics; and valid/absent/collector-error compatibility.

All checks use local synthetic state. Candidate-specific checks and independent review remain required before any new candidate qualification. Frozen RC5 evidence does not qualify changed source bytes.
