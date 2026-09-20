"""
Scoring engine for source classification.

Combines two complementary signals:
  1. Decision Tree class probabilities (when a trained model is available).
  2. Feature-range similarity scores (computed from per-class reference statistics).

The final `match_score` is a weighted combination.  It is NOT a calibrated
probability — it is a normalized pattern-matching score in [0, 1].

The `confidence` field is populated ONLY when the Decision Tree provides
genuine class probabilities (sklearn predict_proba); otherwise it is None.
"""

import json
import logging
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.source_classifier.categories import (
    ALL_SOURCE_CLASSIFIER_FEATURES,
    SourceCategory,
    SourceClassifierConfig,
)

logger = logging.getLogger(__name__)


class ReferenceStats:
    """
    Per-class feature distributions loaded from a JSON artifact.

    Structure:
    {
      "CLEAN_OR_BACKGROUND": {
        "mq2_v": {"median": 1.2, "mad": 0.3, "q25": 0.9, "q75": 1.5, "min": 0.1, "max": 2.5, "count": 200},
        ...
      },
      ...
    }
    """

    def __init__(self) -> None:
        self.stats: Dict[str, Dict[str, Dict[str, float]]] = {}
        self._loaded = False

    def load(self, path: Path) -> bool:
        try:
            with open(path) as f:
                self.stats = json.load(f)
            self._loaded = bool(self.stats)
            logger.info(
                "Loaded reference stats for %d source categories from %s",
                len(self.stats),
                path,
            )
            return self._loaded
        except Exception as e:
            logger.error("Failed to load reference stats from %s: %s", path, e)
            return False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def categories(self) -> List[str]:
        return list(self.stats.keys())


def compute_feature_similarity(
    features: Dict[str, Optional[float]],
    category_stats: Dict[str, Dict[str, float]],
    config: SourceClassifierConfig,
) -> Tuple[float, List[str], List[str]]:
    """
    Compute a graded similarity score between observed features and
    a single source category's reference distribution.

    For each feature:
      - If the observed value falls within the learned [q25, q75] range
        (expanded by ±tolerance), similarity is high (close to 1.0).
      - As the value moves beyond the range, similarity decays smoothly
        using a Gaussian-like falloff based on the MAD.

    Returns:
        (similarity_score, supporting_features, limitations)
    """
    scores: List[float] = []
    supporting: List[str] = []
    limitations: List[str] = []
    available_count = 0

    feature_labels = {
        "mq2_v": "MQ2 sensor response",
        "mq9_v": "MQ9 sensor response",
        "mq135_v": "MQ135 sensor response",
        "temp_c": "Temperature pattern",
        "hum_pct": "Humidity pattern",
        "pm1_0": "PM1.0 pattern",
        "pm2_5": "PM2.5 pattern",
        "pm10": "PM10 pattern",
        "pm_coarse_ratio": "PM coarse/fine ratio",
        "pm_fine_ratio": "PM fine particle ratio",
        "mq_mean_v": "Mean MQ sensor response",
        "mq_max_v": "Max MQ sensor response",
        "mq2_mq9_ratio": "MQ2/MQ9 ratio",
        "mq135_mq2_ratio": "MQ135/MQ2 ratio",
    }

    for feat_name in ALL_SOURCE_CLASSIFIER_FEATURES:
        observed = features.get(feat_name)
        ref = category_stats.get(feat_name)

        if observed is None or ref is None:
            continue

        available_count += 1

        median = ref.get("median", 0.0)
        mad = ref.get("mad", 1.0)
        q25 = ref.get("q25", median - mad)
        q75 = ref.get("q75", median + mad)

        # Compute tolerance-expanded range
        range_span = q75 - q25
        if range_span < config.near_zero_threshold:
            # Near-zero range: use absolute tolerance
            tol = config.near_zero_absolute_tolerance
        else:
            tol = range_span * config.tolerance_fraction

        expanded_low = q25 - tol
        expanded_high = q75 + tol

        # Compute similarity score
        if expanded_low <= observed <= expanded_high:
            # Inside expanded IQR — high similarity
            # Score 0.8 to 1.0 depending on distance from median
            dist_from_median = abs(observed - median)
            half_range = max((expanded_high - expanded_low) / 2, 0.01)
            sim = 1.0 - 0.2 * (dist_from_median / half_range)
            sim = max(sim, 0.8)
        else:
            # Outside expanded IQR — Gaussian-like decay
            if observed < expanded_low:
                distance = expanded_low - observed
            else:
                distance = observed - expanded_high

            # Use MAD as the decay scale (minimum floor to avoid division by zero)
            scale = max(mad, 0.1)
            # Gaussian falloff: exp(-0.5 * (distance/scale)^2)
            sim = math.exp(-0.5 * (distance / scale) ** 2)

        scores.append(sim)

        # Track supporting features (similarity > 0.7)
        label = feature_labels.get(feat_name, feat_name)
        if sim > 0.7:
            supporting.append(label)

    if not scores:
        return 0.0, [], ["No features available for comparison"]

    # Weighted mean — give slightly more weight to PM and MQ features
    # which are more discriminative for source identification
    similarity = sum(scores) / len(scores)

    if available_count < len(ALL_SOURCE_CLASSIFIER_FEATURES) * 0.5:
        limitations.append("Limited features available for matching")

    return similarity, supporting, limitations


