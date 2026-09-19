"""
Time-aware baseline estimator for anomaly detection.

Implements a three-level hierarchy:
  Level 1  (BOOTSTRAPPING/CALIBRATING):
      Rolling median + exponentially-weighted mean when insufficient data.
  Level 2  (LEARNING/MONITORING):
      OLS regression:  y = β₀ + β₁·sin(2πh/24) + β₂·cos(2πh/24)
      capturing the diurnal cycle with only 3 coefficients.
  Level 3  (MONITORING with trend):
      Level-2 prediction + recent linear trend correction.

All computation uses numpy for speed; no pandas or sklearn required.
"""

import logging
import math
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore[assignment]

from app.anomaly.temporal import extract_temporal_features


# --------------------------------------------------------------------------
# Minimum deviation floors per feature category to avoid infinite sensitivity
# --------------------------------------------------------------------------
_MIN_DEVIATION_FLOORS: Dict[str, float] = {
    "temperature_C": 0.5,
    "humidity_pct": 2.0,
    "PM1_0": 3.0,
    "PM2_5": 3.0,
    "PM10": 5.0,
    "MQ2_raw_adc": 5.0,
    "MQ2_voltage_V": 0.05,
    "MQ9_raw_adc": 5.0,
    "MQ9_voltage_V": 0.05,
    "MQ135_raw_adc": 5.0,
    "MQ135_voltage_V": 0.05,
}

DEFAULT_MIN_FLOOR = 1.0


