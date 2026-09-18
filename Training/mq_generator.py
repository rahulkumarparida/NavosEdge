#!/usr/bin/env python3
"""
Synthetic dataset generator for MQ-2, MQ-9, MQ-135 gas sensors.
Produces a CSV with columns:
sample_id, timestamp, MQ2_V, MQ9_V, MQ135_V, temperature_C,
humidity_pct, gas_label, concentration_ppm
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# ------------------------------------------------------------------
# 1. Configuration
# ------------------------------------------------------------------
RANDOM_SEED = 42
N_SAMPLES = 12000
V_C = 5.0                     # supply voltage (V)
R_L = 10_000.0               # load resistor (Ω)
ADC_MAX = 1023               # 10-bit ADC
ADC_REF = 3.3                # ADC reference (V)
DIVIDER_RATIO = 0.5          # 2:1 divider before ADC

# Gas-specific model parameters: (log-log slope a, intercept b)
# Derived from typical sensitivity curves in datasheets.
# Format: {sensor: {gas: (a, b)}}
SENSOR_MODEL = {
    'MQ2': {
        'LPG':      (-0.45, 2.30),   # high sensitivity
        'Methane':  (-0.35, 2.10),
        'Propane':  (-0.50, 2.35),
        'Hydrogen': (-0.40, 2.20),
        'CO':       (-0.25, 1.90),   # low sensitivity
        'Alcohol':  (-0.30, 2.00),
        'Smoke':    (-0.55, 2.40),
        'CleanAir': ( 0.00, 0.00),   # baseline
    },
    'MQ9': {
        'LPG':      (-0.40, 2.20),
        'Methane':  (-0.45, 2.25),
        'Propane':  (-0.35, 2.10),
        'Hydrogen': (-0.30, 2.00),
        'CO':       (-0.50, 2.40),   # high sensitivity
        'Alcohol':  (-0.25, 1.90),
        'Smoke':    (-0.35, 2.05),
        'CleanAir': ( 0.00, 0.00),
    },
    'MQ135': {
        'LPG':      (-0.30, 2.00),
        'Methane':  (-0.25, 1.90),
        'Propane':  (-0.35, 2.05),
        'Hydrogen': (-0.40, 2.15),
        'CO':       (-0.30, 2.00),
        'Alcohol':  (-0.45, 2.30),   # high sensitivity
        'Smoke':    (-0.50, 2.35),   # high sensitivity
        'CleanAir': ( 0.00, 0.00),
    },
}

# Baseline resistance R0 in clean air (Ω) for each sensor
R0 = {
    'MQ2':   5_000.0,
    'MQ9':   8_000.0,
    'MQ135': 20_000.0,
}

# Gas concentration ranges (ppm)
CONC_RANGE = {
    'LPG':      (200, 5000),
    'Methane':  (5000, 20000),
    'Propane':  (200, 5000),
    'Hydrogen': (300, 5000),
    'CO':       (20, 2000),
    'Alcohol':  (100, 2000),
    'Smoke':    (10, 1000),
    'CleanAir': (0, 0),
}

# Sampling probabilities (class imbalance)
GAS_PROBS = {
    'LPG':      0.10,
    'Methane':  0.08,
    'Propane':  0.08,
    'Hydrogen': 0.08,
    'CO':       0.08,
    'Alcohol':  0.08,
    'Smoke':    0.09,
    'CleanAir': 0.41,
}

# Safety thresholds (ppm) – 8-hour TWA unless noted
SAFETY_LIMIT = {
    'LPG':      1000,
    'Methane':  1000,
    'Propane':  1000,
    'Hydrogen': 8000,
    'CO':       50,
    'Alcohol':  1000,
    'Smoke':    50,
    'CleanAir': np.inf,
}

# ------------------------------------------------------------------
# 2. Helper functions
# ------------------------------------------------------------------
def loglog_to_rs_ratio(a, b, conc):
    """Return Rs/R0 from log-log model."""
    if conc <= 0:
        return 1.0
    log_ratio = a * np.log10(conc) + b
    return 10.0 ** log_ratio

def rs_to_voltage(rs, rl=10_000.0, vc=5.0):
    """Voltage across RL in a voltage divider."""
    return vc * rl / (rs + rl)

def adc_quantise(v, ref=3.3, bits=10):
    """Quantise voltage to ADC counts."""
    counts = np.clip(np.round(v / ref * (2**bits - 1)), 0, 2**bits - 1)
    return counts / (2**bits - 1) * ref

# ------------------------------------------------------------------
# 3. Generate samples
# ------------------------------------------------------------------
rng = np.random.default_rng(RANDOM_SEED)

# Base timestamp
start_time = datetime(2024, 1, 1, 0, 0, 0)

# Baseline drift (random walk)
drift_mq2 = 1.0
drift_mq9 = 1.0
drift_mq135 = 1.0

records = []
for i in range(N_SAMPLES):
    # ---- environmental conditions ----
    temp = rng.uniform(10, 40)
    rh = rng.uniform(30, 90)

    # ---- baseline drift update (slow random walk) ----
    drift_mq2 += rng.normal(0, 0.002)
    drift_mq9 += rng.normal(0, 0.002)
    drift_mq135 += rng.normal(0, 0.002)
    drift_mq2 = np.clip(drift_mq2, 0.8, 1.2)
    drift_mq9 = np.clip(drift_mq9, 0.8, 1.2)
    drift_mq135 = np.clip(drift_mq135, 0.8, 1.2)

    # ---- choose gas ----
    gas = rng.choice(list(GAS_PROBS.keys()), p=list(GAS_PROBS.values()))

    if gas == 'CleanAir':
        conc = 0.0
    else:
        lo, hi = CONC_RANGE[gas]
        conc = rng.uniform(lo, hi)

    # ---- ambiguous samples (5% of non-clean-air) ----
    if gas != 'CleanAir' and rng.random() < 0.05:
        # mix with an interfering gas
        interferer = rng.choice([g for g in GAS_PROBS if g != gas and g != 'CleanAir'])
        lo_i, hi_i = CONC_RANGE[interferer]
        conc_i = rng.uniform(lo_i, hi_i)
        # 80% target, 20% interferer
        conc = 0.8 * conc + 0.2 * conc_i

    # ---- compute Rs for each sensor ----
    voltages = {}
    for sensor in ['MQ2', 'MQ9', 'MQ135']:
        # baseline drift
        r0_eff = R0[sensor] * (drift_mq2 if sensor=='MQ2' else
                               drift_mq9 if sensor=='MQ9' else
                               drift_mq135)

        # temperature effect
        r0_eff *= (1 + 0.003 * (20 - temp))

        # humidity effect
        r0_eff *= (1 + 0.002 * (rh - 55))

        # gas response
        a, b = SENSOR_MODEL[sensor][gas]
        ratio = loglog_to_rs_ratio(a, b, conc)
        rs = r0_eff * ratio

        # cross-sensitivity: add a small response from a random interfering gas
        if gas != 'CleanAir' and rng.random() < 0.3:
            interferer = rng.choice([g for g in GAS_PROBS if g != gas and g != 'CleanAir'])
            a_i, b_i = SENSOR_MODEL[sensor][interferer]
            ratio_i = loglog_to_rs_ratio(a_i, b_i, conc * 0.3)
            rs *= ratio_i

        # voltage divider
        v_out = rs_to_voltage(rs, R_L, V_C)
        # 2:1 divider before ADC
        v_adc = v_out * DIVIDER_RATIO
        # ADC quantisation
        v_quant = adc_quantise(v_adc, ADC_REF, 10)
        # add sensor noise (1% of signal)
        v_noisy = v_quant + rng.normal(0, 0.01 * v_quant)
        v_noisy = np.clip(v_noisy, 0, ADC_REF)

        voltages[sensor] = v_noisy

    # ---- safety label ----
    unsafe = conc > SAFETY_LIMIT[gas]

    # ---- timestamp ----
    ts = start_time + timedelta(seconds=i * 10)  # 10 s intervals

    records.append({
        'sample_id': i + 1,
        'timestamp': ts.isoformat(),
        'MQ2_V': round(voltages['MQ2'], 6),
        'MQ9_V': round(voltages['MQ9'], 6),
        'MQ135_V': round(voltages['MQ135'], 6),
        'temperature_C': round(temp, 2),
        'humidity_pct': round(rh, 2),
        'gas_label': gas,
        'concentration_ppm': round(conc, 2),
        'safety_status': 'unsafe' if unsafe else 'safe',
    })

# ------------------------------------------------------------------
# 4. Save CSV
# ------------------------------------------------------------------
df = pd.DataFrame(records)
df.to_csv('mq_synthetic_dataset.csv', index=False)
print(f'Generated {len(df)} samples.')
print(df.head())