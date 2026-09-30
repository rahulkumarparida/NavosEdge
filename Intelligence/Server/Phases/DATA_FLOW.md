# NavosEdge Intelligence Architecture and Data Flow

This document describes how data moves through `Intelligence/`, what each component in `Server/app/` does, when each component runs, and how the components work independently and together.

The implementation is an edge-oriented FastAPI service. It receives validated environmental telemetry from hardware or a simulator, performs several kinds of analysis, stores the result in local JSONL files, and exposes synchronous API responses, node status, forecast APIs, and per-node Server-Sent Events (SSE).

## 1. System Purpose

The Intelligence server sits between sensor-producing hardware and a future dashboard or other consumer:

```text
Hardware / Simulator
        |
        | HTTP JSON telemetry
        v
FastAPI API layer
        |
        v
Sensor validation -> ProcessingService
        |
        +--> TinyGasNet gas inference
        +--> Modular health/anomaly/persistence/advisory pipeline
        +--> Main full-reading JSONL store
        +--> Stateful multi-sensor anomaly engine
        +--> Source classifier
        +--> Forecast PM store/plugin
        +--> Per-node SSE event stream
        |
      +--> Compact HTTP intelligence response
```

The server is designed for local or VLAN deployment. It currently has no authentication, no database server, and no global event stream.

## 2. Main Runtime Components

The application is assembled in `Server/app/main.py` during the FastAPI lifespan startup:

| Component | Runtime role | State lifetime |
|---|---|---|
| `JsonlStorageService` | Stores complete sensor records | Filesystem, survives restart |
| `TinyGasNetAdapter` | Classifies gas sensor/environment features | Model loaded in memory; artifacts on disk |
| `AnomalyEngine` | Stateful multi-sensor anomaly detection | In memory; history is reloaded per node on first use |
| `SourceClassifier` | Estimates broad possible pollution/source categories | Model/statistics in memory; artifacts on disk |
| `NodeRegistry` | Tracks nodes seen during the current process | In memory only |
| `EventService` | Publishes node-specific SSE messages | In memory only |
| `ForecastPlugin` | Stores PM history and creates short-term forecasts | PM files on disk plus plugin state |
| `ProcessingService` | Coordinates the complete reading workflow | In memory; owns per-node priming set |
| `ModularPipeline` | Performs fast health, feature, EMA, persistence and advisory logic | In memory per node |

At startup the server creates `data/` and `artifacts/` if needed, loads the available artifacts, initializes the forecast plugin when enabled, and stores all services on `app.state` for route handlers.

At shutdown the forecast plugin is shut down. The main JSONL storage and in-memory services do not require a separate flush protocol because writes are completed before the request continues.

## 3. End-to-End Sensor Reading Flow

The primary workflow is:

`POST /api/v1/nodes/{node_id}/readings`

### 3.1 Request enters FastAPI

1. The payload-size middleware checks the optional `Content-Length` header. Payloads above `MAX_PAYLOAD_BYTES` are rejected with HTTP `413`.
2. FastAPI/Pydantic parses the JSON into `SensorPayload`.
3. Validation checks:
   - `node_id` is 1-64 characters and matches the allowed identifier pattern.
   - Temperature is between `-40` and `85` degrees C.
   - Humidity is between `0` and `100` percent.
   - MQ ADC values are between `0` and `1023`.
   - MQ voltages are between `0` and `5` V.
   - PM values are non-negative and approximately ordered as `PM1.0 <= PM2.5 <= PM10` with a `0.5` tolerance.
   - The timestamp is not more than 24 hours in the future.
4. The route verifies that the URL `node_id` equals the payload `node_id`. A mismatch returns HTTP `400`.

Validation errors are converted into the common `ErrorResponse` shape with HTTP `422`. Unexpected exceptions are logged and returned as HTTP `500`.

### 3.2 ProcessingService begins

`ProcessingService.process_reading()` creates a 12-character hexadecimal `reading_id`, reads the node ID and timestamp, and immediately registers the reading with `NodeRegistry`.

The registry updates or creates an in-memory `NodeInfo` record containing:

- first-seen timestamp;
- latest timestamp received;
- total readings received during this process lifetime;
- active status.

This registry update happens before inference or storage. Therefore a failed later stage can still cause the node to appear in the in-memory node list.

### 3.3 TinyGasNet inference

