# 1.2 candidate qualification

Updated: 2026-10-01. Candidate: **1.2.0rc2**. Status: **PENDING sustained qualification; not published**.

The five 1.2 implementation goals are present: read-only guided setup, honest monitoring coverage, deterministic incident explanations, reproducible optional Investigator installation, and stronger internal reliability qualification. Missing/unknown mount observations now preserve OPEN incidents; only an explicit healthy observation records recovery.

| Gate | Result | Qualified scope |
|---|---|---|
| Correctness/lifecycle/failure/privacy/authority suite | PASS | 213 tests; resource warnings treated as errors |
| CI | PASS | Python 3.11, 3.12 and 3.13 |
| Fresh installation and reboot | PASS | Disposable Debian 12, exact candidate installer/wheel |
| Stable upgrade, rollback and re-upgrade | PASS | Pre-existing rows/config preserved; legitimate appended history retained |
| Invalid-wheel rejection | PASS | Installed code, database and configuration preserved |
| Installed artifact integrity | PASS | 94 wheel members byte verified |
| HTTP/MCP | PASS | Six HTTP routes; eleven MCP positive calls and six rejection cases |
| Connection check | PASS | Exact read-only tool contract, local HTTP MCP |
| Local plugin install | PASS | Codex CLI 0.159.3; versioned marketplace and three cached plugin files byte verified |
| Private hosted import | PASS | Versioned combined archive, existing connected app and one bundled skill |
| Explicit hosted policy acceptance | PASS | Work-mode explicit skill selection: timestamped health/lifecycle, canonical evidence, fact/advisory separation, restart/manual-closure denial, unsupported-resource limits |
| Dependency audit | PASS within scope | 29 installed optional-runtime dependencies, zero known vulnerabilities; local project is outside the vulnerability-database audit |
| Static review | PASS within scope | Zero high, 23 medium and 82 low; medium test/module/code contexts match the previously reviewed baseline |
| Expanded source/artifact privacy | PASS | Generic public source, wheel, sdist, installer and local plugin; private cloud binding excluded |
| 72-hour sustained synthetic operation | PENDING | Repeated exact-wheel integrity, synthetic mount observation/process/recovery, HTTP/MCP and maximum-gap checks |

## Limits and continuation

The bounded synthetic window started October 1 and cannot complete before October 4, 2026. Actual successful samples and gap checks are required; elapsed time alone is insufficient. Its scope is synthetic MOUNT processing and local HTTP/MCP on a disposable installation. It does not qualify production collectors, production routine use or 1.1 stable promotion.

The installed cloud archive and explicit Work-mode policy acceptance are retained separately. A normal Chat-mode candidate conversation failed to retrieve records while a direct registered-app health call succeeded. Chat-mode/implicit activation is unqualified. Desktop activation, authenticated local model conversations, additional clients and broader audience controls are also unqualified. No public release or stable promotion has occurred.

The fresh-install harness briefly queried immediately after a service restart and hit a readiness race. The service was healthy; resumed and reboot checks passed. This harness failure is retained separately from product results.

Qualification follows these exact artifacts built from source commit `f5d4cbc54ce17deb13a700027c795cc42de2045d`. Later documentation updates do not replace those artifacts. Any changed runtime requires fresh installation/upgrade/privacy/security qualification and a new sustained runtime window.
