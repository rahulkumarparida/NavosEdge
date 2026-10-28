from datetime import datetime, timezone
from pathlib import Path
import pytest

from app.schemas.sensor import SensorPayload
from app.schemas.source_classification import SourceClassificationResult
from app.source_classifier.categories import SourceCategory
from app.source_classifier.classifier import SourceClassifier


@pytest.fixture
def unconfigured_classifier(tmp_path):
    """Empty artifacts directory to test graceful fallback."""
    return SourceClassifier(artifacts_dir=tmp_path)


@pytest.fixture
def loaded_classifier():
    """Classifier loaded with production artifacts."""
    artifacts_dir = Path(__file__).resolve().parent.parent / "artifacts"
    sc = SourceClassifier(artifacts_dir=artifacts_dir)
    sc.load()
    return sc


def make_payload(
    pm1: float = 15.0,
    pm25: float = 35.0,
    pm10: float = 65.0,
    mq2: float = 1.20,
    mq9: float = 1.40,
    mq135: float = 1.30,
    temp: float = 28.0,
    hum: float = 60.0,
    node_id: str = "test-node",
) -> SensorPayload:
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return SensorPayload(
        node_id=node_id,
        timestamp=now_iso,
        environment={"temperature_C": temp, "humidity_pct": hum},
        particulate_matter={"PM1_0": pm1, "PM2_5": pm25, "PM10": pm10},
        gas_sensors={
            "MQ2": {"voltage_V": mq2, "raw_adc": int(mq2 / 5.0 * 1023)},
            "MQ9": {"voltage_V": mq9, "raw_adc": int(mq9 / 5.0 * 1023)},
            "MQ135": {"voltage_V": mq135, "raw_adc": int(mq135 / 5.0 * 1023)},
        },
    )


def test_classifier_not_configured(unconfigured_classifier, sample_payload):
    result = unconfigured_classifier.classify(SensorPayload(**sample_payload))
    assert result["status"] == "success"
    assert result["top_source"] == SourceCategory.UNKNOWN.value
    assert result["uncertainty"]["is_uncertain"] is True
    assert "No model artifacts" in result["predictions"][0]["limitations"][0]


def test_data_quality_missing_features(unconfigured_classifier, sample_payload):
    payload = SensorPayload(**sample_payload)
    result = unconfigured_classifier.classify(payload)
    assert result["data_quality"]["status"] in ["valid", "degraded"]


# --- Phase 2B: Hardware Fault & Out-of-Bounds Pre-Inference Abstention ---

def test_hardware_fault_abstention_railed_ground(loaded_classifier):
    """Sensors railed to GND (<0.100V) must force invalid data quality and UNKNOWN abstention."""
    p = make_payload(mq2=0.05)
    res = loaded_classifier.classify(p)
    assert res["data_quality"]["status"] == "invalid"
    assert res["top_source"] == SourceCategory.UNKNOWN.value
    assert res["uncertainty"]["is_uncertain"] is True
    assert "below physical limit" in res["uncertainty"]["reason"]
    assert res["predictions"][0]["source"] == SourceCategory.UNKNOWN.value


def test_hardware_fault_abstention_railed_vcc(loaded_classifier):
    """Sensors railed to VCC (>4.900V) must force invalid data quality and UNKNOWN abstention."""
    p = make_payload(mq9=4.95)
    res = loaded_classifier.classify(p)
    assert res["data_quality"]["status"] == "invalid"
    assert res["top_source"] == SourceCategory.UNKNOWN.value
    assert res["uncertainty"]["is_uncertain"] is True
    assert "above physical limit" in res["uncertainty"]["reason"]


def test_out_of_bounds_temperature_abstention(loaded_classifier):
    """Extreme out-of-domain temperature must trigger invalid quality and UNKNOWN abstention."""
    p = make_payload(temp=72.0)
    res = loaded_classifier.classify(p)
    assert res["data_quality"]["status"] == "invalid"
    assert res["top_source"] == SourceCategory.UNKNOWN.value
    assert res["uncertainty"]["is_uncertain"] is True
    assert "Temperature out of physical bounds" in res["uncertainty"]["reason"]


# --- Phase 2B: Physical Ambiguity Handling & Calibration ---

