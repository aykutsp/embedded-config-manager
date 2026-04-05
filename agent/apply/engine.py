"""Apply pipeline.

The pipeline deliberately mirrors the flow described in
``docs/architecture.md``:

1. validate
2. backup current rendered targets
3. render new targets via exporters
4. atomically write rendered files over their destinations
5. execute reload/restart hooks
6. run health checks
7. mark revision active — or roll back on failure

In dry-run mode (``ECM_DRY_RUN=1``) every filesystem and shell side effect
is redirected to a sandbox directory. This is the default so tests and
local development never touch real system files.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from agent.core.errors import ApplyError, HealthCheckError, ValidationError
from agent.core.models import ApplyStep, Revision
from agent.core.settings import Settings
from agent.exporters.jinja import JinjaExporter, Target, TargetRegistry
from agent.storage.revisions import RevisionStore
from agent.validation.engine import Validator


@dataclass
class ApplyResult:
    run_id: int
    status: str  # success | failed | rolled_back
    steps: list[ApplyStep]


class ApplyEngine:
    def __init__(
        self,
        *,
        settings: Settings,
        store: RevisionStore,
        validator: Validator,
        targets: TargetRegistry,
        exporter: JinjaExporter,
    ):
        self.settings = settings
        self.store = store
        self.validator = validator
        self.targets = targets
        self.exporter = exporter

    # ------------------------------------------------------------------

    def apply(self, revision: Revision, *, actor: str = "admin") -> ApplyResult:
        run_id = self.store.start_apply_run(revision.id)
        self.store.update_apply_status(revision.id, "applying")
        self.store.log_audit(
            actor=actor, action="apply.start", revision_id=revision.id, status="running"
        )

        steps: list[ApplyStep] = []
        previous_active = self._active_or_none()
        backup_dir: Path | None = None
        self._last_failed_step: ApplyStep | None = None

        try:
            steps.append(self._step("validate", lambda: self._validate(revision)))
            backup_dir, step = self._timed(
                "backup", lambda: self._backup(previous_active)
            )
            steps.append(step)

            rendered, step = self._timed(
                "render", lambda: self._render_all(revision)
            )
            steps.append(step)

            steps.append(self._step("write", lambda: self._write_all(rendered)))
            steps.append(self._step("reload", lambda: self._run_hooks("reload")))
            steps.append(self._step("health", lambda: self._run_hooks("health")))

        except Exception as exc:
            if self._last_failed_step is not None:
                steps.append(self._last_failed_step)
            else:
                steps.append(ApplyStep(name="error", status="failed", detail=str(exc)))
            rolled_back = False
            if previous_active is not None and backup_dir is not None:
                try:
                    self._restore(backup_dir)
                    rolled_back = True
                except Exception as rexc:  # pragma: no cover - defensive
                    steps.append(
                        ApplyStep(
                            name="rollback",
                            status="failed",
                            detail=f"rollback failed: {rexc}",
                        )
                    )
            final_status = "rolled_back" if rolled_back else "failed"
            self.store.update_apply_status(
                revision.id, "rolled_back" if rolled_back else "failed"
            )
            if rolled_back and previous_active is not None:
                self.store.set_active(previous_active.id)
                self.store.update_apply_status(previous_active.id, "applied")
            self.store.finish_apply_run(run_id, status=final_status, steps=steps)
            self.store.log_audit(
                actor=actor,
                action="apply.finish",
                revision_id=revision.id,
                status=final_status,
                note=str(exc),
            )
            return ApplyResult(run_id=run_id, status=final_status, steps=steps)

        # success path
        self.store.set_active(revision.id)
        self.store.update_apply_status(revision.id, "applied")
        if previous_active is not None and previous_active.id != revision.id:
            self.store.update_apply_status(previous_active.id, "not_applied")
        self.store.finish_apply_run(run_id, status="success", steps=steps)
        self.store.log_audit(
            actor=actor,
            action="apply.finish",
            revision_id=revision.id,
            status="success",
        )
        return ApplyResult(run_id=run_id, status="success", steps=steps)

    def rollback_to(self, revision: Revision, *, actor: str = "admin") -> ApplyResult:
        self.store.log_audit(
            actor=actor, action="rollback.request", revision_id=revision.id
        )
        return self.apply(revision, actor=actor)

    # ------------------------------------------------------------------
    # helpers

    def _active_or_none(self) -> Revision | None:
        active_id = self.store.get_active_id()
        if active_id is None:
            return None
        return self.store.get_revision(active_id)

    def _validate(self, revision: Revision) -> None:
        errors = self.validator.validate(revision.config)
        if errors:
            raise ValidationError(errors)

    def _sandbox_output(self, output: str) -> Path:
        """Map a real filesystem path into the sandbox directory."""
        stripped = output.lstrip("/").replace(":", "_").replace("\\", "/")
        return self.settings.data_dir / "sandbox" / stripped

    def _resolve_output(self, output: str) -> Path:
        if self.settings.dry_run:
            return self._sandbox_output(output)
        return Path(output)

    def _backup(self, active: Revision | None) -> Path:
        ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        backup_dir = self.settings.backups_dir / f"backup-{ts}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        for target in self.targets.targets:
            src = self._resolve_output(target.output)
            if src.exists():
                dst = backup_dir / f"{target.name}{_suffix(src)}"
                shutil.copy2(src, dst)
        return backup_dir

    def _render_all(self, revision: Revision) -> dict[str, tuple[Target, str]]:
        rendered: dict[str, tuple[Target, str]] = {}
        for target in self.targets.targets:
            rendered[target.name] = (target, self.exporter.render(target, revision.config))
        return rendered

    def _write_all(self, rendered: dict[str, tuple[Target, str]]) -> None:
        for _, (target, content) in rendered.items():
            dst = self._resolve_output(target.output)
            dst.parent.mkdir(parents=True, exist_ok=True)
            tmp = dst.with_suffix(dst.suffix + ".tmp")
            tmp.write_text(content, encoding="utf-8")
            os.replace(tmp, dst)

    def _run_hooks(self, kind: str) -> None:
        for target in self.targets.targets:
            cmd = target.reload if kind == "reload" else target.health
            if not cmd:
                continue
            if self.settings.dry_run:
                continue  # hooks are logged via step detail, not executed
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=30
            )
            if result.returncode != 0:
                err = result.stderr.strip() or result.stdout.strip()
                if kind == "health":
                    raise HealthCheckError(
                        f"health check failed for {target.name}: {err}"
                    )
                raise ApplyError(f"reload hook failed for {target.name}: {err}")

    def _restore(self, backup_dir: Path) -> None:
        for target in self.targets.targets:
            candidate = backup_dir / f"{target.name}{_suffix(self._resolve_output(target.output))}"
            if candidate.exists():
                dst = self._resolve_output(target.output)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(candidate, dst)

    # step timing helper ------------------------------------------------

    def _step(self, name: str, fn) -> ApplyStep:
        _, step = self._timed(name, fn)
        return step

    def _timed(self, name: str, fn):
        """Run ``fn`` and return (result, step). Re-raises on failure after
        recording the failed step on ``self._last_failed_step`` so the outer
        handler can append it before rolling back."""
        start = time.perf_counter()
        try:
            result = fn()
        except Exception as exc:
            duration = int((time.perf_counter() - start) * 1000)
            self._last_failed_step = ApplyStep(
                name=name, status="failed", duration_ms=duration, detail=str(exc)
            )
            raise
        duration = int((time.perf_counter() - start) * 1000)
        return result, ApplyStep(name=name, status="success", duration_ms=duration)


def _suffix(path: Path) -> str:
    return path.suffix or ".dat"
