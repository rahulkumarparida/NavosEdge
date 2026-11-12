# NavosEdge — Anomaly Detection Validation & FPR Report (Part C)

**Reproducibility Script:** `experiments/phase8/run_gasnet_and_anomaly_study.py`  
**Saved Results:** `experiments/phase8/results/phase8_gasnet_and_anomaly.json`

---

## 1. Investigation of `0.1556` FPR in 85-Step Controlled Sequence

In Phase 7 (`n = 75` post-warmup samples: `45` normal, `30` spike), `AnomalyEngine` produced `TP=29, FP=7, TN=38, FN=1` (`Precision=0.8056`, `Recall=0.9667`, `FPR=0.1556`). Tracing all `7` false-positive steps (`[33, 37, 39, 55, 56, 57, 58]`) reveals two distinct root causes:

1. **Post-Spike Baseline Recovery Lag (`steps 55, 56, 57, 58` — 4 of 7 FPs):**
   - Immediately after the `pm_spike` window (`steps 40–54`) ends, the periodic baseline refit at `step 55` produced skewed OLS/EMA expectations (`MQ9_voltage_V expected = 0.3113 V` vs `actual = 0.751 V`; `temperature_C expected = 17.97 °C` vs `actual = 24.51 °C`), causing `4` consecutive post-spike recovery samples to score `3.24–4.43` (`HIGH`).
2. **Normal Wave Oscillation vs Tight MAD (`steps 33, 37, 39` — 3 of 7 FPs):**
   - Sinusoidal `clean_background` oscillation on `MQ2_raw_adc` (`212` vs `expected 180.1`) exceeded the tight clean-air MAD window (`score = 2.81` at step 33).

---

## 2. Long-Horizon Normal Diurnal False-Alarm Rate

- **Experiment:** `360` samples (`60s` interval = `6.0` hours simulated, `350` post-warmup = `5.833` hours) of `ScenarioGenerator("clean_background", seed=42)`.
- **Measured Result:** `67` false positives over `5.833` hours = **`11.486` false alarms/hour** (`FPR = 19.1%`).
- **Recommendation (Evidence-Driven):** Add spike-contamination exclusion / post-event cooldown before OLS refits (to eliminate `steps 55–58` recovery lag) and enforce a minimum MAD floor for integer ADC counts (`MQ*_raw_adc`) so normal 10-bit quantization/diurnal waves do not trigger `HIGH`/`MEDIUM` alerts. (Thresholds were **not** modified during Phase 8.)

---

## 3. Investigation of `REAL_RECORDED_DATA` `session_1` Flagged Events

Replaying the first `300` rows of `dataset/{MPM_10,DHT22,MQ}_Dataset/session_1` (unlabeled) flagged exactly **2 events**, both correctly classified as **`is_hardware_fault = True`** (`score = 5.0, severity = HIGH`):

| Row Index | Timestamp | `pm1_0` | `pm2_5` | `pm10` | `is_hardware_fault` | Diagnostic Interpretation |
| :---: | :--- | :---: | :---: | :---: | :---: | :--- |
| `98` | `2026-09-30 20:33:07` | `174.0` | **`64,513.0`** | `4,864.0` | `True` | Optical PM UART byte-alignment / overflow glitch (`64513` ≈ `0xFC01`). |
| `190` | `2026-09-30 20:36:15` | `192.0` | `302.0` | **`22,784.0`** | `True` | Optical PM UART frame glitch (`22784` ≈ `0x5900`). |

*Note: No accuracy metric is reported for `session_1` because ground-truth labels do not exist.*

