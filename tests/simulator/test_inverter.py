import math
import pytest
from unittest.mock import patch

from simulator.devices.inverter import SolarInverter, _DAY_CYCLE_SECONDS


def test_state_includes_required_fields():
    inv = SolarInverter("inv-test")
    state = inv.state()
    assert state["id"] == "inv-test"
    assert state["type"] == "inverter"
    for field in ("dc_voltage", "ac_voltage", "output_power", "efficiency"):
        assert field in state, f"missing field: {field}"


def test_zero_output_at_start_of_cycle():
    """t=0 in the cycle: sin(0) = 0, so output and efficiency should both be 0."""
    inv = SolarInverter("inv-test")
    inv._phase_offset = 0.0
    inv._peak_output = 8.0
    with patch("simulator.devices.inverter.time.time", return_value=0.0):
        t = inv.generate_telemetry()
    assert t["output_power"] == 0.0
    assert t["efficiency"] == 0.0


def test_peak_output_near_midpoint_of_cycle():
    """t=150s (half cycle): sin(π/2) = 1.0 — maximum solar output."""
    inv = SolarInverter("inv-test")
    inv._phase_offset = 0.0
    inv._peak_output = 8.0
    with patch("simulator.devices.inverter.time.time", return_value=150.0):
        t = inv.generate_telemetry()
    # output = 8.0 * 1.0 * uniform(0.95, 1.05) → between 7.6 and 8.4
    assert 7.5 <= t["output_power"] <= 8.5


def test_efficiency_nonzero_when_producing():
    inv = SolarInverter("inv-test")
    inv._phase_offset = 0.0
    with patch("simulator.devices.inverter.time.time", return_value=150.0):
        t = inv.generate_telemetry()
    assert 0.93 <= t["efficiency"] <= 0.98


def test_efficiency_zero_when_no_output():
    inv = SolarInverter("inv-test")
    inv._phase_offset = 0.0
    with patch("simulator.devices.inverter.time.time", return_value=0.0):
        t = inv.generate_telemetry()
    assert t["efficiency"] == 0.0


def test_ac_voltage_in_realistic_range():
    inv = SolarInverter("inv-test")
    for _ in range(30):
        t = inv.generate_telemetry()
        assert 220.0 <= t["ac_voltage"] <= 240.0


def test_peak_output_initialised_in_valid_range():
    for i in range(30):
        inv = SolarInverter(f"inv-{i}")
        assert 4.0 <= inv._peak_output <= 10.0


def test_phase_offset_initialised_in_valid_range():
    for i in range(30):
        inv = SolarInverter(f"inv-{i}")
        assert 0.0 <= inv._phase_offset <= _DAY_CYCLE_SECONDS


def test_output_power_nonnegative():
    inv = SolarInverter("inv-test")
    for _ in range(50):
        t = inv.generate_telemetry()
        assert t["output_power"] >= 0.0
