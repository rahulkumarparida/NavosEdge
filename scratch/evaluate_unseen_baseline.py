"""
Evaluate current baseline models on the unseen evaluation suites.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parents[1]
server_dir = root_dir / "Intelligence" / "Server"
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))
if str(server_dir) not in sys.path:
    sys.path.insert(0, str(server_dir))

import asyncio
from app.services.numpy_inference import NumpyGasNetAdapter
from app.source_classifier.classifier import SourceClassifier
from app.schemas.sensor import SensorPayload
from app.anomaly.engine import AnomalyEngine


def evaluate_unseen_suites(artifacts_dir: Path):
    print("=" * 60)
    print("EVALUATING BASELINE ON UNSEEN SUITES")
    print("=" * 60)

    # Load models
    gasnet = NumpyGasNetAdapter(artifacts_dir=artifacts_dir)
    gasnet.load()
    source_classifier = SourceClassifier(artifacts_dir=artifacts_dir)
    source_classifier.load()
    anomaly_engine = AnomalyEngine()

    eval_dir = Path("test_data/unseen_eval")
    with open(eval_dir / "eval_unseen_combinations.json") as f:
        unseen_cases = json.load(f)
    with open(eval_dir / "eval_boundary_ood.json") as f:
        boundary_cases = json.load(f)
    with open(eval_dir / "eval_perturbations.json") as f:
        perturb_cases = json.load(f)

    # 1. Unseen Combinations
    print("\n--- 1. Unseen Environmental Combinations ---")
    gasnet_correct = 0
    sc_correct = 0
    for case in unseen_cases:
        p = SensorPayload.model_validate(case["payload"])
        # GasNet
        gn_res = asyncio.run(gasnet.predict(
            p.gas_sensors.MQ2.voltage_V,
            p.gas_sensors.MQ9.voltage_V,
            p.gas_sensors.MQ135.voltage_V,
            p.environment.temperature_C,
            p.environment.humidity_pct,
        ))
        gn_pred = gn_res.gas_class
        gn_match = (gn_pred == case["expected_gas"])
        if gn_match:
            gasnet_correct += 1

        # SourceClassifier
        sc_res = source_classifier.classify(p)
        sc_pred = sc_res.get("top_source") or "UNKNOWN"
        sc_match = (sc_pred == case["expected_source"])
        if sc_match:
            sc_correct += 1

        print(f"[{case['id']}] Expected: Gas={case['expected_gas']}, Src={case['expected_source']} | "
              f"GasNet={gn_pred} ({'OK' if gn_match else 'FAIL'}), SC={sc_pred} ({'OK' if sc_match else 'FAIL'})")

    print(f"Unseen Combinations Score -> GasNet: {gasnet_correct}/{len(unseen_cases)} ({gasnet_correct/len(unseen_cases)*100:.1f}%), "
          f"SourceClassifier: {sc_correct}/{len(unseen_cases)} ({sc_correct/len(unseen_cases)*100:.1f}%)")

    # 2. Boundary & OOD
    print("\n--- 2. Boundary and OOD Tests ---")
    boundary_safe = 0
    for case in boundary_cases:
        p = SensorPayload.model_validate(case["payload"])
        sc_res = source_classifier.classify(p)
        sc_pred = sc_res.get("top_source") or "UNKNOWN"
        is_uncertain = sc_res.get("uncertainty", {}).get("is_uncertain", False) or (sc_pred == "UNKNOWN")

        gn_res = asyncio.run(gasnet.predict(
            p.gas_sensors.MQ2.voltage_V,
            p.gas_sensors.MQ9.voltage_V,
            p.gas_sensors.MQ135.voltage_V,
            p.environment.temperature_C,
            p.environment.humidity_pct,
        ))

        anom_res = anomaly_engine.analyse(p.node_id, case["payload"])
        is_anom = anom_res.get("is_anomaly", False)

        passed = True
        if case.get("expected_anomaly") and not is_anom:
            passed = False
        if case.get("expected_uncertainty") and not is_uncertain:
            passed = False
        if passed:
            boundary_safe += 1

        print(f"[{case['id']}] Anomaly={is_anom} (exp={case.get('expected_anomaly')}), "
              f"SC Uncertain={is_uncertain} (exp={case.get('expected_uncertainty')}), "
              f"GasNet={gn_res.gas_class} -> {'PASS' if passed else 'FAIL'}")

    print(f"Boundary/OOD Safe Pass Rate: {boundary_safe}/{len(boundary_cases)} ({boundary_safe/len(boundary_cases)*100:.1f}%)")

    # 3. Perturbation Robustness
    print("\n--- 3. Perturbation Robustness ---")
    perturb_stable = 0
    for case in perturb_cases:
        p = SensorPayload.model_validate(case["payload"])
        gn_res = asyncio.run(gasnet.predict(
            p.gas_sensors.MQ2.voltage_V,
            p.gas_sensors.MQ9.voltage_V,
            p.gas_sensors.MQ135.voltage_V,
            p.environment.temperature_C,
            p.environment.humidity_pct,
        ))
        sc_res = source_classifier.classify(p)
        top_src = sc_res.get("top_source") or "UNKNOWN"
        match = (gn_res.gas_class == case["expected_gas"]) and (top_src == case["expected_source"])
        if match:
            perturb_stable += 1

    print(f"Perturbation Accuracy: {perturb_stable}/{len(perturb_cases)} ({perturb_stable/len(perturb_cases)*100:.1f}%)")

    retrained_metrics = {
        "unseen_gasnet_acc": gasnet_correct / len(unseen_cases),
        "unseen_sc_acc": sc_correct / len(unseen_cases),
        "boundary_pass_rate": boundary_safe / len(boundary_cases),
        "perturbation_acc": perturb_stable / len(perturb_cases),
    }
    with open("test_data/unseen_eval/retrained_unseen_results.json", "w") as f:
        json.dump(retrained_metrics, f, indent=2)


if __name__ == "__main__":
    evaluate_unseen_suites((server_dir / "artifacts").resolve())
