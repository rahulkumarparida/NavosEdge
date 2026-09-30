# NavosEdge Phase 5 Hardware Simulator

## Purpose

`Intelligence/Server/Simulator` is a terminal-based synthetic hardware node for testing the existing Intelligence Server before connecting the Arduino UNO Q and physical sensors.

It generates readings in the exact `SensorPayload` shape accepted by the server, including:

- `node_id`
- `timestamp`
- `environment.temperature_C`
- `environment.humidity_pct`
- `particulate_matter.PM1_0`, `PM2_5`, `PM10`
- `gas_sensors.MQ2`, `MQ9`, and `MQ135` raw ADC and voltage values

The simulator does not add a synthetic field to the request payload because the current server schema does not define one. Synthetic provenance is recorded in simulator session output and in a `.meta.json` sidecar next to every saved dataset.

Synthetic readings are test patterns only. They are not physical measurements, validated sensor fingerprints, or source-classifier ground truth.

## Folder Structure

```text
Intelligence/Server/
├── Simulator/
│   ├── __init__.py       # Public simulator package exports
│   ├── __main__.py       # python -m Simulator entry point
│   ├── cli.py            # Terminal commands and fixture generation
│   ├── client.py         # HTTP client for the existing server routes
│   ├── generator.py      # Schema-valid scenario generation
│   ├── session.py        # Sessions, controls, saving, and replay
│   ├── test_data/        # Reproducible synthetic JSONL fixtures
│   └── tests/            # Simulator tests
└── phase5simulator.md
```

The simulator, its tests, fixtures, and this guide now live inside `Intelligence/Server`, alongside the server virtual environment.

## Running Commands

Run the simulator from `Intelligence/Server` so it uses the same virtual environment and imports the server application directly:

```bash
cd Intelligence/Server
./venv/bin/python -m Simulator list
```

If dependencies are not installed yet:

```bash
cd Intelligence/Server
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

Start the real Intelligence Server in another terminal:

```bash
cd Intelligence/Server
./venv/bin/python -m app.main
```

The default server URL is `http://127.0.0.1:8420`. Override it with `--server-url`.

## Available Scenarios

```text
clean_background   Stable background-like values with small variation
traffic            Changing gas and fine-particulate pattern
heavy_dust         Elevated coarse particulate pattern
construction       Variable dust with moderate gas response
combustion         Changing gas response and elevated fine PM
indoor_activity    Indoor temperature, humidity, PM, and gas variation
mixed_pollution    Overlapping particulate and gas patterns
random             Controlled broad random variation
custom             Base values overridden by --custom NAME=VALUE
```

Each scenario combines a broad profile, gradual sinusoidal movement, random noise, and occasional spikes. The profiles are deliberately synthetic and should not be interpreted as real source signatures.

## One-Shot Samples

Print one payload without sending it:

```bash
cd Intelligence/Server
./venv/bin/python -m Simulator sample \
  --node-id sim-node-01 \
  --scenario traffic \
  --seed 42
```

Submit one sample through the actual ingestion endpoint:

```bash
./venv/bin/python -m Simulator sample \
  --node-id sim-node-01 \
  --scenario clean_background \
  --send
```

The simulator uses these real routes:

```text
GET  /health
GET  /ready
POST /api/v1/nodes/{node_id}/readings
GET  /api/v1/nodes/{node_id}/status
GET  /api/v1/nodes/{node_id}/latest
```

Before a session starts, the client checks both `/health` and `/ready`. A session is rejected if either check fails or the readiness response has `ready=false`.

## Fixed-Count and Continuous Simulation

Generate and send 12 samples at five-second simulated intervals:

```bash
./venv/bin/python -m Simulator start \
  --node-id sim-node-01 \
  --scenario traffic \
  --interval 5 \
  --samples 12
```

Run continuously with `--samples 0` and stop with Ctrl+C:

```bash
./venv/bin/python -m Simulator start \
  --node-id sim-node-01 \
  --scenario mixed_pollution \
  --interval 5 \
  --samples 0
```

Run multiple simulated nodes concurrently. Each node has its own deterministic generator seed (`--seed`, then incremented per node):

```bash
./venv/bin/python -m Simulator start \
  --node-id sim-node-01 \
  --node-id sim-node-02 \
  --scenario construction \
  --interval 10 \
  --samples 20
```

Use the interactive controls for manual pause, resume, and stop:

```bash
./venv/bin/python -m Simulator start \
  --node-id sim-node-01 \
  --scenario traffic \
  --samples 0 \
  --interactive
```

At the `sim>` prompt enter `pause`, `resume`, or `stop`. Ctrl+C also stops the session gracefully.

The `--send/--no-send` switch controls network submission. `--verify` additionally queries status and latest after successful submissions:

```bash
./venv/bin/python -m Simulator start \
  --no-send \
  --samples 5 \
  --save /tmp/navos-sim.jsonl
```

## Custom Scenario Parameters

Custom parameters override profile values. Supported profile names include `temp`, `humidity`, `pm1`, `pm25`, `pm10`, `mq2`, `mq9`, `mq135`, `variation`, and `spike`:

