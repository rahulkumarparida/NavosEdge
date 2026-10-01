"""
TinyGasNet inference adapter (PyTorch-Free / Pure NumPy).

Wraps the trained MQ-sensor classifier behind a clean async interface.
When model artifacts are not present the adapter returns NOT_CONFIGURED
instead of failing. Uses pure NumPy for zero-dependency edge execution.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from app.schemas.inference import InferenceResult

logger = logging.getLogger(__name__)


class InferenceAdapter(ABC):
    """Abstract interface for classifier adapters."""

    @abstractmethod
    async def predict(
        self,
        mq2_v: float,
        mq9_v: float,
        mq135_v: float,
        temperature_c: float,
        humidity_pct: float,
    ) -> InferenceResult:
        ...


class TinyGasNetAdapter(InferenceAdapter):
    """
    Pure NumPy implementation of TinyGasNet MC-Dropout inference.
    100% PyTorch-Free.
    """

    def __init__(self, artifacts_dir: Path, n_mc: int = 20) -> None:
        self.artifacts_dir = artifacts_dir
        self.n_mc = n_mc
        self._numpy_adapter = None

    def load(self) -> None:
        from app.services.numpy_inference import NumpyGasNetAdapter
        self._numpy_adapter = NumpyGasNetAdapter(artifacts_dir=self.artifacts_dir, n_mc=self.n_mc)
        self._numpy_adapter.load()

    @property
    def _loaded(self) -> bool:
        return self._numpy_adapter._loaded if self._numpy_adapter else False

    async def predict(
        self,
        mq2_v: float,
        mq9_v: float,
        mq135_v: float,
        temperature_c: float,
        humidity_pct: float,
    ) -> InferenceResult:
        if self._numpy_adapter is None:
            self.load()
        return await self._numpy_adapter.predict(
            mq2_v=mq2_v,
            mq9_v=mq9_v,
            mq135_v=mq135_v,
            temperature_c=temperature_c,
            humidity_pct=humidity_pct,
        )
