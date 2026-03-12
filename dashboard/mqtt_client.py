"""
Background MQTT client for the dashboard.

Subscribes to:
  shadow/devices/#   — device telemetry (modified by attack engine)
  events/alarms      — structured SCADA-style alarms from the engine
"""

import json
import threading
from collections import deque, defaultdict
from datetime import datetime

import paho.mqtt.client as mqtt

_DEVICE_METRIC = {
    "meter":      "voltage",
    "ev_charger": "power",
    "inverter":   "output_power",
    "substation": "load_mw",
}

device_states:  dict  = {}
event_log:      deque = deque(maxlen=80)
metric_history: dict  = defaultdict(lambda: deque(maxlen=90))
temp_history:   dict  = defaultdict(lambda: deque(maxlen=90))  # substation transformer_temp
_lock = threading.Lock()

_client = None


# ── Public read accessors ───────────────────────────────────────────────────

def get_states() -> dict:
    with _lock:
        return dict(device_states)


def get_events() -> list:
    with _lock:
        return list(event_log)


def get_metric_history() -> dict:
    with _lock:
        return {k: list(v) for k, v in metric_history.items()}


def get_temp_history() -> dict:
    with _lock:
        return {k: list(v) for k, v in temp_history.items()}


def publish(topic: str, payload: dict) -> None:
    if _client:
        _client.publish(topic, json.dumps(payload))


# ── MQTT callbacks ──────────────────────────────────────────────────────────

def _on_message(client, userdata, msg):
    topic = msg.topic

    if topic == "events/alarms":
        _handle_alarm(msg.payload)
        return

    if topic.startswith("shadow/devices/"):
        _handle_telemetry(msg.payload)


def _handle_alarm(raw: bytes) -> None:
    try:
        event = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return

    with _lock:
        event_log.append({
            "time":     event.get("time", datetime.now().strftime("%H:%M:%S")),
            "source":   event.get("source", "SYSTEM"),
            "severity": event.get("severity", "INFO"),
            "message":  event.get("message", ""),
            "engine":   True,   # rendered differently — full message, not inferred
        })


def _handle_telemetry(raw: bytes) -> None:
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return

    device_id = payload.get("id")
    if not device_id:
        return

    ts = datetime.now()

    with _lock:
        prev_status = device_states.get(device_id, {}).get("status")
        device_states[device_id] = {**payload, "_ts": ts.isoformat()}

        if payload.get("_wiped"):
            metric_history[device_id].clear()

        device_type = payload.get("type", "")
        field = _DEVICE_METRIC.get(device_type)
        if field and not payload.get("_wiped"):
            value = payload.get(field)
            if value is not None:
                metric_history[device_id].append((ts.strftime("%H:%M:%S"), float(value)))

        # Track transformer temperature for substations (shows Stuxnet heat-up)
        if device_type == "substation" and not payload.get("_wiped"):
            temp = payload.get("transformer_temp")
            if temp is not None:
                temp_history[device_id].append((ts.strftime("%H:%M:%S"), float(temp)))

        # Only log status transitions — engine events carry the detail
        new_status = payload.get("status", "online")
        if new_status != prev_status and new_status not in ("online",):
            event_log.append({
                "time":     ts.strftime("%H:%M:%S"),
                "source":   device_id.upper(),
                "severity": _status_severity(new_status),
                "message":  _status_message(payload),
                "engine":   False,
            })


def _status_severity(status: str) -> str:
    return {
        "fault":   "CRITICAL",
        "offline": "CRITICAL",
        "no_grid": "CRITICAL",
        "wiped":   "CRITICAL",
    }.get(status, "WARNING")


def _status_message(payload: dict) -> str:
    status = payload.get("status", "online")
    if status == "wiped":
        return "Device went dark — no telemetry. Possible wiper."
    if status == "no_grid":
        reason = payload.get("_cascade_reason", "de-energised")
        return f"Supply lost. Substation {payload.get('_cascaded_from', '?')} {reason}."
    if status == "fault":
        alarms = payload.get("alarms", [])
        return f"Fault state. Alarms: {', '.join(alarms) if alarms else 'none recorded'}."
    if status == "offline":
        return "Device offline. Last known state preserved."
    return f"Status changed to {status}."


# ── Start ───────────────────────────────────────────────────────────────────

def start(host: str = "localhost", port: int = 1883) -> None:
    global _client
    try:
        _client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    except AttributeError:
        _client = mqtt.Client()
    _client.on_message = _on_message
    _client.connect(host, port)
    _client.subscribe("shadow/devices/#")
    _client.subscribe("events/alarms")
    thread = threading.Thread(target=_client.loop_forever, daemon=True)
    thread.start()
    print(f"[dashboard] MQTT connected to {host}:{port}")
