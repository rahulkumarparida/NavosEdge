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


# =====================================================================
# Phase 4.1: Acute Gas Hazard & Toxic Spike Detection Tests
# =====================================================================


def test_mq9_carbon_monoxide_spike_escalates_to_critical():
    # PM2.5 is low (clean air), but MQ-9 reads 3.3V (critical CO concentration)
    r = reading(aqi=20, pm25=12.0, pm10=25.0)
    r["mq9_v"] = 3.30
    result = AdvisoryEngine().evaluate(r)

    assert result["severity"] == "CRITICAL"
    assert "carbon monoxide" in result["advice"].lower() or "co" in result["advice"].lower()
    assert any("evacuate" in action.lower() for action in result["actions"])
    assert any("ventilate" in action.lower() for action in result["actions"])
    assert set(result) == {"severity", "advice", "actions", "weather_advice"}


def test_mq2_flammable_lpg_spike_escalates_to_critical():
    # Low particulate reading with MQ-2 at 3.5V (critical combustible/LPG leak)
    r = reading(aqi=25, pm25=14.0)
    r["gas_sensors"] = {"MQ2_V": 3.50, "MQ9_V": 0.80, "MQ135_V": 0.90}
    result = AdvisoryEngine().evaluate(r)

    assert result["severity"] == "CRITICAL"
    assert "combustible" in result["advice"].lower() or "flammable" in result["advice"].lower() or "gas" in result["advice"].lower()
    assert any("switches" in action.lower() or "flames" in action.lower() for action in result["actions"])
    assert any("evacuate" in action.lower() for action in result["actions"])


def test_mq135_toxic_voc_spike_escalates_to_critical():
    # Clean PM baseline, MQ-135 at 3.4V (critical toxic chemical vapors / VOCs)
    r = reading(aqi=30, pm25=15.0)
    r["mq135_v"] = 3.40
    result = AdvisoryEngine().evaluate(r)

    assert result["severity"] == "CRITICAL"
    assert "chemical" in result["advice"].lower() or "voc" in result["advice"].lower() or "toxic" in result["advice"].lower()
    assert any("chemical" in action.lower() or "ventilation" in action.lower() for action in result["actions"])


def test_rate_of_change_gas_spike_escalation():
    # Ambient voltages are moderate, but rate-of-change shows a sudden surge >= 0.8V
    r = reading(aqi=20, pm25=10.0)
    r["mq9_v"] = 2.0  # normally moderate
    r["mq9_delta_v"] = 0.85  # rapid surge
    result = AdvisoryEngine().evaluate(r)

    # Escalates beyond moderate due to rapid spike
    assert result["severity"] in ("HIGH", "SEVERE", "CRITICAL")
    assert any(term in result["advice"].lower() for term in ("surge", "spike", "carbon monoxide"))


def test_neural_inference_hazard_escalation():
    # Particulates are low, but TinyGasNet model flags hazardous CO
    r = reading(aqi=25, pm25=12.0)
    r["gas_inference"] = {
        "gas_class": "CO",
        "safety_status": "hazardous",
        "safety_confidence": 0.90,
    }
    result = AdvisoryEngine().evaluate(r)

    assert result["severity"] in ("HIGH", "SEVERE", "CRITICAL")
    assert "co" in result["advice"].lower() or "carbon monoxide" in result["advice"].lower()


def test_sensor_fault_rails_rejected_without_false_gas_alarm():
    # Readings < 0.10V (GND short) or > 4.90V (VCC short) are sensor faults, NOT gas leaks
    r_gnd = reading(aqi=20, pm25=12.0)
    r_gnd["mq9_v"] = 0.05  # Ground short
    res_gnd = AdvisoryEngine().evaluate(r_gnd)
    assert res_gnd["severity"] == "NORMAL"

    r_vcc = reading(aqi=20, pm25=12.0)
    r_vcc["mq2_v"] = 4.95  # VCC rail short
    res_vcc = AdvisoryEngine().evaluate(r_vcc)
    assert res_vcc["severity"] == "NORMAL"


def test_gas_hazard_overrides_particulate_window_sealing():
    # Severe particulates would normally prescribe "Keep windows closed",
    # but a severe gas leak requires ventilation and evacuation!
    r = reading(aqi=250, pm25=105.0, pm10=300.0)
    r["mq9_v"] = 3.30  # Critical CO leak
    result = AdvisoryEngine().evaluate(r)

    assert result["severity"] == "CRITICAL"
    # Gas evacuation actions must be present
    assert any("evacuate" in a.lower() for a in result["actions"])
    # Contradictory particulate advice to keep windows closed must be suppressed
    assert not any("windows closed" in a.lower() for a in result["actions"])


# =====================================================================
# Phase 4.2: Multi-Language Localization Tests (Hindi & Odia)
# =====================================================================


def test_hindi_advisory_clean_air_and_weather():
    r = reading(aqi=20, pm25=10.0, temperature=22.0, humidity=50.0)
    result = AdvisoryEngine(language="hi").evaluate(r)

    assert set(result) == {"severity", "advice", "actions", "weather_advice"}
    assert result["severity"] == "NORMAL"
    assert result["actions"] == ["सामान्य प्रदूषण सावधानियों का पालन करें।"]
    assert "हवा" in result["advice"] or "वायु" in result["advice"]
    assert "मौसम" in result["weather_advice"]


def test_hindi_advisory_acute_gas_hazard():
    r = reading(aqi=20, pm25=10.0)
    r["mq9_v"] = 3.30
    result = AdvisoryEngine().evaluate(r, language="hi")

    assert result["severity"] == "CRITICAL"
    assert "कार्बन मोनोऑक्साइड" in result["advice"]
    assert any("तुरंत" in a for a in result["actions"])
    assert any("वेंटिलेशन" in a or "खिड़कियाँ" in a for a in result["actions"])


def test_odia_advisory_clean_air_and_weather():
    r = reading(aqi=20, pm25=10.0, temperature=22.0, humidity=50.0)
    result = AdvisoryEngine(language="or").evaluate(r)

    assert set(result) == {"severity", "advice", "actions", "weather_advice"}
    assert result["severity"] == "NORMAL"
    assert result["actions"] == ["ସାଧାରଣ ପ୍ରଦୂଷଣ ସତର୍କତା ଅବଲମ୍ବନ କରନ୍ତୁ।"]
    assert "ବାୟୁ" in result["advice"]
    assert "ପାଗ" in result["weather_advice"]


def test_odia_advisory_acute_gas_hazard():
    r = reading(aqi=20, pm25=10.0)
    r["mq2_v"] = 3.50  # Flammable leak
    result = AdvisoryEngine().evaluate(r, language="or")

    assert result["severity"] == "CRITICAL"
    assert "ଜ୍ୱଳନଶୀଳ" in result["advice"] or "ଗ୍ୟାସ୍" in result["advice"]
    assert any("ନିରାପଦ ସ୍ଥାନ" in a or "ସ୍ଥାନ" in a for a in result["actions"])
    assert any("ବିଦ୍ୟୁତ୍" in a for a in result["actions"])


def test_unsupported_language_fallback_to_english():
    r = reading(aqi=20, pm25=10.0)
    result = AdvisoryEngine(language="fr").evaluate(r)

    # Seamlessly falls back to English
    assert result["severity"] == "NORMAL"
    assert result["actions"] == ["Use general pollution precautions."]
    assert "air" in result["advice"].lower()

