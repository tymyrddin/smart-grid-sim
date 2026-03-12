import random
from simulator.base_device import BaseDevice


class EVCharger(BaseDevice):
    def __init__(self, device_id: str, **kwargs):
        super().__init__(device_id, "ev_charger", **kwargs)
        self._charging = random.random() > 0.3
        self._power = round(random.uniform(7.0, 22.0), 2) if self._charging else 0.0
        self._session_energy = 0.0

    def generate_telemetry(self) -> dict:
        if self._charging:
            if random.random() < 0.03:          # ~3% chance session ends each tick
                self._charging = False
                self._power = 0.0
                self._session_energy = 0.0
            else:
                # Charging power drifts gradually (simulates real charging curve)
                self._power = max(7.0, min(22.0, self._power + random.gauss(0, 0.5)))
                self._session_energy = min(80.0, self._session_energy + self._power * (2 / 3600))
        else:
            if random.random() < 0.05:          # ~5% chance new session starts each tick
                self._charging = True
                self._power = round(random.uniform(7.0, 22.0), 2)

        return {
            "charging":       self._charging,
            "power":          round(self._power, 2) if self._charging else 0.0,
            "voltage":        round(random.gauss(230.0, 1.5), 2),
            "session_energy": round(self._session_energy, 1),
        }
