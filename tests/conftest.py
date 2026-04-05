"""Shared pytest fixtures.

Every test gets a fresh temp directory and a ConfigService wired against
isolated schemas/templates/targets, so suites never share state.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from agent.core.settings import Settings
from agent.service import ConfigService

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def valid_config() -> dict:
    with (REPO_ROOT / "examples" / "config.example.json").open("r", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    schemas_dir = tmp_path / "schemas"
    templates_dir = tmp_path / "templates"
    schemas_dir.mkdir()
    templates_dir.mkdir()
    shutil.copytree(REPO_ROOT / "schemas", schemas_dir, dirs_exist_ok=True)
    shutil.copytree(REPO_ROOT / "templates", templates_dir, dirs_exist_ok=True)

    targets_file = tmp_path / "targets.json"
    targets_file.write_text(
        json.dumps(
            {
                "targets": [
                    {
                        "name": "telemetry",
                        "template": "env/telemetry.env.j2",
                        "output": "/etc/telemetry/config.env",
                    },
                    {
                        "name": "network",
                        "template": "env/network.env.j2",
                        "output": "/etc/network/interfaces.d/ecm.conf",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    data_dir = tmp_path / "var"
    return Settings(
        data_dir=data_dir,
        schemas_dir=schemas_dir,
        templates_dir=templates_dir,
        targets_file=targets_file,
        backups_dir=data_dir / "backups",
        db_path=data_dir / "ecm.sqlite3",
        dry_run=True,
    )


@pytest.fixture
def service(settings: Settings) -> ConfigService:
    return ConfigService(settings)
