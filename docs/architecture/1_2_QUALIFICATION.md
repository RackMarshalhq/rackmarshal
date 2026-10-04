# 1.2 candidate qualification

Updated: 2026-10-04. Frozen candidate: **1.2.0rc2**, source `f5d4cbc54ce17deb13a700027c795cc42de2045d`. Status: **PASS within supported scope; not published**.

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
| 72-hour sustained synthetic operation | PASS | 866 passing samples; 259453.182158 seconds; maximum gap 301.084669 seconds against a 420-second limit |

## Limits and continuation

The actual successful sample window ran from 2026-10-01T07:42:11.479589Z through 2026-10-04T07:46:24.661747Z: 72 hours, 4 minutes and 13 seconds. All 866 samples passed with strictly increasing timestamps and no gap above 301.084669 seconds. Every sample verified the exact wheel and 94 installed package members, synthetic MOUNT processing, five HTTP routes and the local MCP connection contract. Independent missing-evidence observations kept an incident OPEN without recording recovery; explicit healthy observations recorded recovery. The run retained 73 openings and 73 recoveries. The original 28 baseline rows across 34 tables, schema and configuration were preserved; database integrity passed. The fresh fixture had zero notification rows before and after, with delivery stopped.

These recorded samples establish the synthetic gate; elapsed time alone was not used. Its scope is synthetic MOUNT processing and local HTTP/MCP on a disposable installation. It does not qualify production collectors, production routine use or 1.1 stable promotion.

The installed cloud archive and explicit Work-mode policy acceptance are retained separately. A normal Chat-mode candidate conversation failed to retrieve records while a direct registered-app health call succeeded. Chat-mode/implicit activation is unqualified. Desktop activation, authenticated local model conversations, additional clients and broader audience controls are also unqualified. No public release or stable promotion has occurred.

The fresh-install harness briefly queried immediately after a service restart and hit a readiness race. The service was healthy; resumed and reboot checks passed. This harness failure is retained separately from product results.

Qualification follows these exact artifacts built from source commit `f5d4cbc54ce17deb13a700027c795cc42de2045d`. Later documentation updates do not replace those artifacts. Any changed runtime requires fresh installation/upgrade/privacy/security qualification and a new sustained runtime window.

## Frozen artifacts and integrated main

PR10 merged into main on 2026-10-02 at commit `e95bed91585c457361db9285c9b0d14f50c59563`. That integrated runtime includes later checker changes and differs from this frozen candidate. This result does not qualify merged main. A distinct candidate identity and fresh exact-artifact qualification, including a new sustained window, are required for that runtime before release.

The four qualified artifacts remained unchanged throughout the window:

| Artifact | SHA256 |
|---|---|
| rackmarshal-1.2.0rc2-py3-none-any.whl | `c0d0def907adeec9fd165d49b3dabb05644e01230e47dd94f64f89619171a17d` |
| rackmarshal-1.2.0rc2.tar.gz | `2d123e9f5521e8f047a09d499e0cbdfe8b929c43943a738417256561bb524760` |
| rackmarshal-installer-1.2.0-rc2.tar.gz | `79d9427422e73682571f5f5a948e1d9f02684fedaf6f6be702d0584baf812ea6` |
| rackmarshal-investigator-local-1.2.0-rc2.zip | `18c7c7e085b90658a934dd0ffaf440f62bd1d2a63f340de57874f9b512d092a5` |

Frozen documentation-head CI receipts: [CI receipt 1](https://github.com/RackMarshalhq/rackmarshal/actions/runs/36833089204) and [CI receipt 2](https://github.com/RackMarshalhq/rackmarshal/actions/runs/36833093503). Private receipts and the complete synthetic sample log are retained outside the public tree. Qualification-specific fixture services are stopped after evidence retention. No release, tag, promotion, production deployment or audience expansion is part of this completion.
