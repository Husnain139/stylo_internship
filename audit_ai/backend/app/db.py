"""SQLite schema, connections, and prototype users.

audit_events is append-only at the database: triggers abort UPDATE and DELETE.
"""

from __future__ import annotations

import sqlite3

from . import rbac
from .config import data_dir, db_path, files_dir

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('junior_auditor', 'senior_auditor', 'administrator')),
  password_hash TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS engagements (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  proposed_type TEXT,
  proposed_confidence REAL,
  proposed_reasons TEXT NOT NULL DEFAULT '[]',
  missing_evidence TEXT NOT NULL DEFAULT '[]',
  scope_status TEXT NOT NULL DEFAULT 'proposed',
  scope_audit_type TEXT,
  scope_confirmed_by TEXT,
  scope_confirmed_at TEXT,
  scope_rejected_by TEXT,
  scope_rejected_at TEXT,
  scope_rejection_note TEXT,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memberships (
  engagement_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  PRIMARY KEY (engagement_id, user_id)
);

CREATE TABLE IF NOT EXISTS documents (
  id TEXT PRIMARY KEY,
  engagement_id TEXT NOT NULL,
  filename TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  page_count INTEGER NOT NULL,
  stored_name TEXT NOT NULL,
  document_class TEXT,
  class_confidence REAL,
  class_reasons TEXT NOT NULL DEFAULT '[]',
  uploaded_by TEXT NOT NULL,
  uploaded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence_fields (
  id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL,
  field_name TEXT NOT NULL,
  value TEXT,
  page INTEGER,
  confidence REAL NOT NULL,
  validation_status TEXT NOT NULL,
  source TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS analysis_runs (
  id TEXT PRIMARY KEY,
  engagement_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  created_by TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS findings (
  id TEXT PRIMARY KEY,
  engagement_id TEXT NOT NULL,
  analysis_run_id TEXT NOT NULL,
  rule_id TEXT NOT NULL,
  title TEXT NOT NULL,
  narrative_status TEXT NOT NULL,
  delta_amount INTEGER,
  currency TEXT,
  risk_band TEXT NOT NULL,
  explanation TEXT NOT NULL,
  evidence_ids TEXT NOT NULL,
  detail TEXT NOT NULL,
  review_status TEXT NOT NULL DEFAULT 'open',
  review_note TEXT,
  reviewed_by TEXT,
  reviewed_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts_utc TEXT NOT NULL,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  object_type TEXT NOT NULL,
  object_id TEXT NOT NULL,
  payload_json TEXT NOT NULL DEFAULT '{}',
  payload_hash TEXT NOT NULL,
  prev_hash TEXT NOT NULL,
  chain_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS audit_events_no_update
BEFORE UPDATE ON audit_events
BEGIN
  SELECT RAISE(ABORT, 'audit_events are append-only');
END;

CREATE TRIGGER IF NOT EXISTS audit_events_no_delete
BEFORE DELETE ON audit_events
BEGIN
  SELECT RAISE(ABORT, 'audit_events are append-only');
END;
"""

SEED_USERS = (
    ("junior.auditor@stylo.local", "Junior Auditor", rbac.JUNIOR),
    ("senior.auditor@stylo.local", "Senior Auditor", rbac.SENIOR),
    ("admin.auditor@stylo.local", "Administrator", rbac.ADMIN),
)


def _ensure_engagement_columns(conn: sqlite3.Connection) -> None:
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(engagements)")}
    for name in ("scope_rejected_by", "scope_rejected_at", "scope_rejection_note"):
        if name not in existing:
            conn.execute(f"ALTER TABLE engagements ADD COLUMN {name} TEXT")


def _ensure_audit_columns(conn: sqlite3.Connection) -> None:
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(audit_events)")}
    if "payload_json" not in existing:
        conn.execute("ALTER TABLE audit_events ADD COLUMN payload_json TEXT NOT NULL DEFAULT '{}'")


def connect() -> sqlite3.Connection:
    data_dir().mkdir(parents=True, exist_ok=True)
    files_dir().mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    from .rbac import hash_password

    conn = connect()
    try:
        conn.executescript(SCHEMA)
        _ensure_engagement_columns(conn)
        _ensure_audit_columns(conn)
        existing = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        if existing == 0:
            password_hash = hash_password(bootstrap_password())
            for email, name, role in SEED_USERS:
                conn.execute(
                    "INSERT INTO users (id, email, name, role, password_hash, active) VALUES (?,?,?,?,?,1)",
                    (email, email, name, role, password_hash),
                )
        if conn.execute("SELECT 1 FROM settings WHERE key = 'retention'").fetchone() is None:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES ('retention', ?)",
                ('{"retention_days":2555,"legal_hold":false}',),
            )
        conn.commit()
    finally:
        conn.close()


def bootstrap_password() -> str:
    from .config import bootstrap_password as configured

    return configured()

