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

        # Step 3: Get Decision Tree probabilities (if model available)
        dt_probabilities = None
        if self._model is not None and self._scaler is not None:
            dt_probabilities = self._get_dt_probabilities(features)

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

            # Step 5: Handle MIXED_POLLUTION
            if detect_mixed_pollution(predictions, self.config):
                # Insert MIXED_POLLUTION as a candidate
                mixed_score = max(p["match_score"] for p in predictions[:3]) * 0.95
                mixed_pred = {
                    "source": SourceCategory.MIXED_POLLUTION.value,
                    "match_score": round(mixed_score, 4),
                    "confidence": None,
                    "supporting_features": [
                        f"Multiple sources scoring above {self.config.mixed_pollution_threshold}"
                    ],
                    "limitations": [
                        "Cannot distinguish individual source contributions"
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
                predictions, self.config, data_quality["status"]
            )

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

        # Check for railed sensors
        for sensor_key, label in [
            ("mq2_v", "MQ2"),
            ("mq9_v", "MQ9"),
            ("mq135_v", "MQ135"),
        ]:
            v = features.get(sensor_key)
            if v is not None:
                if v <= 0.01:
                    warnings.append(f"{label} voltage railed to GND")
                elif v >= 4.99:
                    warnings.append(f"{label} voltage railed to VCC")

        # Check staleness
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
                if status == "valid":
                    status = "degraded"
        except Exception:
            pass

        if warnings and status == "valid":
            status = "degraded"

        return {
            "status": status,
            "missing_features": missing_features,
            "warnings": warnings,
            "stale": stale,
        }
