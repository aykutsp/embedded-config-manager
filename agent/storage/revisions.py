"""SQLite-backed revision, audit, and apply-run store.

The store is intentionally thin: every public method takes native Python types
and returns Pydantic models from :mod:`agent.core.models`. Transactions are
scoped per call so the store is safe to use from the FastAPI request thread
and from the apply engine worker.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent.core.errors import NoActiveRevisionError, RevisionNotFoundError
from agent.core.models import (
    ApplyRun,
    ApplyStatus,
    ApplyStep,
    AuditEvent,
    Revision,
    RevisionSummary,
    ValidationStatus,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    author TEXT NOT NULL,
    note TEXT,
    config_json TEXT NOT NULL,
    checksum TEXT NOT NULL,
    validation_status TEXT NOT NULL,
    validation_errors TEXT NOT NULL DEFAULT '[]',
    apply_status TEXT NOT NULL DEFAULT 'not_applied'
);

CREATE TABLE IF NOT EXISTS active_revision (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    revision_id INTEGER NOT NULL REFERENCES revisions(id)
);

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    revision_id INTEGER,
    module TEXT,
    status TEXT,
    note TEXT
);

CREATE TABLE IF NOT EXISTS apply_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    revision_id INTEGER NOT NULL REFERENCES revisions(id),
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    steps_json TEXT NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_revisions_created ON revisions(created_at DESC);
"""


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def checksum_config(config: dict[str, Any]) -> str:
    canonical = json.dumps(config, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class RevisionStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as cx:
            cx.executescript(SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        cx = sqlite3.connect(self.db_path, isolation_level=None, timeout=5.0)
        cx.row_factory = sqlite3.Row
        cx.execute("PRAGMA foreign_keys = ON")
        cx.execute("PRAGMA journal_mode = WAL")
        try:
            yield cx
        finally:
            cx.close()

    # ---------- revisions ----------

    def create_revision(
        self,
        *,
        config: dict[str, Any],
        author: str,
        note: str | None,
        validation_status: ValidationStatus,
        validation_errors: list[str],
    ) -> Revision:
        payload = json.dumps(config, sort_keys=True)
        checksum = checksum_config(config)
        created_at = _utcnow_iso()
        with self._conn() as cx:
            cur = cx.execute(
                """
                INSERT INTO revisions (
                    created_at, author, note, config_json, checksum,
                    validation_status, validation_errors
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    created_at,
                    author,
                    note,
                    payload,
                    checksum,
                    validation_status,
                    json.dumps(validation_errors),
                ),
            )
            rev_id = cur.lastrowid
        return self.get_revision(rev_id)

    def get_revision(self, revision_id: int) -> Revision:
        with self._conn() as cx:
            row = cx.execute(
                "SELECT * FROM revisions WHERE id = ?", (revision_id,)
            ).fetchone()
        if row is None:
            raise RevisionNotFoundError(f"revision {revision_id} not found")
        return _row_to_revision(row)

    def list_revisions(self, limit: int = 50) -> list[RevisionSummary]:
        with self._conn() as cx:
            rows = cx.execute(
                """
                SELECT id, created_at, author, note, validation_status, apply_status
                FROM revisions ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            RevisionSummary(
                id=row["id"],
                created_at=datetime.fromisoformat(row["created_at"]),
                author=row["author"],
                note=row["note"],
                validation_status=row["validation_status"],
                apply_status=row["apply_status"],
            )
            for row in rows
        ]

    def update_apply_status(self, revision_id: int, status: ApplyStatus) -> None:
        with self._conn() as cx:
            cx.execute(
                "UPDATE revisions SET apply_status = ? WHERE id = ?",
                (status, revision_id),
            )

    # ---------- active revision ----------

    def set_active(self, revision_id: int) -> None:
        with self._conn() as cx:
            cx.execute(
                "INSERT INTO active_revision (id, revision_id) VALUES (1, ?) "
                "ON CONFLICT(id) DO UPDATE SET revision_id = excluded.revision_id",
                (revision_id,),
            )

    def get_active_id(self) -> int | None:
        with self._conn() as cx:
            row = cx.execute(
                "SELECT revision_id FROM active_revision WHERE id = 1"
            ).fetchone()
        return int(row["revision_id"]) if row else None

    def get_active(self) -> Revision:
        rid = self.get_active_id()
        if rid is None:
            raise NoActiveRevisionError("no active revision")
        return self.get_revision(rid)

    # ---------- audit ----------

    def log_audit(
        self,
        *,
        actor: str,
        action: str,
        revision_id: int | None = None,
        module: str | None = None,
        status: str | None = None,
        note: str | None = None,
    ) -> None:
        with self._conn() as cx:
            cx.execute(
                """
                INSERT INTO audit_events
                    (created_at, actor, action, revision_id, module, status, note)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (_utcnow_iso(), actor, action, revision_id, module, status, note),
            )

    def list_audit(self, limit: int = 100) -> list[AuditEvent]:
        with self._conn() as cx:
            rows = cx.execute(
                "SELECT * FROM audit_events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            AuditEvent(
                id=row["id"],
                created_at=datetime.fromisoformat(row["created_at"]),
                actor=row["actor"],
                action=row["action"],
                revision_id=row["revision_id"],
                module=row["module"],
                status=row["status"],
                note=row["note"],
            )
            for row in rows
        ]

    # ---------- apply runs ----------

    def start_apply_run(self, revision_id: int) -> int:
        with self._conn() as cx:
            cur = cx.execute(
                "INSERT INTO apply_runs (revision_id, started_at, status) "
                "VALUES (?, ?, 'running')",
                (revision_id, _utcnow_iso()),
            )
            return int(cur.lastrowid)

    def finish_apply_run(
        self, run_id: int, *, status: str, steps: list[ApplyStep]
    ) -> None:
        with self._conn() as cx:
            cx.execute(
                "UPDATE apply_runs SET finished_at = ?, status = ?, steps_json = ? "
                "WHERE id = ?",
                (
                    _utcnow_iso(),
                    status,
                    json.dumps([s.model_dump() for s in steps]),
                    run_id,
                ),
            )

    def get_apply_run(self, run_id: int) -> ApplyRun:
        with self._conn() as cx:
            row = cx.execute(
                "SELECT * FROM apply_runs WHERE id = ?", (run_id,)
            ).fetchone()
        if row is None:
            raise RevisionNotFoundError(f"apply run {run_id} not found")
        steps_raw = json.loads(row["steps_json"] or "[]")
        return ApplyRun(
            id=row["id"],
            revision_id=row["revision_id"],
            started_at=datetime.fromisoformat(row["started_at"]),
            finished_at=datetime.fromisoformat(row["finished_at"])
            if row["finished_at"]
            else None,
            status=row["status"],
            steps=[ApplyStep(**s) for s in steps_raw],
        )


def _row_to_revision(row: sqlite3.Row) -> Revision:
    return Revision(
        id=row["id"],
        created_at=datetime.fromisoformat(row["created_at"]),
        author=row["author"],
        note=row["note"],
        config=json.loads(row["config_json"]),
        checksum=row["checksum"],
        validation_status=row["validation_status"],
        validation_errors=json.loads(row["validation_errors"] or "[]"),
        apply_status=row["apply_status"],
    )
