"""Attack engine: a transparent MQTT proxy that rewrites device telemetry.

Devices publish to devices/#; this republishes to shadow/# after applying any
active attacks. A faulted substation stays faulted while a fault-inducing
attack is active, and alarms go out on events/alarms for the dashboard.
"""

import asyncio
import json
import random
from datetime import datetime

import aiomqtt
import yaml

BROKER_HOST = "localhost"
BROKER_PORT = 1883

_active_attacks: dict[str, list[dict]] = {}
_device_states: dict[str, dict] = {}
_topology: dict[str, list[str]] = {}
_faulted_substations: set[str] = set()
_frozen_states: dict[str, dict] = {}
_homes_map: dict[str, int] = {}
_thermal_accumulation: dict[str, float] = {}  # device_id -> degrees C above baseline
_aurora_ticks: dict[str, int] = {}  # device_id -> tick counter
_background_tasks: set = set()  # strong refs to staged-transition tasks


def _load_yaml(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f) or {}


def load_attacks(path: str = "config/attacks.yaml") -> dict:
    config = _load_yaml(path)
    return {a["id"]: a for a in config.get("attacks", [])}


def load_topology(path: str = "config/devices.yaml") -> dict[str, list[str]]:
    config = _load_yaml(path)
    topology: dict[str, list[str]] = {}
    for d in config.get("devices", []):
        parent = d.get("connected_to")
        if parent:
            topology.setdefault(parent, []).append(d["id"])
    return topology


def load_homes(path: str = "config/devices.yaml") -> dict[str, int]:
    config = _load_yaml(path)
    return {d["id"]: d.get("homes_per_feeder", 80)
            for d in config.get("devices", []) if d.get("type") == "substation"}


def _get_parent(device_id: str) -> str | None:
    # TODO(pre-demo): linear scan every message. fine for 11 devices, but if we
    # ever load a real feeder topology this wants an inverted dict built once.
    for sub_id, children in _topology.items():
        if device_id in children:
            return sub_id
    return None


def _has_fault_attack(device_id: str) -> bool:
    return any(a.get("type") in ("cascading_failure", "shutdown", "wiper", "thermal_stress")
               for a in _active_attacks.get(device_id, []))


def _homes_behind(sub_id: str, homes_map: dict | None = None) -> int:
    # _device_states holds what the simulator sent, so feeders_active is still
    # the real count even while the shadow copy says 0.
    feeders = _device_states.get(sub_id, {}).get("feeders_active", 6)
    hpf = (_homes_map if homes_map is None else homes_map).get(sub_id, 80)
    return feeders * hpf


async def _event(client, severity: str, source: str, message: str):
    await client.publish("events/alarms", json.dumps({
        "time": datetime.now().strftime("%H:%M:%S"),
        "severity": severity,
        "source": source,
        "message": message,
    }))


_ATTACK_EVENTS = {
    "spoofing": (
        "WARNING",
        "Telemetry falsified. Operator view no longer matches the physical grid.",
    ),
    "shutdown": (
        "CRITICAL",
        "Device forced offline by an unauthorised session. No local override.",
    ),
    "demand_spike": (
        "WARNING",
        "False load report injected. Load-shedding relays may trip incorrectly.",
    ),
    "frequency_attack": (
        "CRITICAL",
        "Frequency manipulated outside the 49-51 Hz band. Protection relays may trip.",
    ),
    "replay": (
        "WARNING",
        "Replay attack: device is publishing a stale snapshot. Real state is masked.",
    ),
    "wiper": (
        "CRITICAL",
        "Wiper payload deployed. Config, logs and firmware overwritten. Device unresponsive.",
    ),
    "relay_bypass": (
        "CRITICAL",
        "Protection relay overridden. Overcurrent/overvoltage trips disabled.",
    ),
    "safety_bypass": (
        "CRITICAL",
        "Safety instrumented system overridden (Triton/TRISIS). No safe-state on fault.",
    ),
    "cascading_failure": (
        "CRITICAL",
        "Cascading fault injected. Breaker trip sequence started; feeders de-energising.",
    ),
    "thermal_stress": (
        "WARNING",
        "Transformer cooling setpoint falsified (Stuxnet-style). Temperature climbing.",
    ),
    "ransomware": (
        "CRITICAL",
        "Ransomware deployed. Config and firmware encrypted, telemetry suspended.",
    ),
    "modbus_write": (
        "WARNING",
        "Unauthorised Modbus write. Setpoint overwritten; device off SCADA control.",
    ),
    "aurora": (
        "CRITICAL",
        "Aurora attack: out-of-phase breaker switching. Generator oscillating (INL, 2007).",
    ),
}


