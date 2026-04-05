from __future__ import annotations

import copy
from pathlib import Path


def _sandboxed(service, output: str) -> Path:
    return service.apply_engine._sandbox_output(output)


def test_apply_writes_targets_in_dry_run(service, valid_config):
    rev = service.create_revision(config=valid_config, author="alice", note="first")
    result = service.apply_revision(rev.id)
    assert result.status == "success"
    assert {s.name for s in result.steps} >= {"validate", "backup", "render", "write"}

    telemetry = _sandboxed(service, "/etc/telemetry/config.env")
    assert telemetry.exists()
    text = telemetry.read_text(encoding="utf-8")
    assert "TELEMETRY_ENDPOINT=https://telemetry.example.com/ingest" in text
    assert "TELEMETRY_INTERVAL=60" in text


def test_apply_updates_active_revision(service, valid_config):
    rev = service.create_revision(config=valid_config, author="alice", note="first")
    service.apply_revision(rev.id)
    active = service.get_active()
    assert active is not None
    assert active.id == rev.id
    assert active.apply_status == "applied"


def test_apply_refuses_invalid_revision_and_rolls_back(service, valid_config):
    # First a valid revision becomes active.
    good = service.create_revision(config=valid_config, author="a", note="good")
    service.apply_revision(good.id)

    # Now push an invalid one.
    bad_config = copy.deepcopy(valid_config)
    bad_config["telemetry"]["interval_seconds"] = -1
    bad = service.create_revision(config=bad_config, author="a", note="bad")
    result = service.apply_revision(bad.id)

    assert result.status in {"rolled_back", "failed"}
    active = service.get_active()
    assert active is not None
    assert active.id == good.id  # still the previous good revision


def test_diff_against_active(service, valid_config):
    r1 = service.create_revision(config=valid_config, author="a", note="base")
    service.apply_revision(r1.id)

    modified = copy.deepcopy(valid_config)
    modified["telemetry"]["interval_seconds"] = 30
    r2 = service.create_revision(config=modified, author="a", note="faster")
    diff = service.diff(r2.id, against="active")
    assert diff.from_revision == r1.id
    assert diff.to_revision == r2.id
    assert any(e.path == "telemetry/interval_seconds" for e in diff.entries)


def test_rollback_reapplies_old_revision(service, valid_config):
    r1 = service.create_revision(config=valid_config, author="a", note="v1")
    service.apply_revision(r1.id)

    modified = copy.deepcopy(valid_config)
    modified["system"]["hostname"] = "gateway-99"
    r2 = service.create_revision(config=modified, author="a", note="v2")
    service.apply_revision(r2.id)
    assert service.get_active().id == r2.id

    service.rollback_to(r1.id)
    assert service.get_active().id == r1.id
    telemetry = _sandboxed(service, "/etc/telemetry/config.env")
    assert "HOSTNAME=gateway-01" in telemetry.read_text(encoding="utf-8")


def test_apply_run_is_persisted(service, valid_config):
    rev = service.create_revision(config=valid_config, author="a", note="x")
    result = service.apply_revision(rev.id)
    run = service.store.get_apply_run(result.run_id)
    assert run.status == "success"
    assert run.revision_id == rev.id
    assert len(run.steps) >= 4
