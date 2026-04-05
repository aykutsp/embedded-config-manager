from __future__ import annotations

import copy


def test_example_config_is_valid(service, valid_config):
    errors = service.validator.validate(valid_config)
    assert errors == []


def test_missing_hostname_is_rejected(service, valid_config):
    cfg = copy.deepcopy(valid_config)
    del cfg["system"]["hostname"]
    errors = service.validator.validate(cfg)
    assert any("hostname" in e for e in errors)


def test_invalid_ip_is_rejected(service, valid_config):
    cfg = copy.deepcopy(valid_config)
    cfg["network"]["static_ip"] = "999.1.1.1"
    errors = service.validator.validate(cfg)
    assert any("static_ip" in e for e in errors)


def test_dhcp_disabled_requires_static(service, valid_config):
    cfg = copy.deepcopy(valid_config)
    cfg["network"]["dhcp"] = False
    cfg["network"]["static_ip"] = ""
    cfg["network"]["gateway"] = ""
    errors = service.validator.validate(cfg)
    assert any("dhcp" in e for e in errors)


def test_interval_out_of_range(service, valid_config):
    cfg = copy.deepcopy(valid_config)
    cfg["telemetry"]["interval_seconds"] = 0
    errors = service.validator.validate(cfg)
    assert any("interval_seconds" in e for e in errors)


def test_bad_hostname(service, valid_config):
    cfg = copy.deepcopy(valid_config)
    cfg["system"]["hostname"] = "NOT VALID!"
    errors = service.validator.validate(cfg)
    assert any("hostname" in e for e in errors)


def test_schema_registry_discovers_modules(service):
    assert set(service.schemas.modules) >= {"system", "network", "telemetry"}
