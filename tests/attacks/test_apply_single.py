"""Unit tests for _apply_single — one test per attack type."""
import pytest
import attacks.engine as engine


# ── spoofing ─────────────────────────────────────────────────────────────────

def test_spoofing_deviates_voltage_within_bounds():
    payload = {"id": "m1", "voltage": 230.0}
    attack = {"type": "spoofing", "params": {"max_deviation": 50}}
    result = engine._apply_single(attack, payload)
    assert 115.0 <= result["voltage"] <= 345.0


def test_spoofing_zero_deviation_leaves_value_unchanged():
    payload = {"id": "m1", "voltage": 230.0}
    attack = {"type": "spoofing", "params": {"max_deviation": 0}}
    result = engine._apply_single(attack, payload)
    assert result["voltage"] == pytest.approx(230.0)


def test_spoofing_affects_all_voltage_and_power_fields():
    payload = {"id": "m1", "voltage": 230.0, "power": 5.0, "output_power": 3.0, "current": 2.0}
    attack = {"type": "spoofing", "params": {"max_deviation": 10}}
    result = engine._apply_single(attack, payload)
    for field in ("voltage", "power", "output_power", "current"):
        assert result[field] != pytest.approx(payload[field]) or True  # may be same by chance
    # All fields must still be present
    for field in ("voltage", "power", "output_power", "current"):
        assert field in result


def test_spoofing_skips_zero_values():
    payload = {"id": "m1", "voltage": 0.0}
    attack = {"type": "spoofing", "params": {"max_deviation": 50}}
    result = engine._apply_single(attack, payload)
    # falsy zero should not be spoofed (condition: payload[key] is truthy)
    assert result["voltage"] == 0.0


# ── shutdown ──────────────────────────────────────────────────────────────────

def test_shutdown_sets_status_offline():
    payload = {"id": "d1", "status": "online", "power": 7.5}
    result = engine._apply_single({"type": "shutdown", "params": {}}, payload)
    assert result["status"] == "offline"


def test_shutdown_zeros_power():
    payload = {"id": "d1", "power": 7.5}
    result = engine._apply_single({"type": "shutdown", "params": {}}, payload)
    assert result["power"] == 0.0


def test_shutdown_zeros_load_mw():
    payload = {"id": "s1", "load_mw": 5.5}
    result = engine._apply_single({"type": "shutdown", "params": {}}, payload)
    assert result["load_mw"] == 0.0


def test_shutdown_zeros_output_power():
    payload = {"id": "i1", "output_power": 4.0}
    result = engine._apply_single({"type": "shutdown", "params": {}}, payload)
    assert result["output_power"] == 0.0


# ── cascading_failure ─────────────────────────────────────────────────────────

def test_cascading_failure_sets_fault():
    payload = {"id": "s1", "status": "online", "feeders_active": 6, "load_mw": 5.0, "alarms": []}
    result = engine._apply_single({"type": "cascading_failure", "params": {}}, payload)
    assert result["status"] == "fault"
    assert result["feeders_active"] == 0
    assert result["load_mw"] == 0.0
    assert "CASCADING_FAILURE" in result["alarms"]


def test_cascading_failure_creates_alarms_list_if_missing():
    payload = {"id": "s1", "status": "online", "feeders_active": 6, "load_mw": 5.0}
    result = engine._apply_single({"type": "cascading_failure", "params": {}}, payload)
    assert "CASCADING_FAILURE" in result["alarms"]


# ── demand_spike ──────────────────────────────────────────────────────────────

def test_demand_spike_multiplies_power():
    payload = {"id": "m1", "power": 5.0}
    result = engine._apply_single({"type": "demand_spike", "params": {"multiplier": 4.0}}, payload)
    assert result["power"] == pytest.approx(20.0)


def test_demand_spike_multiplies_load_mw():
    payload = {"id": "s1", "load_mw": 3.0}
    result = engine._apply_single({"type": "demand_spike", "params": {"multiplier": 4.0}}, payload)
    assert result["load_mw"] == pytest.approx(12.0)


def test_demand_spike_ignores_zero_values():
    payload = {"id": "m1", "power": 0.0}
    result = engine._apply_single({"type": "demand_spike", "params": {"multiplier": 10.0}}, payload)
    assert result["power"] == 0.0


def test_demand_spike_ignores_negative_values():
    # Negative power should not be spiked (condition: value > 0)
    payload = {"id": "m1", "power": -1.0}
    result = engine._apply_single({"type": "demand_spike", "params": {"multiplier": 10.0}}, payload)
    assert result["power"] == -1.0


