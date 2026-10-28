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


# Physical source archetypes for mixture and ambiguity analysis (Phase 2B)
PARTICULATE_ARCHETYPES = {
    SourceCategory.HEAVY_DUST.value,
    SourceCategory.CONSTRUCTION_ACTIVITY.value,
}
COMBUSTION_ARCHETYPES = {
    SourceCategory.TRAFFIC.value,
    SourceCategory.INDUSTRIAL_OR_GENERATOR_EMISSIONS.value,
    SourceCategory.BIOMASS_OR_WASTE_BURNING.value,
    SourceCategory.COOKING_OR_FUEL_COMBUSTION.value,
}


SMOKE_ARCHETYPES = {
    SourceCategory.BIOMASS_OR_WASTE_BURNING.value,
    SourceCategory.COOKING_OR_FUEL_COMBUSTION.value,
}
ENGINE_EXHAUST_ARCHETYPES = {
    SourceCategory.TRAFFIC.value,
    SourceCategory.INDUSTRIAL_OR_GENERATOR_EMISSIONS.value,
}


def detect_mixed_pollution(
    predictions: List[Dict[str, Any]],
    config: SourceClassifierConfig,
    features: Optional[Dict[str, Optional[float]]] = None,
) -> bool:
    """
    Check if the pattern suggests multiple overlapping sources.

    Multi-tier detection (Phase 2B):
      Tier 1 (Tri-source): >= 3 categories scoring above mixed_pollution_threshold (0.35).
      Tier 2 (Dual distinct archetypes): Top 2 candidates from different physical archetypes
             (e.g., particulate/dust vs combustion/gas) both scoring >= mixed_pollution_dual_threshold (0.35)
             with gap <= mixed_pollution_dual_gap (0.15).
      Tier 3 (Asymmetric weaker secondary with orthogonal evidence):
        3A: Coarse dust (PM10 >= 140 ug/m3 or coarse_ratio >= 1.7) + active gas (MQ >= 2.05V)
            with particulate candidate >= 0.40 and combustion candidate >= 0.28.
        3B: Dense combustion smoke (PM2.5 >= 100 ug/m3, MQ2 >= 2.2V) + heavy engine CO (MQ9 >= 2.0V)
            with smoke candidate >= 0.40 and engine exhaust candidate >= 0.25 (top score < 0.85).
    """
    candidates = [
        p
        for p in predictions
        if p["source"] not in (
            SourceCategory.UNKNOWN.value,
            SourceCategory.MIXED_POLLUTION.value,
            SourceCategory.CLEAN_OR_BACKGROUND.value,
        )
    ]

    if not candidates:
        return False

    # Tier 1: Tri-source or more (at least 3 sources scoring above threshold)
    tri_threshold = getattr(config, "mixed_pollution_tri_threshold", config.mixed_pollution_threshold)
    high_scoring = [p for p in candidates if p["match_score"] >= tri_threshold]
    if len(high_scoring) >= config.mixed_pollution_min_sources:
        return True

    # Tier 2: Dual distinct archetypes (comparable scores)
    if len(candidates) >= 2:
        c1, c2 = candidates[0], candidates[1]
        s1, s2 = c1["match_score"], c2["match_score"]
        gap = abs(s1 - s2)
        dual_gap = getattr(config, "mixed_pollution_dual_gap", 0.15)
        dual_thresh = getattr(config, "mixed_pollution_dual_threshold", 0.35)

        if s1 >= dual_thresh and s2 >= dual_thresh and gap <= dual_gap:
            src1, src2 = c1["source"], c2["source"]
            is_c1_part = src1 in PARTICULATE_ARCHETYPES
            is_c2_part = src2 in PARTICULATE_ARCHETYPES
            is_c1_comb = src1 in COMBUSTION_ARCHETYPES
            is_c2_comb = src2 in COMBUSTION_ARCHETYPES

            # Dust/particulate co-occurring with fuel/gas combustion
            if (is_c1_part and is_c2_comb) or (is_c1_comb and is_c2_part):
                # If one is CONSTRUCTION_ACTIVITY and the other is fuel combustion,
                # construction already includes diesel machinery. Only treat as mixture if gap is <= 0.10
                if (src1 == SourceCategory.CONSTRUCTION_ACTIVITY.value and src2 in (SourceCategory.TRAFFIC.value, SourceCategory.INDUSTRIAL_OR_GENERATOR_EMISSIONS.value)) or \
                   (src2 == SourceCategory.CONSTRUCTION_ACTIVITY.value and src1 in (SourceCategory.TRAFFIC.value, SourceCategory.INDUSTRIAL_OR_GENERATOR_EMISSIONS.value)):
                    if gap <= 0.10 and s1 >= 0.40 and s2 >= 0.40:
                        return True
                else:
                    return True

            # Two distinct combustion archetypes: Biomass burning + Vehicle traffic
            if (
                src1 == SourceCategory.BIOMASS_OR_WASTE_BURNING.value
                and src2 == SourceCategory.TRAFFIC.value
            ) or (
                src2 == SourceCategory.BIOMASS_OR_WASTE_BURNING.value
                and src1 == SourceCategory.TRAFFIC.value
            ):
                return True

    # Tier 3: Asymmetric weaker secondary source with orthogonal physical sensor evidence
    if features is not None:
        pm_coarse_ratio = features.get("pm_coarse_ratio") or 0.0
        pm10 = features.get("pm10") or 0.0
        pm25 = features.get("pm2_5") or 0.0
        mq2_v = features.get("mq2_v") or 0.0
        mq9_v = features.get("mq9_v") or 0.0
        mq135_v = features.get("mq135_v") or 0.0

        # Sub-tier 3A: Coarse dust co-occurring with elevated combustion/industrial gas
        has_coarse_dust = pm10 >= 140.0 or pm_coarse_ratio >= 1.7
        has_elevated_gas = mq9_v >= 2.05 or mq135_v >= 2.05 or mq2_v >= 2.05

        if has_coarse_dust and has_elevated_gas:
            part_cands = [p for p in candidates if p["source"] in PARTICULATE_ARCHETYPES and p["match_score"] >= 0.40]
            comb_cands = [
                p for p in candidates
                if p["source"] in COMBUSTION_ARCHETYPES
                and p["match_score"] >= config.mixed_pollution_weak_secondary_threshold
            ]
            if part_cands and comb_cands:
                return True

        # Sub-tier 3B: Dense combustion smoke co-occurring with vehicle / engine exhaust gas
        has_dense_smoke = pm25 >= 100.0 and mq2_v >= 2.20
        has_engine_exhaust = mq9_v >= 2.00
        top_cand_score = candidates[0]["match_score"] if candidates else 0.0

        if has_dense_smoke and has_engine_exhaust and top_cand_score < 0.85:
            smoke_cands = [p for p in candidates if p["source"] in SMOKE_ARCHETYPES and p["match_score"] >= 0.40]
            engine_cands = [
                p for p in candidates
                if p["source"] in ENGINE_EXHAUST_ARCHETYPES
                and p["match_score"] >= config.mixed_pollution_weak_secondary_threshold
            ]
            if smoke_cands and engine_cands:
                return True

    return False


