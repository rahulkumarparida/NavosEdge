from fastapi import APIRouter, Request
from app.schemas.responses import HealthResponse, ReadinessResponse
from app.core.config import get_settings
from datetime import datetime, timezone

router = APIRouter()

@router.get('/health', response_model=HealthResponse)
async def health_check():
    settings = get_settings()
    return HealthResponse(
        status='ok',
        version=settings.APP_VERSION,
        timestamp=datetime.now(timezone.utc)
    )

@router.get('/ready', response_model=ReadinessResponse)
async def readiness_check(request: Request):
    storage = request.app.state.storage
    inference = request.app.state.inference_adapter
    emergency_db = getattr(request.app.state, 'emergency_db', None)
    escalation_worker = getattr(request.app.state, 'escalation_worker', None)
    storage_ok = storage.check_storage_health()
    model_loaded = getattr(inference, '_loaded', False)
    emergency_db_ok = bool(emergency_db is not None and getattr(emergency_db, 'is_initialized', False))
    escalation_worker_running = bool(
        escalation_worker is not None and getattr(escalation_worker, '_task', None) is not None
    )
    return ReadinessResponse(
        ready=storage_ok and emergency_db_ok,
        storage_ok=storage_ok,
        model_loaded=model_loaded,
        emergency_db_ok=emergency_db_ok,
        escalation_worker_running=escalation_worker_running,
        timestamp=datetime.now(timezone.utc)
    )
