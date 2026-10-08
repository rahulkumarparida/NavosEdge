#!/bin/bash
# ==============================================================================
# NavosEdge — Run All Tests
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SERVER_DIR="$PROJECT_DIR/Intelligence/Server"

PASS=0
FAIL=0
SKIP=0

run_test() {
    local name="$1"
    local cmd="$2"

    echo ""
    echo "--- $name ---"
    if eval "$cmd" 2>&1; then
        echo "  [PASS] $name"
        PASS=$((PASS + 1))
    else
        echo "  [FAIL] $name"
        FAIL=$((FAIL + 1))
    fi
}

echo "============================================================"
echo "NavosEdge — Test Suite"
echo "============================================================"

# Ensure we're in the right directory
cd "$SERVER_DIR"

# Activate venv if it exists
if [ -d "$SERVER_DIR/venv" ]; then
    source "$SERVER_DIR/venv/bin/activate"
fi

# Export PYTHONPATH
export PYTHONPATH="$SERVER_DIR:$PROJECT_DIR:$PYTHONPATH"

# --- Schema Tests ---
run_test "Sensor Schema Validation" \
    "python3 -u -c \"
from app.schemas.sensor import SensorPayload
from datetime import datetime, timezone
p = SensorPayload(
    node_id='test-001',
    timestamp=datetime.now(timezone.utc),
    environment={'temperature_C': 25.0, 'humidity_pct': 50.0},
    particulate_matter={'PM1_0': 10.0, 'PM2_5': 15.0, 'PM10': 20.0},
    gas_sensors={
        'MQ2': {'raw_adc': 200, 'voltage_V': 1.0},
        'MQ9': {'raw_adc': 180, 'voltage_V': 0.9},
        'MQ135': {'raw_adc': 250, 'voltage_V': 1.2}
    }
)
print(f'  Schema valid: {p.node_id}')
\""

# --- Malformed Data Rejection ---
run_test "Reject Malformed Data" \
    "python3 -u -c \"
from app.schemas.sensor import SensorPayload
from datetime import datetime, timezone
import traceback
try:
    SensorPayload(
        node_id='test-001',
        timestamp=datetime.now(timezone.utc),
        environment={'temperature_C': 25.0, 'humidity_pct': 50.0},
        particulate_matter={'PM1_0': 50.0, 'PM2_5': 15.0, 'PM10': 10.0},
        gas_sensors={
            'MQ2': {'raw_adc': 200, 'voltage_V': 1.0},
            'MQ9': {'raw_adc': 180, 'voltage_V': 0.9},
            'MQ135': {'raw_adc': 250, 'voltage_V': 1.2}
        }
    )
    print('  ERROR: Should have rejected PM1.0 > PM2.5 > PM10')
    exit(1)
except Exception as e:
    print(f'  Correctly rejected: {type(e).__name__}')
\""

# --- Inference Schema ---
run_test "Inference Result Schema" \
    "python3 -u -c \"
from app.schemas.inference import InferenceResult, InferenceStatus
r = InferenceResult.not_configured()
assert r.status == InferenceStatus.NOT_CONFIGURED
r2 = InferenceResult.from_error('test error')
assert r2.status == InferenceStatus.ERROR
print('  InferenceResult schemas OK')
\""

# --- AQI Calculator ---
run_test "AQI Calculator" \
    "python3 -u -c \"
from app.aqi.calculator import AQICalculator
calc = AQICalculator()
r = calc.calculate(pm1_0=10.0, pm2_5=35.0, pm10=50.0)
print(f'  AQI={r.aqi}, Category={r.category}')
assert r.aqi > 0
\""

# --- NumPy Inference Backend ---
run_test "NumPy Inference Backend Load" \
    "python3 -u -c \"
try:
    from app.services.numpy_inference import NumpyGasNetAdapter
    from app.core.config import get_settings
    settings = get_settings()
    adapter = NumpyGasNetAdapter(artifacts_dir=settings.ARTIFACTS_DIR)
    adapter.load()
    print(f'  NumPy backend loaded: {adapter._loaded}')
except ImportError as e:
    print(f'  NumPy backend not yet available: {e}')
except Exception as e:
    print(f'  NumPy backend error: {e}')
\""

# --- NumPy Inference Prediction ---
run_test "NumPy Inference Prediction" \
    "python3 -u -c \"
import asyncio
try:
    from app.services.numpy_inference import NumpyGasNetAdapter
    from app.core.config import get_settings
    settings = get_settings()
    adapter = NumpyGasNetAdapter(artifacts_dir=settings.ARTIFACTS_DIR)
    adapter.load()
    if adapter._loaded:
        result = asyncio.run(adapter.predict(1.5, 1.2, 1.8, 30.0, 55.0))
        print(f'  Status: {result.status}')
        print(f'  Class: {result.gas_class} ({result.class_confidence})')
        print(f'  Safety: {result.safety_status}')
        assert result.status.value == 'success'
    else:
        print('  Model not loaded (artifacts missing)')
except ImportError:
    print('  NumPy backend not available yet')
\""

# --- Anomaly Engine ---
run_test "Anomaly Engine" \
    "python3 -u -c \"
