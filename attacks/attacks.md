# Attack reference

What each attack in the simulation represents, and the real techniques and incidents behind it. Each entry covers both how the technique works and the real-world context. Composite scenarios, those that sequence or combine multiple techniques, are listed at the end.

Where no famous named attack exists for a technique, that is noted along with relevant context.



### Telemetry spoofing
`spoof-meter-001` `spoof-meter-002` `spoof-inverter-001`

Telemetry spoofing does not have a single famous named attack behind it, but falsifying sensor data is a component of 
almost every sophisticated ICS operation on record. Stuxnet fed false centrifuge speed readings back to operators at 
Natanz for months while the centrifuges were being destroyed. Industroyer replayed frozen network state data to mask 
its own actions during the 2016 Ukraine blackout. TRISIS concealed the fact that safety controllers were being 
reprogrammed.

The underlying principle is simple: industrial control systems trust their sensors completely. There is no equivalent 
of a checksum on a meter reading, no way for a SCADA historian to verify that the value it received corresponds to 
what the physical device actually measured. A 2009 academic paper by Liu, Ning, and Reiter at the University of 
Illinois formally described "[false data injection attacks](https://reitermk.github.io/papers/2009/CCS1.pdf)" on 
power grid state estimation, demonstrating mathematically that an attacker who knew the network topology could 
manipulate multiple meter readings simultaneously in a way that would pass every consistency check the control 
system performed. The paper caused significant concern in the power sector and triggered a decade of research 
into detection methods.



### Forced shutdown
`shutdown-ev-001` `shutdown-ev-002`

There is no single famous attack exclusively associated with remote shutdown of individual edge devices like EV chargers. The technique is generic: most industrial protocols from the 1980s and 1990s include a stop or disable command that requires no authentication.

The closest real-world precedent at this scale is the 2016 Ukraine attack, in which Sandworm sent remote shutdown commands to serial-to-Ethernet converters at distribution substations. These were not sophisticated exploits. The devices were simply commanded to disconnect using their native protocol. A firmware update that added authentication would have prevented it. Most had not received one.

