"""Append-only hash-chained audit events. There is no update or delete helper."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timezone

_lock = threading.Lock()


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def canonical(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def append_event(
    conn: sqlite3.Connection,
    *,
    actor: str,
    action: str,
    object_type: str,
    object_id: str,
    payload: dict,
) -> None:
    payload_json = canonical(payload)
    payload_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
    with _lock:
        row = conn.execute("SELECT chain_hash FROM audit_events ORDER BY id DESC LIMIT 1").fetchone()
        prev = row["chain_hash"] if row else "GENESIS"
        chain = hashlib.sha256(f"{prev}{payload_hash}".encode("utf-8")).hexdigest()
        conn.execute(
            """
            INSERT INTO audit_events (
              ts_utc, actor, action, object_type, object_id, payload_json, payload_hash, prev_hash, chain_hash
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (utc_now(), actor, action, object_type, object_id, payload_json, payload_hash, prev, chain),
        )
        conn.commit()


def list_events(conn: sqlite3.Connection, *, newest_first: bool = False) -> list[sqlite3.Row]:
    order = "DESC" if newest_first else "ASC"
    return list(conn.execute(f"SELECT * FROM audit_events ORDER BY id {order}"))


def event_payload(row: sqlite3.Row) -> dict:
    raw = row["payload_json"] if "payload_json" in row.keys() else None
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}
