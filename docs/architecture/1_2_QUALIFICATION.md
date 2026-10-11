# 1.2 candidate qualification

## Unpublished security follow-up to frozen RC5

This development tree changes outbound HTTP validation/redirect handling and
optimized-interpreter acceptance guards. Frozen RC5 source `f9ccecb`, artifacts,
and retained qualification evidence are unchanged. See
[static review follow-up](STATIC_REVIEW_FOLLOWUP.md) for findings and coverage.
Local regression results do not qualify these changed bytes. A separately
versioned candidate would need new exact-artifact security, installation,
lifecycle, client and sustained-operation receipts before promotion. No new
qualification run or deployment is started by these changes.

## Current preparation: 1.2.0rc5

Status: **LOCAL HEALTH-POLICY FIX; unpublished; fresh qualification PENDING**.

A live local rc4 client loaded the exact packaged policy and successfully called get_health, but omitted the get_status call required by HEALTH_ACCEPTANCE. The shipped policy did not express that requirement, and its runtime health plan selected only get_health. The failed receipt is retained privately; installation/cache checks and the independent rc4 synthetic run are separate evidence.

This source aligns the runtime instructions, canonical packaged skill and deterministic health plan with the existing dual-tool acceptance contract. It does not change the acceptance prompt or relax the gate. Deterministic tests cannot establish live model compliance. Local and private hosted client acceptance, exact artifact lifecycle/privacy/security checks and a separate sustained window remain PENDING for rc5. Frozen rc4 files and its sampler are unchanged; no receipt transfers to changed bytes.

## Frozen qualification: 1.2.0rc4

Status: **UNPUBLISHED; independent synthetic window RUNNING; local health acceptance FAIL**.

The window began October 4, 2026 and cannot complete before October 7. Actual successful samples and bounded gaps remain required. Its exact frozen artifacts and sampler are unchanged by this policy fix; client acceptance remains a separate release blocker.

This source fixes release gating, compressed-asset inspection, narrow scanner exemptions, recovery-summary wording and offset-aware material-change bounds. Development tests and artifact build receipts do not qualify changed runtime bytes. Frozen rc2 and rc3 runs, their artifacts and their owners remain unchanged. No evidence from those runs is promoted to rc4 qualification.

The upload workflow requires a source/artifact-bound receipt package as described in [release gate](RELEASE_GATE.md). Synthetic 72-hour operation and production routine-use remain separate, initially PENDING. Local explicit and private hosted explicit client acceptance require their own receipts; other activation surfaces remain unsupported until separately qualified. No new qualification run or publication is authorized by preparing this source.

## Historical preparation: 1.2.0rc3

Updated: 2026-10-02. Status: **LOCAL PREPARATION; not published; fresh qualification pending**.

This candidate combines the reviewed 1.2 implementation, setup regression coverage, health acceptance fixtures, exact MCP tool-count enforcement, and public source/archive privacy fixes. It has a distinct package/plugin version. Build receipts must pin its source commit, toolchain, artifact hashes, local checks, and scope limits. Local test/build results do not establish installation, client activation, resource health, or sustained operation.

Before promotion, retain fresh evidence for the exact rc3 bytes: disposable Debian installation/reboot; stable upgrade, rollback and re-upgrade with state/configuration preservation; invalid-wheel rejection; installed-file integrity; HTTP/MCP positive and negative cases; dependency audit/static review; separately scoped local/private hosted client acceptance; and a new 72-hour consecutive disposable synthetic window with successful cycles and bounded sample gaps. These gates are PENDING until their own receipts exist. No new window is started by preparing this candidate.

The frozen rc2 artifacts and owner-controlled run remain unchanged. Their evidence applies only to the original hashes. The separate 1.1 routine-use gate is not satisfied by either synthetic candidate run. A release/tag, deployment, or qualification start requires separate authorization.

## Historical frozen candidate: 1.2.0rc2

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