def apply_attacks(device_id: str, payload: dict) -> dict:
    attacks = _active_attacks.get(device_id, [])
    if not attacks:
        return payload
    for attack in attacks:
        payload = _apply_single(attack, payload)
    payload["_compromised"] = True
    return payload


def _apply_single(attack: dict, payload: dict) -> dict:
    t = attack.get("type")
    params = attack.get("params", {})

    if t == "spoofing":
        dev = params.get("max_deviation", 10) / 100
        for key in ("voltage", "power", "current", "output_power", "ac_voltage", "dc_voltage"):
            if key in payload and payload[key]:
                payload[key] = round(payload[key] * (1 + random.uniform(-dev, dev)), 3)

    elif t == "shutdown":
        payload["status"] = "offline"
        for key in ("power", "output_power", "load_mw"):
            if key in payload:
                payload[key] = 0.0

    elif t == "cascading_failure":
        # Deterministic while active; cascade state lives in _faulted_substations.
        payload["status"] = "fault"
        payload["feeders_active"] = 0
        payload["load_mw"] = 0.0
        payload.setdefault("alarms", []).append("CASCADING_FAILURE")

    elif t == "modbus_write":
        reg = params.get("register")
        if reg and reg in payload:
            payload[reg] = params.get("value", 0)

    elif t == "demand_spike":
        mul = params.get("multiplier", 3.0)
        for key in ("power", "output_power", "load_mw", "current"):
            if key in payload and payload[key] and payload[key] > 0:
                payload[key] = round(payload[key] * mul, 3)

    elif t == "frequency_attack":
        if "frequency" in payload:
            payload["frequency"] = round(
                params.get("target_frequency", 47.5) + random.gauss(0, 0.05), 3)

    elif t == "replay":
        dev_id = payload.get("id")
        if dev_id is None:
            return payload
        if dev_id not in _frozen_states:
            _frozen_states[dev_id] = dict(payload)
        else:
            frozen = dict(_frozen_states[dev_id])
            frozen["_compromised"] = True
            return frozen

    elif t == "wiper":
        payload["status"] = "wiped"
        payload["_wiped"] = True
        for key in list(payload.keys()):
            if isinstance(payload[key], (int, float)) and not isinstance(payload[key], bool):
                payload[key] = 0.0

    elif t == "relay_bypass":
        payload["protection_online"] = False
        payload.setdefault("alarms", []).append("PROTECTION_RELAY_OFFLINE")

    elif t == "safety_bypass":
        payload["safety_system"] = "offline"
        payload.setdefault("alarms", []).append("SIS_OFFLINE")

    elif t == "thermal_stress":
        # Heat the transformer each tick until thermal protection trips.
        device_id = payload.get("id", "")
        rate = params.get("rate", 2.0)
        threshold = params.get("trip_threshold", 112.0)
        _thermal_accumulation[device_id] = _thermal_accumulation.get(device_id, 0.0) + rate
        if "transformer_temp" in payload:
            payload["transformer_temp"] = round(
                payload["transformer_temp"] + _thermal_accumulation[device_id], 1)
        if payload.get("transformer_temp", 0) >= threshold:
            payload["status"] = "fault"
            payload["feeders_active"] = 0
            payload["load_mw"] = 0.0
            payload.setdefault("alarms", []).append(
                f"THERMAL_OVERLOAD_TRIP_{payload['transformer_temp']:.0f}C")

    elif t == "ransomware":
        payload["status"] = "encrypted"
        payload["_ransomware"] = True
        for key in ("voltage", "current", "power", "output_power", "load_mw"):
            if key in payload:
                payload[key] = None

    elif t == "aurora":
        # Out-of-phase breaker cycling; after 8 ticks the generator trips for good.
        device_id = payload.get("id", "")
        _aurora_ticks[device_id] = _aurora_ticks.get(device_id, 0) + 1
        tick = _aurora_ticks[device_id]
        if tick >= 8:
            payload["status"] = "fault"
            for key in ("output_power", "power", "ac_voltage", "dc_voltage"):
                if key in payload:
                    payload[key] = 0.0
            payload.setdefault("alarms", []).append(f"AURORA_GENERATOR_TRIP_TICK{tick}")
        else:
            if tick % 2 == 0:
                for key in ("output_power", "power"):
                    if key in payload and payload[key] is not None:
                        payload[key] = round(payload[key] * 2.8, 3)  # reconnection surge
            else:
                for key in ("output_power", "power"):
                    if key in payload:
                        payload[key] = 0.0  # breaker open

    return payload


