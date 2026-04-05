"""FastAPI routes. Mirrors the endpoints described in docs/api.md."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from agent.core.errors import RevisionNotFoundError
from agent.core.models import ApplyRequest, CreateRevisionRequest
from agent.service import ConfigService, get_service

router = APIRouter(prefix="/api/v1")


def _svc() -> ConfigService:
    return get_service()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/config/current")
def get_current(svc: ConfigService = Depends(_svc)) -> dict[str, Any]:
    active = svc.get_active()
    if active is None:
        return {"active": None}
    return {"active": active.model_dump(mode="json")}


@router.get("/config/schema")
def get_schema(
    module: str | None = None, svc: ConfigService = Depends(_svc)
) -> dict[str, Any]:
    if module is None:
        return svc.schemas.merged()
    schema = svc.schemas.get(module)
    if schema is None:
        raise HTTPException(status_code=404, detail=f"unknown module: {module}")
    return schema


@router.post("/revisions")
def create_revision(
    payload: CreateRevisionRequest, svc: ConfigService = Depends(_svc)
) -> dict[str, Any]:
    rev = svc.create_revision(
        config=payload.config, author=payload.author, note=payload.note
    )
    return {
        "revision_id": rev.id,
        "validation_status": rev.validation_status,
        "validation_errors": rev.validation_errors,
        "apply_status": rev.apply_status,
    }


@router.post("/revisions/{revision_id}/validate")
def revalidate(
    revision_id: int, svc: ConfigService = Depends(_svc)
) -> dict[str, Any]:
    try:
        errors = svc.revalidate(revision_id)
    except RevisionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "revision_id": revision_id,
        "valid": not errors,
        "errors": errors,
    }


@router.get("/revisions")
def list_revisions(
    limit: int = Query(50, ge=1, le=500),
    svc: ConfigService = Depends(_svc),
) -> list[dict[str, Any]]:
    return [r.model_dump(mode="json") for r in svc.list_revisions(limit=limit)]


@router.get("/revisions/{revision_id}")
def get_revision(
    revision_id: int, svc: ConfigService = Depends(_svc)
) -> dict[str, Any]:
    try:
        return svc.get_revision(revision_id).model_dump(mode="json")
    except RevisionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/revisions/{revision_id}/diff")
def diff_revision(
    revision_id: int,
    against: str = "active",
    svc: ConfigService = Depends(_svc),
) -> dict[str, Any]:
    try:
        result = svc.diff(revision_id, against=against)
    except RevisionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return result.model_dump(mode="json")


@router.post("/revisions/{revision_id}/apply")
def apply_revision(
    revision_id: int,
    payload: ApplyRequest | None = None,
    svc: ConfigService = Depends(_svc),
) -> dict[str, Any]:
    try:
        result = svc.apply_revision(revision_id)
    except RevisionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "run_id": result.run_id,
        "status": result.status,
        "steps": [s.model_dump() for s in result.steps],
    }


@router.post("/revisions/{revision_id}/rollback")
def rollback_revision(
    revision_id: int, svc: ConfigService = Depends(_svc)
) -> dict[str, Any]:
    try:
        result = svc.rollback_to(revision_id)
    except RevisionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "run_id": result.run_id,
        "status": result.status,
        "steps": [s.model_dump() for s in result.steps],
    }


@router.get("/audit")
def audit(
    limit: int = Query(100, ge=1, le=1000),
    svc: ConfigService = Depends(_svc),
) -> list[dict[str, Any]]:
    return [e.model_dump(mode="json") for e in svc.audit(limit=limit)]


@router.get("/apply-runs/{run_id}")
def get_apply_run(
    run_id: int, svc: ConfigService = Depends(_svc)
) -> dict[str, Any]:
    try:
        return svc.store.get_apply_run(run_id).model_dump(mode="json")
    except RevisionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
