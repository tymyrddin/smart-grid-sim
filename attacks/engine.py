"""
Attack Engine — transparent MQTT proxy with full nation-state attack support.

Cascade fix: once a substation is faulted, it stays faulted while any
fault-inducing attack is active — regardless of per-tick probability rolls.

Events: publishes to events/alarms so the dashboard can show realistic
SCADA-style alarm messages rather than inferring them from status changes.
"""

import asyncio
import json
import random
import yaml
from datetime import datetime
import aiomqtt

BROKER_HOST = "localhost"
BROKER_PORT = 1883

_active_attacks:       dict[str, list[dict]] = {}
_device_states:        dict[str, dict]       = {}
_topology:             dict[str, list[str]]  = {}
_faulted_substations:  set[str]              = set()
_frozen_states:        dict[str, dict]       = {}
_homes_map:            dict[str, int]        = {}
_thermal_accumulation: dict[str, float]      = {}  # device_id -> accumulated °C above baseline
_aurora_ticks:         dict[str, int]        = {}  # device_id -> tick counter for Aurora attack


# ── Config loading ──────────────────────────────────────────────────────────

def load_attacks(path: str = "config/attacks.yaml") -> dict:
    with open(path) as f:
        config = yaml.safe_load(f)
    return {a["id"]: a for a in config.get("attacks", [])}


def load_topology(path: str = "config/devices.yaml") -> dict[str, list[str]]:
    with open(path) as f:
        config = yaml.safe_load(f)
    topology: dict[str, list[str]] = {}
    for d in config.get("devices", []):
        parent = d.get("connected_to")
        if parent:
            topology.setdefault(parent, []).append(d["id"])
    return topology


def load_homes(path: str = "config/devices.yaml") -> dict[str, int]:
    with open(path) as f:
        config = yaml.safe_load(f)
    return {d["id"]: d.get("homes_per_feeder", 80)
            for d in config.get("devices", []) if d.get("type") == "substation"}


def _get_parent(device_id: str) -> str | None:
    for sub_id, children in _topology.items():
        if device_id in children:
            return sub_id
    return None


def _has_fault_attack(device_id: str) -> bool:
    return any(a.get("type") in ("cascading_failure", "shutdown", "wiper", "thermal_stress")
               for a in _active_attacks.get(device_id, []))


# ── Event publishing ────────────────────────────────────────────────────────

async def _event(client, severity: str, source: str, message: str):
    await client.publish("events/alarms", json.dumps({
        "time":     datetime.now().strftime("%H:%M:%S"),
        "severity": severity,   # CRITICAL | WARNING | INFO
        "source":   source,
        "message":  message,
    }))


_ATTACK_EVENTS = {
    "spoofing": (
        "WARNING",
        "Telemetry manipulation active. Sensor readings falsified. "
        "SCADA operator view no longer reflects physical grid state."
    ),
    "shutdown": (
        "CRITICAL",
        "Remote shutdown command issued via unauthorised session. "
        "Device forced offline. No local override attempted."
    ),
    "demand_spike": (
        "WARNING",
        "False load report injected. Demand readings inflated. "
        "Automatic load-shedding relay may activate incorrectly."
    ),
    "frequency_attack": (
        "CRITICAL",
        "Grid frequency manipulation active. Reporting value outside 49–51 Hz safe band. "
        "Under/over-frequency protection relays at risk of spurious trip."
    ),
    "replay": (
        "WARNING",
        "Data replay attack initiated. Device publishing stale snapshot. "
        "Real grid state masked from operators — any ongoing fault is invisible."
    ),
    "wiper": (
        "CRITICAL",
        "Destructive wiper payload deployed. Configuration, logs, and firmware "
        "checksum being overwritten. Device will become unresponsive. Anti-forensics active."
    ),
    "relay_bypass": (
        "CRITICAL",
        "Protection relay override command accepted. Overcurrent and overvoltage "
        "trip functions DISABLED. Physical damage to transformer or bus now possible."
    ),
    "safety_bypass": (
        "CRITICAL",
        "Safety Instrumented System override sent. SIS vote logic bypassed. "
        "Triton/TRISIS-style attack: no automatic safe-state on fault. "
        "Physical destruction of equipment now possible."
    ),
    "cascading_failure": (
        "CRITICAL",
        "Cascading fault injection initiated. Breaker trip sequence triggered on bus. "
        "Connected feeders will de-energise."
    ),
    "thermal_stress": (
        "WARNING",
        "Thermal manipulation active (Stuxnet-style). Transformer cooling setpoint falsified. "
        "Temperature rising beyond rated limits. Thermal protection trip imminent."
    ),
    "ransomware": (
        "CRITICAL",
        "RANSOMWARE DEPLOYED. Device configuration and firmware encrypted. "
        "All telemetry suspended. Manual restoration required. "
        "Attacker demands payment before decryption key released."
    ),
    "modbus_write": (
        "WARNING",
        "Unauthorised Modbus write to control register. "
        "Setpoint overwritten — device no longer following SCADA commands."
    ),
    "aurora": (
        "CRITICAL",
        "Aurora-class attack active. Out-of-phase breaker switching commands injected. "
        "Generator output oscillating violently. Rotor subject to mechanical stress. "
        "Physical destruction imminent — Idaho National Laboratory vulnerability (2007)."
    ),
}


