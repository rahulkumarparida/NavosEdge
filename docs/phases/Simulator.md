# NavosEdge Hardware Simulator

## What It Is

The simulator behaves like one or more NavosEdge sensor nodes. It generates synthetic readings using the same JSON payload accepted by the Intelligence Server and sends them through the real HTTP ingestion route.

It simulates:

- DHT22-style temperature and humidity values
- MQ2, MQ9, and MQ135 ADC and voltage values
- PM1.0, PM2.5, and PM10 values
- Changing environmental scenarios, noise, gradual movement, and occasional spikes
- Multiple nodes sending concurrently
- Fixed-count or continuous sessions
- Dataset saving and replay

All generated values are synthetic. They are not physical measurements and must not be treated as validated pollution-source fingerprints or model ground truth.

The public intelligence response is intentionally compact: AQI (currently
`null` because no approved AQI formula exists in this project), PM values,
temperature, humidity, and source/forecast predictions containing only value
and confidence.

## Location and Environment

The simulator is inside the server project so it uses the same virtual environment and server schemas:

```text
Intelligence/Server/
├── app/
├── Simulator/
│   ├── __main__.py
│   ├── cli.py
│   ├── client.py
│   ├── generator.py
│   ├── session.py
│   ├── test_data/
│   ├── tests/
│   └── Simulator.md
├── artifacts/
├── data/
├── requirements.txt
└── venv/
```

Always run commands from `Intelligence/Server`:

```bash
cd Intelligence/Server
```

Use the installed server virtual environment:

```bash
./venv/bin/python -m Simulator --help
```

## Start the Server First

In terminal 1:

```bash
cd Intelligence/Server
./venv/bin/python -m app.main
```

Wait until the log contains:

```text
Application startup complete.
Uvicorn running on http://0.0.0.0:8420
```

The server loads model artifacts during startup. The startup can take several seconds because TinyGasNet and the source classifier are loaded before the API becomes ready.

Check readiness in terminal 2:

```bash
curl -s http://127.0.0.1:8420/health | python -m json.tool
curl -s http://127.0.0.1:8420/ready | python -m json.tool
```

Expected readiness fields include:

```json
{
  "ready": true,
  "storage_ok": true,
  "model_loaded": true
}
```

The simulator performs these checks automatically before a session that sends data.

## List Scenarios

```bash
./venv/bin/python -m Simulator list
```

Available scenarios:

- `clean_background`
- `traffic`
- `heavy_dust`
- `construction`
- `combustion`
- `indoor_activity`
- `mixed_pollution`
- `random`
- `custom`

Scenarios are broad synthetic patterns. They are useful for exercising server branches, not for proving that a real-world source produces the same sensor response.

The CLI also accepts `--classification` as an alias for `--scenario`:

```bash
./venv/bin/python -m Simulator sample \
  --classification combustion
```

## Generate One Sample

Print a payload without sending it:

```bash
./venv/bin/python -m Simulator sample \
  --node-id sim-node-01 \
  --scenario traffic \
  --seed 42
```

This prints only fields accepted by the server:

```json
{
  "node_id": "sim-node-01",
  "timestamp": "2026-09-25T...+00:00",
  "environment": {
    "temperature_C": 32.4,
    "humidity_pct": 49.1
  },
  "particulate_matter": {
    "PM1_0": 20.2,
    "PM2_5": 48.0,
    "PM10": 79.4
  },
  "gas_sensors": {
    "MQ2": {"raw_adc": 280, "voltage_V": 1.37},
    "MQ9": {"raw_adc": 390, "voltage_V": 1.91},
    "MQ135": {"raw_adc": 340, "voltage_V": 1.66}
  }
}
```

Submit one reading:

```bash
./venv/bin/python -m Simulator sample \
  --node-id sim-node-01 \
  --scenario traffic \
  --seed 42 \
  --send
```

`sample --send` prints the full HTTP response, including inference and pipeline results.

## Set Exact Sensor Values

For classification experiments, override individual generated values directly.
These flags are available on `sample`, `start`, and `save`:

