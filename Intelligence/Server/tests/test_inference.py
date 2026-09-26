"""
Tests for inference adapter behavior when model is not configured.
"""

import pytest

from app.schemas.inference import InferenceStatus
from app.services.inference import TinyGasNetAdapter

import tempfile
from pathlib import Path


@pytest.mark.asyncio
async def test_not_configured_when_no_artifacts():
    adapter = TinyGasNetAdapter(artifacts_dir=Path(tempfile.mkdtemp()))
    adapter.load()
    assert adapter._loaded is False

    result = await adapter.predict(1.0, 1.5, 2.0, 25.0, 50.0)
    assert result.status == InferenceStatus.NOT_CONFIGURED
    assert result.gas_class is None
    assert result.class_confidence is None
    assert result.safety_status is None
    assert result.error_message is None


@pytest.mark.asyncio
async def test_inference_result_not_configured_classmethod():
    from app.schemas.inference import InferenceResult
    r = InferenceResult.not_configured()
    assert r.status == InferenceStatus.NOT_CONFIGURED


@pytest.mark.asyncio
async def test_inference_result_from_error():
    from app.schemas.inference import InferenceResult
    r = InferenceResult.from_error("something broke")
    assert r.status == InferenceStatus.ERROR
    assert r.error_message == "something broke"
