from datetime import datetime, timedelta, timezone
from pydantic import BaseModel, Field, model_validator

class EnvironmentReading(BaseModel):
    temperature_C: float = Field(ge=-40, le=85)
    humidity_pct: float = Field(ge=0, le=100)

class GasSensorReading(BaseModel):
    raw_adc: int = Field(ge=0, le=1023)
    voltage_V: float = Field(ge=0.0, le=5.0)

class ParticulateMatterReading(BaseModel):
    PM1_0: float = Field(ge=0)
    PM2_5: float = Field(ge=0)
    PM10: float = Field(ge=0)

    @model_validator(mode='after')
    def check_pm_values(self) -> 'ParticulateMatterReading':
        tolerance = 0.5
        if not (self.PM1_0 <= self.PM2_5 + tolerance and self.PM2_5 <= self.PM10 + tolerance):
            raise ValueError(f"PM values must satisfy PM1.0 <= PM2.5 <= PM10. Got {self.PM1_0}, {self.PM2_5}, {self.PM10}")
        return self

class GasSensors(BaseModel):
    MQ2: GasSensorReading
    MQ9: GasSensorReading
    MQ135: GasSensorReading

class SensorPayload(BaseModel):
    node_id: str = Field(min_length=1, max_length=64, pattern=r'^[a-zA-Z0-9_-]+$')
    timestamp: datetime
    environment: EnvironmentReading
    particulate_matter: ParticulateMatterReading
    gas_sensors: GasSensors

    @model_validator(mode='after')
    def check_timestamp(self) -> 'SensorPayload':
        now = datetime.now(timezone.utc)
        if self.timestamp.tzinfo is not None:
            payload_utc = self.timestamp.astimezone(timezone.utc)
        else:
            # Treat naive timestamps as local time for comparison purposes
            payload_utc = self.timestamp.replace(tzinfo=timezone.utc)
        # Allow generous slack: sensor nodes may be in different timezones
        # or have slightly drifted clocks
        if payload_utc > now + timedelta(hours=24):
            raise ValueError(
                "Timestamp cannot be more than 24 hours in the future"
            )
        return self
