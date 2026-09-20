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


# Feature names used by the source classifier.
# These are the 8 raw features extracted from SensorPayload.
SOURCE_CLASSIFIER_FEATURES = [
    "mq2_v",
    "mq9_v",
    "mq135_v",
    "temp_c",
    "hum_pct",
    "pm1_0",
    "pm2_5",
    "pm10",
]

# Derived ratio features calculated from raw features.
SOURCE_CLASSIFIER_DERIVED_FEATURES = [
    "pm_coarse_ratio",   # PM10 / PM2.5 — dust vs combustion discriminator
    "pm_fine_ratio",     # PM2.5 / PM1.0 — fine particle enrichment
    "mq_mean_v",         # mean(MQ2, MQ9, MQ135) voltage
    "mq_max_v",          # max(MQ2, MQ9, MQ135) voltage
    "mq2_mq9_ratio",    # MQ2 / MQ9 — smoke vs CO discriminator
    "mq135_mq2_ratio",  # MQ135 / MQ2 — air quality vs smoke
]

ALL_SOURCE_CLASSIFIER_FEATURES = (
    SOURCE_CLASSIFIER_FEATURES + SOURCE_CLASSIFIER_DERIVED_FEATURES
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
    # If the top N categories (excluding UNKNOWN) all have scores above this
    # threshold, classify as MIXED_POLLUTION.
    mixed_pollution_threshold: float = 0.40
    mixed_pollution_min_sources: int = 3

    # ---- Model paths (relative to artifacts dir) ----
    model_filename: str = "source_classifier_model.pkl"
    reference_stats_filename: str = "source_classifier_stats.json"
    metadata_filename: str = "source_classifier_metadata.json"

    # Model version label
    model_version: str = "0.1.0-synthetic"
