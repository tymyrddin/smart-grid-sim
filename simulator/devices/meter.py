import random
from simulator.base_device import BaseDevice


class SmartMeter(BaseDevice):
    def __init__(self, device_id: str, **kwargs):
        super().__init__(device_id, "meter", **kwargs)
        self._base_load = random.uniform(1.5, 8.0)  # kW

    def generate_telemetry(self) -> dict:
        return {
            "voltage":   round(random.gauss(230.0, 2.0), 2),    # V
            "current":   round(self._base_load + random.gauss(0, 0.3), 3),  # A
            "power":     round(self._base_load * random.uniform(0.95, 1.05), 2),  # kW
            "frequency": round(random.gauss(50.0, 0.05), 3),    # Hz
        }
