"""Deterministic synthetic sensor payload generation."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from app.schemas.sensor import SensorPayload

SCENARIOS = (
    "clean_background",
    "traffic",
    "heavy_dust",
    "construction",
    "combustion",
    "indoor_activity",
    "mixed_pollution",
    "random",
    "custom",
)

# Profiles are intentionally broad synthetic patterns, not sensor fingerprints.
_PROFILES: dict[str, dict[str, float]] = {
    "clean_background": {"temp": 28.0, "humidity": 58.0, "pm1": 8.0, "pm25": 18.0, "pm10": 32.0, "mq2": 0.9, "mq9": 0.7, "mq135": 0.8, "variation": 0.08, "spike": 0.01},
    "traffic": {"temp": 32.0, "humidity": 48.0, "pm1": 20.0, "pm25": 48.0, "pm10": 78.0, "mq2": 1.4, "mq9": 1.8, "mq135": 1.6, "variation": 0.18, "spike": 0.04},
    "heavy_dust": {"temp": 34.0, "humidity": 40.0, "pm1": 16.0, "pm25": 48.0, "pm10": 175.0, "mq2": 1.0, "mq9": 0.8, "mq135": 0.9, "variation": 0.2, "spike": 0.06},
    "construction": {"temp": 33.0, "humidity": 43.0, "pm1": 22.0, "pm25": 65.0, "pm10": 155.0, "mq2": 1.1, "mq9": 1.3, "mq135": 1.2, "variation": 0.28, "spike": 0.08},
    "combustion": {"temp": 30.0, "humidity": 50.0, "pm1": 42.0, "pm25": 84.0, "pm10": 108.0, "mq2": 2.3, "mq9": 1.7, "mq135": 2.0, "variation": 0.24, "spike": 0.07},
    "indoor_activity": {"temp": 26.0, "humidity": 55.0, "pm1": 12.0, "pm25": 28.0, "pm10": 40.0, "mq2": 1.0, "mq9": 0.85, "mq135": 1.1, "variation": 0.14, "spike": 0.02},
    "mixed_pollution": {"temp": 31.0, "humidity": 48.0, "pm1": 35.0, "pm25": 90.0, "pm10": 145.0, "mq2": 2.0, "mq9": 1.9, "mq135": 2.0, "variation": 0.3, "spike": 0.1},
    "random": {"temp": 27.0, "humidity": 55.0, "pm1": 18.0, "pm25": 42.0, "pm10": 75.0, "mq2": 1.3, "mq9": 1.2, "mq135": 1.4, "variation": 0.35, "spike": 0.08},
}


@dataclass
class ScenarioGenerator:
    """Generate schema-valid readings for one simulated node."""

    node_id: str
    scenario: str = "clean_background"
    seed: int = 42
    noise: float = 1.0
    start_time: datetime | None = None
    custom: dict[str, float] = field(default_factory=dict)
    exact: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.scenario not in SCENARIOS:
            raise ValueError(f"Unknown scenario '{self.scenario}'. Choose from: {', '.join(SCENARIOS)}")
        self._rng = random.Random(self.seed)
        self._start = self.start_time or datetime.now(timezone.utc)
        if self._start.tzinfo is None:
            self._start = self._start.replace(tzinfo=timezone.utc)
        else:
            self._start = self._start.astimezone(timezone.utc)
        self._index = 0

    def next_payload(self, interval_seconds: float = 5.0) -> dict[str, Any]:
        """Return the next backend-compatible JSON payload."""
        index = self._index
        self._index += 1
        profile = dict(_PROFILES.get(self.scenario, _PROFILES["clean_background"]))
        if self.scenario == "custom":
            profile.update(self.custom)
        if self.scenario == "random":
            profile["variation"] = self._rng.uniform(0.15, 0.4)

        phase = index / 12.0
        wave = math.sin(phase) * profile["variation"]
        pulse = math.sin(phase * 0.37 + 1.3) * profile["variation"] * 0.55
        spike = 1.0
        if self._rng.random() < profile["spike"]:
            spike = self._rng.uniform(1.25, 2.2)

        def value(name: str, scale: float = 1.0) -> float:
            if name in self.exact:
                return self.exact[name]
            base = profile[name] * (1.0 + wave * scale + pulse * 0.4)
            return max(0.0, base + self._rng.gauss(0.0, max(profile[name] * 0.025 * self.noise, 0.001)))

        pm1 = value("pm1") if "pm1" in self.exact else value("pm1") * spike
        pm25 = value("pm25") if "pm25" in self.exact else value("pm25") * spike
        pm10 = value("pm10") if "pm10" in self.exact else value("pm10") * spike
        pm25 = max(pm1, pm25)
        pm10 = max(pm25, pm10)
        temperature = min(85.0, max(-40.0, value("temp", 0.25)))
        humidity = min(100.0, max(0.0, value("humidity", 0.18)))

        voltages = {
            "MQ2": min(5.0, max(0.0, value("mq2", 0.8) if "mq2" in self.exact else value("mq2", 0.8) * (1.0 + (spike - 1.0) * 0.6))),
            "MQ9": min(5.0, max(0.0, value("mq9", 0.8) if "mq9" in self.exact else value("mq9", 0.8) * (1.0 + (spike - 1.0) * 0.5))),
            "MQ135": min(5.0, max(0.0, value("mq135", 0.8) if "mq135" in self.exact else value("mq135", 0.8) * (1.0 + (spike - 1.0) * 0.55))),
        }
        gas_sensors = {
            name: {"raw_adc": int(round(voltage * 1023 / 5.0)), "voltage_V": round(voltage, 3)}
            for name, voltage in voltages.items()
        }
        timestamp = self._start + timedelta(seconds=index * interval_seconds)
        payload = {
            "node_id": self.node_id,
            "timestamp": timestamp.isoformat(),
            "environment": {"temperature_C": round(temperature, 2), "humidity_pct": round(humidity, 2)},
            "particulate_matter": {"PM1_0": round(pm1, 2), "PM2_5": round(pm25, 2), "PM10": round(pm10, 2)},
            "gas_sensors": gas_sensors,
        }
        SensorPayload.model_validate(payload)
        return payload


def available_scenarios() -> tuple[str, ...]:
    return SCENARIOS
