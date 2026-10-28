"""
constants.py — Centralized constants for Simulation module.
Single source of truth for scenario profiles, ADC bounds, default intervals, seasonal parameters, and fault modes.
"""

from datetime import datetime, timezone
from typing import Dict, Tuple, Any

# Default Simulation Parameters
DEFAULT_SCENARIO: str = "clean_indoor"
DEFAULT_SIM_NODE_ID: str = "sim_node_01"
DEFAULT_SAMPLING_INTERVAL_SECONDS: int = 60

# ADC Conversion Parameters (10-bit ADC, 5V reference)
ADC_BITS: int = 10
ADC_VREF: float = 5.0
ADC_MAX: int = 1023

# Physical Sensor Bounds
TEMP_MIN: float = -40.0
TEMP_MAX: float = 85.0
HUMIDITY_MIN: float = 0.0
HUMIDITY_MAX: float = 100.0
VOLTAGE_MIN: float = 0.0
VOLTAGE_MAX: float = 5.0
PM_TOLERANCE: float = 0.5

# Simulated Timeline: September through November (Autumn / Transition)
DEFAULT_TIMELINE_START: datetime = datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc)
DEFAULT_TIMELINE_END: datetime = datetime(2026, 11, 30, 23, 59, 59, tzinfo=timezone.utc)

# Seasonal Trend Slopes (Sep 1 -> Nov 30, approx 91 days)
# September (late monsoon): warm (31-33 C), high humidity (78-90%), lower baseline PM (rains wash air).
# October (post-monsoon/autumn): cooling (26-30 C), dropping humidity (60-75%), rising PM.
# November (early winter): cooler nights (18-24 C), lower humidity (45-60%), winter inversion raises PM baseline.
SEASONAL_SEPT_TEMP_BASE: float = 31.5
SEASONAL_NOV_TEMP_BASE: float = 22.0
SEASONAL_SEPT_HUM_BASE: float = 82.0
SEASONAL_NOV_HUM_BASE: float = 52.0
SEASONAL_SEPT_PM25_BASE: float = 20.0
SEASONAL_NOV_PM25_BASE: float = 62.0

# Diurnal Cycle Parameters
DIURNAL_TEMP_AMPLITUDE: float = 4.5       # +/- 4.5 C peak-to-trough (warmest at 14:30, coolest at 05:30)
DIURNAL_HUM_AMPLITUDE: float = 14.0       # +/- 14% relative humidity swing (inversely correlated with lag)
DIURNAL_PEAK_SOLAR_HOUR: float = 14.5     # 2:30 PM local peak solar temperature
DIURNAL_LAG_HOURS: float = 1.0            # Humidity minimum lags temperature peak by 1h

# Scenario Profile Bounds
# Format: (pm25_range, pm10_range, mq2_v_range, mq9_v_range, mq135_v_range, temp_c_range, hum_pct_range)
SCENARIO_PROFILES: Dict[str, Tuple[Tuple[float, float], Tuple[float, float], Tuple[float, float], Tuple[float, float], Tuple[float, float], Tuple[float, float], Tuple[float, float]]] = {
    'clean_indoor':        ((6, 18),   (12, 28),   (0.7, 1.1), (0.6, 0.95), (0.7, 1.1), (22, 26), (42, 58)),
    'clean_background':    ((6, 18),   (12, 28),   (0.7, 1.1), (0.6, 0.95), (0.7, 1.1), (22, 26), (42, 58)),
    'traffic':             ((35, 80),  (60, 120),  (1.3, 2.0), (1.5, 2.5),  (1.3, 2.0), (28, 35), (32, 52)),
    'dust_construction':   ((45, 95),  (150, 380), (0.9, 1.3), (0.8, 1.3),  (0.8, 1.3), (29, 37), (25, 45)),
    'heavy_dust':          ((45, 95),  (150, 380), (0.9, 1.3), (0.8, 1.3),  (0.8, 1.3), (29, 37), (25, 45)),
    'construction':        ((50, 110), (160, 400), (1.1, 1.6), (1.3, 2.2),  (1.1, 1.7), (29, 37), (25, 45)),
    'combustion_smoke':    ((75, 180), (100, 240), (2.2, 3.8), (1.6, 2.8),  (1.8, 3.2), (28, 36), (32, 52)),
    'combustion':          ((75, 180), (100, 240), (2.2, 3.8), (1.6, 2.8),  (1.8, 3.2), (28, 36), (32, 52)),
    'biomass_burning':     ((70, 175), (95, 230),  (2.4, 4.0), (1.5, 2.6),  (1.7, 3.0), (27, 35), (35, 60)),
    'industrial':          ((40, 95),  (65, 150),  (1.2, 2.0), (1.5, 2.7),  (2.2, 3.6), (28, 36), (35, 55)),
    'indoor_activity':     ((15, 35),  (25, 50),   (0.9, 1.3), (0.7, 1.1),  (1.0, 1.5), (23, 27), (45, 65)),
    'high_humidity':       ((10, 25),  (15, 35),   (0.8, 1.2), (0.6, 1.0),  (0.8, 1.2), (24, 30), (85, 98)),
    'pm_spike':            ((220, 500),(320, 700), (1.0, 1.5), (0.8, 1.2),  (0.9, 1.4), (25, 32), (40, 60)),
    'gas_spike':           ((15, 35),  (25, 45),   (3.0, 4.5), (2.5, 4.2),  (3.0, 4.5), (25, 35), (35, 55)),
    'mixed_pollution':     ((60, 140), (110, 240), (1.8, 3.0), (1.6, 2.8),  (1.6, 2.8), (28, 35), (40, 60)),
    'stable':              ((14.0, 14.0), (22.0, 22.0), (1.0, 1.0), (0.8, 0.8), (0.9, 0.9), (25.0, 25.0), (50.0, 50.0)),
    'unknown_ambiguous':   ((30, 55),  (50, 85),   (1.3, 1.7), (1.2, 1.6),  (1.2, 1.6), (26, 31), (45, 65)),
    'sensor_fault':        ((8, 18),   (14, 28),   (0.7, 1.1), (0.6, 0.95), (0.7, 1.1), (22, 26), (42, 58)),
    'random':              ((15, 90),  (30, 160),  (0.9, 2.5), (0.8, 2.5),  (0.9, 2.5), (22, 35), (30, 85)),
}

