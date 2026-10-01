# NavosEdge Phase 12 — PyTorch-Free Model Retraining, Model Mechanics & Simulation Guide

## Overview

NavosEdge Phase 12 implements a complete **100% PyTorch-Free** model retraining, range calibration, and history-priming pipeline using sensor measurements in `dataset/`. By eliminating the heavy PyTorch dependency ($\approx 500\text{ MB}+$ installation size), NavosEdge ensures ultra-lightweight Edge-AI performance tailored for Arduino UNO Q (2 GB RAM / 16 GB eMMC) using pure NumPy and Scikit-learn.

This document details:
1. **How each machine learning model works under the hood**
2. **Component architecture & retraining division**
3. **Dataset structure, ingestion & feature engineering**
4. **How to run the PyTorch-free retraining pipeline**
5. **How to check and verify if the models are working correctly**
6. **How to use and test the models within the simulation environment**

---

## Detailed Model Mechanics: How Each Model Works

NavosEdge uses a hybrid multi-model intelligence pipeline combining neural inference, decision trees, autoregressive time-series forecasting, and deterministic rule engines.

```
                  ┌─────────────────────────────────────────┐
                  │          Sensor Payload Stream          │
                  │  (MQ2, MQ9, MQ135, PM1/2.5/10, Temp, RH)│
                  └────────────────────┬────────────────────┘
                                       │
        ┌──────────────────────────────┼──────────────────────────────┐
        │                              │                              │
        ▼                              ▼                              ▼
┌──────────────┐               ┌──────────────┐               ┌──────────────┐
│  TinyGasNet  │               │    Source    │               │ Online AR(p) │
│  (Anomaly)   │               │ Classifier   │               │ (Forecast)   │
└───────┬──────┘               └───────┬──────┘               └───────┬──────┘
        │                              │                              │
        └──────────────────────────────┼──────────────────────────────┘
                                       │
                                       ▼
                       ┌──────────────────────────────┐
                       │ AQI Calculator & Advisory    │
                       │          Engine              │
                       └──────────────────────────────┘
```

### 1. Anomaly & Safety Model (`TinyGasNet`)

* **Purpose**: Detects gas concentration anomalies and determines safety risk (`safe` vs. `unsafe`) along with predictive uncertainty.
* **Architecture**: Pure NumPy Multi-Layer Perceptron (MLP) with dual output heads:
  $$\text{Input}(5: MQ_2, MQ_9, MQ_{135}, T, RH) \xrightarrow{\text{Linear}(5, 32)} \text{ReLU} \xrightarrow{\text{Dropout}(0.1)} \text{Linear}(32, 16) \xrightarrow{\text{ReLU}} \begin{cases} \text{Class Head}(16 \to N_{classes}) \\ \text{Safety Head}(16 \to 1) \end{cases}$$
* **Execution & Mechanics**:
  * **Feature Normalization**: Incoming 5-dimensional feature vectors are normalized using mean ($\mu$) and scale ($\sigma$) parameters stored in `model_metadata.json`.
  * **Temperature Scaling ($T_{cal} = 1.3500$)**: Class head logits are scaled before Softmax calculation ($z / T_{cal}$) to calibrate output confidence probabilities.
  * **Sigmoid Safety Head**: Computes binary safety probability $P_{\text{unsafe}} = \frac{1}{1 + e^{-z_{\text{safety}}}}$. If $P_{\text{unsafe}} > 0.5$, safety status is declared `unsafe`.
  * **Pure NumPy Monte-Carlo (MC) Dropout**: Executes 20 stochastic forward passes with dropout mask enabled ($p=0.1$). Calculates normalized predictive entropy across runs to estimate model uncertainty without PyTorch runtime overhead:
    $$\text{Uncertainty} = \frac{-\sum p_i \ln(p_i + \epsilon)}{\ln(N_{classes})}$$

### 2. Source Classifier (`SourceClassifier`)

