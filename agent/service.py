"""Thin orchestration layer used by the API and tests.

Holds the shared dependencies (store, validator, exporter, apply engine)
so the FastAPI routes stay trivial and the test suite can instantiate
the same service against an isolated temp directory.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.apply.engine import ApplyEngine, ApplyResult
from agent.core.errors import NoActiveRevisionError
from agent.core.models import Revision, RevisionDiff, RevisionSummary
from agent.core.settings import Settings
from agent.diff.engine import diff_configs
from agent.exporters.jinja import JinjaExporter, TargetRegistry
from agent.storage.revisions import RevisionStore
from agent.validation.engine import SchemaRegistry, Validator


class ConfigService:
    def __init__(self, settings: Settings):
        settings.ensure_dirs()
        self.settings = settings
        self.store = RevisionStore(settings.db_path)
        self.schemas = SchemaRegistry(settings.schemas_dir)
        self.validator = Validator(self.schemas)
        self.targets = TargetRegistry(settings.targets_file)
        self.exporter = JinjaExporter(settings.templates_dir)
        self.apply_engine = ApplyEngine(
            settings=settings,
            store=self.store,
            validator=self.validator,
            targets=self.targets,
            exporter=self.exporter,
        )

    # --- revisions -----------------------------------------------------

    def create_revision(
        self, *, config: dict[str, Any], author: str, note: str | None
    ) -> Revision:
        errors = self.validator.validate(config)
        status = "valid" if not errors else "invalid"
        revision = self.store.create_revision(
            config=config,
            author=author,
            note=note,
            validation_status=status,
            validation_errors=errors,
        )
        self.store.log_audit(
            actor=author,
            action="revision.create",
            revision_id=revision.id,
            status=status,
            note=note,
        )
        return revision

    def list_revisions(self, limit: int = 50) -> list[RevisionSummary]:
        return self.store.list_revisions(limit=limit)

    def get_revision(self, revision_id: int) -> Revision:
        return self.store.get_revision(revision_id)

    def get_active(self) -> Revision | None:
        try:
            return self.store.get_active()
        except NoActiveRevisionError:
            return None

    def revalidate(self, revision_id: int) -> list[str]:
        rev = self.store.get_revision(revision_id)
        errors = self.validator.validate(rev.config)
        return errors

    # --- diff ----------------------------------------------------------

    def diff(self, revision_id: int, against: int | str = "active") -> RevisionDiff:
        target = self.store.get_revision(revision_id)
        before_rev: Revision | None
        if against == "active":
            active_id = self.store.get_active_id()
            before_rev = self.store.get_revision(active_id) if active_id else None
        else:
            before_rev = self.store.get_revision(int(against))
        return diff_configs(
            before_rev.config if before_rev else None,
            target.config,
            from_revision=before_rev.id if before_rev else None,
            to_revision=target.id,
        )

    # --- apply / rollback ---------------------------------------------

    def apply_revision(self, revision_id: int, *, actor: str = "admin") -> ApplyResult:
        rev = self.store.get_revision(revision_id)
        return self.apply_engine.apply(rev, actor=actor)

    def rollback_to(self, revision_id: int, *, actor: str = "admin") -> ApplyResult:
        rev = self.store.get_revision(revision_id)
        return self.apply_engine.rollback_to(rev, actor=actor)

    # --- audit ---------------------------------------------------------

    def audit(self, limit: int = 100):
        return self.store.list_audit(limit=limit)


_default_service: ConfigService | None = None


def get_service() -> ConfigService:
    global _default_service
    if _default_service is None:
        _default_service = ConfigService(Settings.from_env())
    return _default_service


def reset_service() -> None:
    global _default_service
    _default_service = None
