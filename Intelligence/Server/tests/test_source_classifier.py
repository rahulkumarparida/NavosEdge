import pytest
from app.source_classifier.classifier import SourceClassifier
from app.schemas.sensor import SensorPayload
from app.source_classifier.categories import SourceCategory

@pytest.fixture
def classifier(tmp_path):
    # Empty artifacts dir, should fall back gracefully
    return SourceClassifier(artifacts_dir=tmp_path)

def test_classifier_not_configured(classifier, sample_payload):
    result = classifier.classify(SensorPayload(**sample_payload))
    assert result["status"] == "success"
    assert result["top_source"] == SourceCategory.UNKNOWN.value
    assert result["uncertainty"]["is_uncertain"] is True
    assert "No model artifacts" in result["predictions"][0]["limitations"][0]

def test_data_quality_missing_features(classifier, sample_payload):
    # Alter payload to trigger data quality checks
    payload = SensorPayload(**sample_payload)
    
    result = classifier.classify(payload)
    assert result["data_quality"]["status"] in ["valid", "degraded"]
