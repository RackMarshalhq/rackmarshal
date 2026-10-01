"""Bounded read-only Investigator connection qualification; never prints evidence."""
import asyncio
import ipaddress
from urllib.parse import urlsplit

EXPECTED_TOOLS = frozenset(("get_health", "get_status", "list_incidents", "get_incident",
    "get_recent_changes", "get_domain_status", "get_backup_status", "get_evidence",
    "get_recovery_history", "get_incident_timeline", "get_incident_evidence_bundle"))

def validate_url(url):
    parts = urlsplit(url)
    if parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("Use an endpoint without credentials, query or fragment.")
    try:
        loopback = parts.hostname == "localhost" or ipaddress.ip_address(parts.hostname).is_loopback
    except ValueError:
        loopback = False
    if not parts.hostname or parts.scheme not in ("http", "https") or (parts.scheme == "http" and not loopback):
        raise ValueError("Use loopback HTTP or an HTTPS endpoint.")
    if parts.path != "/mcp":
        raise ValueError("The endpoint path must be /mcp.")
    # Also validates malformed ports without including the supplied URL in output.
    parts.port
    return url

def inspect_tools(tools):
    if {t.name for t in tools} != EXPECTED_TOOLS:
        return False
    return all(t.annotations and t.annotations.readOnlyHint is True
        and t.annotations.destructiveHint is False
        and t.annotations.openWorldHint is False for t in tools)

async def _check(url):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    async with streamable_http_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            if not inspect_tools(tools):
                return {"result": "FAIL", "reason": "TOOL_CONTRACT_MISMATCH"}
            health = await session.call_tool("get_health", {})
            if health.isError:
                return {"result": "FAIL", "reason": "HEALTH_TOOL_ERROR"}
            import json
            payload = json.loads("".join(x.text for x in health.content if hasattr(x, "text")))
            if payload.get("api_version") != "v1" or not isinstance(payload.get("data"), dict):
                return {"result": "FAIL", "reason": "HEALTH_CONTRACT_MISMATCH"}
            return {"result": "PASS", "tool_count": len(tools),
                    "limitations": ["Connection and read-only tool contract verified.",
                        "Health evidence was read but resource health, recovery and client activation are not established."]}

def connection_check(url="http://127.0.0.1:8000/mcp"):
    try:
        validate_url(url)
    except (ValueError, TypeError):
        return {"result": "FAIL", "reason": "INVALID_ENDPOINT"}
    try:
        return asyncio.run(asyncio.wait_for(_check(url), timeout=10))
    except ImportError:
        return {"result": "FAIL", "reason": "MCP_DEPENDENCY_MISSING"}
    except Exception:
        # Avoid leaking URLs, authentication headers, response bodies or exception details.
        return {"result": "FAIL", "reason": "CONNECTION_OR_PROTOCOL_ERROR"}
