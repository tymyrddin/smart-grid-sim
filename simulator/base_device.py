import json
import time
from abc import ABC, abstractmethod


class BaseDevice(ABC):
    def __init__(self, device_id: str, device_type: str, update_interval: float = 1.0, vulnerabilities: list = None):
        self.id = device_id
        self.type = device_type
        self.update_interval = update_interval
        self.vulnerabilities = vulnerabilities or []
        self.status = "online"

    @abstractmethod
    def generate_telemetry(self) -> dict:
        pass

    def state(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "status": self.status,
            **self.generate_telemetry(),
        }

    def run(self, client) -> None:
        topic = f"devices/{self.type}/{self.id}/state"
        print(f"[device] {self.id} ({self.type}) → {topic}")
        while True:
            client.publish(topic, json.dumps(self.state()))
            time.sleep(self.update_interval)
