"""Tests for coordinated and staged meta-attacks."""
import json
import pytest
import attacks.engine as engine


@pytest.fixture
def mock_client():
    class _MockClient:
        def __init__(self):
            self.published = []

        async def publish(self, topic: str, payload):
            self.published.append((topic, payload))

    return _MockClient()


# ── coordinated ───────────────────────────────────────────────────────────────

async def test_coordinated_trigger_activates_all_named_sub_attacks():
    all_attacks = {
        "coord": {
            "id": "coord", "type": "coordinated", "target": "_meta",
            "params": {"attacks": ["a1", "a2"]},
        },
        "a1": {"id": "a1", "type": "shutdown", "target": "meter-001", "params": {}},
        "a2": {"id": "a2", "type": "shutdown", "target": "meter-002", "params": {}},
    }
    await engine._handle_coordinated(all_attacks["coord"], "trigger", all_attacks)

    assert any(a["id"] == "a1" for a in engine._active_attacks.get("meter-001", []))
    assert any(a["id"] == "a2" for a in engine._active_attacks.get("meter-002", []))


async def test_coordinated_stop_deactivates_all_sub_attacks():
    all_attacks = {
        "coord": {
            "id": "coord", "type": "coordinated", "target": "_meta",
            "params": {"attacks": ["a1"]},
        },
        "a1": {"id": "a1", "type": "shutdown", "target": "meter-001", "params": {}},
    }
    await engine._handle_coordinated(all_attacks["coord"], "trigger", all_attacks)
    assert engine._active_attacks.get("meter-001")

    await engine._handle_coordinated(all_attacks["coord"], "stop", all_attacks)
    assert not engine._active_attacks.get("meter-001")


async def test_coordinated_inline_attacks_are_registered():
    all_attacks = {
        "colonial": {
            "id": "colonial", "type": "coordinated", "target": "_meta",
            "params": {"attacks": [
                {"type": "ransomware", "target": "sub-01"},
                {"type": "ransomware", "target": "sub-02"},
            ]},
        },
    }
    await engine._handle_coordinated(all_attacks["colonial"], "trigger", all_attacks)

    assert "_inline_colonial_sub-01" in all_attacks
    assert "_inline_colonial_sub-02" in all_attacks
    assert all_attacks["_inline_colonial_sub-01"]["type"] == "ransomware"
    assert all_attacks["_inline_colonial_sub-02"]["type"] == "ransomware"


async def test_coordinated_inline_attacks_are_activated():
    all_attacks = {
        "colonial": {
            "id": "colonial", "type": "coordinated", "target": "_meta",
            "params": {"attacks": [
                {"type": "ransomware", "target": "sub-01"},
                {"type": "ransomware", "target": "sub-02"},
            ]},
        },
    }
    await engine._handle_coordinated(all_attacks["colonial"], "trigger", all_attacks)

    assert any(a["type"] == "ransomware" for a in engine._active_attacks.get("sub-01", []))
    assert any(a["type"] == "ransomware" for a in engine._active_attacks.get("sub-02", []))


async def test_coordinated_inline_and_named_attacks_can_coexist():
    all_attacks = {
        "mixed": {
            "id": "mixed", "type": "coordinated", "target": "_meta",
            "params": {"attacks": [
                "named-a",
                {"type": "wiper", "target": "sub-02"},
            ]},
        },
        "named-a": {"id": "named-a", "type": "shutdown", "target": "meter-001", "params": {}},
    }
    await engine._handle_coordinated(all_attacks["mixed"], "trigger", all_attacks)

    assert any(a["type"] == "shutdown" for a in engine._active_attacks.get("meter-001", []))
    assert any(a["type"] == "wiper" for a in engine._active_attacks.get("sub-02", []))


async def test_coordinated_skips_unknown_sub_attack_ids():
    all_attacks = {
        "coord": {
            "id": "coord", "type": "coordinated", "target": "_meta",
            "params": {"attacks": ["nonexistent"]},
        },
    }
    # Should not raise
    await engine._handle_coordinated(all_attacks["coord"], "trigger", all_attacks)
    assert not engine._active_attacks


# ── staged ────────────────────────────────────────────────────────────────────

async def test_staged_trigger_activates_phase1_only(monkeypatch):
    monkeypatch.setattr(engine.asyncio, "create_task", lambda coro: coro.close() or None)

    all_attacks = {
        "staged": {
            "id": "staged", "type": "staged", "target": "_meta",
            "params": {
                "phase_1": {"duration": 10, "attack_ids": ["replay-a"]},
                "phase_2": {"attack_ids": ["cascade-b"]},
            },
        },
        "replay-a":  {"id": "replay-a",  "type": "replay",            "target": "meter-001", "params": {}},
        "cascade-b": {"id": "cascade-b", "type": "cascading_failure", "target": "sub-01",    "params": {}},
    }
    await engine._handle_staged(all_attacks["staged"], "trigger", all_attacks)

    assert any(a["type"] == "replay" for a in engine._active_attacks.get("meter-001", []))
    assert not engine._active_attacks.get("sub-01")


async def test_staged_stop_clears_both_phases():
    all_attacks = {
        "staged": {
            "id": "staged", "type": "staged", "target": "_meta",
            "params": {
                "phase_1": {"duration": 10, "attack_ids": ["replay-a"]},
                "phase_2": {"attack_ids": ["cascade-b"]},
            },
        },
        "replay-a":  {"id": "replay-a",  "type": "replay",            "target": "meter-001", "params": {}},
        "cascade-b": {"id": "cascade-b", "type": "cascading_failure", "target": "sub-01",    "params": {}},
    }
    # Pre-seed both phases as if they were activated
    engine._active_attacks["meter-001"] = [all_attacks["replay-a"]]
    engine._active_attacks["sub-01"]    = [all_attacks["cascade-b"]]

    await engine._handle_staged(all_attacks["staged"], "stop", all_attacks)

    assert not engine._active_attacks.get("meter-001")
    assert not engine._active_attacks.get("sub-01")
