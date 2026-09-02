# Changelog

## 0.1.0 "Black Start" - 2026-08-30

First public release.

- Synthetic smart grid published over MQTT: smart meters, solar inverters, EV chargers, and two
  substations with a feeder topology, each device on its own thread.
- Attack engine as a transparent MQTT proxy, with 39 configured attacks. Basic techniques
  (telemetry spoofing, forced shutdown, demand spike, frequency manipulation, cascading failure,
  Modbus register write, replay) and nation-state scenarios modelled on documented incidents
  (Ukraine 2015, Stuxnet, Industroyer, Triton/TRISIS, Volt Typhoon, FrostyGoop, Colonial Pipeline,
  Aurora, Predatory Sparrow, PIPEDREAM).
- Real-time Flask and Dash dashboard: device cards, live telemetry charts, a SCADA-style event log,
  a homes-affected counter, and one-click attack triggering from the browser or a REST endpoint.
- Docker Compose stack wiring the broker, simulator, engine, and dashboard together.
- Licensed under MIT.
