# NavosEdge Runtime Flow

**Document:** Phase 2 — Complete Pipeline Trace  
**Date:** September 2026

---

## Architecture Overview

```
Sensors (MQ2, MQ9, MQ135, DHT22, MPM10-CS)
       ↓ (via C++ Hardware Bridge or Mock Driver)
SensorPayload (validated JSON)
       ↓
POST /hardware/data
       ↓
ProcessingService.process_reading()
       ├── InferenceAdapter.predict()     → gas class, safety, uncertainty
       ├── ModularPipeline.process()      → health, EMA anomaly, advisory
       ├── JSONL Storage                  → append to disk
       ├── AnomalyEngine.analyse()        → statistical anomaly report
       ├── SourceClassifier.classify()    → pollution source hypothesis
       ├── ForecastPlugin.async_ingest()  → feed PM time series
       ├── ForecastPlugin.async_forecast()→ AR(p) PM predictions
       ├── AQIService.compute()           → EPA breakpoint AQI
       ├── AdvisoryEngine.evaluate()      → severity + action messages
       └── aggregate_intelligence()       → final public response
              ↓
IntelligenceResult (JSON)
       ↓
SSE EventService → connected dashboards
```

---

## 1. Entry Point — `app/main.py`

The application is a FastAPI app started via uvicorn.

### Startup Sequence (lifespan function)

1. **Load Settings** from `app/core/config.py` (`pydantic-settings`, env prefix `NAVOS_`)
2. **Setup Logging** (configurable log level)
3. **Create Directories** — `DATA_DIR`, `ARTIFACTS_DIR`
4. **Initialize Storage** — `JsonlStorageService` (append-only JSONL per node)
5. **Initialize Inference** — `TinyGasNetAdapter(artifacts_dir)` then `.load()`
6. **Initialize Anomaly Engine** — `AnomalyEngine(window_hours, thresholds...)`
7. **Initialize Source Classifier** — `SourceClassifier(artifacts_dir)` then `.load()`
8. **Initialize Registries** — `NodeRegistry`, `EventService`
9. **Initialize Forecast** — `ForecastPlugin` + `ForecastSettings`
10. **Initialize AQI** — `AQIService(storage_path, standard)`
11. **Initialize Processing** — `ProcessingService` receives all above as dependencies
12. **Attach to app.state** — for route handler access
13. **Register Routers** — health, nodes, forecast, AQI, hardware

### Registered Routes

| Method | Path | Handler |
|:---|:---|:---|
| GET | `/health` | Health check |
| GET | `/ready` | Readiness check |
| POST | `/hardware/data` | Sensor data ingestion |
| GET | `/hardware/events` | SSE event stream |
| POST | `/hardware/config` | Dynamic config updates |
| GET | `/nodes` | Node registry |
| GET | `/forecast/{node_id}` | Forecast query |
| GET | `/aqi/latest` | Latest AQI |
| GET | `/intelligence/latest/{node_id}` | Latest intelligence result |

---

## 2. Core Pipeline — `ProcessingService.process_reading()`

When a `SensorPayload` arrives at `POST /hardware/data`:

### Step-by-step execution

1. **Generate reading_id** — UUID hex[:12]
2. **Register node** — `node_registry.register_reading(node_id, timestamp)`
3. **Extract features** — MQ2_V, MQ9_V, MQ135_V, temperature_C, humidity_pct
4. **Inference** — `inference_adapter.predict(mq2_v, mq9_v, mq135_v, temp, hum)` → `InferenceResult`
5. **Modular pipeline** — `pipeline.process(payload, inference_result)` → `PipelineResults`
   - Health check (stale, railed sensors, extreme values)
   - Feature extraction
   - EMA-based anomaly detection
   - Persistence forecast
   - Rule-based advisory
6. **Persist** — `storage.append_reading(node_id, record)` to JSONL
7. **Anomaly engine** — `anomaly_engine.analyse(node_id, record)` (statistical, with history priming)
8. **Source classifier** — `source_classifier.classify(payload)` (DecisionTree + similarity scoring)
9. **Forecast ingest** — `forecast_plugin.async_ingest(reading)` (feed PM values)
10. **Forecast generate** — `forecast_plugin.async_forecast(node_id)` (AR(p) model)
11. **AQI compute** — `aqi_service.compute(payload)` (EPA breakpoints)
12. **Advisory** — `AdvisoryEngine.evaluate(...)` (rule-based severity)
13. **Aggregate** — `aggregate_intelligence(payload, pipeline, inference, forecast)` → `IntelligenceResult`
14. **SSE publish** — `event_service.publish(node_id, result)`
15. **Store latest** — `_latest_results[node_id] = result`

---

## 3. Inference — `TinyGasNetAdapter`

### Model Architecture (verified)

```
Input: [MQ2_V, MQ9_V, MQ135_V, temperature_C, humidity_pct]  (5 features)
    ↓
fc1: Linear(5, 32) → ReLU → Dropout(p=0.1)
    ↓
fc2: Linear(32, 16) → ReLU → Dropout(p=0.1)
    ↓
┌─────────────────────┬───────────────────┐
│ class_head(16, 8)   │ safety_head(16,1) │
│ → softmax/T_cal     │ → sigmoid         │
└─────────────────────┴───────────────────┘
```

