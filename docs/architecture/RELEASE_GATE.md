# Exact candidate upload gate

The manually dispatched Release Build workflow downloads a same-repository `release-qualification` artifact from the supplied run ID, builds the candidate, then runs `scripts/release-candidate-gate.py`. It uploads candidate assets only after the gate passes. It does not publish a release. The input bundle must contain only sanitized release evidence suitable for that repository's artifact audience; private operational payloads, bindings and credentials remain in private storage.

Run locally from a clean exact source checkout:

```sh
python scripts/release-candidate-gate.py --source FULL_COMMIT_SHA --record .qualification/release.json
```

`release.json` contains `source_commit`, an `artifacts` object mapping every wheel, sdist, installer and local-plugin filename to its SHA-256, `supported_activation`, and `gates`. Source must equal HEAD, the checkout must have no tracked changes or untracked source, and the artifact set/hashes must match exactly. Build outputs and designated private receipt paths are ignored by Git. Final assets are recursively privacy-scanned before exclusive creation of `SHA256SUMS`; an existing checksum file causes failure. This is a reviewed-evidence integrity gate, not a cryptographic attestation that a trusted receipt author actually ran the tests.

Each gate defaults to PENDING when no evidence exists. Required candidate gates are `tests`, `lifecycle`, `privacy_review`, `dependency_review`, `synthetic_72h`, `activation_local_explicit` and `activation_private_hosted_explicit`. `production_routine_72h` must have an explicit separate state; it may remain PENDING for an rc candidate. `--scope stable` requires it to pass too, and a non-rc version cannot use candidate scope. Do not translate a scheduled date or elapsed wall time into PASS.

A PASS gate names a relative `receipt` file and its `sha256`. Every claimed PASS (including optional gates) requires a matching receipt with `gate`, `result: "PASS"`, the same `source_commit` and complete `artifacts` mapping. Missing, duplicate, mismatched or escaping references fail. Optional activation names are `desktop`, `implicit`, `other_clients` and `broader_distribution`; adding one to `supported_activation` requires its own gate/receipt with a matching `activation` field. The two required modes are `local_explicit` and `private_hosted_explicit`. Unsupported modes are not evidence of acceptance.

A window receipt additionally contains `kind` (`disposable_synthetic` or `production_routine_use`), `start`, `finished` and chronological `samples`. Each sample carries zero-based `sequence`, `at`, and explicit `result: "PASS"`. The gate verifies timezone-aware timestamps, continuous sequence, positive gaps no longer than 420 seconds, at least 72 hours between the actual first and final samples, and no future final sample. The start/finish fields must equal the recorded endpoints. Preserve underlying scoped cycle, lifecycle, HTTP/MCP and history evidence privately; a sanitized receipt does not broaden that evidence's scope. A different routine-use sampling cadence needs its own reviewed gate contract, not a synthetic waiver.

A new candidate starts with both window gates PENDING. Never point its record at an earlier candidate's receipt: changed source or any changed artifact hash invalidates that binding. Local client installation/cache integrity, authenticated hosted explicit selection, and any additionally advertised client modes must be requalified for the new package. Packaging/toolchain differences that change bytes also require matching evidence; reproducibility claims are scoped to the retained toolchain.
