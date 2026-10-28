"""
NavosEdge New Independent Challenge Suite Generator & Evaluator.

Constructs and evaluates:
1. Dhenkanal Station Reserve (864 hourly steps of independent real atmospheric data).
2. Held-out scenario parameters with shifted centroids (seed 999).
3. Physical cross-sensitivity stress tests (overlapping MQ response curves).
4. Boundary, out-of-distribution, ambiguity, and safe-failure abstention tests.

Evaluates both:
- Original Baseline Artifacts (backups/original_baseline/)
- Current Retrained Artifacts (artifacts/)
"""

import asyncio
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score

# Paths
root_dir = Path(__file__).resolve().parents[1]
server_dir = root_dir / "Intelligence" / "Server"

if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))
if str(server_dir) not in sys.path:
    sys.path.insert(0, str(server_dir))

from app.forecast.model import _ar_predict, _fit_ar
from app.schemas.sensor import SensorPayload
from app.services.numpy_inference import NumpyGasNetAdapter
from app.source_classifier.classifier import SourceClassifier
from Simulator.session import load_dataset


def generate_new_challenge_cases() -> Dict[str, Any]:
    """Build novel challenge test cases with shifted parameter distributions."""
    rng = np.random.default_rng(999)  # Completely separate seed

    # -------------------------------------------------------------
    # 1. Shifted GasNet Parameter Challenge Cases (N=10)
    # Centroids shifted by 15-25% from training, with realistic cross-sensitivity
    # -------------------------------------------------------------
    gas_challenge_cases = [
        # Case 1: Cool, humid Clean Air with baseline MQ drift (16C, 88%H)
        {"id": "ch_gas_01_clean_cool_humid", "exp_gas": "CleanAir", "mq2": 0.65, "mq9": 0.58, "mq135": 0.62, "t": 16.5, "h": 88.0, "desc": "Cool humid baseline with low gas voltages"},
        # Case 2: Hot, dry Clean Air (41C, 24%H)
        {"id": "ch_gas_02_clean_hot_dry", "exp_gas": "CleanAir", "mq2": 0.88, "mq9": 0.72, "mq135": 0.78, "t": 41.2, "h": 24.5, "desc": "Hot dry baseline near thermal ceiling"},
        # Case 3: Dilute Smoke with elevated VOCs (wood burning transport)
        {"id": "ch_gas_03_dilute_woodsmoke", "exp_gas": "Smoke", "mq2": 2.15, "mq9": 1.45, "mq135": 2.10, "t": 27.5, "h": 62.0, "desc": "Dilute smoke from biomass with high VOC fraction"},
        # Case 4: Heavy Smoke spike (dense burning)
        {"id": "ch_gas_04_dense_smoke", "exp_gas": "Smoke", "mq2": 3.75, "mq9": 2.30, "mq135": 2.95, "t": 32.0, "h": 48.0, "desc": "Dense close-proximity smoke plume"},
        # Case 5: Solvent evaporation (pure alcohol vapor with minimal combustion gases)
        {"id": "ch_gas_05_pure_alcohol_solvent", "exp_gas": "Alcohol", "mq2": 0.82, "mq9": 0.68, "mq135": 3.15, "t": 24.0, "h": 52.0, "desc": "Hand sanitizer or solvent evaporation indoors"},
        # Case 6: Moderate Alcohol in humid kitchen (26C, 75%H)
        {"id": "ch_gas_06_moderate_alcohol_humid", "exp_gas": "Alcohol", "mq2": 0.92, "mq9": 0.75, "mq135": 2.20, "t": 26.0, "h": 75.0, "desc": "Cooking alcohol vapor in humid environment"},
        # Case 7: Generator CO exhaust (cold start, high CO, moderate MQ2)
        {"id": "ch_gas_07_generator_co", "exp_gas": "CO", "mq2": 1.25, "mq9": 2.95, "mq135": 1.40, "t": 35.0, "h": 42.0, "desc": "Diesel generator cold-start with rich CO emissions"},
        # Case 8: Vehicle idling CO in basement parking
        {"id": "ch_gas_08_parking_idling_co", "exp_gas": "CO", "mq2": 1.05, "mq9": 2.25, "mq135": 1.25, "t": 29.0, "h": 60.0, "desc": "Enclosed vehicle idling with high carbon monoxide"},
        # Case 9: LPG cylinder valve leak (rich combustible, negligible VOC)
        {"id": "ch_gas_09_lpg_cylinder_leak", "exp_gas": "LPG", "mq2": 2.85, "mq9": 2.45, "mq135": 1.05, "t": 28.0, "h": 55.0, "desc": "Kitchen LPG cylinder leak with high combustible response"},
        # Case 10: Dilute LPG odorant trace
        {"id": "ch_gas_10_dilute_lpg", "exp_gas": "LPG", "mq2": 1.95, "mq9": 1.80, "mq135": 0.95, "t": 25.0, "h": 50.0, "desc": "Early-stage gas leak near alarm threshold"},
    ]

    # -------------------------------------------------------------
    # 2. Shifted SourceClassifier Challenge Cases (N=10)
    # Centroids shifted with novel multi-feature ratios
    # -------------------------------------------------------------
    sc_challenge_cases = [
        # Case 1: Rural Background in morning mist (19C, 92%H, low PM)
        {
            "id": "ch_sc_01_rural_mist_background",
            "exp_src": "CLEAN_OR_BACKGROUND",
            "desc": "Pristine rural atmosphere in morning mist",
            "payload": {
                "node_id": "ch-node", "timestamp": "2024-09-15T06:00:00Z",
                "environment": {"temperature_C": 19.2, "humidity_pct": 92.0},
                "particulate_matter": {"PM1_0": 5.2, "PM2_5": 11.5, "PM10": 18.0},
                "gas_sensors": {"MQ2": {"voltage_V": 0.65, "raw_adc": 133}, "MQ9": {"voltage_V": 0.58, "raw_adc": 118}, "MQ135": {"voltage_V": 0.62, "raw_adc": 127}},
            }
        },
        # Case 2: Dense Highway Traffic in dry afternoon (37C, 30%H)
        {
            "id": "ch_sc_02_arterial_traffic_afternoon",
            "exp_src": "TRAFFIC",
            "desc": "Heavy urban corridor with high fine PM and CO",
            "payload": {
                "node_id": "ch-node", "timestamp": "2024-09-15T16:00:00Z",
                "environment": {"temperature_C": 36.8, "humidity_pct": 32.0},
                "particulate_matter": {"PM1_0": 26.0, "PM2_5": 62.0, "PM10": 88.0},
                "gas_sensors": {"MQ2": {"voltage_V": 1.45, "raw_adc": 296}, "MQ9": {"voltage_V": 1.95, "raw_adc": 399}, "MQ135": {"voltage_V": 1.70, "raw_adc": 348}},
            }
        },
        # Case 3: Excavation / Quarry Dust (coarse dominant, ratio > 5.0)
        {
            "id": "ch_sc_03_quarry_excavation_dust",
            "exp_src": "HEAVY_DUST",
            "desc": "Mechanical crustal dust from surface excavation",
            "payload": {
                "node_id": "ch-node", "timestamp": "2024-09-15T11:00:00Z",
                "environment": {"temperature_C": 35.5, "humidity_pct": 36.0},
                "particulate_matter": {"PM1_0": 14.0, "PM2_5": 42.0, "PM10": 265.0},
                "gas_sensors": {"MQ2": {"voltage_V": 0.88, "raw_adc": 180}, "MQ9": {"voltage_V": 0.72, "raw_adc": 147}, "MQ135": {"voltage_V": 0.82, "raw_adc": 168}},
            }
        },
        # Case 4: Commercial building construction site (concrete dust + diesel machinery)
        {
            "id": "ch_sc_04_commercial_construction",
            "exp_src": "CONSTRUCTION_ACTIVITY",
            "desc": "Construction site with mixed heavy earthmoving and concrete work",
            "payload": {
                "node_id": "ch-node", "timestamp": "2024-09-15T13:00:00Z",
                "environment": {"temperature_C": 33.5, "humidity_pct": 45.0},
                "particulate_matter": {"PM1_0": 21.0, "PM2_5": 68.0, "PM10": 210.0},
                "gas_sensors": {"MQ2": {"voltage_V": 1.15, "raw_adc": 235}, "MQ9": {"voltage_V": 1.35, "raw_adc": 276}, "MQ135": {"voltage_V": 1.25, "raw_adc": 256}},
            }
        },
        # Case 5: Nighttime agricultural stubble burning plume
        {
            "id": "ch_sc_05_stubble_burning_plume",
            "exp_src": "BIOMASS_OR_WASTE_BURNING",
            "desc": "Distant agricultural residue smoke with high fine particle load",
            "payload": {
                "node_id": "ch-node", "timestamp": "2024-09-15T21:00:00Z",
                "environment": {"temperature_C": 28.0, "humidity_pct": 68.0},
                "particulate_matter": {"PM1_0": 72.0, "PM2_5": 145.0, "PM10": 175.0},
                "gas_sensors": {"MQ2": {"voltage_V": 2.95, "raw_adc": 603}, "MQ9": {"voltage_V": 1.95, "raw_adc": 399}, "MQ135": {"voltage_V": 2.65, "raw_adc": 542}},
            }
        },
        # Case 6: Industrial generator running backup power (high NOx/CO)
        {
            "id": "ch_sc_06_industrial_backup_generator",
            "exp_src": "INDUSTRIAL_OR_GENERATOR_EMISSIONS",
            "desc": "Stationary diesel generator cluster during grid failure",
            "payload": {
                "node_id": "ch-node", "timestamp": "2024-09-15T15:00:00Z",
                "environment": {"temperature_C": 34.0, "humidity_pct": 46.0},
                "particulate_matter": {"PM1_0": 28.0, "PM2_5": 58.0, "PM10": 88.0},
                "gas_sensors": {"MQ2": {"voltage_V": 1.75, "raw_adc": 358}, "MQ9": {"voltage_V": 2.65, "raw_adc": 542}, "MQ135": {"voltage_V": 2.45, "raw_adc": 501}},
            }
        },
        # Case 7: Domestic LPG cooking / kitchen fumes
        {
            "id": "ch_sc_07_kitchen_cooking_fumes",
            "exp_src": "COOKING_OR_FUEL_COMBUSTION",
            "desc": "Kitchen cooking exhaust with moderate fine PM and smoke",
            "payload": {
                "node_id": "ch-node", "timestamp": "2024-09-15T19:30:00Z",
                "environment": {"temperature_C": 29.5, "humidity_pct": 58.0},
                "particulate_matter": {"PM1_0": 38.0, "PM2_5": 78.0, "PM10": 95.0},
                "gas_sensors": {"MQ2": {"voltage_V": 2.25, "raw_adc": 460}, "MQ9": {"voltage_V": 1.48, "raw_adc": 303}, "MQ135": {"voltage_V": 1.75, "raw_adc": 358}},
            }
        },
        # Case 8: Quiet indoor office space (AC on, 24C, 50%H, low particulate)
        {
            "id": "ch_sc_08_indoor_office_ac",
            "exp_src": "INDOOR_ACTIVITY",
            "desc": "Conditioned indoor commercial environment",
            "payload": {
                "node_id": "ch-node", "timestamp": "2024-09-15T14:00:00Z",
                "environment": {"temperature_C": 23.8, "humidity_pct": 52.0},
                "particulate_matter": {"PM1_0": 9.5, "PM2_5": 22.0, "PM10": 32.0},
                "gas_sensors": {"MQ2": {"voltage_V": 0.95, "raw_adc": 194}, "MQ9": {"voltage_V": 0.82, "raw_adc": 168}, "MQ135": {"voltage_V": 1.10, "raw_adc": 225}},
            }
        },
        # Case 9: Street food market evening (deep frying + coal brazier)
        {
            "id": "ch_sc_09_street_market_evening",
            "exp_src": "COOKING_OR_FUEL_COMBUSTION",
            "desc": "High concentration of food combustion aerosols",
            "payload": {
                "node_id": "ch-node", "timestamp": "2024-09-15T20:00:00Z",
                "environment": {"temperature_C": 28.5, "humidity_pct": 62.0},
                "particulate_matter": {"PM1_0": 45.0, "PM2_5": 85.0, "PM10": 115.0},
                "gas_sensors": {"MQ2": {"voltage_V": 2.40, "raw_adc": 491}, "MQ9": {"voltage_V": 1.65, "raw_adc": 338}, "MQ135": {"voltage_V": 1.95, "raw_adc": 399}},
            }
        },
        # Case 10: Brick kiln plume transport across suburban boundary
        {
            "id": "ch_sc_10_brick_kiln_transport",
            "exp_src": "BIOMASS_OR_WASTE_BURNING",
            "desc": "Heavy coal/biomass combustion plume with dense aerosols",
            "payload": {
                "node_id": "ch-node", "timestamp": "2024-09-15T18:00:00Z",
                "environment": {"temperature_C": 31.0, "humidity_pct": 48.0},
                "particulate_matter": {"PM1_0": 58.0, "PM2_5": 125.0, "PM10": 160.0},
                "gas_sensors": {"MQ2": {"voltage_V": 2.70, "raw_adc": 552}, "MQ9": {"voltage_V": 2.10, "raw_adc": 430}, "MQ135": {"voltage_V": 2.40, "raw_adc": 491}},
            }
        },
    ]

    # -------------------------------------------------------------
    # 3. Ambiguity & Safe-Failure / Abstention Test Cases (N=6)
    # Inputs that MUST flag uncertainty, degraded quality, or UNKNOWN
    # -------------------------------------------------------------
    abstention_cases = [
        # Case 1: Electrical Rail to GND on MQ2 (0.005V)
        {
            "id": "ch_abs_01_mq2_rail_gnd",
            "desc": "MQ2 sensor pin disconnected or shorted to GND",
            "payload": {
                "node_id": "abs-node", "timestamp": "2024-09-15T12:00:00Z",
                "environment": {"temperature_C": 28.0, "humidity_pct": 55.0},
                "particulate_matter": {"PM1_0": 12.0, "PM2_5": 25.0, "PM10": 40.0},
                "gas_sensors": {"MQ2": {"voltage_V": 0.005, "raw_adc": 1}, "MQ9": {"voltage_V": 0.85, "raw_adc": 174}, "MQ135": {"voltage_V": 0.90, "raw_adc": 184}},
            },
            "expect_degraded": True,
        },
        # Case 2: Electrical Rail to VCC on MQ9 (4.995V)
        {
            "id": "ch_abs_02_mq9_rail_vcc",
            "desc": "MQ9 analog output shorted to 5V rail",
            "payload": {
                "node_id": "abs-node", "timestamp": "2024-09-15T12:00:00Z",
                "environment": {"temperature_C": 28.0, "humidity_pct": 55.0},
                "particulate_matter": {"PM1_0": 12.0, "PM2_5": 25.0, "PM10": 40.0},
                "gas_sensors": {"MQ2": {"voltage_V": 0.95, "raw_adc": 194}, "MQ9": {"voltage_V": 4.995, "raw_adc": 1022}, "MQ135": {"voltage_V": 0.90, "raw_adc": 184}},
            },
            "expect_degraded": True,
        },
        # Case 3: Out-of-Distribution extreme cold (-18C, 98%H)
        {
            "id": "ch_abs_03_extreme_cold_ood",
            "desc": "Extreme sub-zero temperature far beyond tropical sensor calibration",
            "payload": {
                "node_id": "abs-node", "timestamp": "2024-09-15T12:00:00Z",
                "environment": {"temperature_C": -18.0, "humidity_pct": 98.0},
                "particulate_matter": {"PM1_0": 15.0, "PM2_5": 30.0, "PM10": 45.0},
                "gas_sensors": {"MQ2": {"voltage_V": 0.85, "raw_adc": 174}, "MQ9": {"voltage_V": 0.75, "raw_adc": 153}, "MQ135": {"voltage_V": 0.80, "raw_adc": 164}},
            },
            "expect_uncertain": True,
        },
        # Case 4: Out-of-Distribution extreme heat (68C, 10%H)
        {
            "id": "ch_abs_04_extreme_heat_ood",
            "desc": "Industrial thermal chamber or direct solar overheating",
            "payload": {
                "node_id": "abs-node", "timestamp": "2024-09-15T12:00:00Z",
                "environment": {"temperature_C": 68.0, "humidity_pct": 10.0},
                "particulate_matter": {"PM1_0": 15.0, "PM2_5": 30.0, "PM10": 45.0},
                "gas_sensors": {"MQ2": {"voltage_V": 0.85, "raw_adc": 174}, "MQ9": {"voltage_V": 0.75, "raw_adc": 153}, "MQ135": {"voltage_V": 0.80, "raw_adc": 164}},
            },
            "expect_uncertain": True,
        },
        # Case 5: Inverted Particulate Matter Physics (PM1.0 > PM2.5 > PM10)
        {
            "id": "ch_abs_05_inverted_pm_physics",
            "desc": "Severe optical counter sensor failure where submicron exceeds coarse mass",
            "payload": {
                "node_id": "abs-node", "timestamp": "2024-09-15T12:00:00Z",
                "environment": {"temperature_C": 28.0, "humidity_pct": 55.0},
                "particulate_matter": {"PM1_0": 120.0, "PM2_5": 60.0, "PM10": 25.0},
                "gas_sensors": {"MQ2": {"voltage_V": 0.85, "raw_adc": 174}, "MQ9": {"voltage_V": 0.75, "raw_adc": 153}, "MQ135": {"voltage_V": 0.80, "raw_adc": 164}},
            },
            "expect_uncertain": True,
        },
        # Case 6: Equivocal flat gas signature (MQ2=1.55, MQ9=1.55, MQ135=1.55)
        {
            "id": "ch_abs_06_equivocal_flat_gas",
            "desc": "Ambiguous uniform gas elevation with zero differentiating peak",
            "payload": {
                "node_id": "abs-node", "timestamp": "2024-09-15T12:00:00Z",
                "environment": {"temperature_C": 28.0, "humidity_pct": 55.0},
                "particulate_matter": {"PM1_0": 20.0, "PM2_5": 45.0, "PM10": 70.0},
                "gas_sensors": {"MQ2": {"voltage_V": 1.55, "raw_adc": 317}, "MQ9": {"voltage_V": 1.55, "raw_adc": 317}, "MQ135": {"voltage_V": 1.55, "raw_adc": 317}},
            },
            "expect_uncertain": True,
        },
    ]

    return {
        "gas_challenge_cases": gas_challenge_cases,
        "sc_challenge_cases": sc_challenge_cases,
        "abstention_cases": abstention_cases,
    }


