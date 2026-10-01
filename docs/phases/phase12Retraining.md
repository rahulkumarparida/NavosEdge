# NavosEdge Phase 12 — PyTorch-Free Model Retraining & Calibration Documentation

## Overview

NavosEdge Phase 12 implements a complete **100% PyTorch-Free** model retraining, range calibration, and history-priming pipeline using sensor measurements in `dataset/`. By eliminating the heavy PyTorch dependency ($\approx 500\text{ MB}+$ installation size), NavosEdge ensures ultra-lightweight Edge-AI performance tailored for Arduino UNO Q (2 GB RAM / 16 GB eMMC) using pure NumPy and Scikit-learn.

---

## Component Architecture & Retraining Division (PyTorch-Free)

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
python Training/retrain.py
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
   python Training/retrain.py
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
