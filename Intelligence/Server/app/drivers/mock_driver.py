import os
import sys

# Ensure simulation module can be imported
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../..")))

from app.drivers.base import SensorDriver
from app.schemas.sensor import SensorPayload
from simulation.sensor_simulator import SensorSimulator

class MockSensorDriver(SensorDriver):
    def __init__(self, scenario: str = 'clean_indoor', node_id: str = "sim_node_01", seed: int = None):
        self.simulator = SensorSimulator(scenario=scenario, node_id=node_id, seed=seed)
        
    def read(self) -> SensorPayload:
        """Read current sensor values and return a validated SensorPayload."""
        data = self.simulator.generate()
        # The sensor payload validation logic checks timezone etc.
        # Ensure timestamp has a Z for fromisoformat if needed, though dict passing to **data
        # will handle standard iso strings if model parses it. Pydantic handles str -> datetime.
        return SensorPayload(**data)
        
    def is_available(self) -> bool:
        """Check if the sensor hardware is available."""
        return True
        
    def get_node_id(self) -> str:
        """Get the ID of the sensor node."""
        return self.simulator.node_id
