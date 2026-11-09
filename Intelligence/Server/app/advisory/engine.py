"""Deterministic multi-layer advisory engine."""

from __future__ import annotations

from typing import Any

from .rules import (
    AdvisoryConfig,
    LayerResult,
    build_fusion_advice,
    build_three_pillar_actions,
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

        # Generate cohesive Cause -> Forecast -> Action fusion advice
        advice = build_fusion_advice(data, cfg, air, source, forecast, gas, winning.severity, lang=effective_lang)

        # Generate structured 3-Pillar categorized actions ([ACTIVITY], [HOME], [HEALTH], [FORECAST/GAS])
        actions = build_three_pillar_actions(data, cfg, winning.severity, gas, forecast, source, lang=effective_lang)

        return AdvisoryResult(
            severity=winning.severity,
            advice=advice,
            actions=actions,
            weather_advice=weather,
        ).model_dump(mode="json")
