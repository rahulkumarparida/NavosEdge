"""
Synthetic PM data generator for testing the forecast plugin.

Generates timestamped PM1.0, PM2.5, PM10 time-series with:
- Diurnal baseline variation (sinusoidal cycle)
- Gradual trend (linear ramp up/down)
- Random spikes (short-lived jumps)
- Gaussian noise

All generated data is clearly labelled as **synthetic**.
"""

import json
import logging
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

from app.schemas.forecast import (
    ForecastReadingInput,
    SyntheticGeneratorConfig,
    SyntheticGeneratorResponse,
)

logger = logging.getLogger(__name__)

# Typical ambient PM baselines (µg/m³)
_BASELINES = {"PM1_0": 12.0, "PM2_5": 25.0, "PM10": 50.0}
# Inter-channel ratios (PM1.0 < PM2.5 < PM10)
_RATIOS = {"PM1_0": 0.48, "PM2_5": 1.0, "PM10": 2.0}


def generate_synthetic_series(
    config: SyntheticGeneratorConfig,
) -> List[ForecastReadingInput]:
    """
    Generate a list of synthetic PM readings.

    Parameters
    ----------
    config : SyntheticGeneratorConfig
        Generator configuration.

    Returns
    -------
    list[ForecastReadingInput]
        Chronologically ordered synthetic readings.
    """
    rng = random.Random(config.seed if config.seed is not None else 42)
    seed_used = config.seed if config.seed is not None else 42

    total_minutes = config.duration_hours * 60
    n_samples = total_minutes // config.sampling_interval_minutes
    start_time = datetime.now(timezone.utc) - timedelta(hours=config.duration_hours)

    readings: list[ForecastReadingInput] = []

    # Pre-generate spike positions
    spike_positions: set[int] = set()
    if config.include_spikes:
        n_spikes = max(1, n_samples // 50)  # ~2% of readings
        spike_positions = set(rng.sample(range(n_samples), min(n_spikes, n_samples)))

    # Trend direction
    trend_direction = rng.choice([-1, 1]) if config.include_trend else 0

    for i in range(n_samples):
        ts = start_time + timedelta(minutes=i * config.sampling_interval_minutes)
        fraction = i / max(n_samples - 1, 1)  # 0..1 over full duration

        # Diurnal component: 24-hour sinusoidal cycle
        hour_angle = 2 * math.pi * (ts.hour + ts.minute / 60) / 24
        diurnal_factor = 1.0 + 0.3 * math.sin(hour_angle - math.pi / 2)

        # Trend component
        trend_factor = 1.0 + trend_direction * 0.2 * fraction

        # Spike component
        spike_factor = 1.0
        if i in spike_positions:
            spike_factor = rng.uniform(2.0, 5.0)

        pm_values: dict[str, float] = {}
        for ch in ["PM1_0", "PM2_5", "PM10"]:
            base = _BASELINES[ch] * _RATIOS[ch] / _RATIOS["PM2_5"]
            value = base * diurnal_factor * trend_factor * spike_factor
            noise = rng.gauss(0, config.noise_level * base * 0.05)
            value = max(0.0, value + noise)
            pm_values[ch] = round(value, 2)

        # Enforce PM ordering: PM1.0 <= PM2.5 <= PM10
        pm_values["PM2_5"] = max(pm_values["PM2_5"], pm_values["PM1_0"])
        pm_values["PM10"] = max(pm_values["PM10"], pm_values["PM2_5"])

        readings.append(
            ForecastReadingInput(
                node_id=config.node_id,
                timestamp=ts,
                PM1_0=pm_values["PM1_0"],
                PM2_5=pm_values["PM2_5"],
                PM10=pm_values["PM10"],
                is_synthetic=True,
            )
        )

    return readings


def save_synthetic_to_jsonl(
    readings: List[ForecastReadingInput], output_path: Path
) -> int:
    """
    Save generated readings to a JSONL file (same format as forecast store).

    Returns the number of records written.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with open(output_path, "w", encoding="utf-8") as fh:
        for r in readings:
            record = {
                "timestamp": r.timestamp.isoformat(),
                "node_id": r.node_id,
                "PM1_0": r.PM1_0,
                "PM2_5": r.PM2_5,
                "PM10": r.PM10,
                "is_synthetic": True,
            }
            fh.write(json.dumps(record) + "\n")
            count += 1
    logger.info("Saved %d synthetic records to %s", count, output_path)
    return count


def replay_through_plugin(
    readings: List[ForecastReadingInput],
    plugin,  # ForecastPlugin — avoid circular import
) -> int:
    """
    Replay synthetic readings through the plugin's normal ingestion pipeline.

    Returns the number of records successfully ingested.
    """
    count = 0
    for reading in readings:
        try:
            plugin.ingest(reading)
            count += 1
        except Exception as exc:
            logger.warning("Failed to ingest synthetic reading: %s", exc)
    logger.info("Replayed %d synthetic readings through plugin.", count)
    return count
