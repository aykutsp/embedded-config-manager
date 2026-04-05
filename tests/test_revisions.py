from __future__ import annotations

import copy


def test_create_revision_returns_valid(service, valid_config):
    rev = service.create_revision(config=valid_config, author="alice", note="initial")
    assert rev.id > 0
    assert rev.validation_status == "valid"
    assert rev.validation_errors == []
    assert rev.checksum


def test_create_invalid_revision_is_stored_with_errors(service, valid_config):
    bad = copy.deepcopy(valid_config)
    bad["telemetry"]["interval_seconds"] = -5
    rev = service.create_revision(config=bad, author="alice", note="broken")
    assert rev.validation_status == "invalid"
    assert rev.validation_errors


def test_list_revisions_orders_newest_first(service, valid_config):
    service.create_revision(config=valid_config, author="a", note="one")
    service.create_revision(config=valid_config, author="a", note="two")
    listed = service.list_revisions()
    assert listed[0].note == "two"
    assert listed[1].note == "one"


def test_checksum_changes_with_config(service, valid_config):
    r1 = service.create_revision(config=valid_config, author="a", note=None)
    modified = copy.deepcopy(valid_config)
    modified["telemetry"]["interval_seconds"] = 120
    r2 = service.create_revision(config=modified, author="a", note=None)
    assert r1.checksum != r2.checksum


def test_audit_captures_create(service, valid_config):
    service.create_revision(config=valid_config, author="alice", note="x")
    audit = service.audit()
    assert any(e.action == "revision.create" and e.actor == "alice" for e in audit)
