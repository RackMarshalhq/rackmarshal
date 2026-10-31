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

## Retiring the baseline of a deleted guest

When you delete a guest in Proxmox its baseline row stays, and RackMarshal reports the guest as MISSING until the row is removed. `scripts/retire-pve-baseline.py` removes those rows. It is the mirror image of the adoption tool and follows the same rules: it plans first and writes nothing without `--apply`; apply needs root, an approval note, a private backup directory and a fresh PVE observation (under 900 seconds, verified TLS) given by ID.

Every named guest (`--resource lxc:<id>` or `qemu:<id>`, repeated) must have a baseline row and must be **absent** from that observation. A guest that still exists is refused, so the tool cannot be used to stop watching a live guest. Only `resource_baseline` rows are deleted, in one transaction after a consistent database copy; incidents, events and observations are never changed. At the next Proxmox cycle the MISSING incident recovers by itself.

```text
sudo python3 -I -B retire-pve-baseline.py --db /var/lib/rackmarshal/state.db --observation-id N --resource lxc:123 --approval-note "why" --backup-dir /root/baseline-backups          # plan only
```

Add `--apply` after reading the plan. To undo, restore the database copy the tool printed, or insert the rows again with the adoption tool while the guest exists.
