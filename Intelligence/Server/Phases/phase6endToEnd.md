# NavosEdge Phase 6: End-to-End Simulation

## Purpose

Phase 6 connects the synthetic hardware node to the complete Intelligence Server workflow with one command.

```text
Simulator
  -> /health and /ready
  -> SSE connection: server -> simulator
  -> HTTP POST readings: simulator -> server
  -> validation and processing
  -> TinyGasNet inference
  -> source classification
  -> anomaly and advisory processing
  -> PM forecast ingestion
  -> latest result and forecast query
  -> one aggregated JSON result
```

The simulator sends sensor data only with HTTP POST. SSE is never used for sensor data; it is used only for server-to-simulator connection confirmation and processed-reading events.

## Command

Start the server first:

```bash
cd Intelligence/Server
./venv/bin/python -m app.main
```

Then run the complete workflow in another terminal:

```bash
cd Intelligence/Server
./venv/bin/python -m Simulator e2e \
  --scenario traffic \
  --node-id e2e-node-01 \
  --count 3 \
  --interval 1
```

The equivalent direct module command exposes the full option set:

```bash
./venv/bin/python -m Simulator.e2e \
  --scenario traffic \
  --node-id e2e-node-01 \
  --count 3 \
  --accelerated
```

Use machine-readable output:

```bash
./venv/bin/python -m Simulator.e2e \
  --scenario combustion \
  --node-id e2e-combustion \
  --count 2 \
  --accelerated \
  --json
```

`--json` prints one JSON document without human-format indentation. It is suitable for piping to another program:

```bash
./venv/bin/python -m Simulator.e2e --scenario traffic --count 2 --accelerated --json | python -m json.tool
```

## Available Options

| Option | Default | Meaning |
|---|---:|---|
| `--server-url` | `http://127.0.0.1:8420` | Intelligence Server URL |
| `--node-id` | `e2e-node-01` | Simulated hardware node ID |
| `--scenario` | `traffic` | Synthetic scenario |
| `--count` | `1` | Number of readings |
| `--duration` | unset | Simulated session duration; determines count from interval |
| `--interval` | `5` | Seconds between readings when not accelerated |
| `--accelerated` | off | Send readings without waiting between them |
| `--json` | off | Compact machine-readable final output |
| `--seed` | `42` | Reproducible generator seed |
| `--noise` | `1.0` | Generated sensor noise |
| `--timeout` | `10` | HTTP/SSE timeout |
| `--horizon` | `60` | Forecast horizon in minutes |
| `--forecast-interval` | `5` | Forecast sampling interval in minutes |
| `--custom NAME=VALUE` | none | Profile override such as `variation=0.2` |
| `--temperature` | generated | Exact temperature override |
| `--humidity` | generated | Exact humidity override |
| `--pm1` | generated | Exact PM1.0 override |
| `--pm25` | generated | Exact PM2.5 override |
| `--pm10` | generated | Exact PM10 override |
| `--mq2` | generated | Exact MQ2 voltage override |
| `--mq9` | generated | Exact MQ9 voltage override |
| `--mq135` | generated | Exact MQ135 voltage override |

Example with exact classification inputs:

```bash
./venv/bin/python -m Simulator.e2e \
  --scenario combustion \
  --node-id exact-combustion \
  --count 2 \
  --accelerated \
  --temperature 31 \
  --humidity 45 \
  --pm1 55 \
  --pm25 120 \
  --pm10 160 \
  --mq2 2.8 \
  --mq9 2.1 \
  --mq135 2.5 \
  --json
```

## Connection and Handshake Sequence

The end-to-end command performs the following sequence:

1. Create an end-to-end session ID and synthetic node identity.
2. Call `GET /health`.
3. Call `GET /ready` and require `ready=true`.
4. Open `GET /api/v1/nodes/{node_id}/events` as an SSE stream.
5. Wait for the server's `event: connected` frame.
6. Generate a schema-valid sensor payload.
7. Submit it through `POST /api/v1/nodes/{node_id}/readings`.
8. Wait for the server to process inference, anomaly, classifier, advisory, storage, event publication, and forecast ingestion.
9. Collect SSE `new_reading` events.
10. Query `GET /api/v1/nodes/{node_id}/latest` for the final persisted reading.
11. Query `GET /api/v1/forecast/nodes/{node_id}/predict` for the full forecast result.
12. Stop the SSE task cleanly and print the final aggregated JSON.

The HTTP and SSE channels have separate roles:

```text
Simulator -> HTTP POST -> Server: sensor readings
Server -> SSE -> Simulator: connected/new_reading events
Simulator -> HTTP GET -> Server: latest and forecast results
```

## Final JSON Structure

The output combines existing server contracts rather than inventing a second processing pipeline:

