#!/usr/bin/env python3

import argparse
import datetime
import json
import sqlite3
import subprocess
import urllib.error
import urllib.request

from rackmarshal.core.config import (
    ha_credential_file,
    local_ai_attach_to_notify,
    local_ai_enabled,
)


SCHEMA_VERSION = 1
WORKER = "incident_notification_delivery_worker"


class DeliveryError(RuntimeError):
    pass


def utc_now():
    return (
        datetime.datetime.now(datetime.timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def load_ha_credentials(path):
    command = r'''
set -a
. "$1"
printf '%s\0%s' "$HA_URL" "$HA_TOKEN"
'''

    result = subprocess.run(
        ["bash", "-c", command, "_", path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if result.returncode != 0:
        raise DeliveryError(
            "unable to load Home Assistant credential"
        )

    parts = result.stdout.split(b"\0", 1)

    if len(parts) != 2:
        raise DeliveryError(
            "invalid Home Assistant credential output"
        )

    url = parts[0].decode("utf-8").strip().rstrip("/")
    token = parts[1].decode("utf-8").strip()

    if not url or not token:
        raise DeliveryError(
            "Home Assistant URL/token missing"
        )

    return url, token


def deterministic_opened(packet):
    incident = packet["incident"]

    name = (
        incident.get("display_name")
        or incident.get("resource_key")
        or "unknown resource"
    )

    incident_type = incident.get("incident_type")
    expected = incident.get("expected_status")
    actual = incident.get("actual_status")
    count = incident.get("occurrence_count")

    lines = [
        f"Incident opened for {name}.",
        f"Type: {incident_type}.",
    ]

    if expected is not None:
        lines.append(f"Expected status: {expected}.")

    if actual is not None:
        lines.append(f"Observed status: {actual}.")

    if count is not None:
        lines.append(f"Occurrence count: {count}.")

    return " ".join(lines)


def deterministic_recovery(packet):
    incident = packet["incident"]
    recovery = packet.get("recovery") or {}

    name = (
        incident.get("display_name")
        or incident.get("resource_key")
        or "unknown resource"
    )

    incident_type = incident.get("incident_type")
    count = incident.get("occurrence_count")
    recovered_at = recovery.get("recovered_at")

    text = (
        f"{name} recovered from incident type "
        f"{incident_type}."
    )

    if count is not None:
        text += f" Abnormal observations: {count}."

    if recovered_at:
        text += f" Recovered at {recovered_at}."

    return text



def _parse_explanation_json(raw):
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    text = str(raw).strip()
    if not text:
        return None
    try:
        obj = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return None
    return obj if isinstance(obj, dict) else None


def _is_successful_ai(rec):
    if not isinstance(rec, dict):
        return False
    return (
        rec.get("mode") == "AI"
        and rec.get("explainer_succeeded") is True
        and isinstance(rec.get("explanation"), dict)
    )


def resolve_opened_explanation_and_message(row, facts):
    """Async worker fills AI; deliver never calls explain_incident.

    Local-AI 5.5: if LOCAL_AI_ATTACH_TO_NOTIFY and AI already present, decorate
    notify body; otherwise facts-only.
    """
    existing = _parse_explanation_json(row["explanation_json"])

    if _is_successful_ai(existing):
        explanation_record = existing
    elif isinstance(existing, dict) and existing.get("mode"):
        # Keep FALLBACK / DISABLED / PENDING_ASYNC / etc.
        explanation_record = existing
        if explanation_record.get("deterministic_summary") in (None, ""):
            explanation_record = dict(explanation_record)
            explanation_record["deterministic_summary"] = facts
    elif not local_ai_enabled():
        explanation_record = {
            "mode": "DISABLED",
            "explainer_succeeded": None,
            "deterministic_summary": facts,
        }
    else:
        explanation_record = {
            "mode": "PENDING_ASYNC",
            "explainer_succeeded": None,
            "deterministic_summary": facts,
        }

    message = facts
    if local_ai_attach_to_notify() and _is_successful_ai(explanation_record):
        message = build_ai_message(
            facts,
            explanation_record["explanation"],
        )

    return explanation_record, message


def run_explainer(explainer, incident, timeout_seconds=20):
    payload = json.dumps(
        incident,
        separators=(",", ":"),
        sort_keys=True,
    )

    try:
        result = subprocess.run(
            [explainer],
            input=payload,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise DeliveryError(
            f"explainer timed out after {timeout_seconds}s"
        ) from exc

    if result.returncode != 0:
        message = (
            result.stderr.strip()
            or result.stdout.strip()
            or f"explainer exited {result.returncode}"
        )
        raise DeliveryError(message)

    try:
        explanation = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise DeliveryError(
            f"explainer returned invalid JSON: {exc}"
        ) from exc

    if not isinstance(explanation, dict):
        raise DeliveryError(
            "explainer output is not a JSON object"
        )

    return explanation


def build_ai_message(facts, explanation):
    """Build notify body from facts + explainer output (nested or flat)."""
    if not isinstance(explanation, dict):
        return facts

    # explain_incident stdout nests fields under "explanation"
    advisory = explanation.get("explanation")
    if not isinstance(advisory, dict):
        advisory = explanation.get("advisory")
    if not isinstance(advisory, dict):
        advisory = explanation

    summary = (
        advisory.get("summary")
        or explanation.get("summary")
        or explanation.get("deterministic_summary")
    )

    parts = [facts]

    if isinstance(summary, str) and summary.strip():
        if summary.strip() != facts.strip():
            parts.append(summary.strip())

    impact = advisory.get("impact")
    causes = advisory.get("possible_causes")
    checks = advisory.get("recommended_checks")
    confidence = advisory.get("confidence")

    if isinstance(impact, str) and impact.strip():
        parts.append("Impact: " + impact.strip())

    if isinstance(causes, list) and causes:
        parts.append(
            "Possible causes: "
            + "; ".join(str(x) for x in causes)
        )

    if isinstance(checks, list) and checks:
        parts.append(
            "Recommended checks: "
            + "; ".join(str(x) for x in checks)
        )

    if isinstance(confidence, str) and confidence.strip():
        parts.append(
            "Advisory confidence: "
            + confidence.strip()
            + " (explain-only, not authoritative)"
        )

    return "\n\n".join(parts)


def send_ha(
    base_url,
    token,
    notification_id,
    title,
    message,
):
    url = (
        base_url
        + "/api/services/persistent_notification/create"
    )

    payload = {
        "title": title,
        "message": message,
        "notification_id": notification_id,
    }

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=10,
        ) as response:
            response.read()
            status = response.status

    except urllib.error.HTTPError as exc:
        body = exc.read().decode(
            "utf-8",
            errors="replace",
        )
        raise DeliveryError(
            f"Home Assistant HTTP {exc.code}: "
            f"{body[:300]}"
        ) from exc

    except Exception as exc:
        raise DeliveryError(
            f"Home Assistant delivery failed: "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    if status != 200:
        raise DeliveryError(
            f"Home Assistant returned HTTP {status}"
        )


def validate_packet(packet, row):
    if not isinstance(packet, dict):
        raise DeliveryError(
            "packet_json is not a JSON object"
        )

    if packet.get("schema_version") != 1:
        raise DeliveryError(
            "unexpected packet schema version"
        )

    if (
        packet.get("builder")
        != "incident_notification_packet"
    ):
        raise DeliveryError(
            "unexpected packet builder identity"
        )

    if packet.get("source_domain") != row["source_domain"]:
        raise DeliveryError(
            "packet source domain mismatch"
        )

    if packet.get("incident_id") != row["incident_id"]:
        raise DeliveryError(
            "packet incident id mismatch"
        )

    if (
        packet.get("notification_type")
        != row["notification_type"]
    ):
        raise DeliveryError(
            "packet notification type mismatch"
        )

    incident = packet.get("incident")

    if not isinstance(incident, dict):
        raise DeliveryError(
            "packet incident object missing"
        )


def deliver_one(
    conn,
    row,
    base_url,
    token,
    explainer,
    notification_prefix,
):
    now = utc_now()

    conn.execute(
        """
        UPDATE incident_notifications
        SET
            attempt_count = attempt_count + 1,
            last_attempt_at = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (now, now, row["id"]),
    )
    conn.commit()

    try:
        packet = json.loads(row["packet_json"])
        validate_packet(packet, row)

        incident = packet["incident"]

        explanation_record = None

        if row["notification_type"] == "OPENED":
            facts = deterministic_opened(packet)

            # Async worker (5.7) fills explanation_json; deliver never
            # subprocesses explain_incident. 5.5 may attach AI text when
            # LOCAL_AI_ATTACH_TO_NOTIFY and AI is already present.
            # --explainer CLI flag is ignored for OPENED AI (compat only).
            explanation_record, message = (
                resolve_opened_explanation_and_message(row, facts)
            )

            title = (
                "RackMarshal Incident OPENED "
                f"[{row['source_domain']}]"
            )

        elif row["notification_type"] == "RECOVERED":
            message = deterministic_recovery(packet)

            explanation_record = {
                "mode": "RECOVERY_DETERMINISTIC",
                "explainer_succeeded": None,
            }

            title = (
                "RackMarshal Incident RECOVERED "
                f"[{row['source_domain']}]"
            )

        else:
            raise DeliveryError(
                "unsupported notification type"
            )

        notification_id = (
            f"{notification_prefix}_"
            f"{row['source_domain'].lower()}_"
            f"{row['incident_id']}_"
            f"{row['notification_type'].lower()}_"
            f"{row['id']}"
        )

        send_ha(
            base_url,
            token,
            notification_id,
            title,
            message,
        )

        delivered_at = utc_now()

        # Preserve async AI if worker filled explanation_json after we read the row.
        conn.execute(
            """
            UPDATE incident_notifications
            SET
                delivery_state = 'SENT',
                explanation_json = CASE
                    WHEN explanation_json IS NOT NULL
                     AND length(trim(explanation_json)) > 2
                     AND json_extract(explanation_json, '$.mode') = 'AI'
                     AND json_extract(explanation_json, '$.explainer_succeeded') = 1
                    THEN explanation_json
                    ELSE ?
                END,
                delivered_at = ?,
                last_error = NULL,
                updated_at = ?
            WHERE id = ?
            """,
            (
                json.dumps(
                    explanation_record,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                delivered_at,
                delivered_at,
                row["id"],
            ),
        )
        conn.commit()

        return {
            "id": row["id"],
            "result": "SENT",
            "fallback": (
                explanation_record.get("mode")
                == "FALLBACK"
            ),
        }

    except Exception as exc:
        failed_at = utc_now()

        conn.execute(
            """
            UPDATE incident_notifications
            SET
                delivery_state = 'FAILED',
                delivered_at = NULL,
                last_error = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                str(exc),
                failed_at,
                row["id"],
            ),
        )
        conn.commit()

        return {
            "id": row["id"],
            "result": "FAILED",
            "error": str(exc),
        }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--db",
        required=True,
    )

    # Phase 3 Step 2: default credential path from config helper
    # (defaults = today's layout). Callers may still pass --credential.
    parser.add_argument(
        "--credential",
        default=str(ha_credential_file()),
    )

    parser.add_argument(
        "--explainer",
        required=True,
    )

    parser.add_argument(
        "--notification-prefix",
        default="rackmarshal",
    )

    parser.add_argument(
        "--only-id",
        type=int,
    )

    args = parser.parse_args()

    base_url, token = load_ha_credentials(
        args.credential
    )

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    try:
        sql = """
            SELECT *
            FROM incident_notifications
            WHERE delivery_state IN ('PENDING','FAILED')
        """

        params = []

        if args.only_id is not None:
            sql += " AND id = ?"
            params.append(args.only_id)

        sql += " ORDER BY id"

        rows = conn.execute(
            sql,
            params,
        ).fetchall()

        results = []

        for row in rows:
            results.append(
                deliver_one(
                    conn,
                    row,
                    base_url,
                    token,
                    args.explainer,
                    args.notification_prefix,
                )
            )

        sent = sum(
            1
            for item in results
            if item["result"] == "SENT"
        )

        failed = sum(
            1
            for item in results
            if item["result"] == "FAILED"
        )

        fallback = sum(
            1
            for item in results
            if item.get("fallback")
        )

        print(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "worker": WORKER,
                    "status": "OK",
                    "rows_scanned": len(rows),
                    "sent": sent,
                    "failed": failed,
                    "fallback_deliveries": fallback,
                    "results": results,
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        )

        return 0

    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
