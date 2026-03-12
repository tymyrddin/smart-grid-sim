"""Tests for stateful attacks: replay, thermal_stress, aurora."""
import pytest
import attacks.engine as engine


# ── replay ────────────────────────────────────────────────────────────────────

def test_replay_freezes_state_on_first_call():
    attack = {"type": "replay", "params": {}}
    payload = {"id": "m1", "voltage": 230.0, "status": "online"}
    engine._apply_single(attack, dict(payload))
    assert "m1" in engine._frozen_states
    assert engine._frozen_states["m1"]["voltage"] == 230.0


def test_replay_returns_frozen_state_on_subsequent_calls():
    attack = {"type": "replay", "params": {}}
    # First call: freeze at 230V
    engine._apply_single(attack, {"id": "m1", "voltage": 230.0})
    # Second call with changed value: should return 230V, not 999V
    result = engine._apply_single(attack, {"id": "m1", "voltage": 999.0})
    assert result["voltage"] == 230.0
    assert result["_compromised"] is True


def test_replay_frozen_state_is_not_overwritten():
    attack = {"type": "replay", "params": {}}
    engine._apply_single(attack, {"id": "m1", "voltage": 100.0})
    engine._apply_single(attack, {"id": "m1", "voltage": 200.0})
    engine._apply_single(attack, {"id": "m1", "voltage": 300.0})
    # Frozen state should remain at the first value
    assert engine._frozen_states["m1"]["voltage"] == 100.0


def test_replay_clear_removes_frozen_state():
    attack = {"type": "replay", "params": {}}
    engine._frozen_states["m1"] = {"voltage": 230.0}
    engine._clear_attack(attack, "m1")
    assert "m1" not in engine._frozen_states


# ── thermal_stress ────────────────────────────────────────────────────────────

def test_thermal_accumulates_per_tick():
    attack = {"type": "thermal_stress", "params": {"rate": 2.0, "trip_threshold": 999.0}}
    payload = {"id": "s1", "transformer_temp": 65.0}
    engine._apply_single(attack, dict(payload))  # tick 1: accumulation = 2
    engine._apply_single(attack, dict(payload))  # tick 2: accumulation = 4
    result = engine._apply_single(attack, dict(payload))  # tick 3: accumulation = 6
    assert result["transformer_temp"] == pytest.approx(65.0 + 6.0)


def test_thermal_trips_when_threshold_exceeded():
    attack = {"type": "thermal_stress", "params": {"rate": 50.0, "trip_threshold": 112.0}}
    payload = {"id": "s1", "transformer_temp": 65.0, "feeders_active": 6, "load_mw": 5.0}
    # After 2 ticks: accumulation = 100, temp = 65 + 100 = 165°C → above threshold
    engine._apply_single(attack, dict(payload))
    result = engine._apply_single(attack, dict(payload))
    assert result["status"] == "fault"
    assert result["feeders_active"] == 0
    assert result["load_mw"] == 0.0
    assert any("THERMAL_OVERLOAD_TRIP" in a for a in result.get("alarms", []))


def test_thermal_does_not_trip_below_threshold():
    attack = {"type": "thermal_stress", "params": {"rate": 1.0, "trip_threshold": 200.0}}
    payload = {"id": "s1", "transformer_temp": 65.0, "feeders_active": 6, "load_mw": 5.0}
    result = engine._apply_single(attack, dict(payload))  # only +1°C
    assert result.get("status") != "fault"


def test_thermal_clear_removes_accumulation():
    attack = {"type": "thermal_stress", "params": {"rate": 2.0, "trip_threshold": 200.0}}
    engine._thermal_accumulation["s1"] = 10.0
    engine._clear_attack(attack, "s1")
    assert "s1" not in engine._thermal_accumulation


def test_thermal_accumulation_persists_across_calls():
    attack = {"type": "thermal_stress", "params": {"rate": 3.0, "trip_threshold": 999.0}}
    payload = {"id": "s1", "transformer_temp": 65.0}
    engine._apply_single(attack, dict(payload))
    assert engine._thermal_accumulation["s1"] == pytest.approx(3.0)
    engine._apply_single(attack, dict(payload))
    assert engine._thermal_accumulation["s1"] == pytest.approx(6.0)


# ── aurora ────────────────────────────────────────────────────────────────────

def test_aurora_odd_tick_zeroes_power():
    attack = {"type": "aurora", "params": {}}
    payload = {"id": "i1", "output_power": 5.0}
    result = engine._apply_single(attack, dict(payload))  # tick 1: odd
    assert result["output_power"] == 0.0


def test_aurora_even_tick_surges_power():
    attack = {"type": "aurora", "params": {}}
    payload = {"id": "i1", "output_power": 5.0}
    engine._apply_single(attack, dict(payload))            # tick 1: zero
    result = engine._apply_single(attack, dict(payload))   # tick 2: surge
    assert result["output_power"] == pytest.approx(5.0 * 2.8)


def test_aurora_trips_at_tick_8():
    attack = {"type": "aurora", "params": {}}
    payload = {"id": "i1", "status": "online", "output_power": 5.0, "ac_voltage": 230.0}
    for _ in range(8):
        result = engine._apply_single(attack, dict(payload))
    assert result["status"] == "fault"
    assert result["output_power"] == 0.0
    assert any("AURORA_GENERATOR_TRIP" in a for a in result.get("alarms", []))


def test_aurora_does_not_trip_before_tick_8():
    attack = {"type": "aurora", "params": {}}
    payload = {"id": "i1", "status": "online", "output_power": 5.0}
    for _ in range(7):
        result = engine._apply_single(attack, dict(payload))
    assert result.get("status") != "fault"


def test_aurora_clear_removes_tick_counter():
    attack = {"type": "aurora", "params": {}}
    engine._aurora_ticks["i1"] = 5
    engine._clear_attack(attack, "i1")
    assert "i1" not in engine._aurora_ticks


def test_aurora_tick_counter_increments():
    attack = {"type": "aurora", "params": {}}
    payload = {"id": "i1", "output_power": 5.0}
    for n in range(1, 5):
        engine._apply_single(attack, dict(payload))
        assert engine._aurora_ticks["i1"] == n
