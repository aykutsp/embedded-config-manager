from __future__ import annotations

import copy

from agent.diff.engine import diff_configs


def test_diff_detects_modified(valid_config):
    after = copy.deepcopy(valid_config)
    after["telemetry"]["interval_seconds"] = 120
    result = diff_configs(valid_config, after, from_revision=1, to_revision=2)
    paths = {e.path: e for e in result.entries}
    assert "telemetry/interval_seconds" in paths
    assert paths["telemetry/interval_seconds"].change == "modified"
    assert paths["telemetry/interval_seconds"].before == 60
    assert paths["telemetry/interval_seconds"].after == 120


def test_diff_detects_added_key(valid_config):
    after = copy.deepcopy(valid_config)
    after["system"]["new_field"] = "x"
    result = diff_configs(valid_config, after, from_revision=1, to_revision=2)
    assert any(e.change == "added" and "new_field" in e.path for e in result.entries)


def test_diff_detects_removed_key(valid_config):
    after = copy.deepcopy(valid_config)
    del after["network"]["mtu"]
    result = diff_configs(valid_config, after, from_revision=1, to_revision=2)
    assert any(e.change == "removed" and "mtu" in e.path for e in result.entries)


def test_diff_against_none_baseline(valid_config):
    result = diff_configs(None, valid_config, from_revision=None, to_revision=1)
    assert len(result.entries) > 0
    assert all(e.change == "added" for e in result.entries)


def test_diff_handles_list_changes():
    before = {"system": {"ntp_servers": ["a", "b"]}}
    after = {"system": {"ntp_servers": ["a", "b", "c"]}}
    result = diff_configs(before, after, from_revision=1, to_revision=2)
    assert any(e.change == "added" and "ntp_servers[2]" in e.path for e in result.entries)
