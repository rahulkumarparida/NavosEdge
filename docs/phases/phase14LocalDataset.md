# Phase 14 — Persistent Local Sensor Dataset Logging

## Overview

NavosEdge implements an automatic, persistent local dataset logger that captures all valid sensor measurements (from physical sensors or the simulation engine) as daily CSV files stored at the root of the repository:

```
local_dataset/
├── 2026-10-03.csv
├── 2026-10-04.csv
└── 2026-10-05.csv
```

The dataset logger acts as a non-blocking side-path along the Intelligence pipeline. It maintains a clean, portable sensor history that can be copied, inspected, validated, or fed directly into model retraining workflows.

---

## 1. Dataset Location

- **Directory**: `local_dataset/` (located at the repository root)
- **Path Resolution**: Automatically resolved relative to repo root (`/home/.../NavosEdge/local_dataset/`).
- **Storage Type**: Portable plain-text CSV files (no heavy database required).

---

## 2. File Naming Convention

Daily CSV files follow the calendar date format of the sensor reading timestamp:

```
local_dataset/YYYY-MM-DD.csv
```

Example:
- Readings on October 3, 2026 $\rightarrow$ `local_dataset/2026-10-03.csv`
- Readings on October 4, 2026 $\rightarrow$ `local_dataset/2026-10-04.csv`

---

## 3. CSV Schema

Each daily CSV file contains the following 13 columns:

| Column | Data Type | Description |
|--------|-----------|-------------|
| `timestamp` | ISO 8601 String | Reading timestamp produced by hardware/simulator |
| `node_id` | String | Sensor node identifier (e.g. `uno-q-001`) |
| `temperature_C` | Float | Ambient temperature in $^{\circ}\text{C}$ from DHT22 |
| `humidity_pct` | Float | Relative humidity percentage ($\%$) from DHT22 |
| `PM1_0` | Float | Particulate matter PM1.0 ($\mu\text{g/m}^3$) |
| `PM2_5` | Float | Particulate matter PM2.5 ($\mu\text{g/m}^3$) |
| `PM10` | Float | Particulate matter PM10 ($\mu\text{g/m}^3$) |
| `MQ2_raw_adc` | Integer | MQ2 raw 10-bit ADC count ($0-1023$) |
| `MQ2_voltage_V` | Float | MQ2 analog output voltage ($0.0 - 5.0\text{V}$) |
| `MQ9_raw_adc` | Integer | MQ9 raw 10-bit ADC count ($0-1023$) |
| `MQ9_voltage_V` | Float | MQ9 analog output voltage ($0.0 - 5.0\text{V}$) |
| `MQ135_raw_adc` | Integer | MQ135 raw 10-bit ADC count ($0-1023$) |
| `MQ135_voltage_V` | Float | MQ135 analog output voltage ($0.0 - 5.0\text{V}$) |

### Sample CSV Row:

```csv
timestamp,node_id,temperature_C,humidity_pct,PM1_0,PM2_5,PM10,MQ2_raw_adc,MQ2_voltage_V,MQ9_raw_adc,MQ9_voltage_V,MQ135_raw_adc,MQ135_voltage_V
2026-10-03T18:35:10.123456Z,uno-q-001,28.5,65.0,12.0,18.0,25.0,350,1.71,280,1.37,420,2.05
```

---

## 4. When a Row is Written

A row is appended to the current day's CSV **every time a valid sensor payload is received** at the Intelligence Server (`POST /hardware/data`).

Pipeline flow:
```text
Sensor (Physical / Simulator)
       ↓
  POST /hardware/data
       ↓
  Local Dataset Logger (Appends to local_dataset/YYYY-MM-DD.csv)
       ↓
  Intelligence Processing (AQI, Anomaly, Source Classifier, Forecast)
       ↓
  Advisory Engine
       ↓
  Display (MPI3501 GUI)
```

---

## 5. How Daily Files are Created

1. When a reading arrives, the logger parses the timestamp date (`YYYY-MM-DD`).
2. Checks if `local_dataset/` exists (creates it if missing).
3. Checks if `local_dataset/YYYY-MM-DD.csv` exists:
   - **If new file**: Writes the header row first, followed by the reading row.
   - **If existing file**: Opens in append mode (`a`), appends the reading row, and flushes to disk.
4. On midnight date rollover, the next reading automatically initializes a new daily CSV file.

---

## 6. Error Handling & Reliability

- **File / Directory Permissions**: Errors are caught and logged as warnings; file write failures **never** crash or interrupt the main Intelligence pipeline.
- **Application Restart**: Logger checks existing file size before writing; headers are **never** duplicated upon server restart.
- **Thread Safety**: Uses a `threading.Lock` to guarantee safe concurrent file appends.
- **Graceful Shutdown**: Each append calls `f.flush()`, ensuring zero data loss if the server process is stopped unexpectedly.

---

## 7. How to Inspect Files

Inspect logged data using standard Linux command-line tools or Python:

```bash
# View list of recorded daily datasets
ls -lh local_dataset/

# View headers and latest 10 readings
head -n 1 local_dataset/2026-10-03.csv
tail -n 10 local_dataset/2026-10-03.csv

# Count total logged samples today (minus header)
wc -l local_dataset/2026-10-03.csv
```

Quick Python summary:
```python
import pandas as pd
df = pd.read_csv("local_dataset/2026-10-03.csv")
print(df.describe())
```

---

## 8. Integration with Retraining Workflow (Phase 12)

The `local_dataset/` CSV structure is designed to be directly compatible with the Phase 12 retraining pipeline (`Training/retrain.py` and `Training/mq_train.py`).

### Workflow:

```text
Physical Sensors / Simulator
      ↓
local_dataset/YYYY-MM-DD.csv
      ↓
Dataset accumulation & inspection
      ↓
Data validation & preprocessing (Training/retrain.py)
      ↓
Model retraining & evaluation
      ↓
Exported artifacts (gasnet_weights.npz, model_metadata.json)
      ↓
UNO Q On-Device Inference
```

---

## 9. How to Copy/Add New Datasets for Retraining

To incorporate accumulated `local_dataset/*.csv` files into model retraining:

1. **Copy recorded daily CSVs into the training dataset folder**:
   ```bash
   cp local_dataset/*.csv dataset/MQ_Dataset/
   ```

2. **Execute retraining**:
   ```bash
   cd Intelligence/Server
   source venv/bin/activate
   cd ../..
   python3 Training/retrain.py --dataset-dir dataset/ --epochs 50
   ```

3. **Export updated weights to server artifacts**:
   ```bash
   python3 Training/export_gasnet.py --output Intelligence/Server/artifacts/
   ```

> **Note**: Retraining remains an explicit, user-triggered operation. The logger only records readings to disk and does not trigger automated model retraining.
