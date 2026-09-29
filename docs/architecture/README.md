# RackMarshal Architecture

This directory contains the frozen architecture baseline for RackMarshal's API, MCP, and agent integration work.

## Documents

- [Core Principles](CORE_PRINCIPLES.md)
- [API Architecture](API_ARCHITECTURE.md)
- [API v1 Schema](API_V1_SCHEMA.md)
- [Agent Architecture](AGENT_ARCHITECTURE.md)
- [Agent Contract](AGENT_CONTRACT.md)
- [MCP Architecture](MCP_ARCHITECTURE.md)
- [Security Model](SECURITY_MODEL.md)
- [Roadmap](ROADMAP.md)
- [Source of Truth](SOURCE_OF_TRUTH.md)

## Status semantics

**FROZEN** means implementation should conform to the documented contract unless an explicit architecture revision is made.

**DESIGN BASELINE** means the direction is adopted but implementation details may evolve without violating the core principles.

The architecture is intentionally provider-neutral. OpenAI/ChatGPT/Codex may be first-class clients, but RackMarshal Core must remain fully functional without them.
