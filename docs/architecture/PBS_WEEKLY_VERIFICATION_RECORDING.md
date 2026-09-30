# PBS verification task visibility

The optional packaging/observers/pbs-native-verify-cache helper queries PBS through Proxmox QGA. Configure your own VM identity, datastore, verification job, and cache output explicitly. The base installer does not install or schedule this helper.

Example (fictional values):

```bash
pbs-native-verify-cache --vmid 900 --datastore example-store --job example-weekly --output /var/lib/rackmarshal/pbs-verification.json
```

The helper searches up to 1000 tasks, matches exact verificationjob type and datastore:job worker identity, and uses the newest matching row in PBS task-list order. Individual snapshot verification is distinct from scheduled job completion. A failed or running newest job cannot borrow older success. No match means UNKNOWN within the bounded window, not proof of a failed job or exhaustive absence.

[Primary PBS CLI reference](https://pbs.proxmox.com/docs/proxmox-backup-manager/man1.html).

Validate site-specific QGA access and output-directory permissions before scheduling. Protect the resulting metadata according to site policy. The helper launches no verification job, changes no schedule, and cannot close incidents. Only ordinary collection/processing and separate recorded recovery evidence establish recovery.

For code rollback, retain the prior helper and permissions, quiesce its caller, wait for in-flight work, restore the prior artifact, and restore scheduling. Do not erase recorded operational history.
