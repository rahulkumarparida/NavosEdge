#!/usr/bin/env python3
"""
Inference for trained TinyGasNet (PyTorch-Free / Pure NumPy).
Returns: gas class, class confidence, safety status,
safety confidence, and predictive uncertainty.
"""

import numpy as np
import joblib
import json
import sys
from pathlib import Path

# ------------------------------------------------------------------
# Pure NumPy Inference Implementation
# ------------------------------------------------------------------
def predict(mq2_v: float, mq9_v: float, mq135_v: float,
            temperature_c: float, humidity_pct: float,
            n_mc: int = 20):
    """
    Pure NumPy MC-Dropout prediction.
    """
    artifacts_dir = Path("Intelligence/Server/artifacts")
    if not (artifacts_dir / "gasnet_weights.npz").exists():
        artifacts_dir = Path("Training/models")

    weights_data = np.load(artifacts_dir / "gasnet_weights.npz")
    W1 = weights_data["fc1.weight"].astype(np.float32)
    b1 = weights_data["fc1.bias"].astype(np.float32)
    W2 = weights_data["fc2.weight"].astype(np.float32)
    b2 = weights_data["fc2.bias"].astype(np.float32)
    Wc = weights_data["class_head.weight"].astype(np.float32)
    bc = weights_data["class_head.bias"].astype(np.float32)
    Ws = weights_data["safety_head.weight"].astype(np.float32)
    bs = weights_data["safety_head.bias"].astype(np.float32)

    with open(artifacts_dir / "model_metadata.json") as f:
        meta = json.load(f)

    labels = meta["class_labels"]
    T_cal = float(meta["calibration_temperature"])
    mean = np.array(meta["preprocessing"]["scaler_mean"], dtype=np.float32)
    scale = np.array(meta["preprocessing"]["scaler_scale"], dtype=np.float32)

    x_raw = np.array([[mq2_v, mq9_v, mq135_v, temperature_c, humidity_pct]], dtype=np.float32)
    x = (x_raw - mean) / scale

    rng = np.random.RandomState(42)
    p_drop = float(meta["architecture"].get("p_drop", 0.1))
    keep_prob = 1.0 - p_drop
    drop_scale = 1.0 / keep_prob

    class_probs_runs = []
    safety_probs_runs = []

    for _ in range(n_mc):
        h1 = np.maximum(0, x @ W1.T + b1)
        m1 = (rng.rand(*h1.shape) >= p_drop).astype(np.float32) * drop_scale
        h1 = h1 * m1

        h2 = np.maximum(0, h1 @ W2.T + b2)
        m2 = (rng.rand(*h2.shape) >= p_drop).astype(np.float32) * drop_scale
        h2 = h2 * m2

        logits_c = h2 @ Wc.T + bc
        scaled_c = logits_c / T_cal
        exp_c = np.exp(scaled_c - np.max(scaled_c, axis=-1, keepdims=True))
        probs_c = exp_c / np.sum(exp_c, axis=-1, keepdims=True)

        logit_s = (h2 @ Ws.T + bs).squeeze(-1)
        prob_s = 1.0 / (1.0 + np.exp(-logit_s))

        class_probs_runs.append(probs_c[0])
        safety_probs_runs.append(float(prob_s[0]) if np.ndim(prob_s) > 0 else float(prob_s))

    class_probs = np.stack(class_probs_runs)
    safety_probs = np.array(safety_probs_runs)

    mean_class = class_probs.mean(axis=0)
    mean_safety = float(safety_probs.mean())

    class_idx = int(mean_class.argmax())
    class_name = str(labels[class_idx])
    class_conf = float(mean_class[class_idx])

    eps = 1e-12
    entropy = -float(np.sum(mean_class * np.log(mean_class + eps)))
    max_entropy = float(np.log(len(labels)))
    uncertainty = entropy / max_entropy if max_entropy > 0 else 0.0

    safety_status = "unsafe" if mean_safety > 0.5 else "safe"
    safety_conf = mean_safety if mean_safety > 0.5 else 1.0 - mean_safety

    return {
        "gas_class": class_name,
        "class_confidence": round(class_conf, 4),
        "class_probabilities": {str(labels[i]): round(float(mean_class[i]), 4) for i in range(len(labels))},
        "safety_status": safety_status,
        "safety_confidence": round(float(safety_conf), 4),
        "uncertainty": round(uncertainty, 4),
    }

if __name__ == "__main__":
    if len(sys.argv) == 6:
        mq2, mq9, mq135, tc, rh = map(float, sys.argv[1:])
    else:
        mq2, mq9, mq135, tc, rh = 0.1900, 0.1200, 0.0500, 35, 70
        print("No args supplied — running demo sample.\n"
              "Usage: python mq_infer.py MQ2_V MQ9_V MQ135_V TEMP_C RH_PCT\n")

    result = predict(mq2, mq9, mq135, tc, rh)
    print(json.dumps(result, indent=2))