def assess_uncertainty(
    predictions: List[Dict[str, Any]],
    config: SourceClassifierConfig,
    data_quality_status: str,
    features: Optional[Dict[str, Optional[float]]] = None,
) -> Dict[str, Any]:
    """
    Assess whether the classification result is uncertain.

    Uncertainty arises from:
      - Low top match score
      - Small gap between top two candidates
      - Degraded or invalid data quality
      - Mixed pollution
      - Physical sensor ambiguity (Traffic vs Industrial/Generator emissions)
      - Baseline ambiguity (Indoor activity vs Clean ambient background)
    """
    reasons: List[str] = []

    non_unknown = [
        p
        for p in predictions
        if p["source"] not in (SourceCategory.UNKNOWN.value, SourceCategory.MIXED_POLLUTION.value)
    ]

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

    if detect_mixed_pollution(predictions, config, features):
        reasons.append("Multiple sources may be contributing")

    # Domain-specific physical ambiguity 1: Traffic vs Industrial / Generator Emissions
    p_traffic = next((p for p in predictions if p["source"] == SourceCategory.TRAFFIC.value), None)
    p_industrial = next((p for p in predictions if p["source"] == SourceCategory.INDUSTRIAL_OR_GENERATOR_EMISSIONS.value), None)
    if p_traffic and p_industrial:
        st = p_traffic["match_score"]
        si = p_industrial["match_score"]
        if max(st, si) >= 0.22 and abs(st - si) <= config.traffic_generator_ambiguity_gap:
            reasons.append(
                "Physical sensor ambiguity: MOS sensors cannot reliably differentiate vehicle traffic emissions from stationary diesel generator exhaust without chemical speciation"
            )

    # Domain-specific physical ambiguity 2: Indoor Activity vs Clean / Background
    p_clean = next((p for p in predictions if p["source"] == SourceCategory.CLEAN_OR_BACKGROUND.value), None)
    p_indoor = next((p for p in predictions if p["source"] == SourceCategory.INDOOR_ACTIVITY.value), None)
    if p_clean and p_indoor:
        sc = p_clean["match_score"]
        s_in = p_indoor["match_score"]
        if max(sc, s_in) >= 0.20 and abs(sc - s_in) <= config.indoor_background_ambiguity_gap:
            near_baseline = True
            if features:
                pm25 = features.get("pm2_5") or 0.0
                mq9 = features.get("mq9_v") or 0.0
                mq2 = features.get("mq2_v") or 0.0
                if pm25 > 35.0 or mq9 > 1.2 or mq2 > 1.2:
                    near_baseline = False
            if near_baseline:
                reasons.append(
                    "Baseline ambiguity: Low particulate and clean baseline gas levels cannot distinguish well-ventilated indoor activity from clean ambient outdoor air"
                )

    return {
        "is_uncertain": len(reasons) > 0,
        "reason": "; ".join(reasons) if reasons else None,
    }
