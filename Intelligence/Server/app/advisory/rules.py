"""Configuration and private rule-layer results for advisory decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .content import (
    AQI_VARIANTS,
    SOURCE_VARIANTS,
    FORECAST_VARIANTS,
    WEATHER_VARIANTS,
    get_aqi_variants,
    get_source_variants,
    get_forecast_variants,
    get_weather_variants,
    get_gas_variants,
    get_action_text,
    get_provisional_text,
    normalize_language,
)

_GAS_PRIORITY = {"NORMAL": 0, "MODERATE": 1, "HIGH": 2, "SEVERE": 3, "CRITICAL": 4}


@dataclass(frozen=True)
class AdvisoryConfig:
    """Thresholds are centralized so deployments can tune policy explicitly."""

    standard: str = "CPCB"
    language: str = "en"
    aqi_moderate: float = 51.0
    aqi_high: float = 101.0
    aqi_severe: float = 201.0
    aqi_critical: float = 301.0
    pm25_moderate: float = 31.0
    pm25_high: float = 61.0
    pm25_severe: float = 91.0
    pm25_critical: float = 121.0
    pm10_moderate: float = 51.0
    pm10_high: float = 101.0
    pm10_severe: float = 251.0
    pm10_critical: float = 351.0
    source_confidence_minimum: float = 0.60
    forecast_confidence_minimum: float = 0.50
    forecast_change_fraction: float = 0.10
    hot_temperature: float = 32.0
    cold_temperature: float = 16.0
    humid_humidity: float = 75.0
    dry_humidity: float = 30.0

    # Gas Hazard Thresholds (Volts across RL = 10 kΩ, 5V reference)
    mq9_critical: float = 3.20
    mq9_severe: float = 2.80
    mq9_high: float = 2.40
    mq9_moderate: float = 1.80

    mq2_critical: float = 3.40
    mq2_severe: float = 3.00
    mq2_high: float = 2.50
    mq2_moderate: float = 1.80

    mq135_critical: float = 3.30
    mq135_severe: float = 2.80
    mq135_high: float = 2.40
    mq135_moderate: float = 1.80

    gas_spike_delta_v: float = 0.80
    mq_voltage_min: float = 0.100  # < 0.10V = GND rail short / sensor fault
    mq_voltage_max: float = 4.900  # > 4.90V = VCC rail short / sensor fault

    @classmethod
    def for_standard(cls, standard: str = "CPCB", language: str = "en") -> AdvisoryConfig:
        std = (standard or "CPCB").upper()
        lang = normalize_language(language)
        if std == "EPA":
            return cls(
                standard="EPA",
                language=lang,
                aqi_moderate=51.0,
                aqi_high=101.0,
                aqi_severe=151.0,
                aqi_critical=201.0,
                pm25_moderate=35.0,
                pm25_high=55.0,
                pm25_severe=150.0,
                pm25_critical=250.0,
                pm10_moderate=50.0,
                pm10_high=100.0,
                pm10_severe=250.0,
                pm10_critical=350.0,
            )
        return cls(
            standard="CPCB",
            language=lang,
            aqi_moderate=51.0,
            aqi_high=101.0,
            aqi_severe=201.0,
            aqi_critical=301.0,
            pm25_moderate=31.0,
            pm25_high=61.0,
            pm25_severe=91.0,
            pm25_critical=121.0,
            pm10_moderate=51.0,
            pm10_high=101.0,
            pm10_severe=251.0,
            pm10_critical=351.0,
        )


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
    if max_val <= min_val or value <= min_val:
        return "LOW"
    ratio = (value - min_val) / (max_val - min_val)
    if ratio < 0.33:
        return "LOW"
    elif ratio < 0.66:
        return "MODERATE"
    else:
        return "HIGH"


def current_air_quality(data: dict[str, Any], config: AdvisoryConfig, lang: str = "en") -> LayerResult:
    """Evaluate AQI and PM without calculating or fabricating AQI."""
    aqi = data.get("aqi")
    pm = data.get("pm") or {}
    aqi_value = _number(aqi, -1.0) if aqi is not None else -1.0
    pm25 = _number(pm.get("PM2_5"))
    pm10 = _number(pm.get("PM10"))
    seed = _get_seed(data)
    data_sufficiency = str(data.get("data_sufficiency") or "VALID").upper()
    is_provisional = (data_sufficiency == "INSUFFICIENT_DATA") or bool(data.get("is_provisional"))

    # Missing measurements must not be interpreted as zero pollution
    if aqi is None and pm25 <= 0.0 and pm10 <= 0.0 and ("PM2_5" not in pm or "PM10" not in pm):
        msg = get_provisional_text("PROVISIONAL_UNAVAILABLE", lang=lang)
        act = (get_action_text("VERIFY_SENSOR_TELEMETRY", lang=lang),)
        return LayerResult("NORMAL", msg, act)

    # If data sufficiency is incomplete, provide provisional particulate advice without claiming complete AQI
    if is_provisional:
        effective_val = aqi_value if aqi_value >= 0 else max(pm25, pm10)
        if effective_val >= config.aqi_critical or pm25 >= config.pm25_critical or pm10 >= config.pm10_critical:
            msg = get_provisional_text("PROVISIONAL_CRITICAL", lang=lang)
            acts = (
                get_action_text("AVOID_OUTDOOR_EXPOSURE", lang=lang),
                get_action_text("USE_RESPIRATORY_PROTECTION", lang=lang),
            )
            return LayerResult("CRITICAL", msg, acts)
        if effective_val >= config.aqi_severe or pm25 >= config.pm25_severe or pm10 >= config.pm10_severe:
            msg = get_provisional_text("PROVISIONAL_SEVERE", lang=lang)
            acts = (
                get_action_text("LIMIT_OUTDOOR_ACTIVITY", lang=lang),
                get_action_text("KEEP_WINDOWS_CLOSED", lang=lang),
            )
            return LayerResult("SEVERE", msg, acts)
        if effective_val >= config.aqi_high or pm25 >= config.pm25_high or pm10 >= config.pm10_high:
            msg = get_provisional_text("PROVISIONAL_HIGH", lang=lang)
            acts = (get_action_text("REDUCE_PROLONGED_OUTDOOR", lang=lang),)
            return LayerResult("HIGH", msg, acts)
        if effective_val >= config.aqi_moderate or pm25 >= config.pm25_moderate or pm10 >= config.pm10_moderate:
            msg = get_provisional_text("PROVISIONAL_MODERATE", lang=lang)
            acts = (get_action_text("PREFER_WELL_VENTILATED", lang=lang),)
            return LayerResult("MODERATE", msg, acts)
        msg = get_provisional_text("PROVISIONAL_NORMAL", lang=lang)
        return LayerResult("NORMAL", msg, ())

    if aqi_value >= config.aqi_critical:
        sub = _get_sub_level(aqi_value, config.aqi_critical, config.aqi_critical + 100)
        variants = get_aqi_variants("CRITICAL", sub, lang=lang)
        acts = (
            get_action_text("AVOID_OUTDOOR_EXPOSURE", lang=lang),
            get_action_text("USE_RESPIRATORY_PROTECTION", lang=lang),
        )
        return LayerResult("CRITICAL", _pick(variants, seed), acts)
    if aqi_value >= config.aqi_severe or pm25 >= config.pm25_severe or pm10 >= config.pm10_severe:
        sub = _get_sub_level(aqi_value, config.aqi_severe, config.aqi_critical)
        variants = get_aqi_variants("SEVERE", sub, lang=lang)
        acts = (
            get_action_text("LIMIT_OUTDOOR_ACTIVITY", lang=lang),
            get_action_text("KEEP_WINDOWS_CLOSED", lang=lang),
        )
        return LayerResult("SEVERE", _pick(variants, seed), acts)
    if aqi_value >= config.aqi_high or pm25 >= config.pm25_high or pm10 >= config.pm10_high:
        sub = _get_sub_level(aqi_value, config.aqi_high, config.aqi_severe)
        variants = get_aqi_variants("HIGH", sub, lang=lang)
        acts = (
            get_action_text("REDUCE_PROLONGED_OUTDOOR", lang=lang),
            get_action_text("SENSITIVE_TAKE_CARE", lang=lang),
        )
        return LayerResult("HIGH", _pick(variants, seed), acts)
    if aqi_value >= config.aqi_moderate or pm25 >= config.pm25_moderate or pm10 >= config.pm10_moderate:
        sub = _get_sub_level(aqi_value, config.aqi_moderate, config.aqi_high)
        variants = get_aqi_variants("MODERATE", sub, lang=lang)
        acts = (get_action_text("PREFER_WELL_VENTILATED", lang=lang),)
        return LayerResult("MODERATE", _pick(variants, seed), acts)

    sub = _get_sub_level(max(aqi_value, 0), 0, config.aqi_moderate)
    variants = get_aqi_variants("NORMAL", sub, lang=lang)
    return LayerResult("NORMAL", _pick(variants, seed), ())


def source_advice(data: dict[str, Any], config: AdvisoryConfig, lang: str = "en") -> LayerResult:
    source = ((data.get("predictions") or {}).get("source") or {})
    value = str(source.get("value") or "UNKNOWN").upper()
    confidence = source.get("confidence")
    seed = _get_seed(data)

    if confidence is None or _number(confidence) < config.source_confidence_minimum or value in {"UNKNOWN", "UNAVAILABLE"}:
        sub = _get_sub_level(_number(confidence), 0, config.source_confidence_minimum)
        variants = get_source_variants("UNKNOWN", sub, lang=lang)
        act = (get_action_text("USE_GENERAL_PRECAUTIONS", lang=lang),)
        return LayerResult("NORMAL", _pick(variants, seed), act)

    sub = _get_sub_level(_number(confidence), config.source_confidence_minimum, 1.0)
    variants = get_source_variants(value, sub, lang=lang)

    actions_map = {
        "TRAFFIC": (get_action_text("ACTION_TRAFFIC", lang=lang),),
        "HEAVY_DUST": (get_action_text("ACTION_HEAVY_DUST", lang=lang),),
        "CONSTRUCTION": (get_action_text("ACTION_CONSTRUCTION", lang=lang),),
        "COMBUSTION": (get_action_text("ACTION_COMBUSTION", lang=lang),),
        "BIOMASS_OR_WASTE_BURNING": (get_action_text("ACTION_BIOMASS", lang=lang),),
        "INDUSTRIAL": (get_action_text("ACTION_INDUSTRIAL", lang=lang),),
        "INDOOR_ACTIVITY": (get_action_text("ACTION_INDOOR", lang=lang),),
    }
    actions = actions_map.get(value, (get_action_text("USE_GENERAL_PRECAUTIONS", lang=lang),))

    return LayerResult("NORMAL", _pick(variants, seed), actions)


def forecast_advice(data: dict[str, Any], config: AdvisoryConfig, lang: str = "en") -> ForecastTrend:
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
        variants = get_forecast_variants("RISING", sub, lang=lang)
        acts = (get_action_text("ACTION_FORECAST_PRECAUTION", lang=lang),)
        return ForecastTrend("rising", LayerResult("HIGH", _pick(variants, seed), acts))
    if change <= -config.forecast_change_fraction:
        sub = _get_sub_level(-change, config.forecast_change_fraction, config.forecast_change_fraction + 0.5)
        variants = get_forecast_variants("FALLING", sub, lang=lang)
        return ForecastTrend("falling", LayerResult("NORMAL", _pick(variants, seed), ()))

    sub = _get_sub_level(abs(change), 0, config.forecast_change_fraction)
    variants = get_forecast_variants("STABLE", sub, lang=lang)
    return ForecastTrend("stable", LayerResult("NORMAL", _pick(variants, seed), ()))


def weather_advice(data: dict[str, Any], config: AdvisoryConfig, lang: str = "en") -> str:
    temperature = _number(data.get("temperature_C"))
    humidity = _number(data.get("humidity_pct"))
    seed = _get_seed(data)

    if temperature >= config.hot_temperature and humidity >= config.humid_humidity:
        sub = _get_sub_level(temperature * humidity, config.hot_temperature * config.humid_humidity, (config.hot_temperature + 10) * 100)
        variants = get_weather_variants("HOT_HUMID", sub, lang=lang)
        return _pick(variants, seed)
    if temperature >= config.hot_temperature:
        sub = _get_sub_level(temperature, config.hot_temperature, config.hot_temperature + 10)
        variants = get_weather_variants("HOT", sub, lang=lang)
        return _pick(variants, seed)
    if temperature <= config.cold_temperature and humidity <= config.dry_humidity:
        sub = _get_sub_level(-temperature, -config.cold_temperature, -config.cold_temperature + 15)
        variants = get_weather_variants("COLD_DRY", sub, lang=lang)
        return _pick(variants, seed)
    if temperature <= config.cold_temperature:
        sub = _get_sub_level(-temperature, -config.cold_temperature, -config.cold_temperature + 15)
        variants = get_weather_variants("COLD", sub, lang=lang)
        return _pick(variants, seed)
    if humidity >= config.humid_humidity:
        sub = _get_sub_level(humidity, config.humid_humidity, 100)
        variants = get_weather_variants("HUMID", sub, lang=lang)
        return _pick(variants, seed)
    if humidity <= config.dry_humidity:
        sub = _get_sub_level(-humidity, -config.dry_humidity, 0)
        variants = get_weather_variants("DRY", sub, lang=lang)
        return _pick(variants, seed)

    sub = _get_sub_level(temperature, config.cold_temperature, config.hot_temperature)
    variants = get_weather_variants("COMFORTABLE", sub, lang=lang)
    return _pick(variants, seed)


def _extract_voltage(raw: Any) -> float | None:
    """Safely extract voltage in volts from float, dict, or ADC reading."""
    if raw is None:
        return None
    if isinstance(raw, dict):
        raw = raw.get("voltage_V") or raw.get("voltage") or raw.get("V")
    try:
        val = float(raw)
        return val if val >= 0.0 else None
    except (TypeError, ValueError):
        return None


def gas_hazard_advice(data: dict[str, Any], config: AdvisoryConfig, lang: str = "en") -> LayerResult:
    """
    Evaluate physical gas telemetry (MQ-2, MQ-9, MQ-135) and TinyGasNet neural inference
    for acute toxic spikes, flammable leaks, and hazardous gas conditions.
    """
    # 1. Telemetry extraction (support structured dict or flat keys)
    gas_sensors = data.get("gas_sensors") or {}
    mq2_raw = gas_sensors.get("MQ2_V") or gas_sensors.get("MQ2") or data.get("mq2_v") or data.get("MQ2_V") or data.get("mq2")
    mq9_raw = gas_sensors.get("MQ9_V") or gas_sensors.get("MQ9") or data.get("mq9_v") or data.get("MQ9_V") or data.get("mq9")
    mq135_raw = gas_sensors.get("MQ135_V") or gas_sensors.get("MQ135") or data.get("mq135_v") or data.get("MQ135_V") or data.get("mq135")

    v_mq2 = _extract_voltage(mq2_raw)
    v_mq9 = _extract_voltage(mq9_raw)
    v_mq135 = _extract_voltage(mq135_raw)

    # 2. Electrical rail validation: exclude sensor faults (GND/VCC shorts) from gas calculations
    valid_mq2 = v_mq2 if (v_mq2 is not None and config.mq_voltage_min <= v_mq2 <= config.mq_voltage_max) else None
    valid_mq9 = v_mq9 if (v_mq9 is not None and config.mq_voltage_min <= v_mq9 <= config.mq_voltage_max) else None
    valid_mq135 = v_mq135 if (v_mq135 is not None and config.mq_voltage_min <= v_mq135 <= config.mq_voltage_max) else None

    # 3. Rate-of-change / Acute surge check
    delta_mq2 = _number(data.get("mq2_delta_v") or gas_sensors.get("MQ2_delta_v"))
    delta_mq9 = _number(data.get("mq9_delta_v") or gas_sensors.get("MQ9_delta_v"))
    delta_mq135 = _number(data.get("mq135_delta_v") or gas_sensors.get("MQ135_delta_v"))
    is_acute_spike = bool(
        data.get("gas_spike")
        or delta_mq2 >= config.gas_spike_delta_v
        or delta_mq9 >= config.gas_spike_delta_v
        or delta_mq135 >= config.gas_spike_delta_v
    )

    # 4. Neural inference metadata
    gas_inf = data.get("gas_inference") or ((data.get("predictions") or {}).get("gas") or {})
    gas_class = str(gas_inf.get("gas_class") or data.get("gas_class") or "CleanAir").strip()
    safety_status = str(gas_inf.get("safety_status") or data.get("safety_status") or "safe").strip().lower()
    safety_conf = _number(gas_inf.get("safety_confidence") or data.get("safety_confidence"), 0.0)

    # 5. Evaluate individual channel hazard levels
    mq9_sev = "NORMAL"
    if valid_mq9 is not None:
        if valid_mq9 >= config.mq9_critical:
            mq9_sev = "CRITICAL"
        elif valid_mq9 >= config.mq9_severe:
            mq9_sev = "SEVERE"
        elif valid_mq9 >= config.mq9_high:
            mq9_sev = "HIGH"
        elif valid_mq9 >= config.mq9_moderate:
            mq9_sev = "MODERATE"

    mq2_sev = "NORMAL"
    if valid_mq2 is not None:
        if valid_mq2 >= config.mq2_critical:
            mq2_sev = "CRITICAL"
        elif valid_mq2 >= config.mq2_severe:
            mq2_sev = "SEVERE"
        elif valid_mq2 >= config.mq2_high:
            mq2_sev = "HIGH"
        elif valid_mq2 >= config.mq2_moderate:
            mq2_sev = "MODERATE"

    mq135_sev = "NORMAL"
    if valid_mq135 is not None:
        if valid_mq135 >= config.mq135_critical:
            mq135_sev = "CRITICAL"
        elif valid_mq135 >= config.mq135_severe:
            mq135_sev = "SEVERE"
        elif valid_mq135 >= config.mq135_high:
            mq135_sev = "HIGH"
        elif valid_mq135 >= config.mq135_moderate:
            mq135_sev = "MODERATE"

    # Select leading gas channel by severity
    channel_sevs = [
        ("CO", mq9_sev, valid_mq9 or 0.0),
        ("FLAMMABLE", mq2_sev, valid_mq2 or 0.0),
        ("TOXIC_VOC", mq135_sev, valid_mq135 or 0.0),
    ]
    channel_sevs.sort(key=lambda item: (_GAS_PRIORITY.get(item[1], 0), item[2]), reverse=True)
    top_gas_type, top_sev, top_voltage = channel_sevs[0]

    # Model gas_class override / refinement
    if gas_class in ("CO", "LPG", "Smoke", "Alcohol"):
        if gas_class == "CO":
            top_gas_type = "CO"
        elif gas_class == "LPG":
            top_gas_type = "FLAMMABLE"
        elif gas_class == "Smoke":
            top_gas_type = "SMOKE"
        elif gas_class == "Alcohol":
            top_gas_type = "TOXIC_VOC"

    # 6. Neural safety hazard escalation
    if safety_status == "hazardous" and safety_conf >= 0.65:
        if _GAS_PRIORITY[top_sev] < _GAS_PRIORITY["HIGH"]:
            top_sev = "HIGH"
        elif top_sev == "HIGH" and (top_gas_type in ("CO", "FLAMMABLE") or top_voltage >= 2.6):
            top_sev = "SEVERE"

    # 7. Acute spike rate-of-change escalation
    if is_acute_spike:
        current_pri = _GAS_PRIORITY[top_sev]
        if current_pri == _GAS_PRIORITY["NORMAL"]:
            top_sev = "HIGH"
            top_gas_type = "GAS_SPIKE"
        elif current_pri == _GAS_PRIORITY["MODERATE"]:
            top_sev = "HIGH"
        elif current_pri == _GAS_PRIORITY["HIGH"]:
            top_sev = "SEVERE"
        elif current_pri == _GAS_PRIORITY["SEVERE"]:
            top_sev = "CRITICAL"

    if top_sev == "NORMAL":
        return LayerResult("NORMAL", "", ())

    # 8. Localized message and action generation
    seed = _get_seed(data)
    sub = _get_sub_level(top_voltage, 1.8, 3.5)
    variants = get_gas_variants(top_gas_type, top_sev, sub, lang=lang)
    advice_text = _pick(variants, seed)

    # Contextual protective actions based on compound and hazard tier
    actions: list[str] = []
    if top_gas_type == "CO":
        if top_sev in ("SEVERE", "CRITICAL"):
            actions = [
                get_action_text("ACTION_EVACUATE_ENCLOSED", lang=lang),
                get_action_text("ACTION_VENTILATE_GAS", lang=lang),
                get_action_text("ACTION_SEEK_MEDICAL", lang=lang),
            ]
        else:
            actions = [
                get_action_text("ACTION_VENTILATE_GAS", lang=lang),
                get_action_text("ACTION_INSPECT_GAS_APPLIANCES", lang=lang),
            ]
    elif top_gas_type == "FLAMMABLE":
        if top_sev in ("SEVERE", "CRITICAL"):
            actions = [
                get_action_text("ACTION_EVACUATE_IMMEDIATELY", lang=lang),
                get_action_text("ACTION_NO_IGNITION_OR_SWITCHES", lang=lang),
                get_action_text("ACTION_VENTILATE_GAS", lang=lang),
                get_action_text("ACTION_SHUT_GAS_SUPPLY", lang=lang),
            ]
        else:
            actions = [
                get_action_text("ACTION_VENTILATE_GAS", lang=lang),
                get_action_text("ACTION_INSPECT_GAS_APPLIANCES", lang=lang),
            ]
    elif top_gas_type == "TOXIC_VOC":
        if top_sev in ("SEVERE", "CRITICAL"):
            actions = [
                get_action_text("ACTION_MOVE_AWAY_CHEMICAL", lang=lang),
                get_action_text("ACTION_STRONG_VENTILATION", lang=lang),
                get_action_text("ACTION_AVOID_FUMES", lang=lang),
            ]
        else:
            actions = [
                get_action_text("ACTION_STRONG_VENTILATION", lang=lang),
                get_action_text("PREFER_WELL_VENTILATED", lang=lang),
            ]
    elif top_gas_type == "SMOKE":
        if top_sev in ("SEVERE", "CRITICAL"):
            actions = [
                get_action_text("ACTION_CHECK_FIRE", lang=lang),
                get_action_text("ACTION_MOVE_AWAY_SMOKE", lang=lang),
                get_action_text("USE_RESPIRATORY_PROTECTION", lang=lang),
            ]
        else:
            actions = [
                get_action_text("ACTION_MOVE_AWAY_SMOKE", lang=lang),
                get_action_text("PREFER_WELL_VENTILATED", lang=lang),
            ]
    else:  # GAS_SPIKE / general
        if top_sev in ("SEVERE", "CRITICAL"):
            actions = [
                get_action_text("ACTION_EVACUATE_IMMEDIATELY", lang=lang),
                get_action_text("ACTION_VENTILATE_GAS", lang=lang),
                get_action_text("ACTION_NO_IGNITION_OR_SWITCHES", lang=lang),
            ]
        else:
            actions = [
                get_action_text("ACTION_VENTILATE_GAS", lang=lang),
                get_action_text("ACTION_INSPECT_GAS_APPLIANCES", lang=lang),
            ]

    return LayerResult(severity=top_sev, advice=advice_text, actions=tuple(actions))