def test_traffic_generator_ambiguity_flagged(loaded_classifier):
    """
    Fuel combustion emissions (elevated MQ9/MQ135 and PM2.5) must be flagged
    with explicit uncertainty and explanatory physical limitations.
    """
    p = make_payload(pm1=28.0, pm25=65.0, pm10=85.0, mq2=1.45, mq9=2.25, mq135=1.85)
    res = loaded_classifier.classify(p)
    assert res["uncertainty"]["is_uncertain"] is True
    assert "Physical sensor ambiguity" in res["uncertainty"]["reason"]
    
    # Limitations must be appended to both fuel combustion hypotheses
    traf_pred = next((x for x in res["predictions"] if x["source"] == SourceCategory.TRAFFIC.value), None)
    ind_pred = next((x for x in res["predictions"] if x["source"] == SourceCategory.INDUSTRIAL_OR_GENERATOR_EMISSIONS.value), None)
    assert traf_pred is not None
    assert ind_pred is not None
    assert any("MOS sensors" in lim for lim in traf_pred["limitations"])
    assert any("MOS sensors" in lim for lim in ind_pred["limitations"])

    # Confidence must be capped to ambiguous_confidence_cap (<= 0.40)
    if traf_pred.get("confidence") is not None:
        assert traf_pred["confidence"] <= 0.40
    if ind_pred.get("confidence") is not None:
        assert ind_pred["confidence"] <= 0.40


def test_indoor_clean_ambiguity_flagged(loaded_classifier):
    """
    Clean baseline telemetry must trigger baseline ambiguity warning
    acknowledging the absence of CO2 NDIR or VOC speciation.
    """
    p = make_payload(pm1=3.0, pm25=7.0, pm10=11.0, mq2=0.72, mq9=0.68, mq135=0.85)
    res = loaded_classifier.classify(p)
    assert res["uncertainty"]["is_uncertain"] is True
    assert "Baseline ambiguity" in res["uncertainty"]["reason"]
    
    cln_pred = next((x for x in res["predictions"] if x["source"] == SourceCategory.CLEAN_OR_BACKGROUND.value), None)
    assert cln_pred is not None
    assert any("CO2 NDIR" in lim for lim in cln_pred["limitations"])


# --- Phase 2B: Multi-Tier Mixed-Pollution Detection ---

def test_dual_mixture_traffic_plus_construction(loaded_classifier):
    """Co-occurring vehicle exhaust and coarse construction dust must predict MIXED_POLLUTION."""
    p = make_payload(pm1=22.0, pm25=65.0, pm10=210.0, mq2=1.45, mq9=2.25, mq135=1.55)
    res = loaded_classifier.classify(p)
    assert res["top_source"] == SourceCategory.MIXED_POLLUTION.value
    assert res["predictions"][0]["source"] == SourceCategory.MIXED_POLLUTION.value
    assert res["uncertainty"]["is_uncertain"] is True


def test_dual_mixture_combustion_plus_traffic(loaded_classifier):
    """Co-occurring dense biomass smoke and vehicle exhaust gas must predict MIXED_POLLUTION."""
    p = make_payload(pm1=58.0, pm25=145.0, pm10=175.0, mq2=2.65, mq9=2.15, mq135=2.10)
    res = loaded_classifier.classify(p)
    assert res["top_source"] == SourceCategory.MIXED_POLLUTION.value
    assert res["predictions"][0]["source"] == SourceCategory.MIXED_POLLUTION.value


def test_dual_mixture_industrial_plus_pm(loaded_classifier):
    """Co-occurring elevated industrial gas (high MQ135) and coarse dust must predict MIXED_POLLUTION."""
    p = make_payload(pm1=28.0, pm25=68.0, pm10=192.0, mq2=1.25, mq9=1.40, mq135=2.95)
    res = loaded_classifier.classify(p)
    assert res["top_source"] == SourceCategory.MIXED_POLLUTION.value
    assert res["predictions"][0]["source"] == SourceCategory.MIXED_POLLUTION.value


def test_tri_source_mixture(loaded_classifier):
    """Three co-occurring elevated sources must trigger Tier 1 tri-source MIXED_POLLUTION."""
    p = make_payload(pm1=35.0, pm25=85.0, pm10=195.0, mq2=2.15, mq9=2.10, mq135=2.25)
    res = loaded_classifier.classify(p)
    assert res["top_source"] == SourceCategory.MIXED_POLLUTION.value


def test_pure_heavy_dust_unambiguous(loaded_classifier):
    """Pure resuspended dust with low gas sensors must correctly predict HEAVY_DUST without false mixed trigger."""
    p = make_payload(pm1=8.0, pm25=28.0, pm10=160.0, mq2=0.75, mq9=0.70, mq135=0.85)
    res = loaded_classifier.classify(p)
    assert res["top_source"] == SourceCategory.HEAVY_DUST.value


def test_response_schema_compatibility(loaded_classifier):
    """Verify that classify() return value conforms to SourceClassificationResult schema."""
    p = make_payload()
    res = loaded_classifier.classify(p)
    model = SourceClassificationResult.from_classifier_dict(res)
    assert model.classifier == "source_classifier"
    assert model.status.value == "success"
    assert model.top_source is not None