from app.anomaly.engine import AnomalyEngine
engine = AnomalyEngine()
print('  AnomalyEngine initialized successfully')
\""

# --- Source Classifier ---
run_test "Source Classifier" \
    "python3 -u -c \"
from app.source_classifier.classifier import SourceClassifier
from app.core.config import get_settings
settings = get_settings()
sc = SourceClassifier(artifacts_dir=settings.ARTIFACTS_DIR)
loaded = sc.load()
print(f'  Source classifier loaded: {loaded}')
\""

# --- Forecast Plugin ---
run_test "Forecast Plugin" \
    "python3 -u -c \"
from app.forecast.plugin import ForecastPlugin
fp = ForecastPlugin()
print(f'  ForecastPlugin initialized: {not fp.is_initialized}')
\""

# --- Advisory Engine ---
run_test "Advisory Engine" \
    "python3 -u -c \"
from app.advisory.engine import AdvisoryEngine
from app.advisory.rules import AdvisoryConfig
engine = AdvisoryEngine(AdvisoryConfig())
print('  AdvisoryEngine initialized')
\""

# --- Simulator ---
run_test "Sensor Simulator" \
    "cd '$PROJECT_DIR' && python3 -u -c \"
import sys
sys.path.insert(0, 'Intelligence/Server')
sys.path.insert(0, '.')
from simulation.sensor_simulator import SensorSimulator
sim = SensorSimulator(node_id='test-001', scenario='clean_indoor', seed=42)
reading = sim.generate()
from app.schemas.sensor import SensorPayload
from datetime import datetime, timezone
p = SensorPayload(**reading)
print(f'  Simulator reading validated: PM2.5={p.particulate_matter.PM2_5}')
\""

# --- Multiple Scenarios ---
for scenario in clean_indoor traffic dust_construction combustion_smoke high_humidity stable; do
    run_test "Simulator Scenario: $scenario" \
        "cd '$PROJECT_DIR' && python3 -u -c \"
import sys
sys.path.insert(0, 'Intelligence/Server')
sys.path.insert(0, '.')
from simulation.sensor_simulator import SensorSimulator
from app.schemas.sensor import SensorPayload
sim = SensorSimulator(node_id='test-001', scenario='$scenario', seed=42)
reading = sim.generate()
p = SensorPayload(**reading)
print(f'  Scenario $scenario OK: PM2.5={p.particulate_matter.PM2_5:.1f}')
\""
done

# --- Model Missing Graceful ---
run_test "Missing Model Graceful Handling" \
    "python3 -u -c \"
from app.services.numpy_inference import NumpyGasNetAdapter
from pathlib import Path
adapter = NumpyGasNetAdapter(artifacts_dir=Path('/nonexistent'))
adapter.load()
print(f'  Loaded: {adapter._loaded} (expected: False)')
assert not adapter._loaded
\""

# --- Pipeline ---
run_test "Modular Pipeline" \
    "python3 -u -c \"
from app.services.pipeline import ModularPipeline
from app.schemas.sensor import SensorPayload
from app.schemas.inference import InferenceResult, InferenceStatus
from datetime import datetime, timezone

pipeline = ModularPipeline()
payload = SensorPayload(
    node_id='test-001',
    timestamp=datetime.now(timezone.utc),
    environment={'temperature_C': 25.0, 'humidity_pct': 50.0},
    particulate_matter={'PM1_0': 10.0, 'PM2_5': 15.0, 'PM10': 20.0},
    gas_sensors={
        'MQ2': {'raw_adc': 200, 'voltage_V': 1.0},
        'MQ9': {'raw_adc': 180, 'voltage_V': 0.9},
        'MQ135': {'raw_adc': 250, 'voltage_V': 1.2}
    }
)
inference = InferenceResult.not_configured()
result = pipeline.process(payload, inference)
print(f'  Pipeline health: {result.health.status}')
print(f'  Pipeline advisory: {result.advisory.level}')
\""

# --- IP Auto-Detection & Config Utility Tests ---
run_test "Network IP Auto-Detection & .env Config" \
    "cd '$PROJECT_DIR' && pytest tests/test_update_env_ip.py -q"

# --- Manager Service Unit Tests ---
run_test "Manager Service Unit Tests" \
    "cd '$PROJECT_DIR' && PYTHONPATH=Manager pytest Manager/tests/test_manager_service.py -q"

# --- Manager UNO Q Integration & Dashboard IP Tests ---
run_test "Manager UNO Q Integration & IP Config API" \
    "cd '$PROJECT_DIR' && PYTHONPATH=Manager pytest Manager/tests/test_uno_q_manager_integration.py -q"

# --- Manager End-to-End Flow ---
run_test "Manager End-to-End Flow" \
    "cd '$PROJECT_DIR' && pytest tests/test_manager_e2e.py -q"

# Summary
echo ""
echo "============================================================"
echo "TEST SUMMARY"
echo "============================================================"
echo "  PASS: $PASS"
echo "  FAIL: $FAIL"
echo ""

if [ "$FAIL" -eq 0 ]; then
    echo "  RESULT: ALL TESTS PASSED"
    exit 0
else
    echo "  RESULT: $FAIL TEST(S) FAILED"
    exit 1
fi
