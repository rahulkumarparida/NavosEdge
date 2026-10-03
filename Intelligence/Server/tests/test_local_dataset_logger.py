"""
Unit and Integration Tests for LocalDatasetLogger (Phase 14)
"""

import os
import shutil
import tempfile
import pandas as pd
import pytest
from datetime import datetime, timezone
from pathlib import Path

from app.schemas.sensor import SensorPayload
from app.storage.local_dataset_logger import LocalDatasetLogger, CSV_HEADER


@pytest.fixture
def temp_dataset_dir():
    tmp_dir = tempfile.mkdtemp()
    yield Path(tmp_dir)
    shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.fixture
def sample_payload():
    return SensorPayload(
        node_id="uno-q-test-01",
        timestamp=datetime(2026, 10, 3, 14, 30, 0, tzinfo=timezone.utc),
        environment={"temperature_C": 28.5, "humidity_pct": 65.0},
        particulate_matter={"PM1_0": 12.0, "PM2_5": 18.0, "PM10": 25.0},
        gas_sensors={
            "MQ2": {"raw_adc": 350, "voltage_V": 1.71},
            "MQ9": {"raw_adc": 280, "voltage_V": 1.37},
            "MQ135": {"raw_adc": 420, "voltage_V": 2.05},
        },
    )


def test_logger_creates_directory_and_file(temp_dataset_dir, sample_payload):
    logger = LocalDatasetLogger(dataset_dir=temp_dataset_dir)
    success = logger.log_reading(sample_payload)
    assert success is True

    expected_file = temp_dataset_dir / "2026-10-03.csv"
    assert expected_file.exists()

    df = pd.read_csv(expected_file)
    assert list(df.columns) == CSV_HEADER
    assert len(df) == 1
    assert df.iloc[0]["node_id"] == "uno-q-test-01"
    assert df.iloc[0]["temperature_C"] == 28.5
    assert df.iloc[0]["humidity_pct"] == 65.0
    assert df.iloc[0]["PM1_0"] == 12.0
    assert df.iloc[0]["PM2_5"] == 18.0
    assert df.iloc[0]["PM10"] == 25.0
    assert df.iloc[0]["MQ2_raw_adc"] == 350
    assert df.iloc[0]["MQ2_voltage_V"] == 1.71
    assert df.iloc[0]["MQ9_raw_adc"] == 280
    assert df.iloc[0]["MQ9_voltage_V"] == 1.37
    assert df.iloc[0]["MQ135_raw_adc"] == 420
    assert df.iloc[0]["MQ135_voltage_V"] == 2.05


def test_logger_appends_without_header_duplication(temp_dataset_dir, sample_payload):
    logger1 = LocalDatasetLogger(dataset_dir=temp_dataset_dir)
    logger1.log_reading(sample_payload)

    # Re-instantiate logger to simulate server/app restart
    logger2 = LocalDatasetLogger(dataset_dir=temp_dataset_dir)
    payload2 = SensorPayload(
        node_id="uno-q-test-01",
        timestamp=datetime(2026, 10, 3, 14, 31, 0, tzinfo=timezone.utc),
        environment={"temperature_C": 29.0, "humidity_pct": 64.0},
        particulate_matter={"PM1_0": 13.0, "PM2_5": 19.0, "PM10": 26.0},
        gas_sensors={
            "MQ2": {"raw_adc": 355, "voltage_V": 1.73},
            "MQ9": {"raw_adc": 285, "voltage_V": 1.39},
            "MQ135": {"raw_adc": 425, "voltage_V": 2.07},
        },
    )
    logger2.log_reading(payload2)

    expected_file = temp_dataset_dir / "2026-10-03.csv"
    df = pd.read_csv(expected_file)
    assert len(df) == 2
    assert list(df.columns) == CSV_HEADER
    assert df.iloc[1]["temperature_C"] == 29.0


def test_logger_handles_new_date(temp_dataset_dir, sample_payload):
    logger = LocalDatasetLogger(dataset_dir=temp_dataset_dir)
    logger.log_reading(sample_payload)

    payload_next_day = SensorPayload(
        node_id="uno-q-test-01",
        timestamp=datetime(2026, 10, 4, 0, 5, 0, tzinfo=timezone.utc),
        environment={"temperature_C": 22.0, "humidity_pct": 70.0},
        particulate_matter={"PM1_0": 8.0, "PM2_5": 10.0, "PM10": 15.0},
        gas_sensors={
            "MQ2": {"raw_adc": 200, "voltage_V": 0.98},
            "MQ9": {"raw_adc": 180, "voltage_V": 0.88},
            "MQ135": {"raw_adc": 300, "voltage_V": 1.47},
        },
    )
    logger.log_reading(payload_next_day)

    file_day1 = temp_dataset_dir / "2026-10-03.csv"
    file_day2 = temp_dataset_dir / "2026-10-04.csv"

    assert file_day1.exists()
    assert file_day2.exists()

    df1 = pd.read_csv(file_day1)
    df2 = pd.read_csv(file_day2)

    assert len(df1) == 1
    assert len(df2) == 1
    assert df2.iloc[0]["temperature_C"] == 22.0