def run_evaluation():
    artifacts_dir = (server_dir / "artifacts").resolve()
    backup_dir = (server_dir / "artifacts" / "backups" / "original_baseline").resolve()

    print("=" * 80)
    print("NAVOSEDGE NEW INDEPENDENT CHALLENGE SUITE EVALUATION")
    print("=" * 80)

    # -------------------------------------------------------------
    # 1. External Station Reserve: Dhenkanal Station (Lat 20.70, Lon 85.60)
    # -------------------------------------------------------------
    print("\n--- PART 1: EXTERNAL STATION RESERVE (DHENKANAL STATION) ---")
    dhenkanal_aq_path = root_dir / "data" / "historical_cache" / "airquality_dhenkanal_2024-09-01_2024-10-06.json"
    with open(dhenkanal_aq_path) as f:
        dh_data = json.load(f)

    dh_pm25 = dh_data["hourly"]["pm2_5"]
    dh_pm10 = dh_data["hourly"]["pm10"]
    # Filter out missing None values
    valid_indices = [i for i in range(len(dh_pm25)) if dh_pm25[i] is not None and dh_pm10[i] is not None]
    dh_pm25 = [dh_pm25[i] for i in valid_indices]
    dh_pm10 = [dh_pm10[i] for i in valid_indices]

    print(f"Loaded {len(dh_pm25)} hourly observations from Dhenkanal monitoring station.")
    print(f"Dhenkanal PM2.5: min={min(dh_pm25):.1f}, mean={np.mean(dh_pm25):.1f}, max={max(dh_pm25):.1f} ug/m3")
    print(f"Dhenkanal PM10 : min={min(dh_pm10):.1f}, mean={np.mean(dh_pm10):.1f}, max={max(dh_pm10):.1f} ug/m3")

    # Fit AR(3) model on Bhubaneswar training data (first 80% of Bhubaneswar)
    dataset_records = load_dataset(root_dir / "test_data" / "historical_35d.jsonl")
    bb_pm25 = [r["particulate_matter"]["PM2_5"] for r in dataset_records if "particulate_matter" in r]
    bb_pm10 = [r["particulate_matter"]["PM10"] for r in dataset_records if "particulate_matter" in r]
    bb_split = int(len(bb_pm25) * 0.8)
    c25_bb, b25_bb = _fit_ar(bb_pm25[:bb_split], order=3)
    c10_bb, b10_bb = _fit_ar(bb_pm10[:bb_split], order=3)

    # Evaluate on Dhenkanal external station without any retraining or adaptation
    dh_results = {}
    for h_label, h_step in [("1-hour horizon (1 step)", 1), ("3-hour horizon (3 steps)", 3), ("6-hour horizon (6 steps)", 6)]:
        def eval_dh(data, coeffs, intercept, step):
            acts, preds_p, preds_ar = [], [], []
            for s in range(len(data) - step):
                hist = data[:s + 1]
                if len(hist) < 3:
                    continue
                preds_p.append(hist[-1])
                acts.append(data[s + step])
                preds_ar.append(_ar_predict(coeffs, intercept, hist, step)[-1])
            p_mae = sum(abs(p - a) for p, a in zip(preds_p, acts)) / len(acts)
            p_rmse = math.sqrt(sum((p - a)**2 for p, a in zip(preds_p, acts)) / len(acts))
            ar_mae = sum(abs(p - a) for p, a in zip(preds_ar, acts)) / len(acts)
            ar_rmse = math.sqrt(sum((p - a)**2 for p, a in zip(preds_ar, acts)) / len(acts))
            return p_mae, p_rmse, ar_mae, ar_rmse

        dh25_p_mae, dh25_p_rmse, dh25_ar_mae, dh25_ar_rmse = eval_dh(dh_pm25, c25_bb, b25_bb, h_step)
        dh10_p_mae, dh10_p_rmse, dh10_ar_mae, dh10_ar_rmse = eval_dh(dh_pm10, c10_bb, b10_bb, h_step)
        dh_results[h_label] = {
            "PM2.5": {"p_mae": dh25_p_mae, "ar_mae": dh25_ar_mae, "p_rmse": dh25_p_rmse, "ar_rmse": dh25_ar_rmse},
            "PM10": {"p_mae": dh10_p_mae, "ar_mae": dh10_ar_mae, "p_rmse": dh10_p_rmse, "ar_rmse": dh10_ar_rmse},
        }
        print(f"  {h_label}:")
        print(f"    PM2.5 -> Persistence: MAE={dh25_p_mae:.2f}, RMSE={dh25_p_rmse:.2f} | Damped AR(3): MAE={dh25_ar_mae:.2f}, RMSE={dh25_ar_rmse:.2f} [{'WIN' if dh25_ar_mae <= dh25_p_mae else 'LOSS'}]")
        print(f"    PM10  -> Persistence: MAE={dh10_p_mae:.2f}, RMSE={dh10_p_rmse:.2f} | Damped AR(3): MAE={dh10_ar_mae:.2f}, RMSE={dh10_ar_rmse:.2f} [{'WIN' if dh10_ar_mae <= dh10_p_mae else 'LOSS'}]")

    # -------------------------------------------------------------
    # 2. Shifted Parameter Challenge Cases (GasNet & SourceClassifier)
    # -------------------------------------------------------------
    print("\n--- PART 2: HELD-OUT SCENARIO PARAMETERS & SHIFTED CENTROIDS ---")
    challenges = generate_new_challenge_cases()

    gn_active = NumpyGasNetAdapter(artifacts_dir=artifacts_dir)
    gn_active.load()
    gn_backup = NumpyGasNetAdapter(artifacts_dir=backup_dir)
    gn_backup.load()

    sc_active = SourceClassifier(artifacts_dir=artifacts_dir)
    sc_active.load()
    sc_backup = SourceClassifier(artifacts_dir=backup_dir)
    sc_backup.load()

    print("\nA. TinyGasNet Shifted Parameter Cases (N=10):")
    gn_ch_act, gn_ch_bk = 0, 0
    for tc in challenges["gas_challenge_cases"]:
        r_act = asyncio.run(gn_active.predict(tc["mq2"], tc["mq9"], tc["mq135"], tc["t"], tc["h"]))
        r_bk = asyncio.run(gn_backup.predict(tc["mq2"], tc["mq9"], tc["mq135"], tc["t"], tc["h"]))
        ok_act = (r_act.gas_class == tc["exp_gas"])
        ok_bk = (r_bk.gas_class == tc["exp_gas"])
        if ok_act: gn_ch_act += 1
        if ok_bk: gn_ch_bk += 1
        print(f"  [{tc['id']:<30s}] Exp={tc['exp_gas']:<10s} | Baseline={str(r_bk.gas_class):<10s} ({'OK' if ok_bk else 'FAIL'}) | Retrained={str(r_act.gas_class):<10s} ({'OK' if ok_act else 'FAIL'})")

    print(f"TinyGasNet Shifted Challenge Score: Baseline = {gn_ch_bk}/10 ({gn_ch_bk*10}%) -> Retrained = {gn_ch_act}/10 ({gn_ch_act*10}%)")

    print("\nB. SourceClassifier Shifted Parameter Cases (N=10):")
    sc_ch_act, sc_ch_bk = 0, 0
    for tc in challenges["sc_challenge_cases"]:
        p = SensorPayload.model_validate(tc["payload"])
        r_act = sc_active.classify(p)
        r_bk = sc_backup.classify(p)
        act_src = r_act.get("top_source")
        bk_src = r_bk.get("top_source")
        ok_act = (act_src == tc["exp_src"])
        ok_bk = (bk_src == tc["exp_src"])
        if ok_act: sc_ch_act += 1
        if ok_bk: sc_ch_bk += 1
        print(f"  [{tc['id']:<35s}] Exp={tc['exp_src']:<32s} | Baseline={str(bk_src):<28s} | Retrained={str(act_src):<32s} ({'OK' if ok_act else 'FAIL'})")

    print(f"SourceClassifier Shifted Challenge Score: Baseline = {sc_ch_bk}/10 ({sc_ch_bk*10}%) -> Retrained = {sc_ch_act}/10 ({sc_ch_act*10}%)")

    # -------------------------------------------------------------
    # 3. Ambiguity & Safe-Failure / Abstention Tests (N=6)
    # -------------------------------------------------------------
    print("\n--- PART 3: AMBIGUITY, OOD & SAFE-FAILURE ABSTENTION TESTS ---")
    abs_passed = 0
    for tc in challenges["abstention_cases"]:
        try:
            p = SensorPayload.model_validate(tc["payload"])
        except Exception as e:
            abs_passed += 1
            print(f"  [{tc['id']:<32s}] Ingress Schema Validation Rejected Invalid Data ({type(e).__name__}) -> Safe Failure = PASS")
            continue
        r_sc = sc_active.classify(p)
        r_gn = asyncio.run(gn_active.predict(p.gas_sensors.MQ2.voltage_V, p.gas_sensors.MQ9.voltage_V, p.gas_sensors.MQ135.voltage_V, p.environment.temperature_C, p.environment.humidity_pct))

        data_q = r_sc.get("data_quality", {}).get("status", "valid")
        uncert = r_sc.get("uncertainty", {}).get("is_uncertain", False)
        top_src = r_sc.get("top_source")
        match_score = r_sc.get("predictions", [{}])[0].get("match_score", 0.0) if r_sc.get("predictions") else 0.0

        is_safe = False
        if tc.get("expect_degraded") and data_q in {"degraded", "invalid"}:
            is_safe = True
        elif tc.get("expect_uncertain") and (uncert is True or top_src == "UNKNOWN" or match_score < 0.35):
            is_safe = True

        if is_safe: abs_passed += 1
        print(f"  [{tc['id']:<32s}] DQ={data_q:<8s} | Uncertain={str(uncert):<5s} | TopSrc={str(top_src):<22s} | Score={match_score:.2f} -> Safe Failure = {'PASS' if is_safe else 'FAIL'}")

    print(f"Abstention & Safe-Failure Score: {abs_passed}/6 ({abs_passed/6*100:.1f}%)")

    # Save summary
    out_dir = root_dir / "test_data" / "new_challenge_eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dhenkanal_station_forecasting": dh_results,
        "tinygasnet_shifted": {"baseline": gn_ch_bk / 10, "retrained": gn_ch_act / 10},
        "source_classifier_shifted": {"baseline": sc_ch_bk / 10, "retrained": sc_ch_act / 10},
        "safe_failure_abstention": {"passed": abs_passed, "total": 6, "rate": abs_passed / 6},
    }
    with open(out_dir / "challenge_evaluation_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print("\nNEW CHALLENGE EVALUATION COMPLETE. Saved to test_data/new_challenge_eval/challenge_evaluation_summary.json")


if __name__ == "__main__":
    run_evaluation()
