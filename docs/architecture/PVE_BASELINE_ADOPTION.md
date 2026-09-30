# Scoped PVE baseline adoption

This is operator administration under explicit user approval, not an Investigator
or MCP write capability. The incident UI and eleven-tool MCP contract stay read-only.

scripts/adopt-pve-baseline.py plans or applies explicitly selected lxc/qemu
identities from one pinned stored PVE observation. It requires a nonempty approval
note, timezone-qualified observation within 900 seconds, known running/stopped
states, unique resource scope and no existing selected baseline. It refuses
updates to existing baselines. The approved states are copied as expected_status,
VERIFIED denotes accepted baseline state, and source_observation/note retain
provenance. Unselected baselines are preserved.

Apply requires root and an existing private backup parent. The tool validates,
creates a consistent SQLite backup (private directory/file), revalidates within
BEGIN IMMEDIATE, inserts the whole batch and commits atomically. Errors roll
back every baseline insert. Plan opens the database read-only and does not write.
Do not feed it a guessed observation ID or use it to overwrite existing policy.

Operator sequence: obtain fresh observation identity through read-only MCP;
review the plan; qualify fixtures on staging/target Python; select the committed
script blob and verify its checksum; stop the PVE timer and wait for in-flight
work; apply only the authorized scope with approval note/backup parent; restore
prior timer state. Then normal collection/comparison/processing must provide
independent lifecycle evidence. No incident updates are part of this tool.

Baseline rollback is scoped policy rollback: after quiescing the PVE timer,
remove only the newly inserted rows if they still match the receipt exactly,
then restore the timer and collect normally. Do not restore the entire database
merely to undo eight baseline entries: that would erase unrelated later evidence.
The private full snapshot is retained for recovery/reference, never committed or
returned to Investigator. Already recorded observations/recoveries stay history.

2026-09-30 authorized scope: keep LXC 117–124. Planned source
observation:PVE:11340 (16:58:32.889191 UTC), expected stopped for 117–123 and running
for 124. Existing 20 baseline entries are preserved; the batch adds eight.
The user’s direct request is retained in the approval note/Source of Truth.


## Retained PVE baseline and recorded recovery — September 30

The user explicitly approved keeping LXC 117–124 and creating a baseline. Operator source 26cb00c added eight VERIFIED entries atomically from observation:PVE:11340: 117–123 expected stopped, 124 expected running. The existing 20 entries and all guest states were preserved. Consistent private backup: /var/lib/rackmarshal/deployment-backups/pve-baseline-3edeeage. Investigator remains read-only.

Normal processing independently recovered PVE:36–PVE:43 at 17:05:44.344970 UTC from observation:PVE:11345. Latest abnormal evidence remains observation:PVE:11344; all eight retain 153 recorded occurrences and explicit legacy correlation provenance. These were NEW inventory conditions resolved by accepting intended policy, not guest faults repaired. No incident was manually closed.

Production proof: PVE OK, zero PVE incidents open, three phone BACKUP incidents open; HTTP 47 checks and Investigator 18/18 pass. Status, MCP, tunnel and PVE timer active. Qualification: 173 staging test executions pass; target 172 pass/one Git-only skip; zero ResourceWarnings. Planned phone backups remain Michael tonight September 30 and Olivia/Preston October 5, with ordinary evidence-based recovery required. Business workspace setup remains pending explicit instructions.
