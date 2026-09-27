"""
NumPy-only TinyGasNet inference adapter.

Drop-in replacement for the PyTorch-based TinyGasNetAdapter.
Loads weights from gasnet_weights.npz and metadata from model_metadata.json,
both exported by Training/export_gasnet.py.

No PyTorch dependency required.
"""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from app.schemas.inference import InferenceResult, InferenceStatus
from app.services.inference import InferenceAdapter

logger = logging.getLogger(__name__)


class NumpyGasNetAdapter(InferenceAdapter):
    """
    Pure NumPy implementation of TinyGasNet MC-Dropout inference.

    Architecture (must match Training/mq_train.py):
        Input(5) → Linear(5,32) → ReLU → Dropout(0.1)
                 → Linear(32,16) → ReLU → Dropout(0.1)
                 → class_head(16, n_classes)    [softmax / T_cal]
                 → safety_head(16, 1)           [sigmoid]

    MC-Dropout: 20 forward passes with dropout active,
    averaging class probabilities and safety probability.
    """

    def __init__(
        self,
        artifacts_dir: Path,
        n_mc: int = 20,
        deterministic_seed: Optional[int] = None,
    ) -> None:
        self.artifacts_dir = Path(artifacts_dir)
        self.n_mc = n_mc
        self.deterministic_seed = deterministic_seed
        self._loaded: bool = False

        # Model parameters (populated by load())
        self._W1: Optional[np.ndarray] = None
        self._b1: Optional[np.ndarray] = None
        self._W2: Optional[np.ndarray] = None
        self._b2: Optional[np.ndarray] = None
        self._Wc: Optional[np.ndarray] = None
        self._bc: Optional[np.ndarray] = None
        self._Ws: Optional[np.ndarray] = None
        self._bs: Optional[np.ndarray] = None

        # Preprocessing
        self._scaler_mean: Optional[np.ndarray] = None
        self._scaler_scale: Optional[np.ndarray] = None
        self._class_labels: List[str] = []
        self._calibration_temp: float = 1.0
        self._p_drop: float = 0.1

    def load(self) -> None:
        """Load model weights and metadata from artifacts directory."""
        weights_path = self.artifacts_dir / "gasnet_weights.npz"
        metadata_path = self.artifacts_dir / "model_metadata.json"

        if not weights_path.exists():
            logger.warning(
                "NumPy weights not found at %s — "
                "run Training/export_gasnet.py to generate. "
                "Adapter will report NOT_CONFIGURED.",
                weights_path,
            )
            return

        if not metadata_path.exists():
            logger.warning(
                "Model metadata not found at %s — "
                "run Training/export_gasnet.py to generate. "
                "Adapter will report NOT_CONFIGURED.",
                metadata_path,
            )
            return

        try:
            # Load weights
            data = np.load(weights_path)
            self._W1 = data["fc1.weight"].astype(np.float32)
            self._b1 = data["fc1.bias"].astype(np.float32)
            self._W2 = data["fc2.weight"].astype(np.float32)
            self._b2 = data["fc2.bias"].astype(np.float32)
            self._Wc = data["class_head.weight"].astype(np.float32)
            self._bc = data["class_head.bias"].astype(np.float32)
            self._Ws = data["safety_head.weight"].astype(np.float32)
            self._bs = data["safety_head.bias"].astype(np.float32)

            # Load metadata
            with open(metadata_path) as f:
                meta = json.load(f)

            self._class_labels = meta["class_labels"]
            self._calibration_temp = float(meta["calibration_temperature"])
            self._p_drop = float(meta["architecture"].get("p_drop", 0.1))
            self._scaler_mean = np.array(
                meta["preprocessing"]["scaler_mean"], dtype=np.float32
            )
            self._scaler_scale = np.array(
                meta["preprocessing"]["scaler_scale"], dtype=np.float32
            )

            # Validate dimensions
            n_features = meta["architecture"]["n_features"]
            n_classes = meta["architecture"]["n_classes"]
            assert self._W1.shape == (32, n_features), f"W1 shape mismatch: {self._W1.shape}"
            assert self._W2.shape == (16, 32), f"W2 shape mismatch: {self._W2.shape}"
            assert self._Wc.shape == (n_classes, 16), f"Wc shape mismatch: {self._Wc.shape}"
            assert self._Ws.shape == (1, 16), f"Ws shape mismatch: {self._Ws.shape}"

            # Verify with a dummy forward pass (no dropout)
            dummy = np.zeros((1, n_features), dtype=np.float32)
            h1 = np.maximum(0, dummy @ self._W1.T + self._b1)
            h2 = np.maximum(0, h1 @ self._W2.T + self._b2)
            _ = h2 @ self._Wc.T + self._bc
            _ = h2 @ self._Ws.T + self._bs

            self._loaded = True
            logger.info(
                "NumpyGasNet loaded (%d classes, T_cal=%.4f, %d params). Verified.",
                n_classes,
                self._calibration_temp,
                sum(w.size for w in [self._W1, self._b1, self._W2, self._b2,
                                      self._Wc, self._bc, self._Ws, self._bs]),
            )

        except Exception as exc:
            logger.error("Failed to load NumPy model: %s", exc)
            self._loaded = False

    def _sync_predict(
        self,
        mq2_v: float,
        mq9_v: float,
        mq135_v: float,
        temperature_c: float,
        humidity_pct: float,
    ) -> InferenceResult:
        """Synchronous MC-Dropout inference using pure NumPy."""
        t0 = time.perf_counter()

        # Preprocessing: StandardScaler transform
        x_raw = np.array(
            [[mq2_v, mq9_v, mq135_v, temperature_c, humidity_pct]],
            dtype=np.float32,
        )
        x = (x_raw - self._scaler_mean) / self._scaler_scale

        # MC-Dropout: run n_mc forward passes with dropout active
        rng = np.random.RandomState(self.deterministic_seed)
        keep_prob = 1.0 - self._p_drop
        scale = 1.0 / keep_prob

        class_probs_runs = []
        safety_probs_runs = []

        for _ in range(self.n_mc):
            # Layer 1: Linear + ReLU + Dropout
            h1 = np.maximum(0, x @ self._W1.T + self._b1)
            mask1 = (rng.rand(*h1.shape) >= self._p_drop).astype(np.float32) * scale
            h1 = h1 * mask1

            # Layer 2: Linear + ReLU + Dropout
            h2 = np.maximum(0, h1 @ self._W2.T + self._b2)
            mask2 = (rng.rand(*h2.shape) >= self._p_drop).astype(np.float32) * scale
            h2 = h2 * mask2

            # Class head: logits → temperature-scaled softmax
            logits_c = h2 @ self._Wc.T + self._bc
            scaled_c = logits_c / self._calibration_temp
            exp_c = np.exp(scaled_c - np.max(scaled_c, axis=-1, keepdims=True))
            probs_c = exp_c / np.sum(exp_c, axis=-1, keepdims=True)

            # Safety head: logit → sigmoid
            logit_s = (h2 @ self._Ws.T + self._bs).squeeze(-1)
            prob_s = 1.0 / (1.0 + np.exp(-logit_s))

            class_probs_runs.append(probs_c[0])
            if np.ndim(prob_s) > 0:
                safety_probs_runs.append(float(prob_s[0]))
            else:
                safety_probs_runs.append(float(prob_s))

        # Aggregate MC runs
        class_probs = np.stack(class_probs_runs)       # (n_mc, n_classes)
        safety_probs = np.array(safety_probs_runs)     # (n_mc,)

        mean_class = class_probs.mean(axis=0)
        mean_safety = float(safety_probs.mean())

        # Predicted class
        class_idx = int(mean_class.argmax())
        class_name = str(self._class_labels[class_idx])
        class_conf = float(mean_class[class_idx])

        # Normalized predictive entropy [0, 1]
        eps = 1e-12
        entropy = -float(np.sum(mean_class * np.log(mean_class + eps)))
        max_entropy = float(np.log(len(self._class_labels)))
        uncertainty = entropy / max_entropy if max_entropy > 0 else 0.0

        # Safety status
        safety_status = "unsafe" if mean_safety > 0.5 else "safe"
        safety_conf = mean_safety if mean_safety > 0.5 else 1.0 - mean_safety

        # Per-class probabilities
        class_probabilities = {
            str(self._class_labels[i]): round(float(mean_class[i]), 4)
            for i in range(len(self._class_labels))
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
            logger.error("NumPy inference failed: %s", exc, exc_info=True)
            return InferenceResult.from_error(str(exc))