# Scenario Aliases (mapping alternate names to canonical keys)
SCENARIO_ALIASES: Dict[str, str] = {
    'normal': 'clean_indoor',
    'clean_background': 'clean_indoor',
    'heavy_dust': 'dust_construction',
    'construction': 'dust_construction',
    'combustion': 'combustion_smoke',
    'biomass_burning': 'combustion_smoke',
    'biomass_or_waste_burning': 'combustion_smoke',
    'cooking': 'indoor_activity',
    'cooking_or_fuel_combustion': 'indoor_activity',
    'unknown': 'unknown_ambiguous',
}

# Documented Metadata for Each Scenario:
# Expected physical properties, model targets, and rationale
SCENARIO_METADATA: Dict[str, Dict[str, Any]] = {
    'clean_indoor': {
        'description': 'Low baseline particulates and gases in a well-ventilated indoor space.',
        'expected_source': 'CLEAN_OR_BACKGROUND',
        'expected_gasnet': 'CleanAir',
        'coarse_ratio_target': (1.4, 1.9),
        'fine_ratio_target': (1.6, 2.2),
        'rationale': 'Represents reference baseline without acute pollution sources.'
    },
    'traffic': {
        'description': 'Roadside vehicle exhaust with elevated CO (MQ9), NOx/VOCs (MQ135), and fine exhaust PM.',
        'expected_source': 'TRAFFIC',
        'expected_gasnet': 'CleanAir',
        'coarse_ratio_target': (1.4, 1.8),
        'fine_ratio_target': (1.8, 2.5),
        'rationale': 'Simulates morning/evening commute spikes with fine particle dominance.'
    },
    'dust_construction': {
        'description': 'Resuspended coarse soil and mineral road dust with high PM10/PM2.5 ratio and baseline gases.',
        'expected_source': 'HEAVY_DUST',
        'expected_gasnet': 'CleanAir',
        'coarse_ratio_target': (2.6, 4.2),
        'fine_ratio_target': (2.0, 3.2),
        'rationale': 'Differentiates mechanical dust resuspension from combustion particles.'
    },
    'construction': {
        'description': 'Construction site with heavy coarse dust resuspension and diesel exhaust emissions.',
        'expected_source': 'CONSTRUCTION_ACTIVITY',
        'expected_gasnet': 'CleanAir',
        'coarse_ratio_target': (2.4, 3.8),
        'fine_ratio_target': (1.8, 2.8),
        'rationale': 'Combines coarse mineral dust with diesel equipment gas signatures.'
    },
    'combustion_smoke': {
        'description': 'Open biomass, crop residue, or garbage combustion with dense smoke and high MQ2/MQ9 response.',
        'expected_source': 'BIOMASS_OR_WASTE_BURNING',
        'expected_gasnet': 'Smoke',
        'coarse_ratio_target': (1.2, 1.5),
        'fine_ratio_target': (1.5, 2.2),
        'rationale': 'Simulates seasonal autumn burning episodes with fine aerosols and reducing gases.'
    },
    'industrial': {
        'description': 'Industrial fumes and diesel generator exhaust elevating MQ135 and MQ9.',
        'expected_source': 'INDUSTRIAL_OR_GENERATOR_EMISSIONS',
        'expected_gasnet': 'CleanAir',
        'coarse_ratio_target': (1.4, 1.9),
        'fine_ratio_target': (1.6, 2.4),
        'rationale': 'Tests detection of solvent/chemical air contaminants with moderate PM.'
    },
    'indoor_activity': {
        'description': 'Occupied indoor environment with cooking or domestic activity, modest PM, and baseline gases.',
        'expected_source': 'INDOOR_ACTIVITY',
        'expected_gasnet': 'CleanAir',
        'coarse_ratio_target': (1.3, 1.7),
        'fine_ratio_target': (1.5, 2.2),
        'rationale': 'Simulates domestic cooking or localized indoor activities.'
    },
    'high_humidity': {
        'description': 'High relative humidity post-monsoon or coastal fog with normal background pollution.',
        'expected_source': 'CLEAN_OR_BACKGROUND',
        'expected_gasnet': 'CleanAir',
        'coarse_ratio_target': (1.3, 1.7),
        'fine_ratio_target': (1.6, 2.2),
        'rationale': 'Tests sensor baseline robustness under 85-98% relative humidity.'
    },
    'pm_spike': {
        'description': 'Transient acute particulate spike without corresponding gas sensor elevation.',
        'expected_source': 'HEAVY_DUST',
        'expected_gasnet': 'CleanAir',
        'coarse_ratio_target': (1.3, 2.0),
        'fine_ratio_target': (1.8, 2.8),
        'rationale': 'Tests anomaly detector and forecast resilience against sudden particulate surges.'
    },
    'gas_spike': {
        'description': 'Transient acute gas release elevating MQ sensors without particulate elevation.',
        'expected_source': 'UNKNOWN',
        'expected_gasnet': 'Alcohol',
        'coarse_ratio_target': (1.3, 1.7),
        'fine_ratio_target': (1.6, 2.2),
        'rationale': 'Tests gas hazard detection and MC-Dropout uncertainty on chemical events.'
    },
    'mixed_pollution': {
        'description': 'Overlapping traffic, ambient dust, and distant combustion creating complex mixed signatures.',
        'expected_source': 'MIXED_POLLUTION',
        'expected_gasnet': 'CleanAir',
        'coarse_ratio_target': (1.6, 2.2),
        'fine_ratio_target': (1.6, 2.4),
        'rationale': 'Validates the source classifier multi-category overlap detection.'
    },
    'stable': {
        'description': 'Static baseline with minimal noise for calibration and sensor health checks.',
        'expected_source': 'CLEAN_OR_BACKGROUND',
        'expected_gasnet': 'CleanAir',
        'coarse_ratio_target': (1.5, 1.6),
        'fine_ratio_target': (1.8, 1.9),
        'rationale': 'Deterministic constant reference values for baseline checks.'
    },
    'unknown_ambiguous': {
        'description': 'Borderline values designed to fall between category clusters and test model uncertainty.',
        'expected_source': 'UNKNOWN',
        'expected_gasnet': 'CleanAir',
        'coarse_ratio_target': (1.5, 1.8),
        'fine_ratio_target': (1.6, 2.2),
        'rationale': 'Tests classifier uncertainty logic, score gaps, and confidence floors.'
    },
    'sensor_fault': {
        'description': 'Hardware or communication failure injection (rail saturation, frozen readings, drift).',
        'expected_source': 'UNKNOWN',
        'expected_gasnet': 'CleanAir',
        'coarse_ratio_target': (1.4, 1.8),
        'fine_ratio_target': (1.6, 2.2),
        'rationale': 'Verifies sensor health checks and anomaly engine hardware fault discrimination.'
    },
}

# Configurable Fault Injection Types
VALID_FAULT_TYPES = {
    'none',
    'rail_gnd',       # Pin grounded: 0.0V / ADC 0
    'rail_vcc',       # Pin railed to VCC: 5.0V / ADC 1023
    'stuck',          # Frozen bit-identical reading over time
    'drift',          # Gradual linear sensor calibration drift
    'warmup',         # Pre-heating stabilization decay (first 30-60s)
    'transient_spike',# Single reading high outlier
    'missing',        # Omitted field from payload
}

