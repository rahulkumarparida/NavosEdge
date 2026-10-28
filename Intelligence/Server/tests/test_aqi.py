"""Tests for the AQI calculation, persistence, update, and API endpoint."""

import os
from datetime import datetime, timezone
import pytest
from app.aqi.calculator import AQICalculator
from app.aqi.schemas import AQICalculationResult, LatestAQIResponse
from app.aqi.store import AQIStore
from app.aqi.service import AQIService
from app.schemas.sensor import SensorPayload
from tests.conftest import valid_sensor_payload


def test_aqi_calculator_epa():
    calc = AQICalculator(standard="EPA")
    # Test Good range
    res = calc.calculate(pm1_0=5.0, pm2_5=10.0, pm10=20.0)
    assert res.status == "available"
    assert res.category == "Good"
    assert res.dominant_pollutant == "PM2_5"
    assert res.sub_indices["PM2_5"] <= 50.0
    assert res.pm == {"PM1_0": 5.0, "PM2_5": 10.0, "PM10": 20.0}

    # Test Moderate range
    res_mod = calc.calculate(pm1_0=15.0, pm2_5=25.0, pm10=80.0)
    assert res_mod.category == "Moderate"
    assert res_mod.sub_indices["PM2_5"] > 50.0

    # Test Unhealthy for Sensitive Groups range
    res_unhealthy = calc.calculate(pm1_0=30.0, pm2_5=40.0, pm10=100.0)
    assert res_unhealthy.category == "Unhealthy for Sensitive Groups"
    assert 101.0 <= res_unhealthy.aqi <= 150.0


def test_aqi_calculator_cpcb():
    calc = AQICalculator(standard="CPCB")
    res = calc.calculate(pm1_0=10.0, pm2_5=20.0, pm10=40.0)
    assert res.category in ("Good", "Satisfactory")
    assert "PM1_0" not in res.sub_indices
    assert set(res.sub_indices.keys()) == {"PM2_5", "PM10"}
    assert res.calculation_method == "CPCB_PM_ESTIMATE"
    assert res.is_complete_national_aqi is False


def test_default_standard_is_cpcb():
    calc = AQICalculator()
    assert calc.standard == "CPCB"


def test_explicit_epa_standard_selection():
    calc = AQICalculator(standard="EPA")
    assert calc.standard == "EPA"


def test_cpcb_sub_index_pm25_reference_values():
    calc = AQICalculator(standard="CPCB")
    # Official CPCB reference breakpoints:
    # 0-30 -> 0-50 (Good)
    # 30.1-60 -> 51-100 (Satisfactory)
    # 60.1-90 -> 101-200 (Moderate)
    # 90.1-120 -> 201-300 (Poor)
    # 120.1-250 -> 301-400 (Very Poor)
    # 250.1-500 -> 401-500 (Severe)
    test_cases = [
        (15.0, 25.0, "Good"),
        (45.0, 75.42, "Satisfactory"),
        (75.0, 150.33, "Moderate"),
        (105.0, 250.33, "Poor"),
        (185.0, 350.46, "Very Poor"),
        (375.0, 450.48, "Severe"),
    ]
    for conc, expected_si, expected_cat in test_cases:
        si = calc.calculate_sub_index("PM2_5", conc)
        assert abs(si - expected_si) <= 0.5, f"PM2.5 {conc} produced SI {si}, expected ~{expected_si}"
        res = calc.calculate(pm1_0=0.0, pm2_5=conc, pm10=0.0)
        assert res.category == expected_cat, f"PM2.5 {conc} category {res.category} != {expected_cat}"