The public ingestion and latest-reading APIs use the compact intelligence
contract. The E2E CLI wrapper may additionally include session and system
bookkeeping for command-line diagnostics; those fields are not part of the
public intelligence response.

```json
{
  "session": {
    "id": "...",
    "node_id": "e2e-node-01",
    "scenario": "traffic",
    "data_source": "synthetic",
    "samples_sent": 3
  },
  "sensor_data": {
    "aqi": null,
    "pm": {"PM1_0": 0.0, "PM2_5": 0.0, "PM10": 0.0},
    "temperature_C": 0.0,
    "humidity_pct": 0.0,
    "predictions": {
      "source": {"value": "TRAFFIC", "confidence": 0.78},
      "forecast": {"value": {"status": "insufficient_history", "PM1_0": [], "PM2_5": [], "PM10": []}, "confidence": 0.0}
    }
  },
  "source_classification": {
    "value": "TRAFFIC",
    "confidence": 0.78
  },
  "forecast": {
    "status": "insufficient_history",
    "channels": []
  },
  "advisory": {
    "severity": "HIGH",
    "advice": "...",
    "actions": [],
    "weather_advice": "..."
  },
  "system": {
    "server_connected": true,
    "ready": true,
    "sse_connected": true,
    "sse_events_received": 3,
    "processing_status": "completed"
  }
}
```

`forecast.status` is normalized to `insufficient_history` when the existing forecast API returns `insufficient_data`. No prediction is fabricated. After enough PM history exists, the actual forecast response contains `channels`, trends, predictions, reliability, and persistence baselines.

## Intelligence Processing

Every submitted reading follows the existing server path:

1. Pydantic validates ranges, PM ordering, node ID, and timestamp.
2. `ProcessingService` registers the node.
3. TinyGasNet receives MQ voltages, temperature, and humidity.
4. `ModularPipeline` calculates sensor health, EMA anomaly state, PM persistence, and advisory level.
5. The complete base record is stored in main JSONL storage.
6. `AnomalyEngine` updates the richer rolling baseline and report.
7. `SourceClassifier` extracts raw/derived features and ranks source hypotheses.
8. `ForecastPlugin` receives PM1.0/PM2.5/PM10 through its normal ingest path.
9. The server publishes a compact `new_reading` SSE event.
10. The E2E client reads the persisted latest record and requests the forecast API.

If artifacts are unavailable, the output reports the server's actual state, such as `inference.status=not_configured` or an unavailable source-classifier result. The rest of the pipeline continues where possible.

## Forecast Behavior

A short E2E run normally returns:

```json
"forecast": {
  "status": "insufficient_history",
  "reliability": "unavailable",
  "channels": []
}
```

This is expected because the forecast plugin needs a minimum history, normally 12 valid points per channel. To test a populated forecast, use the existing accelerated fixture replay first:

```bash
./venv/bin/python -m Simulator replay \
  Simulator/test_data/forecast_48h.jsonl \
  --interval 0.01 \
  --rebase-to-now

./venv/bin/python -m Simulator.e2e \
  --node-id fixture-node-01 \
  --count 1 \
  --accelerated \
  --json
```

The forecast is experimental and informational.

## Failure Handling

The command returns exit code `1` and a JSON or readable error result for:

- server unavailable during `/health`;
- readiness failure from `/ready`;
- SSE HTTP error or connection timeout;
- no `connected` SSE confirmation before timeout;
- invalid sensor payload rejected by the existing POST route;
- failed inference reported by the server;
- forecast unavailable or insufficient history;
- final latest-reading timeout or failure.

A typical failure result is:

```json
{
  "error": "server unavailable during health check: ...",
  "session": {
    "node_id": "e2e-node-01",
    "data_source": "synthetic"
  },
  "system": {
    "server_connected": false,
    "sse_connected": false,
    "processing_status": "failed"
  }
}
```

## End-to-End Test

Run the isolated fake-client E2E contract test:

```bash
./venv/bin/python -m pytest Simulator/tests/test_e2e.py -q
```

Run the live test that starts the actual FastAPI server, opens the actual SSE endpoint, sends actual HTTP readings, queries the actual forecast endpoint, and shuts the server down:

```bash
./venv/bin/python -m pytest Simulator/tests/test_e2e_live.py -q
```

Run all simulator tests:

```bash
./venv/bin/python -m pytest Simulator/tests -q
```

The live test uses an isolated port and temporary data directory. It does not modify the normal runtime data or require another manually running server.

## Synthetic Data Limitations

- All readings are synthetic.
- Scenario names describe test patterns, not validated real-world signatures.
- Source classification is a pattern hypothesis, not chemical identification.
- Forecasts are experimental and need real-world validation.
- The server's node registry and SSE subscribers are in memory and reset on restart.
- The E2E workflow reuses server APIs and does not bypass validation or write directly to storage.