The inference adapter receives five model inputs:

```text
[MQ2 voltage, MQ9 voltage, MQ135 voltage, temperature, humidity]
```

When `gasnet.pt` and `preprocess.pkl` are available and compatible:

1. The preprocessing scaler transforms the five values.
2. The `TinyGasNet` model runs 20 forward passes with dropout enabled (MC-Dropout).
3. Class logits are temperature-scaled and converted to probabilities.
4. The safety head is converted to a safe/unsafe probability.
5. The adapter returns the predicted gas class, confidence and all class probabilities, safety status and confidence, normalized predictive entropy as uncertainty, and inference duration.

If dependencies or artifacts are missing, `predict()` returns `status=not_configured` with null prediction fields. If runtime inference fails, it returns `status=error`. The reading is still allowed to continue.

### 3.4 ModularPipeline processing

The fast `ModularPipeline.process()` stage runs these operations in order:

1. **Health check**
   - marks readings older than one hour as stale;
   - detects MQ voltages railed near ground or VCC;
   - detects temperature/humidity near hardware limits;
   - produces `ok`, `degraded`, or `stale` status and issue messages.
2. **Feature extraction**
   - copies MQ voltages, temperature, humidity, and PM values into a flat feature dictionary.
3. **EMA anomaly check**
   - tracks MQ2, MQ9, MQ135 and PM2.5 per node;
   - compares the current value with an exponentially weighted baseline;
   - reports a deviation above three standard deviations;
   - dampens baseline updates when a value is anomalous.
4. **Persistence PM baseline**
   - returns the previous PM2.5 and PM10 values as the next-reading baseline when prior history exists;
   - updates the per-node last-PM state.
5. **Deterministic advisory**
   - starts at `NORMAL`;
   - escalates to `CAUTION` for baseline shifts or PM2.5 above 50;
   - escalates to `WARNING` for PM2.5 above 150 or trusted unsafe inference;
   - escalates to `MAINTENANCE` for stale/degraded hardware conditions;
   - considers high model uncertainty before treating unsafe inference as a full warning.

This result is represented by `PipelineResults` with health, lightweight anomaly, persistence forecast, and advisory fields.

### 3.5 Main record creation and persistence

The service builds a complete record containing:

```text
reading_id
node_id
timestamp
environment
particulate_matter
gas_sensors
inference
pipeline
```

`JsonlStorageService.append_reading()` writes it asynchronously through a thread-pool executor. The main store is:

```text
data/readings/{node_id}/{YYYY-MM-DD}.jsonl
```

Each line is one JSON object. Writes use a per-node thread lock. When a file exceeds the configured size, it is renamed with a timestamp suffix, and old files are deleted after the per-node file limit is exceeded.

The main JSONL record remains an internal durable record. It is not exposed as the user-facing intelligence response; the API aggregation layer strips raw sensor fields and model diagnostics before returning data.

### 3.6 Rich anomaly engine

After the base record is written, the service runs `AnomalyEngine.analyse()` in an executor so CPU-bound work does not block the async event loop.

On the first reading for a node during this process lifetime:

1. The service loads up to 24 hours of recent main-store records.
2. The records are converted to observations and loaded into a bounded rolling window.
3. Baselines and residual history are initialized.

For each current observation the engine:

1. extracts 11 canonical features: PM1.0/2.5/10, temperature, humidity, raw ADC and voltage values for MQ2/MQ9/MQ135;
2. adds the observation to a per-node rolling window, normally 24 hours and capped at 10,000 observations;
3. checks staleness and sensor health;
4. predicts expected values using the best available baseline:
   - EMA while data is scarce;
   - time-of-day regression after enough samples;
   - recent trend correction when enough recent points exist;
5. calculates robust residual scores using median absolute deviation;
6. fuses particulate, gas, and environmental category scores;
7. adds a corroboration bonus when PM and gas anomalies agree;
8. produces severity, confidence, system state, evidence, explanations, and possible anomaly source.

The state progresses through `BOOTSTRAPPING`, `CALIBRATING`, `LEARNING`, and `MONITORING`, or enters `DEGRADED` for stale data. Baselines are periodically refit according to configuration, normally every 15 minutes.

The report is attached to the in-memory `pipeline_results` object. The current implementation does not append this enriched object back to the already-written main JSONL line.

