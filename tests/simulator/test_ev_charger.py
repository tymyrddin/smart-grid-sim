import pytest
from unittest.mock import patch

from simulator.devices.ev_charger import EVCharger


def test_state_includes_required_fields():
    ev = EVCharger("ev-test")
    state = ev.state()
    assert state["id"] == "ev-test"
    assert state["type"] == "ev_charger"
    for field in ("charging", "power", "voltage", "session_energy"):
        assert field in state, f"missing field: {field}"


def test_power_zero_when_idle():
    ev = EVCharger("ev-test")
    ev._charging = False
    ev._power = 0.0
    # random.random() = 0.9 > 0.05 → no new session
    with patch("simulator.devices.ev_charger.random.random", return_value=0.9):
        t = ev.generate_telemetry()
    assert t["power"] == 0.0
    assert t["charging"] is False


def test_power_matches_internal_state_when_charging():
    ev = EVCharger("ev-test")
    ev._charging = True
    ev._power = 11.0
    ev._session_energy = 0.0
    # random.random() = 0.5 > 0.03 → no session end; gauss = 0 → no drift
    with patch("simulator.devices.ev_charger.random.random", return_value=0.5), \
         patch("simulator.devices.ev_charger.random.gauss", return_value=0.0):
        t = ev.generate_telemetry()
    assert t["charging"] is True
    assert t["power"] == pytest.approx(11.0)


def test_session_ends_when_random_below_threshold():
    ev = EVCharger("ev-test")
    ev._charging = True
    ev._power = 11.0
    ev._session_energy = 5.0
    with patch("simulator.devices.ev_charger.random.random", return_value=0.01):  # < 0.03
        t = ev.generate_telemetry()
    assert t["charging"] is False
    assert t["power"] == 0.0
    assert ev._session_energy == 0.0


def test_session_starts_when_random_below_threshold():
    ev = EVCharger("ev-test")
    ev._charging = False
    ev._power = 0.0
    with patch("simulator.devices.ev_charger.random.random", return_value=0.02), \
         patch("simulator.devices.ev_charger.random.uniform", return_value=15.0):
        t = ev.generate_telemetry()
    assert t["charging"] is True
    assert ev._power == 15.0


def test_no_session_starts_when_random_above_threshold():
    ev = EVCharger("ev-test")
    ev._charging = False
    with patch("simulator.devices.ev_charger.random.random", return_value=0.9):
        t = ev.generate_telemetry()
    assert t["charging"] is False


def test_power_clamped_at_maximum():
    ev = EVCharger("ev-test")
    ev._charging = True
    ev._power = 21.9
    ev._session_energy = 0.0
    with patch("simulator.devices.ev_charger.random.random", return_value=0.5), \
         patch("simulator.devices.ev_charger.random.gauss", return_value=5.0):
        ev.generate_telemetry()
    assert ev._power <= 22.0


def test_power_clamped_at_minimum():
    ev = EVCharger("ev-test")
    ev._charging = True
    ev._power = 7.1
    ev._session_energy = 0.0
    with patch("simulator.devices.ev_charger.random.random", return_value=0.5), \
         patch("simulator.devices.ev_charger.random.gauss", return_value=-5.0):
        ev.generate_telemetry()
    assert ev._power >= 7.0


def test_session_energy_accumulates_per_tick():
    ev = EVCharger("ev-test")
    ev._charging = True
    ev._power = 10.0
    ev._session_energy = 0.0
    with patch("simulator.devices.ev_charger.random.random", return_value=0.5), \
         patch("simulator.devices.ev_charger.random.gauss", return_value=0.0):
        ev.generate_telemetry()
    expected = 10.0 * (2 / 3600)
    assert ev._session_energy == pytest.approx(expected)


def test_session_energy_capped_at_80kwh():
    ev = EVCharger("ev-test")
    ev._charging = True
    ev._power = 22.0
    ev._session_energy = 79.999
    with patch("simulator.devices.ev_charger.random.random", return_value=0.5), \
         patch("simulator.devices.ev_charger.random.gauss", return_value=0.0):
        ev.generate_telemetry()
    assert ev._session_energy <= 80.0


def test_voltage_in_realistic_range():
    ev = EVCharger("ev-test")
    for _ in range(30):
        t = ev.generate_telemetry()
        assert 225.0 <= t["voltage"] <= 235.0
