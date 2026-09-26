"""
Shared test fixtures for the NavosEdge Intelligence Server.
"""

import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

# Temp directories for test isolation
_test_data_dir = tempfile.mkdtemp(prefix="navos_test_data_")
_test_artifacts_dir = tempfile.mkdtemp(prefix="navos_test_artifacts_")

os.environ["NAVOS_DATA_DIR"] = _test_data_dir
os.environ["NAVOS_ARTIFACTS_DIR"] = _test_artifacts_dir
os.environ["NAVOS_LOG_LEVEL"] = "WARNING"


def valid_sensor_payload(
    node_id: str = "test-node-01",
    temperature: float = 31.2,
    humidity: float = 68.5,
) -> dict:
    """Returns a valid sensor payload dict with current timestamp."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    return {
        "node_id": node_id,
        "timestamp": now,
        "environment": {
            "temperature_C": temperature,
            "humidity_pct": humidity,
        },
        "particulate_matter": {
            "PM1_0": 18.4,
            "PM2_5": 42.7,
            "PM10": 76.3,
        },
        "gas_sensors": {
            "MQ2": {"raw_adc": 420, "voltage_V": 1.35},
            "MQ9": {"raw_adc": 510, "voltage_V": 1.64},
            "MQ135": {"raw_adc": 610, "voltage_V": 1.96},
        },
    }


@pytest.fixture()
def sample_payload():
    return valid_sensor_payload()


@pytest.fixture()
async def client():
    """
    Async test client that manually initialises app state since
    httpx.ASGITransport does not trigger ASGI lifespan events.
    """
    from app.core.config import get_settings

    get_settings.cache_clear()

    from app.main import create_app
    from app.storage.jsonl_store import JsonlStorageService
    from app.services.inference import TinyGasNetAdapter
    from app.services.node_registry import NodeRegistry
    from app.services.events import EventService
    from app.services.processing import ProcessingService

    app = create_app()
    settings = get_settings()

    # Manually initialise services (mirrors lifespan)
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    settings.ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    storage = JsonlStorageService(
        data_dir=settings.DATA_DIR,
        max_file_size_mb=settings.STORAGE_MAX_FILE_SIZE_MB,
        max_files_per_node=settings.STORAGE_MAX_FILES_PER_NODE,
    )
    inference_adapter = TinyGasNetAdapter(artifacts_dir=settings.ARTIFACTS_DIR)
    inference_adapter.load()
    node_registry = NodeRegistry()
    event_service = EventService(heartbeat_interval=settings.SSE_HEARTBEAT_INTERVAL_S)
    from app.anomaly.engine import AnomalyEngine
    from app.source_classifier.classifier import SourceClassifier
    from app.forecast.plugin import ForecastPlugin
    from app.forecast.config import ForecastSettings

    anomaly_engine = AnomalyEngine(
        window_hours=settings.ANOMALY_HISTORY_WINDOW_HOURS,
        model_update_interval_minutes=settings.ANOMALY_MODEL_UPDATE_INTERVAL_MINUTES,
        threshold_medium=settings.ANOMALY_SCORE_THRESHOLD_MEDIUM,
        threshold_high=settings.ANOMALY_SCORE_THRESHOLD_HIGH,
        bootstrap_samples=settings.ANOMALY_BOOTSTRAP_SAMPLES,
        min_samples_monitoring=settings.ANOMALY_MIN_SAMPLES_FOR_MONITORING,
        min_samples_regression=settings.ANOMALY_MIN_SAMPLES_FOR_REGRESSION,
        stale_data_minutes=settings.ANOMALY_STALE_DATA_MINUTES,
    )
    
    source_classifier = SourceClassifier(artifacts_dir=settings.ARTIFACTS_DIR)
    source_classifier.load()

    # Phase 4 — Forecast plugin
    forecast_plugin = ForecastPlugin()
    forecast_settings = ForecastSettings(
        STORAGE_DIR=Path(_test_data_dir) / "forecast",
        RETENTION_HOURS=48,
    )
    forecast_plugin.initialize(forecast_settings)

    from app.aqi.service import AQIService
    aqi_service = AQIService(
        storage_path=Path(_test_data_dir) / "aqi_latest.json",
        standard=settings.AQI_STANDARD,
    )

    processing_service = ProcessingService(
        inference_adapter=inference_adapter,
        node_registry=node_registry,
        storage=storage,
        event_service=event_service,
        anomaly_engine=anomaly_engine,
        source_classifier=source_classifier,
        forecast_plugin=forecast_plugin,
        aqi_service=aqi_service,
    )

    app.state.storage = storage
    app.state.inference_adapter = inference_adapter
    app.state.node_registry = node_registry
    app.state.event_service = event_service
    app.state.processing_service = processing_service
    app.state.anomaly_engine = anomaly_engine
    app.state.source_classifier = source_classifier
    app.state.forecast_plugin = forecast_plugin
    app.state.aqi_service = aqi_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


def pytest_sessionfinish(session, exitstatus):
    """Clean up temp dirs after all tests."""
    for d in (_test_data_dir, _test_artifacts_dir):
        if os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)
