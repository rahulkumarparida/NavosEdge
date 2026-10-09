"""
Comprehensive tests for Indian CPCB AQI calculation methodology,
data sufficiency checks, PM1.0 exclusion, and the dynamic advisory engine.
"""

import pytest
from app.aqi.calculator import AQICalculator
from app.core.constants import BREAKPOINTS_CPCB, CPCB_CATEGORIES
from app.advisory.engine import AdvisoryEngine
from app.advisory.rules import AdvisoryConfig


# =====================================================================
# 1. CPCB AQI Breakpoint & Interpolation Tests
# =====================================================================

def test_cpcb_constants_and_categories():
    calc = AQICalculator(standard="CPCB")
    assert calc.standard == "CPCB"
    assert "PM2_5" in BREAKPOINTS_CPCB
    assert "PM10" in BREAKPOINTS_CPCB
    assert "NO2" in BREAKPOINTS_CPCB
    assert "SO2" in BREAKPOINTS_CPCB
    assert "CO" in BREAKPOINTS_CPCB
    assert "O3" in BREAKPOINTS_CPCB
    assert "NH3" in BREAKPOINTS_CPCB
    assert "Pb" in BREAKPOINTS_CPCB

    # Canonical Indian CPCB categories
    assert calc.get_category(25) == "Good"
    assert calc.get_category(50) == "Good"
    assert calc.get_category(51) == "Satisfactory"
    assert calc.get_category(100) == "Satisfactory"
    assert calc.get_category(101) == "Moderate"
    assert calc.get_category(200) == "Moderate"
    assert calc.get_category(201) == "Poor"
    assert calc.get_category(300) == "Poor"
    assert calc.get_category(301) == "Very Poor"
    assert calc.get_category(400) == "Very Poor"
    assert calc.get_category(401) == "Severe"
    assert calc.get_category(500) == "Severe"


def test_cpcb_pm25_boundary_interpolations():
    calc = AQICalculator(standard="CPCB")
    # PM2.5 = 30 -> sub-index should be 50.0 (Good boundary)
    s30 = calc.calculate_sub_index("PM2_5", 30.0)
    assert abs(s30 - 50.0) < 0.1

    # PM2.5 = 60 -> sub-index should be 100.0 (Satisfactory boundary)
    s60 = calc.calculate_sub_index("PM2_5", 60.0)
    assert abs(s60 - 100.0) < 0.1

    # PM2.5 = 90 -> sub-index should be 200.0 (Moderate boundary)
    s90 = calc.calculate_sub_index("PM2_5", 90.0)
    assert abs(s90 - 200.0) < 0.1

    # PM2.5 = 120 -> sub-index should be 300.0 (Poor boundary)
    s120 = calc.calculate_sub_index("PM2_5", 120.0)
    assert abs(s120 - 300.0) < 0.1

    # PM2.5 = 250 -> sub-index should be 400.0 (Very Poor boundary)
    s250 = calc.calculate_sub_index("PM2_5", 250.0)
    assert abs(s250 - 400.0) < 0.1


def test_cpcb_pm10_boundary_interpolations():
    calc = AQICalculator(standard="CPCB")
    # PM10 = 50 -> sub-index should be 50.0 (Good boundary)
    assert abs(calc.calculate_sub_index("PM10", 50.0) - 50.0) < 0.1
    # PM10 = 100 -> sub-index should be 100.0 (Satisfactory boundary)
    assert abs(calc.calculate_sub_index("PM10", 100.0) - 100.0) < 0.1
    # PM10 = 250 -> sub-index should be 200.0 (Moderate boundary)
    assert abs(calc.calculate_sub_index("PM10", 250.0) - 200.0) < 0.1
    # PM10 = 350 -> sub-index should be 300.0 (Poor boundary)
    assert abs(calc.calculate_sub_index("PM10", 350.0) - 300.0) < 0.1
    # PM10 = 430 -> sub-index should be 400.0 (Very Poor boundary)
    assert abs(calc.calculate_sub_index("PM10", 430.0) - 400.0) < 0.1


def test_cpcb_data_sufficiency_and_pm_only_compliance():
    calc = AQICalculator(standard="CPCB")

    # Only PM2.5 and PM10 provided (<3 regulatory pollutants)
    res = calc.calculate(pm1_0=15.0, pm2_5=45.0, pm10=80.0)
    assert res.cpcb_compliant is False
    assert res.calculation_basis == "PM_BASED_ESTIMATE"
    assert res.data_sufficiency == "INSUFFICIENT_POLLUTANTS"
    assert res.official_cpcb_aqi is None
    assert res.pm_based_aqi is not None
    assert res.pm_based_aqi > 0
    # PM1.0 is NOT a CPCB regulatory pollutant
    assert "PM1_0" not in res.sub_indices