* **Purpose**: Classifies environmental pollution sources into specific categories (e.g., *Traffic*, *Combustion / Smoke*, *Dust / Construction*, *Clean Indoor*, *High Humidity*).
* **Architecture**: Explainable Scikit-learn `DecisionTreeClassifier` (tree depth $\le 8$) paired with robust statistical reference profiles (Median, Median Absolute Deviation, IQR).
* **Execution & Mechanics**:
  * **Feature Extraction**: Derives 14 raw and ratio features from incoming sensor data:
    * $PM_{\text{coarse}} = PM_{10} / PM_{2.5}$
    * $PM_{\text{fine}} = PM_{2.5} / PM_{1.0}$
    * $MQ_{\text{mean}} = (MQ_2 + MQ_9 + MQ_{135}) / 3$
    * $MQ_{\text{max}} = \max(MQ_2, MQ_9, MQ_{135})$
    * Gas sensor cross-ratios: $MQ_2 / MQ_9$, $MQ_{135} / MQ_2$
  * **Dual Scoring Mechanism**:
    1. **Tree Probability**: Decision Tree outputs leaf node class probabilities.
    2. **Statistical Distance Matching**: Computes Mahalanobis-like robust distance against per-class reference medians and MAD profiles (`source_classifier_stats.json`).
  * **Combined Output**: Produces a ranked list of source hypotheses with confidence scores, match percentages, and mixed-pollution detection.

### 3. Forecast Model (Online AR(p))

* **Purpose**: Predicts future particulate matter concentrations ($PM_{1.0}, PM_{2.5}, PM_{10}$) over 1-hour, 6-hour, 12-hour, and 24-hour horizons.
* **Architecture**: Pure Python / NumPy Autoregressive model $\text{AR}(p)$ fitted online using Ordinary Least Squares (OLS) via normal equations.
* **Execution & Mechanics**:
  * **History Store**: Ingests chronological sensor readings into node storage (`readings.jsonl`), enforcing a 48-hour data retention window.
  * **Least-Squares Solver**: Fits coefficients $\beta$ by solving $(X^T X) \beta = X^T y$ via Gauss-Jordan elimination with partial pivoting:
    $$\hat{y}_{t} = c + \sum_{i=1}^{p} \phi_i y_{t-i}$$
  * **Baseline Fallback**: If historical readings count $< p+2$, the model gracefully falls back to a persistence baseline (latest value) while setting reliability flags.
  * **Trend Analysis**: Computes linear slope across predicted horizons to assign trend direction (`IMPROVING`, `STABLE`, or `DETERIORATING`).

### 4. AQI Calculator & Advisory Engine

* **AQI Calculator**: Deterministic piecewise linear algorithm mapping $PM_{2.5}$, $PM_{10}$, and $PM_{1.0}$ to US EPA / Indian CPCB Breakpoint Tables, assigning AQI numerical value and category (*Good*, *Moderate*, *Unhealthy*, *Hazardous*).
* **Advisory Engine**: Deterministic rule engine evaluating combined outputs (AQI + Anomaly + Source + Forecast Trend) to generate actionable health recommendations and automated relay control signals.

---

## Component Architecture & Retraining Division

| Component | Features Used | Architecture & Retraining Action |
|---|---|---|
| **Anomaly Model (`TinyGasNet`)** | `MQ2`, `MQ9`, `MQ135`, `temperature`, `humidity` | **Retrained Pure NumPy MLP**: Trained using pure NumPy AdamW mini-batch gradient descent with chronological 70/15/15 train/val/test splits and fast vector temperature scaling ($T_{cal} = 1.3500$). Exports pure NumPy weight matrices (`gasnet_weights.npz`) for zero-dependency edge inference. |
| **Source Classifier** | `PM1.0`, `PM2.5`, `PM10`, `MQ`, `temperature`, `humidity` | **Range Calibrated**: Computed robust per-class statistics (median, MAD, IQR) & trained a lightweight `DecisionTreeClassifier` ($depth \le 8$) on real dataset distributions. |
| **Forecast Model** | Chronological PM1.0, PM2.5, PM10 history | **History-based Online AR(p)**: Ingested 2,672 valid chronological dataset records into node storage (`data/readings/uno-q-001/readings.jsonl`), enforcing the 48-hour data retention policy. |
| **AQI Calculation** | `PM2.5`, `PM10`, `PM1.0` | **Deterministic**: Retained piecewise linear EPA/CPCB calculation math. |
| **Advisory Engine** | AQI, Anomaly, Source, Forecast | **Rule-Based**: Retained deterministic health & safety alert engine. |

