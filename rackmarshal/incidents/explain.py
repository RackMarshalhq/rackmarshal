#!/usr/bin/env python3

import json
import sys
import urllib.error
import urllib.request

from rackmarshal.core.config import (
    load_config,
    require,
)


SCHEMA_VERSION = 1
EXPLAINER = "qwen_incident_explainer"

ALLOWED_INCIDENT_TYPES = {
    "STATUS-CHANGED",
    "MISSING",
    "NEW",
}

ALLOWED_BASELINE_STATES = {
    "VERIFIED",
    "EXPECTED",
    "KNOWN-ISSUE",
    "FAILED",
    "DECOMMISSIONED",
}

RESOURCE_LABELS = {
    "qemu": "QEMU VM",
    "lxc": "LXC container",
    "node": "Proxmox node",
    "storage": "Proxmox storage",
    "network": "Proxmox network resource",
    "zfs_pool": "ZFS pool",
    "zfs_vdev": "ZFS vdev",
    "backup_job": "backup job",
    "backup_guest": "protected backup guest",
    "backup_scheduled_run": "scheduled backup run",
    "ha_api": "Home Assistant API",
    "ha_core": "Home Assistant Core",
}


class ExplainError(Exception):
    pass


def load_packet():
    try:
        packet = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        raise ExplainError(
            f"invalid input JSON: {exc}"
        ) from exc

    if not isinstance(packet, dict):
        raise ExplainError(
            "input must be a JSON object"
        )

    # CLI convenience: full notification packet → inner incident
    if (
        "incident" in packet
        and isinstance(packet.get("incident"), dict)
        and "resource_type" not in packet
    ):
        packet = packet["incident"]

    return packet


def require_string(packet, key):
    value = packet.get(key)

    if not isinstance(value, str) or not value.strip():
        raise ExplainError(
            f"{key} must be a non-empty string"
        )

    return value.strip()


def validate_packet(packet):
    resource_type = require_string(
        packet,
        "resource_type",
    )

    resource_key = require_string(
        packet,
        "resource_key",
    )

    display_name = require_string(
        packet,
        "display_name",
    )

    incident_type = require_string(
        packet,
        "incident_type",
    )

    if incident_type not in ALLOWED_INCIDENT_TYPES:
        raise ExplainError(
            f"unsupported incident_type: {incident_type}"
        )

    baseline_state = packet.get(
        "baseline_state"
    )

    if baseline_state is not None:
        if baseline_state not in ALLOWED_BASELINE_STATES:
            raise ExplainError(
                f"unsupported baseline_state: {baseline_state}"
            )

    expected_status = packet.get(
        "expected_status"
    )

    actual_status = packet.get(
        "actual_status"
    )

    if expected_status is not None \
            and not isinstance(expected_status, str):
        raise ExplainError(
            "expected_status must be string or null"
        )

    if actual_status is not None \
            and not isinstance(actual_status, str):
        raise ExplainError(
            "actual_status must be string or null"
        )

    occurrence_count = packet.get(
        "occurrence_count",
        1,
    )

    if (
        not isinstance(occurrence_count, int)
        or isinstance(occurrence_count, bool)
        or occurrence_count < 1
    ):
        raise ExplainError(
            "occurrence_count must be a positive integer"
        )

    validated = {
        "resource_type": resource_type,
        "resource_key": resource_key,
        "display_name": display_name,
        "incident_type": incident_type,
        "baseline_state": baseline_state,
        "expected_status": expected_status,
        "actual_status": actual_status,
        "occurrence_count": occurrence_count,
    }

    for key in (
        "opened_at",
        "last_abnormal_at",
        "note",
    ):
        value = packet.get(key)

        if value is not None:
            if not isinstance(value, str):
                raise ExplainError(
                    f"{key} must be string or null"
                )

            validated[key] = value

    return validated


def resource_label(packet):
    resource_type = packet["resource_type"]

    return RESOURCE_LABELS.get(
        resource_type,
        f"resource type {resource_type}",
    )


