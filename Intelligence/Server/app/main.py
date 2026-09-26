"""
NavosEdge Intelligence Server — FastAPI application entry point.
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.schemas.responses import ErrorResponse
from app.storage.jsonl_store import JsonlStorageService
from app.services.inference import TinyGasNetAdapter
from app.services.node_registry import NodeRegistry
from app.services.events import EventService
from app.services.processing import ProcessingService
from app.anomaly.engine import AnomalyEngine
from app.source_classifier.classifier import SourceClassifier
from app.forecast.plugin import ForecastPlugin
from app.forecast.config import ForecastSettings
from app.api.routes.health import router as health_router
from app.api.routes.nodes import router as nodes_router
from app.api.routes.forecast import router as forecast_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.LOG_LEVEL)
    logger.info("Starting NavosEdge Intelligence Server v%s", settings.APP_VERSION)

    # Ensure directories
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    settings.ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    # Storage
    storage = JsonlStorageService(
        data_dir=settings.DATA_DIR,
        max_file_size_mb=settings.STORAGE_MAX_FILE_SIZE_MB,
        max_files_per_node=settings.STORAGE_MAX_FILES_PER_NODE,
    )

    # Inference adapter
    inference_adapter = TinyGasNetAdapter(artifacts_dir=settings.ARTIFACTS_DIR)
    inference_adapter.load()

    # Anomaly engine
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

    # Source classifier (Phase 3)
    source_classifier = SourceClassifier(artifacts_dir=settings.ARTIFACTS_DIR)
    source_classifier.load()  # Fails gracefully if artifacts missing

    # Registries / services
    node_registry = NodeRegistry()
    event_service = EventService(
        heartbeat_interval=settings.SSE_HEARTBEAT_INTERVAL_S
    )
    # Phase 4 — Forecast plugin
    forecast_plugin = ForecastPlugin()
    if settings.FORECAST_ENABLED:
        forecast_settings = ForecastSettings(
            STORAGE_DIR=settings.FORECAST_STORAGE_DIR,
            RETENTION_HOURS=settings.FORECAST_RETENTION_HOURS,
            DEFAULT_HORIZON_MINUTES=settings.FORECAST_DEFAULT_HORIZON_MINUTES,
            DEFAULT_SAMPLING_INTERVAL_MINUTES=settings.FORECAST_DEFAULT_SAMPLING_INTERVAL_MINUTES,
        )
        forecast_plugin.initialize(forecast_settings)

    # AQI Service
    from app.aqi.service import AQIService
    from app.aqi.router import router as aqi_router

    aqi_service = AQIService(
        storage_path=settings.AQI_STORAGE_FILE,
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

    # Attach to app state so route handlers can access them
    app.state.storage = storage
    app.state.inference_adapter = inference_adapter
    app.state.node_registry = node_registry
    app.state.event_service = event_service
    app.state.processing_service = processing_service
    app.state.anomaly_engine = anomaly_engine
    app.state.source_classifier = source_classifier
    app.state.forecast_plugin = forecast_plugin
    app.state.aqi_service = aqi_service

    logger.info(
        "Startup complete — model loaded: %s, source classifier loaded: %s, forecast plugin: %s",
        inference_adapter._loaded,
        source_classifier.is_loaded,
        forecast_plugin.is_initialized,
    )
    yield
    # Shutdown
    if forecast_plugin.is_initialized:
        forecast_plugin.shutdown()
    logger.info("Shutting down NavosEdge Intelligence Server.")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=(
            "Edge-AI environmental monitoring intelligence backend. "
            "Receives sensor data, runs classification, and stores results."
        ),
        lifespan=lifespan,
    )

    # --- Middleware: payload size limit ---
    @app.middleware("http")
    async def limit_payload_size(request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > settings.MAX_PAYLOAD_BYTES:
            return JSONResponse(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                content=ErrorResponse(
                    error="Payload too large",
                    detail=f"Max allowed: {settings.MAX_PAYLOAD_BYTES} bytes",
                    timestamp=datetime.now(timezone.utc),
                ).model_dump(mode="json"),
            )
        return await call_next(request)

    # --- Exception handlers ---
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ErrorResponse(
                error="Validation error",
                detail=str(exc.errors()),
                timestamp=datetime.now(timezone.utc),
            ).model_dump(mode="json"),
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        logger.error("Unhandled exception: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error="Internal server error",
                detail=str(exc),
                timestamp=datetime.now(timezone.utc),
            ).model_dump(mode="json"),
        )

    # --- Routers ---
    app.include_router(health_router)
    app.include_router(nodes_router)
    app.include_router(forecast_router)
    from app.aqi.router import router as aqi_router
    app.include_router(aqi_router)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        log_level=settings.LOG_LEVEL.lower(),
    )