[In 2022, researchers demonstrated](https://dl.acm.org/doi/10.1145/3524454) that a coordinated attack on a large fleet of smart EV chargers in a region could, by switching them on and off simultaneously, create demand fluctuations sufficient to destabilise the local grid. The attack requires no vulnerability; it required only access to the charger management APIs.



### Demand spike
`demand-spike-meter-001` `demand-spike-ev-001` `demand-spike-substation-01`

No prominent real-world cyberattack has used false demand injection as its primary vector against a live power grid, though it is a well-studied theoretical attack and the academic literature on it is substantial. The concern is specifically with energy management systems: automated software that controls how a grid operator dispatches generation in response to demand. If that system's inputs can be manipulated, its outputs can be weaponised.

The practical risk has grown with the proliferation of demand-response programmes. Utilities now aggregate millions of smart thermostats, water heaters, and EV chargers into controllable demand pools. A threat actor who compromises the management platform for one of those programmes gains the ability to simultaneously switch enormous loads on or off. Researchers refer to this as a MadIoT or BlackIoT attack. [A 2018 paper from Princeton](https://www.usenix.org/system/files/conference/usenixsecurity18/sec18-soltan.pdf) estimated that flipping a few percentage points of grid demand simultaneously could trigger frequency deviations large enough to trip generation.



### Frequency attack
`frequency-attack-001` `frequency-attack-002`

No confirmed cyberattack has used frequency falsification as its primary technique, but the consequences of real frequency events are well documented and illustrate exactly why it is a plausible attack vector.

In [November 2006 a single line trip in Germany](https://eepublicdownloads.entsoe.eu/clean-documents/pre2015/publications/ce/report_2006_5.pdf) caused a cascade of automatic disconnections that split the European synchronous grid into three islands. Frequency dropped to 49.0 Hz in the western island and rose to 50.6 Hz in the eastern one. Around 15 million European homes briefly lost power before operators restored balance. The split was caused by protective relays responding automatically to readings they were designed to respond to. The same logic applies to falsified readings.

The UK experienced a significant frequency event in [August 2019 when two generators tripped](https://www.neso.energy/document/152346/download) simultaneously, dropping national frequency to 48.88 Hz and triggering automatic load disconnection affecting nearly a million customers. Again, no cyberattack was involved, but it demonstrated that the protective systems themselves are the mechanism through which a frequency anomaly becomes an outage.



### Cascading failure
`cascade-substation-01` `cascade-substation-02`

No cyberattack has yet produced a cascade comparable to the major accidental events, but the [2015 Ukraine attack](https://nsarchive.gwu.edu/sites/default/files/documents/3891751/SANS-and-Electricity-Information-Sharing-and.pdf) did trigger deliberate cascades at the distribution level, and the concern about transmission-level cascade is taken seriously by national security agencies.

The benchmark for what a cascade looks like is the [Northeast Blackout of August 2003](https://practical.engineering/blog/2022/2/9/what-really-happened-during-the-2003-blackout), which had nothing to do with a cyberattack. A software bug in an alarm system at FirstEnergy in Ohio suppressed alerts while transmission lines were tripping. Operators did not know there was a problem. The failure propagated across interconnections until 55 million people across the northeast United States and Ontario lost power in under eight minutes. The cost was estimated at between four and ten billion dollars.

The 2006 European event mentioned above is a second example. Both demonstrate that cascades in meshed transmission networks are self-reinforcing once they begin, and that the same protective systems designed to contain them can accelerate the spread if they operate without coordination.



### Modbus write — FrostyGoop, Lviv 2024
`modbus-substation-01` `modbus-substation-02` `nation-frostygoop`

Modbus was designed by Modicon in 1979 for connecting programmable logic controllers to supervisory systems inside factories. It was intended to run on isolated serial networks where physical access was already controlled. Authentication was considered unnecessary. The protocol was eventually adapted for TCP/IP networks in 1999, but no authentication was added.

[FrostyGoop, reported publicly by Dragos in July 2024](https://www.dragos.com/blog/protect-against-frostygoop-ics-malware-targeting-operational-technology), followed a January attack on Lvivteploenergo, the municipal heating company serving Lviv in Ukraine. The tool used Modbus TCP to communicate directly with ENERCON heating controllers and sent write commands that altered operational parameters, causing the heating system to malfunction. Around 600 apartment buildings lost heating and hot water for approximately two days during January.

The malware was written in Golang and was functionally simple: it read a target configuration from a file, connected to the specified Modbus TCP endpoints, and issued write commands to specified registers. There was no network propagation, no exploitation of vulnerabilities, and no attempt at persistence. The investigators could not determine with certainty how the attackers gained initial access to the operational network but noted the devices were accessible from the internet.

Shodan, the internet-connected device search engine, routinely indexes tens of thousands of Modbus-enabled devices with no firewall between them and the public internet. Writing to a device register is the same operation whether it comes from a legitimate engineer or an attacker.

`nation-frostygoop` fires the two Modbus write attacks simultaneously alongside a demand spike, modelling the Lviv heating failure.



### Data replay
`replay-meter-003` `replay-substation-02`

Replay of sensor data is not a standalone attack type that appears in famous named incidents on its own, but it is a supporting technique in several. The most notable documented use was in Stuxnet, which fed pre-recorded centrifuge monitoring data back to operators during the destructive phase so that the control room displayed normal operation while the machines were being damaged. This was possible because the monitoring data was transmitted digitally over a network the malware had already compromised.

CISA and other national cybersecurity agencies have described it in advisories on pre-attack reconnaissance patterns, noting that threat actors frequently establish the ability to inject false data before they execute their primary objective, ensuring that discovery is delayed. Replay is the dwell technique in several of the composite scenarios in this simulation.



### Protection relay bypass — Industroyer/CRASHOVERRIDE, Ukraine 2016
`nation-relay-bypass-01` `nation-relay-bypass-02`

Protection relays are the automatic safety switches of the power grid. They monitor current, voltage, frequency, and fault signatures on individual circuits and disconnect equipment within milliseconds when a dangerous condition is detected. Modern digital protection relays communicate over standard industrial protocols including IEC 61850, IEC 60870-5-104, and DNP3. Commands to change relay configuration, including disabling protection functions, can be sent over the same network connections used for monitoring.

The [CRASHOVERRIDE malware, also called Industroyer](https://web-assets.esetstatic.com/wls/2017/06/Win32_Industroyer.pdf), was discovered after the December 2016 Ukraine power attack and analysed publicly by ESET and Dragos. It was the first malware since Stuxnet found to be designed specifically for attacking power grid infrastructure. One of its four payload modules communicated directly with protection relays using IEC 61850 and IEC 60870-5-101 protocols. The module sent commands to open breakers and simultaneously issued trip-prevention commands to the relays, preventing them from automatically reclosing and restoring supply. Without relay bypass, the grid's automatic reclosers would have restored power within seconds or minutes. With it, restoration required manual intervention at each affected substation.

The module was written to understand the operational logic of the protection equipment, not simply to crash it. That level of domain knowledge indicated either insider familiarity with the target systems or an extended reconnaissance phase.



### Safety system bypass — Triton/TRISIS, Saudi Arabia 2017
`nation-safety-bypass-01` `nation-safety-bypass-02`

A Safety Instrumented System is an independent layer of control, separate from the main process control system, that monitors for dangerous physical conditions and takes autonomous action to bring the plant to a safe state. It is deliberately isolated and uses different hardware and software from the operational technology it monitors. Taking a SIS offline requires targeting it directly.

Triton, also called TRISIS and HatMan, was discovered in 2017 after an incident at a petrochemical plant in Saudi Arabia, later reported to be the Tasnee facility. It is the only malware ever found to have directly targeted a Safety Instrumented System. The specific target was Schneider Electric's Triconex SIS controller. The malware was installed on an engineering workstation that had legitimate access to the safety controllers. It exploited [a zero-day vulnerability in the Triconex firmware](https://www.darkreading.com/vulnerabilities-threats/schneider-electric-triton-trisis-attack-used-0-day-flaw-in-its-safety-controller-system-and-a-rat) to write a custom payload directly onto the safety controller's memory.

The malware put the safety controllers into program mode, normally used only during initial configuration. In this mode the controllers would not execute their safety response logic. From the outside, they appeared operational. The attack was discovered by accident: a logic error in the malware caused two safety controllers to enter a fail-safe state, triggering an automatic plant shutdown and prompting the investigation that found it. Had the malware worked as intended, the safety systems would have been silently disabled while appearing operational.

The attribution for Triton is contested in public reporting. The US government attributed it to a Russian government research institute; Mandiant and other firms have published supporting technical analysis.



### Wiper — Sandworm, Ukraine 2015–2022
`nation-wiper-substation-01` `nation-wiper-substation-02` `nation-wiper-all-substations`

A wiper is a destructive payload that overwrites data on a compromised device. Unlike ransomware, it does not encrypt for extortion; it destroys to prevent recovery. In industrial control contexts, the targets are configuration files, firmware images, historian databases, and event logs. Wipers are typically deployed as the final step of an operation, after the primary objective has been achieved: deny forensic evidence, maximise recovery time, and demoralise defenders.

[Sandworm, the Russian GRU unit](https://attack.mitre.org/groups/G0034/) responsible for both Ukraine power attacks and numerous other operations, has deployed destructive wiper malware repeatedly. The pattern is consistent across incidents. In the 2015 Ukraine attack, KillDisk overwrote the master boot records of operator workstations after the blackout was triggered, delaying restoration. In 2017, [NotPetya](https://www.wired.com/story/notpetya-cyberattack-ukraine-russia-code-crashed-the-world/), a wiper disguised as ransomware, caused an estimated ten billion dollars of damage globally and is considered the most destructive cyberattack in history.

In April 2022, Sandworm deployed [Industroyer2](https://blogs.cisco.com/industrial-iot/mitigating-new-industroyer2-and-incontroller-malware-targeting-industrial-control-systems) against a Ukrainian high-voltage substation alongside [CaddyWiper](https://blog.talosintelligence.com/threat-advisory-caddywiper/), a disk-wiping tool set to execute several hours after Industroyer2, timed to destroy forensic evidence and operator workstations after the substation had already been attacked. Unlike the original Industroyer which was modular and broadly capable, Industroyer2 was a single executable hardcoded for a specific substation's configuration: the IP addresses, port numbers, and information object addresses were written directly into the binary, indicating detailed prior reconnaissance. Ukrainian defenders identified the attack before execution and disrupted it.



### Ransomware — Colonial Pipeline, 2021
`nation-colonial-pipeline`

Ransomware encrypts files and demands payment for the decryption key. In an OT context, the encrypted files are typically not the industrial controllers themselves but the management systems around them: engineering workstations, historian servers, and SCADA applications. The loss of these systems can be operationally decisive even when the physical process is still running.

On 7 May 2021, Colonial Pipeline, which carries approximately 45% of the fuel consumed on the US East Coast, shut down its pipeline operations following a ransomware attack. The attacker group was DarkSide, a ransomware-as-a-service operation believed to be based in Russia. The ransomware infected the IT network, not the operational technology controlling the pipeline itself. Colonial's decision to shut down pipeline operations was precautionary: they could not confirm whether the OT systems were also compromised, and operating a 5,500-mile pipeline without reliable IT support was considered too risky. The shutdown caused fuel shortages along the East Coast for several days, with price spikes, queuing at petrol stations, and a brief declaration of emergency by several states. The ransom demanded was approximately 4.4 million dollars in Bitcoin, which Colonial paid on the day of the attack. The US Department of Justice subsequently recovered approximately 2.3 million dollars of the payment.

The initial access vector was a compromised VPN credential, reportedly obtained from a leaked password database. The account had no multi-factor authentication.

Other significant OT-adjacent ransomware incidents include the [2021 JBS Foods attack](https://otsec.substack.com/p/when-ransomware-disrupted-the-food) which halted meat processing across the United States and Australia, and the [2022 Encevo group attack](https://www.techmonitor.ai/technology/cybersecurity/encevo-group-cyberattack-luxembourg-blackcat-ransomware) which affected gas and electricity networks across Luxembourg, Belgium, and the Netherlands.



### Thermal stress — Stuxnet, Iran 2010
`nation-stuxnet-substation-01` `nation-stuxnet-substation-02` `nation-stuxnet-both`

[Stuxnet](https://spectrum.ieee.org/the-real-story-of-stuxnet) was discovered in June 2010 and is widely assessed to have been operational since at least 2007. It is the most sophisticated piece of malware ever publicly analysed, and as of the time of writing it remains the only confirmed cyberweapon to have caused sustained physical destruction of industrial equipment as its primary objective.

The target was the uranium enrichment facility at Natanz in Iran, specifically the Siemens S7-315 programmable logic controllers managing approximately 1,000 IR-1 centrifuges. Stuxnet spread primarily through infected USB drives, a deliberate design choice for penetrating the air-gapped network at Natanz. Once inside, it fingerprinted the specific PLC configuration at the target facility before activating; installations that did not match the Natanz profile were left untouched. The attack modified the centrifuge rotor speed commands, causing the machines to spin intermittently at speeds outside their designed tolerances. At the same time, it intercepted the monitoring communications and replayed the last recorded normal operating values to the SCADA system, so the operators watching the control room screens saw nothing out of the ordinary. The centrifuges failed at a rate several times the normal mechanical failure rate. Iranian engineers repeatedly replaced the damaged machines and investigated the cause, but the source of the failures remained unclear for years.

Stuxnet was publicly attributed to the United States and Israel in reporting by the [New York Times in 2012](https://archive.nytimes.com/www.nytimes.com/interactive/2012/06/01/world/middleeast/how-a-secret-cyberwar-program-worked.html?hp) and is believed to have been part of a covert programme known as Operation Olympic Games. The operation set back the Iranian enrichment programme by an estimated one to two years.



### Aurora vulnerability — Idaho National Laboratory, 2007
`aurora-inverter-001` `aurora-inverter-002` `aurora-both`

[The Aurora vulnerability](https://cdn.selinc.com/assets/Literature/Publications/Technical%20Papers/6392_MitigatingAurora_MZ_20090918_Web.pdf) was demonstrated by the Idaho National Laboratory in March 2007 under the name [Aurora Generator Test](https://www.wired.com/story/how-30-lines-of-code-blew-up-27-ton-generator/). The test was classified at the time but a video of the generator being destroyed leaked to CNN in 2007 and was later officially released.

The demonstration used a 2.25 MW diesel generator connected to the test grid. Researchers sent a series of open and close commands to the generator's circuit breaker, deliberately cycling the connection while the generator and the grid were out of phase with each other. A synchronous generator must be spinning at exactly the right speed and in phase with the grid before its breaker closes. If reconnected out of phase, the electromagnetic forces between rotor and stator are violently misaligned. After a few cycles, pieces of the generator were ejected and smoke began to emerge. The machine was destroyed in under two minutes.

The finding was alarming because the attack requires no vulnerability in the conventional sense. Every large generator connected to the grid has a remotely operable breaker. Remote operation of that breaker is a standard and necessary feature for grid management. The attack simply abuses that feature. Remediation is technically straightforward but operationally complex: add firmware checks that prevent the breaker from closing when phase difference exceeds a safe threshold. Deploying those fixes across ageing substations with diverse equipment from many vendors has proved slow. No Aurora-style attack has been confirmed in the wild against production infrastructure as of the time of writing, though the vulnerability has been known since 2007 and remains unpatched on a large proportion of the affected equipment.



## Composite scenarios

These combine multiple of the above techniques into sequenced or simultaneous operations. The sequencing is often what defines the scenario historically.



### Ukraine 2015 — coordinated blackout
`nation-coordinated-blackout`

On 23 December 2015, operators at three Ukrainian regional electricity distribution companies watched as their cursor moved across their screens without their hands on the mouse. Attackers who had been inside the networks for months, having entered through spear-phishing emails, had established remote desktop sessions and were now manually opening breakers at substations across western and central Ukraine. Around 230,000 customers lost power for between one and six hours.

The intrusion used BlackEnergy malware for initial access and persistence, but the actual blackout was caused by legitimate remote control commands issued by the attackers through the operators' own SCADA systems. After executing the blackout, the attackers deployed KillDisk to overwrite the master boot records of operator workstations, delaying restoration, and launched a telephone denial-of-service attack against the utility's customer service lines to prevent customers from reporting outages.

It remains the first confirmed cyberattack to cause a civilian power outage and a benchmark against which subsequent grid attacks are measured. In the simulation it fires cascading failures on both substations simultaneously.



### Mass telemetry spoofing, coordinated
`nation-coordinated-spoofing`

This scenario does not represent a single named incident. It fires spoofing on meter-001 and meter-002 and a replay attack on meter-003 simultaneously, demonstrating the effect of compromising the entire measurement picture on one side of the network at once. The technique of broad simultaneous sensor manipulation is described in academic literature on coordinated false data injection and in threat intelligence reporting on pre-attack positioning by several nation-state actors.



### Industroyer/CRASHOVERRIDE, Ukraine 2016 — staged
`nation-staged-industroyer`

On 17 December 2016, exactly one year after the first Ukraine attack, the transmission substation at Pivnichna near Kyiv lost power for approximately an hour. The cause was Industroyer, a modular malware framework analysed publicly by ESET and Dragos in 2017.

Unlike the 2015 attack, which relied on operators' own remote desktop tools, Industroyer contained dedicated modules that spoke industrial protocols directly: IEC 60870-5-101, IEC 60870-5-104, IEC 61850, and OPC DA. Each module could independently communicate with grid equipment without requiring any further attacker interaction. The malware included a configurable scheduling component that could be set to execute its payload at a specified time, with or without an active attacker connection. It also included a backdoor for persistence, a module to map the industrial network, and a component that overwrote itself after execution to complicate forensic analysis. The 2016 attack is considered a test run of capabilities rather than a maximum-impact operation; the affected substation was relatively small and power was restored quickly.

In the simulation: 30 seconds of silent data replay on key devices (operators see a stable grid), then simultaneous cascading failures on both substations. Phase 1 is undetectable on the dashboard. Phase 2 hits without warning.



### Slow burn — staged
`nation-staged-slow-burn`

A constructed scenario rather than a direct representation of a named incident. It models the pattern of using sensor falsification to degrade operator situational awareness before triggering a secondary attack, described in MITRE ATT&CK for ICS under the tactic of impairing process control via manipulation of input. Phase 1 spoofs two meters for 20 seconds. Phase 2 fires a demand spike on the substation and EV charger into an environment where the operator has already lost confidence in their instrumentation.



### Volt Typhoon — Chinese APT, pre-positioning 2023
`nation-volt-typhoon`

In May 2023, Microsoft and the US government disclosed that a Chinese state-sponsored group called Volt Typhoon had maintained persistent access inside critical infrastructure networks in the United States and Guam, including energy, water, communications, and transport. The group had been present in some networks for at least five years without being detected.

Volt Typhoon's defining characteristic was the complete absence of custom malware in the initial intrusion and persistence phases. The group used legitimate tools already present on the compromised systems: built-in Windows command-line utilities, legitimate remote management software, and the systems' own network infrastructure to move laterally. This technique, known as living off the land, leaves minimal forensic trace because the tools used are the same ones administrators use every day. The disclosed intelligence assessment was that the group was pre-positioning for potential destructive action in the event of a major geopolitical crisis, not conducting espionage.

In the simulation: 120 seconds of replay and spoofing across four devices (operators see a normal grid), then cascading failures on both substations plus wiper attacks on both. The 120-second dwell is a compressed representation of the years-long access Volt Typhoon maintained.



### Pipedream/INCONTROLLER, 2022
`nation-pipedream`

Pipedream was disclosed jointly by CISA, the FBI, the NSA, and the Department of Energy in April 2022. It is the most comprehensive ICS attack framework ever publicly documented, targeting Schneider Electric MODICON programmable logic controllers and OMRON SYSMAC engineering software. The framework comprised at least seven distinct components: a tool for scanning and enumerating industrial networks; modules that communicated using native Modbus, OPC-UA, and CODESYS protocols; a component that could modify PLC ladder logic and brick devices by modifying firmware; and a component for OMRON devices that exploited a custom communications protocol. The framework had been developed but not yet deployed against a live target when it was discovered.

In the simulation: 45 seconds of simultaneous spoofing on three devices, demand spike, and frequency attack (the reconnaissance and disruption phase), then wiper attacks on both substations plus forced shutdown of both EV chargers.



### Triton/TRISIS full kill chain — Tasnee, Saudi Arabia 2017

`triton-full-kill-chain`

The kill chain as designed: disable the SIS on both substations for 20 seconds (no automatic protection active), then 
fire simultaneous cascading failures. In the actual 2017 incident this sequence did not complete. A bug in the Triton 
payload caused two Triconex controllers to enter a fail-safe state independently, triggering an automatic plant 
shutdown and revealing the malware. Had it executed cleanly, the most likely outcome would have been a hazardous 
release or explosion with no automated response to contain it.


### Predatory Sparrow/Gonjeshke Darande — Iranian steel mills, 2022

`predatory-sparrow`

On 27 June 2022, a group calling itself Gonjeshke Darande (Persian for hunting sparrow) published video footage showing industrial equipment on fire and emergency workers responding at the Khuzestan Steel Company, one of Iran's largest steel producers. Two other steel companies reported simultaneous cyberattacks the same day, though Khuzestan was the only one to suffer visible physical damage. The attack disabled safety systems first, then overloaded equipment with no automatic protection to intervene. The group's communications have been in Persian and their targeting has been exclusively directed at Iranian infrastructure. The attack is widely attributed in open-source intelligence reporting to Israeli intelligence or a group operating with Israeli support, though no government has formally claimed responsibility.

In the simulation: 15 seconds with the SIS taken offline and thermal stress accumulating on substation-01 (phase 1), then a demand spike and cascading failure (phase 2). With the safety system already offline, nothing stops the fault.
