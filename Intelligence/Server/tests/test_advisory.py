import pytest

from app.advisory import AdvisoryEngine


def reading(
    *,
    aqi=20,
    pm25=12.0,
    pm10=25.0,
    temperature=22.0,
    humidity=50.0,
    source="UNKNOWN",
    source_confidence=None,
    forecast=None,
    forecast_confidence=None,
):
    return {
        "aqi": aqi,
        "pm": {"PM1_0": min(5.0, pm25), "PM2_5": pm25, "PM10": pm10},
        "temperature_C": temperature,
        "humidity_pct": humidity,
        "predictions": {
            "source": {"value": source, "confidence": source_confidence},
            "forecast": {"value": forecast, "confidence": forecast_confidence},
        },
    }


def test_normal_air_quality_has_concise_public_shape():
    result = AdvisoryEngine().evaluate(reading())
    assert set(result) == {"severity", "advice", "actions", "weather_advice"}
    assert result["severity"] == "NORMAL"
    assert result["actions"] == ["Use general pollution precautions."]
    assert "temperature" not in result["advice"].lower()


def test_high_pollution_takes_priority():
    result = AdvisoryEngine().evaluate(reading(aqi=142, pm25=82.4, pm10=141.3))
    assert result["severity"] == "HIGH"
    assert result["actions"]


def test_severe_and_critical_levels_are_distinct():
    # Under CPCB defaults: Poor (201-300) -> SEVERE, Very Poor/Severe (>300) -> CRITICAL
    assert AdvisoryEngine().evaluate(reading(aqi=250, pm25=105, pm10=300))["severity"] == "SEVERE"
    assert AdvisoryEngine().evaluate(reading(aqi=350, pm25=185, pm10=390))["severity"] == "CRITICAL"

    # Explicit EPA standard preserves EPA thresholds (Unhealthy 151-200 -> SEVERE, Very Unhealthy 201+ -> CRITICAL)
    epa_engine = AdvisoryEngine(standard="EPA")
    assert epa_engine.evaluate(reading(aqi=160, pm25=160, pm10=260))["severity"] == "SEVERE"
    assert epa_engine.evaluate(reading(aqi=220, pm25=160, pm10=260))["severity"] == "CRITICAL"


def test_high_confidence_source_adds_source_aware_action():
    result = AdvisoryEngine().evaluate(reading(source="TRAFFIC", source_confidence=0.78))
    assert "traffic" in result["advice"].lower()
    assert any("roads" in action for action in result["actions"])


def test_low_confidence_source_is_not_treated_as_confirmed():
    result = AdvisoryEngine().evaluate(reading(source="COMBUSTION", source_confidence=0.2))
    assert "source" in result["advice"].lower()
    assert all("smoke" not in action.lower() for action in result["actions"])


def test_rising_forecast_adds_precautionary_advice():
    result = AdvisoryEngine().evaluate(
        reading(
            pm25=50,
            pm10=80,
            forecast={"PM1_0": [10, 15], "PM2_5": [55, 70], "PM10": [90, 120]},
            forecast_confidence=0.71,
        )
    )
    assert "worsen" in result["advice"] or "increase" in result["advice"]
    assert "precautions" in " ".join(result["actions"])


def test_falling_forecast_reports_improvement():
    result = AdvisoryEngine().evaluate(
        reading(
            pm25=100,
            pm10=180,
            forecast={"PM1_0": [20, 10], "PM2_5": [80, 60], "PM10": [150, 100]},
            forecast_confidence=0.8,
        )
    )
    assert "improve" in result["advice"]


def test_missing_or_low_confidence_forecast_is_ignored():
    missing = AdvisoryEngine().evaluate(reading(forecast=None, forecast_confidence=None))
    low = AdvisoryEngine().evaluate(
        reading(forecast={"PM2_5": [100, 200]}, forecast_confidence=0.2)
    )
    assert missing["severity"] == "NORMAL"
    assert low["severity"] == "NORMAL"
    assert "increase" not in low["advice"]


def test_conflicting_conditions_keep_weather_separate():
    result = AdvisoryEngine().evaluate(
        reading(
            aqi=180,
            pm25=160,
            pm10=280,
            temperature=35,
            humidity=85,
            source="HEAVY_DUST",
            source_confidence=0.9,
        )
    )
    assert result["severity"] == "SEVERE"
    assert "dust" in result["advice"].lower()
    assert "humid" in result["weather_advice"].lower()
    assert "water" in result["weather_advice"].lower() or "cool" in result["weather_advice"].lower()


@pytest.mark.parametrize(
    ("temperature", "humidity", "expected"),
    [
        (35, 40, "Warm"),
        (10, 50, "Cool"),
        (22, 85, "water"),
        (22, 20, "Dry"),
        (22, 50, "comfortable"),
    ],
)
def test_weather_recommendations(temperature, humidity, expected):
    result = AdvisoryEngine().evaluate(reading(temperature=temperature, humidity=humidity))
    assert expected.lower() in result["weather_advice"].lower()


@pytest.mark.parametrize(
    ("aqi", "pm25", "pm10", "expected_severity"),
    [
        (35, 15.0, 30.0, "NORMAL"),      # Good (0-50)
        (75, 45.0, 75.0, "MODERATE"),    # Satisfactory (51-100)
        (150, 75.0, 180.0, "HIGH"),      # Moderate (101-200)
        (250, 105.0, 300.0, "SEVERE"),   # Poor (201-300)
        (350, 185.0, 390.0, "CRITICAL"), # Very Poor (301-400)
        (450, 300.0, 480.0, "CRITICAL"), # Severe (401-500)
    ],
)
def test_cpcb_category_transitions(aqi, pm25, pm10, expected_severity):
    result = AdvisoryEngine().evaluate(reading(aqi=aqi, pm25=pm25, pm10=pm10))
    assert result["severity"] == expected_severity


def test_provisional_pm_advice_when_insufficient_data():
    # When data sufficiency is INSUFFICIENT_DATA, advice must be clearly labelled as provisional
    r = reading(aqi=85, pm25=50.0, pm10=80.0)
    r["data_sufficiency"] = "INSUFFICIENT_DATA"
    r["is_provisional"] = True
    result = AdvisoryEngine().evaluate(r)
    assert result["severity"] == "MODERATE"
    assert "provisional" in result["advice"].lower()


def test_missing_measurements_not_interpreted_as_zero_pollution():
    # If aqi is None and pm dict is missing readings, it should not claim zero pollution
    r = {
        "aqi": None,
        "pm": {},
        "temperature_C": 25.0,
        "humidity_pct": 50.0,
        "predictions": {
            "source": {"value": "UNKNOWN", "confidence": None},
            "forecast": {"value": None, "confidence": None},
        },
    }
    result = AdvisoryEngine().evaluate(r)
    assert "unavailable" in result["advice"].lower() or "unverified" in result["advice"].lower()
