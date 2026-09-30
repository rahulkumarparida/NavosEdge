# NavosEdge Project Guide

This guide explains how to run the Intelligence project as a whole, how to run each component separately, and how to use the simulator as a client that exercises the backend and reads its feedback.

All commands in this guide are run from:

```bash
cd Intelligence/Server
```

The server virtual environment is:

```text
Intelligence/Server/venv/
```

## 1. Project Components

```text
Intelligence/Server/
├── app/
│   ├── main.py                  FastAPI application and lifecycle
│   ├── api/routes/              HTTP and SSE endpoints
│   ├── schemas/                 Input/output validation contracts
│   ├── services/                Inference, processing, nodes, events
│   ├── anomaly/                 Stateful anomaly detection
│   ├── source_classifier/       Source classification and training
│   ├── forecast/                PM forecast plugin
│   └── storage/                 Main JSONL reading storage
├── Simulator/                   Synthetic hardware client
├── artifacts/                   Model and classifier artifacts
├── data/                        Runtime JSONL data
├── tests/                       Backend tests
├── requirements.txt             Python dependencies
└── venv/                        Project Python environment
```

## 2. Install and Configure

Create the environment if it does not exist:

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

Optional environment configuration:

```bash
cp .env.example .env
```

Important defaults:

```text
Host:       0.0.0.0
Port:       8420
Main data:  ./data
Artifacts:  ./artifacts
Forecast:   enabled, 48-hour retention
```

The available artifacts are loaded automatically at startup:

```text
artifacts/gasnet.pt
artifacts/preprocess.pkl
artifacts/source_classifier_model.pkl
artifacts/source_classifier_stats.json
artifacts/source_classifier_metadata.json
```

## 3. Run the Entire Backend

Start the Intelligence API:

```bash
./venv/bin/python -m app.main
```

Wait for:

```text
Application startup complete.
Uvicorn running on http://0.0.0.0:8420
```

Check liveness and readiness from another terminal:

```bash
curl -s http://127.0.0.1:8420/health | python -m json.tool
curl -s http://127.0.0.1:8420/ready | python -m json.tool
```

A ready server should report:

```json
{
  "ready": true,
  "storage_ok": true,
  "model_loaded": true
}
```

The startup can take several seconds because the PyTorch model and source classifier artifacts are loaded before the API becomes ready.

## 4. Run Only the Simulator

The simulator is a client. It does not start the server itself.

List scenarios:

```bash
./venv/bin/python -m Simulator list
```

Generate a local sample without network access:

```bash
./venv/bin/python -m Simulator sample \
  --node-id sim-node-01 \
  --scenario clean_background
```

Run a local session without sending:

```bash
./venv/bin/python -m Simulator start \
  --no-send \
  --scenario traffic \
  --samples 5 \
  --save /tmp/navos-simulator.jsonl
```

The generated payload is validated using the real `app.schemas.sensor.SensorPayload` model.

## 5. Run Simulator and Backend Together

Use two terminals.

### Terminal 1: backend

```bash
cd Intelligence/Server
./venv/bin/python -m app.main
```

### Terminal 2: simulator client

```bash
cd Intelligence/Server
./venv/bin/python -m Simulator start \
  --node-id sim-node-01 \
  --scenario traffic \
  --samples 10 \
  --interval 2 \
  --verify
```

The simulator checks `/health` and `/ready`, submits to:

```text
POST /api/v1/nodes/sim-node-01/readings
```

For every accepted reading it prints:

```text
[ACCEPTED] node=sim-node-01 http=201 reading_id=... gas=... safety=... health=... advisory=... anomaly=... source=...
```

With `--verify`, it also calls:

```text
GET /api/v1/nodes/sim-node-01/status
GET /api/v1/nodes/sim-node-01/latest
```

and prints their HTTP statuses.

The ingestion response is the compact user-facing intelligence result. It
contains only `aqi`, `pm`, `temperature_C`, `humidity_pct`, and
`predictions.source`/`predictions.forecast`, where each prediction has only
`value` and `confidence`. Raw ADC, voltage, model probabilities, anomaly
evidence, and storage details remain internal.

## 6. Run Each Backend Area Individually

