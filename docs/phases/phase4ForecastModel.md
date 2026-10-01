# Phase 4: Lightweight Autoregressive Forecast Plugin

> **Status**: Experimental — forecasts have not been validated against real sensor data.

## Overview

Phase 4 adds a **lightweight autoregressive (AR) forecasting plugin** to the NavosEdge Intelligence Server. It predicts short-term PM1.0, PM2.5, and PM10 trends using the most recent 24–48 hours of sensor data, operating entirely locally with bounded memory and storage.

No model training is required. The plugin fits a simple AR(p) model via least-squares on the stored time-series and generates multi-step forecasts.

---

## Model Approach

### Autoregressive (AR) Model

The forecast engine uses a classic **AR(p)** model:

```
y(t) = c + φ₁·y(t-1) + φ₂·y(t-2) + ... + φₚ·y(t-p) + ε
```

Where:
- `y(t)` is the PM value at time `t`
- `φ₁...φₚ` are the autoregressive coefficients
- `c` is the intercept
- `p` is the AR order (max 6 by default)

**Fitting**: Coefficients are estimated via ordinary least-squares (normal equations) solved by Gauss-Jordan elimination — no external ML libraries needed.

**Multi-step prediction**: Forecasts are generated iteratively, feeding each prediction back as input for the next step.

### Persistence Baseline

Every forecast includes a **persistence baseline** (repeat the last known value). The MAE between the AR forecast and persistence baseline is reported, providing a simple accuracy benchmark.

### Trend Classification

Trend direction is computed from the difference between first and last predicted values:
- **Rising**: difference > threshold (default 0.5 µg/m³)
- **Falling**: difference < -threshold
- **Stable**: within threshold

### Reliability Assessment

| Level       | Condition                                |
|-------------|------------------------------------------|
| HIGH        | AR fitted + ≥ 3× min history points      |
| MEDIUM      | AR fitted + < 3× min history points      |
| LOW         | AR failed, using persistence fallback     |
| UNAVAILABLE | Insufficient data                         |

---

## Plugin Interface

```python
class ForecastPlugin:
    def initialize(config: ForecastSettings) -> None
    def ingest(reading: ForecastReadingInput) -> ForecastReadingAccepted
    def forecast(node_id, horizon_minutes?, sampling_interval_minutes?) -> ForecastResponse
    def get_history(node_id) -> ForecastHistoryResponse
    def delete_expired_data(node_id?) -> CleanupResponse
    def shutdown() -> None
```

Each method also has an `async_*` variant for use in the FastAPI async context.

---

## Input / Output Schema

### ForecastReadingInput (ingest)

```json
{
  "node_id": "sensor-01",
  "timestamp": "2025-01-15T10:30:00Z",
  "PM1_0": 12.5,
  "PM2_5": 28.0,
  "PM10": 55.3,
  "is_synthetic": false
}
```

### ForecastResponse (predict)

```json
{
  "node_id": "sensor-01",
  "status": "ok",
  "reliability": "high",
  "generated_at": "2025-01-15T10:31:00Z",
  "horizon_minutes": 60,
  "sampling_interval_minutes": 5,
  "history_points_used": 576,
  "channels": [
    {
      "channel": "PM2_5",
      "predicted_values": [28.1, 28.3, ...],
      "predicted_timestamps": ["2025-01-15T10:35:00Z", ...],
      "trend": "stable",
      "persistence_baseline": [28.0, 28.0, ...],
      "mae_vs_persistence": 0.42
    }
  ],
  "message": "Forecast generated for 3 channel(s).",
  "experimental_warning": "Forecasts are experimental..."
}
```

### Status Values

| Status              | Meaning                                 |
|---------------------|------------------------------------------|
| `ok`                | Forecast generated successfully          |
| `insufficient_data` | Not enough history points                |
| `no_valid_channels` | Requested channels not in data           |
| `error`             | Internal error                           |

---

## Storage & 48-Hour Cleanup

### Architecture

