"""
constants.py — Centralized constants for Training module.
Single source of truth for circuit specs, sensor model curves, synthetic generator parameters,
model architecture hyperparameters, dataset filenames, and socket client endpoints.
"""

import numpy as np
from typing import Dict, List, Tuple

# ------------------------------------------------------------------
# Circuit & ADC Electrical Parameters
# ------------------------------------------------------------------
RANDOM_SEED: int = 42
N_SAMPLES_DEFAULT: int = 12000
V_C: float = 5.0                     # supply voltage (V)
R_L: float = 10_000.0               # load resistor (Ω)
ADC_MAX: int = 1023               # 10-bit ADC
ADC_REF: float = 3.3                # ADC reference (V)
DIVIDER_RATIO: float = 0.5          # 2:1 divider before ADC

# ------------------------------------------------------------------
# Baseline Resistance R0 in clean air (Ω) for each sensor
# ------------------------------------------------------------------
R0_DEFAULTS: Dict[str, float] = {
    'MQ2':   5_000.0,
    'MQ9':   8_000.0,
    'MQ135': 20_000.0,
}

# ------------------------------------------------------------------
# Gas-Specific Model Parameters: (log-log slope a, intercept b)
# Derived from typical sensitivity curves in datasheets.
# Format: {sensor: {gas: (a, b)}}
# ------------------------------------------------------------------
SENSOR_MODEL: Dict[str, Dict[str, Tuple[float, float]]] = {
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

# ------------------------------------------------------------------
# Gas Concentration Ranges (ppm) & Sampling Probabilities
# ------------------------------------------------------------------
CONC_RANGE: Dict[str, Tuple[float, float]] = {
    'LPG':      (200, 5000),
    'Methane':  (5000, 20000),
    'Propane':  (200, 5000),
    'Hydrogen': (300, 5000),
    'CO':       (20, 2000),
    'Alcohol':  (100, 2000),
    'Smoke':    (10, 1000),
    'CleanAir': (0, 0),
}

GAS_PROBS: Dict[str, float] = {
    'LPG':      0.10,
    'Methane':  0.08,
    'Propane':  0.08,
    'Hydrogen': 0.08,
    'CO':       0.08,
    'Alcohol':  0.08,
    'Smoke':    0.09,
    'CleanAir': 0.41,
}

# Safety Thresholds (ppm) – 8-hour TWA unless noted
SAFETY_LIMIT: Dict[str, float] = {
    'LPG':      1000,
    'Methane':  1000,
    'Propane':  1000,
    'Hydrogen': 8000,
    'CO':       50,
    'Alcohol':  1000,
    'Smoke':    50,
    'CleanAir': float('inf'),
}

# ------------------------------------------------------------------
# Dataset Filenames & Artifact Paths
# ------------------------------------------------------------------
DATASET_FILENAME: str = 'mq_synthetic_dataset.csv'
MODEL_PT_FILENAME: str = 'gasnet.pt'
PREPROCESS_PKL_FILENAME: str = 'preprocess.pkl'
WEIGHTS_NPZ_FILENAME: str = 'gasnet_weights.npz'
METADATA_JSON_FILENAME: str = 'model_metadata.json'

# ------------------------------------------------------------------
# Model Architecture & Training Hyperparameters
# ------------------------------------------------------------------
FEATURES: List[str] = ['MQ2_V', 'MQ9_V', 'MQ135_V', 'temperature_C', 'humidity_pct']
N_FEATURES_DEFAULT: int = 5
N_CLASSES_DEFAULT: int = 8
HIDDEN1_DEFAULT: int = 32
HIDDEN2_DEFAULT: int = 16
DROPOUT_DEFAULT: float = 0.1

TRAIN_SPLIT_RATIO: float = 0.70
VAL_SPLIT_RATIO: float = 0.15

BATCH_SIZE_TRAIN: int = 64
BATCH_SIZE_EVAL: int = 256
EPOCHS_DEFAULT: int = 60
LEARNING_RATE_DEFAULT: float = 1e-3
WEIGHT_DECAY_DEFAULT: float = 1e-4

# ------------------------------------------------------------------
# Service Socket Client
# ------------------------------------------------------------------
SOCK_PATH: str = "/tmp/mq_service.sock"