def test_cpcb_sub_index_pm10_reference_values():
    calc = AQICalculator(standard="CPCB")
    # Official CPCB reference breakpoints:
    # 0-50 -> 0-50 (Good)
    # 50.1-100 -> 51-100 (Satisfactory)
    # 100.1-250 -> 101-200 (Moderate)
    # 251-350 -> 201-300 (Poor)
    # 351-430 -> 301-400 (Very Poor)
    # 430.1-500 -> 401-500 (Severe)
    test_cases = [
        (25.0, 25.0, "Good"),
        (75.0, 75.45, "Satisfactory"),
        (175.0, 150.47, "Moderate"),
        (300.0, 250.0, "Poor"),
        (390.0, 349.87, "Very Poor"),
        (465.0, 450.43, "Severe"),
    ]
    for conc, expected_si, expected_cat in test_cases:
        si = calc.calculate_sub_index("PM10", conc)
        assert abs(si - expected_si) <= 0.5, f"PM10 {conc} produced SI {si}, expected ~{expected_si}"
        res = calc.calculate(pm1_0=0.0, pm2_5=0.0, pm10=conc)
        assert res.category == expected_cat, f"PM10 {conc} category {res.category} != {expected_cat}"


def test_cpcb_pm1_excluded_from_sub_indices_and_dominant():
    calc = AQICalculator(standard="CPCB")
    # Even if PM1.0 is extremely high (400.0), CPCB does not regulate PM1.0
    res = calc.calculate(pm1_0=400.0, pm2_5=20.0, pm10=35.0)
    assert "PM1_0" not in res.sub_indices
    assert set(res.sub_indices.keys()) == {"PM2_5", "PM10"}
    assert res.dominant_pollutant in ("PM2_5", "PM10")
    assert res.dominant_pollutant != "PM1_0"
    # PM1.0 is preserved purely for diagnostic inspection
    assert res.pm["PM1_0"] == 400.0
    # Overall AQI corresponds only to PM2.5 or PM10 (Good range <= 50)
    assert res.aqi <= 50.0
    assert res.category == "Good"


def test_moving_average_sufficiency_and_spike_smoothing(tmp_path):
    storage_file = tmp_path / "aqi_service_test.json"
    service = AQIService(storage_path=storage_file, standard="CPCB")

    from datetime import timedelta
    t0 = datetime(2026, 10, 23, 0, 0, tzinfo=timezone.utc)

    def _make_payload(ts, pm25, pm10, pm1=10.0):
        p = valid_sensor_payload()
        p["node_id"] = "test-node-moving-avg"
        p["timestamp"] = ts.isoformat()
        p["particulate_matter"] = {"PM1_0": pm1, "PM2_5": pm25, "PM10": pm10}
        return SensorPayload(**p)

    # 1. First reading: only 1 sample, coverage = 1 covered hour (< 16h) -> INSUFFICIENT_DATA
    res1 = service.process_reading(_make_payload(t0, pm25=20.0, pm10=40.0))
    assert res1.data_sufficiency == "INSUFFICIENT_DATA"
    assert res1.is_provisional is True
    assert res1.is_complete_national_aqi is False
    assert res1.calculation_method == "CPCB_PM_ESTIMATE"
    assert res1.data_coverage_hours == 1.0

    # 2. Reading at 8 hours: coverage = 2 distinct covered hours (< 16h) -> INSUFFICIENT_DATA
    res2 = service.process_reading(_make_payload(t0 + timedelta(hours=8), pm25=20.0, pm10=40.0))
    assert res2.data_sufficiency == "INSUFFICIENT_DATA"
    assert res2.is_provisional is True
    assert res2.data_coverage_hours == 2.0

    # 3. Simulate readings across 18 hours: actual hourly readings from hour 1 to 18
    # Covers 19 distinct hours (0 through 18) -> VALID (>= 16h)
    for h in range(1, 19):
        res = service.process_reading(_make_payload(t0 + timedelta(hours=h), pm25=20.0, pm10=40.0))

    # Coverage is now 19 hours (>= 16h) -> VALID
    assert res.data_sufficiency == "VALID"
    assert res.is_provisional is False
    assert res.is_complete_national_aqi is False
    assert res.data_coverage_hours >= 16.0
    assert res.category == "Good"

    # 4. Instantaneous spike test: single extreme reading (PM2.5 = 450)
    # The moving average must smooth this spike and NOT jump to Severe AQI = 450!
    spike_res = service.process_reading(_make_payload(t0 + timedelta(hours=18, minutes=5), pm25=450.0, pm10=500.0))
    # With ~12 baseline readings at PM2.5=20 and only 1 spike reading at 450,
    # moving average is ~53 ug/m3 (Satisfactory range), NOT Severe (>400)!
    assert spike_res.aqi < 150.0
    assert spike_res.category in ("Good", "Satisfactory")