async def _activate_single(sub_id: str, all_attacks: dict) -> None:
    if sub_id not in all_attacks:
        return
    sub = all_attacks[sub_id]
    target = sub.get("target", "_meta")
    if sub.get("type") in ("coordinated", "staged"):
        await _handle_meta(sub, "trigger", all_attacks)
        return
    _active_attacks.setdefault(target, [])
    if sub not in _active_attacks[target]:
        _active_attacks[target].append(sub)


async def _deactivate_single(sub_id: str, all_attacks: dict) -> None:
    if sub_id not in all_attacks:
        return
    sub = all_attacks[sub_id]
    target = sub.get("target", "_meta")
    if sub.get("type") in ("coordinated", "staged"):
        await _handle_meta(sub, "stop", all_attacks)
        return
    _clear_attack(sub, target)


async def _handle_coordinated(attack: dict, action: str, all_attacks: dict, client=None) -> None:
    sub_items = attack.get("params", {}).get("attacks", [])
    resolved_ids: list[str] = []

    for item in sub_items:
        if isinstance(item, str):
            resolved_ids.append(item)
        else:
            # Inline attack definition: register it under a stable synthetic id.
            synthetic_id = f"_inline_{attack['id']}_{item['target']}"
            all_attacks[synthetic_id] = {
                "id": synthetic_id,
                "type": item["type"],
                "target": item["target"],
                "params": item.get("params", {}),
            }
            resolved_ids.append(synthetic_id)

    for sub_id in resolved_ids:
        if action == "trigger":
            await _activate_single(sub_id, all_attacks)
        else:
            await _deactivate_single(sub_id, all_attacks)

    verb = "TRIGGERED" if action == "trigger" else "STOPPED"
    print(f"[engine] coordinated '{attack['id']}' {verb} ({len(resolved_ids)} sub-attacks)")

    if client and action == "trigger":
        targets = ", ".join(
            all_attacks[s]["target"] for s in resolved_ids
            if s in all_attacks and all_attacks[s].get("target") != "_meta"
        )
        await _event(client, "CRITICAL", "SYSTEM",
                     f"Coordinated strike across {len(resolved_ids)} targets "
                     f"[{targets}]. Ukraine 2015 pattern.")


async def _handle_staged(attack: dict, action: str, all_attacks: dict, client=None) -> None:
    params = attack.get("params", {})
    phase_1 = params.get("phase_1", {})
    phase_2 = params.get("phase_2", {})
    p1_ids = phase_1.get("attack_ids", [])
    p1_duration = phase_1.get("duration", 30)
    p2_ids = phase_2.get("attack_ids", [])

    if action == "trigger":
        for sub_id in p1_ids:
            await _activate_single(sub_id, all_attacks)
        print(f"[engine] staged '{attack['id']}' PHASE 1 - {p1_duration}s dwell")

        if client:
            dwell_targets = ", ".join(
                all_attacks[s]["target"] for s in p1_ids if s in all_attacks
            )
            await _event(client, "INFO", "SYSTEM",
                         f"Staged attack phase 1 active. {p1_duration}s dwell. "
                         f"Replay/spoofing on [{dwell_targets}]; grid state masked.")

        async def _transition():
            await asyncio.sleep(p1_duration)
            for sub_id in p1_ids:
                await _deactivate_single(sub_id, all_attacks)
            for sub_id in p2_ids:
                await _activate_single(sub_id, all_attacks)
            print(f"[engine] staged '{attack['id']}' PHASE 2 EXECUTED")
            if client:
                strike_targets = ", ".join(
                    all_attacks[s]["target"] for s in p2_ids if s in all_attacks
                )
                await _event(client, "CRITICAL", "SYSTEM",
                             f"Phase 2 executed - dwell ended. Strike on "
                             f"[{strike_targets}]. Operators had no warning.")

        task = asyncio.create_task(_transition())
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

    elif action == "stop":
        for sub_id in p1_ids + p2_ids:
            await _deactivate_single(sub_id, all_attacks)
        print(f"[engine] staged '{attack['id']}' STOPPED")


