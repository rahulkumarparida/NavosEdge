# NavosEdge Phase Runbook

This is the operational guide for running NavosEdge through the API, CLI, simulator, and complete end-to-end workflow.

All commands below assume:

```bash
cd Intelligence/Server
```

The project virtual environment is `Intelligence/Server/venv`.

## 1. Architecture

```text
Arduino UNO Q or Simulator
        |
        | SensorPayload JSON over HTTP POST
        v
Intelligence Server
        |
        +--> Pydantic input validation
        +--> TinyGasNet inference
        +--> Sensor/PM processing
        +--> Source classifier
        +--> Forecast plugin/history
        +--> Deterministic advisory engine
        +--> JSONL storage
        +--> SSE event publication
        |
        v
Compact IntelligenceResult JSON
```

The simulator and physical hardware use the same input contract. The server does not have a separate simulated-data pipeline.

## 2. Install and Start

Create/install the environment if necessary:

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

Start the server:

```bash
./venv/bin/python -m app.main
```

The API listens on:

```text
http://127.0.0.1:8420
```

Wait for:

```text
Application startup complete.
Uvicorn running on http://0.0.0.0:8420
```

Startup loads the gas model, source classifier artifacts, and forecast plugin. Startup can take several seconds.

### Port already in use

If startup exits with code `3` or reports that port `8420` is already in use:

```bash
ss -ltnp | grep 8420
```

Stop the old process, or run the server on another port:

```bash
NAVOS_PORT=8421 ./venv/bin/python -m app.main
```

Then pass the same URL to the simulator:

```bash
./venv/bin/python -m Simulator e2e --server-url http://127.0.0.1:8421
```

## 3. Health and Readiness API

### Liveness

```bash
curl -s http://127.0.0.1:8420/health | python -m json.tool
```

Example response:

```json
{
  "status": "ok",
  "version": "0.1.0",
  "timestamp": "..."
}
```

### Readiness

```bash
curl -s http://127.0.0.1:8420/ready | python -m json.tool
```

Example response:

```json
{
  "ready": true,
  "storage_ok": true,
  "model_loaded": true,
  "timestamp": "..."
}
```

`ready` currently depends on writable storage. `model_loaded` separately reports gas-model availability.

## 4. Complete Sensor Input Contract

Hardware and simulator send this shape to:

```text
POST /api/v1/nodes/{node_id}/readings
```

```json
{
  "node_id": "node-01",
  "timestamp": "2026-09-25T10:30:00Z",
  "environment": {
    "temperature_C": 31.2,
    "humidity_pct": 68.5
  },
  "particulate_matter": {
    "PM1_0": 18.4,
    "PM2_5": 42.7,
    "PM10": 76.3
  },
  "gas_sensors": {
    "MQ2": {"raw_adc": 420, "voltage_V": 1.35},
    "MQ9": {"raw_adc": 510, "voltage_V": 1.64},
    "MQ135": {"raw_adc": 610, "voltage_V": 1.96}
  }
}
```

Validation includes:

- Node ID format and URL/payload node-ID equality
- Temperature `-40..85`
- Humidity `0..100`
- ADC `0..1023`
- Voltage `0..5`
- Non-negative PM values
- PM ordering: `PM1_0 <= PM2_5 <= PM10` with the server tolerance
- Timestamp not more than 24 hours in the future

## 5. Complete Reading API Flow

Request:

```bash
curl -X POST http://127.0.0.1:8420/api/v1/nodes/node-01/readings \
  -H 'Content-Type: application/json' \
  -d @payload.json
```

Communication sequence:

```text
Client -> POST SensorPayload
Server -> validate payload
Server -> inference using MQ voltages, temperature, humidity
Server -> PM/environment processing
Server -> source classification using gas, PM, temperature, humidity
Server -> append PM history to forecast plugin
Server -> generate forecast when enough history exists
Server -> evaluate advisory from compact intelligence data
Server -> store internal JSONL record
Server -> return IntelligenceResult
```

The public response is compact:

```json
{
  "aqi": null,
  "pm": {
    "PM1_0": 18.4,
    "PM2_5": 42.7,
    "PM10": 76.3
  },
  "temperature_C": 31.2,
  "humidity_pct": 68.5,
  "predictions": {
    "source": {
      "value": "TRAFFIC",
      "confidence": 0.78
    },
    "forecast": {
      "value": {
        "status": "insufficient_data",
        "PM1_0": [],
        "PM2_5": [],
        "PM10": []
      },
      "confidence": 0.0
    }
  },
  "advisory": {
    "severity": "HIGH",
    "advice": "...",
    "actions": [],
    "weather_advice": "..."
  }
}
```

