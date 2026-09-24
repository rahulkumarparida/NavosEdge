"""Deterministic multi-layer advisory engine."""

from __future__ import annotations

from typing import Any

from .rules import AdvisoryConfig, LayerResult, current_air_quality, forecast_advice, source_advice, weather_advice
from .schemas import AdvisoryResult

_PRIORITY = {"NORMAL": 0, "MODERATE": 1, "HIGH": 2, "SEVERE": 3, "CRITICAL": 4}


class AdvisoryEngine:
    """Evaluate an existing intelligence result without invoking models."""

    def __init__(self, config: AdvisoryConfig | None = None) -> None:
        self.config = config or AdvisoryConfig()

    def evaluate(self, data: dict[str, Any]) -> dict[str, Any]:
        """Return exactly severity, advice, actions, and weather_advice."""
        air = current_air_quality(data, self.config)
        source = source_advice(data, self.config)
        forecast = forecast_advice(data, self.config)
        weather = weather_advice(data, self.config)

        pollution_layers = (air, source, forecast.layer)
        winning = max(pollution_layers, key=lambda layer: _PRIORITY.get(layer.severity, 0))
        actions = _merge_actions(pollution_layers)
        advice = _combine_advice(winning, source, forecast.layer)
        return AdvisoryResult(
            severity=winning.severity,
            advice=advice,
            actions=actions,
            weather_advice=weather,
        ).model_dump(mode="json")


def _merge_actions(layers: tuple[LayerResult, ...]) -> list[str]:
    actions: list[str] = []
    for layer in layers:
        for action in layer.actions:
            if action not in actions:
                actions.append(action)
    return actions


def _combine_advice(winning: LayerResult, source: LayerResult, forecast: LayerResult) -> str:
    messages: list[str] = []
    for layer in (winning, source, forecast):
        if layer.advice and layer.advice not in messages:
            messages.append(layer.advice)
    return " ".join(messages)