---

## Dataset Structure & Ingestion

The raw sensor dataset is stored under `dataset/`:

- `dataset/DHT22_Dataset/session_01.csv` ... `session_04.csv`: Timestamped temperature (`temperature_c`) and relative humidity (`humidity_percent`).
- `dataset/MPM_10_Dataset/session_1.csv` ... `session_4.csv`: Particulate matter measurements (`pm1_0`, `pm2_5`, `pm10`).
- `dataset/MQ_Dataset/session_01.csv` ... `session_03.csv`: Gas sensor voltage outputs (`mq2_ao_voltage`, `mq9_ao_voltage`, `mq135_ao_voltage`) and raw ADC values.

### Data Validation & Cleaning Logic

1. **Outlier Filtering**:
   - Temperature constrained to physical limits `[-35.0, 80.0] °C`.
   - Humidity constrained to `[0.0, 100.0] %`.
   - MQ sensor voltages constrained to `[0.0, 5.0] V`.
   - PM values clipped/cleaned for corrupt sensor spikes (`> 1000 µg/m³`) and non-negative bounds.
2. **Physical Hierarchy Enforcement**:
   - Enforces $PM_{1.0} \le PM_{2.5} \le PM_{10}$.
3. **Chronological Alignment**:
   - Sensor streams are sorted chronologically.
   - Sessions are merged using relative timestamp offsets (`pd.merge_asof` with 5-second tolerance) to prevent row-index mismatch.

---

## Model Features

### Raw & Derived Features
- **Raw Features**: `mq2_v`, `mq9_v`, `mq135_v`, `temp_c`, `hum_pct`, `pm1_0`, `pm2_5`, `pm10`
- **Derived Features**:
  - `pm_coarse_ratio = PM10 / PM2.5`
  - `pm_fine_ratio = PM2.5 / PM1.0`
  - `mq_mean_v = (MQ2 + MQ9 + MQ135) / 3`
  - `mq_max_v = max(MQ2, MQ9, MQ135)`
  - `mq2_mq9_ratio = MQ2 / MQ9`
  - `mq135_mq2_ratio = MQ135 / MQ2`

---

## PyTorch-Free Retraining Command

Run the complete, reproducible retraining pipeline:

```bash
python3 Training/retrain.py
```

### What the Command Does:
1. Validates & cleans dataset files in `dataset/`.
2. Chronologically aligns sensor streams across sessions into 2,672 clean feature records.
3. Automatically backs up existing model artifacts into `Intelligence/Server/artifacts/backups/backup_<timestamp>`.
4. Retrains `TinyGasNet` Anomaly Detection model in pure NumPy using 70/15/15 chronological train/val/test splits and calibrates output probabilities using temperature scaling ($T_{cal}$).
5. Computes robust per-class reference statistics (median, MAD, $Q_{25}$, $Q_{75}$) and trains `DecisionTreeClassifier` for the Source Classifier.
6. Prunes data older than 48 hours and ingests valid records into `data/readings/uno-q-001/readings.jsonl` for Forecast Model history.
7. Exports and deploys updated model artifacts across expected directories (`artifacts/`, `models/`).
8. Verifies that `NumpyGasNetAdapter` and `SourceClassifier` automatically load the newly generated artifacts without PyTorch.

---

## How to Check if the Model is Working (Verification & Testing)

You can verify model integrity and execution using unit tests, precision comparison, live API endpoints, or terminal monitoring.

