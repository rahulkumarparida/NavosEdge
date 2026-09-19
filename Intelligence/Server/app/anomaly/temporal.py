"""
Temporal feature extraction for time-aware anomaly baseline.

Provides cyclical and linear time features that allow regression models
to capture diurnal (daily) and weekly patterns without requiring complex
time-series libraries.
"""

import math
from datetime import datetime, timezone
from typing import Dict


def extract_temporal_features(timestamp: datetime) -> Dict[str, float]:
    """
    Extract temporal features from a timestamp for regression.

    Returns:
        Dictionary containing:
        - hour_of_day:    float in [0, 24)
        - minute_of_day:  float in [0, 1440)
        - day_of_week:    int in [0, 6]  (Monday=0)
        - sin_hour:       sin(2π · hour / 24) — cyclical hour encoding
        - cos_hour:       cos(2π · hour / 24) — cyclical hour encoding
        - sin_dow:        sin(2π · dow / 7) — cyclical day-of-week encoding
        - cos_dow:        cos(2π · dow / 7) — cyclical day-of-week encoding
    """
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)

    hour = timestamp.hour + timestamp.minute / 60.0 + timestamp.second / 3600.0
    minute_of_day = timestamp.hour * 60.0 + timestamp.minute + timestamp.second / 60.0
    dow = timestamp.weekday()  # Monday = 0

    return {
        "hour_of_day": hour,
        "minute_of_day": minute_of_day,
        "day_of_week": float(dow),
        "sin_hour": math.sin(2.0 * math.pi * hour / 24.0),
        "cos_hour": math.cos(2.0 * math.pi * hour / 24.0),
        "sin_dow": math.sin(2.0 * math.pi * dow / 7.0),
        "cos_dow": math.cos(2.0 * math.pi * dow / 7.0),
    }
