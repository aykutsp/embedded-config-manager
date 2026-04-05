"""Schema-driven validation engine.

Schemas live under ``schemas/<module>.schema.json``. The top-level config
object is expected to be keyed by module name; each module is validated
independently against its own schema. Unknown modules are allowed but
produce a warning-level issue.

Semantic and cross-field checks are layered on top of JSON schema
validation. They are pluggable via :class:`Validator.register_semantic`.
"""

from __future__ import annotations

import ipaddress
import json
import re
from pathlib import Path
from typing import Any, Callable

from jsonschema import Draft202012Validator

SemanticCheck = Callable[[dict[str, Any]], list[str]]


class SchemaRegistry:
    def __init__(self, schemas_dir: Path):
        self.schemas_dir = schemas_dir
        self._cache: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not self.schemas_dir.exists():
            return
        for path in sorted(self.schemas_dir.glob("*.schema.json")):
            module = path.name.removesuffix(".schema.json")
            with path.open("r", encoding="utf-8") as fh:
                self._cache[module] = json.load(fh)

    @property
    def modules(self) -> list[str]:
        return sorted(self._cache.keys())

    def get(self, module: str) -> dict[str, Any] | None:
        return self._cache.get(module)

    def merged(self) -> dict[str, Any]:
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {m: self._cache[m] for m in self._cache},
            "additionalProperties": True,
        }


class Validator:
    def __init__(self, registry: SchemaRegistry):
        self.registry = registry
        self._semantic: list[SemanticCheck] = [
            _check_network_ips,
            _check_hostname,
            _check_cross_field_dhcp,
        ]

    def register_semantic(self, check: SemanticCheck) -> None:
        self._semantic.append(check)

    def validate(self, config: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        if not isinstance(config, dict):
            return ["config must be a JSON object"]

        for module, module_config in config.items():
            schema = self.registry.get(module)
            if schema is None:
                continue
            v = Draft202012Validator(schema)
            for err in sorted(v.iter_errors(module_config), key=lambda e: e.path):
                path = "/".join(str(p) for p in err.path) or "(root)"
                errors.append(f"{module}.{path}: {err.message}")

        for check in self._semantic:
            errors.extend(check(config))

        return errors


# ---------- semantic checks ----------


def _check_network_ips(config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    network = config.get("network") or {}
    for field in ("static_ip", "gateway", "dns_primary", "dns_secondary"):
        value = network.get(field)
        if value in (None, ""):
            continue
        try:
            ipaddress.ip_address(value)
        except ValueError:
            errors.append(f"network.{field}: invalid IP address '{value}'")
    return errors


_HOSTNAME_RE = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$")


def _check_hostname(config: dict[str, Any]) -> list[str]:
    system = config.get("system") or {}
    hostname = system.get("hostname")
    if hostname and not _HOSTNAME_RE.match(hostname):
        return [f"system.hostname: '{hostname}' is not a valid RFC 1123 hostname"]
    return []


def _check_cross_field_dhcp(config: dict[str, Any]) -> list[str]:
    network = config.get("network") or {}
    if network.get("dhcp") is False:
        missing = [
            f for f in ("static_ip", "gateway") if not network.get(f)
        ]
        if missing:
            return [
                f"network: dhcp disabled but {', '.join(missing)} not provided"
            ]
    return []