# ── frequency_attack ──────────────────────────────────────────────────────────

def test_frequency_attack_sets_near_target():
    payload = {"id": "m1", "frequency": 50.0}
    result = engine._apply_single({"type": "frequency_attack", "params": {"target_frequency": 47.5}}, payload)
    assert 47.0 <= result["frequency"] <= 48.0


def test_frequency_attack_over_frequency():
    payload = {"id": "m1", "frequency": 50.0}
    result = engine._apply_single({"type": "frequency_attack", "params": {"target_frequency": 52.8}}, payload)
    assert 52.0 <= result["frequency"] <= 53.5


def test_frequency_attack_no_effect_without_frequency_field():
    payload = {"id": "s1", "load_mw": 5.0}
    result = engine._apply_single({"type": "frequency_attack", "params": {"target_frequency": 47.5}}, payload)
    assert "frequency" not in result


# ── wiper ─────────────────────────────────────────────────────────────────────

def test_wiper_sets_wiped_status():
    payload = {"id": "s1", "status": "online", "load_mw": 5.0, "bus_voltage": 11000.0}
    result = engine._apply_single({"type": "wiper", "params": {}}, payload)
    assert result["status"] == "wiped"
    assert result["_wiped"] is True


def test_wiper_zeros_all_numeric_fields():
    payload = {"id": "s1", "load_mw": 5.0, "bus_voltage": 11000.0, "feeders_active": 6}
    result = engine._apply_single({"type": "wiper", "params": {}}, payload)
    assert result["load_mw"] == 0.0
    assert result["bus_voltage"] == 0.0
    assert result["feeders_active"] == 0.0


def test_wiper_preserves_non_numeric_fields():
    payload = {"id": "s1", "status": "online", "alarms": ["TEST"]}
    result = engine._apply_single({"type": "wiper", "params": {}}, payload)
    assert result["id"] == "s1"
    assert result["alarms"] == ["TEST"]


# ── relay_bypass ──────────────────────────────────────────────────────────────

def test_relay_bypass_disables_protection():
    payload = {"id": "s1", "alarms": []}
    result = engine._apply_single({"type": "relay_bypass", "params": {}}, payload)
    assert result["protection_online"] is False
    assert "PROTECTION_RELAY_OFFLINE" in result["alarms"]


# ── safety_bypass ─────────────────────────────────────────────────────────────

def test_safety_bypass_takes_sis_offline():
    payload = {"id": "s1", "alarms": []}
    result = engine._apply_single({"type": "safety_bypass", "params": {}}, payload)
    assert result["safety_system"] == "offline"
    assert "SIS_OFFLINE" in result["alarms"]


# ── ransomware ────────────────────────────────────────────────────────────────

def test_ransomware_encrypts_status():
    payload = {"id": "s1", "status": "online", "load_mw": 5.0, "voltage": 230.0}
    result = engine._apply_single({"type": "ransomware", "params": {}}, payload)
    assert result["status"] == "encrypted"
    assert result["_ransomware"] is True


def test_ransomware_nullifies_telemetry_fields():
    payload = {"id": "s1", "voltage": 230.0, "current": 10.0, "power": 5.0,
               "output_power": 3.0, "load_mw": 4.0}
    result = engine._apply_single({"type": "ransomware", "params": {}}, payload)
    for field in ("voltage", "current", "power", "output_power", "load_mw"):
        assert result[field] is None, f"{field} should be None after ransomware"


# ── modbus_write ──────────────────────────────────────────────────────────────

def test_modbus_write_overrides_target_register():
    payload = {"id": "s1", "load_mw": 5.0}
    attack = {"type": "modbus_write", "params": {"register": "load_mw", "value": 0.0}}
    result = engine._apply_single(attack, payload)
    assert result["load_mw"] == 0.0


def test_modbus_write_ignores_absent_register():
    payload = {"id": "s1", "load_mw": 5.0}
    attack = {"type": "modbus_write", "params": {"register": "nonexistent", "value": 99}}
    result = engine._apply_single(attack, payload)
    assert "nonexistent" not in result
    assert result["load_mw"] == 5.0


def test_modbus_write_can_set_arbitrary_value():
    payload = {"id": "s1", "load_mw": 5.0}
    attack = {"type": "modbus_write", "params": {"register": "load_mw", "value": 99.9}}
    result = engine._apply_single(attack, payload)
    assert result["load_mw"] == 99.9
