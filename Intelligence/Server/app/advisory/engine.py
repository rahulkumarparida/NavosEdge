"""Deterministic multi-layer advisory engine."""

from __future__ import annotations

from typing import Any

from .rules import (
    AdvisoryConfig,
    LayerResult,
    current_air_quality,
    forecast_advice,
    gas_hazard_advice,
    source_advice,
    weather_advice,
)
from .schemas import AdvisoryResult

_PRIORITY = {"NORMAL": 0, "MODERATE": 1, "HIGH": 2, "SEVERE": 3, "CRITICAL": 4}


class AdvisoryEngine:
    """Evaluate an existing intelligence result without invoking models."""

    def __init__(
        self,
        config: AdvisoryConfig | None = None,
        standard: str | None = None,
        language: str | None = None,
    ) -> None:
        if config is not None:
            self.config = config
        else:
            self.config = AdvisoryConfig.for_standard(standard or "CPCB", language=language or "en")

    def evaluate(self, data: dict[str, Any], language: str | None = None) -> dict[str, Any]:
        """Return exactly severity, advice, actions, and weather_advice."""
        cfg = self.config
        effective_lang = language or data.get("language") or data.get("lang") or cfg.language or "en"
        data_std = data.get("standard")

        if (data_std and str(data_std).upper() != cfg.standard) or (effective_lang != cfg.language):
            cfg = AdvisoryConfig.for_standard(str(data_std or cfg.standard), language=effective_lang)

        air = current_air_quality(data, cfg, lang=effective_lang)
        source = source_advice(data, cfg, lang=effective_lang)
        forecast = forecast_advice(data, cfg, lang=effective_lang)
        gas = gas_hazard_advice(data, cfg, lang=effective_lang)
        weather = weather_advice(data, cfg, lang=effective_lang)

        pollution_layers = (air, source, forecast.layer, gas)
        winning = max(pollution_layers, key=lambda layer: _PRIORITY.get(layer.severity, 0))

        gas_severe = gas.severity in ("SEVERE", "CRITICAL")
        ordered_layers = (gas, air, source, forecast.layer) if gas_severe else (air, source, forecast.layer, gas)

        actions = _merge_actions(ordered_layers, gas_priority=gas_severe)
        advice = _combine_advice(winning, air, source, forecast.layer, gas, gas_priority=gas_severe)

        return AdvisoryResult(
            severity=winning.severity,
            advice=advice,
            actions=actions,
            weather_advice=weather,
        ).model_dump(mode="json")


def _merge_actions(layers: tuple[LayerResult, ...], gas_priority: bool = False) -> list[str]:
    actions: list[str] = []
    # If an acute toxic or flammable gas hazard is present, suppress contradictory advice
    # like sealing windows which could lead to lethal asphyxiation or explosion.
    contradictory_snippets = (
        "keep windows closed",
        "खिड़कियाँ बंद",
        "ଝରକା କବାଟ ବନ୍ଦ",
    )
    for layer in layers:
        for action in layer.actions:
            if gas_priority and any(s in action.lower() for s in contradictory_snippets):
                continue
            if action not in actions:
                actions.append(action)
    return actions


def _combine_advice(
    winning: LayerResult,
    air: LayerResult,
    source: LayerResult,
    forecast: LayerResult,
    gas: LayerResult,
    gas_priority: bool = False,
) -> str:
    messages: list[str] = []
    if gas_priority and gas.advice:
        messages.append(gas.advice)
    for layer in (winning, air, source, forecast, gas):
        if layer.advice and layer.advice not in messages:
            messages.append(layer.advice)
    return " ".join(messages)
