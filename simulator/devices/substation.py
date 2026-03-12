import math
import random
import time
from simulator.base_device import BaseDevice

# Full day cycle every 5 minutes — matches the inverter solar cycle period
_DAY_CYCLE_SECONDS = 300


class Substation(BaseDevice):
    def __init__(self, device_id: str, **kwargs):
        super().__init__(device_id, "substation", **kwargs)
        self._feeder_count = random.randint(4, 8)
        # Stagger substations so their peaks don't coincide
        self._phase_offset = random.uniform(0, math.pi)

    def generate_telemetry(self) -> dict:
        # Day-cycle load: peak during "business hours", trough at "night"
        # Range: 3 – 9 MW over the 5-minute synthetic day
        t = (time.time() / _DAY_CYCLE_SECONDS) * math.pi
        cycle = math.sin(t + self._phase_offset)
        load_base = 6.0 + 3.0 * cycle          # 3 – 9 MW

        return {
            "bus_voltage":      round(random.gauss(11000.0, 100.0), 0),
            "load_mw":          round(random.gauss(load_base, 0.2), 3),
            "feeders_active":   self._feeder_count,
            "transformer_temp": round(random.gauss(65.0, 2.0), 1),
            "alarms":           [],
        }