def observation_scope(packet):
    resource_type = packet["resource_type"]

    if resource_type in {
        "qemu",
        "lxc",
        "node",
        "storage",
        "network",
    }:
        return "Proxmox resource observation"

    if resource_type in {
        "zfs_pool",
        "zfs_vdev",
    }:
        return "ZFS observation"

    if resource_type in {
        "backup_job",
        "backup_guest",
        "backup_scheduled_run",
    }:
        return "backup-domain observation"

    if resource_type in {
        "ha_api",
        "ha_core",
    }:
        return "Home Assistant observation"

    return "resource observation"


def deterministic_summary(packet):
    label = resource_label(packet)
    key = packet["resource_key"]
    name = packet["display_name"]
    incident_type = packet["incident_type"]
    expected = packet["expected_status"]
    actual = packet["actual_status"]

    identity = f"{label} {key} ({name})"

    if incident_type == "STATUS-CHANGED":
        if expected is not None and actual is not None:
            return (
                f"{identity} changed status from "
                f"{expected} to {actual}."
            )

        if actual is not None:
            return (
                f"{identity} has unexpected status "
                f"{actual}."
            )

        return (
            f"{identity} has a status change."
        )

    if incident_type == "MISSING":
        return (
            f"{identity} is missing from the current "
            f"{observation_scope(packet)}."
        )

    if incident_type == "NEW":
        if actual is not None:
            return (
                f"{identity} is new relative to the "
                f"authoritative baseline and currently "
                f"reports status {actual}."
            )

        return (
            f"{identity} is new relative to the "
            f"authoritative baseline."
        )

    raise ExplainError(
        f"cannot summarize incident type: {incident_type}"
    )


def build_prompt(packet, fact_summary):
    incident_json = json.dumps(
        packet,
        ensure_ascii=False,
        sort_keys=True,
    )

    label = resource_label(packet)

    return f"""
You are the advisory explanation layer for a private
RackMarshal monitoring system.

A deterministic monitoring engine has already established
the facts.

AUTHORITATIVE FACT:
{fact_summary}

AUTHORITATIVE RESOURCE CLASS:
{label}

You MUST obey these rules:

1. Treat the AUTHORITATIVE FACT and INCIDENT DATA as facts.
2. Never change the resource class.
3. A QEMU VM is a VM. Do not call it a service,
   container, host, application, or physical machine.
4. An LXC container is a container. Do not call it a VM.
5. Do not invent observations, logs, errors, causes,
   timestamps, configuration changes, or symptoms.
6. Clearly distinguish possible causes from confirmed facts.
7. Never state a possible cause as though it is confirmed.
8. Do not claim you inspected logs, configuration, the host,
   VM, container, network, database, or filesystem.
9. Do not issue shell commands.
10. Do not recommend automatic remediation.
11. Recommended checks must be investigation steps only.
12. Return valid JSON only.
13. Do not use Markdown fences.

Do NOT return a summary. The deterministic program creates
the factual summary itself.

Return exactly this JSON structure:

{{
  "impact": "likely operational impact based only on supplied facts",
  "possible_causes": [
    "possible cause 1",
    "possible cause 2"
  ],
  "recommended_checks": [
    "safe read-only investigation step 1",
    "safe read-only investigation step 2"
  ],
  "confidence": "low|medium|high"
}}

INCIDENT DATA:
{incident_json}
""".strip()


