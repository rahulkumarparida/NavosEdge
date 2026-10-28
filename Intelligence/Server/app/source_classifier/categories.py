"""
Source category definitions and configuration for Phase 3 classifier.

Categories represent broad environmental source hypotheses relevant to
urban Indian cities like Bhubaneswar.  They are NOT confirmed source
identities — the sensors available (MQ2, MQ9, MQ135, PM1.0/2.5/10,
temperature, humidity) cannot uniquely identify chemical composition.

Design decisions documented inline.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional


class SourceCategory(str, Enum):
    """
    Broad environmental source categories.

    Merged categories (documented rationale):
    - HEAVY_DUST and CONSTRUCTION_ACTIVITY are kept separate because PM
      coarse-to-fine ratio and MQ-sensor response patterns differ: pure
      dust resuspension shows high PM10/PM2.5 ratio with low MQ response,
      whereas active construction may involve diesel equipment that elevates
      MQ9 (CO-sensitive) readings.
    - COOKING_OR_FUEL_COMBUSTION and INDOOR_ACTIVITY are kept separate
      because cooking combustion produces elevated MQ2 (smoke) and PM1.0,
      while generic indoor activity may show moderate PM without MQ spikes.
    """

    CLEAN_OR_BACKGROUND = "CLEAN_OR_BACKGROUND"
    TRAFFIC = "TRAFFIC"
    HEAVY_DUST = "HEAVY_DUST"
    CONSTRUCTION_ACTIVITY = "CONSTRUCTION_ACTIVITY"
    BIOMASS_OR_WASTE_BURNING = "BIOMASS_OR_WASTE_BURNING"
    INDUSTRIAL_OR_GENERATOR_EMISSIONS = "INDUSTRIAL_OR_GENERATOR_EMISSIONS"
    COOKING_OR_FUEL_COMBUSTION = "COOKING_OR_FUEL_COMBUSTION"
    INDOOR_ACTIVITY = "INDOOR_ACTIVITY"
    MIXED_POLLUTION = "MIXED_POLLUTION"
    UNKNOWN = "UNKNOWN"


# Human-readable descriptions for each category
SOURCE_DESCRIPTIONS: Dict[SourceCategory, str] = {
    SourceCategory.CLEAN_OR_BACKGROUND: (
        "Relatively low and stable particulate and gas-response patterns, "
        "consistent with background ambient conditions."
    ),
    SourceCategory.TRAFFIC: (
        "Patterns potentially consistent with vehicle-related emissions "
        "and roadside particulate matter."
    ),
    SourceCategory.HEAVY_DUST: (
        "Patterns potentially consistent with resuspended road dust, "
        "construction debris, or soil particles."
    ),
    SourceCategory.CONSTRUCTION_ACTIVITY: (
        "Patterns potentially consistent with construction-related dust "
        "and diesel equipment emissions."
    ),
    SourceCategory.BIOMASS_OR_WASTE_BURNING: (
        "Patterns potentially consistent with biomass or waste combustion."
    ),
    SourceCategory.INDUSTRIAL_OR_GENERATOR_EMISSIONS: (
        "Patterns potentially consistent with industrial activity "
        "or diesel generator exhaust."
    ),
    SourceCategory.COOKING_OR_FUEL_COMBUSTION: (
        "Patterns potentially consistent with cooking or fuel-burning activity."
    ),
    SourceCategory.INDOOR_ACTIVITY: (
        "Patterns potentially consistent with indoor environmental sources."
    ),
    SourceCategory.MIXED_POLLUTION: (
        "Patterns that may reflect multiple overlapping sources."
    ),
    SourceCategory.UNKNOWN: (
        "Insufficient evidence, out-of-distribution input, or no suitable match."
    ),
}


from app.core.constants import (
    RAW_FEATURES as SOURCE_CLASSIFIER_FEATURES,
    DERIVED_FEATURES as SOURCE_CLASSIFIER_DERIVED_FEATURES,
    ALL_CLASSIFIER_FEATURES as ALL_SOURCE_CLASSIFIER_FEATURES,
)


@dataclass
class SourceClassifierConfig:
    """
    Configuration for the source classifier.

    All values are configurable and documented.
    """

    # ---- Tolerance ----
    # Default ±10% tolerance applied to learned reference ranges.
    # This expands the "in-range" boundaries by this fraction.
    # NOT applied when the reference value is near zero (abs < near_zero_threshold).
    tolerance_fraction: float = 0.10

    # For features with reference values near zero, use this absolute tolerance
    # instead of percentage-based, to avoid nonsensical tiny ranges.
    near_zero_threshold: float = 1.0
    near_zero_absolute_tolerance: float = 0.5

    # ---- Scoring weights ----
    # Weight for Decision Tree probability in combined score.
    # Must be in [0, 1]; similarity weight = 1 - dt_weight.
    dt_probability_weight: float = 0.6
    similarity_weight: float = 0.4

    # ---- Uncertainty thresholds ----
    # If the top match_score is below this, mark as uncertain.
    uncertainty_score_threshold: float = 0.35

    # If the gap between the top two scores is below this, mark as uncertain.
    uncertainty_gap_threshold: float = 0.10

    # If more than this fraction of features are missing, degrade data quality.
    missing_feature_degraded_threshold: float = 0.3
    # If more than this, mark as invalid.
    missing_feature_invalid_threshold: float = 0.6

    # Number of top sources to return in predictions.
    top_n: int = 5

    # Minimum match_score to include a source in predictions (below this, omit).
    min_score_threshold: float = 0.05

    # ---- MIXED_POLLUTION detection ----
    # Tier 1 (Tri-source): If >= 3 categories have scores above this threshold, classify as MIXED_POLLUTION.
    mixed_pollution_threshold: float = 0.35
    mixed_pollution_min_sources: int = 3
    # Tier 2 (Dual-source): Both top candidates from distinct archetypes above this threshold with narrow gap
    mixed_pollution_dual_threshold: float = 0.35
    mixed_pollution_dual_gap: float = 0.15
    # Tier 3 (Asymmetric weaker secondary): Weaker secondary threshold when orthogonal physical features are present
    mixed_pollution_weak_secondary_threshold: float = 0.28
    # Score boost for MIXED_POLLUTION when multi-source pollution is detected to ensure it tops predictions
    mixed_pollution_boost: float = 0.05

    # ---- Ambiguity & Domain-Specific Uncertainty (Phase 2B) ----
    # Threshold gap below which fuel combustion sources (Traffic vs Industrial/Generator)
    # cannot be physically resolved by low-cost MOS/PM sensors.
    traffic_generator_ambiguity_gap: float = 0.18
    # Baseline threshold gap for indoor activity vs ambient background air.
    indoor_background_ambiguity_gap: float = 0.15
    # Cap confidence on physically ambiguous sources (MOS array cannot claim high certainty)
    ambiguous_confidence_cap: float = 0.40
    # Near-tie abstention gap: when two competing ambiguous sources are virtually tied (within 0.5% match score), mark UNKNOWN
    ambiguity_abstain_gap: float = 0.005

    # ---- Model paths (relative to artifacts dir) ----
    model_filename: str = "source_classifier_model.pkl"
    reference_stats_filename: str = "source_classifier_stats.json"
    metadata_filename: str = "source_classifier_metadata.json"

    # Model version label
    model_version: str = "0.2.0-phase2b-ambiguity"
