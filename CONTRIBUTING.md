# Contributing to RackMarshal

RackMarshal is being prepared for broader open-source use. Contributions should preserve its local-first, evidence-based operating model and avoid embedding assumptions from any one infrastructure site.

## Before submitting a change

- keep production credentials and private infrastructure details out of the repository
- do not introduce hard-coded hostnames, addresses, usernames, VM IDs, storage paths, or dataset names
- put site-specific behavior behind explicit configuration
- preserve database migration history; add a new migration instead of rewriting an applied one
- keep collectors read-only unless a future capability explicitly documents otherwise
- update documentation when behavior or configuration changes

## Working in the open

All development happens on GitHub, from the first commit.

- Every branch is pushed to GitHub as soon as it has a commit, and has a pull request (a draft is fine) so CI runs on it. There are no private-only branches, bundles or patch files.
- Changes reach `main` through a pull request with passing CI. Do not commit directly to `main`.
- A release is made from a tagged commit that is on GitHub and whose CI passed. The release is created from CI as a draft, and a maintainer publishes it.
- Qualification and test evidence is recorded in the pull request or release it belongs to, with the commit it was run against.
- Private material (credentials, site topology, personal data) never goes in a branch, even a short-lived one. Keep it outside the repository.

To check that nothing lives only on your machine, run this in each working clone:

```sh
scripts/unpushed-check.sh --fetch
```

It lists local branches with commits no remote has, tags missing on origin, stashes (which are never pushed) and uncommitted changes. It exits non-zero if it finds any.

## Development checks

At minimum, Python changes should compile cleanly and relevant smoke/installation tests should pass. Packaging changes should be tested from built artifacts rather than only from the source tree.

Changes affecting installation, migrations, systemd units, configuration preservation, upgrade, or uninstall behavior should be validated on a disposable clean host.

The setup/coverage safety regressions can be run without collectors, credentials, or a live installation:

```sh
python3 -W error::ResourceWarning -m unittest discover -s tests -p 'test_setup*.py' -v
```

These cases cover all supported domain setup requirements, credential-content privacy, file readiness, disabled/unknown selection, and retained incident history under changing freshness labels. They use temporary files and in-memory databases. The full `./scripts/publication-gate.sh` also starts localhost HTTP fixture servers; allow local socket binding when running it in a sandbox. The script validates the tree and does not publish it.

Test results are development evidence. They do not replace the exact-artifact installation or sustained-operation gates in [release acceptance](docs/architecture/RELEASE_ACCEPTANCE.md), and do not expand the supported client or platform matrix.

## Publication safety

Before release, the intended public tree and built artifacts are scanned for private addresses, personal/site names, legacy project identifiers, site storage paths, private-key material, likely credential assignments, databases, and prohibited secret-bearing file types.

A passing pattern scan reduces accidental disclosure risk but is not a substitute for code review.

## License

By contributing, you agree that your contribution may be distributed under the project's Apache License 2.0.