The server currently has no approved AQI formula or breakpoint table, so `aqi` remains `null`. No AQI value is fabricated.

## 6. Node Status, Latest, and SSE

### List nodes

```bash
curl -s http://127.0.0.1:8420/api/v1/nodes | python -m json.tool
```

### Node status

```bash
curl -s http://127.0.0.1:8420/api/v1/nodes/node-01/status | python -m json.tool
```

This is operational metadata and includes node count/status and model availability. It is not part of the compact intelligence result.

### Latest compact result

```bash
curl -s http://127.0.0.1:8420/api/v1/nodes/node-01/latest | python -m json.tool
```

After a successful reading, `/latest` returns the same compact result shape as the POST response.

### SSE stream

```bash
curl -N http://127.0.0.1:8420/api/v1/nodes/node-01/events
```

SSE is server-to-client only:

```text
Server -> SSE connected event
Server -> SSE new_reading event after processing
Server -> SSE heartbeat comments
```

Sensor data is never sent through SSE. The client sends sensor data through HTTP POST.

A `200` SSE response means the stream was opened. `/status` and `/latest` can still return `404` until a reading has been accepted for that node in the current server process.

## 7. Forecast API

The complete reading route automatically forwards PM1.0, PM2.5, and PM10 into the forecast plugin.

### Direct forecast ingestion

```bash
curl -X POST http://127.0.0.1:8420/api/v1/forecast/nodes/node-01/readings \
  -H 'Content-Type: application/json' \
  -d '{
    "node_id": "node-01",
    "timestamp": "2026-09-25T10:30:00Z",
    "PM1_0": 18.4,
    "PM2_5": 42.7,
    "PM10": 76.3,
    "is_synthetic": true
  }'
```

### Forecast prediction

```bash
curl -s 'http://127.0.0.1:8420/api/v1/forecast/nodes/node-01/predict?horizon_minutes=60&sampling_interval_minutes=5' | python -m json.tool
```

### Forecast history

```bash
curl -s http://127.0.0.1:8420/api/v1/forecast/nodes/node-01/history | python -m json.tool
```

### Forecast cleanup

```bash
curl -X POST 'http://127.0.0.1:8420/api/v1/forecast/cleanup?node_id=node-01'
```

Forecast status can be `insufficient_data` when history is too short. The E2E CLI presents this as `insufficient_history`. Predictions are not fabricated.

## 8. Simulator CLI

List scenarios:

```bash
./venv/bin/python -m Simulator list
```

Generate one local payload without sending:

```bash
./venv/bin/python -m Simulator sample \
  --node-id sim-node-01 \
  --scenario traffic
```

Send one reading:

```bash
./venv/bin/python -m Simulator sample \
  --node-id sim-node-01 \
  --scenario traffic \
  --send
```

Run a fixed session:

```bash
./venv/bin/python -m Simulator start \
  --node-id sim-node-01 \
  --scenario combustion \
  --samples 10 \
  --interval 1
```

Run continuously:

```bash
./venv/bin/python -m Simulator start \
  --node-id sim-node-01 \
  --scenario traffic \
  --samples 0 \
  --interval 5
```

Use multiple nodes:

```bash
./venv/bin/python -m Simulator start \
  --node-id sim-node-01 \
  --node-id sim-node-02 \
  --scenario mixed_pollution \
  --samples 20 \
  --interval 1
```

The normal CLI prints feedback such as:

```text
[ACCEPTED] node=sim-node-01 http=201 PM2.5=42.7 source=TRAFFIC source_confidence=0.78 forecast_confidence=0.0
```

## 9. Exact Sensor Values Through CLI

Use exact inputs for controlled model/advisory experiments:

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

Available direct overrides:

```text
--temperature
--humidity
--pm1
--pm25
--pm10
--mq2
--mq9
--mq135
```

The simulator calculates MQ raw ADC from supplied voltage. Direct values remain exact; omitted values continue to follow the selected scenario.

## 10. One-Command End-to-End Workflow

Start the server in terminal 1:

```bash
./venv/bin/python -m app.main
```

Run the complete workflow in terminal 2:

```bash
./venv/bin/python -m Simulator e2e \
  --scenario traffic \
  --node-id e2e-node-01 \
  --count 10 \
  --interval 1
```