- **Format**: JSONL (one JSON object per line)
- **Layout**: `data/forecast/{node_id}/{YYYY-MM-DD}.jsonl`
- **Isolation**: Completely separate from the main sensor JSONL store
- **Thread safety**: Per-node threading locks

### Retention Policy

- Rolling window: **48 hours** (configurable)
- Cleanup strategy:
  1. Files whose date is entirely outside the window → deleted whole
  2. Boundary files → rewritten, keeping only valid records
- Cleanup can be triggered manually via API or called programmatically

### Memory Behavior

- Reads stream line-by-line — never loads the entire history into RAM
- Write is append-only
- Maximum file size configurable (default 10 MB)

---

## Configuration

All settings can be overridden via environment variables with `NAVOS_` prefix (core settings) or `NAVOS_FORECAST_` prefix (plugin-specific).

| Setting                                    | Default             | Description                          |
|--------------------------------------------|---------------------|--------------------------------------|
| `NAVOS_FORECAST_ENABLED`                   | `true`              | Enable/disable the forecast plugin   |
| `NAVOS_FORECAST_STORAGE_DIR`               | `./data/forecast`   | Forecast data storage directory      |
| `NAVOS_FORECAST_RETENTION_HOURS`           | `48`                | Rolling window retention             |
| `NAVOS_FORECAST_DEFAULT_HORIZON_MINUTES`   | `60`                | Default forecast horizon             |
| `NAVOS_FORECAST_DEFAULT_SAMPLING_INTERVAL_MINUTES` | `5`       | Default sampling interval            |
| `NAVOS_FORECAST_MIN_HISTORY_POINTS`        | `12`                | Minimum points for forecasting       |
| `NAVOS_FORECAST_MAX_AR_ORDER`              | `6`                 | Maximum AR lag order                 |
| `NAVOS_FORECAST_TREND_THRESHOLD`           | `0.5`               | µg/m³ threshold for trend detection  |

---

## Synthetic Data Generator

### Usage

Generate and replay a 48-hour dataset via API:

```bash
curl -X POST http://localhost:8420/api/v1/forecast/synthetic/generate \
  -H "Content-Type: application/json" \
  -d '{
    "node_id": "synth-node-01",
    "duration_hours": 48,
    "sampling_interval_minutes": 5,
    "seed": 42,
    "include_spikes": true,
    "include_trend": true,
    "noise_level": 1.0
  }'
```

Then request a forecast:

```bash
curl http://localhost:8420/api/v1/forecast/nodes/synth-node-01/predict?horizon_minutes=60
```

### Characteristics

The generator produces data with:
- **Diurnal cycle**: 24-hour sinusoidal baseline variation
- **Gradual trend**: linear ramp (configurable direction)
- **Spikes**: ~2% of readings with 2-5× amplitude
- **Noise**: Gaussian noise scaled to baseline
- **PM ordering**: PM1.0 ≤ PM2.5 ≤ PM10 always enforced

All synthetic records are clearly tagged with `is_synthetic: true`.

### Programmatic Usage

```python
from app.forecast.generator import generate_synthetic_series, replay_through_plugin
from app.schemas.forecast import SyntheticGeneratorConfig

config = SyntheticGeneratorConfig(
    node_id="test-node",
    duration_hours=48,
    seed=42,
)
readings = generate_synthetic_series(config)
replay_through_plugin(readings, forecast_plugin)
```

---

## API Endpoints

| Method | Path                                          | Description                           |
|--------|-----------------------------------------------|---------------------------------------|
| POST   | `/api/v1/forecast/nodes/{node_id}/readings`   | Submit a PM reading for forecasting   |
| GET    | `/api/v1/forecast/nodes/{node_id}/predict`    | Request a forecast                    |
| GET    | `/api/v1/forecast/nodes/{node_id}/history`    | View retained history/status          |
| POST   | `/api/v1/forecast/cleanup`                    | Trigger expired-data cleanup          |
| POST   | `/api/v1/forecast/synthetic/generate`         | Generate & ingest synthetic data      |

### Query Parameters (predict)

