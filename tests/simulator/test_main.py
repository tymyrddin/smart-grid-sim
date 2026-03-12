import pytest
from simulator.main import build_devices, DEVICE_CLASSES
from simulator.devices.meter import SmartMeter
from simulator.devices.inverter import SolarInverter
from simulator.devices.ev_charger import EVCharger
from simulator.devices.substation import Substation


SAMPLE_CONFIG = {
    "devices": [
        {"id": "meter-001",    "type": "meter",      "update_interval": 1, "vulnerabilities": []},
        {"id": "inverter-001", "type": "inverter",   "update_interval": 2, "vulnerabilities": []},
        {"id": "ev-001",       "type": "ev_charger", "update_interval": 1, "vulnerabilities": []},
        {"id": "sub-001",      "type": "substation", "update_interval": 5, "vulnerabilities": []},
    ]
}


def test_build_devices_creates_correct_types():
    devices = build_devices(SAMPLE_CONFIG)
    by_id = {d.id: type(d) for d in devices}
    assert by_id["meter-001"]    == SmartMeter
    assert by_id["inverter-001"] == SolarInverter
    assert by_id["ev-001"]       == EVCharger
    assert by_id["sub-001"]      == Substation


def test_build_devices_sets_device_id():
    devices = build_devices(SAMPLE_CONFIG)
    ids = {d.id for d in devices}
    assert ids == {"meter-001", "inverter-001", "ev-001", "sub-001"}


def test_build_devices_sets_update_interval():
    devices = build_devices(SAMPLE_CONFIG)
    inverter = next(d for d in devices if d.id == "inverter-001")
    assert inverter.update_interval == 2


def test_build_devices_sets_vulnerabilities():
    config = {"devices": [
        {"id": "m1", "type": "meter", "update_interval": 1, "vulnerabilities": ["spoof", "replay"]},
    ]}
    devices = build_devices(config)
    assert devices[0].vulnerabilities == ["spoof", "replay"]


def test_build_devices_skips_unknown_type(capsys):
    config = {"devices": [{"id": "ghost-001", "type": "ghost", "update_interval": 1}]}
    devices = build_devices(config)
    assert len(devices) == 0
    captured = capsys.readouterr()
    assert "unknown device type" in captured.out


def test_build_devices_empty_list():
    devices = build_devices({"devices": []})
    assert devices == []


def test_device_classes_registry_covers_all_types():
    assert set(DEVICE_CLASSES.keys()) == {"meter", "inverter", "ev_charger", "substation"}


def test_build_devices_defaults_update_interval():
    config = {"devices": [{"id": "m1", "type": "meter"}]}
    devices = build_devices(config)
    assert devices[0].update_interval == 1  # default