def call_ollama(prompt):
    config = load_config()
    ollama_url = require(config, "OLLAMA_URL")
    model = require(config, "OLLAMA_MODEL")
    request_body = {
        "model": model,
        "stream": False,
        "think": False,
        "format": "json",
        "options": {
            "temperature": 0,
        },
        "prompt": prompt,
    }

    encoded = json.dumps(
        request_body
    ).encode("utf-8")

    request = urllib.request.Request(
        ollama_url,
        data=encoded,
        headers={
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=120,
        ) as response:
            raw = response.read().decode(
                "utf-8"
            )

    except (
        urllib.error.URLError,
        TimeoutError,
    ) as exc:
        raise ExplainError(
            f"Ollama request failed: {exc}"
        ) from exc

    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ExplainError(
            "Ollama returned invalid envelope JSON"
        ) from exc

    if envelope.get("model") != model:
        raise ExplainError(
            "Ollama returned unexpected model"
        )

    if envelope.get("done") is not True:
        raise ExplainError(
            "Ollama did not report completion"
        )

    response_text = envelope.get("response")
    thinking_text = envelope.get("thinking")

    # qwen3 / thinking models: with think=false, response is preferred.
    # If response is empty, fall back to extracting a JSON object from thinking.
    if not isinstance(response_text, str):
        response_text = ""
    if not isinstance(thinking_text, str):
        thinking_text = ""

    candidate = response_text.strip()
    if not candidate and thinking_text.strip():
        candidate = _extract_json_object(thinking_text)
        if not candidate:
            raise ExplainError(
                "Ollama response empty and thinking had no JSON object "
                "(qwen3 think-mode quirk)"
            )
    elif not candidate:
        raise ExplainError(
            "Ollama response field is empty"
        )

    try:
        explanation = json.loads(candidate)
    except json.JSONDecodeError as exc:
        # Last resort: scrape JSON object from mixed prose+json
        scraped = _extract_json_object(candidate)
        if not scraped:
            raise ExplainError(
                "model response is not valid JSON"
            ) from exc
        try:
            explanation = json.loads(scraped)
        except json.JSONDecodeError as exc2:
            raise ExplainError(
                "model response is not valid JSON"
            ) from exc2

    return explanation


def _extract_json_object(text):
    """Return first top-level {...} substring, or empty string."""
    start = text.find("{")
    if start < 0:
        return ""
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return ""


def validate_advisory(explanation):
    if not isinstance(explanation, dict):
        raise ExplainError(
            "model explanation must be a JSON object"
        )

    expected_keys = {
        "impact",
        "possible_causes",
        "recommended_checks",
        "confidence",
    }

    if set(explanation) != expected_keys:
        raise ExplainError(
            "model explanation has unexpected fields"
        )

    impact = explanation["impact"]

    if not isinstance(impact, str) or not impact.strip():
        raise ExplainError(
            "impact must be a non-empty string"
        )

    for key in (
        "possible_causes",
        "recommended_checks",
    ):
        value = explanation[key]

        if not isinstance(value, list) or not value:
            raise ExplainError(
                f"{key} must be a non-empty array"
            )

        if not all(
            isinstance(item, str)
            and item.strip()
            for item in value
        ):
            raise ExplainError(
                f"{key} must contain non-empty strings"
            )

    if explanation["confidence"] not in {
        "low",
        "medium",
        "high",
    }:
        raise ExplainError(
            "confidence must be low, medium, or high"
        )

    return explanation


def main():
    try:
        packet = validate_packet(
            load_packet()
        )

        fact_summary = deterministic_summary(
            packet
        )

        advisory = validate_advisory(
            call_ollama(
                build_prompt(
                    packet,
                    fact_summary,
                )
            )
        )

        explanation = {
            "summary": fact_summary,
            "impact": advisory["impact"],
            "possible_causes":
                advisory["possible_causes"],
            "recommended_checks":
                advisory["recommended_checks"],
            "confidence":
                advisory["confidence"],
        }

        output = {
            "schema_version": SCHEMA_VERSION,
            "explainer": EXPLAINER,
            "status": "complete",
            "model": require(load_config(), "OLLAMA_MODEL"),
            "incident": packet,
            "explanation": explanation,
        }

        print(
            json.dumps(
                output,
                indent=2,
                ensure_ascii=False,
            )
        )

        return 0

    except ExplainError as exc:
        print(
            json.dumps(
                {
                    "schema_version":
                        SCHEMA_VERSION,
                    "explainer":
                        EXPLAINER,
                    "status":
                        "failed",
                    "error":
                        str(exc),
                },
                indent=2,
            ),
            file=sys.stderr,
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(main())
