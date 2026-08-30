import math
import random
import time

from simulator.base_device import BaseDevice

# One full solar day compressed into 5 minutes, so the curve is visible live.
_DAY_CYCLE_SECONDS = 300


class SolarInverter(BaseDevice):
    def __init__(self, device_id: str, **kwargs):
        super().__init__(device_id, "inverter", **kwargs)
        self._peak_output = random.uniform(4.0, 10.0)
        # phase_offset was random.random()*300 at first and every inverter clumped
        # near t=0 on startup, so the curves overlapped. this spreads them out.
        self._phase_offset = random.uniform(0, _DAY_CYCLE_SECONDS)

    def generate_telemetry(self) -> dict:
        t = (time.time() + self._phase_offset) % _DAY_CYCLE_SECONDS
        sun_factor = max(0.0, math.sin(math.pi * t / _DAY_CYCLE_SECONDS))
        output = round(self._peak_output * sun_factor * random.uniform(0.95, 1.05), 2)
        return {
            "dc_voltage": round(random.gauss(380.0, 5.0) * (0.5 + 0.5 * sun_factor), 1),
            "ac_voltage": round(random.gauss(230.0, 2.0), 2),
            "output_power": output,
            "efficiency": round(random.uniform(0.93, 0.98), 3) if output > 0 else 0.0,
        }
