"""
Pydantic schemas for Phase 3 Source Classification results.

These schemas define the structured output format for source classification
predictions, integrated into the existing response pipeline.
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SourceClassificationStatus(str, Enum):
    SUCCESS = "success"
    NOT_CONFIGURED = "not_configured"
    ERROR = "error"


class SourcePrediction(BaseModel):
    """A single source hypothesis with supporting evidence."""

    source: str = Field(description="Source category name")
    match_score: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Normalized pattern-matching score [0,1]. NOT a calibrated probability. "
            "Indicates how closely the input matches the learned source profile."
        ),
    )
    confidence: Optional[float] = Field(
        default=None,
        description=(
            "Decision Tree class probability, if available. Only set when the "
            "DT model provides genuine predict_proba output. None if similarity-only."
        ),
    )
    supporting_features: List[str] = Field(
        default_factory=list,
        description="Features that contributed most to this match",
    )
    limitations: List[str] = Field(
        default_factory=list,
        description="Known limitations or caveats for this prediction",
    )


class UncertaintyInfo(BaseModel):
    """Uncertainty assessment for the classification result."""

    is_uncertain: bool = Field(
        description="Whether the classification result has significant uncertainty"
    )
    reason: Optional[str] = Field(
        default=None,
        description="Human-readable explanation of why the result is uncertain",
    )


class SourceDataQuality(BaseModel):
    """Data quality assessment for source classification input."""

    status: str = Field(description="Overall quality: valid, degraded, invalid")
    missing_features: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    stale: bool = Field(default=False)


class SourceClassificationResult(BaseModel):
    """
    Complete source classification result.

    Returned by the source classifier for each sensor reading.
    """

    classifier: str = Field(default="source_classifier")
    status: SourceClassificationStatus
    predictions: List[SourcePrediction] = Field(default_factory=list)
    top_source: Optional[str] = Field(
        default=None,
        description=(
            "The highest-scoring source hypothesis. This is NOT a confirmed "
            "source identity — it is the best pattern match."
        ),
    )
    uncertainty: Optional[UncertaintyInfo] = None
    data_quality: Optional[SourceDataQuality] = None
    model_version: Optional[str] = None
    processing_time_ms: Optional[float] = None
    error_message: Optional[str] = None

    @classmethod
    def not_configured(cls) -> "SourceClassificationResult":
        return cls(
            status=SourceClassificationStatus.NOT_CONFIGURED,
            top_source=None,
        )

    @classmethod
    def from_error(cls, message: str) -> "SourceClassificationResult":
        return cls(
            status=SourceClassificationStatus.ERROR,
            error_message=message,
        )

    @classmethod
    def from_classifier_dict(cls, result: Dict[str, Any]) -> "SourceClassificationResult":
        """Convert the raw classifier output dict to a Pydantic model."""
        predictions = [
            SourcePrediction(**pred) for pred in result.get("predictions", [])
        ]
        uncertainty = None
        if result.get("uncertainty"):
            uncertainty = UncertaintyInfo(**result["uncertainty"])
        data_quality = None
        if result.get("data_quality"):
            data_quality = SourceDataQuality(**result["data_quality"])

        return cls(
            classifier=result.get("classifier", "source_classifier"),
            status=SourceClassificationStatus(result.get("status", "success")),
            predictions=predictions,
            top_source=result.get("top_source"),
            uncertainty=uncertainty,
            data_quality=data_quality,
            model_version=result.get("model_version"),
            processing_time_ms=result.get("processing_time_ms"),
        )
