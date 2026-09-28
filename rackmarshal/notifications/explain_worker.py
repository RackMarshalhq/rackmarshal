#!/usr/bin/env python3
"""Async Local-AI explainer worker for RackMarshal incident_notifications.

Fills explanation_json for OPENED rows that still need AI (null/empty,
PENDING_ASYNC, FALLBACK, or DISABLED). Never blocks deliver; never
overwrites a successful AI explanation.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rackmarshal.core.config import (
    load_config,
    local_ai_enabled,
    local_ai_timeout_seconds,
    state_db,
)

EXPLAIN_MODULE = "rackmarshal.incidents.explain"
WORKER_NAME = "explain_pending_notifications"
NEED_MODES = frozenset({"PENDING_ASYNC", "FALLBACK", "DISABLED"})


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def connect_rw(db_path: str) -> sqlite3.Connection:
    con = sqlite3.connect(db_path, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=30000")
    return con


def parse_explanation(raw: Any) -> dict | None:
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


def is_successful_ai(rec: dict | None) -> bool:
    if not rec:
        return False
    mode = str(rec.get("mode") or "")
    if mode.startswith("RECOVERY"):
        return True
    return mode == "AI" and rec.get("explainer_succeeded") is True


def needs_explain(rec: dict | None) -> bool:
    if is_successful_ai(rec):
        return False
    if rec is None:
        return True
    mode = str(rec.get("mode") or "")
    if mode.startswith("RECOVERY"):
        return False
    if mode in NEED_MODES:
        return True
    # Unknown / empty mode → treat as needing explain
    if not mode:
        return True
    # Explicit AI failure without succeeded flag
    if mode == "AI" and rec.get("explainer_succeeded") is not True:
        return True
    return False


def load_packet(packet_json: str) -> dict:
    """Match explain_incident load_packet: unwrap incident_notification_packet."""
    packet = json.loads(packet_json)
    if not isinstance(packet, dict):
        raise ValueError("packet_json is not an object")
    if packet.get("builder") == "incident_notification_packet" or (
        "incident" in packet and isinstance(packet.get("incident"), dict)
    ):
        incident = packet.get("incident")
        if isinstance(incident, dict):
            return incident
    return packet


def select_candidates(con: sqlite3.Connection, limit: int) -> list[sqlite3.Row]:
    # Prefetch a wider window; filter needs_explain in Python for JSON modes.
    rows = con.execute(
        """
        SELECT id, packet_json, explanation_json, created_at, delivery_state
        FROM incident_notifications
        WHERE notification_type = 'OPENED'
          AND packet_json IS NOT NULL
          AND length(trim(packet_json)) > 0
        ORDER BY created_at ASC
        LIMIT ?
        """,
        (max(limit * 20, 50),),
    ).fetchall()
    out: list[sqlite3.Row] = []
    for row in rows:
        if needs_explain(parse_explanation(row["explanation_json"])):
            out.append(row)
            if len(out) >= limit:
                break
    return out


def run_explainer(incident: dict, timeout: int) -> tuple[bool, Any]:
    payload = json.dumps(incident, separators=(",", ":"))
    try:
        cp = subprocess.run(
            [sys.executable, "-m", EXPLAIN_MODULE],
            input=payload,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return False, f"timeout after {timeout}s: {exc}"
    except OSError as exc:
        return False, f"spawn failed: {exc}"

    if cp.returncode != 0:
        detail = (cp.stderr or cp.stdout or "").strip() or f"rc={cp.returncode}"
        return False, detail

    out = (cp.stdout or "").strip()
    if not out:
        return False, "empty explainer stdout"
    try:
        parsed = json.loads(out)
    except json.JSONDecodeError as exc:
        return False, f"invalid explainer JSON: {exc}"
    return True, parsed


def may_write_fallback(existing: dict | None) -> bool:
    """Only write FALLBACK if null/empty or already FALLBACK/DISABLED/PENDING_ASYNC."""
    if existing is None:
        return True
    if is_successful_ai(existing):
        return False
    mode = str(existing.get("mode") or "")
    if mode.startswith("RECOVERY"):
        return False
    return mode in NEED_MODES or mode == "" or mode == "AI"


def update_explanation(
    con: sqlite3.Connection, row_id: int, record: dict, dry_run: bool
) -> None:
    blob = json.dumps(record, separators=(",", ":"), sort_keys=True)
    if dry_run:
        return
    con.execute(
        """
        UPDATE incident_notifications
        SET explanation_json = ?
        WHERE id = ?
        """,
        (blob, row_id),
    )


def process_row(
    con: sqlite3.Connection,
    row: sqlite3.Row,
    timeout: int,
    dry_run: bool,
) -> str:
    existing = parse_explanation(row["explanation_json"])
    if is_successful_ai(existing):
        return "skipped_ai"

    try:
        incident = load_packet(row["packet_json"])
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        if may_write_fallback(existing):
            update_explanation(
                con,
                int(row["id"]),
                {
                    "mode": "FALLBACK",
                    "explainer_succeeded": False,
                    "error": f"packet parse: {exc}",
                    "worker": WORKER_NAME,
                    "explained_at": utc_now(),
                },
                dry_run,
            )
        return "failed"

    ok, result = run_explainer(incident, timeout)
    now = utc_now()
    if ok:
        update_explanation(
            con,
            int(row["id"]),
            {
                "mode": "AI",
                "explainer_succeeded": True,
                "explanation": result,
                "worker": WORKER_NAME,
                "explained_at": now,
            },
            dry_run,
        )
        return "succeeded"

    if may_write_fallback(existing):
        update_explanation(
            con,
            int(row["id"]),
            {
                "mode": "FALLBACK",
                "explainer_succeeded": False,
                "error": str(result),
                "worker": WORKER_NAME,
                "explained_at": now,
            },
            dry_run,
        )
    return "failed"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Async Local-AI worker for OPENED explanation_json"
    )
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Select candidates and simulate; no DB writes",
    )
    parser.add_argument("--db", default=None, help="Override state.db path")
    args = parser.parse_args()

    summary = {
        "attempted": 0,
        "succeeded": 0,
        "failed": 0,
        "skipped_disabled": 0,
        "dry_run": bool(args.dry_run),
        "candidates": [],
    }

    if not local_ai_enabled():
        summary["skipped_disabled"] = 1
        print(json.dumps({**summary, "skipped": "disabled"}, separators=(",", ":")))
        return 0

    cfg = load_config()
    db_path = args.db or str(state_db(cfg))
    timeout = int(local_ai_timeout_seconds())

    con = connect_rw(db_path)
    try:
        candidates = select_candidates(con, max(1, int(args.limit)))
        for row in candidates:
            summary["attempted"] += 1
            summary["candidates"].append(
                {
                    "id": int(row["id"]),
                    "created_at": row["created_at"],
                    "delivery_state": row["delivery_state"],
                    "prior_mode": (parse_explanation(row["explanation_json"]) or {}).get(
                        "mode"
                    ),
                }
            )
            outcome = process_row(con, row, timeout, args.dry_run)
            if outcome == "succeeded":
                summary["succeeded"] += 1
            elif outcome == "failed":
                summary["failed"] += 1
        if not args.dry_run:
            con.commit()
        else:
            con.rollback()
    finally:
        con.close()

    print(json.dumps(summary, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
