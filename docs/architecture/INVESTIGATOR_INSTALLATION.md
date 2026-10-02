# Investigator installation and verification (1.2 candidate)

Core works without AI. Investigator is optional and read-only. A connection check does not establish resource health or recovery.

## Prepare the server

Install the exact candidate wheel using the installer. Install its optional MCP dependencies into the same environment:

```bash
sudo /opt/rackmarshal/venv/bin/pip install '/path/to/rackmarshal-1.2.0rc2-py3-none-any.whl[mcp]'
sudo RACKMARSHAL_CONFIG=/etc/rackmarshal/rackmarshal.conf /opt/rackmarshal/venv/bin/rackmarshal-mcp
```

The default MCP endpoint is loopback HTTP on port 8000. Keep it private. The local client must run on the same host or use a separately configured secure connection. Loopback on a desktop computer cannot reach a server on another computer. Do not expose an unauthenticated MCP endpoint publicly. The core installer does not start MCP automatically.

From another terminal on the server:

```bash
/opt/rackmarshal/venv/bin/rackmarshal investigator-check
```

This initializes MCP, verifies exactly eleven read-only/non-destructive/non-open-world tools, and reads get_health. It prints no operational payloads or endpoint values and writes no configuration. It has a ten-second bound. Exit 0 means the connection/contract passed; exit 2 identifies a dependency, endpoint, transport or contract failure. Resource state and recovery still require timestamped evidence. Only loopback HTTP or HTTPS endpoints without embedded credentials/query/fragment are accepted. Authentication must be provisioned separately.

## Local package

Build a deterministic marketplace ZIP from the exact source revision:

```bash
python3 scripts/build-investigator-plugin.py --surface local --output /path/to/local-plugin.zip
```

Extract it into a dedicated directory. It contains a marketplace and a plugin with the canonical policy, versioned manifest, and loopback MCP declaration. For a supported Codex CLI with plugin commands:

```bash
codex plugin marketplace add /path/to/extracted-marketplace
codex plugin add rackmarshal-investigator@rackmarshal-local
```

Verify the installed version and cached policy against the package. Explicitly select RackMarshal Investigator for operational requests. CLI installation and a direct MCP check are separate from an authenticated model conversation or desktop activation; do not infer those from installation success.

## Private hosted package

ChatGPT cloud needs an existing registered, authenticated RackMarshal connection. A local loopback MCP declaration cannot provide that connection.

```bash
python3 scripts/build-investigator-plugin.py --surface cloud --app-id YOUR_REGISTERED_APP_ID --output /private/location/hosted-plugin.zip
```

The builder requires a registered-ID format and an output outside the public repository, creates the archive with mode 0600, and refuses overwrites. It includes the existing app declaration, canonical policy plus explicit app binding, and a skill dependency. It includes no local MCP declaration. Import and install privately using the workspace plugin interface; confirm the connected app and bundled skill. Repeat an explicitly selected fresh conversation covering timestamped evidence, fact/advisory separation, restart/manual-closure refusal and unsupported-resource limitations. If disconnected, report the connection failure rather than using another infrastructure tool.

Never publish this archive, its binding, credentials, private receipts or operational records. Public releases contain only generic local packages and sanitized qualification summaries. No broader workspace distribution or permission expansion is implied.

## Qualification limits

Each version and client surface requires retained proof. The earlier private combined package was installed and accepted; that does not qualify a newly generated candidate package. Desktop activation, implicit selection, broader audience controls and other model clients require their own acceptance. Missing evidence stays PENDING.
