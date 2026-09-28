# Contributing to RackMarshal

RackMarshal is being prepared for broader open-source use. Contributions should preserve its local-first, evidence-based operating model and avoid embedding assumptions from any one infrastructure site.

## Before submitting a change

- keep production credentials and private infrastructure details out of the repository
- do not introduce hard-coded hostnames, addresses, usernames, VM IDs, storage paths, or dataset names
- put site-specific behavior behind explicit configuration
- preserve database migration history; add a new migration instead of rewriting an applied one
- keep collectors read-only unless a future capability explicitly documents otherwise
- update documentation when behavior or configuration changes

## Development checks

At minimum, Python changes should compile cleanly and relevant smoke/installation tests should pass. Packaging changes should be tested from built artifacts rather than only from the source tree.

Changes affecting installation, migrations, systemd units, configuration preservation, upgrade, or uninstall behavior should be validated on a disposable clean host.

## Publication safety

Before release, the intended public tree and built artifacts are scanned for private addresses, personal/site names, legacy project identifiers, site storage paths, private-key material, likely credential assignments, databases, and prohibited secret-bearing file types.

A passing pattern scan reduces accidental disclosure risk but is not a substitute for code review.

## License

By contributing, you agree that your contribution may be distributed under the project's Apache License 2.0.