```bash
./venv/bin/python -m Simulator sample \
  --scenario custom \
  --custom temp=35 \
  --custom humidity=45 \
  --custom pm25=70 \
  --custom pm10=150
```

Values remain bounded to the backend schema. PM ordering is enforced before validation.

## Saving Datasets

Save payloads locally without sending them:

```bash
./venv/bin/python -m Simulator save \
  --node-id fixture-node-01 \
  --scenario heavy_dust \
  --samples 24 \
  --interval 300 \
  --seed 20260925 \
  --output /tmp/heavy-dust.jsonl
```

This creates:

```text
/tmp/heavy-dust.jsonl
/tmp/heavy-dust.jsonl.meta.json
```

The JSONL contains only fields accepted by `SensorPayload`. The sidecar contains `synthetic=true`, `source_type=hardware_simulator`, record count, session information, and a warning that the records are not physical measurements.

## Replaying Datasets

Replay a saved complete-reading dataset through the normal backend ingestion route. Replay is accelerated by default and preserves each payload's timestamp sequence:

```bash
./venv/bin/python -m Simulator replay \
  /tmp/heavy-dust.jsonl \
  --server-url http://127.0.0.1:8420
```

Use a small delay between requests without waiting for timestamp gaps:

```bash
./venv/bin/python -m Simulator replay \
  /tmp/heavy-dust.jsonl \
  --interval 0.05
```

Use real-time timestamp gaps only for short datasets:

```bash
./venv/bin/python -m Simulator replay \
  /tmp/heavy-dust.jsonl \
  --real-time
```

The complete-reading route automatically forwards PM values to the server's existing `ForecastPlugin`, so replaying a time series exercises the same forecast ingestion path as hardware readings. The simulator does not write directly into forecast storage.

The client logs status codes and errors. `--on-error continue` records failures and continues; `--on-error stop` stops at the first rejected request. Connection errors, timeouts, HTTP validation errors, and server restarts are reported as failed submissions.

## Reading Server Feedback

The simulator prints the complete response for `sample --send`. For longer
sessions, use the server endpoints after the session:

```bash
curl -s http://127.0.0.1:8420/api/v1/nodes/sim-node-01/status | python -m json.tool
curl -s http://127.0.0.1:8420/api/v1/nodes/sim-node-01/latest | python -m json.tool
```

The `201` ingestion response contains these important feedback sections:

```text
inference.status                         Model availability/result
inference.gas_class                      Predicted gas class, when configured
inference.safety_status                  safe or unsafe model head result
inference.uncertainty                    Normalized model uncertainty
pipeline.health.status                   Sensor quality: ok/degraded/stale
pipeline.health.issues                   Hardware-quality warnings
pipeline.advisory.level                  NORMAL/CAUTION/WARNING/MAINTENANCE
pipeline.advisory.messages               Human-readable reasons
pipeline.anomaly_report.anomaly          Rich anomaly decision and score
pipeline.anomaly_report.system_state     BOOTSTRAPPING/.../MONITORING
pipeline.source_classification           Ranked source hypotheses
```

Interpret the response in this order:

1. Check the HTTP status. `201` means the reading was accepted; `400` means
  the URL and payload node IDs differ; `422` means the payload violates the
  server schema; connection errors mean the server could not be reached.
2. Check `inference.status`. `success` means model artifacts were loaded and
  a result was calculated. `not_configured` means telemetry was still
  accepted but the model was unavailable. `error` means inference failed for
  that reading.
3. Check `pipeline.health`. `ok` indicates no immediate quality issue;
  `degraded` or `stale` requires inspecting `issues` before trusting other
  interpretations.
4. Check `pipeline.advisory.level`. This is the server's deterministic
  qualitative action level, not a regulatory AQI measurement.
5. Check `anomaly_report.system_state`. Early simulator readings normally show
  `BOOTSTRAPPING` or `CALIBRATING`; collect a sequence before expecting
  `MONITORING` confidence.
6. Check `source_classification.predictions[0]`. `top_source` is a synthetic
  pattern match, not proof of a physical pollution source. Always inspect
  `uncertainty.is_uncertain` and `data_quality` alongside it.

For a compact feedback view, pipe the response through a small Python client:

```bash
./venv/bin/python - <<'PY'
import json
import urllib.request

url = "http://127.0.0.1:8420/api/v1/nodes/sim-node-01/latest"
with urllib.request.urlopen(url) as response:
   data = json.load(response)

pipeline = data["reading"].get("pipeline", {})
inference = data.get("inference") or {}
source = pipeline.get("source_classification") or {}
print("gas:", inference.get("gas_class"), inference.get("safety_status"))
print("advisory:", pipeline.get("advisory", {}).get("level"))
print("health:", pipeline.get("health", {}).get("status"))
print("top source:", source.get("top_source"))
print("uncertain:", (source.get("uncertainty") or {}).get("is_uncertain"))
PY
```

For live downstream consumers, subscribe to the existing per-node SSE stream:

```bash
curl -N http://127.0.0.1:8420/api/v1/nodes/sim-node-01/events
```