def test_invalid_input_produces_invalid_status(tmp_path):
    storage_file = tmp_path / "aqi_service_invalid.json"
    service = AQIService(storage_path=storage_file, standard="CPCB")

    p = valid_sensor_payload()
    p["node_id"] = "invalid-pm-node"
    # Negative concentration is physically invalid
    p["particulate_matter"]["PM2_5"] = -15.0
    payload = SensorPayload.model_construct(**p)
    res = service.process_reading(payload)
    assert res.data_sufficiency == "INVALID_INPUT"
    assert res.status == "invalid_input"
    assert res.category == "Invalid Input"


def test_aqi_store_persistence(tmp_path):
    storage_file = tmp_path / "aqi_latest.json"
    store = AQIStore(storage_path=storage_file)

    # Initial state: empty
    assert store.get_latest() is None

    # Save a result
    now = datetime.now(timezone.utc)
    res = AQICalculationResult(
        status="available",
        aqi=75.5,
        category="Satisfactory",
        dominant_pollutant="PM2_5",
        pm={"PM1_0": 15.0, "PM2_5": 23.5, "PM10": 45.0},
        sub_indices={"PM2_5": 75.5, "PM10": 41.0},
        timestamp=now,
        node_id="test-node-01",
    )
    store.save_latest(res)

    # Check disk file created
    assert storage_file.exists()

    # Load into fresh store
    store2 = AQIStore(storage_path=storage_file)
    loaded = store2.load_latest()
    assert loaded is not None
    assert loaded.aqi == 75.5
    assert loaded.node_id == "test-node-01"


def test_aqi_store_update(tmp_path):
    storage_file = tmp_path / "aqi_latest.json"
    store = AQIStore(storage_path=storage_file)

    now = datetime.now(timezone.utc)
    res1 = AQICalculationResult(
        status="available",
        aqi=45.0,
        category="Good",
        dominant_pollutant="PM2_5",
        pm={"PM1_0": 5.0, "PM2_5": 10.0, "PM10": 20.0},
        sub_indices={"PM2_5": 45.0, "PM10": 18.0},
        timestamp=now,
        node_id="test-node-01",
    )
    store.save_latest(res1)
    assert store.get_latest().aqi == 45.0

    # Overwrite with newer reading
    res2 = AQICalculationResult(
        status="available",
        aqi=120.0,
        category="Moderate",
        dominant_pollutant="PM2_5",
        pm={"PM1_0": 30.0, "PM2_5": 43.0, "PM10": 90.0},
        sub_indices={"PM2_5": 120.0, "PM10": 68.0},
        timestamp=now,
        node_id="test-node-01",
    )
    store.save_latest(res2)
    assert store.get_latest().aqi == 120.0

    # Reload from disk to ensure disk was updated
    store3 = AQIStore(storage_path=storage_file)
    loaded = store3.load_latest()
    assert loaded.aqi == 120.0


@pytest.mark.asyncio
async def test_aqi_latest_endpoint_not_available(client):
    # Reset AQI store state for this test if app state is available
    transport = getattr(client, "_transport", None)
    app = getattr(transport, "app", None)
    if app and hasattr(app.state, "aqi_service"):
        svc = app.state.aqi_service
        svc.store._latest = None
        svc.store._latest_by_node.clear()
        if svc.store.storage_path.exists():
            svc.store.storage_path.unlink()

    resp = await client.get("/aqi/latest")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "not_available"
    assert data["detail"] is not None


