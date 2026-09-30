# NavosEdge Intelligence Server

The core processing layer for the NavosEdge environmental monitoring system. This backend service sits between the physical hardware nodes and any future dashboard or UI. It handles receiving, validating, storing, and analyzing incoming sensor data.

## Features

- **Data Ingestion**: Receives sensor data (Environment, PM, MQ gas sensors) from hardware nodes.
- **Inference Pipeline**: Pluggable interface for the `TinyGasNet` model (MC-Dropout classification & safety flags) using MQ sensor signals, temperature, and humidity.
- **Local Storage**: Lightweight append-only JSONL storage. Includes file rotation to prevent eMMC wear and tear, avoiding heavy databases like PostgreSQL on edge hardware.
- **Real-time Events**: Server-Sent Events (SSE) endpoint to push real-time status and telemetry downstream.
- **Modular Pipeline**: An extensible sequence evaluating sensor health, online anomalies (EMA-based baseline shifts), PM persistence forecasts, and deterministic qualitative advisories.
- **Health & Readiness Checks**: Endpoints for nodes to verify connectivity and system readiness before transmission.

## Setup

1. **Prerequisites**: Python 3.12+ (tested on 3.14). 
2. **Virtual Environment**:
   ```bash
   cd Intelligence/Server
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
3. **Environment Variables**:
   Copy `.env.example` to `.env` and adjust the variables.
   ```bash
   cp .env.example .env
   ```
4. **Model Artifacts (Optional but Recommended)**:
   Place the trained model files (`gasnet.pt` and `preprocess.pkl`) into the `artifacts/` directory. Without these, the server will still accept and store valid readings, but the inference status will be reported as `not_configured`.

## Running the Server

Start the FastAPI application using uvicorn:
```bash
python3 app/main.py
```
By default, the server runs on `0.0.0.0:8420`.

## API Examples

**Health Check**
```bash
curl http://localhost:8420/health
```

**Submit a Sensor Reading**
```bash
curl -X POST http://localhost:8420/api/v1/nodes/navos-node-01/readings \
     -H "Content-Type: application/json" \
     -d '{
         "node_id": "navos-node-01",
         "timestamp": "2026-09-19T10:30:00Z",
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
     }'
```

The ingestion response is intentionally compact:

```json
{
    "aqi": null,
    "pm": {"PM1_0": 18.4, "PM2_5": 42.7, "PM10": 76.3},
    "temperature_C": 31.2,
    "humidity_pct": 68.5,
    "predictions": {
        "source": {"value": "TRAFFIC", "confidence": 0.78},
        "forecast": {
            "value": {"status": "insufficient_history", "PM1_0": [], "PM2_5": [], "PM10": []},
            "confidence": 0.0
        }
    }
}
```

`aqi` is `null` because the repository does not currently contain an
approved AQI formula or breakpoint table. The server does not fabricate AQI.
Raw ADC values, voltages, model probability arrays, anomaly evidence, and
model metadata remain internal.

**Get Node Status**
```bash
curl http://localhost:8420/api/v1/nodes/navos-node-01/status
```

**Get Latest Reading**
```bash
curl http://localhost:8420/api/v1/nodes/navos-node-01/latest
```

## Storage Behavior

We use file-based storage on the edge device to prevent excessive disk writes and DB overhead on the Arduino UNO Q.
- Readings are written to append-only JSONL files in `data/readings/{node_id}/`.
- Files are rotated when they exceed `NAVOS_STORAGE_MAX_FILE_SIZE_MB` (default 50MB).
- Only the most recent `NAVOS_STORAGE_MAX_FILES_PER_NODE` files are kept.
- Writing is non-blocking (asyncio executor) and thread-safe per node.

## Inference & Artifacts

The inference adapter strongly validates model artifacts (`gasnet.pt` and `preprocess.pkl`) on startup without retraining or modifying the architecture. 

**Genuine Model Outputs:**
When artifacts are loaded successfully, the backend populates the following fields using MC-Dropout over 20 forward passes:
- `gas_class`: The actual string label from the `LabelEncoder`.
- `class_confidence`: The temperature-scaled, averaged probability of the predicted class.
- `class_probabilities`: The full dictionary of probabilities for all mapped classes.
- `safety_status` / `safety_confidence`: Derived from the dedicated safety prediction head.
- `uncertainty`: The normalized entropy representing the model's confidence distribution.

**Placeholder/Fallback Outputs:**
If artifacts are missing, incompatible, or load fails, the server gracefully falls back. It continues accepting and storing readings, but the inference block is a placeholder:
- `status`: `"not_configured"`
- All prediction fields (`gas_class`, `class_confidence`, `safety_status`, etc.) will be `null`. No fake or hardcoded guesses are ever returned.

## Modular Processing Pipeline

Beyond simple ML inference, the server processes every reading through a sequence of checks designed to synthesize qualitative advice without fabricating precise AQI measurements:

1. **Sensor Health Checks:** Verifies readings against physical hardware bounds (e.g., verifying MQ sensors aren't railed to GND or VCC, catching stale timestamps).
2. **Feature Extraction:** Cleans and formats raw values (e.g. voltage ranges and particulate distributions).
3. **Online Anomaly Detection:** Utilizes an Exponential Moving Average (EMA) to maintain an online baseline of individual sensor behavior with bounded memory. Identifies unexpected standard-deviation shifts.
4. **PM Forecasting:** Evaluates sufficient valid history to provide a persistence-based baseline forecast for future particulate matter observations.
5. **Deterministic Advisory Engine:** Combines hardware health, baseline anomalies, PM metrics, and ML safety predictions (factoring in normalized predictive uncertainty) to emit an actionable `advisory_level` (`NORMAL`, `CAUTION`, `WARNING`, `MAINTENANCE`) and plain-text context messages. These results append directly into the storage record and the SSE telemetry stream.

## Known Limitations

- **Inference Fallback**: If the model artifacts are absent or load fails, the server still processes telemetry but returns a `not_configured` inference state.
- **Single-Node SSE**: Server-Sent Events are partitioned per node ID. There's currently no global event stream for a dashboard encompassing all nodes at once (this will be addressed in future UI integrations).
- **Authentication**: No API authentication is currently implemented. This is a lightweight internal service intended for local/VLAN usage.