### 1. Run the Complete Test Suite
Run the automated test runner to test all pipeline components:
```bash
bash scripts/run_all_tests.sh
```
* **Expected Output**:
  ```text
  --- NumPy Inference Backend Load ---
    [PASS] NumPy Inference Backend Load
  --- NumPy Inference Prediction ---
    Status: success
    Class: Clean Air (0.9852)
    Safety: safe
    [PASS] NumPy Inference Prediction
  --- Source Classifier ---
    [PASS] Source Classifier
  --- Forecast Plugin ---
    [PASS] Forecast Plugin
  RESULT: ALL TESTS PASSED
  ```

### 2. PyTorch vs. NumPy Numerical Precision Validation
If you have PyTorch installed on your workstation, run the precision validation script to ensure the NumPy model matches PyTorch outputs within $10^{-5}$ tolerance:
```bash
python3 tests/test_torch_vs_numpy.py
```

### 3. Check Live Server Health & Model Endpoints
Start the server:
```bash
cd Intelligence/Server
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8420
```

1. **Server Health Endpoint**:
   ```bash
   curl http://127.0.0.1:8420/health
   ```
   * **Expected JSON Response**:
     ```json
     {
       "status": "healthy",
       "services": {
         "numpy_inference": "ready",
         "source_classifier": "ready",
         "forecast": "ready"
       }
     }
     ```

2. **Inference & Processing Verification**:
   Send a sample sensor payload to the processing endpoint:
   ```bash
   curl -X POST http://127.0.0.1:8420/hardware/data \
     -H "Content-Type: application/json" \
     -d '{
       "node_id": "UNO-Q-TEST",
       "timestamp": "2026-10-02T03:00:00Z",
       "environment": {"temperature_C": 24.5, "humidity_pct": 48.0},
       "particulate_matter": {"PM1_0": 12.0, "PM2_5": 18.0, "PM10": 25.0},
       "gas_sensors": {
         "MQ2": {"raw_adc": 210, "voltage_V": 1.05},
         "MQ9": {"raw_adc": 190, "voltage_V": 0.95},
         "MQ135": {"raw_adc": 240, "voltage_V": 1.20}
       }
     }'
   ```
   * **Expected Output**: Contains populated `aqi`, `predictions.anomaly`, `predictions.source`, and `advisory` fields.

3. **Forecast Model Endpoint**:
   ```bash
   curl http://127.0.0.1:8420/forecast/uno-q-001?horizon_hours=6
   ```

### 4. Interactive Terminal Dashboard (TUI)
Monitor real-time model inference stats, AQI, anomaly alerts, and source classification:
```bash
python3 scripts/unoq_tui.py
```

---

## How to Use Models from the Simulation Environment

NavosEdge includes a sensor simulator and multi-scenario runner to evaluate models under simulated environmental conditions (*Clean Indoor*, *Traffic*, *Dust / Construction*, *Combustion / Smoke*, *High Humidity*, *Stable*).

### 1. Running the Full Simulation Pipeline
Run the all-in-one simulation command specifying a scenario:

```bash
# Available scenarios: clean_indoor, traffic, dust_construction, combustion_smoke, high_humidity, stable
bash scripts/run_simulation.sh clean_indoor NAVOS-SIM-001 5
```

* **What happens**:
  1. Starts the Intelligence Server on `http://127.0.0.1:8420`.
  2. Waits for health checks to pass.
  3. Launches `SensorSimulator` to generate scenario readings every 5 seconds.
  4. Streams sensor payloads to the server, printing HTTP status, computed AQI, and predicted pollution source in real time.

```text
============================================================
NavosEdge — Simulation Mode
============================================================
  Scenario:  traffic
  Node ID:   NAVOS-SIM-001
  Interval:  5s
============================================================
[NAVOS] Server ready.
[SIM] Simulator started. Sending readings every 5s...
[SIM] Reading #1 → HTTP 200 | AQI: 42 | Source: Traffic Emission
[SIM] Reading #2 → HTTP 200 | AQI: 45 | Source: Traffic Emission
```

