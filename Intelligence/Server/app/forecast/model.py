"""
Lightweight autoregressive forecasting model.

Approach:
- Uses a simple AR(p) model fitted via least-squares on recent data.
- No external ML libraries required — pure Python + basic linear algebra.
- Predicts PM1.0, PM2.5, PM10 independently per channel.
- Falls back to persistence baseline when insufficient data.
- Computes trend direction from predicted slope.
- Reports MAE vs persistence baseline for reliability assessment.
"""

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from app.schemas.forecast import (
    ChannelPrediction,
    ForecastReliability,
    ForecastResponse,
    ForecastStatus,
    TrendDirection,
)

logger = logging.getLogger(__name__)


def _solve_least_squares(
    X: List[List[float]], y: List[float]
) -> Optional[List[float]]:
    """
    Solve X @ beta = y via normal equations: beta = (X^T X)^{-1} X^T y.
    Returns None if the system is singular.
    """
    n = len(X)
    p = len(X[0]) if n > 0 else 0
    if n == 0 or p == 0 or n < p:
        return None

    # X^T X
    XtX = [[0.0] * p for _ in range(p)]
    for i in range(p):
        for j in range(p):
            s = 0.0
            for k in range(n):
                s += X[k][i] * X[k][j]
            XtX[i][j] = s

    # X^T y
    Xty = [0.0] * p
    for i in range(p):
        s = 0.0
        for k in range(n):
            s += X[k][i] * y[k]
        Xty[i] = s

    # Gauss-Jordan elimination on augmented matrix [XtX | Xty]
    aug = [row[:] + [Xty[i]] for i, row in enumerate(XtX)]
    for col in range(p):
        # Partial pivoting
        max_row = col
        for row in range(col + 1, p):
            if abs(aug[row][col]) > abs(aug[max_row][col]):
                max_row = row
        aug[col], aug[max_row] = aug[max_row], aug[col]

        pivot = aug[col][col]
        if abs(pivot) < 1e-12:
            return None  # Singular

        for j in range(col, p + 1):
            aug[col][j] /= pivot

        for row in range(p):
            if row == col:
                continue
            factor = aug[row][col]
            for j in range(col, p + 1):
                aug[row][j] -= factor * aug[col][j]

    return [aug[i][p] for i in range(p)]


def _fit_ar(
    values: List[float], order: int
) -> Optional[Tuple[List[float], float]]:
    """
    Fit AR(order) model. Returns (coefficients, intercept) or None.
    coefficients[0] corresponds to lag 1 (most recent), etc.
    """
    if len(values) < order + 2:  # Need at least order+2 points
        return None

    # Build design matrix
    X: list[list[float]] = []
    y: list[float] = []
    for t in range(order, len(values)):
        row = [values[t - lag - 1] for lag in range(order)]
        row.append(1.0)  # intercept
        X.append(row)
        y.append(values[t])

    beta = _solve_least_squares(X, y)
    if beta is None:
        return None

    coefficients = beta[:-1]
    intercept = beta[-1]
    return coefficients, intercept


def _ar_predict(
    coefficients: List[float],
    intercept: float,
    recent: List[float],
    steps: int,
) -> List[float]:
    """
    Generate multi-step AR predictions.
    `recent` must be in chronological order (oldest first),
    with length >= len(coefficients).
    """
    order = len(coefficients)
    buffer = list(recent[-order:])  # last `order` values
    predictions: list[float] = []

    for _ in range(steps):
        pred = intercept
        for lag in range(order):
            pred += coefficients[lag] * buffer[-(lag + 1)]
        # Clamp to non-negative (PM values can't be negative)
        pred = max(0.0, pred)
        predictions.append(round(pred, 2))
        buffer.append(pred)

    return predictions


def _compute_trend(
    predictions: List[float], threshold: float
) -> TrendDirection:
    """Determine trend from first and last predicted values."""
    if len(predictions) < 2:
        return TrendDirection.UNKNOWN
    diff = predictions[-1] - predictions[0]
    if diff > threshold:
        return TrendDirection.RISING
    elif diff < -threshold:
        return TrendDirection.FALLING
    return TrendDirection.STABLE


def _mae(predicted: List[float], baseline: List[float]) -> float:
    """Mean Absolute Error between two lists."""
    n = min(len(predicted), len(baseline))
    if n == 0:
        return 0.0
    return round(sum(abs(predicted[i] - baseline[i]) for i in range(n)) / n, 4)


