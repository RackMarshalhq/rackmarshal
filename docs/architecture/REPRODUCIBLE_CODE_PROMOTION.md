# Reproducible code-only promotion

Use `scripts/promote-package-files.py` for already qualified Python-file patches
to existing status and MCP installations. This replaces ad hoc source copying.
It is an operator/development tool, not an Investigator tool or API capability.

For dependency, packaging, schema, configuration, service-unit, credential, or
permission changes, use the existing release installer/upgrade workflow instead.
This procedure neither installs wheels nor changes package distribution metadata.
Its selected Git revision is the authority for the promoted source bytes.

## Qualification and scope

Choose one bounded patch and explicitly list its changed `rackmarshal/*.py`
files. Include related modules needed by both installations. Review that the
patch needs no migrations or dependency upgrades. Commit the source and record
the full 40-character SHA; moving refs and working-tree contents are not inputs.

Run the publication gate once with ResourceWarnings enabled on the staging
interpreter, then the full suite once on the existing target Python version in
an isolated candidate directory. Record results against that source revision.
Repeat checks only after relevant changes, failures, or unresolved concerns.
Do not invoke the production installer to qualify this code-only procedure.

```sh
PYTHONWARNINGS=always::ResourceWarning ./scripts/publication-gate.sh
```

The procedure reuses the committed `scripts/prove-incident-narrative.py` and
`rackmarshal/agent/live_eval.py` with `evals/investigator_v1_1_live.json`.
They qualify the current incident narrative/Investigator surface; their
representative data assumptions may need review if production state changes.
An acceptance failure is a rollback trigger, never permission to weaken a check.

## Prepare and inspect

Use the actual qualified full commit SHA and a new output directory:

```sh
python3 scripts/promote-package-files.py prepare \
  --repo /path/to/repository \
  --revision FULL_40_CHARACTER_COMMIT_SHA \
  --file rackmarshal/api/v1.py \
  --output /path/to/new-bundle
```

Repeat `--file` for each selected Python file. The bundle includes a manifest,
selected committed blobs, SHA-256 hashes, and the pinned acceptance scripts and
suite. It excludes configuration, credentials, databases, and raw evidence.
SHA-256 proves byte consistency; it is not a signature or a substitute for
trusting/reviewing the source commit and operator-provided bundle.

Transfer the directory intact to the installation host. Do not extract an
untrusted archive as root. Verify and inspect using the existing interpreters:

```sh
python3 /path/to/promote-package-files.py plan \
  --bundle /path/to/new-bundle \
  --status-python /opt/rackmarshal/venv/bin/python \
  --mcp-python /opt/rackmarshal-mcp/venv/bin/python
```

The tool discovers package roots using isolated interpreter execution, validates
bundle hashes and Python syntax, rejects symlink/escaping paths, and compares
every selected file in both installations. No-op means all selected bytes
already match; it is not a service-health or acceptance certification. Unchanged
sources are not copied, services are not restarted, and no new backup is created.

## Apply during an authorized maintenance window

Both existing application services must be active. Run as root on the target
host with rollback storage outside both package roots:

```sh
python3 /path/to/promote-package-files.py apply \
  --bundle /path/to/new-bundle \
  --backups /var/lib/rackmarshal/deployment-backups \
  --ready-url http://127.0.0.1:8080/readyz
```

Default acceptance endpoints are loopback status port 9110 and MCP port 8000.
Use `--status-url`, `--mcp-url`, or the interpreter options for an existing
non-default installation. URLs must stay on unauthenticated loopback HTTP.
The optional tunnel readiness probe preserves the existing private transport;
the tunnel service itself is not restarted or reconfigured.

Execution order:

1. Acquire an exclusive host promotion lock; inspect both installations.
2. Save original bytes, modes/ownership, before/after hashes, the pinned revision,
   and the existing runtime snapshot in a unique rollback transaction directory.
3. Stop RackMarshal timers, then their service targets and loaded RackMarshal
   services, excluding the tunnel. Inactive timer targets are included to close
   the snapshot-to-stop race. Existing in-flight oneshot jobs may be interrupted;
   their timers resume after qualification instead of manually replaying jobs.
4. Atomically replace only changed files in both installations; preserve existing
   ownership/mode, clear affected bytecode caches, and verify selected SHA-256s
   in both roots. The database and authoritative lifecycle records are untouched.
