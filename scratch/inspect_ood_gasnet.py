import json

with open("test_data/phase2_model_audit/synthetic_tinygasnet_eval_seed_42.json") as f:
    d = json.load(f)

from pathlib import Path
import sys
ROOT_DIR = Path(".").resolve()
sys.path.insert(0, str(ROOT_DIR / "Intelligence" / "Server"))
from app.services.numpy_inference import NumpyGasNetAdapter

adapter = NumpyGasNetAdapter(ROOT_DIR / "Intelligence" / "Server" / "artifacts")
adapter.load()

print("=== OUT-OF-RANGE & FAULT BOUNDARY PREDICTIONS (ACTIVE TINYGASNET) ===")
for item in d["data"]:
    if item["category"] == "out_of_range_ood":
        res = adapter._sync_predict(item["mq2"], item["mq9"], item["mq135"], item["t"], item["h"])
        print(f"[{item.get('desc', 'OOD'):26s}] Inputs: MQ=({item['mq2']}, {item['mq9']}, {item['mq135']}), T={item['t']}C, H={item['h']}% -> "
              f"Pred: {res.gas_class:10s} (Conf={res.class_confidence:.4f}, Entropy={res.uncertainty:.4f}, Safety={res.safety_status})")

print("\n=== AMBIGUOUS SAMPLES PREDICTIONS (ACTIVE TINYGASNET) ===")
for item in d["data"]:
    if item["category"] == "ambiguous_mixture":
        res = adapter._sync_predict(item["mq2"], item["mq9"], item["mq135"], item["t"], item["h"])
        print(f"Inputs: MQ=({item['mq2']}, {item['mq9']}, {item['mq135']}), T={item['t']}C, H={item['h']}% -> "
              f"Exp={item['expected_gas']:8s} | Pred: {res.gas_class:10s} (Conf={res.class_confidence:.4f}, Entropy={res.uncertainty:.4f})")