# ── Single-device attack application ───────────────────────────────────────

def apply_attacks(device_id: str, payload: dict) -> dict:
    attacks = _active_attacks.get(device_id, [])
    if not attacks:
        return payload
    for attack in attacks:
        payload = _apply_single(attack, payload)
    payload["_compromised"] = True
    return payload


def _apply_single(attack: dict, payload: dict) -> dict:
    t      = attack.get("type")
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
        # Deterministic while active — cascade state managed by _faulted_substations
        payload["status"]         = "fault"
        payload["feeders_active"] = 0
        payload["load_mw"]        = 0.0
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
        if dev_id not in _frozen_states:
            _frozen_states[dev_id] = dict(payload)
        else:
            frozen = dict(_frozen_states[dev_id])
            frozen["_compromised"] = True
            return frozen

    elif t == "wiper":
        payload["status"]  = "wiped"
        payload["_wiped"]  = True
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
        # Stuxnet-style: gradually overheat transformer until thermal protection trips
        device_id = payload.get("id", "")
        rate = params.get("rate", 2.0)          # °C added per substation publish tick
        threshold = params.get("trip_threshold", 112.0)
        _thermal_accumulation[device_id] = _thermal_accumulation.get(device_id, 0.0) + rate
        if "transformer_temp" in payload:
            payload["transformer_temp"] = round(
                payload["transformer_temp"] + _thermal_accumulation[device_id], 1)
        if payload.get("transformer_temp", 0) >= threshold:
            payload["status"]         = "fault"
            payload["feeders_active"] = 0
            payload["load_mw"]        = 0.0
            payload.setdefault("alarms", []).append(
                f"THERMAL_OVERLOAD_TRIP_{payload['transformer_temp']:.0f}C")

    elif t == "ransomware":
        payload["status"] = "encrypted"
        payload["_ransomware"] = True
        for key in ("voltage", "current", "power", "output_power", "load_mw"):
            if key in payload:
                payload[key] = None

    elif t == "aurora":
        # Aurora 2007: rapid out-of-phase breaker cycling → violent output oscillation → physical fault
        device_id = payload.get("id", "")
        _aurora_ticks[device_id] = _aurora_ticks.get(device_id, 0) + 1
        tick = _aurora_ticks[device_id]
        if tick >= 8:
            # Physical destruction — permanent trip
            payload["status"] = "fault"
            for key in ("output_power", "power", "ac_voltage", "dc_voltage"):
                if key in payload:
                    payload[key] = 0.0
            payload.setdefault("alarms", []).append(f"AURORA_GENERATOR_TRIP_TICK{tick}")
        else:
            # Violent oscillation: alternate between surge and zero every tick
            if tick % 2 == 0:
                for key in ("output_power", "power"):
                    if key in payload and payload[key] is not None:
                        payload[key] = round(payload[key] * 2.8, 3)   # reconnection surge
            else:
                for key in ("output_power", "power"):
                    if key in payload:
                        payload[key] = 0.0                              # breaker open

    return payload


# ── Meta-attack handlers ────────────────────────────────────────────────────

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
            # Inline attack definition — synthesise a stable ID and register it
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
                     f"Coordinated simultaneous strike initiated across {len(resolved_ids)} targets "
                     f"[{targets}]. Ukraine 2015-pattern attack detected.")


