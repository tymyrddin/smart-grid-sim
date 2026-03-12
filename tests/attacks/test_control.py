"""Tests for handle_control — the MQTT control message dispatcher."""
import json
import pytest
import attacks.engine as engine


@pytest.fixture
def sample_attacks():
    return {
        "spoof-m1":   {"id": "spoof-m1",   "type": "spoofing",  "target": "meter-001", "params": {"max_deviation": 50}},
        "replay-m2":  {"id": "replay-m2",  "type": "replay",    "target": "meter-002", "params": {}},
        "cascade-s1": {"id": "cascade-s1", "type": "cascading_failure", "target": "sub-01", "params": {}},
    }


async def test_trigger_adds_attack_to_active(sample_attacks):
    payload = json.dumps({"attack_id": "spoof-m1", "action": "trigger"}).encode()
    await engine.handle_control(payload, sample_attacks)
    assert any(a["id"] == "spoof-m1" for a in engine._active_attacks.get("meter-001", []))


async def test_trigger_is_idempotent(sample_attacks):
    payload = json.dumps({"attack_id": "spoof-m1", "action": "trigger"}).encode()
    await engine.handle_control(payload, sample_attacks)
    await engine.handle_control(payload, sample_attacks)
    assert len(engine._active_attacks["meter-001"]) == 1


async def test_stop_removes_attack_from_active(sample_attacks):
    engine._active_attacks["meter-001"] = [sample_attacks["spoof-m1"]]
    payload = json.dumps({"attack_id": "spoof-m1", "action": "stop"}).encode()
    await engine.handle_control(payload, sample_attacks)
    assert not engine._active_attacks.get("meter-001")


async def test_unknown_attack_id_is_ignored(sample_attacks):
    payload = json.dumps({"attack_id": "nonexistent", "action": "trigger"}).encode()
    await engine.handle_control(payload, sample_attacks)
    assert not engine._active_attacks


async def test_invalid_json_is_silently_ignored(sample_attacks):
    await engine.handle_control(b"not valid json {{", sample_attacks)
    assert not engine._active_attacks


async def test_stop_clears_replay_frozen_state(sample_attacks):
    engine._active_attacks["meter-002"] = [sample_attacks["replay-m2"]]
    engine._frozen_states["meter-002"]  = {"voltage": 230.0}
    payload = json.dumps({"attack_id": "replay-m2", "action": "stop"}).encode()
    await engine.handle_control(payload, sample_attacks)
    assert "meter-002" not in engine._frozen_states


# ── apply_attacks ─────────────────────────────────────────────────────────────

def test_apply_attacks_marks_compromised(sample_attacks):
    engine._active_attacks["meter-001"] = [sample_attacks["spoof-m1"]]
    result = engine.apply_attacks("meter-001", {"id": "meter-001", "voltage": 230.0})
    assert result["_compromised"] is True


def test_apply_attacks_passes_through_unmodified_when_no_attacks():
    payload = {"id": "meter-001", "voltage": 230.0}
    result = engine.apply_attacks("meter-001", payload)
    assert result == payload
    assert "_compromised" not in result


def test_apply_attacks_chains_multiple_attacks(sample_attacks):
    engine._active_attacks["meter-001"] = [
        sample_attacks["spoof-m1"],
        {"id": "freq-m1", "type": "frequency_attack", "params": {"target_frequency": 47.5}, "target": "meter-001"},
    ]
    payload = {"id": "meter-001", "voltage": 230.0, "frequency": 50.0}
    result = engine.apply_attacks("meter-001", payload)
    # Spoofing applied: voltage changed; frequency attack applied: frequency near 47.5
    assert result["_compromised"] is True
    assert 47.0 <= result["frequency"] <= 48.0
