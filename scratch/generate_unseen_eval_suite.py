"""
Generate genuinely unseen, out-of-distribution, boundary, and perturbation
evaluation datasets for rigorous model validation.
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

# Seed for reproducible test set generation
SEED = 999
rng = random.Random(SEED)


def generate_unseen_evaluation_suites(output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------
    # Suite 1: Unseen Environmental Combinations
    # Combinations never present in the original 4-session training dataset
    # (where T=30C, H=87%)
    # -------------------------------------------------------------
    unseen_combinations = [
        # 1. Hot & Dry Afternoon Traffic
        {
            "id": "unseen_hot_dry_traffic",
            "description": "High temperature, low humidity with traffic emissions",
            "scenario": "TRAFFIC",
            "expected_source": "TRAFFIC",
            "expected_gas": "Smoke",
            "payload": {
                "node_id": "eval-unseen-01",
                "timestamp": "2024-09-15T14:30:00Z",
                "environment": {"temperature_C": 38.5, "humidity_pct": 28.0},
                "particulate_matter": {"PM1_0": 28.0, "PM2_5": 72.0, "PM10": 115.0},
                "gas_sensors": {
                    "MQ2": {"raw_adc": 360, "voltage_V": 1.76},
                    "MQ9": {"raw_adc": 420, "voltage_V": 2.05},
                    "MQ135": {"raw_adc": 380, "voltage_V": 1.86},
                },
            },
        },
        # 2. Cool & Humid Morning Background
        {
            "id": "unseen_cool_humid_background",
            "description": "Cool morning with high humidity and clean air",
            "scenario": "CLEAN_OR_BACKGROUND",
            "expected_source": "CLEAN_OR_BACKGROUND",
            "expected_gas": "CleanAir",
            "payload": {
                "node_id": "eval-unseen-01",
                "timestamp": "2024-09-16T05:45:00Z",
                "environment": {"temperature_C": 18.2, "humidity_pct": 92.0},
                "particulate_matter": {"PM1_0": 5.0, "PM2_5": 11.0, "PM10": 18.0},
                "gas_sensors": {
                    "MQ2": {"raw_adc": 130, "voltage_V": 0.64},
                    "MQ9": {"raw_adc": 120, "voltage_V": 0.59},
                    "MQ135": {"raw_adc": 145, "voltage_V": 0.71},
                },
            },
        },
        # 3. Construction Dust with variable fine-particle fractions
        {
            "id": "unseen_construction_dust_variable_fine",
            "description": "Construction dust with low fine PM and huge coarse PM",
            "scenario": "CONSTRUCTION_ACTIVITY",
            "expected_source": "CONSTRUCTION_ACTIVITY",
            "expected_gas": "CleanAir",
            "payload": {
                "node_id": "eval-unseen-01",
                "timestamp": "2024-09-17T11:00:00Z",
                "environment": {"temperature_C": 32.0, "humidity_pct": 45.0},
                "particulate_matter": {"PM1_0": 8.0, "PM2_5": 22.0, "PM10": 240.0},
                "gas_sensors": {
                    "MQ2": {"raw_adc": 145, "voltage_V": 0.71},
                    "MQ9": {"raw_adc": 135, "voltage_V": 0.66},
                    "MQ135": {"raw_adc": 155, "voltage_V": 0.76},
                },
            },
        },
        # 4. Biomass Burning during night inversion
        {
            "id": "unseen_biomass_night_inversion",
            "description": "Heavy smoke and combustion at night with cooler temp",
            "scenario": "BIOMASS_OR_WASTE_BURNING",
            "expected_source": "BIOMASS_OR_WASTE_BURNING",
            "expected_gas": "Smoke",
            "payload": {
                "node_id": "eval-unseen-01",
                "timestamp": "2024-09-18T22:15:00Z",
                "environment": {"temperature_C": 22.5, "humidity_pct": 78.0},
                "particulate_matter": {"PM1_0": 85.0, "PM2_5": 165.0, "PM10": 210.0},
                "gas_sensors": {
                    "MQ2": {"raw_adc": 580, "voltage_V": 2.84},
                    "MQ9": {"raw_adc": 410, "voltage_V": 2.00},
                    "MQ135": {"raw_adc": 490, "voltage_V": 2.40},
                },
            },
        },
        # 5. Heavy Coarse Dust Storm
        {
            "id": "unseen_heavy_dust_storm",
            "description": "Severe wind-blown dust with elevated temperature",
            "scenario": "HEAVY_DUST",
            "expected_source": "HEAVY_DUST",
            "expected_gas": "CleanAir",
            "payload": {
                "node_id": "eval-unseen-01",
                "timestamp": "2024-09-19T15:00:00Z",
                "environment": {"temperature_C": 35.0, "humidity_pct": 30.0},
                "particulate_matter": {"PM1_0": 18.0, "PM2_5": 55.0, "PM10": 460.0},
                "gas_sensors": {
                    "MQ2": {"raw_adc": 150, "voltage_V": 0.73},
                    "MQ9": {"raw_adc": 140, "voltage_V": 0.68},
                    "MQ135": {"raw_adc": 160, "voltage_V": 0.78},
                },
            },
        },
        # 6. Alcohol/Solvent Spill in Laboratory/Indoor environment
        {
            "id": "unseen_alcohol_solvent_indoor",
            "description": "Solvent/alcohol vapor spike with normal PM",
            "scenario": "INDOOR_ACTIVITY",
            "expected_source": "INDOOR_ACTIVITY",
            "expected_gas": "Alcohol",
            "payload": {
                "node_id": "eval-unseen-01",
                "timestamp": "2024-09-20T10:30:00Z",
                "environment": {"temperature_C": 24.0, "humidity_pct": 52.0},
                "particulate_matter": {"PM1_0": 4.0, "PM2_5": 9.0, "PM10": 14.0},
                "gas_sensors": {
                    "MQ2": {"raw_adc": 180, "voltage_V": 0.88},
                    "MQ9": {"raw_adc": 170, "voltage_V": 0.83},
                    "MQ135": {"raw_adc": 640, "voltage_V": 3.13},
                },
            },
        },
        # 7. Industrial / Generator Exhaust (High MQ9 and CO)
        {
            "id": "unseen_industrial_generator_exhaust",
            "description": "Diesel generator emissions with high CO response and PM",
            "scenario": "INDUSTRIAL_OR_GENERATOR_EMISSIONS",
            "expected_source": "INDUSTRIAL_OR_GENERATOR_EMISSIONS",
            "expected_gas": "CO",
            "payload": {
                "node_id": "eval-unseen-01",
                "timestamp": "2024-09-21T16:45:00Z",
                "environment": {"temperature_C": 33.0, "humidity_pct": 48.0},
                "particulate_matter": {"PM1_0": 45.0, "PM2_5": 95.0, "PM10": 135.0},
                "gas_sensors": {
                    "MQ2": {"raw_adc": 340, "voltage_V": 1.66},
                    "MQ9": {"raw_adc": 590, "voltage_V": 2.89},
                    "MQ135": {"raw_adc": 390, "voltage_V": 1.91},
                },
            },
        },
        # 8. Mixed Pollution (Traffic + Biomass Smoke)
        {
            "id": "unseen_mixed_traffic_biomass",
            "description": "Simultaneous traffic congestion and evening biomass burning",
            "scenario": "MIXED_POLLUTION",
            "expected_source": "MIXED_POLLUTION",
            "expected_gas": "Smoke",
            "payload": {
                "node_id": "eval-unseen-01",
                "timestamp": "2024-09-22T19:00:00Z",
                "environment": {"temperature_C": 26.5, "humidity_pct": 68.0},
                "particulate_matter": {"PM1_0": 60.0, "PM2_5": 125.0, "PM10": 170.0},
                "gas_sensors": {
                    "MQ2": {"raw_adc": 480, "voltage_V": 2.35},
                    "MQ9": {"raw_adc": 440, "voltage_V": 2.15},
                    "MQ135": {"raw_adc": 460, "voltage_V": 2.25},
                },
            },
        },
    ]

    with open(output_dir / "eval_unseen_combinations.json", "w") as f:
        json.dump(unseen_combinations, f, indent=2)

    # -------------------------------------------------------------
    # Suite 2: Boundary and Out-of-Distribution Tests
    # Tests safety, uncertainty abstention, and edge-case behavior
    # -------------------------------------------------------------
    boundary_ood_cases = [
        # 1. Rail to GND (Sensor hardware failure)
        {
            "id": "boundary_rail_gnd",
            "type": "hardware_fault",
            "expected_anomaly": True,
            "expected_uncertainty": True,
            "payload": {
                "node_id": "eval-boundary-01",
                "timestamp": "2024-09-23T12:00:00Z",
                "environment": {"temperature_C": 25.0, "humidity_pct": 50.0},
                "particulate_matter": {"PM1_0": 10.0, "PM2_5": 20.0, "PM10": 30.0},
                "gas_sensors": {
                    "MQ2": {"raw_adc": 0, "voltage_V": 0.00},
                    "MQ9": {"raw_adc": 180, "voltage_V": 0.88},
                    "MQ135": {"raw_adc": 180, "voltage_V": 0.88},
                },
            },
        },
        # 2. Rail to VCC (Short circuit / saturation)
        {
            "id": "boundary_rail_vcc",
            "type": "hardware_fault",
            "expected_anomaly": True,
            "expected_uncertainty": True,
            "payload": {
                "node_id": "eval-boundary-01",
                "timestamp": "2024-09-23T12:05:00Z",
                "environment": {"temperature_C": 25.0, "humidity_pct": 50.0},
                "particulate_matter": {"PM1_0": 10.0, "PM2_5": 20.0, "PM10": 30.0},
                "gas_sensors": {
                    "MQ2": {"raw_adc": 1023, "voltage_V": 5.00},
                    "MQ9": {"raw_adc": 1023, "voltage_V": 5.00},
                    "MQ135": {"raw_adc": 1023, "voltage_V": 5.00},
                },
            },
        },
        # 3. Extreme Plausible Temperature Boundary (Heatwave 44.5C)
        {
            "id": "boundary_extreme_heatwave",
            "type": "environmental_boundary",
            "expected_anomaly": False,
            "expected_gas": "CleanAir",
            "payload": {
                "node_id": "eval-boundary-01",
                "timestamp": "2024-09-23T13:30:00Z",
                "environment": {"temperature_C": 44.5, "humidity_pct": 22.0},
                "particulate_matter": {"PM1_0": 12.0, "PM2_5": 28.0, "PM10": 45.0},
                "gas_sensors": {
                    "MQ2": {"raw_adc": 150, "voltage_V": 0.73},
                    "MQ9": {"raw_adc": 140, "voltage_V": 0.68},
                    "MQ135": {"raw_adc": 160, "voltage_V": 0.78},
                },
            },
        },
        # 4. Extreme High Humidity Boundary (98% fog/monsoon)
        {
            "id": "boundary_extreme_humidity_monsoon",
            "type": "environmental_boundary",
            "expected_anomaly": False,
            "expected_gas": "CleanAir",
            "payload": {
                "node_id": "eval-boundary-01",
                "timestamp": "2024-09-23T06:00:00Z",
                "environment": {"temperature_C": 21.0, "humidity_pct": 98.0},
                "particulate_matter": {"PM1_0": 7.0, "PM2_5": 16.0, "PM10": 25.0},
                "gas_sensors": {
                    "MQ2": {"raw_adc": 140, "voltage_V": 0.68},
                    "MQ9": {"raw_adc": 130, "voltage_V": 0.64},
                    "MQ135": {"raw_adc": 150, "voltage_V": 0.73},
                },
            },
        },
        # 5. Out of distribution / Ambiguous pattern
        {
            "id": "ood_ambiguous_signal",
            "type": "ood_uncertainty",
            "expected_uncertainty": True,
            "payload": {
                "node_id": "eval-boundary-01",
                "timestamp": "2024-09-23T15:00:00Z",
                "environment": {"temperature_C": 27.0, "humidity_pct": 55.0},
                "particulate_matter": {"PM1_0": 1.0, "PM2_5": 2.0, "PM10": 3.0},
                "gas_sensors": {
                    "MQ2": {"raw_adc": 700, "voltage_V": 3.42},
                    "MQ9": {"raw_adc": 120, "voltage_V": 0.59},
                    "MQ135": {"raw_adc": 140, "voltage_V": 0.68},
                },
            },
        },
    ]

    with open(output_dir / "eval_boundary_ood.json", "w") as f:
        json.dump(boundary_ood_cases, f, indent=2)

    # -------------------------------------------------------------
    # Suite 3: Controlled Perturbation Robustness Tests
    # Measures prediction stability under noise and offsets
    # -------------------------------------------------------------
    perturbation_cases = []
    base_cases = [
        {"name": "clean_room", "mq2": 0.70, "mq9": 0.65, "mq135": 0.75, "t": 24.0, "h": 50.0, "pm25": 12.0, "pm10": 20.0, "src": "CLEAN_OR_BACKGROUND", "gas": "CleanAir"},
        {"name": "traffic_rush", "mq2": 1.65, "mq9": 1.95, "mq135": 1.75, "t": 30.0, "h": 55.0, "pm25": 65.0, "pm10": 110.0, "src": "TRAFFIC", "gas": "Smoke"},
        {"name": "smoke_plume", "mq2": 2.80, "mq9": 1.90, "mq135": 2.40, "t": 28.0, "h": 60.0, "pm25": 150.0, "pm10": 190.0, "src": "BIOMASS_OR_WASTE_BURNING", "gas": "Smoke"},
    ]

    for b in base_cases:
        for p_idx in range(5):
            # Apply slight Gaussian noise (+-3% to voltages, +-1C to temp, +-3% to hum)
            noise_t = rng.gauss(0.0, 1.0)
            noise_h = rng.gauss(0.0, 3.0)
            noise_v2 = rng.gauss(0.0, 0.04)
            noise_v9 = rng.gauss(0.0, 0.04)
            noise_v135 = rng.gauss(0.0, 0.04)

            perturbation_cases.append({
                "base_name": b["name"],
                "perturbation_idx": p_idx,
                "expected_source": b["src"],
                "expected_gas": b["gas"],
                "payload": {
                    "node_id": "eval-perturb-01",
                    "timestamp": f"2024-09-24T10:{p_idx*5:02d}:00Z",
                    "environment": {
                        "temperature_C": round(b["t"] + noise_t, 2),
                        "humidity_pct": round(min(100.0, max(0.0, b["h"] + noise_h)), 2),
                    },
                    "particulate_matter": {
                        "PM1_0": round(b["pm25"] * 0.4, 2),
                        "PM2_5": round(b["pm25"], 2),
                        "PM10": round(b["pm10"], 2),
                    },
                    "gas_sensors": {
                        "MQ2": {"raw_adc": int((b["mq2"] + noise_v2)/5.0*1023), "voltage_V": round(b["mq2"] + noise_v2, 3)},
                        "MQ9": {"raw_adc": int((b["mq9"] + noise_v9)/5.0*1023), "voltage_V": round(b["mq9"] + noise_v9, 3)},
                        "MQ135": {"raw_adc": int((b["mq135"] + noise_v135)/5.0*1023), "voltage_V": round(b["mq135"] + noise_v135, 3)},
                    },
                },
            })

    with open(output_dir / "eval_perturbations.json", "w") as f:
        json.dump(perturbation_cases, f, indent=2)

    print(f"Generated unseen evaluation test suites in {output_dir}:")
    print(f"  1. eval_unseen_combinations.json ({len(unseen_combinations)} cases)")
    print(f"  2. eval_boundary_ood.json ({len(boundary_ood_cases)} cases)")
    print(f"  3. eval_perturbations.json ({len(perturbation_cases)} cases)")


if __name__ == "__main__":
    generate_unseen_evaluation_suites(Path("test_data/unseen_eval"))