class BaselineEstimator:
    """
    Per-feature baseline estimator with three auto-levelling tiers.

    Parameters
    ----------
    min_samples_regression : int
        Minimum observations required to fit an OLS regression (Level 2).
    min_samples_monitoring : int
        Minimum observations to produce any estimate (Level 1).
    ema_alpha : float
        Smoothing factor for the exponentially-weighted mean in Level 1.
    trend_window : int
        Number of most-recent observations to estimate short-term trend.
    """

    def __init__(
        self,
        min_samples_regression: int = 30,
        min_samples_monitoring: int = 10,
        ema_alpha: float = 0.1,
        trend_window: int = 10,
    ):
        self.min_samples_regression = min_samples_regression
        self.min_samples_monitoring = min_samples_monitoring
        self.ema_alpha = ema_alpha
        self.trend_window = trend_window

        # Learned coefficients per feature:  {feature: (β₀, β₁, β₂)}
        self._coefficients: Dict[str, Tuple[float, float, float]] = {}
        # EMA state per feature
        self._ema: Dict[str, float] = {}
        self._ema_count: Dict[str, int] = {}

    # ------------------------------------------------------------------
    # Fit
    # ------------------------------------------------------------------

    def fit(
        self,
        feature_name: str,
        timestamps: List[datetime],
        values: List[float],
    ) -> bool:
        """
        Fit the baseline model for *feature_name* from historical data.

        Returns True if a regression was fitted (Level 2+), False if only
        Level 1 statistics were updated.
        """
        if np is None:
            logger.warning("numpy not available — baseline limited to EMA")
            self._update_ema(feature_name, values)
            return False

        n = len(values)
        if n == 0:
            return False

        # Always update the EMA
        self._update_ema(feature_name, values)

        if n < self.min_samples_regression:
            return False

        # Build design matrix  X = [1,  sin(2πh/24),  cos(2πh/24)]
        X = np.empty((n, 3), dtype=np.float64)
        y = np.array(values, dtype=np.float64)

        for i, ts in enumerate(timestamps):
            feats = extract_temporal_features(ts)
            X[i, 0] = 1.0
            X[i, 1] = feats["sin_hour"]
            X[i, 2] = feats["cos_hour"]

        # OLS via normal equations:  β = (XᵀX)⁻¹ Xᵀy
        try:
            XtX = X.T @ X
            Xty = X.T @ y
            beta = np.linalg.solve(XtX, Xty)
            self._coefficients[feature_name] = (
                float(beta[0]),
                float(beta[1]),
                float(beta[2]),
            )
            return True
        except np.linalg.LinAlgError:
            logger.warning(
                "Singular matrix when fitting baseline for %s — falling back to EMA",
                feature_name,
            )
            return False

    # ------------------------------------------------------------------
    # Predict
    # ------------------------------------------------------------------

    def predict(
        self,
        feature_name: str,
        timestamp: datetime,
        recent_values: Optional[List[float]] = None,
        recent_timestamps: Optional[List[datetime]] = None,
    ) -> Optional[float]:
        """
        Predict the expected value for *feature_name* at *timestamp*.

        Uses the highest available level:
          - Level 3 if regression coefficients exist AND recent data for trend
          - Level 2 if regression coefficients exist
          - Level 1 (EMA) if only EMA state exists
          - None if no data has been seen
        """
        base = None

        # Level 2/3: regression
        if feature_name in self._coefficients:
            feats = extract_temporal_features(timestamp)
            b0, b1, b2 = self._coefficients[feature_name]
            base = b0 + b1 * feats["sin_hour"] + b2 * feats["cos_hour"]

            # Level 3: trend correction
            if (
                recent_values is not None
                and recent_timestamps is not None
                and len(recent_values) >= 3
            ):
                trend = self._estimate_trend(recent_values, recent_timestamps)
                if trend is not None:
                    # Project trend forward from the midpoint of the recent window
                    mid_ts = recent_timestamps[len(recent_timestamps) // 2]
                    dt_hours = (timestamp - mid_ts).total_seconds() / 3600.0
                    base += trend * dt_hours

        # Level 1: EMA fallback
        if base is None and feature_name in self._ema:
            base = self._ema[feature_name]

        return base

    def has_regression(self, feature_name: str) -> bool:
        return feature_name in self._coefficients

    def has_any_estimate(self, feature_name: str) -> bool:
        return feature_name in self._ema or feature_name in self._coefficients

    def get_level(self, feature_name: str) -> int:
        """Return the highest available baseline level for this feature."""
        if feature_name in self._coefficients:
            return 2  # or 3 if trend available, but that's runtime
        if feature_name in self._ema:
            return 1
        return 0

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _update_ema(self, feature_name: str, values: List[float]) -> None:
        """Update exponentially-weighted mean from a batch of values."""
        if not values:
            return
        if feature_name not in self._ema:
            self._ema[feature_name] = values[0]
            self._ema_count[feature_name] = 1
            start = 1
        else:
            start = 0

        alpha = self.ema_alpha
        ema = self._ema[feature_name]
        for v in values[start:]:
            ema = alpha * v + (1 - alpha) * ema
        self._ema[feature_name] = ema
        self._ema_count[feature_name] = self._ema_count.get(feature_name, 0) + len(
            values
        )

    def _estimate_trend(
        self, values: List[float], timestamps: List[datetime]
    ) -> Optional[float]:
        """
        Estimate the recent linear trend (units per hour) from the
        last *trend_window* observations using simple linear regression.

        Returns slope in units/hour, or None if insufficient data.
        """
        n = min(len(values), self.trend_window)
        if n < 3:
            return None

        vals = values[-n:]
        tss = timestamps[-n:]

        # Convert timestamps to hours relative to the first
        t0 = tss[0]
        hours = [(ts - t0).total_seconds() / 3600.0 for ts in tss]

        if np is None:
            return None

        x = np.array(hours, dtype=np.float64)
        y = np.array(vals, dtype=np.float64)

        x_mean = x.mean()
        y_mean = y.mean()
        denom = float(np.sum((x - x_mean) ** 2))
        if denom < 1e-12:
            return None
        slope = float(np.sum((x - x_mean) * (y - y_mean))) / denom
        return slope

    @staticmethod
    def get_min_deviation_floor(feature_name: str) -> float:
        """Return the minimum deviation floor for a feature."""
        return _MIN_DEVIATION_FLOORS.get(feature_name, DEFAULT_MIN_FLOOR)
