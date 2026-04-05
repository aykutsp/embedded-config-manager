"""Structured diff between two configuration snapshots.

The diff walks nested dicts and lists and emits one entry per changed
path using ``/``-separated JSON pointer-ish syntax. Lists are compared
index-by-index; callers treat removals at indices beyond the shorter
list as ``removed`` and extras as ``added``.
"""

from __future__ import annotations

from typing import Any

from agent.core.models import DiffEntry, RevisionDiff


def diff_configs(
    before: dict[str, Any] | None,
    after: dict[str, Any],
    *,
    from_revision: int | None,
    to_revision: int,
) -> RevisionDiff:
    entries: list[DiffEntry] = []
    _walk("", before or {}, after, entries)
    return RevisionDiff(
        from_revision=from_revision,
        to_revision=to_revision,
        entries=entries,
    )


def _walk(prefix: str, before: Any, after: Any, out: list[DiffEntry]) -> None:
    if isinstance(before, dict) and isinstance(after, dict):
        keys = sorted(set(before.keys()) | set(after.keys()))
        for key in keys:
            child_prefix = f"{prefix}/{key}" if prefix else key
            if key not in before:
                out.append(
                    DiffEntry(path=child_prefix, change="added", after=after[key])
                )
            elif key not in after:
                out.append(
                    DiffEntry(path=child_prefix, change="removed", before=before[key])
                )
            else:
                _walk(child_prefix, before[key], after[key], out)
        return

    if isinstance(before, list) and isinstance(after, list):
        for idx in range(max(len(before), len(after))):
            child_prefix = f"{prefix}[{idx}]"
            if idx >= len(before):
                out.append(
                    DiffEntry(path=child_prefix, change="added", after=after[idx])
                )
            elif idx >= len(after):
                out.append(
                    DiffEntry(path=child_prefix, change="removed", before=before[idx])
                )
            else:
                _walk(child_prefix, before[idx], after[idx], out)
        return

    if before != after:
        out.append(
            DiffEntry(path=prefix or "(root)", change="modified", before=before, after=after)
        )
