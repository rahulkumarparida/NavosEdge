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
    storage_ok = storage.check_storage_health()
    model_loaded = getattr(inference, '_loaded', False)
    return ReadinessResponse(
        ready=storage_ok,
        storage_ok=storage_ok,
        model_loaded=model_loaded,
        timestamp=datetime.now(timezone.utc)
    )