### 2. Interactive Terminal Display Simulation
To view live TUI dashboard during simulation:
```bash
bash run_display_simulation.sh
```

### 3. Programmatic Python Simulation Usage
You can import and use the `SensorSimulator` class directly in custom test scripts:

```python
import time
import json
import urllib.request
from simulation.sensor_simulator import SensorSimulator

# Initialize simulator for a specific scenario
sim = SensorSimulator(node_id="NAVOS-SIM-001", scenario="combustion_smoke", seed=42)

# Generate a simulated sensor reading payload
reading = sim.generate()

# Send payload to Intelligence Server
url = "http://127.0.0.1:8420/hardware/data"
payload = json.dumps(reading).encode("utf-8")
req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})

with urllib.request.urlopen(req) as resp:
    result = json.loads(resp.read().decode("utf-8"))
    print("AQI:", result.get("aqi"))
    print("Anomaly Status:", result["predictions"]["anomaly"]["safety_status"])
    print("Predicted Source:", result["predictions"]["source"]["value"])
```

---

## Artifact Locations (PyTorch-Free)

| Artifact | File Name | Deployment Path | Description |
|---|---|---|---|
| **NumPy Weights** | `gasnet_weights.npz` | `Training/models/`, `Intelligence/Server/models/`, `Intelligence/Server/artifacts/` | Pure NumPy weight matrices for zero-dependency edge inference. |
| **GasNet Metadata** | `model_metadata.json` | `Training/models/`, `Intelligence/Server/models/`, `Intelligence/Server/artifacts/` | Feature ordering, class labels, scaler means/scales, $T_{cal}$. |
| **Preprocessing Bundle** | `preprocess.pkl` | `Training/models/`, `Intelligence/Server/artifacts/` | Scikit-learn StandardScaler and LabelEncoder objects. |
| **Source Classifier Model** | `source_classifier_model.pkl` | `Intelligence/Server/artifacts/` | DecisionTree model and scaler bundle. |
| **Source Reference Stats** | `source_classifier_stats.json` | `Intelligence/Server/artifacts/` | Robust per-class feature distribution statistics. |
| **Source Classifier Metadata** | `source_classifier_metadata.json` | `Intelligence/Server/artifacts/` | Source Classifier version, tree depth, and evaluation metrics. |
| **Historical Sensor Store** | `readings.jsonl` | `Intelligence/Server/data/readings/uno-q-001/` | Chronological historical sensor readings for AR(p) forecasting. |

---

## Adding Future Data & Retraining Workflow

To add future sensor collection sessions:

1. Place new CSV files in the respective folder:
   - `dataset/DHT22_Dataset/session_05.csv`
   - `dataset/MPM_10_Dataset/session_5.csv`
   - `dataset/MQ_Dataset/session_04.csv`
2. Execute the PyTorch-free retraining script:
   ```bash
   python3 Training/retrain.py
   ```
3. Run test verification:
   ```bash
   bash scripts/run_all_tests.sh
   ```

---

## Restoring Previous Model Artifacts

If you need to rollback to a previous model iteration:

1. Navigate to the desired backup folder:
   ```bash
   cd Intelligence/Server/artifacts/backups/backup_<timestamp>
   ```
2. Copy backup files back to `Intelligence/Server/artifacts/` and `Intelligence/Server/models/`.
3. Restart the server service to reload model weights.

---

## Edge Resource Verification (Arduino UNO Q)

- **PyTorch-Free**: Completely eliminates PyTorch library footprint ($\approx 500\text{ MB}+$ saved).
- **Memory Footprint**: Pure NumPy inference consumes $< 5 \text{ MB}$ RAM.
- **Model Parameters**: TinyGasNet has $\approx 1,500$ parameters; DecisionTree has depth $\le 8$.
- **Disk Usage**: Total artifact footprint is $< 500 \text{ KB}$.
- Fully optimized for Arduino UNO Q's 2 GB RAM and 16 GB eMMC storage environment.