async def _handle_meta(attack: dict, action: str, all_attacks: dict, client=None) -> None:
    if attack.get("type") == "coordinated":
        await _handle_coordinated(attack, action, all_attacks, client)
    elif attack.get("type") == "staged":
        await _handle_staged(attack, action, all_attacks, client)


def _clear_attack(attack: dict, target: str) -> None:
    if target in _active_attacks:
        _active_attacks[target] = [a for a in _active_attacks[target] if a != attack]
    if attack.get("type") == "replay":
        _frozen_states.pop(target, None)
    if attack.get("type") == "thermal_stress":
        _thermal_accumulation.pop(target, None)
    if attack.get("type") == "aurora":
        _aurora_ticks.pop(target, None)


# Fault-inducing attacks get an immediate substation publish on trigger, so the
# operator view faults without waiting for the next publish cycle. Each maps to
# the (status, alarm) that matches its steady-state semantics.
_FAULT_IMMEDIATE = {
    "cascading_failure": ("fault", "CASCADING_FAILURE"),
    "shutdown": ("offline", "DEVICE_OFFLINE"),
    "wiper": ("wiped", "WIPER_DEPLOYED"),
}


async def handle_control(payload: bytes, all_attacks: dict, client=None) -> None:
    try:
        cmd = json.loads(payload)
    except json.JSONDecodeError:
        return

    attack_id = cmd.get("attack_id")
    action = cmd.get("action", "trigger")

    if attack_id not in all_attacks:
        print(f"[engine] unknown attack_id: {attack_id}")
        return

    attack = all_attacks[attack_id]

    if attack.get("type") in ("coordinated", "staged"):
        await _handle_meta(attack, action, all_attacks, client)
        return

    target = attack["target"]
    a_type = attack.get("type")

    if action == "trigger":
        _active_attacks.setdefault(target, [])
        if attack not in _active_attacks[target]:
            _active_attacks[target].append(attack)
            print(f"[engine] '{attack_id}' ACTIVE on {target}")
            if client and a_type in _ATTACK_EVENTS:
                sev, msg = _ATTACK_EVENTS[a_type]
                await _event(client, sev, target.upper(), msg)

            # shutdown-ev-* is a shutdown too; a charger just waits for its next tick
            last_sub = _device_states.get(target)
            is_substation = last_sub is None or last_sub.get("type", "substation") == "substation"
            if a_type in _FAULT_IMMEDIATE and is_substation:
                _faulted_substations.add(target)
                if last_sub and client:
                    status, alarm = _FAULT_IMMEDIATE[a_type]
                    fault_payload = {
                        **last_sub,
                        "status": status,
                        "feeders_active": 0,
                        "load_mw": 0.0,
                        "_compromised": True,
                        "_homes_lost": _homes_behind(target),
                        "alarms": [alarm],
                    }
                    if a_type == "wiper":
                        fault_payload["_wiped"] = True
                    sub_type = last_sub.get("type", "substation")
                    await client.publish(
                        f"shadow/devices/{sub_type}/{target}/state",
                        json.dumps(fault_payload),
                    )
                    await cascade_to_connected(client, target, _homes_map)

    elif action == "stop":
        _clear_attack(attack, target)
        if a_type in ("cascading_failure", "shutdown", "wiper", "thermal_stress") \
                and not _has_fault_attack(target):
            _faulted_substations.discard(target)
            _thermal_accumulation.pop(target, None)
        print(f"[engine] '{attack_id}' STOPPED on {target}")
        if client:
            await _event(client, "INFO", target.upper(),
                         f"Attack '{attack_id}' [{a_type}] stopped. "
                         f"Device returning to normal operation.")