### 3.7 Source classification

When source-classifier artifacts are loaded, the service runs `SourceClassifier.classify()` in an executor.

The classifier extracts eight raw features and six derived features:

```text
Raw:     MQ2, MQ9, MQ135 voltages, temperature, humidity, PM1.0, PM2.5, PM10
Derived: PM coarse ratio, PM fine ratio, MQ mean, MQ maximum,
         MQ2/MQ9 ratio, MQ135/MQ2 ratio
```

The classifier then:

1. assesses missing values, railed sensors, and staleness;
2. obtains Decision Tree probabilities when the model and scaler are present;
3. computes similarity against per-category reference statistics;
4. combines Decision Tree probability and similarity when both are present;
5. detects possible mixed pollution when several categories score highly;
6. limits and sorts the returned hypotheses;
7. marks results uncertain when the top score is low, candidates overlap, data quality is degraded, or multiple sources are plausible.

The broad categories include traffic, heavy dust, construction, biomass or waste burning, industrial/generator emissions, cooking/fuel combustion, indoor activity, clean/background, mixed pollution, and unknown.

These are source hypotheses, not laboratory-identifiable gas measurements. The training script uses synthetic scenario data and the classifier is explicitly unvalidated against real-world ground truth.

If the classifier is not loaded, the service skips this stage because the processing code checks `is_loaded`. The standalone classifier itself is designed to return `UNKNOWN` when no artifacts exist.

### 3.8 Forecast ingestion

When the forecast plugin is initialized, the service forwards only:

```text
node_id, timestamp, PM1_0, PM2_5, PM10
```

to `ForecastPlugin.async_ingest()`.

The forecast store is intentionally separate from the main store:

```text
data/forecast/{node_id}/{YYYY-MM-DD}.jsonl
```

It stores PM-only records, uses per-node locks, reads line-by-line, and keeps a configurable rolling retention window, normally 48 hours. Forecast ingest failure is logged but does not fail the sensor request.

### 3.9 SSE publication and HTTP response

The service publishes a compact `new_reading` event to subscribers for the same node. The summary includes:

- reading ID and timestamp;
- gas class and safety status;
- advisory level;
- health status;
- lightweight anomaly flag;
- rich anomaly summary when available;
- top source, classifier status, and uncertainty when available.

The route then returns HTTP `201` with `IntelligenceResult`, containing only AQI, PM values, temperature, humidity, and source/forecast `{value, confidence}` predictions. AQI is `null` until an approved project formula is configured; no AQI value is fabricated.

## 4. Data Stores and State

### 4.1 Main reading store

The main store is append-only JSONL and contains the complete sensor payload plus inference and the initial modular pipeline result. It is optimized for edge storage rather than relational querying:

- one directory per node;
- one current calendar-day file per node;
- rotation by file size;
- retention by maximum file count;
- streaming reads for latest and recent-history operations;
- per-node locks and executor-backed file operations.

It is used by `latest`, anomaly history priming, and main reading retention.

### 4.2 Forecast store

The forecast store is independent and contains only PM series. It supports:

- forecast history retrieval;
- AR model input;
- record counts and time ranges;
- explicit expired-data cleanup;
- boundary-file rewriting and old-file deletion.

Main readings automatically enter this store through `ProcessingService`. Forecast-only API clients can also submit PM readings directly.

### 4.3 In-memory state

The following state is lost on process restart unless rebuilt from files:

- node registry and active-node list;
- SSE subscribers and queues;
- modular EMA state;
- anomaly engine windows, residuals, and fitted baselines;
- the set of nodes already history-primed in `ProcessingService`.

The anomaly engine rebuilds its recent history on a node's first reading after startup. The modular pipeline's smaller EMA state does not perform the same disk reload.

## 5. API Surface

### Health and readiness

| Method | Endpoint | Behavior |
|---|---|---|
| `GET` | `/health` | Returns service status, version, and timestamp. |
| `GET` | `/ready` | Checks main storage writability and reports whether the gas model loaded. |

Readiness is based on storage health. A missing model is reported in `model_loaded` but does not make `ready` false.

### Node and telemetry API