def _determine_reliability(
    history_points: int, min_points: int, ar_fitted: bool
) -> ForecastReliability:
    if history_points < min_points:
        return ForecastReliability.UNAVAILABLE
    if not ar_fitted:
        return ForecastReliability.LOW
    if history_points < min_points * 3:
        return ForecastReliability.MEDIUM
    return ForecastReliability.HIGH


def generate_forecast(
    records: List[dict],
    channels: List[str],
    node_id: str,
    horizon_minutes: int = 60,
    sampling_interval_minutes: int = 5,
    min_history_points: int = 12,
    max_ar_order: int = 6,
    trend_threshold: float = 0.5,
) -> ForecastResponse:
    """
    Produce forecasts for the given PM channels from stored records.

    Parameters
    ----------
    records : list[dict]
        Historical records in chronological order, each containing
        ``timestamp``, and optionally PM channel keys.
    channels : list[str]
        PM channel names to forecast (e.g. ["PM1_0", "PM2_5", "PM10"]).
    node_id : str
        The node identifier.
    horizon_minutes : int
        How far into the future to forecast.
    sampling_interval_minutes : int
        Expected interval between samples.
    min_history_points : int
        Minimum number of valid observations required.
    max_ar_order : int
        Maximum AR lag order to try.
    trend_threshold : float
        Threshold for trend classification.

    Returns
    -------
    ForecastResponse
    """
    now = datetime.now(timezone.utc)
    steps = max(1, horizon_minutes // sampling_interval_minutes)

    if not records:
        return ForecastResponse(
            node_id=node_id,
            status=ForecastStatus.INSUFFICIENT_DATA,
            reliability=ForecastReliability.UNAVAILABLE,
            generated_at=now,
            horizon_minutes=horizon_minutes,
            sampling_interval_minutes=sampling_interval_minutes,
            history_points_used=0,
            message="No historical data available for forecasting.",
        )

    # Extract per-channel time series
    channel_series: dict[str, list[float]] = {ch: [] for ch in channels}
    valid_channels: list[str] = []

    for rec in records:
        for ch in channels:
            val = rec.get(ch)
            if val is not None and isinstance(val, (int, float)) and math.isfinite(val):
                channel_series[ch].append(float(val))

    for ch in channels:
        if len(channel_series[ch]) >= min_history_points:
            valid_channels.append(ch)

    if not valid_channels:
        total_pts = max(len(v) for v in channel_series.values()) if channel_series else 0
        return ForecastResponse(
            node_id=node_id,
            status=ForecastStatus.INSUFFICIENT_DATA,
            reliability=ForecastReliability.UNAVAILABLE,
            generated_at=now,
            horizon_minutes=horizon_minutes,
            sampling_interval_minutes=sampling_interval_minutes,
            history_points_used=total_pts,
            message=(
                f"Insufficient data for forecasting. Need at least "
                f"{min_history_points} points per channel."
            ),
        )

    # Forecast each valid channel
    predictions: list[ChannelPrediction] = []
    any_ar_fitted = False
    total_history = max(len(channel_series[ch]) for ch in valid_channels)

    for ch in valid_channels:
        series = channel_series[ch]

        # Determine AR order (use min of max_ar_order and available data)
        order = min(max_ar_order, len(series) // 3, len(series) - 2)
        order = max(1, order)

        ar_result = _fit_ar(series, order)

        # Timestamps for predictions
        pred_timestamps = [
            now + timedelta(minutes=sampling_interval_minutes * (i + 1))
            for i in range(steps)
        ]

        # Persistence baseline: repeat last known value
        last_val = series[-1]
        persistence = [round(last_val, 2)] * steps

        if ar_result is not None:
            coefficients, intercept = ar_result
            predicted = _ar_predict(coefficients, intercept, series, steps)
            any_ar_fitted = True
            mae_val = _mae(predicted, persistence)
        else:
            # Fall back to persistence
            predicted = persistence[:]
            mae_val = 0.0

        trend = _compute_trend(predicted, trend_threshold)

        predictions.append(
            ChannelPrediction(
                channel=ch,
                predicted_values=predicted,
                predicted_timestamps=pred_timestamps,
                trend=trend,
                persistence_baseline=persistence,
                mae_vs_persistence=mae_val,
            )
        )

    reliability = _determine_reliability(
        total_history, min_history_points, any_ar_fitted
    )

    return ForecastResponse(
        node_id=node_id,
        status=ForecastStatus.OK,
        reliability=reliability,
        generated_at=now,
        horizon_minutes=horizon_minutes,
        sampling_interval_minutes=sampling_interval_minutes,
        history_points_used=total_history,
        channels=predictions,
        message=f"Forecast generated for {len(predictions)} channel(s).",
    )