```text
--temperature C       environment.temperature_C
--humidity PCT        environment.humidity_pct
--pm1 VALUE           particulate_matter.PM1_0
--pm25 VALUE          particulate_matter.PM2_5
--pm10 VALUE          particulate_matter.PM10
--mq2 VOLTS           gas_sensors.MQ2.voltage_V
--mq9 VOLTS           gas_sensors.MQ9.voltage_V
--mq135 VOLTS         gas_sensors.MQ135.voltage_V
```

Example: send a combustion-like input with explicit values:

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

Direct flags are exact values: scenario wave, noise, and spikes do not change
the fields supplied with these flags. The simulator calculates each MQ
`raw_adc` value from the supplied voltage, keeps all values within the server's
physical bounds, and enforces PM ordering before validating the payload. Use
`--custom NAME=VALUE` for evolving profile values or for setting `variation`
and `spike`:

```bash
./venv/bin/python -m Simulator start \
  --scenario custom \
  --temperature 35 \
  --humidity 40 \
  --pm1 20 \
  --pm25 80 \
  --pm10 180 \
  --mq2 1.5 \
  --mq9 2.2 \
  --mq135 1.9 \
  --custom variation=0.2 \
  --samples 10 \
  --interval 2
```

## Run a Session

Send 10 readings at five-second intervals:

```bash
./venv/bin/python -m Simulator start \
  --node-id sim-node-01 \
  --scenario traffic \
  --interval 5 \
  --samples 10
```

Run continuously until Ctrl+C:

```bash
./venv/bin/python -m Simulator start \
  --node-id sim-node-01 \
  --scenario mixed_pollution \
  --interval 5 \
  --samples 0
```

Use multiple nodes:

```bash
./venv/bin/python -m Simulator start \
  --node-id sim-node-01 \
  --node-id sim-node-02 \
  --scenario construction \
  --interval 5 \
  --samples 20
```

The nodes are generated and submitted concurrently for each sample round.

Use interactive controls:

```bash
./venv/bin/python -m Simulator start \
  --node-id sim-node-01 \
  --scenario traffic \
  --samples 0 \
  --interactive
```

At the prompt:

```text
pause
resume
stop
```

## Terminal Feedback

For every accepted reading, `start` prints a line like:

```text
[ACCEPTED] node=sim-node-01 http=201 reading_id=abc123 gas=CleanAir safety=safe health=ok advisory=NORMAL anomaly=False source=TRAFFIC
```

The fields mean:

| Field | Meaning |
|---|---|
| `http=201` | The server accepted and processed the reading |
| `reading_id` | Server-generated identifier for this reading |
| `gas` | TinyGasNet predicted gas class |
| `safety` | Model safety result: `safe` or `unsafe` |
| `health` | Immediate sensor quality: `ok`, `degraded`, or `stale` |
| `advisory` | Deterministic server level: `NORMAL`, `CAUTION`, `WARNING`, or `MAINTENANCE` |
| `anomaly` | Rich anomaly detector decision |
| `source` | Top source pattern hypothesis, not confirmed ground truth |

For a failed request, the simulator prints:

```text
[FAILED] node=sim-node-01 status=422 error=HTTP 422
```

For `--verify`, it also prints:

```text
[VERIFY] node=sim-node-01 status_http=200 latest_http=200
```

This confirms that the node registry and latest-reading endpoint can see the accepted reading.

## Why Status or Latest Can Return 404

These responses are normal when no reading has been accepted for that node:

```text
GET /api/v1/nodes/sim-node-01/status 404 Not Found
GET /api/v1/nodes/sim-node-01/latest 404 Not Found
```

Common causes:

1. The simulator has not sent a reading yet.
2. The simulator used a different node ID.
3. The server was restarted, which clears the in-memory node registry.
4. Every submission failed validation or connection checks.

Correct order:

```bash
# Start server
./venv/bin/python -m app.main

# Send at least one reading
./venv/bin/python -m Simulator sample --node-id sim-node-01 --send

# Query the same node ID
curl -s http://127.0.0.1:8420/api/v1/nodes/sim-node-01/status | python -m json.tool
curl -s http://127.0.0.1:8420/api/v1/nodes/sim-node-01/latest | python -m json.tool
```

The SSE endpoint is different. It usually returns `200` immediately because it opens a long-lived stream, even if no reading has arrived yet:

```bash
curl -N http://127.0.0.1:8420/api/v1/nodes/sim-node-01/events
```

