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
    "clean_indoor",
    "traffic",
    "heavy_dust",
    "dust_construction",
    "construction",
    "combustion",
    "combustion_smoke",
    "biomass_burning",
    "industrial",
    "indoor_activity",
    "mixed_pollution",
    "high_humidity",
    "pm_spike",
    "gas_spike",
    "stable",
    "unknown_ambiguous",
    "random",
    "custom",
)

# Profiles are broad synthetic patterns aligned with sensor specifications and physical constraints.
_PROFILES: dict[str, dict[str, float]] = {
    "clean_background": {"temp": 25.0, "humidity": 52.0, "pm1": 7.0, "pm25": 14.0, "pm10": 24.0, "mq2": 0.85, "mq9": 0.72, "mq135": 0.82, "variation": 0.08, "spike": 0.01},
    "clean_indoor": {"temp": 24.5, "humidity": 50.0, "pm1": 7.0, "pm25": 14.0, "pm10": 24.0, "mq2": 0.85, "mq9": 0.72, "mq135": 0.82, "variation": 0.08, "spike": 0.01},
    "traffic": {"temp": 31.0, "humidity": 45.0, "pm1": 25.0, "pm25": 55.0, "pm10": 85.0, "mq2": 1.5, "mq9": 2.0, "mq135": 1.7, "variation": 0.18, "spike": 0.04},
    "heavy_dust": {"temp": 33.0, "humidity": 38.0, "pm1": 18.0, "pm25": 65.0, "pm10": 220.0, "mq2": 1.05, "mq9": 0.95, "mq135": 1.0, "variation": 0.22, "spike": 0.06},
    "dust_construction": {"temp": 33.0, "humidity": 38.0, "pm1": 18.0, "pm25": 65.0, "pm10": 220.0, "mq2": 1.05, "mq9": 0.95, "mq135": 1.0, "variation": 0.22, "spike": 0.06},
    "construction": {"temp": 32.5, "humidity": 40.0, "pm1": 24.0, "pm25": 75.0, "pm10": 240.0, "mq2": 1.3, "mq9": 1.6, "mq135": 1.4, "variation": 0.26, "spike": 0.07},
    "combustion": {"temp": 30.5, "humidity": 48.0, "pm1": 55.0, "pm25": 110.0, "pm10": 145.0, "mq2": 2.8, "mq9": 2.1, "mq135": 2.4, "variation": 0.24, "spike": 0.07},
    "combustion_smoke": {"temp": 30.5, "humidity": 48.0, "pm1": 55.0, "pm25": 110.0, "pm10": 145.0, "mq2": 2.8, "mq9": 2.1, "mq135": 2.4, "variation": 0.24, "spike": 0.07},
    "biomass_burning": {"temp": 30.0, "humidity": 50.0, "pm1": 60.0, "pm25": 115.0, "pm10": 150.0, "mq2": 3.0, "mq9": 2.0, "mq135": 2.3, "variation": 0.25, "spike": 0.08},
    "industrial": {"temp": 31.0, "humidity": 46.0, "pm1": 30.0, "pm25": 68.0, "pm10": 110.0, "mq2": 1.6, "mq9": 2.1, "mq135": 2.8, "variation": 0.22, "spike": 0.05},
    "indoor_activity": {"temp": 25.5, "humidity": 55.0, "pm1": 12.0, "pm25": 26.0, "pm10": 38.0, "mq2": 1.05, "mq9": 0.88, "mq135": 1.15, "variation": 0.14, "spike": 0.02},
    "mixed_pollution": {"temp": 31.0, "humidity": 48.0, "pm1": 42.0, "pm25": 95.0, "pm10": 165.0, "mq2": 2.2, "mq9": 2.0, "mq135": 2.1, "variation": 0.28, "spike": 0.09},
    "high_humidity": {"temp": 26.5, "humidity": 92.0, "pm1": 8.0, "pm25": 16.0, "pm10": 26.0, "mq2": 0.95, "mq9": 0.78, "mq135": 0.9, "variation": 0.10, "spike": 0.02},
    "pm_spike": {"temp": 28.0, "humidity": 50.0, "pm1": 120.0, "pm25": 320.0, "pm10": 480.0, "mq2": 1.1, "mq9": 0.9, "mq135": 1.1, "variation": 0.20, "spike": 0.15},
    "gas_spike": {"temp": 28.0, "humidity": 50.0, "pm1": 10.0, "pm25": 22.0, "pm10": 34.0, "mq2": 3.6, "mq9": 3.2, "mq135": 3.8, "variation": 0.20, "spike": 0.15},
    "stable": {"temp": 25.0, "humidity": 50.0, "pm1": 8.0, "pm25": 14.0, "pm10": 22.0, "mq2": 1.0, "mq9": 0.8, "mq135": 0.9, "variation": 0.005, "spike": 0.0},
    "unknown_ambiguous": {"temp": 28.5, "humidity": 52.0, "pm1": 20.0, "pm25": 42.0, "pm10": 68.0, "mq2": 1.45, "mq9": 1.35, "mq135": 1.4, "variation": 0.20, "spike": 0.05},
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

        timestamp = self._start + timedelta(seconds=index * interval_seconds)
        solar_hour = timestamp.hour + timestamp.minute / 60.0 + timestamp.second / 3600.0

        # Temporal diurnal wave (24h solar cycle)
        diurnal_temp = math.sin((solar_hour - 8.5) * (2.0 * math.pi / 24.0)) * 3.5
        diurnal_hum = -math.sin((solar_hour - 9.5) * (2.0 * math.pi / 24.0)) * 10.0

        phase = index / 12.0
        wave = math.sin(phase) * profile["variation"]
        pulse = math.sin(phase * 0.37 + 1.3) * profile["variation"] * 0.55
        spike = 1.0
        if self._rng.random() < profile.get("spike", 0.0):
            spike = self._rng.uniform(1.25, 2.0)

        def value(name: str, scale: float = 1.0) -> float:
            if name in self.exact:
                return self.exact[name]
            base = profile[name] * (1.0 + wave * scale + pulse * 0.4)
            return max(0.0, base + self._rng.gauss(0.0, max(profile[name] * 0.02 * self.noise, 0.001)))

        pm1 = value("pm1") if "pm1" in self.exact else value("pm1") * spike
        pm25 = value("pm25") if "pm25" in self.exact else value("pm25") * spike
        pm10 = value("pm10") if "pm10" in self.exact else value("pm10") * spike
        pm25 = max(pm1, pm25)
        pm10 = max(pm25, pm10)

        if "temp" in self.exact:
            temperature = self.exact["temp"]
        else:
            t_val = value("temp", 0.25) + (diurnal_temp if self.scenario != "stable" else 0.0)
            temperature = min(85.0, max(-40.0, t_val))

        if "humidity" in self.exact:
            humidity = self.exact["humidity"]
        else:
            h_val = value("humidity", 0.18) + (diurnal_hum if self.scenario != "stable" else 0.0)
            humidity = min(100.0, max(0.0, h_val))

        voltages = {
            "MQ2": min(5.0, max(0.0, value("mq2", 0.8) if "mq2" in self.exact else value("mq2", 0.8) * (1.0 + (spike - 1.0) * 0.6))),
            "MQ9": min(5.0, max(0.0, value("mq9", 0.8) if "mq9" in self.exact else value("mq9", 0.8) * (1.0 + (spike - 1.0) * 0.5))),
            "MQ135": min(5.0, max(0.0, value("mq135", 0.8) if "mq135" in self.exact else value("mq135", 0.8) * (1.0 + (spike - 1.0) * 0.55))),
        }
        gas_sensors = {
            name: {"raw_adc": int(round(voltage * 1023 / 5.0)), "voltage_V": round(voltage, 3)}
            for name, voltage in voltages.items()
        }
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

