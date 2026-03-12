import threading
import yaml
import paho.mqtt.client as mqtt

from simulator.devices.meter import SmartMeter
from simulator.devices.inverter import SolarInverter
from simulator.devices.ev_charger import EVCharger
from simulator.devices.substation import Substation

DEVICE_CLASSES = {
    "meter":      SmartMeter,
    "inverter":   SolarInverter,
    "ev_charger": EVCharger,
    "substation": Substation,
}


def load_config(path: str = "config/devices.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def build_devices(config: dict) -> list:
    devices = []
    for d in config["devices"]:
        cls = DEVICE_CLASSES.get(d["type"])
        if cls is None:
            print(f"[warn] unknown device type '{d['type']}', skipping {d['id']}")
            continue
        devices.append(cls(
            device_id=d["id"],
            update_interval=d.get("update_interval", 1),
            vulnerabilities=d.get("vulnerabilities", []),
        ))
    return devices


def make_client(host: str, port: int) -> mqtt.Client:
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    except AttributeError:
        client = mqtt.Client()  # paho-mqtt < 2.0
    client.connect(host, port)
    client.loop_start()  # background network thread
    return client


def main():
    config = load_config()
    devices = build_devices(config)

    mqtt_host = config.get("mqtt", {}).get("host", "localhost")
    mqtt_port = config.get("mqtt", {}).get("port", 1883)

    print(f"[sim] connecting to MQTT broker at {mqtt_host}:{mqtt_port}")
    client = make_client(mqtt_host, mqtt_port)

    print(f"[sim] starting {len(devices)} devices")
    threads = [
        threading.Thread(target=device.run, args=(client,), daemon=True)
        for device in devices
    ]
    for t in threads:
        t.start()

    print(f"[sim] {len(threads)} device threads running — Ctrl+C to stop")
    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        print("\n[sim] shutting down")
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
