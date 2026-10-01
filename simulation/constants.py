"""
constants.py — Centralized constants for Simulation module.
Single source of truth for scenario profiles, ADC bounds, default intervals, and noise factors.
"""

from typing import Dict, Tuple

# Default Simulation Parameters
DEFAULT_SCENARIO: str = "clean_indoor"
DEFAULT_SIM_NODE_ID: str = "sim_node_01"
DEFAULT_SAMPLING_INTERVAL_SECONDS: int = 60

# ADC Conversion Parameters (10-bit ADC, 5V reference)
ADC_BITS: int = 10
ADC_VREF: float = 5.0
ADC_MAX: int = 1023

# Scenario Profile Bounds
# Format: (pm25_range, pm10_range, mq2_v_range, mq9_v_range, mq135_v_range, temp_c_range, hum_pct_range)
SCENARIO_PROFILES: Dict[str, Tuple[Tuple[float, float], Tuple[float, float], Tuple[float, float], Tuple[float, float], Tuple[float, float], Tuple[float, float], Tuple[float, float]]] = {
    'clean_indoor':        ((5, 15),   (10, 25),   (0.8, 1.2), (0.6, 1.0), (0.7, 1.1), (22, 26), (40, 55)),
    'traffic':             ((35, 80),  (60, 120),  (1.3, 2.0), (1.5, 2.5), (1.2, 1.8), (28, 35), (30, 50)),
    'dust_construction':   ((50, 120), (150, 400), (0.9, 1.3), (0.7, 1.1), (0.8, 1.2), (30, 38), (25, 40)),
    'combustion_smoke':    ((80, 200), (100, 250), (2.5, 4.0), (2.0, 3.5), (2.0, 3.5), (32, 40), (30, 50)),
    'high_humidity':       ((10, 25),  (15, 35),   (0.9, 1.3), (0.7, 1.1), (0.8, 1.2), (24, 30), (85, 98)),
    'pm_spike':            ((200, 500),(300, 700), (1.0, 1.5), (0.8, 1.2), (0.9, 1.3), (25, 32), (40, 60)),
    'gas_spike':           ((10, 30),  (15, 40),   (3.0, 4.5), (2.5, 4.0), (3.0, 4.5), (25, 35), (35, 55)),
    'mixed_pollution':     ((60, 150), (100, 250), (1.8, 3.0), (1.5, 2.8), (1.5, 2.8), (28, 35), (40, 60)),
    'stable':              ((12, 12),  (20, 20),   (1.0, 1.0), (0.8, 0.8), (0.9, 0.9), (25, 25), (50, 50)),
    'sensor_fault':        ((5, 15),   (10, 25),   (0.8, 1.2), (0.6, 1.0), (0.7, 1.1), (22, 26), (40, 55)),
}
