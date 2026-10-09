"""Convert internal processing results into the minimal public response."""

from __future__ import annotations

from typing import Any

from app.schemas.forecast import ForecastReliability
from app.advisory import AdvisoryEngine
from app.schemas.inference import InferenceResult
from app.schemas.intelligence import IntelligenceResult, PredictionOutput
from app.advisory.schemas import AdvisoryResult
from app.schemas.pipeline import PipelineResults
from app.schemas.sensor import SensorPayload


from app.aqi.calculator import AQICalculator


class AqiProcessor:
    """AQI processor using regulatory standard breakpoint calculation."""

    def __init__(self, standard: str = "CPCB") -> None:
        self.calculator = AQICalculator(standard=standard)

    def calculate(self, pm: dict[str, float]) -> float | None:
        if not pm or "PM2_5" not in pm or "PM10" not in pm:
            return None
        res = self.calculator.calculate(
            pm1_0=pm.get("PM1_0", 0.0),
            pm2_5=pm.get("PM2_5", 0.0),
            pm10=pm.get("PM10", 0.0),
        )
        return res.aqi


def _source_prediction(pipeline: PipelineResults) -> PredictionOutput:
    result = pipeline.source_classification
    if result is None or not result.predictions:
        return PredictionOutput(value="unavailable", confidence=None)
    top = result.predictions[0]
    return PredictionOutput(value=top.source, confidence=top.confidence)


def _forecast_confidence(reliability: str | None) -> float | None:
    # This is a public normalization of the existing reliability enum, not a
    # new model confidence calculation.
    return {
        ForecastReliability.HIGH.value: 1.0,
        ForecastReliability.MEDIUM.value: 0.75,
        ForecastReliability.LOW.value: 0.5,
        ForecastReliability.UNAVAILABLE.value: 0.0,
    }.get(reliability)


def _forecast_prediction(forecast: Any) -> PredictionOutput:
    if forecast is None:
        return PredictionOutput(
            value={"status": "unavailable", "PM1_0": [], "PM2_5": [], "PM10": []},
            confidence=None,
        )
    channels: dict[str, list[float]] = {}
    for channel in getattr(forecast, "channels", []) or []:
        channels[channel.channel] = channel.predicted_values
    return PredictionOutput(
        value={
            "status": getattr(forecast.status, "value", forecast.status),
            "PM1_0": channels.get("PM1_0", []),
            "PM2_5": channels.get("PM2_5", []),
            "PM10": channels.get("PM10", []),
        },
        confidence=_forecast_confidence(
            getattr(forecast.reliability, "value", forecast.reliability)
        ),
    )


def aggregate_intelligence(
    payload: SensorPayload,
    pipeline: PipelineResults,
    inference: InferenceResult,
    forecast: Any = None,
) -> IntelligenceResult:
    """Build the only public intelligence result from internal module outputs."""
    pm = payload.particulate_matter
    result = IntelligenceResult(
        aqi=AqiProcessor().calculate({
            "PM1_0": pm.PM1_0,
            "PM2_5": pm.PM2_5,
            "PM10": pm.PM10,
        }),
        pm={"PM1_0": pm.PM1_0, "PM2_5": pm.PM2_5, "PM10": pm.PM10},
        temperature_C=payload.environment.temperature_C,
        humidity_pct=payload.environment.humidity_pct,
        predictions= {
            "source": _source_prediction(pipeline),
            "forecast": _forecast_prediction(forecast),
        },
        advisory={
            "severity": "NORMAL",
            "advice": "",
            "actions": [],
            "weather_advice": "",
        },
    )
    advisory_input = result.model_dump(mode="python", exclude={"advisory"})
    result.advisory = AdvisoryResult.model_validate(
        AdvisoryEngine().evaluate(advisory_input)
    )
    return result
