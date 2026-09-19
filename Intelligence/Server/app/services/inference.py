"""
TinyGasNet inference adapter.

Wraps the trained MQ-sensor classifier behind a clean async interface.
When model artifacts are not present the adapter returns NOT_CONFIGURED
instead of failing.
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from app.schemas.inference import InferenceResult, InferenceStatus

logger = logging.getLogger(__name__)

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    import numpy as np
    import joblib
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


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


# ---------------------------------------------------------------------------
# Model definition — must mirror Training/mq_train.py exactly
# ---------------------------------------------------------------------------
if TORCH_AVAILABLE:
    class TinyGasNet(nn.Module):
        def __init__(
            self,
            n_features: int = 5,
            n_classes: int = 8,
            hidden1: int = 32,
            hidden2: int = 16,
            p_drop: float = 0.1,
        ):
            super().__init__()
            self.fc1 = nn.Linear(n_features, hidden1)
            self.fc2 = nn.Linear(hidden1, hidden2)
            self.drop = nn.Dropout(p_drop)
            self.class_head = nn.Linear(hidden2, n_classes)
            self.safety_head = nn.Linear(hidden2, 1)

        def forward(self, x: torch.Tensor):
            h = F.relu(self.fc1(x))
            h = self.drop(h)
            h = F.relu(self.fc2(h))
            h = self.drop(h)
            return self.class_head(h), self.safety_head(h).squeeze(-1)


class TinyGasNetAdapter(InferenceAdapter):
    """Loads TinyGasNet artifacts and runs MC-Dropout inference."""

    def __init__(self, artifacts_dir: Path) -> None:
        self.artifacts_dir = artifacts_dir
        self._loaded: bool = False
        self._model: Any = None
        self._scaler: Any = None
        self._label_encoder: Any = None
        self._calibration_temp: float = 1.0

    def load(self) -> None:
        if not TORCH_AVAILABLE:
            logger.warning(
                "PyTorch / numpy / joblib not installed — "
                "inference adapter will report NOT_CONFIGURED."
            )
            return

        weights_path = self.artifacts_dir / "gasnet.pt"
        preprocess_path = self.artifacts_dir / "preprocess.pkl"

        if not weights_path.exists() or not preprocess_path.exists():
            logger.warning(
                "Model artifacts not found at %s — "
                "inference adapter will report NOT_CONFIGURED.",
                self.artifacts_dir,
            )
            return

        try:
            bundle = joblib.load(preprocess_path)
            self._scaler = bundle["scaler"]
            self._label_encoder = bundle["label_encoder"]
            self._calibration_temp = float(bundle.get("temperature", 1.0))

            n_classes = len(self._label_encoder.classes_)
            self._model = TinyGasNet(n_features=5, n_classes=n_classes)
            state_dict = torch.load(
                weights_path, map_location=torch.device("cpu"), weights_only=True
            )
            self._model.load_state_dict(state_dict)
            self._model.eval()

            # Validate compatibility with a dummy pass
            dummy_x = torch.zeros(1, 5, dtype=torch.float32)
            with torch.no_grad():
                self._model(dummy_x)

            self._loaded = True
            logger.info(
                "TinyGasNet loaded (%d classes, T_cal=%.4f). Compatibility verified.",
                n_classes,
                self._calibration_temp,
            )
        except Exception as exc:
            logger.error("Failed to load TinyGasNet artifacts or incompatible: %s", exc)
            self._loaded = False

    # ------------------------------------------------------------------
    # Synchronous prediction (runs in thread-pool executor)
    # ------------------------------------------------------------------
    def _sync_predict(
        self,
        mq2_v: float,
        mq9_v: float,
        mq135_v: float,
        temperature_c: float,
        humidity_pct: float,
    ) -> InferenceResult:
        t0 = time.perf_counter()

        x = np.array(
            [[mq2_v, mq9_v, mq135_v, temperature_c, humidity_pct]],
            dtype=np.float32,
        )
        x = self._scaler.transform(x).astype(np.float32)
        x_t = torch.tensor(x)

        # MC-Dropout: keep dropout active via train()
        self._model.train()
        n_mc = 20
        class_probs_runs: list = []
        safety_probs_runs: list = []

        with torch.no_grad():
            for _ in range(n_mc):
                logits_c, logit_s = self._model(x_t)
                class_probs_runs.append(
                    F.softmax(logits_c / self._calibration_temp, dim=1).numpy()
                )
                safety_probs_runs.append(torch.sigmoid(logit_s).numpy())

        class_probs = np.stack(class_probs_runs)[:, 0, :]  # (n_mc, n_classes)
        safety_probs = np.stack(safety_probs_runs)[:, 0]   # (n_mc,)

        mean_class = class_probs.mean(axis=0)
        mean_safety = float(safety_probs.mean())

        class_idx = int(mean_class.argmax())
        class_name = str(self._label_encoder.classes_[class_idx])
        class_conf = float(mean_class[class_idx])

        # Normalised predictive entropy  [0, 1]
        eps = 1e-12
        entropy = -float(np.sum(mean_class * np.log(mean_class + eps)))
        max_entropy = float(np.log(len(self._label_encoder.classes_)))
        uncertainty = entropy / max_entropy if max_entropy > 0 else 0.0

        safety_status = "unsafe" if mean_safety > 0.5 else "safe"
        safety_conf = mean_safety if mean_safety > 0.5 else 1.0 - mean_safety

        class_probabilities = {
            str(self._label_encoder.classes_[i]): round(float(mean_class[i]), 4)
            for i in range(len(self._label_encoder.classes_))
        }

        inference_time_ms = (time.perf_counter() - t0) * 1000.0

        return InferenceResult(
            status=InferenceStatus.SUCCESS,
            gas_class=class_name,
            class_confidence=round(class_conf, 4),
            class_probabilities=class_probabilities,
            safety_status=safety_status,
            safety_confidence=round(float(safety_conf), 4),
            uncertainty=round(uncertainty, 4),
            inference_time_ms=round(inference_time_ms, 2),
        )

    # ------------------------------------------------------------------
    async def predict(
        self,
        mq2_v: float,
        mq9_v: float,
        mq135_v: float,
        temperature_c: float,
        humidity_pct: float,
    ) -> InferenceResult:
        if not self._loaded:
            return InferenceResult.not_configured()

        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(
                None,
                self._sync_predict,
                mq2_v,
                mq9_v,
                mq135_v,
                temperature_c,
                humidity_pct,
            )
        except Exception as exc:
            logger.error("Inference failed: %s", exc, exc_info=True)
            return InferenceResult.from_error(str(exc))