### MC-Dropout Protocol

1. Set model to `train()` mode (dropout remains active)
2. Run 20 forward passes (`n_mc = 20`)
3. Each pass produces: `class_probs` (softmax with T_cal) and `safety_prob` (sigmoid)
4. Average across all 20 runs → `mean_class`, `mean_safety`
5. Normalized entropy: `H = -Σ(p·log(p+ε)) / log(n_classes)` → uncertainty ∈ [0, 1]
6. Class = argmax(mean_class)
7. Safety = "unsafe" if mean_safety > 0.5

### Preprocessing

- `StandardScaler.transform()` from `preprocess.pkl`
- `LabelEncoder.classes_` from `preprocess.pkl`
- `calibration_temperature` from `preprocess.pkl` bundle

### Artifacts

- `gasnet.pt` — PyTorch state dict (6.6 KB, 873 parameters)
- `preprocess.pkl` — joblib bundle (scaler + label_encoder + temperature)

---

## 4. Sub-system Details

### Anomaly Engine (`app/anomaly/`)
- **Method:** Rolling window + OLS regression baseline + Welford variance
- **Dependencies:** numpy only
- **UNO Q compatible:** YES

### Source Classifier (`app/source_classifier/`)
- **Method:** DecisionTree (`sklearn`) + reference statistics similarity scoring
- **Dependencies:** scikit-learn, joblib, numpy
- **UNO Q compatible:** YES

### Forecast Plugin (`app/forecast/`)
- **Method:** AR(p) autoregressive model, pure Python least-squares
- **Dependencies:** None (pure Python math)
- **UNO Q compatible:** YES

### AQI Calculator (`app/aqi/`)
- **Method:** EPA breakpoint interpolation
- **Dependencies:** None
- **UNO Q compatible:** YES

### Advisory Engine (`app/advisory/`)
- **Method:** Rule-based decision tables
- **Dependencies:** None
- **UNO Q compatible:** YES

### Storage (`app/storage/`)
- **Method:** Append-only JSONL files, per-node, with rotation
- **Dependencies:** None
- **UNO Q compatible:** YES

### SSE Events (`app/services/events.py`)
- **Method:** asyncio.Queue per client
- **Dependencies:** sse-starlette
- **UNO Q compatible:** YES

---

## 5. Configuration

All configuration via environment variables with `NAVOS_` prefix or `.env` file:

| Variable | Default | Purpose |
|:---|:---|:---|
| `NAVOS_HOST` | `0.0.0.0` | Server bind address |
| `NAVOS_PORT` | `8420` | Server port |
| `NAVOS_LOG_LEVEL` | `INFO` | Logging level |
| `NAVOS_DATA_DIR` | `./data` | Data storage directory |
| `NAVOS_ARTIFACTS_DIR` | `./artifacts` | Model artifacts |
| `NAVOS_FORECAST_ENABLED` | `True` | Enable forecast plugin |
| `NAVOS_FORECAST_STORAGE_DIR` | `./data/forecast` | Forecast data |
| `NAVOS_AQI_STORAGE_FILE` | `./data/aqi_latest.json` | AQI state |
| `NAVOS_AQI_STANDARD` | `EPA` | AQI calculation standard |
| `NAVOS_SSE_HEARTBEAT_INTERVAL_S` | `15.0` | SSE heartbeat |

---

## 6. Network Dependencies

| Component | Network Required? | Notes |
|:---|:---|:---|
| Inference (TinyGasNet) | **NO** | Local model file |
| Anomaly detection | **NO** | Pure computation |
| Source classification | **NO** | Local model file |
| Forecast | **NO** | Pure computation |
| AQI | **NO** | Pure computation |
| Advisory | **NO** | Rule-based |
| Storage | **NO** | Local JSONL files |
| Server HTTP API | Local only | Hardware → localhost |
| SSE | Local only | Hardware ↔ localhost |
| Dashboard sync | **OPTIONAL** | Only when laptop connected |
| Weather data | **OPTIONAL** | Only when internet available |

**Core inference pipeline requires ZERO network connectivity.**

---

## 7. Dependency Graph

```
SensorPayload
    │
    ├──→ InferenceAdapter (numpy or torch)
    │       └── gasnet_weights.npz + model_metadata.json
    │
    ├──→ ModularPipeline
    │       ├── Health Check (pure Python)
    │       ├── EMA Anomaly (numpy)
    │       ├── Persistence Forecast (pure Python)
    │       └── Advisory (rules)
    │
    ├──→ AnomalyEngine (numpy)
    │       ├── BaselineEstimator (OLS regression)
    │       ├── ResidualTracker
    │       └── RollingWindow
    │
    ├──→ SourceClassifier (sklearn, joblib, numpy)
    │       ├── DecisionTree model
    │       └── Reference statistics
    │
    ├──→ ForecastPlugin (pure Python)
    │       └── AR(p) via Gauss-Jordan
    │
    ├──→ AQIService (pure Python)
    │       └── EPA breakpoints
    │
    └──→ AdvisoryEngine (pure Python)
            └── Rule tables
```