| Method | Endpoint | Behavior |
|---|---|---|
| `POST` | `/api/v1/nodes/{node_id}/readings` | Validates and processes a complete sensor reading. |
| `GET` | `/api/v1/nodes` | Lists nodes known to the current process. |
| `GET` | `/api/v1/nodes/{node_id}/status` | Returns active state, latest timestamp, count, and artifact availability. |
| `GET` | `/api/v1/nodes/{node_id}/latest` | Returns the latest persisted main-store record. |
| `GET` | `/api/v1/nodes/{node_id}/events` | Streams node-specific SSE events and heartbeats. |

The SSE connection immediately receives a `connected` event and then receives `new_reading` events. A heartbeat comment is emitted at the configured interval, normally 15 seconds. Subscribers are removed when disconnected.

### Forecast API

| Method | Endpoint | Behavior |
|---|---|---|
| `POST` | `/api/v1/forecast/nodes/{node_id}/readings` | Adds a PM-only record to the forecast store. |
| `GET` | `/api/v1/forecast/nodes/{node_id}/predict` | Generates a PM forecast. |
| `GET` | `/api/v1/forecast/nodes/{node_id}/history` | Reports retained forecast history. |
| `POST` | `/api/v1/forecast/cleanup` | Deletes records outside the retention window. |
| `POST` | `/api/v1/forecast/synthetic/generate` | Generates and ingests synthetic PM data. |

Forecast routes return HTTP `503` when the plugin is disabled or not initialized.

## 6. Forecast Processing in Detail

The forecast plugin is enabled by default and normally retains 48 hours of PM history. A forecast request:

1. reads retained records for the node;
2. extracts each configured PM channel independently;
3. requires at least 12 valid points per channel by default;
4. selects an AR order up to 6 based on available history;
5. fits coefficients with least-squares and Gauss-Jordan elimination;
6. generates multi-step predictions by feeding each prediction into the next step;
7. clamps predictions to non-negative values;
8. compares predictions with a persistence baseline that repeats the last value;
9. reports rising, falling, stable, or unknown trend;
10. reports reliability as unavailable, low, medium, or high.

If AR fitting fails, persistence values are returned with low reliability. If there is insufficient history, the response is `insufficient_data`. The response explicitly labels forecasts as experimental and informational.

The synthetic generator creates PM data with optional diurnal variation, trend, spikes, Gaussian noise, and enforced PM ordering. Synthetic records are marked `is_synthetic=true` and are useful for testing the forecast subsystem, not for validating real sensor accuracy.

## 7. Module-by-Module Capability Map

### `app/main.py`

Creates the FastAPI application, configures lifespan startup/shutdown, instantiates every service, installs middleware and exception handlers, and mounts health, node, and forecast routers.

### `app/api/routes/`

- `health.py`: liveness and readiness endpoints.
- `nodes.py`: complete reading ingestion, node listing/status, latest reading, and SSE subscription.
- `forecast.py`: direct forecast ingestion, prediction, history, cleanup, and synthetic-data endpoints.

Routes should remain transport-focused. Processing decisions are delegated to services and domain modules.

### `app/schemas/`

Pydantic models define the contracts between hardware, API routes, services, and clients:

- `sensor.py`: input payload and physical/value validation;
- `inference.py`: gas model status and prediction fields;
- `pipeline.py`: health, lightweight anomaly, persistence, advisory, and optional enrichment results;
- `anomaly.py`: rich anomaly report and evidence;
- `source_classification.py`: source hypotheses and uncertainty;
- `forecast.py`: forecast input, output, history, cleanup, and generator contracts;
- `responses.py`: HTTP response and error envelopes.

### `app/services/processing.py`

The orchestration layer. It owns the sequence of registration, inference, modular processing, base persistence, rich anomaly analysis, source classification, forecast ingestion, SSE publication, and response creation. Optional stages fail independently and allow the reading workflow to continue.

### `app/services/inference.py`

Defines the abstract inference contract and implements the TinyGasNet adapter. It mirrors the model architecture used by `Training/mq_train.py`, validates artifact compatibility at startup, executes prediction off the event loop, and provides explicit not-configured/error results instead of fabricated predictions.

### `app/services/pipeline.py`

Implements the low-latency deterministic pipeline. It is independent of the rich `AnomalyEngine` and maintains its own bounded per-node EMA/PM state. It is suitable for immediate qualitative health/advisory output.

### `app/services/node_registry.py`

Maintains the process-local node inventory and reading counters. It does not discover hardware or persist node metadata.

### `app/services/events.py`

