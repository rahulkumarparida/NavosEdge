"""Configuration and private rule-layer results for advisory decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .content import AQI_VARIANTS, SOURCE_VARIANTS, FORECAST_VARIANTS, WEATHER_VARIANTS

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


@dataclass(frozen=True)
class LayerResult:
    severity: str = "NORMAL"
    advice: str = ""
    actions: tuple[str, ...] = ()


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
    # Simple deterministic seed
    return int(abs(aqi * 100 + pm25 * 10 + temp * 10 + hum))

def _pick(variants: list[str], seed: int) -> str:
    if not variants:
        return ""
    return variants[seed % len(variants)]

def _get_sub_level(value: float, min_val: float, max_val: float) -> str:
    if max_val <= min_val or value <= min_val: return "LOW"
    ratio = (value - min_val) / (max_val - min_val)
    if ratio < 0.33: return "LOW"
    elif ratio < 0.66: return "MODERATE"
    else: return "HIGH"

def current_air_quality(data: dict[str, Any], config: AdvisoryConfig) -> LayerResult:
    """Evaluate AQI and PM without calculating or fabricating AQI."""
    aqi = data.get("aqi")
    pm = data.get("pm") or {}
    aqi_value = _number(aqi, -1.0) if aqi is not None else -1.0
    pm25 = _number(pm.get("PM2_5"))
    pm10 = _number(pm.get("PM10"))
    seed = _get_seed(data)

    if aqi_value >= config.aqi_critical:
        sub = _get_sub_level(aqi_value, config.aqi_critical, config.aqi_critical + 50)
        variants = AQI_VARIANTS["CRITICAL"][sub]
        return LayerResult("CRITICAL", _pick(variants, seed), ("Avoid outdoor exposure.", "Use suitable respiratory protection."))
    if aqi_value >= config.aqi_severe or pm25 >= config.pm25_severe or pm10 >= config.pm10_severe:
        sub = _get_sub_level(aqi_value, config.aqi_severe, config.aqi_critical)
        variants = AQI_VARIANTS["SEVERE"][sub]
        return LayerResult("SEVERE", _pick(variants, seed), ("Limit outdoor activity.", "Keep windows closed where practical."))
    if aqi_value >= config.aqi_high or pm25 >= config.pm25_high or pm10 >= config.pm10_high:
        sub = _get_sub_level(aqi_value, config.aqi_high, config.aqi_severe)
        variants = AQI_VARIANTS["HIGH"][sub]
        return LayerResult("HIGH", _pick(variants, seed), ("Reduce prolonged outdoor activity.", "Sensitive people should take extra care."))
    if aqi_value >= config.aqi_moderate or pm25 >= config.pm25_moderate or pm10 >= config.pm10_moderate:
        sub = _get_sub_level(aqi_value, config.aqi_moderate, config.aqi_high)
        variants = AQI_VARIANTS["MODERATE"][sub]
        return LayerResult("MODERATE", _pick(variants, seed), ("Prefer well-ventilated, lower-pollution areas." ,))
    
    sub = _get_sub_level(max(aqi_value, 0), 0, config.aqi_moderate)
    variants = AQI_VARIANTS["NORMAL"][sub]
    return LayerResult("NORMAL", _pick(variants, seed), ())


def source_advice(data: dict[str, Any], config: AdvisoryConfig) -> LayerResult:
    source = ((data.get("predictions") or {}).get("source") or {})
    value = str(source.get("value") or "UNKNOWN").upper()
    confidence = source.get("confidence")
    seed = _get_seed(data)
    
    if confidence is None or _number(confidence) < config.source_confidence_minimum or value in {"UNKNOWN", "UNAVAILABLE"}:
        sub = _get_sub_level(_number(confidence), 0, config.source_confidence_minimum)
        variants = SOURCE_VARIANTS.get("UNKNOWN", SOURCE_VARIANTS["MIXED"])[sub]
        return LayerResult("NORMAL", _pick(variants, seed), ("Use general pollution precautions.",))
    
    sub = _get_sub_level(_number(confidence), config.source_confidence_minimum, 1.0)
    variants = SOURCE_VARIANTS.get(value)
    if not variants:
        variants = SOURCE_VARIANTS["MIXED"]
    
    actions_map = {
        "TRAFFIC": ("Reduce exposure near busy roads when practical.",),
        "HEAVY_DUST": ("Avoid visibly dusty areas and use respiratory protection if needed.",),
        "CONSTRUCTION": ("Avoid active dust-generating areas when practical.",),
        "COMBUSTION": ("Avoid smoke and poorly ventilated combustion areas.",),
        "BIOMASS_OR_WASTE_BURNING": ("Avoid smoke and keep indoor air protected.",),
        "INDUSTRIAL": ("Limit exposure near industrial zones.",),
        "INDOOR_ACTIVITY": ("Improve indoor ventilation.",),
    }
    actions = actions_map.get(value, ("Use general pollution precautions.",))
    
    return LayerResult("NORMAL", _pick(variants[sub], seed), actions)


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
        return ForecastTrend("rising", LayerResult("HIGH", _pick(FORECAST_VARIANTS["RISING"][sub], seed), ("Take precautions before the forecast period.",)))
    if change <= -config.forecast_change_fraction:
        sub = _get_sub_level(-change, config.forecast_change_fraction, config.forecast_change_fraction + 0.5)
        return ForecastTrend("falling", LayerResult("NORMAL", _pick(FORECAST_VARIANTS["FALLING"][sub], seed), ()))
    
    sub = _get_sub_level(abs(change), 0, config.forecast_change_fraction)
    return ForecastTrend("stable", LayerResult("NORMAL", _pick(FORECAST_VARIANTS["STABLE"][sub], seed), ()))


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
