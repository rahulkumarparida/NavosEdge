"""
Residual analysis and anomaly scoring.

Computes per-feature residuals (actual − predicted) and normalises them
using robust statistics (median absolute deviation) rather than mean/std
to resist outlier contamination.
"""

import logging
import math
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore[assignment]

from app.anomaly.baseline import BaselineEstimator

# MAD-to-sigma consistency constant for normal distributions
MAD_SCALE = 1.4826


class ResidualTracker:
    """
    Tracks residuals for each feature and computes normalised anomaly scores.

    For each feature the tracker maintains a bounded history of residuals
    and computes robust spread estimates (median, MAD).
    """

    def __init__(self, max_residual_history: int = 500):
        self.max_residual_history = max_residual_history
        # {feature: list of recent residuals}
        self._residuals: Dict[str, List[float]] = {}

    def record_residual(self, feature_name: str, residual: float) -> None:
        """Append a residual and trim to bounded size."""
        if feature_name not in self._residuals:
            self._residuals[feature_name] = []
        self._residuals[feature_name].append(residual)
        if len(self._residuals[feature_name]) > self.max_residual_history:
            self._residuals[feature_name] = self._residuals[feature_name][
                -self.max_residual_history :
            ]

    def compute_score(
        self,
        feature_name: str,
        residual: float,
        min_floor: float = 1.0,
    ) -> float:
        """
        Compute the normalised anomaly score for a single feature.

            score = |residual| / (MAD_SCALE * MAD)

        Protected against division by zero via *min_floor*.
        """
        history = self._residuals.get(feature_name, [])
        if len(history) < 3:
            # Not enough history — return raw ratio against floor
            if min_floor <= 0:
                min_floor = 1.0
            return abs(residual) / min_floor

        if np is not None:
            arr = np.array(history, dtype=np.float64)
            med = float(np.median(arr))
            mad = float(np.median(np.abs(arr - med)))
        else:
            sorted_h = sorted(history)
            n = len(sorted_h)
            med = sorted_h[n // 2] if n % 2 else (sorted_h[n // 2 - 1] + sorted_h[n // 2]) / 2.0
            abs_devs = sorted([abs(v - med) for v in history])
            mad = abs_devs[n // 2] if n % 2 else (abs_devs[n // 2 - 1] + abs_devs[n // 2]) / 2.0

        spread = max(MAD_SCALE * mad, min_floor)
        return abs(residual) / spread

    def residual_count(self, feature_name: str) -> int:
        return len(self._residuals.get(feature_name, []))

    def get_median(self, feature_name: str) -> Optional[float]:
        history = self._residuals.get(feature_name, [])
        if not history:
            return None
        if np is not None:
            return float(np.median(history))
        sorted_h = sorted(history)
        n = len(sorted_h)
        return sorted_h[n // 2] if n % 2 else (sorted_h[n // 2 - 1] + sorted_h[n // 2]) / 2.0

    def get_mad(self, feature_name: str) -> Optional[float]:
        history = self._residuals.get(feature_name, [])
        if len(history) < 2:
            return None
        if np is not None:
            arr = np.array(history, dtype=np.float64)
            return float(np.median(np.abs(arr - np.median(arr))))
        sorted_h = sorted(history)
        n = len(sorted_h)
        med = sorted_h[n // 2] if n % 2 else (sorted_h[n // 2 - 1] + sorted_h[n // 2]) / 2.0
        abs_devs = sorted([abs(v - med) for v in history])
        return abs_devs[n // 2] if n % 2 else (abs_devs[n // 2 - 1] + abs_devs[n // 2]) / 2.0

    def load_from_history(
        self,
        feature_name: str,
        predicted_values: List[float],
        actual_values: List[float],
    ) -> None:
        """
        Bulk-load residual history from paired predictions and actuals.
        """
        residuals = [a - p for a, p in zip(actual_values, predicted_values)]
        # Keep only the most recent
        if len(residuals) > self.max_residual_history:
            residuals = residuals[-self.max_residual_history :]
        self._residuals[feature_name] = residuals
