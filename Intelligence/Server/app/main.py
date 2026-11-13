"""
NavosEdge Intelligence Server — FastAPI application entry point.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings, parse_cors_origins, validate_production_config
from app.core.logging import setup_logging
from app.schemas.responses import ErrorResponse
from app.storage.jsonl_store import JsonlStorageService
from app.services.numpy_inference import NumpyGasNetAdapter
from app.services.node_registry import NodeRegistry
from app.services.events import EventService
from app.services.processing import ProcessingService
from app.anomaly.engine import AnomalyEngine
from app.emergency.actuator_service import ActuatorService
from app.emergency.database import EmergencyDatabase
from app.emergency.hazard_evaluator import HazardEvaluator
from app.emergency.notification_provider import (
    SimulatedNotificationProvider,
    TwilioNotificationProvider,
)
from app.emergency.notification_service import (
    EmergencyNotificationService,
    EscalationWorker,
)
from app.emergency.response_policy import HazardPolicyService, ResponsePolicyEngine
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
    validate_production_config(settings)
    logger.info("Starting NavosEdge Intelligence Server v%s (env=%s)", settings.APP_VERSION, settings.ENV)

    # Ensure directories
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    settings.ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    # Storage
    storage = JsonlStorageService(
        data_dir=settings.DATA_DIR,
        max_file_size_mb=settings.STORAGE_MAX_FILE_SIZE_MB,
        max_files_per_node=settings.STORAGE_MAX_FILES_PER_NODE,
    )

    # Phase 1 — Persistent Emergency SQLite Database
    emergency_db = EmergencyDatabase(db_path=settings.EMERGENCY_DB_PATH)
    emergency_db.initialize()

    # Phase 2 — Environmental Hazard Evaluator & Response Policy Engine
    hazard_evaluator = HazardEvaluator(settings=settings)
    response_policy_engine = ResponsePolicyEngine(emergency_db=emergency_db)
    hazard_policy_service = HazardPolicyService(
        evaluator=hazard_evaluator,
        policy_engine=response_policy_engine,
    )

    # Phase 3 — ESP32 Wireless Actuator Service
    actuator_service = ActuatorService(
        emergency_db=emergency_db,
        esp32_port=settings.ACTUATOR_HTTP_PORT,
        command_timeout_s=settings.ACTUATOR_COMMAND_TIMEOUT_S,
        heartbeat_stale_s=settings.ACTUATOR_HEARTBEAT_STALE_S,
        duplicate_window_s=settings.ACTUATOR_DUPLICATE_WINDOW_S,
        default_lease_s=settings.ACTUATOR_DEFAULT_LEASE_S,
        demo_mode_enabled=settings.ACTUATOR_DEMO_MODE,
    )

    # Phase 4 — Emergency Notification & Caregiver Escalation (defaults to SIMULATED)
    if settings.TWILIO_MODE == "LIVE":
        notification_provider = TwilioNotificationProvider(
            account_sid=settings.TWILIO_ACCOUNT_SID,
            auth_token=settings.TWILIO_AUTH_TOKEN,
            from_number=settings.TWILIO_FROM_NUMBER,
            timeout_s=settings.TWILIO_TIMEOUT_S,
        )
    else:
        notification_provider = SimulatedNotificationProvider()

    notification_service = EmergencyNotificationService(
        emergency_db=emergency_db,
        provider=notification_provider,
        ack_signing_secret=settings.ACK_SIGNING_SECRET,
        public_webhook_base_url=settings.PUBLIC_WEBHOOK_BASE_URL,
        ack_timeout_s=settings.ESCALATION_ACK_TIMEOUT_S,
        demo_ack_timeout_s=settings.ESCALATION_DEMO_TIMEOUT_S,
        demo_mode=settings.ESCALATION_DEMO_MODE,
    )
    escalation_worker = EscalationWorker(notification_service=notification_service)
    escalation_worker.start()

    # Inference adapter
    inference_adapter = NumpyGasNetAdapter(artifacts_dir=settings.ARTIFACTS_DIR)
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
        hazard_policy_service=hazard_policy_service,
        actuator_service=actuator_service,
        notification_service=notification_service,
    )

    # Attach to app state so route handlers can access them
    app.state.settings = settings
    app.state.storage = storage
    app.state.emergency_db = emergency_db
    app.state.hazard_evaluator = hazard_evaluator
    app.state.response_policy_engine = response_policy_engine
    app.state.hazard_policy_service = hazard_policy_service
    app.state.actuator_service = actuator_service
    app.state.notification_service = notification_service
    app.state.escalation_worker = escalation_worker
    app.state.inference_adapter = inference_adapter
    app.state.node_registry = node_registry
    app.state.event_service = event_service
    app.state.processing_service = processing_service
    app.state.anomaly_engine = anomaly_engine
    app.state.source_classifier = source_classifier
    app.state.forecast_plugin = forecast_plugin
    app.state.aqi_service = aqi_service

    async def _stale_actuator_monitor() -> None:
        while True:
            try:
                await asyncio.sleep(30.0)
                stale = actuator_service.mark_stale_actuators_offline()
                if stale:
                    logger.warning(
                        "Marked %d stale actuator(s) OFFLINE after >%.0fs without heartbeat: %s",
                        len(stale),
                        settings.ACTUATOR_HEARTBEAT_STALE_S,
                        [a.actuator_id for a in stale],
                    )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Stale actuator monitor tick error: %s", exc)

    stale_actuator_task = asyncio.create_task(_stale_actuator_monitor())

    logger.info(
        "Startup complete — model loaded: %s, source classifier loaded: %s, forecast plugin: %s, emergency db: %s",
        inference_adapter._loaded,
        source_classifier.is_loaded,
        forecast_plugin.is_initialized,
        emergency_db.is_initialized,
    )
    yield
    # Shutdown
    stale_actuator_task.cancel()
    try:
        await stale_actuator_task
    except asyncio.CancelledError:
        pass
    await escalation_worker.stop()
    await notification_service.drain_background_tasks(timeout_s=5.0)
    if forecast_plugin.is_initialized:
        forecast_plugin.shutdown()
    emergency_db.close()
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

    cors_origins = parse_cors_origins(settings.CORS_ORIGINS)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=cors_origins != ["*"],
        allow_methods=["*"],
        allow_headers=["*"],
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
        detail = (
            "An unexpected internal error occurred."
            if settings.ENV == "production"
            else str(exc)
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error="Internal server error",
                detail=detail,
                timestamp=datetime.now(timezone.utc),
            ).model_dump(mode="json"),
        )

    # --- Routers ---
    app.include_router(health_router)
    app.include_router(nodes_router)
    app.include_router(forecast_router)
    from app.aqi.router import router as aqi_router
    app.include_router(aqi_router)
    from app.api.routes.hardware import router as hardware_router
    app.include_router(hardware_router)
    from app.api.routes.actuators import router as actuators_router
    app.include_router(actuators_router)
    from app.api.routes.notifications import router as notifications_router
    app.include_router(notifications_router)
    from app.api.routes.emergency import router as emergency_router
    app.include_router(emergency_router)

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
