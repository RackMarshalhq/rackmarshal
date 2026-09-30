# RackMarshal agent guidance

For operational investigation, use the `rackmarshal-investigator` skill and the RackMarshal MCP server. RackMarshal evidence is authoritative for recorded operational state; agent synthesis is ADVISORY.

Do not bypass the RackMarshal API/MCP boundary with SQLite, shell, filesystem, or host inspection when acting as the Investigator. Do not claim recovery without RackMarshal recovery evidence. Investigator v1 is read-only.
