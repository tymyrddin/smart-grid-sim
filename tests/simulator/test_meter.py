from simulator.devices.meter import SmartMeter


def test_state_includes_required_fields():
    meter = SmartMeter("meter-test")
    state = meter.state()
    assert state["id"] == "meter-test"
    assert state["type"] == "meter"
    assert state["status"] == "online"
    for field in ("voltage", "current", "power", "frequency"):
        assert field in state, f"missing field: {field}"


def test_voltage_in_realistic_range():
    meter = SmartMeter("meter-test")
    for _ in range(50):
        t = meter.generate_telemetry()
        assert 220.0 <= t["voltage"] <= 240.0, f"voltage out of range: {t['voltage']}"


def test_frequency_near_50hz():
    meter = SmartMeter("meter-test")
    for _ in range(50):
        t = meter.generate_telemetry()
        assert 49.5 <= t["frequency"] <= 50.5, f"frequency out of range: {t['frequency']}"


def test_power_positive():
    meter = SmartMeter("meter-test")
    meter._base_load = 5.0
    for _ in range(20):
        t = meter.generate_telemetry()
        assert t["power"] > 0


def test_current_tracks_base_load():
    meter = SmartMeter("meter-test")
    meter._base_load = 5.0
    for _ in range(30):
        t = meter.generate_telemetry()
        # current = base_load + gauss(0, 0.3) — should stay within ~1.5A of base_load
        assert 3.0 <= t["current"] <= 7.0


def test_base_load_initialised_in_valid_range():
    for i in range(30):
        meter = SmartMeter(f"meter-{i}")
        assert 1.5 <= meter._base_load <= 8.0


def test_state_merges_telemetry_with_base_fields():
    meter = SmartMeter("meter-test")
    state = meter.state()
    # Both base fields and telemetry fields present in one dict
    assert "id" in state and "voltage" in state