def compute_combined_scores(
    features: Dict[str, Optional[float]],
    dt_probabilities: Optional[Dict[str, float]],
    reference_stats: ReferenceStats,
    config: SourceClassifierConfig,
) -> List[Dict[str, Any]]:
    """
    Compute combined match scores for all source categories.

    Scoring formula:
        match_score = (dt_weight × dt_probability) + (sim_weight × similarity)

    If the Decision Tree is not available, match_score = similarity only.

    Returns:
        List of prediction dicts sorted by descending match_score.
    """
    predictions: List[Dict[str, Any]] = []

    # Get all categories from reference stats or DT probabilities
    categories: set = set()
    if reference_stats.is_loaded:
        categories.update(reference_stats.categories)
    if dt_probabilities:
        categories.update(dt_probabilities.keys())

    # Always ensure UNKNOWN is considered
    categories.add(SourceCategory.UNKNOWN.value)

    for cat_name in categories:
        if cat_name == SourceCategory.UNKNOWN.value:
            continue  # UNKNOWN is handled separately

        # Decision Tree probability
        dt_prob = dt_probabilities.get(cat_name, 0.0) if dt_probabilities else None

        # Feature similarity
        cat_stats = reference_stats.stats.get(cat_name, {}) if reference_stats.is_loaded else {}
        if cat_stats:
            similarity, supporting, limitations = compute_feature_similarity(
                features, cat_stats, config
            )
        else:
            similarity = 0.0
            supporting = []
            limitations = ["No reference statistics available"]

        # Combined match_score
        if dt_prob is not None and reference_stats.is_loaded:
            match_score = (
                config.dt_probability_weight * dt_prob
                + config.similarity_weight * similarity
            )
        elif dt_prob is not None:
            match_score = dt_prob
        else:
            match_score = similarity

        # Confidence is ONLY set from DT probabilities — never from similarity
        confidence = round(dt_prob, 4) if dt_prob is not None else None

        try:
            source_enum = SourceCategory(cat_name)
        except ValueError:
            source_enum = SourceCategory.UNKNOWN

        predictions.append(
            {
                "source": source_enum.value,
                "match_score": round(match_score, 4),
                "confidence": confidence,
                "supporting_features": supporting,
                "limitations": limitations,
            }
        )

    # Sort by match_score descending
    predictions.sort(key=lambda x: x["match_score"], reverse=True)

    return predictions


def detect_mixed_pollution(
    predictions: List[Dict[str, Any]],
    config: SourceClassifierConfig,
) -> bool:
    """
    Check if the pattern suggests multiple overlapping sources.

    Returns True if >= mixed_pollution_min_sources categories all have
    scores above mixed_pollution_threshold.
    """
    high_scoring = [
        p
        for p in predictions
        if p["source"] not in (SourceCategory.UNKNOWN.value, SourceCategory.MIXED_POLLUTION.value)
        and p["match_score"] >= config.mixed_pollution_threshold
    ]
    return len(high_scoring) >= config.mixed_pollution_min_sources


def assess_uncertainty(
    predictions: List[Dict[str, Any]],
    config: SourceClassifierConfig,
    data_quality_status: str,
) -> Dict[str, Any]:
    """
    Assess whether the classification result is uncertain.

    Uncertainty arises from:
      - Low top match score
      - Small gap between top two candidates
      - Degraded data quality
      - Mixed pollution
    """
    reasons: List[str] = []

    non_unknown = [p for p in predictions if p["source"] != SourceCategory.UNKNOWN.value]

    if not non_unknown:
        return {"is_uncertain": True, "reason": "No candidate sources available"}

    top_score = non_unknown[0]["match_score"]

    if top_score < config.uncertainty_score_threshold:
        reasons.append("Low overall match score")

    if len(non_unknown) >= 2:
        gap = non_unknown[0]["match_score"] - non_unknown[1]["match_score"]
        if gap < config.uncertainty_gap_threshold:
            reasons.append("Overlapping source patterns")

    if data_quality_status in ("degraded", "invalid"):
        reasons.append(f"Data quality is {data_quality_status}")

    if detect_mixed_pollution(predictions, config):
        reasons.append("Multiple sources may be contributing")

    return {
        "is_uncertain": len(reasons) > 0,
        "reason": "; ".join(reasons) if reasons else None,
    }