@pytest.mark.asyncio
async def test_aqi_latest_endpoint_after_submission(client, sample_payload):
    node_id = sample_payload["node_id"]

    # Submit sensor reading
    submit_resp = await client.post(f"/api/v1/nodes/{node_id}/readings", json=sample_payload)
    assert submit_resp.status_code == 201

    # Query GET /aqi/latest
    resp = await client.get("/aqi/latest")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "available"
    assert data["aqi"] is not None
    assert isinstance(data["aqi"], (int, float))
    assert data["category"] is not None
    assert data["dominant_pollutant"] is not None
    assert set(data["pm"]) == {"PM1_0", "PM2_5", "PM10"}
    assert data["node_id"] == node_id
    assert data["data_sufficiency"] in ("VALID", "INSUFFICIENT_DATA")
    assert data["is_complete_national_aqi"] is False
    assert "CPCB" in data["calculation_method"]

    # Query GET /api/v1/aqi/latest alias endpoint
    resp_alias = await client.get("/api/v1/aqi/latest")
    assert resp_alias.status_code == 200
    assert resp_alias.json()["status"] == "available"


def test_inter_bracket_boundary_continuity():
    calc_cpcb = AQICalculator(standard="CPCB")
    # PM2.5 gap boundaries (30.0 to 30.1, 60.0 to 60.1, 250.0 to 250.1)
    assert calc_cpcb.calculate_sub_index("PM2_5", 30.0) == 50.0
    si_30_05 = calc_cpcb.calculate_sub_index("PM2_5", 30.05)
    assert 50.0 < si_30_05 < 51.0
    assert calc_cpcb.calculate_sub_index("PM2_5", 30.1) == 51.0

    assert calc_cpcb.calculate_sub_index("PM2_5", 60.0) == 100.0
    si_60_05 = calc_cpcb.calculate_sub_index("PM2_5", 60.05)
    assert 100.0 < si_60_05 < 101.0
    assert calc_cpcb.calculate_sub_index("PM2_5", 60.1) == 101.0

    # PM10 gap boundaries (250.0 to 251.0, 350.0 to 351.0)
    assert calc_cpcb.calculate_sub_index("PM10", 250.0) == 200.0
    si_250_5 = calc_cpcb.calculate_sub_index("PM10", 250.5)
    assert 200.0 < si_250_5 < 201.0
    assert calc_cpcb.calculate_sub_index("PM10", 251.0) == 201.0

    assert calc_cpcb.calculate_sub_index("PM10", 350.0) == 300.0
    si_350_5 = calc_cpcb.calculate_sub_index("PM10", 350.5)
    assert 300.0 < si_350_5 < 301.0
    assert calc_cpcb.calculate_sub_index("PM10", 351.0) == 301.0

    # EPA PM10 gap boundary (54.0 to 55.0)
    calc_epa = AQICalculator(standard="EPA")
    assert calc_epa.calculate_sub_index("PM10", 54.0) == 50.0
    si_epa_54_5 = calc_epa.calculate_sub_index("PM10", 54.5)
    assert 50.0 < si_epa_54_5 < 51.0
    assert calc_epa.calculate_sub_index("PM10", 55.0) == 51.0


def test_non_finite_inputs_handled_safely(tmp_path):
    storage_file = tmp_path / "aqi_nan_test.json"
    service = AQIService(storage_path=storage_file, standard="CPCB")

    p = valid_sensor_payload()
    p["node_id"] = "nan-node"
    p["particulate_matter"]["PM2_5"] = float("nan")
    payload = SensorPayload.model_construct(**p)
    res = service.process_reading(payload)
    assert res.data_sufficiency == "INVALID_INPUT"
    assert res.status == "invalid_input"
    assert res.aqi == 0.0

    # History should not be poisoned
    p["particulate_matter"]["PM2_5"] = 25.0
    payload_valid = SensorPayload.model_construct(**p)
    res2 = service.process_reading(payload_valid)
    assert res2.status == "available"
    assert res2.aqi > 0