### Health API

```bash
curl -s http://127.0.0.1:8420/health | python -m json.tool
curl -s http://127.0.0.1:8420/ready | python -m json.tool
```

### Node ingestion

Use the simulator one-shot command:

```bash
./venv/bin/python -m Simulator sample \
  --node-id sim-node-01 \
  --scenario traffic \
  --send
```

Or use `curl` with a complete payload:

```bash
curl -X POST http://127.0.0.1:8420/api/v1/nodes/curl-node/readings \
  -H 'Content-Type: application/json' \
  -d '{
    "node_id": "curl-node",
    "timestamp": "2026-09-25T10:00:00Z",
    "environment": {"temperature_C": 31.2, "humidity_pct": 68.5},
    "particulate_matter": {"PM1_0": 18.4, "PM2_5": 42.7, "PM10": 76.3},
    "gas_sensors": {
      "MQ2": {"raw_adc": 420, "voltage_V": 1.35},
      "MQ9": {"raw_adc": 510, "voltage_V": 1.64},
      "MQ135": {"raw_adc": 610, "voltage_V": 1.96}
    }
  }'
```

### Node status and latest

```bash
curl -s http://127.0.0.1:8420/api/v1/nodes/curl-node/status | python -m json.tool
curl -s http://127.0.0.1:8420/api/v1/nodes/curl-node/latest | python -m json.tool
curl -s http://127.0.0.1:8420/api/v1/nodes | python -m json.tool
```

`status` and `latest` return `404` until the same node ID has successfully submitted a reading after the current server process started.

After a successful submission, `/latest` returns the same compact intelligence
result as the POST response.

### SSE events

```bash
curl -N http://127.0.0.1:8420/api/v1/nodes/curl-node/events
```

Expected stream:

```text
event: connected
data: {}

event: new_reading
data: { ... }
```

The SSE summary is smaller than the full HTTP response. Use `/latest` for the persisted record.

### Forecast plugin

Generate and submit 48 hours of PM history through the normal reading path:

```bash
./venv/bin/python -m Simulator replay \
  Simulator/test_data/forecast_48h.jsonl \
  --interval 0.01 \
  --rebase-to-now
```

Request a forecast:

```bash
curl -s 'http://127.0.0.1:8420/api/v1/forecast/nodes/fixture-node-01/predict?horizon_minutes=60' | python -m json.tool
```

Inspect forecast history:

```bash
curl -s http://127.0.0.1:8420/api/v1/forecast/nodes/fixture-node-01/history | python -m json.tool
```

Clean expired forecast data:

```bash
curl -X POST 'http://127.0.0.1:8420/api/v1/forecast/cleanup?node_id=fixture-node-01'
```

### Source classifier

Source classification runs automatically during complete reading ingestion when artifacts are available. Exercise it with different synthetic profiles:

```bash
./venv/bin/python -m Simulator sample --node-id source-traffic --scenario traffic --send
./venv/bin/python -m Simulator sample --node-id source-dust --scenario heavy_dust --send
./venv/bin/python -m Simulator sample --node-id source-combustion --scenario combustion --send
./venv/bin/python -m Simulator sample --node-id source-mixed --scenario mixed_pollution --send
```

Read the response's:

```text
pipeline.source_classification.top_source
pipeline.source_classification.predictions
pipeline.source_classification.uncertainty
pipeline.source_classification.data_quality
```

These are pattern hypotheses, not confirmed physical source identities.

### Anomaly detection

Anomaly detection needs a sequence for its baseline. Send at least 10-30 samples:

```bash
./venv/bin/python -m Simulator start \
  --node-id anomaly-node \
  --scenario clean_background \
  --samples 30 \
  --interval 0.2
```

The response starts in `BOOTSTRAPPING`, then can progress through `CALIBRATING`, `LEARNING`, and `MONITORING`. Inspect:

```text
pipeline.anomaly_report.system_state
pipeline.anomaly_report.anomaly
pipeline.anomaly_report.sensor_evidence
pipeline.anomaly_report.explanations
```

## 7. Exact Classification Inputs

You can run a scenario or provide exact sensor values. The direct flags are available on `sample`, `start`, and `save`:

