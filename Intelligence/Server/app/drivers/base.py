from abc import ABC, abstractmethod
from app.schemas.sensor import SensorPayload

class SensorDriver(ABC):
    @abstractmethod
    def read(self) -> SensorPayload:
        """Read current sensor values and return a validated SensorPayload."""
        ...
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if the sensor hardware is available."""
        ...
    
    @abstractmethod
    def get_node_id(self) -> str:
        """Get the ID of the sensor node."""
        ...
