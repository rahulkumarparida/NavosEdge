"""Deterministic multi-layer advisory engine following 11-step decision order."""

from __future__ import annotations

from typing import Any

from .rules import (
    AdvisoryConfig,
    LayerResult,
    current_air_quality,
    forecast_advice,
    source_advice,
    weather_advice,
)
from .schemas import AdvisoryResult

_PRIORITY = {"NORMAL": 0, "MODERATE": 1, "HIGH": 2, "SEVERE": 3, "CRITICAL": 4}


class AdvisoryEngine:
    """Evaluate an existing intelligence result deterministically without invoking models."""

    def __init__(self, config: AdvisoryConfig | None = None) -> None:
        self.config = config or AdvisoryConfig()
        self._prev_aqi: float | None = None
        self._prev_sub: str | None = None

    def evaluate(self, data: dict[str, Any]) -> dict[str, Any]:
        """Execute the 11-step decision order to produce AdvisoryResult."""
        # Step 1: Validate sensor snapshot
        if not isinstance(data, dict):
            return AdvisoryResult(
                severity="NORMAL",
                advice="Sensor data is unavailable. Check the connection.",
                actions=["Check sensor connection."],
                weather_advice="",
            ).model_dump(mode="json")

        # Step 2: Health & freshness check
        is_valid = data.get("is_valid", True)
        status = str(data.get("status", "")).lower()
        pm_dict = data.get("pm") or {}
        has_pm = bool(isinstance(pm_dict, dict) and (pm_dict.get("PM2_5") is not None or pm_dict.get("PM10") is not None))
        aqi_raw = data.get("aqi")
        has_aqi = aqi_raw is not None and aqi_raw != -1.0

        if is_valid is False or status in ("invalid", "corrupted", "stale", "not_available") or (not has_aqi and not has_pm):
            return AdvisoryResult(
                severity="NORMAL",
                advice="Sensor data is unavailable. Check the connection.",
                actions=["Check sensor connection."],
                weather_advice="",
            ).model_dump(mode="json")

        # Step 3, 5, 6, 9: Evaluate current air quality with sub-bands and hysteresis
        air = current_air_quality(
            data,
            self.config,
            prev_aqi=self._prev_aqi,
            prev_sub=self._prev_sub,
        )
        if has_aqi:
            try:
                self._prev_aqi = float(aqi_raw)
                self._prev_sub = air.sub_level
            except (ValueError, TypeError):
                pass

        # Step 4 & 8: Source classification pattern, confidence, and source-specific selection
        source = source_advice(
            data,
            self.config,
            aqi_severity=air.severity,
            sub_level=air.sub_level,
        )

        # Step 7: Trend evaluation (RISING, FALLING, STABLE)
        forecast = forecast_advice(data, self.config)

        # Separate weather recommendations
        weather = weather_advice(data, self.config)

        # Resolve winning pollution severity
        pollution_layers = (air, source, forecast.layer)
        winning = max(pollution_layers, key=lambda layer: _PRIORITY.get(layer.severity, 0))

        # Step 10: Deduplicate and prioritize actions (max 3 actions, <35 chars)
        actions = _merge_and_prioritize_actions(pollution_layers, winning.severity)

        # Step 11: Return AdvisoryResult
        advice = _combine_advice(winning, source, forecast.layer)
        return AdvisoryResult(
            severity=winning.severity,
            advice=advice,
            actions=actions,
            weather_advice=weather,
        ).model_dump(mode="json")


def _merge_and_prioritize_actions(layers: tuple[LayerResult, ...], winning_severity: str) -> list[str]:
    collected: list[str] = []
    for layer in layers:
        for action in layer.actions:
            trimmed = action.strip()
            if len(trimmed) > 34:
                trimmed = trimmed[:34].rstrip()
            if trimmed and trimmed not in collected:
                collected.append(trimmed)

    # Prioritize critical respiratory and exposure mitigations if high severity
    if winning_severity in ("HIGH", "SEVERE", "CRITICAL") and len(collected) > 1:
        def priority_key(act: str) -> int:
            al = act.lower()
            if "n95" in al or "respirat" in al or "mask" in al:
                return 0
            if "avoid" in al or "indoors" in al or "seal" in al:
                return 1
            if "roads" in al or "traffic" in al or "dust" in al or "smoke" in al:
                return 2
            if "purifier" in al or "filter" in al or "ventilat" in al:
                return 3
            return 4
        collected.sort(key=priority_key)

    # Max 3 actions
    return collected[:3]


def _combine_advice(winning: LayerResult, source: LayerResult, forecast: LayerResult) -> str:
    messages: list[str] = []
    for layer in (winning, source, forecast):
        if layer.advice and layer.advice not in messages:
            messages.append(layer.advice)
    return " ".join(messages)