async def _handle_staged(attack: dict, action: str, all_attacks: dict, client=None) -> None:
    params      = attack.get("params", {})
    phase_1     = params.get("phase_1", {})
    phase_2     = params.get("phase_2", {})
    p1_ids      = phase_1.get("attack_ids", [])
    p1_duration = phase_1.get("duration", 30)
    p2_ids      = phase_2.get("attack_ids", [])

    if action == "trigger":
        for sub_id in p1_ids:
            await _activate_single(sub_id, all_attacks)
        print(f"[engine] staged '{attack['id']}' PHASE 1 — {p1_duration}s dwell")

        if client:
            dwell_targets = ", ".join(
                all_attacks[s]["target"] for s in p1_ids if s in all_attacks
            )
            await _event(client, "INFO", "SYSTEM",
                         f"Staged attack phase 1 active. {p1_duration}s dwell period. "
                         f"Replay/spoofing on [{dwell_targets}] — operators see normal grid state. "
                         f"Actual state is being masked.")

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
                             f"PHASE 2 EXECUTED — dwell period ended. Strike now active on "
                             f"[{strike_targets}]. Operators had no warning — grid state was masked.")

        asyncio.create_task(_transition())

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


# ── Control message handler ─────────────────────────────────────────────────

async def handle_control(payload: bytes, all_attacks: dict, client=None) -> None:
    try:
        cmd = json.loads(payload)
    except json.JSONDecodeError:
        return

    attack_id = cmd.get("attack_id")
    action    = cmd.get("action", "trigger")

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

            # Fault-inducing attacks: immediately fault substation + cascade
            # without waiting for the next substation publish cycle (up to 5s)
            if a_type in ("cascading_failure", "shutdown", "wiper"):
                _faulted_substations.add(target)
                last_sub = _device_states.get(target)
                if last_sub and client:
                    fault_payload = {
                        **last_sub,
                        "status": "fault" if a_type == "cascading_failure" else "offline",
                        "feeders_active": 0,
                        "load_mw": 0.0,
                        "_compromised": True,
                        "alarms": ["CASCADING_FAILURE"],
                    }
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


# ── Cascade ─────────────────────────────────────────────────────────────────

async def cascade_to_connected(client, substation_id: str, homes_map: dict) -> None:
    connected = _topology.get(substation_id, [])
    feeders   = _device_states.get(substation_id, {}).get("feeders_active", 6)
    hpf       = homes_map.get(substation_id, 80)
    homes     = feeders * hpf

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
        print(f"[engine] cascade {substation_id} → {connected}")
        await _event(
            client, "CRITICAL", substation_id.upper(),
            f"Substation fault propagated to {len(connected)} connected devices: "
            f"[{', '.join(connected)}]. Grid section de-energised. "
            f"Estimated {homes:,} homes without power. No automatic restoration active."
        )


# ── Main loop ───────────────────────────────────────────────────────────────

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

            device_id   = payload.get("id")
            device_type = payload.get("type")
            if not device_id:
                continue

            _device_states[device_id] = payload

            # Cascade override: if parent substation is faulted or wiped, device loses grid
            parent = _get_parent(device_id)
            if parent and parent in _faulted_substations:
                parent_state = _device_states.get(parent, {})
                cascade_reason = "wiped — upstream device dark, breakers open" \
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

            await client.publish(f"shadow/{topic}", json.dumps(modified))

            # Cascade management for substations
            if device_type == "substation":
                # Thermal trip: _apply_single sets fault status but doesn't touch _faulted_substations
                if (modified.get("status") in ("fault", "offline", "wiped")
                        and modified.get("feeders_active", 1) == 0
                        and device_id not in _faulted_substations):
                    _faulted_substations.add(device_id)
                    await cascade_to_connected(client, device_id, _homes_map)

                elif device_id in _faulted_substations:
                    if not _has_fault_attack(device_id):
                        # Attack was stopped — allow recovery
                        _faulted_substations.discard(device_id)
                        _thermal_accumulation.pop(device_id, None)
                        print(f"[engine] {device_id} recovered")
                        await _event(client, "INFO", device_id.upper(),
                                     "Substation returning to normal operation. "
                                     "Connected devices will restore on next publish cycle.")
                    # else: still faulted — cascading already handled per-meter-message above


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[engine] shutting down")
