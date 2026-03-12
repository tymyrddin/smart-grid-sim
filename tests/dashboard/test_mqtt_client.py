"""Tests for dashboard/mqtt_client.py — state management, history, events."""
import json
import pytest
import dashboard.mqtt_client as mc


@pytest.fixture(autouse=True)
def reset_state():
    """Reset all module-level state before each test."""
    mc.device_states.clear()
    mc.event_log.clear()
    mc.metric_history.clear()
    mc.temp_history.clear()
    yield


def raw(**kwargs) -> bytes:
    return json.dumps(kwargs).encode()


# ── _handle_alarm ─────────────────────────────────────────────────────────────

def test_alarm_appended_to_event_log():
    mc._handle_alarm(raw(time="12:00:00", severity="CRITICAL", source="ENGINE", message="Test"))
    assert len(mc.event_log) == 1
    entry = mc.event_log[0]
    assert entry["severity"] == "CRITICAL"
    assert entry["source"] == "ENGINE"
    assert entry["message"] == "Test"
    assert entry["engine"] is True


def test_alarm_invalid_json_is_ignored():
    mc._handle_alarm(b"not json")
    assert len(mc.event_log) == 0


def test_alarm_fills_defaults_for_missing_fields():
    mc._handle_alarm(json.dumps({}).encode())
    entry = mc.event_log[0]
    assert entry["severity"] == "INFO"
    assert entry["source"] == "SYSTEM"
    assert entry["message"] == ""


def test_alarm_event_log_maxlen_80():
    for i in range(85):
        mc._handle_alarm(raw(message=str(i)))
    assert len(mc.event_log) == 80


# ── _handle_telemetry ─────────────────────────────────────────────────────────

def test_telemetry_updates_device_state():
    mc._handle_telemetry(raw(id="meter-001", type="meter", status="online", voltage=230.0))
    assert "meter-001" in mc.device_states
    assert mc.device_states["meter-001"]["voltage"] == 230.0


def test_telemetry_ignores_payload_without_id():
    mc._handle_telemetry(raw(type="meter", voltage=230.0))
    assert len(mc.device_states) == 0


def test_telemetry_invalid_json_is_ignored():
    mc._handle_telemetry(b"bad json {{{")
    assert len(mc.device_states) == 0


def test_telemetry_adds_timestamp_to_state():
    mc._handle_telemetry(raw(id="m1", type="meter", status="online", voltage=230.0))
    assert "_ts" in mc.device_states["m1"]


def test_telemetry_appends_voltage_history_for_meter():
    mc._handle_telemetry(raw(id="m1", type="meter", status="online", voltage=230.0))
    assert len(mc.metric_history["m1"]) == 1
    _, value = mc.metric_history["m1"][0]
    assert value == 230.0


def test_telemetry_appends_output_power_for_inverter():
    mc._handle_telemetry(raw(id="inv1", type="inverter", status="online", output_power=4.5))
    _, value = mc.metric_history["inv1"][0]
    assert value == 4.5


def test_telemetry_appends_power_for_ev_charger():
    mc._handle_telemetry(raw(id="ev1", type="ev_charger", status="online", power=11.0))
    _, value = mc.metric_history["ev1"][0]
    assert value == 11.0


def test_telemetry_appends_load_mw_for_substation():
    mc._handle_telemetry(raw(id="sub1", type="substation", status="online", load_mw=5.5))
    _, value = mc.metric_history["sub1"][0]
    assert value == 5.5


def test_telemetry_tracks_transformer_temp_for_substation():
    mc._handle_telemetry(raw(id="sub1", type="substation", status="online",
                              load_mw=5.0, transformer_temp=68.5))
    assert len(mc.temp_history["sub1"]) == 1
    _, temp = mc.temp_history["sub1"][0]
    assert temp == 68.5


def test_telemetry_skips_temp_history_for_non_substation():
    mc._handle_telemetry(raw(id="m1", type="meter", status="online", transformer_temp=68.5))
    assert len(mc.temp_history["m1"]) == 0


def test_telemetry_wiper_clears_metric_history():
    mc.metric_history["sub1"].extend([("12:00:00", 5.0), ("12:00:01", 5.1)])
    mc._handle_telemetry(raw(id="sub1", type="substation", status="wiped",
                              _wiped=True, load_mw=0.0))
    assert len(mc.metric_history["sub1"]) == 0


