# Attack reference

This document explains what each attack does and why it matters.
The simulated effects mirror real techniques used against power infrastructure, the names and scenarios reference documented incidents.

## How attacks work in this simulation

The attack engine sits between the device simulator and the dashboard. Every piece of telemetry the devices publish passes through it. When an attack is active, the engine intercepts that data and modifies it before the dashboard ever sees it, exactly as a real attacker would manipulate the data flowing through a SCADA system.

Attacks can be triggered from the dashboard or via the REST API. Clicking Stop clears the attack and devices return to normal on their next update.

---

## Basic attack techniques

These are the building-block techniques. Nation-state scenarios below combine them into multi-stage operations.

---

### Telemetry spoofing

What the dashboard shows: meter voltage readings spike or collapse wildly, jumping far outside normal range.

What it means: the attacker has modified the sensor data before it reaches the operator. The physical grid is fine, but the operator's screen shows a crisis that isn't there, or masks a real one. Operators making decisions based on falsified readings can trip protection systems incorrectly, or fail to respond to actual faults.

Targets: `meter-001`, `meter-002`, `inverter-001`

---

### Device shutdown

What the dashboard shows: the device card turns red and goes offline. Power output drops to zero.

What it means: a remote shutdown command was sent over the network to the device. No physical access was needed. The device is off, and anything it was supplying power to is now without it.

Targets: `ev-charger-001`, `ev-charger-002`

---

### Demand spike

What the dashboard shows: load or power readings multiply, and meters and substations show demand several times higher than normal. Overload alarms fire.

What it means: false demand data is injected into the control system. The grid's automatic load-management logic sees a huge demand surge and responds accordingly, potentially shedding load from other customers, tripping protection relays, or causing genuine overloads as the system tries to compensate for a problem that does not exist.

Targets: `meter-001`, `ev-charger-001`, `substation-01`

---

### Frequency attack

What the dashboard shows: the grid frequency reading drifts outside the safe 49-51 Hz band, either dropping (under-frequency) or rising (over-frequency).

What it means: grid frequency is the heartbeat of the power system. Every generator connected to the grid must spin in perfect synchrony. If frequency drops below roughly 47.5 Hz or rises above roughly 52 Hz, automatic protection relays disconnect equipment to prevent damage. An attacker who can make a meter report false frequency can trigger those disconnections deliberately, without touching a single generator.

The simulation shows two variants: a dangerous drop to 47.5 Hz and a dangerous spike to 52.8 Hz.

Targets: `meter-001`, `meter-002`

---

### Cascading failure

What the dashboard shows: a substation faults and goes red. Immediately, every meter, charger, and inverter connected to it shows `NO GRID` with all readings dropping to zero. The homes-affected counter jumps.

What it means: when a substation trips, it takes down everything it feeds. Homes, businesses, EV chargers, solar exports, all cut simultaneously. The cascade is the intended outcome: one targeted attack causes a much larger blackout than the directly-attacked device would suggest.

Targets: `substation-01`, `substation-02`

---

### Modbus write

What the dashboard shows: the substation's load setpoint is overwritten to zero. Load readings collapse.

What it means: Modbus is an industrial control protocol from 1979 that is still widely used in power infrastructure. It has no authentication. Anyone who can reach the device on the network can send it commands. This attack sends a direct write command setting load to zero, the industrial equivalent of walking up to a control panel and turning a dial. No malware, no exploit, just a native protocol command.

Targets: `substation-01`, `substation-02`

---

### Data replay (freeze)

What the dashboard shows: a device's readings stop changing. The numbers stay identical tick after tick, a telltale flatline in the chart.

What it means: the attacker has captured a snapshot of normal device output and is replaying it on a loop. The operator sees steady, reassuring data. Meanwhile, the real device could be offline, on fire, or under active attack, and nobody knows. This is a classic pre-attack technique: freeze the sensors before doing something the sensors would otherwise detect.

Targets: `meter-003`, `substation-02`

---

### Protection relay bypass

What the dashboard shows: the device card shows `RELAY BYPASSED` in orange.

What it means: protection relays are the circuit breakers of the grid. They disconnect equipment automatically when dangerous conditions occur, such as overcurrent, overvoltage, or short circuits. Disabling them means physical damage can now occur without any automatic response. The equipment will keep running into a fault condition. This technique was used in Industroyer/CRASHOVERRIDE.

Targets: `substation-01`, `substation-02`

---

### Safety system bypass (SIS offline)

