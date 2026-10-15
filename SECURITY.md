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

Report vulnerabilities through GitHub Private Vulnerability Reporting for the RackMarshal repository. Do not post credentials, exploit details affecting a live installation, private infrastructure data, or other sensitive material in a public issue.
# Outbound HTTP destinations

Development follow-up to frozen 1.2.0rc5: Python HTTP clients accept explicit
HTTP(S) endpoints and reject URL user information, malformed destinations and
control characters. Redirects must retain the original scheme, host and
effective port; redirects to another origin, including HTTPS downgrades, fail
before forwarding the request. Configure the intended endpoint directly when a
service moves. Same-origin redirects retain standard urllib method behavior.

Private and loopback endpoints remain supported for self-hosted operation.
Configuration and proxy settings are trusted operator inputs; this is not a
network sandbox or DNS-rebinding defense. Use HTTPS for credentials outside an
appropriately protected local environment. Custom certificate verification
contexts and configured proxies remain in effect.

Standalone readiness and narrative acceptance scripts reject all redirects:
another URL's response cannot establish the selected endpoint's acceptance.
Acceptance evaluators that use assertions reject optimized Python execution
(`-O`, `-OO`, or `PYTHONOPTIMIZE`) rather than emit a receipt with checks removed.

These changes are local development, not a patch to qualified RC5 artifacts.
The original exact-artifact qualification does not cover these changed bytes.

## Offline bootstrap trust boundary

The private rc6.dev1 installer bundles the unmodified official pip 26.2.1 wheel, pinned by SHA-256 in its standard-library bootstrap. Root-owned inputs must have safe ancestors, no symlinks/hardlinks or group/world writes. Wheel structure and identity are checked before isolated execution in a fresh pip-less venv. Installed payload bytes, site-packages inventory and generated RECORD hashes are verified. Existing environments are refused because Python startup hooks could execute before pip. Runtime files remain root-owned and readable, but not writable, by the service group.

The release privacy gate permits the bundled public CA certificate file only when the complete pip wheel hash, exact member path and member hash match. Upstream license/author/example text exceptions likewise bind complete wheel and member hashes; secret and path checks still apply. See THIRD-PARTY-NOTICES.txt and packaging/bootstrap/manifest.json for retained licenses and provenance.
