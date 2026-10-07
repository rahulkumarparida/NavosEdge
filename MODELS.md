# NavosEdge Models & AI/ML Algorithms Specification

This document details all Artificial Intelligence (AI), Machine Learning (ML), and statistical inference algorithms implemented across the **NavosEdge** edge-computing environmental monitoring platform.

---

## Table of Contents

1. [Architectural Overview & Intelligence Pipeline](#1-architectural-overview--intelligence-pipeline)
2. [Anomaly Detection Subsystem](#2-anomaly-detection-subsystem)
   - [Use & Objectives](#21-use--objectives)
   - [How It Is Used & Algorithmic Mechanics](#22-how-it-is-used--algorithmic-mechanics)
   - [When It Works & Lifecycle Triggers](#23-when-it-works--lifecycle-triggers)
   - [Overall Data Flow](#24-overall-data-flow)
3. [Forecasting Subsystem](#3-forecasting-subsystem)
   - [Use & Objectives](#31-use--objectives)
   - [How It Is Used & Algorithmic Mechanics](#32-how-it-is-used--algorithmic-mechanics)
   - [When It Works & Lifecycle Triggers](#33-when-it-works--lifecycle-triggers)
   - [Overall Data Flow](#34-overall-data-flow)
4. [Source Classifier Subsystem](#4-source-classifier-subsystem)
   - [Use & Objectives](#41-use--objectives)
   - [How It Is Used & Algorithmic Mechanics](#42-how-it-is-used--algorithmic-mechanics)
   - [When It Works & Lifecycle Triggers](#43-when-it-works--lifecycle-triggers)
   - [Overall Data Flow](#44-overall-data-flow)
5. [Advisory Engine Subsystem](#5-advisory-engine-subsystem)
   - [Use & Objectives](#51-use--objectives)
   - [How It Is Used & Algorithmic Mechanics](#52-how-it-is-used--algorithmic-mechanics)
   - [When It Works & Lifecycle Triggers](#53-when-it-works--lifecycle-triggers)
   - [Overall Data Flow](#54-overall-data-flow)
6. [GasNet / TinyGasNet Neural Network](#6-gasnet--tinygasnet-neural-network)
   - [Use & Objectives](#61-use--objectives)
   - [How It Is Used & Algorithmic Mechanics](#62-how-it-is-used--algorithmic-mechanics)
   - [When It Works & Lifecycle Triggers](#63-when-it-works--lifecycle-triggers)
   - [Overall Data Flow](#64-overall-data-flow)
7. [Regulatory AQI Engine](#7-regulatory-aqi-engine)
   - [Use & Objectives](#71-use--objectives)
   - [How It Is Used & Algorithmic Mechanics](#72-how-it-is-used--algorithmic-mechanics)
   - [When It Works & Lifecycle Triggers](#73-when-it-works--lifecycle-triggers)
   - [Overall Data Flow](#74-overall-data-flow)
8. [Summary Matrix of AI/ML Components](#8-summary-matrix-of-aiml-components)

---

## 1. Architectural Overview & Intelligence Pipeline

NavosEdge runs a modular, edge-optimized intelligence pipeline that processes sensor telemetry on embedded edge devices (e.g., Arduino UNO Q, Raspberry Pi, industrial Linux gateways) and central servers with minimal memory and compute overhead.

The entire intelligence workflow is orchestrated by [`ProcessingService`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/services/processing.py#L31) in [`Intelligence/Server/app/services/processing.py`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/services/processing.py):

```
                        ┌──────────────────────────────────────────────┐
                        │        Sensor Payload (HTTP POST)            │
                        │  MQ2, MQ9, MQ135, DHT22 (T/H), MPM10-CS (PM) │
                        └──────────────────────┬───────────────────────┘
                                               │
                                               ▼
                        ┌──────────────────────────────────────────────┐
                        │   1. TinyGasNet / NumpyGasNetAdapter         │
                        │      - 2-Head MLP Gas Classification         │
                        │      - MC-Dropout Uncertainty (20 passes)    │
                        │      - Safety Thresholding (safe/unsafe)     │
                        └──────────────────────┬───────────────────────┘
                                               │
                                               ▼
                        ┌──────────────────────────────────────────────┐
                        │   2. ModularPipeline (Inline Fast Path)      │
                        │      - Sensor Health & Supply Rail Checks    │
                        │      - Inline EMA Baseline & Deviation Check │
                        │      - Step Persistence Forecast Baseline    │
                        └──────────────────────┬───────────────────────┘
                                               │
                                               ▼
                        ┌──────────────────────────────────────────────┐
                        │   3. Data Persistence Engine                 │
                        │      - Append-Only JSONL Storage             │
                        │      - Local Dataset CSV Logging (Phase 14)  │
                        └──────────────────────┬───────────────────────┘
                                               │
                                               ▼
                        ┌──────────────────────────────────────────────┐
                        │   4. Anomaly Detection Engine (Statistical)  │
                        │      - 3-Tier Baseline (EMA / OLS / Trend)   │
                        │      - Median Absolute Deviation (MAD) Score │
                        │      - Multi-Sensor Category Fusion + Bonus  │
                        └──────────────────────┬───────────────────────┘
                                               │
                                               ▼
                        ┌──────────────────────────────────────────────┐
                        │   5. Source Classifier (Hybrid Model)        │
                        │      - Feature Ratios (PM Coarse, MQ Ratios) │
                        │      - Decision Tree Class Probabilities     │
                        │      - IQR / MAD Gaussian Similarity Scoring │
                        │      - Mixed Pollution & Uncertainty Check   │
                        └──────────────────────┬───────────────────────┘
                                               │
                                               ▼
                        ┌──────────────────────────────────────────────┐
                        │   6. Forecasting Plugin (AR(p) Time-Series)  │
                        │      - Pure Python Least Squares (Gauss-Jord)│
                        │      - Multi-Step Rollout (PM1.0, 2.5, 10)   │
                        │      - Trend Classification & Persistence MAE│
                        └──────────────────────┬───────────────────────┘
                                               │
                                               ▼
                        ┌──────────────────────────────────────────────┐
                        │   7. Regulatory AQI Engine                   │
                        │      - EPA / CPCB Breakpoint Interpolation   │
                        │      - Dominant Pollutant Identification     │
                        └──────────────────────┬───────────────────────┘
                                               │
                                               ▼
                        ┌──────────────────────────────────────────────┐
                        │   8. Advisory Engine (Deterministic Expert)  │
                        │      - Air Quality Layer (AQI / PM Limits)   │
                        │      - Source Hypothesis Mitigation Advice   │
                        │      - Predictive Trend Caution Layer        │
                        │      - Ambient Weather Thermal Comfort Layer │
                        └──────────────────────┬───────────────────────┘
                                               │
                                               ▼
                        ┌──────────────────────────────────────────────┐
                        │   9. Aggregation & Dispatch                  │
                        │      - aggregate_intelligence() Result       │
                        │      - SSE Broadcast to Dashboards           │
                        │      - Async Telemetry Forward to Manager    │
                        └──────────────────────────────────────────────┘
```

---

## 2. Anomaly Detection Subsystem

Located in [`Intelligence/Server/app/anomaly/`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/anomaly/).

### 2.1 Use & Objectives
- **Detection of Environmental Outliers**: Detects abnormal baseline shifts across particulate matter concentrations, combustible/toxic gases, and ambient thermal conditions.
- **Hardware Fault Discrimination**: Differentiates true physical environmental events (such as pollution spikes or chemical releases) from hardware sensor failures (such as disconnected pins, railed ADC voltages, frozen ADC readings, or extreme rate-of-change jumps).
- **Explainability**: Outputs human-readable evidence strings and per-channel z-like robust scores rather than uninterpretable opaque flags.

### 2.2 How It Is Used & Algorithmic Mechanics

The subsystem is implemented by [`AnomalyEngine`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/anomaly/engine.py#L109), [`AnomalyDetector`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/anomaly/detector.py#L149), [`BaselineEstimator`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/anomaly/baseline.py#L51), [`ResidualTracker`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/anomaly/residuals.py#L26), and [`SensorHealthChecker`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/anomaly/sensor_health.py#L69).

#### A. 3-Tier Baseline Estimator (`baseline.py`)
Computes the expected value $\hat{y}(t)$ for each feature using an adaptive hierarchy:
1. **Level 1 (Bootstrapping / Calibrating)**: When fewer than 30 observations are available, uses an Exponentially Weighted Moving Average (EMA) with smoothing factor $\alpha = 0.1$:
   $$\text{EMA}_t = \alpha \cdot y_t + (1 - \alpha) \cdot \text{EMA}_{t-1}$$
2. **Level 2 (Learning / Monitoring)**: When $\ge 30$ observations are available, fits an Ordinary Least Squares (OLS) regression over diurnal cycles using sin/cos of the hour of day ($h \in [0, 24)$):
   $$y(t) = \beta_0 + \beta_1 \sin\left(\frac{2\pi h}{24}\right) + \beta_2 \cos\left(\frac{2\pi h}{24}\right)$$
   The design matrix $X \in \mathbb{R}^{n \times 3}$ is solved via normal equations $\beta = (X^T X)^{-1} X^T y$ in NumPy.
3. **Level 3 (Short-Term Trend Correction)**: Estimates short-term linear drift from the last 10 readings ($n=10$) via linear regression slope $m = \frac{\sum (x - \bar{x})(y - \bar{y})}{\sum (x - \bar{x})^2}$ in units/hour, adjusting the diurnal estimate:
   $$\hat{y}(t) = \hat{y}_{\text{OLS}}(t) + m \cdot \Delta t$$

#### B. Robust Residual Tracking & MAD Scoring (`residuals.py`)
- Calculates raw residual: $r_t = y_{\text{actual}} - \hat{y}_{\text{expected}}$.
- Normal distributions scale Median Absolute Deviation (MAD) using constant $1.4826$:
  $$\text{MAD} = \text{median}\left(|r_i - \text{median}(r)|\right)$$
- The robust anomaly score is computed as:
  $$\text{Score} = \frac{|r_t|}{\max(1.4826 \cdot \text{MAD}, \text{min\_floor})}$$
- Minimum deviation floors (`_MIN_DEVIATION_FLOORS`) prevent near-zero divisions and numerical instability (e.g., $3.0\,\mu\text{g/m}^3$ for PM2.5, $0.05\,\text{V}$ for gas voltages, $0.5^\circ\text{C}$ for temperature).

#### C. Sensor Health Validation (`sensor_health.py`)
Validates individual channel integrity against four failure criteria:
1. **Physical range bounds**: Flags impossible values outside valid physical limits (e.g., PM $< 0$ or $> 2000$, voltages $< 0\text{V}$ or $> 5\text{V}$).
2. **Supply rail saturation**: Detects short-to-GND ($V \le 0.01\text{V}$) or short-to-VCC ($V \ge 4.99\text{V}$).
3. **Sudden jump anomalies**: Checks maximum expected single-step change (e.g., $\Delta T > 15^\circ\text{C}$, $\Delta \text{PM10} > 500\,\mu\text{g/m}^3$).
4. **Frozen readings**: Flags sensors where the last 5 consecutive readings are bit-identical ($\text{variance} < 10^{-6}$).

#### D. Multi-Sensor Category Fusion (`detector.py`)
Combines feature scores across three categories:
- **Particulates** ($w_{\text{PM}} = 1.0$): $\max(\text{PM10}, \text{PM2.5}, \text{PM1.0})$
- **Gases** ($w_{\text{Gas}} = 0.8$): $\max(\text{MQ2}, \text{MQ9}, \text{MQ135})$
- **Environment** ($w_{\text{Env}} = 0.5$): $\max(T, H)$
- **Corroboration Bonus**: If both particulate and gas categories exceed the medium threshold ($\ge 2.0$), a bonus of $+0.3 \cdot \min(S_{\text{PM}}, S_{\text{Gas}})$ is added to reflect simultaneous cross-sensor physical correlation.
- **Severity Thresholds**:
  - `NONE`: $\text{Combined Score} < 2.0$
  - `MEDIUM`: $2.0 \le \text{Combined Score} < 3.0$
  - `HIGH`: $\text{Combined Score} \ge 3.0$

### 2.3 When It Works & Lifecycle Triggers
- **Per-Reading Trigger**: Executes synchronously in [`ProcessingService.process_reading`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/services/processing.py#L85) whenever a new [`SensorPayload`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/schemas/sensor.py) is ingested.
- **History Priming**: On first encounter with a node ID, [`_ensure_history_loaded`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/services/processing.py#L58) loads past 24 hours of data from JSONL storage into the rolling window.
- **Periodic Baseline Refit**: Every 15 minutes (`ANOMALY_MODEL_UPDATE_INTERVAL_MINUTES`), baselines and residual histories are refitted in the background using the updated rolling window.
- **Staleness Gating**: If data is older than 30 minutes (`ANOMALY_STALE_DATA_MINUTES`), the detector bypasses alert triggers, labels the record `STALE`, and degrades system state.

### 2.4 Overall Data Flow

```
SensorPayload Record
        │
        ▼
extract_features_from_record()  → [11 flat features: PMs, MQ Voltages & ADC, Temp, Humidity]
        │
        ▼
RollingWindow (24h bounded)      → Appends observation, checks timestamp freshness
        │
        ▼
SensorHealthChecker              → Per-channel status (GOOD, DEGRADED, FAILED, MISSING)
        │
        ▼
BaselineEstimator                → Generates expected values via EMA / OLS / Trend
        │
        ▼
ResidualTracker                  → Calculates residual and MAD-normalized score per feature
        │
        ▼
Multi-Sensor Fusion              → Computes category scores + corroboration bonus
        │
        ▼
DetectionResult                  → Produces AnomalyReport (detected, score, severity, explanations)
        │
        ▼
ProcessingService & SSE Stream   → Injected into PipelineResults and published via SSE
```

---

## 3. Forecasting Subsystem

Located in [`Intelligence/Server/app/forecast/`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/forecast/).

### 3.1 Use & Objectives
- **Short-Term Predictive Trends**: Predicts future concentrations of $PM_{1.0}$, $PM_{2.5}$, and $PM_{10}$ over configurable forecasting horizons (default 60 minutes, up to 24 hours) at discrete sampling steps (default 5 minutes).
- **Proactive Early Warning**: Enables mitigation before peak particulate exposure events materialize.
- **Zero Heavy ML Dependencies**: Operates on edge hardware without PyTorch, TensorFlow, or scikit-learn using pure Python and linear algebra.
- **Persistence Benchmarking**: Concurrently produces a persistence baseline ($y(t+k) = y(t)$) and reports Mean Absolute Error (MAE) against it to assess predictive utility.

### 3.2 How It Is Used & Algorithmic Mechanics

The subsystem is implemented by [`ForecastPlugin`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/forecast/plugin.py#L35), [`generate_forecast`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/forecast/model.py#L174), and [`ForecastStore`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/forecast/store.py).

#### A. Autoregressive AR(p) Formulation
For each PM channel independently, the model assumes:
$$y(t) = c + \sum_{i=1}^{p} \phi_i \cdot y(t-i) + \epsilon$$
Where:
- $p$ is the autoregressive lag order, dynamically chosen based on available data:
  $$p = \max\left(1, \min(6, \lfloor N/3 \rfloor, N - 2)\right)$$
- $\phi_1, \dots, \phi_p$ are lag coefficients; $c$ is the intercept.

#### B. Least-Squares Solver via Gauss-Jordan Elimination (`model.py`)
- Constructs design matrix $X \in \mathbb{R}^{(N-p) \times (p+1)}$ where row $t$ contains $[y(t-1), \dots, y(t-p), 1.0]$.
- Normal equations $\beta = (X^T X)^{-1} X^T y$ are solved using custom Gauss-Jordan elimination with partial pivoting in [`_solve_least_squares`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/forecast/model.py#L29).
- If the matrix is singular or data points are insufficient ($N < p + 2$), the model gracefully falls back to persistence.

#### C. Multi-Step Rollout & Clamping
- Generates predictions step-by-step: each predicted $\hat{y}(t+k)$ is appended to the autoregressive lag buffer to compute $\hat{y}(t+k+1)$.
- All predicted concentrations are clamped to non-negative values ($\hat{y} = \max(0.0, \hat{y})$) to reflect physical reality.

#### D. Trend Direction & Reliability Staging
- **Trend**:
  - Difference $\Delta = \hat{y}_{\text{final}} - \hat{y}_{\text{first}}$
  - $\Delta > 0.5\,\mu\text{g/m}^3 \implies \text{RISING}$
  - $\Delta < -0.5\,\mu\text{g/m}^3 \implies \text{FALLING}$
  - $|\Delta| \le 0.5\,\mu\text{g/m}^3 \implies \text{STABLE}$
- **Reliability Classification**:
  - `HIGH`: AR model fitted and history points $\ge 3 \times \text{min\_history\_points}$ ($\ge 36$ points).
  - `MEDIUM`: AR model fitted, but history points $< 3 \times \text{min\_history\_points}$.
  - `LOW`: AR fitting failed (matrix singular), using persistence baseline.
  - `UNAVAILABLE`: History points $< 12$ (`MIN_HISTORY_POINTS`).

#### E. Bounded 48-Hour Storage Architecture (`store.py`)
- Independent daily JSONL files: `data/forecast/{node_id}/{YYYY-MM-DD}.jsonl`.
- Retention window: Strict rolling 48 hours. Files outside the window are deleted; boundary files are rewritten to preserve only valid data.
- Streamed reads ensure memory usage remains bounded regardless of total lifetime.

### 3.3 When It Works & Lifecycle Triggers
- **Ingestion**: Ingests PM values asynchronously on every reading via [`ForecastPlugin.async_ingest`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/forecast/plugin.py#L105).
- **Inference**: Generates multi-step predictions asynchronously on every reading via [`ForecastPlugin.async_forecast`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/forecast/plugin.py#L142).
- **On-Demand API**: Serves queries via `GET /api/v1/forecast/nodes/{node_id}/predict` and `GET /forecast/{node_id}`.
- **Data Cleanup**: Pruning executes via `POST /api/v1/forecast/cleanup` or programmatic maintenance tasks.

### 3.4 Overall Data Flow

```
SensorPayload (PM1.0, PM2.5, PM10)
        │
        ▼
ForecastReadingInput             → Formatted payload ingested
        │
        ▼
ForecastStore.append()           → Written to data/forecast/{node_id}/{YYYY-MM-DD}.jsonl
        │
        ▼
ForecastStore.get_history()      → Reads rolling 48-hour history
        │
        ▼
generate_forecast()
   ├── Design Matrix X & Vector y
   ├── Gauss-Jordan Elimination  → Coefficients [phi_1..phi_p, intercept]
   ├── Iterative AR Rollout      → Multi-step forward predictions [t+5m, t+10m, ...]
   ├── Persistence Baseline      → Static rollout [last_value, last_value, ...]
   └── Benchmark MAE & Trend     → Computes error vs persistence and trend direction
        │
        ▼
ForecastResponse                 → Output channels, trend, reliability, mae_vs_persistence
        │
        ▼
aggregate_intelligence()         → Passed to Advisory Engine and SSE event dispatcher
```

---

## 4. Source Classifier Subsystem

Located in [`Intelligence/Server/app/source_classifier/`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/source_classifier/).

### 4.1 Use & Objectives
- **Attribution of Environmental Pollution**: Classifies ambient conditions into 10 broad environmental source hypotheses:
  1. `CLEAN_OR_BACKGROUND`: Low, stable baseline conditions.
  2. `TRAFFIC`: Vehicle emissions and roadside PM (elevated CO/MQ9 and fine PM).
  3. `HEAVY_DUST`: Resuspended coarse road/soil dust (high PM10/PM2.5 coarse ratio, low MQ response).
  4. `CONSTRUCTION_ACTIVITY`: Coarse dust resuspension combined with diesel equipment emissions (elevating MQ9).
  5. `BIOMASS_OR_WASTE_BURNING`: Smoke emissions from open burning (elevating MQ2 and fine PM).
  6. `INDUSTRIAL_OR_GENERATOR_EMISSIONS`: Industrial exhaust or stationary generator fumes (elevating MQ135).
  7. `COOKING_OR_FUEL_COMBUSTION`: Indoor or food preparation emissions (elevating MQ2 and PM1.0).
  8. `INDOOR_ACTIVITY`: Typical indoor environment with moderate PM and baseline gas readings.
  9. `MIXED_POLLUTION`: Complex multi-source overlapping pollution.
  10. `UNKNOWN`: Out-of-distribution input or insufficient evidence.
- **Physically Grounded Uncertainty**: Openly distinguishes between pattern match similarity and model confidence, preventing false claims of chemical identification from low-cost MOS sensors.

### 4.2 How It Is Used & Algorithmic Mechanics

The subsystem is implemented by [`SourceClassifier`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/source_classifier/classifier.py#L44), [`extract_source_features`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/source_classifier/features.py#L23), [`compute_combined_scores`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/source_classifier/scoring.py#L177), and [`ReferenceStats`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/source_classifier/scoring.py#L30).

#### A. Feature Engineering & Ratio Derivations (`features.py`)
Extracts 8 raw sensor measurements and computes 6 physically meaningful derived features:
- **PM Coarse Ratio**: $\frac{\text{PM10}}{\text{PM2.5}}$ — high ratio indicates coarse dust/construction; low ratio indicates fine combustion particles.
- **PM Fine Ratio**: $\frac{\text{PM2.5}}{\text{PM1.0}}$ — distinguishes aerosol particle distribution.
- **MQ Mean & Max**: Mean $\frac{V_{\text{MQ2}} + V_{\text{MQ9}} + V_{\text{MQ135}}}{3}$ and Max voltage across all MOS gas sensors.
- **MQ2 / MQ9 Ratio**: Discriminates smoke-dominant vs. CO/exhaust-dominant emissions.
- **MQ135 / MQ2 Ratio**: Discriminates general air quality gases ($\text{NH}_3, \text{NO}_x$) from combustion smoke.

#### B. Hybrid Scoring Mechanism (`scoring.py`)
Combines two complementary inference paths:
1. **Decision Tree Classifier (`scikit-learn`)**:
   - A shallow, interpretable `DecisionTreeClassifier` trained on verified environmental distributions.
   - Evaluates standardized features and outputs calibrated class probabilities $P_{\text{DT}}(\text{class})$.
2. **Empirical Reference Statistics Similarity**:
   - Loads per-category empirical distribution metrics (`source_classifier_stats.json`): median, MAD, 25th percentile ($Q_{25}$), and 75th percentile ($Q_{75}$).
   - Expands the IQR $[Q_{25}, Q_{75}]$ by a $\pm 10\%$ tolerance factor (`tolerance_fraction = 0.10`).
   - If an observed value lies within the expanded IQR, similarity is high ($0.8 \le \text{sim} \le 1.0$).
   - If outside, decays smoothly using a Gaussian falloff scaled by the feature MAD:
     $$\text{sim}_i = \exp\left( -0.5 \left(\frac{\text{distance}_i}{\max(\text{MAD}_i, 0.1)}\right)^2 \right)$$
   - Category similarity is the mean across all available features.
3. **Combined Match Score**:
   $$\text{match\_score} = w_{\text{DT}} \cdot P_{\text{DT}} + w_{\text{sim}} \cdot \text{Similarity}$$
   Default weights: $w_{\text{DT}} = 0.6$, $w_{\text{sim}} = 0.4$. If the Decision Tree artifact is unavailable, it operates in similarity-only mode ($w_{\text{sim}} = 1.0$).

#### C. Mixed Pollution & Uncertainty Detection
- **Mixed Pollution**: If $\ge 3$ distinct categories score $\ge 0.40$ (`mixed_pollution_threshold`), the engine injects `MIXED_POLLUTION` as a top hypothesis.
- **Uncertainty Evaluation**: Marks predictions uncertain if:
  - Top match score $< 0.35$ (`uncertainty_score_threshold`).
  - Score gap between top two candidates $< 0.10$ (`uncertainty_gap_threshold`).
  - Data quality is degraded or missing $\ge 30\%$ of features.

### 4.3 When It Works & Lifecycle Triggers
- **Inference Trigger**: Runs synchronously on every incoming reading inside [`ProcessingService.process_reading`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/services/processing.py#L156).
- **Graceful Failure**: If model artifacts (`source_classifier_model.pkl` or `source_classifier_stats.json`) are absent, returns `UNKNOWN` with limitation messages without throwing exceptions.
- **Offline Retraining / Calibration**: Retrained and calibrated via [`Training/retrain.py`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Training/retrain.py#L470) or `python -m app.source_classifier.train`.

### 4.4 Overall Data Flow

```
SensorPayload (Voltages, Particulates, Environment)
        │
        ▼
extract_source_features()        → 8 raw features + 6 derived physical ratios
        │
        ▼
_assess_data_quality()           → Validates rail limits, freshness, missing features
        │
        ▼
Hybrid Scoring Execution:
   ├── Decision Tree Inference   → Produces calibrated probabilities P_DT
   └── IQR/MAD Reference Stats   → Computes Gaussian-decayed feature similarities
        │
        ▼
compute_combined_scores()        → Weighted score = 0.6*P_DT + 0.4*Similarity
        │
        ▼
detect_mixed_pollution()         → Evaluates multi-source overlapping conditions
        │
        ▼
assess_uncertainty()             → Analyzes score gap, score floors, and quality
        │
        ▼
SourceClassificationResult       → Ranked hypotheses, top_source, confidence, limitations
        │
        ▼
ProcessingService                → Stored in PipelineResults, fed to Advisory Engine, SSE
```

---

## 5. Advisory Engine Subsystem

Located in [`Intelligence/Server/app/advisory/`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/advisory/).

### 5.1 Use & Objectives
- **Actionable Health & Facility Guidance**: Synthesizes complex telemetry, ML classifications, forecasts, and air quality indices into unambiguous recommendations for occupants and site operators.
- **Strictly Deterministic Expert System**: Operates on verified decision tables rather than generative LLMs, guaranteeing zero hallucination, repeatable outputs, and auditable safety recommendations.
- **Action Consolidation**: Merges discrete precautions (respiratory protection, ventilation, traffic avoidance) across air quality, source attribution, forecasting, and ambient comfort domains.

### 5.2 How It Is Used & Algorithmic Mechanics

The subsystem is implemented by [`AdvisoryEngine`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/advisory/engine.py#L13), [`rules.py`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/advisory/rules.py), and [`content.py`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/advisory/content.py).

#### A. 4-Layer Rule Evaluation (`rules.py`)
Evaluates four distinct environmental dimensions:

1. **Layer 1: Current Air Quality Rule Layer** ([`current_air_quality`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/advisory/rules.py#L73)):
   Evaluates calculated AQI, $PM_{2.5}$, and $PM_{10}$ against graduated thresholds:
   - `CRITICAL`: $\text{AQI} \ge 201$ $\implies$ Actions: *"Avoid outdoor exposure"*, *"Use suitable respiratory protection"*.
   - `SEVERE`: $\text{AQI} \ge 151 \lor \text{PM2.5} \ge 150 \lor \text{PM10} \ge 250$ $\implies$ Actions: *"Limit outdoor activity"*, *"Keep windows closed"*.
   - `HIGH`: $\text{AQI} \ge 101 \lor \text{PM2.5} \ge 55 \lor \text{PM10} \ge 100$ $\implies$ Actions: *"Reduce prolonged outdoor activity"*, *"Sensitive people take care"*.
   - `MODERATE`: $\text{AQI} \ge 51 \lor \text{PM2.5} \ge 35 \lor \text{PM10} \ge 50$ $\implies$ Actions: *"Prefer well-ventilated areas"*.
   - `NORMAL`: Below moderate thresholds.

2. **Layer 2: Source Attribution Advice Layer** ([`source_advice`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/advisory/rules.py#L104)):
   Inspects the top source category from the Source Classifier. If confidence $\ge 0.60$, issues targeted contextual actions:
   - `TRAFFIC`: *"Reduce exposure near busy roads when practical."*
   - `HEAVY_DUST`: *"Avoid visibly dusty areas and use respiratory protection if needed."*
   - `CONSTRUCTION`: *"Avoid active dust-generating areas when practical."*
   - `COMBUSTION` / `BIOMASS_OR_WASTE_BURNING`: *"Avoid smoke and keep indoor air protected."*
   - `INDUSTRIAL`: *"Limit exposure near industrial zones."*
   - `INDOOR_ACTIVITY`: *"Improve indoor ventilation."*

3. **Layer 3: Forecast Trend Advice Layer** ([`forecast_advice`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/advisory/rules.py#L134)):
   Inspects projected $PM_{2.5}$ trend from the Forecasting subsystem. If future concentration increases by $\ge 10\%$ (`forecast_change_fraction`) with confidence $\ge 0.50$, escalates advisory severity to `HIGH` and advises: *"Take precautions before the forecast period."*

4. **Layer 4: Weather & Comfort Layer** ([`weather_advice`](file:///home/rahulroxx/Study/Projects/NavosEdge/Intelligence/Server/app/advisory/rules.py#L163)):
   Evaluates temperature ($T_{\text{hot}} = 32^\circ\text{C}, T_{\text{cold}} = 16^\circ\text{C}$) and relative humidity ($H_{\text{humid}} = 75\%, H_{\text{dry}} = 30\%$) into human bioclimatic comfort categories: `HOT_HUMID`, `HOT`, `COLD_DRY`, `COLD`, `HUMID`, `DRY`, or `COMFORTABLE`.

#### B. Severity Arbitration & Phrasing Diversity
- **Winning Severity Resolution**: Ranked priority:
  $$\text{CRITICAL} (4) > \text{SEVERE} (3) > \text{HIGH} (2) > \text{MODERATE} (1) > \text{NORMAL} (0)$$
  The highest severity across pollution layers (Air Quality, Source, Forecast) is selected as the winning severity.
- **Action Merging**: All actions across active layers are collected and deduplicated preserving priority order.
- **Deterministic Text Variation**: To prevent repetitive UI messaging without introducing non-deterministic drift, selects variant strings using a numeric hash seed:
  $$\text{seed} = \lfloor |\text{AQI} \cdot 100 + \text{PM2.5} \cdot 10 + T \cdot 10 + H| \rfloor$$

### 5.3 When It Works & Lifecycle Triggers
- **End-of-Pipeline Trigger**: Executes automatically inside [`aggregate_intelligence`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/services/aggregation.py#L77) for every processed reading after AQI, source classification, and forecasting results are assembled.
- **Modular Pipeline Fallback**: A simplified inline heuristic advisory engine is also embedded in [`ModularPipeline.generate_advisory`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/services/pipeline.py#L152) for low-overhead execution.

### 5.4 Overall Data Flow

```
Compiled Reading Data (AQI, PMs, Temp, Humidity, Predictions)
        │
        ├──────────────────────┬──────────────────────┬──────────────────────┐
        ▼                      ▼                      ▼                      ▼
current_air_quality()    source_advice()       forecast_advice()     weather_advice()
(AQI/PM Thresholds)     (Source Mitigation)    (Trend Escalation)    (Bioclimatic Comfort)
        │                      │                      │                      │
        └──────────────────────┼──────────────────────┘                      │
                               ▼                                             │
                       Arbitration:                                          │
                       - Winning Severity (Max Priority)                     │
                       - Merged Action Set                                   │
                       - Combined Advisory Phrasing                          │
                               │                                             │
                               ▼                                             ▼
                       AdvisoryResult (severity, advice, actions, weather_advice)
                               │
                               ▼
                       IntelligenceResult
```

---

## 6. GasNet / TinyGasNet Neural Network

Located in [`Intelligence/Server/app/services/numpy_inference.py`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/services/numpy_inference.py), [`Training/mq_train.py`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Training/mq_train.py), and [`Training/retrain.py`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Training/retrain.py).

### 6.1 Use & Objectives
- **Multi-Class Gas Identification**: Classifies multi-channel Metal Oxide Semiconductor (MOS) sensor arrays (`MQ2`, `MQ9`, `MQ135`) into 8 target classes: `LPG`, `Methane`, `Propane`, `Hydrogen`, `CO`, `Alcohol`, `Smoke`, and `CleanAir`.
- **Binary Hazard Safety Staging**: Determines whether current gas concentrations exceed 8-hour Time-Weighted Average (TWA) occupational safety exposure limits (`safe` vs `unsafe`).
- **Uncertainty Quantification**: Uses Monte Carlo Dropout (MC-Dropout) to estimate model epistemic uncertainty, flagging novel gas mixtures or out-of-distribution inputs.

### 6.2 How It Is Used & Algorithmic Mechanics

Implemented by [`NumpyGasNetAdapter`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/services/numpy_inference.py#L26) (pure NumPy for production edge runtime) and [`NumPyTinyGasNet`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Training/retrain.py#L61) / PyTorch for training.

#### A. Multi-Head Multi-Layer Perceptron (MLP) Architecture
- **Input (5 features)**: `MQ2_V`, `MQ9_V`, `MQ135_V`, `temperature_C`, `humidity_pct`
- **Feature Standardization**: Transformed using precomputed `scaler_mean` and `scaler_scale`:
  $$x = \frac{x_{\text{raw}} - \mu}{\sigma}$$
- **Hidden Layer 1**: $\text{Linear}(5, 32) \to \text{ReLU} \to \text{Dropout}(p=0.1)$
- **Hidden Layer 2**: $\text{Linear}(32, 16) \to \text{ReLU} \to \text{Dropout}(p=0.1)$
- **Dual Heads**:
  - **Classification Head**: $\text{Linear}(16, 8) \to \text{Logits}_c \to \text{Softmax}\left(\frac{\text{Logits}_c}{T_{\text{cal}}}\right)$
  - **Safety Head**: $\text{Linear}(16, 1) \to \text{Logit}_s \to \text{Sigmoid}(\text{Logit}_s)$

#### B. Monte Carlo Dropout (MC-Dropout) Inference
1. Executes $N_{\text{mc}} = 20$ stochastic forward passes with dropout active ($p_{\text{drop}} = 0.1$, inverted scaling $\frac{1}{1 - p_{\text{drop}}}$).
2. Averages class probability distributions: $\bar{P} = \frac{1}{20} \sum_{i=1}^{20} P^{(i)}$.
3. Mean safety probability: $\bar{P}_{\text{unsafe}} = \frac{1}{20} \sum_{i=1}^{20} P_{\text{safety}}^{(i)}$.
4. **Predictive Entropy Uncertainty**: Computes normalized Shannon entropy bounded in $[0, 1]$:
   $$H = -\frac{\sum_{c} \bar{P}_c \ln(\bar{P}_c + 10^{-12})}{\ln(N_{\text{classes}})}$$
   High entropy ($H > 0.60$) indicates ambiguous or untrained sensor response patterns.

#### C. Temperature Scaling ($T_{\text{cal}}$)
During training, optimal calibration temperature $T_{\text{cal}}$ is learned via negative log-likelihood (NLL) grid search on the validation split to align predicted softmax probabilities with true empirical accuracy.

### 6.3 When It Works & Lifecycle Triggers
- **Primary Inference**: Executes at the start of [`ProcessingService.process_reading`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/services/processing.py#L102) for every incoming sensor packet.
- **Zero PyTorch Footprint**: Runs in pure NumPy via [`NumpyGasNetAdapter`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/services/numpy_inference.py#L26), loading weights from `gasnet_weights.npz` and metadata from `model_metadata.json`.

### 6.4 Overall Data Flow

```
MQ2_V, MQ9_V, MQ135_V, Temperature, Humidity
        │
        ▼
StandardScaler Transformation    → (x - scaler_mean) / scaler_scale
        │
        ▼
20 Stochastic Forward Passes     → Hidden layers with active dropout mask
        │
        ├── Classification Head  → Logits / T_cal → Softmax
        └── Safety Head          → Logits → Sigmoid
        │
        ▼
MC Aggregation
        ├── Mean Class Proportions → Gas Class Label & Confidence
        ├── Normalized Entropy     → Predictive Uncertainty [0, 1]
        └── Mean Safety Score      → safe / unsafe Status
        │
        ▼
InferenceResult                  → Emitted to ModularPipeline, storage, and Advisory
```

---

## 7. Regulatory AQI Engine

Located in [`Intelligence/Server/app/aqi/`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/aqi/).

### 7.1 Use & Objectives
- **Regulatory Standard Compliance**: Calculates official Air Quality Index (AQI) values strictly following US EPA (Environmental Protection Agency) and Indian CPCB (Central Pollution Control Board) standards.
- **Dominant Pollutant Tracking**: Identifies the primary health-limiting pollutant among $PM_{2.5}$, $PM_{10}$, and $PM_{1.0}$.

### 7.2 How It Is Used & Algorithmic Mechanics

Implemented by [`AQICalculator`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/aqi/calculator.py#L12) and [`AQIService`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/aqi/service.py).

#### A. Piecewise Linear Breakpoint Interpolation
For pollutant concentration $C_p$, the sub-index $I_p$ is calculated using official breakpoint brackets $[C_{\text{low}}, C_{\text{high}}]$ mapped to index brackets $[I_{\text{low}}, I_{\text{high}}]$:
$$I_p = \frac{I_{\text{high}} - I_{\text{low}}}{C_{\text{high}} - C_{\text{low}}} (C_p - C_{\text{low}}) + I_{\text{low}}$$

#### B. Overall AQI & Dominant Pollutant Selection
$$\text{AQI} = \max\left(I_{\text{PM2.5}}, I_{\text{PM10}}, I_{\text{PM1.0}}\right)$$
$$\text{Dominant Pollutant} = \arg\max_{p}\left(I_p\right)$$

#### C. EPA Staging Table
- $0 - 50$: `Good`
- $51 - 100$: `Moderate`
- $101 - 150$: `Unhealthy for Sensitive Groups`
- $151 - 200$: `Unhealthy`
- $201 - 300$: `Very Unhealthy`
- $> 300$: `Hazardous`

### 7.3 When It Works & Lifecycle Triggers
- **Per-Reading Trigger**: Computed in [`ProcessingService.process_reading`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/services/processing.py#L201), updating the latest state in `data/aqi_latest.json`.
- **API Access**: Serves real-time queries via `GET /aqi/latest`.

### 7.4 Overall Data Flow

```
PM1.0, PM2.5, PM10 Concentrations
        │
        ▼
AQICalculator.calculate_sub_index() → Computes piecewise linear sub-index per PM
        │
        ▼
Dominant Pollutant Selection        → Overall AQI = max(sub-indices)
        │
        ▼
Category Mapping                    → Maps score to regulatory text category
        │
        ▼
AQICalculationResult & Storage      → Cached in aqi_latest.json & ingested by Advisory Engine
```

---

## 8. Summary Matrix of AI/ML Components

| Subsystem / Model | Primary Algorithm / Paradigm | Inputs | Key Outputs | Trigger / Timing | Computational Dependencies |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **[Anomaly Detection](#2-anomaly-detection-subsystem)** | Adaptive 3-Tier Baseline (EMA $\to$ Diurnal OLS $\to$ Trend) + Robust MAD Scoring + Cross-Sensor Fusion | 11 canonical channels (PMs, MQ Voltages & ADCs, Temp, Hum) | Anomaly flag, z-like score, severity (`NONE`/`MEDIUM`/`HIGH`), explanation strings | Every reading + 15 min periodic refit | NumPy |
| **[Forecasting](#3-forecasting-subsystem)** | Autoregressive AR(p) with Gauss-Jordan Normal Equations Solver + Persistence Benchmark | Rolling 48h history of $PM_{1.0}$, $PM_{2.5}$, $PM_{10}$ | Multi-step predicted series ($15-1440$ min), trend (`RISING`/`FALLING`/`STABLE`), reliability, MAE | Every reading + on-demand via REST API | Pure Python (Zero external packages) |
| **[Source Classifier](#4-source-classifier-subsystem)** | Hybrid Supervised Decision Tree + Non-parametric IQR/MAD Gaussian Similarity Scoring | 8 raw features + 6 derived physical ratios (PM Coarse, MQ ratios) | Top 5 ranked source categories, match score, confidence, mixed pollution flag | Every reading | scikit-learn, joblib, NumPy |
| **[Advisory Engine](#5-advisory-engine-subsystem)** | Multi-Layer Deterministic Expert System (4 decision layers + hash-seeded phrasing selection) | AQI, PMs, Temp, Humidity, Top Source Hypothesis, Forecast Trend | Overall severity, consolidated action checklist, weather advice | End of every reading pipeline | Pure Python |
| **[GasNet / TinyGasNet](#6-gasnet--tinygasnet-neural-network)** | 2-Head MLP (32 $\to$ 16) with 20-Pass Monte Carlo Dropout & Temperature Calibration | MQ2, MQ9, MQ135 voltages, temperature, humidity | Gas class (8 classes), safety (`safe`/`unsafe`), Shannon entropy uncertainty | Initial step of every reading | Pure NumPy (PyTorch-free edge adapter) |
| **[AQI Engine](#7-regulatory-aqi-engine)** | EPA / CPCB Piecewise Linear Breakpoint Interpolation | $PM_{1.0}$, $PM_{2.5}$, $PM_{10}$ concentrations | Overall AQI, dominant pollutant, hazard category | Every reading | Pure Python |

---

## 9. Code Reference Index

All referenced source code files:
- Server Entry Point: [`Intelligence/Server/app/main.py`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/main.py)
- Core Processing Service: [`Intelligence/Server/app/services/processing.py`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/services/processing.py)
- Fast Inline Pipeline: [`Intelligence/Server/app/services/pipeline.py`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/services/pipeline.py)
- Aggregation Service: [`Intelligence/Server/app/services/aggregation.py`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/services/aggregation.py)
- Anomaly Engine & Detector: [`Intelligence/Server/app/anomaly/engine.py`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/anomaly/engine.py), [`detector.py`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/anomaly/detector.py), [`baseline.py`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/anomaly/baseline.py), [`residuals.py`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/anomaly/residuals.py), [`sensor_health.py`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/anomaly/sensor_health.py)
- Forecast Subsystem: [`Intelligence/Server/app/forecast/plugin.py`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/forecast/plugin.py), [`model.py`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/forecast/model.py), [`store.py`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/forecast/store.py)
- Source Classifier: [`Intelligence/Server/app/source_classifier/classifier.py`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/source_classifier/classifier.py), [`features.py`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/source_classifier/features.py), [`scoring.py`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/source_classifier/scoring.py), [`categories.py`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/source_classifier/categories.py)
- Advisory Engine: [`Intelligence/Server/app/advisory/engine.py`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/advisory/engine.py), [`rules.py`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/advisory/rules.py), [`content.py`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/advisory/content.py)
- NumPy TinyGasNet Inference: [`Intelligence/Server/app/services/numpy_inference.py`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/services/numpy_inference.py)
- AQI Calculator: [`Intelligence/Server/app/aqi/calculator.py`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/aqi/calculator.py), [`service.py`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server/app/aqi/service.py)
- Model Training & Retraining: [`Training/mq_train.py`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Training/mq_train.py), [`Training/retrain.py`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Training/retrain.py), [`Training/export_gasnet.py`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Training/export_gasnet.py)
