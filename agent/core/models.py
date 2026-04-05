"""Pydantic models used across the agent."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ApplyStatus = Literal["not_applied", "applying", "applied", "failed", "rolled_back"]
ValidationStatus = Literal["pending", "valid", "invalid"]


class Revision(BaseModel):
    id: int
    created_at: datetime
    author: str
    note: str | None = None
    config: dict[str, Any]
    checksum: str
    validation_status: ValidationStatus
    validation_errors: list[str] = Field(default_factory=list)
    apply_status: ApplyStatus = "not_applied"


class RevisionSummary(BaseModel):
    id: int
    created_at: datetime
    author: str
    note: str | None
    validation_status: ValidationStatus
    apply_status: ApplyStatus


class CreateRevisionRequest(BaseModel):
    config: dict[str, Any]
    note: str | None = None
    author: str = "admin"


class ApplyRequest(BaseModel):
    force: bool = False
    confirm_restart: bool = True


class DiffEntry(BaseModel):
    path: str
    change: Literal["added", "removed", "modified"]
    before: Any | None = None
    after: Any | None = None


class RevisionDiff(BaseModel):
    from_revision: int | None
    to_revision: int
    entries: list[DiffEntry]


class AuditEvent(BaseModel):
    id: int
    created_at: datetime
    actor: str
    action: str
    revision_id: int | None = None
    module: str | None = None
    status: str | None = None
    note: str | None = None


class ApplyStep(BaseModel):
    name: str
    status: Literal["pending", "running", "success", "failed", "skipped"]
    duration_ms: int | None = None
    detail: str | None = None


class ApplyRun(BaseModel):
    id: int
    revision_id: int
    started_at: datetime
    finished_at: datetime | None
    status: Literal["running", "success", "failed", "rolled_back"]
    steps: list[ApplyStep]
