"""Runtime settings loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    schemas_dir: Path
    templates_dir: Path
    targets_file: Path
    backups_dir: Path
    db_path: Path
    dry_run: bool

    @classmethod
    def from_env(cls) -> Settings:
        root = Path(os.environ.get("ECM_ROOT", Path.cwd())).resolve()
        data_dir = Path(os.environ.get("ECM_DATA_DIR", root / "var"))
        default_targets = root / "examples" / "targets.json"
        return cls(
            data_dir=data_dir,
            schemas_dir=Path(os.environ.get("ECM_SCHEMAS_DIR", root / "schemas")),
            templates_dir=Path(os.environ.get("ECM_TEMPLATES_DIR", root / "templates")),
            targets_file=Path(os.environ.get("ECM_TARGETS_FILE", default_targets)),
            backups_dir=data_dir / "backups",
            db_path=data_dir / "ecm.sqlite3",
            dry_run=os.environ.get("ECM_DRY_RUN", "1") not in {"0", "false", "False"},
        )

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)
