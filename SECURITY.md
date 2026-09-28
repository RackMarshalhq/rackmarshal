# RackMarshal Security

## Development status

RackMarshal is under active development. Treat the current development build as pre-release software and evaluate it in an environment appropriate for testing.

## Credential handling

RackMarshal integrations may require API tokens, SSH private keys, CA certificates, and Home Assistant credentials. Real credentials are site configuration and must not be committed to the RackMarshal source repository.

Use least-privilege API tokens and SSH accounts. Give collectors only the read access they require. Protect credential files with restrictive filesystem permissions.

Do not disable TLS certificate verification or SSH strict host-key checking merely to make an integration work.

## Service isolation

The reference installer runs RackMarshal services as the unprivileged `rackmarshal` account. Supplied systemd units use hardening controls including `NoNewPrivileges`, `ProtectSystem=strict`, `ProtectHome=true`, and explicit writable state/log paths.

The status API defaults to loopback (`127.0.0.1`). Do not expose it to an untrusted network without an intentional authentication/proxy/network-control design.

## Sensitive state

The SQLite state database contains operational history. Depending on configured collectors, that history can reveal infrastructure names, topology, incidents, and service state. Protect backups of the database accordingly.

## Reporting vulnerabilities

Until a dedicated private security-reporting channel is published, do not post credentials, exploit details affecting a live installation, private infrastructure data, or other sensitive material in a public issue. Use the repository's private security-reporting facility when available.