async def cascade_to_connected(client, substation_id: str, homes_map: dict) -> None:
    # once the parent trips, the children go dark faster than an operator can
    # react. propogation here is instant, we publish the shadow.
    connected = _topology.get(substation_id, [])
    homes = _homes_behind(substation_id, homes_map)

    for device_id in connected:
        last = _device_states.get(device_id)
        if last is None:
            continue
        cascade = {**last, "status": "no_grid", "_compromised": True,
                   "_cascaded_from": substation_id}
        for key in ("voltage", "current", "power", "output_power",
                    "ac_voltage", "dc_voltage", "frequency", "load_mw"):
            if key in cascade:
                cascade[key] = 0.0
        if "charging" in cascade:
            cascade["charging"] = False
        shadow_topic = f"shadow/devices/{last.get('type', 'meter')}/{device_id}/state"
        await client.publish(shadow_topic, json.dumps(cascade))

    if connected:
        print(f"[engine] cascade {substation_id} -> {connected}")
        await _event(
            client, "CRITICAL", substation_id.upper(),
            f"Substation fault propagated to {len(connected)} connected devices: "
            f"[{', '.join(connected)}]. Grid section de-energised. "
            f"About {homes:,} homes without power."
        )


async def main():
    all_attacks = load_attacks()
    _homes_map.update(load_homes())
    _topology.update(load_topology())
    print(f"[engine] {len(all_attacks)} attacks | topology: {dict(_topology)}")
    print(f"[engine] connecting to {BROKER_HOST}:{BROKER_PORT}")

    async with aiomqtt.Client(hostname=BROKER_HOST, port=BROKER_PORT) as client:
        await client.subscribe("devices/#")
        await client.subscribe("control/attacks/#")
        print("[engine] proxy running")

        async for message in client.messages:
            topic = str(message.topic)

            if topic.startswith("control/attacks/"):
                await handle_control(message.payload, all_attacks, client)
                continue

            if not topic.startswith("devices/"):
                continue

            try:
                payload = json.loads(message.payload)
            except json.JSONDecodeError:
                continue

            device_id = payload.get("id")
            device_type = payload.get("type")
            if not device_id:
                continue

            _device_states[device_id] = payload
            # print(f"[dbg] {device_id} -> {payload.get('status')}")  # left over from the frostygoop trace, keep handy

            parent = _get_parent(device_id)
            if parent and parent in _faulted_substations:
                parent_state = _device_states.get(parent, {})
                cascade_reason = "wiped - upstream device dark, breakers open" \
                    if parent_state.get("status") == "wiped" else "de-energised"
                modified = {**payload, "status": "no_grid", "_compromised": True,
                            "_cascaded_from": parent,
                            "_cascade_reason": cascade_reason}
                for key in ("voltage", "current", "power", "output_power",
                            "ac_voltage", "dc_voltage", "frequency", "load_mw"):
                    if key in modified:
                        modified[key] = 0.0
                if "charging" in modified:
                    modified["charging"] = False
            else:
                modified = apply_attacks(device_id, dict(payload))

            if device_type == "substation" and modified.get("status") in ("fault", "offline", "wiped"):
                modified["_homes_lost"] = _homes_behind(device_id)

            await client.publish(f"shadow/{topic}", json.dumps(modified))

            if device_type == "substation":
                if (modified.get("status") in ("fault", "offline", "wiped")
                        and modified.get("feeders_active", 1) == 0
                        and device_id not in _faulted_substations):
                    _faulted_substations.add(device_id)
                    await cascade_to_connected(client, device_id, _homes_map)

                elif device_id in _faulted_substations:
                    if not _has_fault_attack(device_id):
                        _faulted_substations.discard(device_id)
                        _thermal_accumulation.pop(device_id, None)
                        print(f"[engine] {device_id} recovered")
                        await _event(client, "INFO", device_id.upper(),
                                     "Substation returning to normal operation. "
                                     "Connected devices will restore on next publish cycle.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[engine] shutting down")