You will first receive `event: connected`, then `event: new_reading` summaries
after each accepted simulated reading, plus heartbeat comments. SSE summaries
are intentionally smaller than the HTTP response; use `/latest` when full
persisted record details are required.

## Reproducible Fixture Datasets

The checked-in fixtures are under `Intelligence/Server/Simulator/test_data/`:

| File | Purpose |
|---|---|
| `clean_background.jsonl` | Stable background-like sequence |
| `traffic.jsonl` | Traffic-like changing gas/PM sequence |
| `heavy_dust.jsonl` | Elevated particulate sequence |
| `combustion.jsonl` | Combustion-like gas/fine-PM sequence |
| `mixed_conditions.jsonl` | Mixed pollution-like sequence |
| `invalid_payload.jsonl` | Invalid humidity for HTTP validation testing |
| `timestamp_irregularities.jsonl` | Non-uniform timestamp gaps |
| `forecast_48h.jsonl` | 576 readings at five-minute spacing, representing 48 hours |

Every valid JSONL file has a `.meta.json` sidecar with the synthetic marker. The fixed seed is `20260925`, except where a command explicitly chooses another seed.

Regenerate the fixtures:

```bash
cd Intelligence/Server
./venv/bin/python -m Simulator generate-datasets \
  --output-dir Simulator/test_data
```

The invalid fixture is intentionally not accepted by `load_dataset()` and should be used to test server/client validation handling, not replayed as a valid series.

## Forecast Testing

The 48-hour fixture contains 48 hours at five-minute intervals:

```text
48 hours * 60 minutes / 5 minutes = 576 records
```

Replay it without waiting 48 hours:

```bash
./venv/bin/python -m Simulator replay \
  Simulator/test_data/forecast_48h.jsonl \
  --interval 0.01 \
  --rebase-to-now
```

Then request the server forecast:

```bash
curl 'http://127.0.0.1:8420/api/v1/forecast/nodes/fixture-node-01/predict?horizon_minutes=60'
```

The backend receives the records through `ProcessingService`, which calls `ForecastPlugin.async_ingest()`. The plugin stores PM-only records separately and applies its normal retention and validation behavior.

`--rebase-to-now` shifts every timestamp by the same amount so the newest fixture record is current. It preserves all intervals and ordering while making a checked-in historical fixture usable with the server's rolling 48-hour retention window. Without this option, the server correctly ignores records older than retention during forecast queries.

Useful forecast cases:

- **Insufficient history**: replay fewer than the configured minimum, normally 12 valid points per channel.
- **Gradual increase/decrease**: generate a custom or scenario dataset with changing PM profile and inspect `trend`.
- **Stable conditions**: use `clean_background.jsonl`.
- **Sudden spikes**: use `heavy_dust.jsonl` or generate a high `spike` custom profile.
- **Missing samples**: use `timestamp_irregularities.jsonl`; the forecast model handles irregular timestamps but assumes channel samples are available.
- **Expiration**: after replaying records with timestamps older than the configured retention period, call:

```bash
curl -X POST 'http://127.0.0.1:8420/api/v1/forecast/cleanup?node_id=fixture-node-01'
```

The server's default forecast retention is 48 hours. Cleanup is explicit; replay does not bypass the plugin or write around retention logic.

## Session Results and Logging

Each session reports a JSON object containing:

- session ID;
- scenario and synthetic marker;
- start/end time;
- generated, submitted, successful, failed, and saved counts;
- server errors;
- output dataset path when saved.

Simulator datasets are kept under `Simulator/test_data` or a caller-selected path, separate from `Server/artifacts`, model files, and physical hardware logs. Use clearly named `sim-*` or `fixture-*` node IDs. The server itself does not persist a synthetic marker because its current schema has no such field; avoid reusing real node IDs for simulator runs.

## Tests

Run the simulator tests:

```bash
cd Intelligence/Server
./venv/bin/python -m pytest Simulator/tests -q
```

The suite covers:

- all scenario payloads against the actual server Pydantic schema;
- fixed-seed reproducibility and evolving values;
- multi-node sessions;
- server readiness checks;
- pause/resume/stop lifecycle;
- continue/stop error policies;
- save/load and invalid dataset handling;
- replay ordering.

Run the complete Intelligence Server test suite:

```bash
cd Intelligence/Server
./venv/bin/python -m pytest -q
```

Expected simulator result at the time of writing: `17 passed`.

## Known Limitations

1. Synthetic provenance is external to the server payload because adding a field would change the current input contract.
2. The simulator does not emulate electrical warm-up, ADC quantization error beyond generated ADC values, sensor disconnection physics, or network streaming/SSE consumption.
3. Accelerated replay preserves timestamps but intentionally does not wait for the represented elapsed time.
4. Forecast data is ingested by the server's complete-reading processing path; the simulator does not directly invoke internal Python forecast objects.
5. The server's node registry, anomaly state, and SSE subscribers are process-local, so restarts reset those in-memory states.
6. Scenario profiles are synthetic test patterns and cannot establish source-classifier or forecast accuracy.
7. Multiple nodes are submitted concurrently within each sample round, but the server still controls its own request processing and storage concurrency.
