"""Tests for cascade propagation logic."""
import json
import pytest
import attacks.engine as engine


@pytest.fixture
def mock_client():
    class _MockClient:
        def __init__(self):
            self.published = []

        async def publish(self, topic: str, payload):
            self.published.append((topic, json.loads(payload)))

    return _MockClient()


# ── cascade_to_connected ──────────────────────────────────────────────────────

async def test_cascade_publishes_shadow_for_each_child(mock_client):
    engine._topology["sub-01"] = ["meter-001", "meter-002"]
    engine._device_states["sub-01"]   = {"id": "sub-01", "feeders_active": 4}
    engine._device_states["meter-001"] = {"id": "meter-001", "type": "meter", "voltage": 230.0}
    engine._device_states["meter-002"] = {"id": "meter-002", "type": "meter", "voltage": 230.0}

    await engine.cascade_to_connected(mock_client, "sub-01", {"sub-01": 80})

    topics = [p[0] for p in mock_client.published]
    assert any("meter-001" in t for t in topics)
    assert any("meter-002" in t for t in topics)


async def test_cascade_sets_no_grid_status(mock_client):
    engine._topology["sub-01"] = ["meter-001"]
    engine._device_states["sub-01"]    = {"id": "sub-01", "feeders_active": 4}
    engine._device_states["meter-001"] = {"id": "meter-001", "type": "meter",
                                          "voltage": 230.0, "power": 5.0}

    await engine.cascade_to_connected(mock_client, "sub-01", {})

    meter_pub = next(p[1] for p in mock_client.published if "meter-001" in p[0])
    assert meter_pub["status"] == "no_grid"
    assert meter_pub["_compromised"] is True
    assert meter_pub["_cascaded_from"] == "sub-01"


async def test_cascade_zeros_all_power_fields(mock_client):
    engine._topology["sub-01"] = ["inverter-001"]
    engine._device_states["sub-01"]      = {"id": "sub-01", "feeders_active": 4}
    engine._device_states["inverter-001"] = {
        "id": "inverter-001", "type": "inverter",
        "output_power": 5.0, "ac_voltage": 230.0, "dc_voltage": 380.0, "frequency": 50.0,
    }

    await engine.cascade_to_connected(mock_client, "sub-01", {})

    pub = next(p[1] for p in mock_client.published if "inverter-001" in p[0])
    for field in ("output_power", "ac_voltage", "dc_voltage", "frequency"):
        assert pub[field] == 0.0


async def test_cascade_stops_ev_charging(mock_client):
    engine._topology["sub-01"] = ["ev-001"]
    engine._device_states["sub-01"]  = {"id": "sub-01", "feeders_active": 4}
    engine._device_states["ev-001"]  = {"id": "ev-001", "type": "ev_charger",
                                        "charging": True, "power": 11.0}

    await engine.cascade_to_connected(mock_client, "sub-01", {})

    pub = next(p[1] for p in mock_client.published if "ev-001" in p[0])
    assert pub["charging"] is False


async def test_cascade_skips_devices_with_no_state(mock_client):
    engine._topology["sub-01"] = ["meter-unknown"]
    engine._device_states["sub-01"] = {"id": "sub-01", "feeders_active": 4}
    # meter-unknown has no entry in _device_states

    await engine.cascade_to_connected(mock_client, "sub-01", {})

    meter_pubs = [p for p in mock_client.published if "meter-unknown" in p[0]]
    assert len(meter_pubs) == 0


async def test_cascade_publishes_alarm_event(mock_client):
    engine._topology["sub-01"] = ["meter-001"]
    engine._device_states["sub-01"]    = {"id": "sub-01", "feeders_active": 4}
    engine._device_states["meter-001"] = {"id": "meter-001", "type": "meter", "voltage": 230.0}

    await engine.cascade_to_connected(mock_client, "sub-01", {"sub-01": 80})

    alarm_pubs = [p[1] for p in mock_client.published if p[0] == "events/alarms"]
    assert len(alarm_pubs) == 1
    assert alarm_pubs[0]["severity"] == "CRITICAL"


async def test_cascade_no_publish_when_no_children(mock_client):
    engine._topology["sub-01"] = []
    engine._device_states["sub-01"] = {"id": "sub-01", "feeders_active": 4}

    await engine.cascade_to_connected(mock_client, "sub-01", {})
    assert len(mock_client.published) == 0


# ── _has_fault_attack ─────────────────────────────────────────────────────────

def test_has_fault_attack_true_for_cascading_failure():
    engine._active_attacks["sub-01"] = [{"type": "cascading_failure"}]
    assert engine._has_fault_attack("sub-01") is True


def test_has_fault_attack_true_for_wiper():
    engine._active_attacks["sub-01"] = [{"type": "wiper"}]
    assert engine._has_fault_attack("sub-01") is True


def test_has_fault_attack_true_for_thermal_stress():
    engine._active_attacks["sub-01"] = [{"type": "thermal_stress"}]
    assert engine._has_fault_attack("sub-01") is True


def test_has_fault_attack_false_when_no_attacks():
    assert engine._has_fault_attack("sub-01") is False


def test_has_fault_attack_false_for_spoofing():
    engine._active_attacks["sub-01"] = [{"type": "spoofing"}]
    assert engine._has_fault_attack("sub-01") is False


def test_has_fault_attack_false_for_replay():
    engine._active_attacks["sub-01"] = [{"type": "replay"}]
    assert engine._has_fault_attack("sub-01") is False


# ── _get_parent ───────────────────────────────────────────────────────────────

def test_get_parent_returns_correct_parent():
    engine._topology["sub-01"] = ["meter-001", "meter-002"]
    assert engine._get_parent("meter-001") == "sub-01"
    assert engine._get_parent("meter-002") == "sub-01"


def test_get_parent_returns_none_for_root_device():
    engine._topology["sub-01"] = ["meter-001"]
    assert engine._get_parent("sub-01") is None


def test_get_parent_returns_none_when_topology_empty():
    assert engine._get_parent("meter-001") is None
