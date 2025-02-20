import pytest
from unittest.mock import AsyncMock
from custom_components.freebox_homexa.sensor import FreeboxSensor
from custom_components.freebox_homexa.router import FreeboxRouter

@pytest.mark.asyncio
async def test_sensor_update_state():
    router = AsyncMock(spec=FreeboxRouter)
    router.sensors = {"rate_down": 10000}  # Simule 10 KB/s
    desc = {"key": "rate_down", "name": "Test Speed", "native_unit_of_measurement": "KB/s"}
    sensor = FreeboxSensor(router, desc)
    sensor.async_update_state()
    assert sensor.native_value == 10.0  # Vérifie la conversion
