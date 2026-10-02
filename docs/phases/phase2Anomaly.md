# Phase 2: Anomaly Detection & Short-Term Forecasting Subsystem

## 1. Overview of Subsystem
The NavosEdge Intelligence Server includes an Anomaly Detection and Short-Term Forecasting subsystem in `app/anomaly/`:

- `temporal.py`: Extracts time-of-day features (sin/cos of hour) for modelling diurnal cycles.
- `window.py`: Manages a memory-bounded rolling window of recent sensor observations.
- `baseline.py`: Computes expected sensor values using a 3-level fallback hierarchy.
- `residuals.py`: Tracks prediction errors (residuals) and computes robust anomaly scores using Median Absolute Deviation (MAD).
- `sensor_health.py`: Validates individual sensor channels for faults (stuck/frozen, impossible ranges, railed voltages).
- `detector.py`: Multi-sensor fusion detector that combines individual scores into a unified anomaly severity.
- `engine.py`: Orchestrator managing per-node state, loading historical data from disk, and integrating with FastAPI.

### Integration Contracts
- `schemas/anomaly.py`: Structured JSON models for the anomaly report.
- `schemas/pipeline.py`: Contains `anomaly_report` in `PipelineResults`.
- `storage/jsonl_store.py`: `get_recent_readings` loads past data for baseline priming.
- `services/processing.py`: Injects `AnomalyEngine`, priming history on first sight, and emitting SSE anomaly reports.

---

## 2. Pipeline Execution Sequence
When a sensor payload arrives:

1. **Ingestion**: `ProcessingService.process_reading` receives the payload.
2. **Inference**: Standard thresholding / TinyGasNet inference runs.
3. **Storage**: Payload is persisted to JSONL storage.
4. **History Loading**: On first node encounter, `AnomalyEngine` loads the last 24h of history from disk to prime baselines.
5. **Anomaly Analysis**:
   - Timestamp and features are added to `RollingWindow`.
   - Stale data (>24h delay) skips detection and is flagged as `STALE`.
   - `AnomalyDetector.detect()` evaluates standard-deviation shifts against time-of-day baselines.
6. **Event Broadcast**: Structured anomaly report is attached to pipeline results and broadcast via SSE.

---

## 3. Anomaly Prediction Mechanics

### Step A: Baseline Estimation
`BaselineEstimator` predicts normal expected values for each feature using a 3-tier hierarchy:
- **Level 1 (Bootstrapping)**: Exponentially Weighted Moving Average (EMA) for initial readings.
- **Level 2 (Learning)**: Ordinary Least Squares (OLS) regression using diurnal sin/cos terms (>30 samples).
- **Level 3 (Monitoring)**: Short-term linear trend correction over recent 10 readings.

### Step B: Residual & MAD Analysis
- Residual = `Actual Value - Expected Value`.
- `ResidualTracker` maintains historical residual distributions and calculates Median Absolute Deviation (MAD).
- Normalized Score = `|Residual| / (Spread Constant * MAD)`.

### Step C: Sensor Health & Classification
- `SensorHealthChecker` verifies hardware boundaries, rate-of-change, and freeze conditions.
- Sensor state is marked `OK`, `DEGRADED`, or `FAILED`.

### Step D: Multi-Sensor Fusion
- Scores across Particulates, Gases, and Environment are combined.
- Corroboration bonus applied when gas and PM sensors spike simultaneously (indicating real environmental events vs. single-sensor noise).
- Severity level: `LOW`, `MEDIUM`, or `HIGH`.
