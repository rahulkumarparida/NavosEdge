"""
Local Dataset Logger — Persistent local sensor dataset logger for NavosEdge.

Appends valid sensor readings to daily CSV files in the root `local_dataset/` directory:
    local_dataset/YYYY-MM-DD.csv

Schema:
    timestamp,node_id,temperature_C,humidity_pct,PM1_0,PM2_5,PM10,MQ2_raw_adc,MQ2_voltage_V,MQ9_raw_adc,MQ9_voltage_V,MQ135_raw_adc,MQ135_voltage_V
"""

import csv
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional, Union

from app.schemas.sensor import SensorPayload

logger = logging.getLogger(__name__)

CSV_HEADER: List[str] = [
    "timestamp",
    "node_id",
    "temperature_C",
    "humidity_pct",
    "PM1_0",
    "PM2_5",
    "PM10",
    "MQ2_raw_adc",
    "MQ2_voltage_V",
    "MQ9_raw_adc",
    "MQ9_voltage_V",
    "MQ135_raw_adc",
    "MQ135_voltage_V",
]


def _find_repo_root() -> Path:
    current = Path(__file__).resolve().parent
    for parent in [current] + list(current.parents):
        if (parent / ".git").exists() or (parent / "run_simulation.sh").exists():
            return parent
    return Path(__file__).resolve().parents[4]


class LocalDatasetLogger:
    """
    Thread-safe, non-blocking persistent CSV logger.
    Appends sensor measurements to daily CSV files at `local_dataset/YYYY-MM-DD.csv`.
    """

    def __init__(self, dataset_dir: Optional[Union[Path, str]] = None) -> None:
        if dataset_dir is None:
            # Default to repo_root/local_dataset
            self.dataset_dir = _find_repo_root() / "local_dataset"
        else:
            self.dataset_dir = Path(dataset_dir)

        self._lock = threading.Lock()

    def log_reading(self, payload: SensorPayload) -> bool:
        """
        Log a valid SensorPayload to local_dataset/YYYY-MM-DD.csv.
        Returns True if successful, False if an error occurred.
        """
        try:
            ts = payload.timestamp
            if isinstance(ts, datetime):
                ts_str = ts.isoformat()
                date_str = ts.strftime("%Y-%m-%d")
            else:
                ts_str = str(ts)
                date_str = ts_str[:10]

            row = [
                ts_str,
                payload.node_id,
                payload.environment.temperature_C,
                payload.environment.humidity_pct,
                payload.particulate_matter.PM1_0,
                payload.particulate_matter.PM2_5,
                payload.particulate_matter.PM10,
                payload.gas_sensors.MQ2.raw_adc,
                payload.gas_sensors.MQ2.voltage_V,
                payload.gas_sensors.MQ9.raw_adc,
                payload.gas_sensors.MQ9.voltage_V,
                payload.gas_sensors.MQ135.raw_adc,
                payload.gas_sensors.MQ135.voltage_V,
            ]

            with self._lock:
                self.dataset_dir.mkdir(parents=True, exist_ok=True)
                csv_path = self.dataset_dir / f"{date_str}.csv"
                file_exists = csv_path.exists() and csv_path.stat().st_size > 0

                with open(csv_path, mode="a", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    if not file_exists:
                        writer.writerow(CSV_HEADER)
                    writer.writerow(row)
                    f.flush()

            logger.debug("Logged sensor reading for %s to %s", payload.node_id, csv_path)
            return True
        except Exception as e:
            logger.error("Failed to log reading to local_dataset: %s", e, exc_info=True)
            return False
