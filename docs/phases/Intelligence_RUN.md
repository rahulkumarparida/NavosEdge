# NavosEdge Intelligence: Quick Start Guide

This guide explains how to run the Intelligence Server backend and details the available API endpoints and their payloads.

## 1. How to Run the Server

The Intelligence backend is a FastAPI application located in the `Server/` directory.

### Prerequisites
Make sure you have Python 3.12+ installed. 

### Setup & Run
```bash
# 1. Navigate to the Server directory
cd Server/

# 2. Set up a virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start the server (runs on port 8420 by default)
python3 app/main.py
```
*Note: The server will automatically create `data/` and `artifacts/` directories on startup.*

---

## 2. API Endpoints Overview

The server exposes the following endpoints:

### System Endpoints
- **`GET /health`**
  Returns the basic health status and version of the server.
- **`GET /ready`**
  Returns the readiness status, verifying if storage is writable and if ML model artifacts are loaded.

### Node Management & Telemetry
- **`GET /api/v1/nodes`**
  Lists all active hardware nodes that have submitted data to the server.
- **`GET /api/v1/nodes/{node_id}/status`**
  Retrieves the status (active/inactive) and total reading count for a specific node.
- **`GET /api/v1/nodes/{node_id}/latest`**
  Retrieves the most recent sensor reading, inference result, and pipeline advisories for a specific node.
- **`GET /api/v1/nodes/{node_id}/events`**
  A Server-Sent Events (SSE) stream endpoint. Connect to this to receive realtime pushes whenever the node submits new data.

### Data Ingestion
- **`POST /api/v1/nodes/{node_id}/readings`**
  Submit a new batch of sensor telemetry for processing, ML inference, anomaly detection, and storage.

---

## 3. Payloads

### Request Payload: `POST /api/v1/nodes/{node_id}/readings`
The physical node (Arduino) must send a JSON payload structured exactly like this:

```json
{
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
        "MQ2": {
            "raw_adc": 420,
            "voltage_V": 1.35
        },
        "MQ9": {
            "raw_adc": 510,
            "voltage_V": 1.64
        },
        "MQ135": {
            "raw_adc": 610,
            "voltage_V": 1.96
        }
    }
}
```
*Constraints: `PM1.0 <= PM2.5 <= PM10`. Timestamps cannot be more than 24 hours in the future.*

### Response Payload
When a reading is successfully processed, the server replies with `201 Created` and returns the inference and pipeline evaluations:

```json
{
    "node_id": "navos-node-01",
    "reading_id": "a1b2c3d4e5f6",
    "timestamp": "2026-09-19T10:30:00Z",
    "inference": {
        "status": "success",
        "gas_class": "CleanAir",
        "class_confidence": 0.9432,
        "class_probabilities": {
            "CleanAir": 0.9432,
            "Smoke": 0.0211,
            "Methane": 0.0101
        },
        "safety_status": "safe",
        "safety_confidence": 0.9912,
        "uncertainty": 0.1243,
        "inference_time_ms": 14.5
    },
    "pipeline": {
        "health": {
            "status": "ok",
            "issues": []
        },
        "anomaly": {
            "is_anomalous": false,
            "deviations": []
        },
        "forecast": {
            "pm2_5_persistence": 42.7,
            "pm10_persistence": 76.3
        },
        "advisory": {
            "level": "NORMAL",
            "messages": [
                "Environmental conditions appear normal and stable."
            ]
        }
    }
}
```