What the dashboard shows: the device card shows `SIS OFFLINE` in purple.

What it means: a Safety Instrumented System (SIS) is the last line of automated defence. It monitors for dangerous physical conditions and takes independent action to prevent equipment destruction or harm to people. Taking it offline means that if something goes wrong, nothing will automatically stop it. The process can now reach a dangerous state with no safety net. This is the defining characteristic of Triton/TRISIS-style attacks.

Targets: `substation-01`, `substation-02`

---

### Wiper

What the dashboard shows: the device card goes dark grey and shows `WIPED`. Its chart line disappears entirely. The substation goes silent and connected devices lose their grid supply.

What it means: a destructive payload has overwritten the device's configuration, logs, and firmware. The device is gone from the network, not just offline but unable to recover without manual physical intervention and reinstallation. Wipers are used as a final act after the main attack objective is complete: deny forensic evidence, maximise recovery time, and demoralise defenders. Used by Sandworm in Industroyer2 and CaddyWiper.

Targets: `substation-01`, `substation-02`

---

### Ransomware

What the dashboard shows: the device card turns burnt orange and shows `ENCRYPTED`. All telemetry values go blank.

What it means: ransomware has encrypted the device's software and data. The device is still physically intact but operationally blind. It cannot report its state, receive commands, or be managed. In Colonial Pipeline (2021), ransomware on the IT network caused the operator to voluntarily shut down the OT system out of caution, producing a real-world fuel shortage with no direct OT attack at all.

Targets: `substation-01`, `substation-02`

---

## Nation-state scenarios

These are documented incidents or techniques attributed to specific threat actors. Each scenario combines multiple basic attacks into a realistic operation.

---

### Ukraine 2015, coordinated blackout
`nation-coordinated-blackout`

The first confirmed cyberattack to cause a civilian power outage. In December 2015, Sandworm (Russian GRU) hit three Ukrainian energy companies simultaneously, cutting power to around 225,000 customers for up to six hours. Both substations are hit at the same moment, the defining feature of the attack was synchronisation across multiple targets.

What to watch: both substation cards go red simultaneously. Everything connected to them loses grid supply at the same instant.

---

### Mass telemetry spoofing, coordinated
`nation-coordinated-spoofing`

Simultaneous manipulation of all meter telemetry plus replay on a third meter. The operator's entire measurement picture is falsified at once, and no single anomaly stands out.

---

### Industroyer / Sandworm style, staged
`nation-staged-industroyer`

Industroyer, used in the December 2016 Ukraine blackout, spent time establishing persistence before executing. This scenario models the dwell-then-strike pattern: 30 seconds of silent data replay on key devices (operators see normal operation), then simultaneous cascading failures on both substations.

What to watch: phase 1 looks completely normal on the dashboard, that is the point. Phase 2 hits without any warning.

---

### Slow burn, staged
`nation-staged-slow-burn`

Spoofing on two meters masks operator visibility for 20 seconds, then a demand spike on the substation and EV charger triggers overload conditions the operator cannot correctly interpret because their sensor data is unreliable.

---

### Protection relay disabled, Industroyer/CRASHOVERRIDE style
`nation-relay-bypass-01`, `nation-relay-bypass-02`

The 2016 Industroyer malware included a module that directly communicated with protection relays using IEC 61850 and IEC 104 protocols, issuing trip commands to disable them. With relays bypassed, subsequent faults cause uncontrolled physical damage.

### Safety system offline, Triton/TRISIS style
`nation-safety-bypass-01`, `nation-safety-bypass-02`

In 2017, attackers attributed to Sandworm and TEMP.Veles deployed Triton malware against a petrochemical plant's Safety Instrumented System. Their goal was to disable the SIS so that a subsequent process attack could cause physical harm without automatic shutdown intervening. A logic error accidentally triggered a safe-state shutdown and revealed the malware before the main attack executed.

### Triton/TRISIS full kill chain, Tasnee, Saudi Arabia 2017
`triton-full-kill-chain`

The complete intended sequence: 20 seconds with the SIS taken offline on both substations (no automatic protection), then simultaneous cascading failures. In the real incident, this final step never happened because the malware bug gave it away first. This scenario shows what would have followed.

What to watch: cards go purple (SIS offline) for 20 seconds. Then both substations fault and cascade with nothing to stop it.

### Wiper, Industroyer2/CaddyWiper style
`nation-wiper-substation-01`, `nation-wiper-substation-02`, `nation-wiper-all-substations`