Implements in-process per-node pub/sub using asyncio queues. It formats SSE frames, sends connection/heartbeat frames, publishes summaries, and cleans up disconnected clients.

### `app/storage/jsonl_store.py`

Provides asynchronous wrappers around thread-safe append and read operations for complete reading records. It handles rotation, maximum file count, latest-record lookup, recent-history lookup, count, and storage health.

### `app/anomaly/`

The richer anomaly subsystem:

- `engine.py`: per-node lifecycle, history loading, refit scheduling, and top-level analysis API;
- `window.py`: bounded time-based observation window;
- `baseline.py`: EMA, diurnal regression, and recent trend prediction;
- `residuals.py`: robust MAD-based residual scoring;
- `detector.py`: sensor-health checks, feature scoring, category fusion, severity, confidence, and state machine;
- `sensor_health.py`: feature-level sensor status and anomaly-source clues;
- `temporal.py`: time-derived features used by baselines.

### `app/source_classifier/`

The Phase 3 source-hypothesis system:

- `categories.py`: source categories, feature names, and thresholds;
- `features.py`: raw and derived feature extraction;
- `scoring.py`: similarity, Decision Tree probability combination, mixed-source detection, and uncertainty;
- `classifier.py`: artifact loading and complete classification workflow;
- `train.py`: synthetic scenario data generation, training, evaluation, and artifact creation.

### `app/forecast/`

The Phase 4 experimental PM forecast system:

- `config.py`: forecast settings and environment overrides;
- `store.py`: independent rolling PM JSONL store;
- `model.py`: AR(p), persistence baseline, trend, and reliability logic;
- `plugin.py`: lifecycle and unified sync/async interface;
- `generator.py`: deterministic synthetic PM series and replay helpers.

### `app/core/`

- `config.py`: core settings, paths, ports, limits, model/anomaly/forecast defaults, and `NAVOS_` environment configuration;
- `logging.py`: JSON-formatted application logging.

### `app/models/`

Currently only a package marker exists. Persistent domain models are not used; the system uses Pydantic schemas and JSONL dictionaries instead.

## 8. How Components Work Independently

Each major subsystem can operate separately:

- **Input validation** can reject malformed data before any ML or storage operation.
- **TinyGasNet** can be unavailable while telemetry is still accepted, stored, and processed by deterministic modules.
- **ModularPipeline** needs only a validated `SensorPayload` and an `InferenceResult`; it does not need model artifacts or disk history.
- **AnomalyEngine** can analyse stored-record-shaped dictionaries and can reload its history from the main JSONL store.
- **SourceClassifier** can classify a validated payload using a model, reference statistics, or its explicit unknown fallback.
- **ForecastPlugin** can ingest PM-only records and generate forecasts without gas sensors or the main reading-processing route.
- **JsonlStorageService** can store and retrieve readings without a database or forecast model.
- **EventService** can stream events without persisting them; events are ephemeral and only delivered to connected subscribers.
- **NodeRegistry** provides current-process status without being required for file storage or forecast calculations.

## 9. How Components Work Together

The normal composition is deliberately tolerant of partial capability:

1. Schema validation guarantees a common sensor contract.
2. `ProcessingService` supplies that contract to inference and the modular pipeline.
3. The base result is written so the system retains telemetry even if later analysis fails.
4. Rich anomaly analysis uses the persisted history to improve over time.
5. Source classification uses the same current payload but contributes a separate interpretation of possible sources.
6. Forecast ingestion extracts PM values into a purpose-built time-series store, avoiding coupling the AR model to gas or environment data.
7. SSE exposes a low-payload live summary while the HTTP response exposes the complete processing result.
8. Later API calls read either the main store, forecast store, or current in-memory state depending on the endpoint.

This arrangement means one sensor reading feeds four downstream products:

```text
                    +--> Immediate inference result
Validated payload --+--> Immediate health/advisory result
                    +--> Persisted full telemetry record
                    +--> Rich anomaly/source analysis and SSE summary
                    +--> PM-only forecast history
```

## 10. Startup, Steady State, and Shutdown

### Startup

1. Load environment settings.
2. Configure JSON logging.
3. Create data and artifact directories.
4. Construct main JSONL storage.
5. Load TinyGasNet artifacts if available.
6. Construct the anomaly engine.
7. Load source-classifier artifacts if available.
8. Construct node registry and SSE service.
9. Initialize the forecast plugin when enabled.
10. Construct `ProcessingService` and attach services to `app.state`.

