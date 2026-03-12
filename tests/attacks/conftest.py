import pytest
import attacks.engine as engine


@pytest.fixture(autouse=True)
def reset_engine_state():
    """Reset all module-level engine state before each test."""
    engine._active_attacks.clear()
    engine._faulted_substations.clear()
    engine._frozen_states.clear()
    engine._thermal_accumulation.clear()
    engine._aurora_ticks.clear()
    engine._device_states.clear()
    engine._topology.clear()
    engine._homes_map.clear()
    yield
