import math
import pytest
from unittest.mock import patch

from simulator.devices.substation import Substation, _DAY_CYCLE_SECONDS


def test_state_includes_required_fields():
    sub = Substation("sub-test")
    state = sub.state()
    assert state["id"] == "sub-test"
    assert state["type"] == "substation"
    for field in ("bus_voltage", "load_mw", "feeders_active", "transformer_temp", "alarms"):
        assert field in state, f"missing field: {field}"


def test_bus_voltage_near_11kv():
    sub = Substation("sub-test")
    for _ in range(30):
        t = sub.generate_telemetry()
        assert 10_500.0 <= t["bus_voltage"] <= 11_500.0


def test_load_within_day_cycle_range():
    """load = 6 ± 3 MW sinusoidal + gauss(0, 0.2) noise — stay well within 2–10 MW."""
    sub = Substation("sub-test")
    sub._phase_offset = 0.0
    for _ in range(50):
        t = sub.generate_telemetry()
        assert 2.0 <= t["load_mw"] <= 10.0, f"load out of range: {t['load_mw']}"


def test_feeder_count_in_valid_range():
    sub = Substation("sub-test")
    assert 4 <= sub._feeder_count <= 8
    t = sub.generate_telemetry()
    assert 4 <= t["feeders_active"] <= 8


def test_transformer_temp_near_baseline():
    sub = Substation("sub-test")
    for _ in range(30):
        t = sub.generate_telemetry()
        assert 55.0 <= t["transformer_temp"] <= 75.0


def test_alarms_empty_by_default():
    sub = Substation("sub-test")
    t = sub.generate_telemetry()
    assert t["alarms"] == []


def test_phase_offset_in_valid_range():
    for i in range(30):
        sub = Substation(f"sub-{i}")
        assert 0.0 <= sub._phase_offset <= math.pi


def test_opposite_phase_offsets_produce_different_loads():
    """Substations at phase 0 and π should have opposite load curves."""
    sub1 = Substation("sub-1")
    sub2 = Substation("sub-2")
    sub1._phase_offset = 0.0
    sub2._phase_offset = math.pi

    # At t=75s, sin(π * 75/300 + 0) ≠ sin(π * 75/300 + π)
    with patch("simulator.devices.substation.time.time", return_value=75.0):
        t1 = sub1.generate_telemetry()
        t2 = sub2.generate_telemetry()

    # The two loads should differ by roughly 6 MW (2 × 3 MW amplitude), minus noise
    assert abs(t1["load_mw"] - t2["load_mw"]) > 3.0


def test_feeder_count_constant_across_ticks():
    sub = Substation("sub-test")
    counts = {sub.generate_telemetry()["feeders_active"] for _ in range(10)}
    assert len(counts) == 1  # deterministic — set at init
