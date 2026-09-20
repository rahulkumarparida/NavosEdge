"""
Feature extraction for source classification.

Reuses the existing SensorPayload schema and extracts the flat feature
dictionary needed by the source classifier.  Also computes derived ratio
features and handles missing/invalid values.
"""

import logging
import math
from typing import Dict, List, Optional, Tuple

from app.schemas.sensor import SensorPayload
from app.source_classifier.categories import (
    SOURCE_CLASSIFIER_FEATURES,
    SOURCE_CLASSIFIER_DERIVED_FEATURES,
    ALL_SOURCE_CLASSIFIER_FEATURES,
)

logger = logging.getLogger(__name__)


def extract_source_features(
    payload: SensorPayload,
) -> Tuple[Dict[str, Optional[float]], List[str]]:
    """
    Extract raw and derived features from a SensorPayload.

    Returns:
        (features_dict, missing_features_list)
        Missing features have value None in the dict and are listed by name.
    """
    features: Dict[str, Optional[float]] = {}
    missing: List[str] = []

    # --- Raw features ---
    # Gas sensors (always present in SensorPayload — it's required)
    features["mq2_v"] = payload.gas_sensors.MQ2.voltage_V
    features["mq9_v"] = payload.gas_sensors.MQ9.voltage_V
    features["mq135_v"] = payload.gas_sensors.MQ135.voltage_V

    # Environment (always present — required)
    features["temp_c"] = payload.environment.temperature_C
    features["hum_pct"] = payload.environment.humidity_pct

    # Particulate matter (always present — required)
    features["pm1_0"] = payload.particulate_matter.PM1_0
    features["pm2_5"] = payload.particulate_matter.PM2_5
    features["pm10"] = payload.particulate_matter.PM10

    # Check for near-zero voltage that may indicate disconnected sensor
    for key in ("mq2_v", "mq9_v", "mq135_v"):
        v = features[key]
        if v is not None and v <= 0.01:
            # Sensor likely railed to GND — mark as unreliable but keep the value
            logger.debug("Sensor %s voltage near zero (%.4f), may be disconnected", key, v)

    # --- Derived features ---
    features.update(_compute_derived(features))

    # Identify missing features (should be rare with current schema, but future-proof)
    for name in ALL_SOURCE_CLASSIFIER_FEATURES:
        if features.get(name) is None:
            missing.append(name)

    return features, missing


def _compute_derived(features: Dict[str, Optional[float]]) -> Dict[str, Optional[float]]:
    """Compute derived ratio features from raw features."""
    derived: Dict[str, Optional[float]] = {}

    pm10 = features.get("pm10")
    pm25 = features.get("pm2_5")
    pm1 = features.get("pm1_0")
    mq2 = features.get("mq2_v")
    mq9 = features.get("mq9_v")
    mq135 = features.get("mq135_v")

    # PM coarse ratio: PM10 / PM2.5
    # High ratio → more coarse particles → dust/construction
    # Low ratio → fine particle enrichment → combustion
    if pm10 is not None and pm25 is not None and pm25 > 0.1:
        derived["pm_coarse_ratio"] = pm10 / pm25
    else:
        derived["pm_coarse_ratio"] = None

    # PM fine ratio: PM2.5 / PM1.0
    if pm25 is not None and pm1 is not None and pm1 > 0.1:
        derived["pm_fine_ratio"] = pm25 / pm1
    else:
        derived["pm_fine_ratio"] = None

    # MQ aggregate features
    mq_vals = [v for v in (mq2, mq9, mq135) if v is not None]
    if mq_vals:
        derived["mq_mean_v"] = sum(mq_vals) / len(mq_vals)
        derived["mq_max_v"] = max(mq_vals)
    else:
        derived["mq_mean_v"] = None
        derived["mq_max_v"] = None

    # MQ2 / MQ9 ratio — discriminates smoke-dominant vs CO-dominant
    if mq2 is not None and mq9 is not None and mq9 > 0.01:
        derived["mq2_mq9_ratio"] = mq2 / mq9
    else:
        derived["mq2_mq9_ratio"] = None

    # MQ135 / MQ2 ratio — air quality gases vs smoke
    if mq135 is not None and mq2 is not None and mq2 > 0.01:
        derived["mq135_mq2_ratio"] = mq135 / mq2
    else:
        derived["mq135_mq2_ratio"] = None

    return derived


def features_to_model_array(
    features: Dict[str, Optional[float]],
    feature_names: Optional[List[str]] = None,
    fill_value: float = 0.0,
) -> List[float]:
    """
    Convert feature dict to ordered list for model input.

    Missing values are replaced with fill_value (default 0.0).
    Returns a plain list (not numpy) to avoid hard numpy dependency.
    """
    if feature_names is None:
        feature_names = ALL_SOURCE_CLASSIFIER_FEATURES

    values = []
    for name in feature_names:
        val = features.get(name)
        if val is None or (isinstance(val, float) and math.isnan(val)):
            values.append(fill_value)
        else:
            values.append(float(val))
    return values
