"""Jinja2-based exporter and target registry.

Targets are described in a JSON file with the following shape::

    {
      "targets": [
        {
          "name": "telemetry",
          "template": "env/telemetry.env.j2",
          "output": "/etc/telemetry/config.env",
          "reload": "systemctl reload telemetry-agent",
          "health": "test -f /etc/telemetry/config.env"
        }
      ]
    }

``reload`` and ``health`` are optional shell commands. When the agent runs
in dry-run mode (``ECM_DRY_RUN=1``, the default) commands are logged but
never executed, and output files are written under a sandbox directory.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound


@dataclass(frozen=True)
class Target:
    name: str
    template: str
    output: str
    reload: str | None = None
    health: str | None = None


class TargetRegistry:
    def __init__(self, targets_file: Path):
        self.targets_file = targets_file
        self.targets: list[Target] = []
        if targets_file.exists():
            with targets_file.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            for entry in data.get("targets", []):
                self.targets.append(Target(**entry))


class JinjaExporter:
    def __init__(self, templates_dir: Path):
        self.templates_dir = templates_dir
        self.env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            undefined=StrictUndefined,
            keep_trailing_newline=True,
        )

    def render(self, target: Target, config: dict[str, Any]) -> str:
        try:
            template = self.env.get_template(target.template)
        except TemplateNotFound as exc:
            raise FileNotFoundError(
                f"template not found: {target.template} under {self.templates_dir}"
            ) from exc
        return template.render(config=config)
