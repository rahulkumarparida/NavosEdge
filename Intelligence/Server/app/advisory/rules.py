"""Configuration and private rule-layer results for advisory decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .content import (
    AQI_ACTIONS,
    AQI_VARIANTS,
    FORECAST_VARIANTS,
    SOURCE_ACTIONS,
    SOURCE_VARIANTS,
    TREND_ACTIONS,
    WEATHER_VARIANTS,
)

@dataclass(frozen=True)
class AdvisoryConfig:
    """Thresholds are centralized so deployments can tune policy explicitly."""

    aqi_moderate: float = 51.0
    aqi_high: float = 101.0
    aqi_severe: float = 151.0
    aqi_critical: float = 201.0
    pm25_moderate: float = 35.0
    pm25_high: float = 55.0
    pm25_severe: float = 150.0
    pm10_moderate: float = 50.0
    pm10_high: float = 100.0
    pm10_severe: float = 250.0
    source_confidence_minimum: float = 0.60
    forecast_confidence_minimum: float = 0.50
    forecast_change_fraction: float = 0.10
    hot_temperature: float = 32.0
    cold_temperature: float = 16.0
    humid_humidity: float = 75.0
    dry_humidity: float = 30.0
    hysteresis_margin: float = 3.0


@dataclass(frozen=True)
class LayerResult:
    severity: str = "NORMAL"
    advice: str = ""
    actions: tuple[str, ...] = ()
    sub_level: str = "LOW"


@dataclass(frozen=True)
class ForecastTrend:
    direction: str = "unknown"
    layer: LayerResult = field(default_factory=LayerResult)


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

def _get_seed(data: dict[str, Any]) -> int:
    aqi = _number(data.get("aqi"))
    pm = data.get("pm") or {}
    pm25 = _number(pm.get("PM2_5"))
    temp = _number(data.get("temperature_C"))
    hum = _number(data.get("humidity_pct"))
    seq = int(_number(data.get("sample_seq"), 0))
    ts = data.get("timestamp")
    time_offset = 0
    if isinstance(ts, str) and len(ts) >= 16:
        try:
            time_offset = int(ts[14:16])
        except Exception:
            time_offset = 0
    elif hasattr(ts, "minute"):
        time_offset = getattr(ts, "minute", 0)
    return int(abs(aqi * 100 + pm25 * 10 + temp * 10 + hum + seq + time_offset))

def _pick(variants: list[str], seed: int) -> str:
    if not variants:
        return ""
    return variants[seed % len(variants)]

def _get_sub_level(
    value: float,
    min_val: float,
    max_val: float,
    prev_val: float | None = None,
    prev_sub: str | None = None,
    hysteresis_margin: float = 3.0,
) -> str:
    if max_val <= min_val or value <= min_val:
        raw_sub = "LOW"
    else:
        ratio = (value - min_val) / (max_val - min_val)
        if ratio < 0.33:
            raw_sub = "LOW"
        elif ratio < 0.66:
            raw_sub = "MODERATE"
        else:
            raw_sub = "HIGH"

    if prev_val is not None and prev_sub in ("LOW", "MODERATE", "HIGH"):
        if abs(value - prev_val) < hysteresis_margin:
            return prev_sub

    return raw_sub

def current_air_quality(
    data: dict[str, Any],
    config: AdvisoryConfig,
    prev_aqi: float | None = None,
    prev_sub: str | None = None,
) -> LayerResult:
    """Evaluate AQI and PM with CPCB thresholds, hysteresis, and sub-band actions."""
    aqi = data.get("aqi")
    pm = data.get("pm") or {}
    aqi_value = _number(aqi, -1.0) if aqi is not None else -1.0
    pm25 = _number(pm.get("PM2_5"))
    pm10 = _number(pm.get("PM10"))
    seed = _get_seed(data)

    if aqi_value >= config.aqi_critical:
        severity = "CRITICAL"
        sub = _get_sub_level(aqi_value, config.aqi_critical, config.aqi_critical + 50, prev_aqi, prev_sub, config.hysteresis_margin)
    elif aqi_value >= config.aqi_severe or pm25 >= config.pm25_severe or pm10 >= config.pm10_severe:
        severity = "SEVERE"
        sub = _get_sub_level(aqi_value, config.aqi_severe, config.aqi_critical, prev_aqi, prev_sub, config.hysteresis_margin)
    elif aqi_value >= config.aqi_high or pm25 >= config.pm25_high or pm10 >= config.pm10_high:
        severity = "HIGH"
        sub = _get_sub_level(aqi_value, config.aqi_high, config.aqi_severe, prev_aqi, prev_sub, config.hysteresis_margin)
    elif aqi_value >= config.aqi_moderate or pm25 >= config.pm25_moderate or pm10 >= config.pm10_moderate:
        severity = "MODERATE"
        sub = _get_sub_level(aqi_value, config.aqi_moderate, config.aqi_high, prev_aqi, prev_sub, config.hysteresis_margin)
    else:
        severity = "NORMAL"
        sub = _get_sub_level(max(aqi_value, 0), 0, config.aqi_moderate, prev_aqi, prev_sub, config.hysteresis_margin)

    variants = AQI_VARIANTS[severity][sub]
    advice = _pick(variants, seed)

    # Specific pollutant emphasis when elevated
    if severity in ("HIGH", "SEVERE", "CRITICAL"):
        if pm25 > 90 and pm25 > pm10 * 0.7:
            advice += " Fine particles (PM2.5) are especially elevated."
        elif pm10 > 180 and pm10 > pm25 * 2.0:
            advice += " Coarse dust (PM10) is heavily elevated."

    sub_idx = 0 if sub == "LOW" else (1 if sub == "MODERATE" else 2)
    actions_options = AQI_ACTIONS.get(severity, [()])
    act_idx = (sub_idx + (seed % len(actions_options))) % len(actions_options)
    actions = actions_options[act_idx]

    return LayerResult(severity, advice, actions, sub_level=sub)


def source_advice(
    data: dict[str, Any],
    config: AdvisoryConfig,
    aqi_severity: str = "NORMAL",
    sub_level: str = "LOW",
) -> LayerResult:
    source = ((data.get("predictions") or {}).get("source") or {})
    value = str(source.get("value") or "UNKNOWN").upper()
    confidence = source.get("confidence")
    seed = _get_seed(data)
    sub_idx = 0 if sub_level == "LOW" else (1 if sub_level == "MODERATE" else 2)

    if confidence is None or _number(confidence) < config.source_confidence_minimum or value in {"UNKNOWN", "UNAVAILABLE"}:
        conf_sub = _get_sub_level(_number(confidence), 0, config.source_confidence_minimum)
        variants = SOURCE_VARIANTS.get("UNKNOWN", SOURCE_VARIANTS["MIXED"])[conf_sub]
        act_dict = SOURCE_ACTIONS.get("UNKNOWN", {})
        act_sev_list = act_dict.get(aqi_severity, act_dict.get("NORMAL", [("Use general pollution precautions.",)]))
        actions = act_sev_list[sub_idx % len(act_sev_list)]
        return LayerResult("NORMAL", _pick(variants, seed), actions, sub_level=conf_sub)

    conf_sub = _get_sub_level(_number(confidence), config.source_confidence_minimum, 1.0)
    variants = SOURCE_VARIANTS.get(value)
    if not variants:
        variants = SOURCE_VARIANTS["MIXED"]

    src_dict = SOURCE_ACTIONS.get(value, SOURCE_ACTIONS["MIXED"])
    src_sev_list = src_dict.get(aqi_severity, src_dict.get("NORMAL", [("Use general pollution precautions.",)]))
    act_idx = (sub_idx + (seed % len(src_sev_list))) % len(src_sev_list)
    actions = src_sev_list[act_idx]

    return LayerResult("NORMAL", _pick(variants[conf_sub], seed), actions, sub_level=conf_sub)


def forecast_advice(data: dict[str, Any], config: AdvisoryConfig) -> ForecastTrend:
    forecast = ((data.get("predictions") or {}).get("forecast") or {})
    confidence = forecast.get("confidence")
    values = forecast.get("value")
    seed = _get_seed(data)

    if not isinstance(values, dict) or confidence is None or _number(confidence) < config.forecast_confidence_minimum:
        return ForecastTrend()
    current = _number((data.get("pm") or {}).get("PM2_5"))
    series = values.get("PM2_5")
    if not isinstance(series, list) or not series:
        return ForecastTrend()
    future = _number(series[-1], current)
    if current <= 0:
        return ForecastTrend()

    change = (future - current) / current

    if change >= config.forecast_change_fraction:
        sub = _get_sub_level(change, config.forecast_change_fraction, config.forecast_change_fraction + 0.5)
        rising_actions = TREND_ACTIONS.get("RISING", ("Take precautions before the forecast period.",))
        act = (rising_actions[seed % len(rising_actions)],)
        return ForecastTrend("rising", LayerResult("HIGH", _pick(FORECAST_VARIANTS["RISING"][sub], seed), act, sub_level=sub))
    if change <= -config.forecast_change_fraction:
        sub = _get_sub_level(-change, config.forecast_change_fraction, config.forecast_change_fraction + 0.5)
        falling_actions = TREND_ACTIONS.get("FALLING", ())
        act = (falling_actions[seed % len(falling_actions)],) if falling_actions else ()
        return ForecastTrend("falling", LayerResult("NORMAL", _pick(FORECAST_VARIANTS["FALLING"][sub], seed), act, sub_level=sub))

    sub = _get_sub_level(abs(change), 0, config.forecast_change_fraction)
    return ForecastTrend("stable", LayerResult("NORMAL", _pick(FORECAST_VARIANTS["STABLE"][sub], seed), (), sub_level=sub))


def weather_advice(data: dict[str, Any], config: AdvisoryConfig) -> str:
    temperature = _number(data.get("temperature_C"))
    humidity = _number(data.get("humidity_pct"))
    seed = _get_seed(data)
    
    if temperature >= config.hot_temperature and humidity >= config.humid_humidity:
        sub = _get_sub_level(temperature * humidity, config.hot_temperature * config.humid_humidity, (config.hot_temperature + 10) * 100)
        return _pick(WEATHER_VARIANTS["HOT_HUMID"][sub], seed)
    if temperature >= config.hot_temperature:
        sub = _get_sub_level(temperature, config.hot_temperature, config.hot_temperature + 10)
        return _pick(WEATHER_VARIANTS["HOT"][sub], seed)
    if temperature <= config.cold_temperature and humidity <= config.dry_humidity:
        sub = _get_sub_level(-temperature, -config.cold_temperature, -config.cold_temperature + 15)
        return _pick(WEATHER_VARIANTS["COLD_DRY"][sub], seed)
    if temperature <= config.cold_temperature:
        sub = _get_sub_level(-temperature, -config.cold_temperature, -config.cold_temperature + 15)
        return _pick(WEATHER_VARIANTS["COLD"][sub], seed)
    if humidity >= config.humid_humidity:
        sub = _get_sub_level(humidity, config.humid_humidity, 100)
        return _pick(WEATHER_VARIANTS["HUMID"][sub], seed)
    if humidity <= config.dry_humidity:
        sub = _get_sub_level(-humidity, -config.dry_humidity, 0)
        return _pick(WEATHER_VARIANTS["DRY"][sub], seed)
    
    sub = _get_sub_level(temperature, config.cold_temperature, config.hot_temperature)
    return _pick(WEATHER_VARIANTS["COMFORTABLE"][sub], seed)