def test_telemetry_wiper_does_not_append_metric():
    mc._handle_telemetry(raw(id="sub1", type="substation", status="wiped",
                              _wiped=True, load_mw=0.0))
    assert len(mc.metric_history["sub1"]) == 0


def test_telemetry_metric_history_maxlen_90():
    for i in range(95):
        mc._handle_telemetry(raw(id="m1", type="meter", status="online", voltage=float(i)))
    assert len(mc.metric_history["m1"]) == 90


def test_telemetry_none_value_not_appended_to_history():
    mc._handle_telemetry(raw(id="sub1", type="substation", status="encrypted",
                              load_mw=None))
    assert len(mc.metric_history["sub1"]) == 0


# ── Status transition logging ─────────────────────────────────────────────────

def test_status_transition_logged_on_fault():
    mc.device_states["m1"] = {"status": "online"}
    mc._handle_telemetry(raw(id="m1", type="meter", status="fault"))
    assert any(e["source"] == "M1" for e in mc.event_log)


def test_status_transition_not_logged_when_returning_to_online():
    mc.device_states["m1"] = {"status": "fault"}
    mc._handle_telemetry(raw(id="m1", type="meter", status="online"))
    assert len(mc.event_log) == 0


def test_status_transition_not_logged_when_status_unchanged():
    mc.device_states["m1"] = {"status": "fault"}
    mc._handle_telemetry(raw(id="m1", type="meter", status="fault"))
    assert len(mc.event_log) == 0


def test_status_transition_logged_for_no_grid():
    mc.device_states["m1"] = {"status": "online"}
    mc._handle_telemetry(raw(id="m1", type="meter", status="no_grid",
                              _cascaded_from="sub-01", _cascade_reason="de-energised"))
    events = list(mc.event_log)
    assert any("sub-01" in e.get("message", "") for e in events)


# ── _status_severity ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("status,expected", [
    ("fault",   "CRITICAL"),
    ("offline", "CRITICAL"),
    ("no_grid", "CRITICAL"),
    ("wiped",   "CRITICAL"),
    ("encrypted", "WARNING"),
    ("compromised", "WARNING"),
])
def test_status_severity_mapping(status, expected):
    assert mc._status_severity(status) == expected


# ── _status_message ───────────────────────────────────────────────────────────

def test_status_message_wiped_mentions_wiper():
    msg = mc._status_message({"status": "wiped"})
    assert "wiper" in msg.lower() or "dark" in msg.lower()


def test_status_message_no_grid_includes_parent_substation():
    msg = mc._status_message({"status": "no_grid", "_cascaded_from": "substation-01"})
    assert "substation-01" in msg


def test_status_message_fault_includes_alarm_names():
    msg = mc._status_message({"status": "fault", "alarms": ["CASCADING_FAILURE"]})
    assert "CASCADING_FAILURE" in msg


def test_status_message_fault_with_no_alarms():
    msg = mc._status_message({"status": "fault", "alarms": []})
    assert "none" in msg.lower()


def test_status_message_offline():
    msg = mc._status_message({"status": "offline"})
    assert "offline" in msg.lower()


def test_status_message_unknown_status():
    msg = mc._status_message({"status": "custom_state"})
    assert "custom_state" in msg


# ── Thread-safe accessors ─────────────────────────────────────────────────────

def test_get_states_returns_shallow_copy():
    mc.device_states["x"] = {"status": "online"}
    result = mc.get_states()
    result["y"] = {"status": "added"}
    assert "y" not in mc.device_states


def test_get_events_returns_plain_list():
    mc.event_log.append({"msg": "a"})
    result = mc.get_events()
    assert isinstance(result, list)
    result.append({"msg": "b"})
    assert len(mc.event_log) == 1  # original deque unaffected


def test_get_metric_history_returns_list_values():
    mc.metric_history["m1"].append(("12:00", 5.0))
    result = mc.get_metric_history()
    assert isinstance(result["m1"], list)
    assert result["m1"] == [("12:00", 5.0)]


def test_get_temp_history_returns_list_values():
    mc.temp_history["sub1"].append(("12:00", 68.5))
    result = mc.get_temp_history()
    assert isinstance(result["sub1"], list)
    assert result["sub1"] == [("12:00", 68.5)]