def test_out_of_order_reading_timestamps(tmp_path):
    storage_file = tmp_path / "aqi_order_test.json"
    service = AQIService(storage_path=storage_file, standard="CPCB")
    from datetime import timedelta

    t0 = datetime(2026, 10, 23, 0, 0, tzinfo=timezone.utc)

    def _payload(ts, pm25):
        p = valid_sensor_payload()
        p["node_id"] = "reorder-node"
        p["timestamp"] = ts.isoformat()
        p["particulate_matter"] = {"PM1_0": 10.0, "PM2_5": pm25, "PM10": 40.0}
        return SensorPayload(**p)

    # Deliver readings in scrambled order across 18 distinct hours:
    hours_scrambled = [10, 0, 17, 5, 2, 8, 14, 1, 16, 7, 3, 12, 6, 15, 4, 11, 9, 13]
    for h in hours_scrambled[:-1]:
        service.process_reading(_payload(t0 + timedelta(hours=h), 20.0))
    res = service.process_reading(_payload(t0 + timedelta(hours=hours_scrambled[-1]), 20.0))

    # All 18 distinct hours represented despite arrival order
    assert res.data_coverage_hours == 18.0
    assert res.data_sufficiency == "VALID"
    assert res.is_provisional is False



def test_two_readings_16_5_hours_apart_is_insufficient_data(tmp_path):
    storage_file = tmp_path / "aqi_gap_test.json"
    service = AQIService(storage_path=storage_file, standard="CPCB")
    from datetime import timedelta

    t0 = datetime(2026, 10, 23, 0, 0, tzinfo=timezone.utc)

    def _payload(ts, pm25):
        p = valid_sensor_payload()
        p["node_id"] = "gap-node"
        p["timestamp"] = ts.isoformat()
        p["particulate_matter"] = {"PM1_0": 10.0, "PM2_5": pm25, "PM10": 40.0}
        return SensorPayload(**p)

    # Reading 1 at t0
    r1 = service.process_reading(_payload(t0, 20.0))
    assert r1.data_coverage_hours == 1.0
    assert r1.data_sufficiency == "INSUFFICIENT_DATA"
    assert r1.is_provisional is True

    # Reading 2 at t0 + 16.5h (only 2 readings across 16.5 hours!)
    r2 = service.process_reading(_payload(t0 + timedelta(hours=16, minutes=30), 25.0))
    # Must report 2 distinct covered hours, NOT 16.5 hours!
    assert r2.data_coverage_hours == 2.0
    assert r2.data_sufficiency == "INSUFFICIENT_DATA"
    assert r2.is_provisional is True


def test_fifteen_versus_sixteen_covered_hours_threshold(tmp_path):
    storage_file = tmp_path / "aqi_threshold_test.json"
    service = AQIService(storage_path=storage_file, standard="CPCB")
    from datetime import timedelta

    t0 = datetime(2026, 10, 23, 0, 0, tzinfo=timezone.utc)

    def _payload(ts, pm25):
        p = valid_sensor_payload()
        p["node_id"] = "threshold-node"
        p["timestamp"] = ts.isoformat()
        p["particulate_matter"] = {"PM1_0": 10.0, "PM2_5": pm25, "PM10": 40.0}
        return SensorPayload(**p)

    # Supply readings for 15 distinct hours (hours 0 to 14)
    for h in range(15):
        r = service.process_reading(_payload(t0 + timedelta(hours=h), 20.0))

    # Exactly 15 hours covered: must be INSUFFICIENT_DATA
    assert r.data_coverage_hours == 15.0
    assert r.data_sufficiency == "INSUFFICIENT_DATA"
    assert r.is_provisional is True

    # Add the 16th hour (hour 15)
    r16 = service.process_reading(_payload(t0 + timedelta(hours=15), 20.0))
    # Exactly 16 hours covered: must transition to VALID and non-provisional
    assert r16.data_coverage_hours == 16.0
    assert r16.data_sufficiency == "VALID"
    assert r16.is_provisional is False


