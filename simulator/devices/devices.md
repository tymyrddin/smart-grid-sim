# Device reference

This document explains what each simulated device is, what it does, and how the devices relate to each other.

---

## How the grid is structured

The simulated grid has a simple but realistic topology: two substations, each feeding a group of smaller devices.

```
substation-01 ──┬── meter-001
                ├── meter-002
                ├── meter-003
                ├── inverter-001
                └── ev-charger-001

substation-02 ──┬── meter-004
                ├── meter-005
                ├── inverter-002
                └── ev-charger-002
```

When a substation faults, everything connected to it loses its grid supply immediately. That is what the `NO GRID` status on connected device cards means, not that the device itself has been attacked, but that the power feeding it is gone.

Each device publishes live telemetry every few seconds over MQTT, and the attack engine intercepts that data before the dashboard sees it.

---

## Devices

---

### Smart meters
`meter-001` through `meter-005`

Smart meters measure the electricity flowing into a home or building. They report voltage, current, power consumption, and grid frequency back to the utility's control system in real time.

What they show on the dashboard: voltage (V). Normal household voltage sits around 230 V. The chart for each meter shows this as a fairly steady line with small natural variation.

Why they matter for attacks: meters are the eyes of the control system. If an attacker can falsify meter readings, making voltage look fine when the grid is stressed or showing a crisis that is not there, operators lose the ability to make correct decisions. Meters are also used as data-freeze targets: replaying stale readings masks any ongoing fault from the operator.

Update rate: every second.

| Device | Connected to | Notes |
|---|---|---|
| meter-001 | substation-01 | Primary spoofing target |
| meter-002 | substation-01 | Secondary spoofing target |
| meter-003 | substation-01 | Replay/freeze target |
| meter-004 | substation-02 | |
| meter-005 | substation-02 | |

---

### Solar inverters
`inverter-001`, `inverter-002`

A solar inverter converts the DC power produced by solar panels into AC power that can be fed into the grid. Inverters export electricity when the sun is shining and reduce or stop output at night.

What they show on the dashboard: output power (kW). The chart follows a smooth bell curve across the five-minute simulated day cycle, rising in the morning, peaking at midday, falling to zero at night. Each inverter has a slightly different peak time so they do not overlap perfectly.

Why they matter for attacks: inverters represent distributed generation, power flowing back into the grid from customer premises. Spoofing their output readings distorts the grid's energy balance picture. The Aurora vulnerability specifically targets generator and inverter connections: rapid breaker cycling at the wrong moment causes violent mechanical stress that physically destroys the equipment.

Update rate: every two seconds.

| Device | Connected to | Peak output |
|---|---|---|
| inverter-001 | substation-01 | 4-10 kW (random at startup) |
| inverter-002 | substation-02 | 4-10 kW (random at startup) |

---

### EV chargers
`ev-charger-001`, `ev-charger-002`

Electric vehicle chargers are increasingly significant loads on the local grid. A single fast charger draws as much power as several homes. They start and stop charging sessions as vehicles arrive and depart.

What they show on the dashboard: power draw (kW). Sessions run at 7-22 kW and drift gradually during charging, simulating a real charge curve that slows as the battery fills. Sessions start and stop randomly, so the line drops to zero when no vehicle is connected and resumes when a new session begins.

Why they matter for attacks: EV chargers are high-load devices with network connectivity, making them attractive for demand-spike attacks. Falsely reporting ten times their actual draw can trigger automatic load-shedding that affects the wider grid. Forced shutdown of chargers disrupts vehicle owners and, at scale, destabilises local grid sections.

Update rate: every two seconds.

| Device | Connected to |
|---|---|
| ev-charger-001 | substation-01 |
| ev-charger-002 | substation-02 |

---

### Substations
`substation-01`, `substation-02`

A substation is the distribution hub that takes high-voltage power from the transmission network, steps it down to usable levels, and feeds it to the local area through a set of feeders. Each feeder supplies a group of homes or buildings. The substation also houses the protection relays and, in modern installations, a Safety Instrumented System (SIS), which provides automated safety controls that disconnect equipment if dangerous conditions arise.

What they show on the dashboard:

- Load (MW): total power flowing out to connected customers. Follows a day-cycle pattern between 3-9 MW, with the two substations slightly out of phase with each other.
- Transformer temperature (°C): shown as a dashed orange line when elevated above roughly 70°C. Under normal conditions, the transformer runs around 65°C. Under a Stuxnet-style thermal attack, this line climbs steadily toward the 112°C trip threshold.

Why they matter for attacks: substations are the highest-leverage targets on the grid. Faulting one device takes down everything connected to it, including meters, chargers, inverters, and the homes they serve. A single substation attack can instantly affect hundreds or thousands of customers. They also carry the most critical industrial control components, including protection relays and safety systems, which nation-state attackers specifically target to prevent automatic recovery.

Update rate: every five seconds. The slower update rate is realistic, as substations have more stable readings than edge devices.

| Device | Feeders | Homes per feeder | Total homes |
|---|---|---|---|
| substation-01 | 4-8 (random) | 80 | 320-640 |
| substation-02 | 4-8 (random) | 80 | 320-640 |

---

## What the status colours mean

| Colour | Status | Meaning |
|---|---|---|
| Green | `ONLINE` | Normal operation |
| Orange | `COMPROMISED` | Active attack, data is being manipulated but device appears online |
| Red | `FAULT` / `OFFLINE` | Device is down |
| Purple | `NO GRID` | Device lost power because its substation faulted |
| Bright purple | `SIS OFFLINE` | Safety Instrumented System has been disabled (Triton-style attack) |
| Dim orange | `RELAY BYPASSED` | Protection relays disabled, equipment unprotected from physical faults |
| Grey | `WIPED` | Device destroyed by wiper payload, no telemetry, no recovery without physical intervention |
| Burnt orange | `ENCRYPTED` | Ransomware deployed, device is running but blind and uncontrollable |

---

## What the "homes affected" counter counts

When a substation faults, the counter adds feeders active multiplied by homes per feeder for that substation. Each substation has 4-8 feeders (set randomly at startup) each serving 80 homes, so a single substation fault puts 320-640 homes without power.

Individual devices showing `NO GRID` add 1 to the count to represent the premises they serve.

The counter resets when attacks are stopped and substations recover.
