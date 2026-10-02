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