You should see `event: connected`, followed by `event: new_reading` after submissions. Heartbeat comments keep the connection alive.

## Inspect Complete Feedback

The full response from the ingestion endpoint contains:

```text
inference.status
inference.gas_class
inference.class_confidence
inference.safety_status
inference.uncertainty
pipeline.health
pipeline.anomaly
pipeline.forecast
pipeline.advisory
pipeline.anomaly_report
pipeline.source_classification
```

Inspect the latest persisted server record:

```bash
curl -s http://127.0.0.1:8420/api/v1/nodes/sim-node-01/latest | python -m json.tool
```

Interpret it in this order:

1. `inference.status`: `success` means the model ran; `not_configured` means the server accepted the reading without model artifacts; `error` means inference failed.
2. `pipeline.health`: check sensor-quality warnings before trusting analysis.
3. `pipeline.advisory.level`: qualitative action guidance, not regulatory AQI.
4. `pipeline.anomaly_report.system_state`: early readings are normally `BOOTSTRAPPING` or `CALIBRATING`.
5. `pipeline.source_classification.top_source`: a pattern match only. Check uncertainty and data quality too.

## Save and Replay Data

Save local synthetic readings:

```bash
./venv/bin/python -m Simulator save \
  --node-id fixture-node-01 \
  --scenario heavy_dust \
  --samples 20 \
  --interval 300 \
  --output /tmp/heavy-dust.jsonl
```

This creates a JSONL file and a `.meta.json` file marking it as synthetic.

Replay through the normal server ingestion route:

```bash
./venv/bin/python -m Simulator replay \
  /tmp/heavy-dust.jsonl \
  --interval 0.05
```

Use the checked-in 48-hour fixture for forecast testing:

```bash
./venv/bin/python -m Simulator replay \
  Simulator/test_data/forecast_48h.jsonl \
  --interval 0.01 \
  --rebase-to-now
```

`--rebase-to-now` preserves the timestamp intervals but moves the newest timestamp to the current time, allowing the server's normal 48-hour forecast retention window to include the data.

Then query the forecast:

```bash
curl -s 'http://127.0.0.1:8420/api/v1/forecast/nodes/fixture-node-01/predict?horizon_minutes=60' | python -m json.tool
```

The simulator does not write directly to forecast storage. It sends complete readings through `/api/v1/nodes/{node_id}/readings`, and the server's `ProcessingService` forwards PM values to the normal `ForecastPlugin`.

## Test Fixtures

Fixtures are in `Simulator/test_data/`:

- `clean_background.jsonl`
- `traffic.jsonl`
- `heavy_dust.jsonl`
- `combustion.jsonl`
- `mixed_conditions.jsonl`
- `invalid_payload.jsonl`
- `timestamp_irregularities.jsonl`
- `forecast_48h.jsonl`

Regenerate them:

```bash
./venv/bin/python -m Simulator generate-datasets --output-dir Simulator/test_data
```

## Run Tests

Simulator tests:

```bash
./venv/bin/python -m pytest Simulator/tests -q
```

Full backend tests:

```bash
./venv/bin/python -m pytest -q
```

The simulator tests cover payload compatibility, scenarios, reproducibility, multi-node sessions, pause/resume/stop, save/load, replay, invalid data, and server-unavailable behavior.

## Runtime Flow

```text
ScenarioGenerator
      |
      v
Schema-compatible payload
      |
      v
SimulationSession
      |
      +--> health/readiness checks
      +--> POST /api/v1/nodes/{node_id}/readings
      +--> print response feedback
      +--> optional status/latest verification
      +--> optional JSONL save
      |
      v
Intelligence Server
      |
      +--> validate payload
      +--> run TinyGasNet inference
      +--> run health/anomaly/advisory pipeline
      +--> run source classification
      +--> ingest PM into forecast plugin
      +--> store reading
      +--> publish SSE event
```

## Important Limitations

- Simulator values are synthetic and not physical measurements.
- Source-classifier output is not proof of a real pollution source.
- Forecasts are experimental.
- Node status is held in server memory and is reset when the server restarts.
- The simulator does not emulate electrical sensor warm-up or hardware faults.
- The complete HTTP response can contain richer post-processing than the persisted latest record because of the current server processing order.
