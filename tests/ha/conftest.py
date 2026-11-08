"""Real HA test fixtures. Never connect to a Freebox or production HA."""
import pytest
from pathlib import Path
import custom_components

# The HA test plugin also ships test custom_components; include our source root.
custom_components.__path__.append(str(Path(__file__).resolve().parents[2] / "custom_components"))

pytest_plugins = ['pytest_homeassistant_custom_component']


@pytest.fixture(autouse=True)
def enable_custom(enable_custom_integrations):
    """Load this custom integration through the actual HA loader."""
    yield
