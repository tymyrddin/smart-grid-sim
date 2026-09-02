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


def _shadow_publish(client, target):
    """The immediate shadow/devices publish for the target substation, if any."""
    return next(
        (p[1] for p in client.published if p[0] == f"shadow/devices/substation/{target}/state"),
        None,
    )


async def _trigger(client, attack_id, all_attacks):
    payload = json.dumps({"attack_id": attack_id, "action": "trigger"}).encode()
    await engine.handle_control(payload, all_attacks, client)


@pytest.fixture
def seeded_substation():
    engine._device_states["sub-01"] = {
        "id": "sub-01", "type": "substation", "feeders_active": 6, "load_mw": 6.0,
    }


async def test_cascading_failure_immediate_publish(mock_client, seeded_substation):
    attacks = {"cf": {"id": "cf", "type": "cascading_failure", "target": "sub-01", "params": {}}}
    await _trigger(mock_client, "cf", attacks)

    pub = _shadow_publish(mock_client, "sub-01")
    assert pub is not None
    assert pub["status"] == "fault"
    assert pub["alarms"] == ["CASCADING_FAILURE"]
    assert pub["feeders_active"] == 0
    assert pub["load_mw"] == 0.0
    assert pub["_compromised"] is True
    assert pub["_homes_lost"] == 6 * 80
    assert "_wiped" not in pub


async def test_shutdown_immediate_publish(mock_client, seeded_substation):
    attacks = {"sd": {"id": "sd", "type": "shutdown", "target": "sub-01", "params": {}}}
    await _trigger(mock_client, "sd", attacks)

    pub = _shadow_publish(mock_client, "sub-01")
    assert pub is not None
    assert pub["status"] == "offline"
    assert pub["alarms"] == ["DEVICE_OFFLINE"]
    assert "_wiped" not in pub


async def test_wiper_immediate_publish_matches_wiped_semantics(mock_client, seeded_substation):
    attacks = {"wp": {"id": "wp", "type": "wiper", "target": "sub-01", "params": {}}}
    await _trigger(mock_client, "wp", attacks)

    pub = _shadow_publish(mock_client, "sub-01")
    assert pub is not None
    assert pub["status"] == "wiped"
    assert pub["alarms"] == ["WIPER_DEPLOYED"]
    assert pub["_wiped"] is True
    assert pub["_compromised"] is True


async def test_target_marked_faulted_on_immediate_fault(mock_client, seeded_substation):
    attacks = {"wp": {"id": "wp", "type": "wiper", "target": "sub-01", "params": {}}}
    await _trigger(mock_client, "wp", attacks)
    assert "sub-01" in engine._faulted_substations


async def test_no_immediate_publish_without_prior_device_state(mock_client):
    attacks = {"wp": {"id": "wp", "type": "wiper", "target": "sub-01", "params": {}}}
    await _trigger(mock_client, "wp", attacks)
    assert _shadow_publish(mock_client, "sub-01") is None
    assert "sub-01" in engine._faulted_substations


async def test_shutdown_on_charger_takes_the_slow_path(mock_client):
    engine._device_states["ev-01"] = {"id": "ev-01", "type": "ev_charger", "power": 11.0}
    attacks = {"sd": {"id": "sd", "type": "shutdown", "target": "ev-01", "params": {}}}
    await _trigger(mock_client, "sd", attacks)

    assert not [p for p in mock_client.published if p[0].startswith("shadow/")]
    assert "ev-01" not in engine._faulted_substations
    assert attacks["sd"] in engine._active_attacks["ev-01"]