Machine-readable output:

```bash
./venv/bin/python -m Simulator.e2e \
  --scenario combustion \
  --node-id e2e-node-01 \
  --count 2 \
  --accelerated \
  --json
```

The E2E CLI performs:

```text
health -> ready -> SSE connected -> HTTP POST readings
-> source classifier -> forecast ingest/prediction
-> advisory engine -> latest result -> final JSON
```

The final E2E wrapper includes session/system bookkeeping for the CLI. The server's public intelligence result remains the compact response described above.

## 11. Save and Replay Datasets

Save synthetic data:

```bash
./venv/bin/python -m Simulator save \
  --node-id saved-node \
  --scenario heavy_dust \
  --samples 20 \
  --interval 300 \
  --output /tmp/heavy-dust.jsonl
```

Replay through the normal complete ingestion endpoint:

```bash
./venv/bin/python -m Simulator replay \
  /tmp/heavy-dust.jsonl \
  --interval 0.05
```

Replay the 48-hour forecast fixture:

```bash
./venv/bin/python -m Simulator replay \
  Simulator/test_data/forecast_48h.jsonl \
  --interval 0.01 \
  --rebase-to-now
```

## 12. Advisory Engine Directly

The advisory engine accepts the compact intelligence input and returns only:

```json
{
  "severity": "HIGH",
  "advice": "...",
  "actions": [],
  "weather_advice": "..."
}
```

Run it from Python:

```bash
./venv/bin/python - <<'PY'
from app.advisory import AdvisoryEngine

input_data = {
    "aqi": 142,
    "pm": {"PM1_0": 35.2, "PM2_5": 82.4, "PM10": 141.3},
    "temperature_C": 31.2,
    "humidity_pct": 68.5,
    "predictions": {
        "source": {"value": "TRAFFIC", "confidence": 0.78},
        "forecast": {
            "value": {"PM1_0": [35, 38], "PM2_5": [82, 95], "PM10": [141, 170]},
            "confidence": 0.71,
        },
    },
}
print(AdvisoryEngine().evaluate(input_data))
PY
```

The server calls this engine automatically inside final response aggregation. The classifier and forecast model remain independent.

## 13. Tests

Run all tests:

```bash
./venv/bin/python -m pytest -q
```

Run advisory tests only:

```bash
./venv/bin/python -m pytest tests/test_advisory.py -q
```

Run simulator and E2E tests:

```bash
./venv/bin/python -m pytest Simulator/tests -q
```

Compile the application:

```bash
./venv/bin/python -m py_compile app/services/*.py app/advisory/*.py Simulator/*.py
```

## 14. Communication Summary

| Sender | Receiver | Transport | Data |
|---|---|---|---|
| Hardware | Intelligence Server | HTTP POST | Complete `SensorPayload` |
| Simulator | Intelligence Server | HTTP POST | Same `SensorPayload` |
| Simulator | Intelligence Server | GET | Health/readiness/status/latest/forecast requests |
| Intelligence Server | Simulator/client | SSE | Connection and processed-reading events |
| ProcessingService | TinyGasNet | Python call | MQ voltages, temperature, humidity |
| ProcessingService | SourceClassifier | Python call | Validated sensor payload |
| ProcessingService | ForecastPlugin | Python call | PM1.0, PM2.5, PM10 history |
| Aggregation layer | AdvisoryEngine | Python call | Compact intelligence input |
| Server | Client | HTTP response | Compact intelligence result |

## 15. Troubleshooting

### Server exits with code 3

Usually the port is already in use:

```bash
ss -ltnp | grep 8420
```

Use another port with `NAVOS_PORT=8421` and update the simulator `--server-url`.

### Status/latest returns 404

Send a successful reading first and use the exact same node ID. The node registry is in memory and resets after server restart.

### Simulator reports connection refused

Start the server and wait for `Application startup complete` before running the simulator.

### HTTP 422

The payload failed schema validation. Check PM ordering, sensor bounds, timestamp, and URL/payload node ID equality.

### Forecast insufficient history

This is expected for short sessions. Replay the 48-hour fixture or submit at least the configured minimum history.

### Model unavailable

The server continues processing telemetry, but source/inference confidence may be unavailable. Check `/ready` and startup artifact logs.

## 16. Synthetic Data Notice

Simulator data is synthetic. It is not a physical measurement, validated pollution fingerprint, AQI ground truth, or proof of a real-world pollution source. Use real hardware data for final validation.
