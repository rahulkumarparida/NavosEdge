import math
from datetime import datetime
from typing import Dict, Any, List

from app.schemas.sensor import SensorPayload

__all__ = [
    "SensorPayload",
    "validate_sensor_reading",
    "reject_nan_inf",
    "validate_ranges",
    "validate_timestamp"
]

def validate_sensor_reading(data: dict) -> SensorPayload:
    """Parse and validate a raw dict to SensorPayload."""
    return SensorPayload(**data)

def reject_nan_inf(data: dict) -> dict:
    """Check all numeric values for NaN/Infinity and raise ValueError."""
    def _check(val):
        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
            raise ValueError(f"Invalid numeric value found: {val}")
    
    def _traverse(item):
        if isinstance(item, dict):
            for v in item.values():
                _traverse(v)
        elif isinstance(item, list):
            for v in item:
                _traverse(v)
        elif isinstance(item, (int, float)):
            _check(item)

    _traverse(data)
    return data

def validate_ranges(data: dict) -> List[str]:
    """Return warnings for out-of-normal-range values."""
    warnings = []
    
    env = data.get("environment", {})
    temp = env.get("temperature_C")
    if temp is not None and (temp < -10 or temp > 50):
        warnings.append(f"Temperature {temp}C is out of normal range (-10 to 50).")
    
    hum = env.get("humidity_pct")
    if hum is not None and (hum < 10 or hum > 90):
        warnings.append(f"Humidity {hum}% is out of normal range (10 to 90).")
        
    pm = data.get("particulate_matter", {})
    pm25 = pm.get("PM2_5")
    if pm25 is not None and pm25 > 250:
        warnings.append(f"PM2.5 {pm25} is unusually high.")
        
    pm10 = pm.get("PM10")
    if pm10 is not None and pm10 > 400:
        warnings.append(f"PM10 {pm10} is unusually high.")
        
    return warnings

def validate_timestamp(ts_str: str) -> datetime:
    """Parse and validate timestamp string."""
    try:
        # ISO format with Z
        if ts_str.endswith("Z"):
            ts_str = ts_str[:-1] + "+00:00"
        return datetime.fromisoformat(ts_str)
    except ValueError as e:
        raise ValueError(f"Invalid timestamp format: {e}")
