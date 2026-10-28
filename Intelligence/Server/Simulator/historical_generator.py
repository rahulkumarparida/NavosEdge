"""
Historical Dataset Generator for NavosEdge.

Generates reproducible, physically-constrained, multi-week datasets (>= 35 days)
using real historical weather and PM context (from Open-Meteo or CPCB stations)
blended with controlled high-frequency sampling, scenario modeling, and fault injection.

Every record tracks source provenance (OBSERVED, REANALYSIS, SYNTHETIC, DERIVED)
and adheres strictly to the backend `SensorPayload` schema.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import sys
# Ensure imports resolve whether run from root or inside Intelligence/Server
server_dir = Path(__file__).resolve().parent.parent
root_dir = server_dir.parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))
if str(server_dir) not in sys.path:
    sys.path.insert(0, str(server_dir))

from app.schemas.sensor import SensorPayload
from simulation.historical_data import HistoricalDataAcquisition, HourlyContextRecord


@dataclass
class GenerationConfig:
    node_id: str = "hist-node-01"
    days: int = 35
    sampling_interval_seconds: float = 300.0  # 5 minutes
    seed: int = 42
    start_date: str = "2024-09-01"
    location: str = "bhubaneswar"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    station_csv: Optional[str] = None
    inject_faults: bool = True
    noise_scale: float = 1.0


class HistoricalDatasetGenerator:
    """Produces multi-week timestamped sensor datasets anchored in historical context."""

    def __init__(self, config: GenerationConfig) -> None:
        self.config = config
        self._rng = random.Random(config.seed)
        
        # Determine date range
        self.start_dt = datetime.fromisoformat(config.start_date).replace(tzinfo=timezone.utc)
        self.end_dt = self.start_dt + timedelta(days=config.days)
        end_date_str = (self.end_dt - timedelta(days=1)).strftime("%Y-%m-%d")

        # Fetch / load context
        acq = HistoricalDataAcquisition(
            location=config.location,
            latitude=config.latitude,
            longitude=config.longitude,
        )
        self.context_records = acq.build_context_series(
            config.start_date,
            end_date_str,
            station_csv=config.station_csv,
        )
        if not self.context_records:
            raise RuntimeError(f"No historical context records available for {config.start_date} to {end_date_str}")

        # Index context by timestamp for fast lookup and interpolation
        self._context_by_hour: Dict[datetime, HourlyContextRecord] = {}
        for r in self.context_records:
            try:
                dt = datetime.fromisoformat(r.timestamp).replace(tzinfo=timezone.utc)
                self._context_by_hour[dt] = r
            except ValueError:
                pass
        self._sorted_context_hours = sorted(self._context_by_hour.keys())

    def _get_context_for_time(self, cur_time: datetime) -> HourlyContextRecord:
        """Find the nearest hourly context record for a given timestamp."""
        # Find hourly bucket
        hour_floor = cur_time.replace(minute=0, second=0, microsecond=0)
        if hour_floor in self._context_by_hour:
            return self._context_by_hour[hour_floor]
        # Fallback to closest available hour
        closest = min(self._sorted_context_hours, key=lambda h: abs((h - cur_time).total_seconds()))
        return self._context_by_hour[closest]

    def _determine_scenario(self, day_index: int, solar_hour: float) -> str:
        """Schedule scenarios across the 35-day timeline."""
        if day_index < 5:
            return "clean_background"
        elif day_index < 10:
            return "traffic"
        elif day_index < 15:
            return "construction_dust"
        elif day_index < 19:
            return "combustion_smoke"
        elif day_index < 24:
            return "mixed_pollution"
        elif day_index < 29:
            return "seasonal_drift"
        else:
            return "sensor_health_and_faults"

    def generate_all(self) -> List[Dict[str, Any]]:
        """Generate the full multi-week dataset."""
        total_seconds = self.config.days * 86400.0
        step_seconds = self.config.sampling_interval_seconds
        total_steps = int(total_seconds / step_seconds)

        records: List[Dict[str, Any]] = []
        cur_time = self.start_dt
        step = 0

        # State for faults and continuity
        mq2_stuck_val: Optional[float] = None
        mq135_drift_accum = 0.0

        while step < total_steps:
            elapsed_days = (cur_time - self.start_dt).total_seconds() / 86400.0
            day_index = int(elapsed_days)
            solar_hour = cur_time.hour + cur_time.minute / 60.0 + cur_time.second / 3600.0

            # 1. Contextual anchors
            ctx = self._get_context_for_time(cur_time)
            base_temp = ctx.temperature_C
            base_hum = ctx.humidity_pct
            base_pm25 = ctx.pm25 if ctx.pm25 is not None else 35.0
            base_pm10 = ctx.pm10 if ctx.pm10 is not None else (base_pm25 * 1.5)

            # 2. Scenario modulation
            scenario = self._determine_scenario(day_index, solar_hour)
            fault_type: Optional[str] = None
            is_fault = False

            # High-frequency noise
            temp_noise = self._rng.gauss(0.0, 0.15 * self.config.noise_scale)
            hum_noise = self._rng.gauss(0.0, 0.5 * self.config.noise_scale)
            pm_noise = self._rng.gauss(0.0, 1.2 * self.config.noise_scale)

            temp = max(-35.0, min(60.0, base_temp + temp_noise))
            hum = max(5.0, min(100.0, base_hum + hum_noise))

            # Gas sensor baseline idle responses (synthetic response voltage, not calibrated concentration)
            mq2_v = 0.85 + self._rng.gauss(0.0, 0.02)
            mq9_v = 0.72 + self._rng.gauss(0.0, 0.02)
            mq135_v = 0.82 + self._rng.gauss(0.0, 0.02)

            pm25 = base_pm25
            pm10 = base_pm10
            pm1 = pm25 * 0.5

            if scenario == "clean_background":
                pm25 = min(pm25, 25.0)
                pm10 = min(pm10, 45.0)
                pm1 = pm25 * 0.45

            elif scenario == "traffic":
                # Morning and evening rush hours
                morning_rush = math.exp(-((solar_hour - 8.5) ** 2) / 2.0) * 28.0
                evening_rush = math.exp(-((solar_hour - 18.5) ** 2) / 2.5) * 35.0
                rush = morning_rush + evening_rush
                pm25 += rush
                pm10 += rush * 1.4
                pm1 += rush * 0.55
                mq2_v += (rush / 35.0) * 0.8
                mq9_v += (rush / 35.0) * 1.2  # CO from vehicle exhaust
                mq135_v += (rush / 35.0) * 0.9

            elif scenario == "construction_dust":
                # High coarse PM10 during working hours (09:00 - 17:00)
                dust_window = 1.0 if (9.0 <= solar_hour <= 17.0) else 0.2
                dust_boost = self._rng.uniform(60.0, 140.0) * dust_window
                pm10 += dust_boost
                pm25 += dust_boost * 0.35
                pm1 += dust_boost * 0.1
                # Gas sensors stay low (mechanical dust, not combustion gases)
                mq2_v += 0.05
                mq9_v += 0.02
                mq135_v += 0.08

            elif scenario == "combustion_smoke":
                # High fine PM and smoke gases
                smoke_factor = self._rng.uniform(1.5, 2.5)
                pm1 = pm25 * 0.75 * smoke_factor
                pm25 = (pm25 + 60.0) * smoke_factor
                pm10 = pm25 * 1.25
                mq2_v += 1.8  # flammable gas / smoke
                mq135_v += 1.4  # air quality / VOCs

            elif scenario == "mixed_pollution":
                # High humidity + moderate traffic & biomass
                if hum > 85.0:
                    # Hygroscopic growth / rain washout
                    pm25 *= 0.65
                    pm10 *= 0.60
                else:
                    pm25 += 20.0
                    pm10 += 35.0
                    mq2_v += 0.4
                    mq9_v += 0.3
                    mq135_v += 0.4

            elif scenario == "seasonal_drift":
                # October/November seasonal transition: cooling temps, stagnant boundary layer
                drift_progress = (day_index - 24) / 5.0
                temp -= drift_progress * 2.5
                pm25 += drift_progress * 25.0
                pm10 += drift_progress * 35.0

            elif scenario == "sensor_health_and_faults" and self.config.inject_faults:
                # Controlled diagnostic validation
                fault_day = day_index - 29
                if fault_day == 0 and cur_time.hour < 1:
                    # Sensor warmup
                    fault_type = "warmup"
                    is_fault = True
                    progress = cur_time.minute / 60.0
                    mq2_v *= (0.3 + 0.7 * progress)
                    mq9_v *= (0.3 + 0.7 * progress)
                    mq135_v *= (0.3 + 0.7 * progress)
                elif fault_day == 1 and (10 <= cur_time.hour < 14):
                    # Stuck sensor
                    fault_type = "stuck_value"
                    is_fault = True
                    if mq2_stuck_val is None:
                        mq2_stuck_val = 1.428
                    mq2_v = mq2_stuck_val
                elif fault_day == 2:
                    # Sensor drift
                    fault_type = "sensor_drift"
                    is_fault = True
                    mq135_drift_accum += 0.015
                    mq135_v = min(4.8, mq135_v + mq135_drift_accum)
                elif fault_day == 3 and (12 <= cur_time.hour < 13):
                    # Rail fault on MQ9 (rail_low, then rail_high)
                    is_fault = True
                    if cur_time.minute < 30:
                        fault_type = "rail_low"
                        mq9_v = 0.005
                    else:
                        fault_type = "rail_high"
                        mq9_v = 4.995
                elif fault_day == 4 and (14 <= cur_time.hour < 16):
                    # Missing readings / transmission drop
                    fault_type = "missing_data"
                    # Advance time without outputting records (simulating hardware offline)
                    cur_time += timedelta(hours=2)
                    step += int(7200 / step_seconds)
                    continue

            # Apply noise and enforce physical boundaries
            pm25 = max(1.0, pm25 + pm_noise)
            pm1 = max(0.5, min(pm25, pm1))
            pm10 = max(pm25, pm10 + pm_noise)

            mq2_v = min(4.99, max(0.01, mq2_v))
            mq9_v = min(4.99, max(0.01, mq9_v))
            mq135_v = min(4.99, max(0.01, mq135_v))

            gas_sensors = {
                "MQ2": {"raw_adc": int(round(mq2_v * 1023 / 5.0)), "voltage_V": round(mq2_v, 3)},
                "MQ9": {"raw_adc": int(round(mq9_v * 1023 / 5.0)), "voltage_V": round(mq9_v, 3)},
                "MQ135": {"raw_adc": int(round(mq135_v * 1023 / 5.0)), "voltage_V": round(mq135_v, 3)},
            }

            # Provenance determination
            if is_fault:
                source_mode = "SYNTHETIC"
            elif ctx.pm_provenance == "OBSERVED":
                source_mode = "DERIVED"  # Derived/resampled from observed
            elif ctx.pm_provenance == "REANALYSIS":
                source_mode = "DERIVED"  # Derived/resampled from reanalysis
            else:
                source_mode = "SYNTHETIC"

            provenance = {
                "source_mode": source_mode,
                "weather_source": ctx.weather_provenance,
                "pm_source": ctx.pm_provenance,
                "gas_source": "SYNTHETIC_SENSOR_RESPONSE",
                "original_source_timestamp": ctx.timestamp,
                "scenario": scenario,
                "fault": fault_type,
            }

            payload = {
                "node_id": self.config.node_id,
                "timestamp": cur_time.isoformat(),
                "environment": {
                    "temperature_C": round(temp, 2),
                    "humidity_pct": round(hum, 2),
                },
                "particulate_matter": {
                    "PM1_0": round(pm1, 2),
                    "PM2_5": round(pm25, 2),
                    "PM10": round(pm10, 2),
                },
                "gas_sensors": gas_sensors,
                "provenance": provenance,
            }

            # Strict validation
            SensorPayload.model_validate(payload)
            records.append(payload)

            cur_time += timedelta(seconds=step_seconds)
            step += 1

        return records