| Parameter                    | Type | Default | Description                 |
|------------------------------|------|---------|-----------------------------|
| `horizon_minutes`            | int  | 60      | How far to forecast (5-1440)|
| `sampling_interval_minutes`  | int  | 5       | Interval between predictions|

### Query Parameters (cleanup)

| Parameter  | Type   | Default | Description                     |
|------------|--------|---------|---------------------------------|
| `node_id`  | string | null    | Limit cleanup to specific node  |

---

## Run Commands

### Start the server

```bash
cd Intelligence/Server
source venv/bin/activate
python -m app.main
```

### Run forecast tests

```bash
cd Intelligence/Server
source venv/bin/activate
python -m pytest tests/test_forecast.py -v
```

### Generate 48-hour dataset and forecast (CLI)

```bash
# From the Server directory with venv activated
python -c "
from app.forecast.plugin import ForecastPlugin
from app.forecast.config import ForecastSettings
from app.forecast.generator import generate_synthetic_series, replay_through_plugin
from app.schemas.forecast import SyntheticGeneratorConfig
import json

plugin = ForecastPlugin()
plugin.initialize()

config = SyntheticGeneratorConfig(node_id='demo', duration_hours=48, seed=42)
readings = generate_synthetic_series(config)
print(f'Generated {len(readings)} readings')

replay_through_plugin(readings, plugin)
result = plugin.forecast('demo', horizon_minutes=60)
print(json.dumps(result.model_dump(mode='json'), indent=2, default=str))
plugin.shutdown()
"
```

---

## Tests

| Test Class / Function                          | What It Covers                                      |
|------------------------------------------------|------------------------------------------------------|
| `TestSyntheticGenerator`                       | Generation, reproducibility, PM ordering, save/replay|
| `TestForecastStore`                            | Append, read, count, time range, malformed JSON      |
| `TestRetentionCleanup`                         | Expired deletion, recent data preservation           |
| `TestForecastModel`                            | Sufficient/insufficient data, missing channels, NaN  |
| `TestIrregularTimestamps`                      | Uneven sampling intervals                            |
| `TestSpikeAndTrend`                            | Rising/falling trends, spike handling                |
| `TestForecastPlugin`                           | Lifecycle, ingest, forecast, uninitialized errors    |
| `test_forecast_api_*`                          | All API endpoints, error cases, parameter handling   |

---

## Architecture

```
Intelligence/Server/app/forecast/
├── __init__.py       # Package marker
├── config.py         # ForecastSettings (pydantic-settings)
├── store.py          # ForecastStore — rolling 48h JSONL store
├── model.py          # AR(p) forecasting engine
├── generator.py      # Synthetic PM data generator
└── plugin.py         # ForecastPlugin — unified interface

Intelligence/Server/app/api/routes/
└── forecast.py       # FastAPI routes

Intelligence/Server/app/schemas/
└── forecast.py       # Pydantic I/O schemas

Intelligence/Server/tests/
└── test_forecast.py  # Comprehensive test suite
```

### Integration Points

1. **Automatic ingestion**: `ProcessingService.process_reading()` forwards PM data to the forecast plugin after each sensor reading
2. **App state**: Plugin is attached to `app.state.forecast_plugin` during lifespan
3. **Independent API**: Forecast routes are mounted at `/api/v1/forecast/`
4. **No coupling**: The plugin can be disabled via `NAVOS_FORECAST_ENABLED=false`

---

## Limitations

1. **No cross-channel correlation**: Each PM channel is forecast independently
2. **Linear model**: AR(p) cannot capture complex nonlinear dynamics
3. **Fixed-lag assumption**: AR assumes regularly spaced observations; irregular timestamps are handled but not optimally
4. **No external features**: Temperature, humidity, and gas readings are not used as forecast inputs
5. **No online learning**: The AR model is refitted from scratch on each forecast request
6. **Experimental**: Forecasts have not been validated against real sensor data
7. **No UI**: Dashboard integration is deferred to a future phase
8. **Single-machine**: No distributed storage or multi-node aggregation
