"""
Tests for the genuine model inference adapter using the actual artifacts.
"""

import pytest
from pathlib import Path
import os
import math

from app.schemas.inference import InferenceStatus
from app.services.inference import TinyGasNetAdapter

# Path to the actual artifacts copied to the Server directory
REAL_ARTIFACTS_DIR = Path(__file__).parent.parent / "artifacts"


@pytest.mark.asyncio
async def test_genuine_model_inference():
    """
    Test using the actual model weights (gasnet.pt) and scaler/encoder (preprocess.pkl).
    This validates that we are correctly parsing the artifacts without
    modifying their architecture.
    """
    if not (REAL_ARTIFACTS_DIR / "gasnet.pt").exists():
        pytest.skip("Real model artifacts not found. Skipping genuine inference test.")

    adapter = TinyGasNetAdapter(artifacts_dir=REAL_ARTIFACTS_DIR)
    adapter.load()

    # Model should successfully load and validate compatibility
    assert adapter._loaded is True

    # Use a known fixture (from assumedata.md / mq_infer.py defaults)
    # MQ2: 1.35V, MQ9: 1.64V, MQ135: 1.96V, Temp: 31.2C, Hum: 68.5%
    result = await adapter.predict(
        mq2_v=1.35,
        mq9_v=1.64,
        mq135_v=1.96,
        temperature_c=31.2,
        humidity_pct=68.5
    )

    # Validate genuine model outputs
    assert result.status == InferenceStatus.SUCCESS
    assert result.gas_class is not None
    assert isinstance(result.class_confidence, float)
    assert 0.0 <= result.class_confidence <= 1.0

    assert result.class_probabilities is not None
    assert isinstance(result.class_probabilities, dict)
    # Sum of probabilities should be close to 1.0
    prob_sum = sum(result.class_probabilities.values())
    assert math.isclose(prob_sum, 1.0, abs_tol=0.01)

    assert result.safety_status in ["safe", "unsafe"]
    assert isinstance(result.safety_confidence, float)
    assert 0.0 <= result.safety_confidence <= 1.0

    assert isinstance(result.uncertainty, float)
    assert 0.0 <= result.uncertainty <= 1.0
    assert result.inference_time_ms > 0
