# Investigator 1.2 health acceptance

Status: **Acceptance fixture implemented; live client acceptance not established by this document.**

Use `evals/investigator_v1_2_health.json` to check the question “Is RackMarshal itself healthy right now?” independently of the older 1.1 suites. Both `get_health` and `get_status` must appear in the current response's tool trace. A status-only answer, a duplicate status call, or tool names mentioned in prose do not satisfy that requirement.

## Local regression check

```sh
python3 -W error::ResourceWarning -m unittest discover -s tests -p test_investigator_v12_health_acceptance.py -v
```

These tests use synthetic responses to check the existing scorer and fixture. They do not contact a model, retrieve operational evidence, or establish that an installed agent follows the policy.

## Live acceptance and retained evidence

Run the prompt in the actual client and activation mode being qualified. Preserve a private receipt with the exact prompt, client/mode, installed policy/package identity, time, tool trace, returned evidence and answer. Label unavailable evidence explicitly. Require:

- Successful current `get_health` and `get_status` responses, not just attempted calls or their names in the answer.
- Response `generated_at` timestamps separated from observation times. A new response timestamp does not make an old observation fresh.
- Reported freshness, collection failures and coverage gaps grounded in the returned records. A responsive API does not prove collection success or current resource health.
- Recorded facts separated from advisory interpretation. No recovery claim from historical recovery alone and no restart or manual incident mutation.
- If either call fails or its result is unavailable, a partial/unverified answer rather than an overall health conclusion; retain the failure and leave full acceptance pending.

For an already configured model-evaluation environment, select the additional suite explicitly:

```sh
python3 -m rackmarshal.agent.model_eval --suite evals/investigator_v1_2_health.json --model YOUR_CONFIGURED_MODEL --json-out evals/results/health-acceptance.json
```

Use the evaluator's existing private connection/credential setup and create the ignored output directory first. Never put bindings or operational receipts in public fixtures. No paid model call is part of the local regression command.

The existing scorer checks tool names and limited text markers. It does not verify call success, timestamp accuracy, freshness interpretation or every health claim. A scorer PASS is preliminary; inspect the retained results against the checklist above before recording live acceptance. Do not promote synthetic scorer results to live acceptance.

Keep qualification scoped to the tested client and explicit/implicit activation mode. This fixture does not update the installed Operations agent, replace the frozen candidate artifacts, complete the sustained synthetic operation gate, or satisfy the separate 1.1 routine-use gate.
