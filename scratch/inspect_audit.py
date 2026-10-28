import json

with open("test_data/phase2_model_audit/audit_summary_metrics.json") as f:
    d = json.load(f)

print("=== TINYGASNET ACTIVE PER-CLASS (Seed 42) ===")
act_gn = d["tinygasnet_results"]["active"][0]
for k, v in act_gn["per_class"].items():
    print(f"  {k:12s}: P={v['precision']:.4f}, R={v['recall']:.4f}, F1={v['f1']:.4f}, Supp={v['support']}")

print("\n=== TINYGASNET BASELINE PER-CLASS (Seed 42) ===")
base_gn = d["tinygasnet_results"]["baseline"][0]
for k, v in base_gn["per_class"].items():
    print(f"  {k:12s}: P={v['precision']:.4f}, R={v['recall']:.4f}, F1={v['f1']:.4f}, Supp={v['support']}")

print("\n=== TINYGASNET CONFUSION MATRIX (ACTIVE) ===")
print("Classes:", act_gn["confusion_matrix"]["classes"])
for row in act_gn["confusion_matrix"]["matrix"]:
    print(row)

print("\n=== TINYGASNET CONFUSION MATRIX (BASELINE) ===")
print("Classes:", base_gn["confusion_matrix"]["classes"])
for row in base_gn["confusion_matrix"]["matrix"]:
    print(row)

print("\n=== SOURCE CLASSIFIER ACTIVE PER-CLASS (Seed 42) ===")
act_sc = d["source_classifier_results"]["active"][0]["standard_shifted_metrics"]
for k, v in act_sc["per_class"].items():
    print(f"  {k:35s}: P={v['precision']:.4f}, R={v['recall']:.4f}, F1={v['f1']:.4f}, Supp={v['support']}")

print("\n=== SOURCE CLASSIFIER BASELINE PER-CLASS (Seed 42) ===")
base_sc = d["source_classifier_results"]["baseline"][0]["standard_shifted_metrics"]
for k, v in base_sc["per_class"].items():
    print(f"  {k:35s}: P={v['precision']:.4f}, R={v['recall']:.4f}, F1={v['f1']:.4f}, Supp={v['support']}")

print("\n=== SOURCE CLASSIFIER CONFUSION MATRIX (ACTIVE) ===")
print("Classes:", act_sc["confusion_matrix"]["classes"])
for row in act_sc["confusion_matrix"]["matrix"]:
    print(row)

print("\n=== SOURCE CLASSIFIER CATEGORY BREAKDOWN (ACTIVE) ===")
for cat, vals in d["source_classifier_results"]["active"][0]["category_breakdown"].items():
    print(f"  {cat:30s}: Acc={vals['effective_accuracy']:.4f}, Uncertain={vals['uncertainty_rate']:.4f}, Mixed={vals['mixed_detected_rate']:.4f}, N={vals['samples']}")

print("\n=== SOURCE CLASSIFIER CATEGORY BREAKDOWN (BASELINE) ===")
for cat, vals in d["source_classifier_results"]["baseline"][0]["category_breakdown"].items():
    print(f"  {cat:30s}: Acc={vals['effective_accuracy']:.4f}, Uncertain={vals['uncertainty_rate']:.4f}, Mixed={vals['mixed_detected_rate']:.4f}, N={vals['samples']}")

print("\n=== TINYGASNET RELIABILITY BINS (ACTIVE) ===")
for b in act_gn["calibration_bins"]:
    if b["count"] > 0:
        print(f"  Bin {b['bin_range']:12s}: Count={b['count']:3d}, Conf={b['confidence']:.4f}, Acc={b['accuracy']:.4f}, Err={b['abs_error']:.4f}")

print("\n=== TINYGASNET RELIABILITY BINS (BASELINE) ===")
for b in base_gn["calibration_bins"]:
    if b["count"] > 0:
        print(f"  Bin {b['bin_range']:12s}: Count={b['count']:3d}, Conf={b['confidence']:.4f}, Acc={b['accuracy']:.4f}, Err={b['abs_error']:.4f}")

