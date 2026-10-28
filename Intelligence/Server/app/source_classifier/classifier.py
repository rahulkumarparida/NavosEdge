"""
Source Classifier — main classifier class.

Loads a trained DecisionTreeClassifier and per-class reference statistics,
accepts validated SensorPayload data, and returns a ranked list of source
hypotheses with match scores, confidence, and uncertainty information.

Fails gracefully when model artifacts are unavailable.
"""

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.schemas.sensor import SensorPayload
from app.source_classifier.categories import (
    SourceCategory,
    SourceClassifierConfig,
    ALL_SOURCE_CLASSIFIER_FEATURES,
)
from app.source_classifier.features import (
    extract_source_features,
    features_to_model_array,
)
from app.source_classifier.scoring import (
    ReferenceStats,
    assess_uncertainty,
    compute_combined_scores,
    detect_mixed_pollution,
)

logger = logging.getLogger(__name__)

try:
    import joblib
    import numpy as np
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False


class SourceClassifier:
    """
    Lightweight, explainable source classifier for environmental monitoring.

    Uses a Decision Tree as the primary classifier with feature-range
    similarity scoring for enhanced explainability.
    """

    def __init__(
        self,
        artifacts_dir: Path,
        config: Optional[SourceClassifierConfig] = None,
    ) -> None:
        self.artifacts_dir = artifacts_dir
        self.config = config or SourceClassifierConfig()
        self._model: Any = None
        self._scaler: Any = None
        self._metadata: Dict[str, Any] = {}
        self._reference_stats = ReferenceStats()
        self._loaded = False
        self._feature_names: List[str] = ALL_SOURCE_CLASSIFIER_FEATURES
        self._class_names: List[str] = []

    def load(self) -> bool:
        """
        Load model artifacts from disk.

        Returns True if at least partial loading succeeded.
        The classifier can still produce similarity-only scores without
        a trained model if reference stats are available.
        """
        if not SKLEARN_AVAILABLE:
            logger.warning(
                "scikit-learn/joblib/numpy not installed — "
                "source classifier will report NOT_CONFIGURED."
            )
            return False

        model_path = self.artifacts_dir / self.config.model_filename
        stats_path = self.artifacts_dir / self.config.reference_stats_filename
        metadata_path = self.artifacts_dir / self.config.metadata_filename

        model_loaded = False
        stats_loaded = False

        # Load Decision Tree model
        if model_path.exists():
            try:
                bundle = joblib.load(model_path)
                self._model = bundle.get("model")
                self._scaler = bundle.get("scaler")
                self._class_names = list(bundle.get("class_names", []))
                self._feature_names = list(
                    bundle.get("feature_names", ALL_SOURCE_CLASSIFIER_FEATURES)
                )
                model_loaded = True
                logger.info(
                    "Source classifier model loaded: %d classes, %d features",
                    len(self._class_names),
                    len(self._feature_names),
                )
            except Exception as e:
                logger.error("Failed to load source classifier model: %s", e)
        else:
            logger.info(
                "Source classifier model not found at %s — "
                "will use similarity-only scoring.",
                model_path,
            )

        # Load reference statistics
        if stats_path.exists():
            stats_loaded = self._reference_stats.load(stats_path)

        # Load metadata
        if metadata_path.exists():
            try:
                with open(metadata_path) as f:
                    self._metadata = json.load(f)
            except Exception as e:
                logger.warning("Failed to load classifier metadata: %s", e)

        self._loaded = model_loaded or stats_loaded

        if not self._loaded:
            logger.warning(
                "Source classifier has no model or reference stats — "
                "will return UNKNOWN for all inputs."
            )

        return self._loaded

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def model_version(self) -> str:
        return self._metadata.get("version", self.config.model_version)

    def classify(self, payload: SensorPayload) -> Dict[str, Any]:
        """
        Classify a sensor payload and return structured source hypotheses.

        Returns the full classification result dict matching the Phase 3 schema.
        Always succeeds — returns UNKNOWN if artifacts are unavailable.
        """
        t0 = time.perf_counter()

        # Step 1: Extract features
        features, missing_features = extract_source_features(payload)

        # Step 2: Assess data quality
        data_quality = self._assess_data_quality(features, missing_features, payload)

        if data_quality["status"] == "invalid":
            predictions = [
                {
                    "source": SourceCategory.UNKNOWN.value,
                    "match_score": 1.0,
                    "confidence": None,
                    "supporting_features": [],
                    "limitations": list(data_quality["warnings"]),
                }
            ]
            top_source = SourceCategory.UNKNOWN.value
            uncertainty = {
                "is_uncertain": True,
                "reason": f"Abstained due to invalid sensor telemetry: {'; '.join(data_quality['warnings'])}",
            }
            processing_time_ms = (time.perf_counter() - t0) * 1000.0
            return {
                "classifier": "source_classifier",
                "status": "success",
                "predictions": predictions,
                "top_source": top_source,
                "uncertainty": uncertainty,
                "data_quality": data_quality,
                "model_version": self.model_version,
                "processing_time_ms": round(processing_time_ms, 2),
            }

        # Step 3: Get Decision Tree probabilities (if model available)
        dt_probabilities = None
        if self._model is not None and self._scaler is not None:
            dt_probabilities = self._get_dt_probabilities(features)
            if dt_probabilities:
                # Domain-specific physical ambiguity calibration (Phase 2B):
                # When physical telemetry falls into unidentifiable sensor ambiguity regimes,
                # temper the overconfident Decision Tree splits between ambiguous pairs.

                # 1. Fuel combustion ambiguity (Traffic vs Industrial / Diesel Generator):
                # Low-cost MOS sensors cannot differentiate vehicle tailpipe from stationary diesel generator exhaust.
                mq9_v = features.get("mq9_v") or 0.0
                mq135_v = features.get("mq135_v") or 0.0
                pm25 = features.get("pm2_5") or 0.0
                pm_coarse = features.get("pm_coarse_ratio") or 1.0

                if mq9_v >= 1.50 and mq135_v >= 1.15 and pm25 >= 20.0 and pm_coarse <= 2.2:
                    p_tr = dt_probabilities.get(SourceCategory.TRAFFIC.value, 0.0)
                    p_ind = dt_probabilities.get(SourceCategory.INDUSTRIAL_OR_GENERATOR_EMISSIONS.value, 0.0)
                    comb_avg = (p_tr + p_ind) / 2.0
                    dt_probabilities[SourceCategory.TRAFFIC.value] = comb_avg
                    dt_probabilities[SourceCategory.INDUSTRIAL_OR_GENERATOR_EMISSIONS.value] = comb_avg

                # 2. Baseline clean air ambiguity (Indoor Activity vs Ambient Clean Background):
                # Low-cost array without CO2 NDIR cannot differentiate ventilated indoor air from clean ambient air.
                mq2_v = features.get("mq2_v") or 0.0
                if pm25 <= 22.0 and mq9_v <= 1.05 and mq2_v <= 1.05 and mq135_v <= 1.35:
                    p_cln = dt_probabilities.get(SourceCategory.CLEAN_OR_BACKGROUND.value, 0.0)
                    p_in = dt_probabilities.get(SourceCategory.INDOOR_ACTIVITY.value, 0.0)
                    base_avg = (p_cln + p_in) / 2.0
                    dt_probabilities[SourceCategory.CLEAN_OR_BACKGROUND.value] = base_avg
                    dt_probabilities[SourceCategory.INDOOR_ACTIVITY.value] = base_avg

        # Step 4: Compute combined scores
        if not self._loaded:
            # No artifacts — return UNKNOWN
            predictions = [
                {
                    "source": SourceCategory.UNKNOWN.value,
                    "match_score": 0.0,
                    "confidence": None,
                    "supporting_features": [],
                    "limitations": ["No model artifacts available"],
                }
            ]
            top_source = SourceCategory.UNKNOWN.value
            uncertainty = {
                "is_uncertain": True,
                "reason": "Classifier not configured (no model artifacts)",
            }
        else:
            predictions = compute_combined_scores(
                features,
                dt_probabilities,
                self._reference_stats,
                self.config,
            )

            # Step 5: Handle MIXED_POLLUTION (Phase 2B multi-tier detection)
            if detect_mixed_pollution(predictions, self.config, features=features):
                contributing = [
                    p["source"]
                    for p in predictions[:3]
                    if p["source"] not in (SourceCategory.UNKNOWN.value, SourceCategory.MIXED_POLLUTION.value)
                    and p["match_score"] >= self.config.mixed_pollution_weak_secondary_threshold
                ]
                top_cand_score = max((p["match_score"] for p in predictions[:3]), default=0.5)
                mixed_score = min(1.0, top_cand_score + self.config.mixed_pollution_boost)
                mixed_pred = {
                    "source": SourceCategory.MIXED_POLLUTION.value,
                    "match_score": round(mixed_score, 4),
                    "confidence": None,
                    "supporting_features": [
                        f"Multiple co-occurring source signatures detected ({', '.join(contributing)})"
                    ] if contributing else [
                        f"Multiple sources scoring above {self.config.mixed_pollution_threshold}"
                    ],
                    "limitations": [
                        "Cannot separate individual emission fractions from low-cost sensor array"
                    ],
                }
                predictions.append(mixed_pred)
                predictions.sort(key=lambda x: x["match_score"], reverse=True)

            # Step 6: Filter and limit
            predictions = [
                p
                for p in predictions
                if p["match_score"] >= self.config.min_score_threshold
            ]
            predictions = predictions[: self.config.top_n]

            # Ensure UNKNOWN is included if top score is low
            if predictions and predictions[0]["match_score"] < self.config.uncertainty_score_threshold:
                if not any(p["source"] == SourceCategory.UNKNOWN.value for p in predictions):
                    predictions.append(
                        {
                            "source": SourceCategory.UNKNOWN.value,
                            "match_score": round(
                                1.0 - predictions[0]["match_score"], 4
                            ),
                            "confidence": None,
                            "supporting_features": [],
                            "limitations": ["Weak evidence for all candidates"],
                        }
                    )
                    predictions.sort(key=lambda x: x["match_score"], reverse=True)
                    predictions = predictions[: self.config.top_n]

            top_source = (
                predictions[0]["source"] if predictions else SourceCategory.UNKNOWN.value
            )

            # Step 7: Assess uncertainty
            uncertainty = assess_uncertainty(
                predictions, self.config, data_quality["status"], features=features
            )

            # Step 8: Ambiguity handling and confidence calibration (Phase 2B)
            # Physical ambiguity: Traffic vs Industrial / Generator Emissions
            p_traf = next((p for p in predictions if p["source"] == SourceCategory.TRAFFIC.value), None)
            p_ind = next((p for p in predictions if p["source"] == SourceCategory.INDUSTRIAL_OR_GENERATOR_EMISSIONS.value), None)
            if p_traf and p_ind:
                gap_tg = abs(p_traf["match_score"] - p_ind["match_score"])
                if max(p_traf["match_score"], p_ind["match_score"]) >= 0.22 and gap_tg <= self.config.traffic_generator_ambiguity_gap:
                    lim_text = "Low-cost MOS sensors (MQ2/9/135) and optical PM counters cannot uniquely differentiate vehicle tailpipe emissions from stationary diesel generator combustion"
                    for p in (p_traf, p_ind):
                        if lim_text not in p["limitations"]:
                            p["limitations"].append(lim_text)
                        if p.get("confidence") is not None and p["confidence"] > self.config.ambiguous_confidence_cap:
                            p["confidence"] = self.config.ambiguous_confidence_cap
                    # Near-tie abstention
                    if top_source in (SourceCategory.TRAFFIC.value, SourceCategory.INDUSTRIAL_OR_GENERATOR_EMISSIONS.value):
                        if gap_tg <= self.config.ambiguity_abstain_gap:
                            top_source = SourceCategory.UNKNOWN.value

            # Baseline ambiguity: Indoor Activity vs Clean Background
            p_cln = next((p for p in predictions if p["source"] == SourceCategory.CLEAN_OR_BACKGROUND.value), None)
            p_in = next((p for p in predictions if p["source"] == SourceCategory.INDOOR_ACTIVITY.value), None)
            if p_cln and p_in:
                gap_ci = abs(p_cln["match_score"] - p_in["match_score"])
                if max(p_cln["match_score"], p_in["match_score"]) >= 0.20 and gap_ci <= self.config.indoor_background_ambiguity_gap:
                    near_baseline = True
                    pm25 = features.get("pm2_5") or 0.0
                    mq9 = features.get("mq9_v") or 0.0
                    mq2 = features.get("mq2_v") or 0.0
                    if pm25 > 35.0 or mq9 > 1.2 or mq2 > 1.2:
                        near_baseline = False
                    if near_baseline:
                        lim_base = "Low-cost array cannot reliably differentiate ventilated indoor environments from clean ambient background air without CO2 NDIR or VOC speciation"
                        for p in (p_cln, p_in):
                            if lim_base not in p["limitations"]:
                                p["limitations"].append(lim_base)
                            if p.get("confidence") is not None and p["confidence"] > self.config.ambiguous_confidence_cap:
                                p["confidence"] = self.config.ambiguous_confidence_cap
                        # Near-tie abstention
                        if top_source in (SourceCategory.CLEAN_OR_BACKGROUND.value, SourceCategory.INDOOR_ACTIVITY.value):
                            if gap_ci <= self.config.ambiguity_abstain_gap:
                                top_source = SourceCategory.UNKNOWN.value

        processing_time_ms = (time.perf_counter() - t0) * 1000.0

        return {
            "classifier": "source_classifier",
            "status": "success",
            "predictions": predictions,
            "top_source": top_source,
            "uncertainty": uncertainty,
            "data_quality": data_quality,
            "model_version": self.model_version,
            "processing_time_ms": round(processing_time_ms, 2),
        }

    def _get_dt_probabilities(
        self, features: Dict[str, Optional[float]]
    ) -> Optional[Dict[str, float]]:
        """
        Run the Decision Tree and return per-class probabilities.

        Returns None if prediction fails.
        """
        try:
            feature_array = features_to_model_array(
                features, self._feature_names, fill_value=0.0
            )
            x = np.array([feature_array], dtype=np.float32)

            if self._scaler is not None:
                x = self._scaler.transform(x)

            proba = self._model.predict_proba(x)[0]

            return {
                cls_name: float(prob)
                for cls_name, prob in zip(self._class_names, proba)
            }
        except Exception as e:
            logger.error("Decision Tree prediction failed: %s", e)
            return None

    def _assess_data_quality(
        self,
        features: Dict[str, Optional[float]],
        missing_features: List[str],
        payload: SensorPayload,
    ) -> Dict[str, Any]:
        """Assess the quality of input data for classification."""
        warnings: List[str] = []

        total_features = len(ALL_SOURCE_CLASSIFIER_FEATURES)
        missing_frac = len(missing_features) / total_features if total_features > 0 else 0

        if missing_frac >= self.config.missing_feature_invalid_threshold:
            status = "invalid"
        elif missing_frac >= self.config.missing_feature_degraded_threshold:
            status = "degraded"
        else:
            status = "valid"

        # Check for railed sensors against Phase 2A validated electrical limits [0.100V, 4.900V]
        for sensor_key, label in [
            ("mq2_v", "MQ2"),
            ("mq9_v", "MQ9"),
            ("mq135_v", "MQ135"),
        ]:
            v = features.get(sensor_key)
            if v is not None:
                if v < 0.100:
                    warnings.append(f"{label} voltage below physical limit ({v:.3f}V < 0.100V)")
                    status = "invalid"
                elif v > 4.900:
                    warnings.append(f"{label} voltage above physical limit ({v:.3f}V > 4.900V)")
                    status = "invalid"

        # Check environmental physical limits [-10°C, 65°C] and [0%, 100%]
        temp = features.get("temp_c")
        if temp is not None and not (-10.0 <= temp <= 65.0):
            warnings.append(f"Temperature out of physical bounds ({temp:.1f}°C)")
            status = "invalid"
        hum = features.get("hum_pct")
        if hum is not None and not (0.0 <= hum <= 100.0):
            warnings.append(f"Humidity out of physical bounds ({hum:.1f}%)")
            status = "invalid"

        # Check PM ordering physical constraint (PM1.0 <= PM2.5 <= PM10)
        pm1 = features.get("pm1_0")
        pm25 = features.get("pm2_5")
        pm10 = features.get("pm10")
        if pm1 is not None and pm25 is not None and pm10 is not None:
            if pm1 > pm25 + 0.5 or pm25 > pm10 + 0.5:
                warnings.append("PM ordering violation (PM1.0 <= PM2.5 <= PM10)")
                status = "invalid"

        # Staleness flag (record flag and warning, but do not degrade status if readings are physically valid)
        stale = False
        try:
            from datetime import datetime, timezone

            now = datetime.now(timezone.utc)
            ts = payload.timestamp
            if ts.tzinfo is not None:
                ts_utc = ts.astimezone(timezone.utc)
            else:
                ts_utc = ts.replace(tzinfo=timezone.utc)
            age_seconds = (now - ts_utc).total_seconds()
            if age_seconds > 300:  # 5 minutes
                stale = True
                warnings.append(f"Data is {age_seconds:.0f}s old")
        except Exception:
            pass

        return {
            "status": status,
            "missing_features": missing_features,
            "warnings": warnings,
            "stale": stale,
        }