```text
--classification / --scenario
--temperature
--humidity
--pm1
--pm25
--pm10
--mq2
--mq9
--mq135
```

Example:

```bash
./venv/bin/python -m Simulator sample \
  --classification combustion \
  --temperature 31 \
  --humidity 45 \
  --pm1 55 \
  --pm25 120 \
  --pm10 160 \
  --mq2 2.8 \
  --mq9 2.1 \
  --mq135 2.5 \
  --send
```

Direct flags remain exact across samples. The simulator calculates raw ADC from MQ voltage, validates physical bounds, and enforces PM ordering. For evolving values, omit direct flags or combine profile values with:

```bash
--custom variation=0.2 --custom spike=0.1
```

## 8. Multiple Nodes

```bash
./venv/bin/python -m Simulator start \
  --node-id node-clean \
  --node-id node-traffic \
  --node-id node-dust \
  --scenario mixed_pollution \
  --samples 20 \
  --interval 1
```

For different profiles, run separate simulator processes with distinct node IDs:

```bash
./venv/bin/python -m Simulator start --node-id node-clean --scenario clean_background --samples 20 --interval 1
./venv/bin/python -m Simulator start --node-id node-traffic --scenario traffic --samples 20 --interval 1
```

## 9. Save, Replay, and Datasets

Save data:

```bash
./venv/bin/python -m Simulator save \
  --node-id saved-node \
  --scenario heavy_dust \
  --samples 20 \
  --interval 300 \
  --output /tmp/heavy-dust.jsonl
```

Replay it through the real ingestion route:

```bash
./venv/bin/python -m Simulator replay /tmp/heavy-dust.jsonl --interval 0.05
```

Checked-in datasets are located at:

```text
Simulator/test_data/
```

Regenerate them:

```bash
./venv/bin/python -m Simulator generate-datasets --output-dir Simulator/test_data
```

## 10. Tests

Run simulator tests:

```bash
./venv/bin/python -m pytest Simulator/tests -q
```

Run all backend tests:

```bash
./venv/bin/python -m pytest -q
```

Compile simulator files:

```bash
./venv/bin/python -m py_compile Simulator/*.py
```

## 11. Typical Complete Workflow

```text
1. Start the backend
       |
2. Wait for health/readiness
       |
3. Start one-shot or continuous simulator
       |
4. Server validates SensorPayload
       |
5. TinyGasNet runs gas inference
       |
6. ModularPipeline calculates health/advisory
       |
7. AnomalyEngine updates node baseline
       |
8. SourceClassifier ranks source hypotheses
       |
9. ForecastPlugin stores PM values
       |
10. JSONL storage persists the reading
       |
11. HTTP response and SSE event expose feedback
       |
12. Query status/latest/forecast for later inspection
```

## 12. Troubleshooting

### `python -m Simulator start` returns command or import errors

Use the server virtual environment and run from the server directory:

```bash
cd Intelligence/Server
./venv/bin/python -m Simulator start --samples 1
```

### Connection refused

Start the API first and wait for `Application startup complete`:

```bash
./venv/bin/python -m app.main
```

### `/status` or `/latest` returns 404

Submit a reading using the exact same node ID, then query again. Server restart clears the in-memory node registry.

### `422` response

The payload violates the backend schema. Use simulator-generated payloads or inspect the server error body. Common causes are invalid PM ordering, out-of-range humidity/temperature/voltage, invalid ADC, mismatched node ID, or a future timestamp.

### Model is not loaded

Check `/ready` and confirm these files exist:

```text
artifacts/gasnet.pt
artifacts/preprocess.pkl
```

The server can still accept telemetry without the model, but inference will report `not_configured`.

### Source classifier or forecast is unavailable

Check startup logs and artifacts/configuration. The main ingestion route continues even if optional enrichment fails.

## 13. Limitations

- Simulator data is synthetic and not physical measurement data.
- Source classifications are pattern matches, not proof of source identity.
- Forecasts are experimental.
- Node registry and SSE subscribers are in memory and reset on server restart.
- The simulator does not emulate actual electrical warm-up, wiring faults, or sensor calibration.
- The server currently has no authentication.