def test_duplicate_readings_in_same_hour_do_not_inflate_coverage(tmp_path):
    storage_file = tmp_path / "aqi_dup_test.json"
    service = AQIService(storage_path=storage_file, standard="CPCB")
    from datetime import timedelta

    t0 = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)

    def _payload(ts, pm25):
        p = valid_sensor_payload()
        p["node_id"] = "dup-node"
        p["timestamp"] = ts.isoformat()
        p["particulate_matter"] = {"PM1_0": 10.0, "PM2_5": pm25, "PM10": 40.0}
        return SensorPayload(**p)

    # Submit 10 readings all within the same hour (12:00, 12:05, 12:10, ..., 12:45)
    for m in range(0, 50, 5):
        res = service.process_reading(_payload(t0 + timedelta(minutes=m), 20.0))

    # Must count as exactly 1.0 covered hour
    assert res.data_coverage_hours == 1.0
    assert res.data_sufficiency == "INSUFFICIENT_DATA"
    assert res.is_provisional is True


def test_large_telemetry_gap_in_window(tmp_path):
    storage_file = tmp_path / "aqi_outage_test.json"
    service = AQIService(storage_path=storage_file, standard="CPCB")
    from datetime import timedelta

    t0 = datetime(2026, 10, 23, 0, 0, tzinfo=timezone.utc)

    def _payload(ts, pm25):
        p = valid_sensor_payload()
        p["node_id"] = "outage-node"
        p["timestamp"] = ts.isoformat()
        p["particulate_matter"] = {"PM1_0": 10.0, "PM2_5": pm25, "PM10": 40.0}
        return SensorPayload(**p)

    # 4 hours active (hours 0, 1, 2, 3)
    for h in range(4):
        service.process_reading(_payload(t0 + timedelta(hours=h), 20.0))

    # 12-hour outage (hours 4 through 15 are unobserved)
    # 4 hours active (hours 16, 17, 18, 19)
    for h in range(16, 20):
        res = service.process_reading(_payload(t0 + timedelta(hours=h), 20.0))

    # Total span is 19 hours, but only 8 distinct hours have telemetry
    assert res.data_coverage_hours == 8.0
    assert res.data_sufficiency == "INSUFFICIENT_DATA"
    assert res.is_provisional is True


def test_invalid_observations_excluded_from_covered_hours(tmp_path):
    storage_file = tmp_path / "aqi_invalid_excl_test.json"
    service = AQIService(storage_path=storage_file, standard="CPCB")
    from datetime import timedelta

    t0 = datetime(2026, 10, 23, 0, 0, tzinfo=timezone.utc)

    p1 = valid_sensor_payload()
    p1["node_id"] = "inv-excl-node"
    p1["timestamp"] = t0.isoformat()
    p1["particulate_matter"] = {"PM1_0": 10.0, "PM2_5": 20.0, "PM10": 40.0}
    r1 = service.process_reading(SensorPayload(**p1))
    assert r1.data_coverage_hours == 1.0

    # Submit invalid reading (NaN) at hour 2
    p2 = valid_sensor_payload()
    p2["node_id"] = "inv-excl-node"
    p2["timestamp"] = (t0 + timedelta(hours=2)).isoformat()
    p2["particulate_matter"] = {"PM1_0": 10.0, "PM2_5": float("nan"), "PM10": 40.0}
    r2 = service.process_reading(SensorPayload.model_construct(**p2))
    assert r2.data_sufficiency == "INVALID_INPUT"

    # Submit valid reading at hour 4
    p3 = valid_sensor_payload()
    p3["node_id"] = "inv-excl-node"
    p3["timestamp"] = (t0 + timedelta(hours=4)).isoformat()
    p3["particulate_matter"] = {"PM1_0": 10.0, "PM2_5": 25.0, "PM10": 45.0}
    r3 = service.process_reading(SensorPayload(**p3))
    # Only hours 0 and 4 are validly covered (hour 2 was rejected and excluded)
    assert r3.data_coverage_hours == 2.0
    assert r3.data_sufficiency == "INSUFFICIENT_DATA"