5. Start status/MCP, wait boundedly for listeners and configured readiness URLs,
   then execute the pinned HTTP proof and full MCP protocol/tool acceptance.
   MCP GET 405/406 is only listener readiness; the following protocol evaluation
   must still pass. Each acceptance runner has a 180-second limit.
6. Restore only timers/long-running units previously active, without changing
   enablement. Mark the transaction `ACCEPTED` and print its path and revision.

Application services and timers stay quiesced while files are being replaced;
atomicity is per file. Successful readiness/acceptance is the transaction gate.
Allow several minutes for acceptance and rollback rather than treating the
service-start command itself as proof of readiness.

## Failure, interruption, and rollback

Copy, hash, readiness, and acceptance failures trigger restoration of original
files in both installations, followed by old-service readiness and restoration
of previously active timers. The command still exits unsuccessfully and records
`ROLLED_BACK`, preserving the original failure and proof logs.

If rollback encounters a checksum conflict, corrupted backup, or service failure,
the transaction records `ROLLBACK_FAILED` and does not deliberately resume the
remaining timer workload. Inspect the journal and fix the concrete blocker;
do not overwrite unrelated later file changes or start timers blindly.

A killed/interrupted process can leave `PREPARED`, `APPLYING`, or `INSTALLED`.
The saved journal and originals support explicit recovery:

```sh
python3 /path/to/promote-package-files.py rollback \
  --transaction /var/lib/rackmarshal/deployment-backups/TRANSACTION_DIRECTORY \
  --ready-url http://127.0.0.1:8080/readyz
```

Rollback checks that the configured interpreters resolve to the journal's
installation roots, rejects unexpected current bytes, verifies original hashes,
and restores code and runtime. It does not undo observations, recoveries, or
notifications already recorded by normal RackMarshal processing. Explicit
rollback certifies original source hashes and service readiness; it does not
rerun historical acceptance against changed production data.

## Evidence and current qualification

Keep the transaction journal, `http-proof.json`, `mcp-proof.json`, and the two
acceptance logs with the deployment record. The existing runners normally store
metadata rather than raw payloads. Failure logs are operator diagnostics; review
before sharing. Transaction directories are private to the invoking operator.

The initial procedure is qualified against disposable package roots, including
partial-copy and acceptance/readiness failures, absent original files, hash/path
rejection, runtime ordering, no-op behavior, and conflicting later changes.
The existing production source is inspected with `plan` and the bundled runners
are exercised read-only. No unchanged source is redeployed to exercise this tool.
Actual systemd stop/start and mutation remain unexercised in production until the
next independently qualified code patch is ready for promotion.


### Qualification snapshot — 2026-09-30

- Staging Python 3.13: 134 tests pass, publication gate PASS, zero ResourceWarnings.
- CT 110 Python 3.11: 134 tests run, 133 pass, one staging-only Git preparation test skipped, zero ResourceWarnings. No Git installation is required on the target.
- Thirteen new regressions cover the transaction and real disposable installations.
- Read-only production plan compares api/v1.py from commit 28534ba293a4aece9b67410c797aaae03a2d1008 against both installed packages: zero differences.
- Existing service snapshot covers 26 units; readiness passes. No stop/start was invoked.
- Pinned acceptance scripts executed from the prepared bundle: 37 HTTP checks and 18/18 MCP cases pass at approximately 11:21 AM EDT.
- Qualification metadata and script/test SHA-256s are in evals/results/package-promotion-qualification-20260930.json; HTTP/MCP proof artifacts accompany it.
- No production source was copied, no dependency installed, and no production rollback or maintenance stop/start was performed in this qualification. Those remain the next real deployment's validation boundary.


### First production use — 2026-09-30

The collection-coverage UI patch was promoted from source d219b51b6d5ac62fc062a9a0b2e45d914b44f41e. Plan review exposed missing shared UI modules in the older MCP installation, so ui/__init__.py and ui/narrative.py were explicitly included with api/status.py, ui/dashboard.py, and ui/incidents.py before application. Existing unchanged modules were skipped; eight package files changed.

Transaction /var/lib/rackmarshal/deployment-backups/d219b51b6d5a-9hvaylv0 is ACCEPTED. Both installation hashes, bounded readiness, 45 pinned HTTP checks, and 18/18 MCP cases passed. All 12 previously active timers were restored, application services and tunnel are active, and a separate LAN proof passed for dashboard/detail security and collection coverage. Actual production stop/start, replacement, and restoration are now exercised; failure/rollback paths remain qualified through disposable regressions rather than deliberately inducing production failure. The acceptance journal and originals remain available for explicit code rollback.