In April 2022, Sandworm deployed Industroyer2 against Ukrainian energy infrastructure alongside the CaddyWiper disk-wiping malware. The intent was to cause a blackout and simultaneously destroy the systems needed to restore it. Both substations going dark simultaneously is the `nation-wiper-all-substations` scenario.

### Stuxnet, Iran Natanz 2010
`nation-stuxnet-substation-01`, `nation-stuxnet-substation-02`, `nation-stuxnet-both`

The most sophisticated cyberweapon discovered to that point. Developed by the US and Israel, Stuxnet targeted Iranian uranium enrichment centrifuges. It made centrifuges spin at destructive speeds while reporting normal operation to operators, for months. Here, the equivalent is a transformer slowly overheating while its temperature readout shows nothing alarming, until the thermal protection trips and the substation faults.

What to watch: the transformer temperature line on the substations chart climbs gradually from roughly 65°C toward the 112°C trip threshold, taking about two minutes. When it trips, the substation faults and everything connected cascades.

### Volt Typhoon, Chinese APT, 2023 to present
`nation-volt-typhoon`

Volt Typhoon, attributed to Chinese state-sponsored actors, was discovered to have maintained undetected access inside US critical infrastructure, including energy and water utilities, for years. Their approach was living off the land: using normal system tools to avoid detection and establishing persistent access for potential future use. This scenario models a 120-second dwell period, during which stale data keeps operators blind, followed by total blackout plus wiper.

What to watch: two full minutes of apparently normal operation, then everything collapses at once and both substations go dark permanently.

### FrostyGoop, Lviv, Ukraine, January 2024
`nation-frostygoop`

In January 2024, attackers used a tool called FrostyGoop to send Modbus TCP write commands directly to heating controllers in Lviv, Ukraine. Around 600 apartment buildings lost heat for two days in sub-zero temperatures. No malware was installed, the attack used the industrial protocol itself. This scenario zeros both substation load setpoints via Modbus and simultaneously spikes demand to create overload conditions.

### Pipedream/INCONTROLLER, 2022
`nation-pipedream`

Pipedream, also called INCONTROLLER, is the most capable ICS attack framework ever publicly documented. Discovered in 2022 before deployment, it targeted Schneider Electric and OMRON industrial controllers. It included modules for reconnaissance, lateral movement, and destructive payload delivery across multiple ICS protocols. This scenario runs 45 seconds of active reconnaissance, spoofing meters and inverters, spiking demand, and distorting frequency, then simultaneously wipes both substations and shuts down all EV chargers.

What to watch: phase 1 is chaotic, with readings wrong across the board. Then phase 2 silences everything at once.

### Colonial Pipeline, 2021
`nation-colonial-pipeline`

In May 2021, DarkSide ransomware was deployed against Colonial Pipeline's IT network. Colonial shut down the OT system voluntarily, not because the pipeline control system was directly attacked, but because operators could not trust their IT environment. 45% of the US East Coast's fuel supply was cut for five days. This scenario deploys ransomware across both substations: telemetry goes dark and the operator is flying blind.

### Aurora vulnerability, Idaho National Laboratory, 2007
`aurora-inverter-001`, `aurora-inverter-002`, `aurora-both`

The Aurora vulnerability was demonstrated by the Idaho National Laboratory in a classified test in 2007, later partially declassified. By rapidly opening and closing a generator's circuit breaker out of phase with the grid, the rotor physically slams against its housing. A 2.25 MW diesel generator was destroyed on camera in under a minute. The vulnerability affects any rotating generator connected to the grid via a remotely-controllable breaker. No exploit is required, just breaker open/close commands at the wrong moment.

What to watch: the inverter output chart oscillates violently, surging to nearly 3 times normal then dropping to zero, cycling rapidly. After about eight cycles, the generator trips permanently. The physical equipment is destroyed; stopping the attack does not repair it in real life.

### Predatory Sparrow/Gonjeshke Darande, Iranian steel mills, 2022
`predatory-sparrow`

Attributed to an Israeli-linked group, Predatory Sparrow attacked three Iranian steel mills simultaneously in June 2022. Khuzestan Steel suffered a fire caused by cyber-induced equipment failure, one of the first confirmed cases of a cyberattack causing visible physical damage to industrial equipment outside of Stuxnet. The attack disabled safety systems first, then overloaded equipment with no automatic protection to intervene.

What to watch: phase 1 disables the SIS (purple card) and begins heating the transformer. After 15 seconds, demand spikes and the cascade triggers. With safety systems already offline, nothing stops the fault.