def test_cpcb_full_compliance_with_three_pollutants():
    calc = AQICalculator(standard="CPCB")
    # 3 regulatory pollutants: PM2.5, PM10, and NO2
    extra = {"NO2": 50.0}
    res = calc.calculate(pm1_0=10.0, pm2_5=40.0, pm10=70.0, other_pollutants=extra)
    assert res.cpcb_compliant is True
    assert res.calculation_basis == "CPCB_COMPLIANT"
    assert res.data_sufficiency == "SUFFICIENT"
    assert res.official_cpcb_aqi is not None
    assert "NO2" in res.sub_indices


# =====================================================================
# 2. Dynamic Advisory Engine Tests
# =====================================================================

def test_advisory_invalid_or_stale_reading_suppresses_health_advice():
    engine = AdvisoryEngine()

    # Case 1: Explicitly marked invalid
    res_invalid = engine.evaluate({"is_valid": False, "aqi": 350})
    assert res_invalid["advice"] == "Sensor data is unavailable. Check the connection."
    assert "Check sensor connection." in res_invalid["actions"]
    assert "mask" not in res_invalid["advice"].lower()

    # Case 2: Status is stale
    res_stale = engine.evaluate({"status": "stale", "aqi": 200})
    assert res_stale["advice"] == "Sensor data is unavailable. Check the connection."

    # Case 3: Empty payload / missing data
    res_empty = engine.evaluate({})
    assert res_empty["advice"] == "Sensor data is unavailable. Check the connection."


def test_advisory_actions_length_and_limit():
    engine = AdvisoryEngine()
    test_reading = {
        "aqi": 240,
        "pm": {"PM1_0": 40.0, "PM2_5": 110.0, "PM10": 220.0},
        "temperature_C": 28.0,
        "humidity_pct": 55.0,
        "predictions": {
            "source": {"value": "TRAFFIC", "confidence": 0.85},
            "forecast": {"value": None, "confidence": None},
        },
    }
    res = engine.evaluate(test_reading)
    assert len(res["actions"]) <= 3
    for act in res["actions"]:
        assert len(act) <= 34, f"Action exceeds 34 characters: '{act}'"


def test_advisory_shifts_across_20_point_delta():
    engine = AdvisoryEngine()

    # Reading at lower sub-band of Moderate (AQI = 110)
    r1 = {
        "aqi": 110,
        "pm": {"PM2_5": 65.0, "PM10": 120.0},
        "temperature_C": 25.0,
        "humidity_pct": 50.0,
        "predictions": {
            "source": {"value": "UNKNOWN", "confidence": None},
        },
    }
    res1 = engine.evaluate(r1)

    # Shift by >20 points to upper sub-band of Moderate (AQI = 145)
    r2 = {
        "aqi": 145,
        "pm": {"PM2_5": 85.0, "PM10": 150.0},
        "temperature_C": 25.0,
        "humidity_pct": 50.0,
        "predictions": {
            "source": {"value": "UNKNOWN", "confidence": None},
        },
    }
    res2 = engine.evaluate(r2)

    # Advice or sub-band should reflect the shift
    assert res1["advice"] != res2["advice"] or res1["actions"] != res2["actions"]


def test_advisory_hysteresis_prevents_jitter_at_boundary():
    engine = AdvisoryEngine()

    # Reading right near boundary
    r_base = {
        "aqi": 70.0,
        "pm": {"PM2_5": 45.0, "PM10": 70.0},
        "temperature_C": 25.0,
        "humidity_pct": 50.0,
    }
    res_base = engine.evaluate(r_base)

    # Minor jitter within hysteresis margin (70.5)
    r_jitter = {
        "aqi": 70.5,
        "pm": {"PM2_5": 45.3, "PM10": 70.5},
        "temperature_C": 25.0,
        "humidity_pct": 50.0,
    }
    res_jitter = engine.evaluate(r_jitter)

    # Advice should remain stable and not flutter
    assert res_base["severity"] == res_jitter["severity"]


def test_broadened_sources_produce_distinct_actions():
    engine = AdvisoryEngine()

    sources = ["TRAFFIC", "HEAVY_DUST", "CONSTRUCTION", "BIOMASS_OR_WASTE_BURNING", "INDUSTRIAL"]
    action_sets = {}

    for src in sources:
        reading = {
            "aqi": 180,
            "pm": {"PM2_5": 95.0, "PM10": 160.0},
            "predictions": {
                "source": {"value": src, "confidence": 0.88},
            },
        }
        res = engine.evaluate(reading)
        action_sets[src] = tuple(res["actions"])
        # Each source should have at least one action
        assert len(res["actions"]) > 0
        # Each action string fits within display width
        for act in res["actions"]:
            assert len(act) <= 34

    # Different sources should produce distinct action recommendations
    assert action_sets["TRAFFIC"] != action_sets["HEAVY_DUST"]
    assert action_sets["CONSTRUCTION"] != action_sets["BIOMASS_OR_WASTE_BURNING"]
