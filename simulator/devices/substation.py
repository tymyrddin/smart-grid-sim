import math
import random
import time

from simulator.base_device import BaseDevice

_DAY_CYCLE_SECONDS = 300


class Substation(BaseDevice):
    def __init__(self, device_id: str, **kwargs):
        super().__init__(device_id, "substation", **kwargs)
        self._feeder_count = random.randint(4, 8)
        self._phase_offset = random.uniform(0, math.pi)

    def generate_telemetry(self) -> dict:
        t = (time.time() / _DAY_CYCLE_SECONDS) * 2 * math.pi
        cycle = math.sin(t + self._phase_offset)
        load_base = 6.0 + 3.0 * cycle

        return {
            "bus_voltage": round(random.gauss(11000.0, 100.0), 0),
            "load_mw": round(random.gauss(load_base, 0.2), 3),
            "feeders_active": self._feeder_count,
            "transformer_temp": round(random.gauss(65.0, 2.0), 1),
            "alarms": [],
        }