### Steady state

The server handles requests asynchronously. File operations, model inference, source classification, rich anomaly detection, and forecast operations are sent to executors where needed. Each node has independent registry, storage lock, event subscribers, pipeline state, forecast history, and anomaly state.

### Shutdown

The forecast plugin is marked uninitialized and releases its store reference. The process-local registry, event subscribers, EMA state, and anomaly state disappear with the process; durable JSONL files remain.

## 11. Configuration and Artifacts

Core settings use the `NAVOS_` prefix and are read from `.env` when present. Forecast settings use the `NAVOS_FORECAST_` prefix.

Important defaults include:

| Setting | Default | Controls |
|---|---:|---|
| `NAVOS_PORT` | `8420` | HTTP port |
| `NAVOS_DATA_DIR` | `./data` | Main reading storage |
| `NAVOS_ARTIFACTS_DIR` | `./artifacts` | ML artifacts |
| `NAVOS_MAX_PAYLOAD_BYTES` | `65536` | Request-size limit |
| `NAVOS_ANOMALY_HISTORY_WINDOW_HOURS` | `24` | Rich anomaly history |
| `NAVOS_FORECAST_ENABLED` | `true` | Forecast plugin lifecycle |
| `NAVOS_FORECAST_RETENTION_HOURS` | `48` | Forecast data retention |
| `NAVOS_FORECAST_DEFAULT_HORIZON_MINUTES` | `60` | Forecast horizon |
| `NAVOS_FORECAST_DEFAULT_SAMPLING_INTERVAL_MINUTES` | `5` | Forecast step |

Expected artifacts include:

```text
artifacts/gasnet.pt
artifacts/preprocess.pkl
artifacts/source_classifier_model.pkl
artifacts/source_classifier_stats.json
artifacts/source_classifier_metadata.json
```

The gas model requires both its weights and preprocessing bundle. The source classifier can operate from reference statistics without a Decision Tree, but full classification uses both model and statistics.

## 12. Operational Caveats and Design Limits

1. **Base-record ordering**: the main record is written before rich anomaly and source-classification fields are attached to the response object. A later persistence update is not currently performed.
2. **Process-local status**: node counts/status and SSE subscribers are not shared between workers and are lost on restart.
3. **No authentication**: the service is intended for trusted local/VLAN use.
4. **No global SSE stream**: consumers subscribe one node at a time.
5. **Two anomaly paths**: the modular EMA anomaly result and the richer `AnomalyEngine` report are separate implementations with different state, thresholds, and output contracts.
6. **Forecast limitations**: channels are forecast independently, external features are not used, irregular sampling is not modeled optimally, and the model is refit from scratch for each forecast request.
7. **Classifier interpretation**: source categories are broad hypotheses from synthetic training data, not confirmed chemical identities.
8. **Forecast interpretation**: forecasts are experimental and should not be treated as validated air-quality predictions.
9. **Readiness semantics**: `/ready` requires writable storage but reports a missing gas model separately instead of failing readiness.
10. **Hardware boundary**: the hardware client is expected to sample without blocking on network requests, periodically submit the documented payload, check health/readiness, reconnect after failures, and optionally consume the node SSE stream.

## 13. Suggested Mental Model

When tracing a reading, follow this order:

```text
Payload
  -> Pydantic validation
  -> URL/node consistency check
  -> NodeRegistry registration
  -> TinyGasNet inference
  -> ModularPipeline health/features/EMA/persistence/advisory
  -> Main JSONL append
  -> Rich AnomalyEngine analysis
  -> SourceClassifier analysis
  -> ForecastPlugin PM append
  -> SSE summary
  -> HTTP ReadingAccepted response
```

When tracing a later read operation, identify the source first:

```text
Node list/status/latest -> NodeRegistry or main JSONL store
Forecast history/predict -> ForecastStore
Live updates -> EventService queues
Rich anomaly state -> AnomalyEngine memory, primed from main JSONL
Model availability -> loaded artifact flags in app.state services
```

That separation explains the complete architecture: the request path is the integration spine, while inference, anomaly detection, source classification, forecasting, storage, and events remain replaceable subsystems connected by validated schemas and service interfaces.
