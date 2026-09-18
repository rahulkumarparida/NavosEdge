#!/usr/bin/env python3
"""
Inference for the trained TinyGasNet.
Returns: gas class, class confidence, safety status,
safety confidence, and predictive uncertainty.
"""

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import joblib
import json
import sys

# ------------------------------------------------------------------
# Model definition (must match training)
# ------------------------------------------------------------------
class TinyGasNet(nn.Module):
    def __init__(self, n_features=5, n_classes=8,
                 hidden1=32, hidden2=16, p_drop=0.1):
        super().__init__()
        self.fc1 = nn.Linear(n_features, hidden1)
        self.fc2 = nn.Linear(hidden1, hidden2)
        self.drop = nn.Dropout(p_drop)
        self.class_head  = nn.Linear(hidden2, n_classes)
        self.safety_head = nn.Linear(hidden2, 1)

    def forward(self, x):
        h = F.relu(self.fc1(x))
        h = self.drop(h)
        h = F.relu(self.fc2(h))
        h = self.drop(h)
        return self.class_head(h), self.safety_head(h).squeeze(-1)

# ------------------------------------------------------------------
# Load artifacts
# ------------------------------------------------------------------
bundle  = joblib.load('models/preprocess.pkl')
scaler  = bundle['scaler']
le      = bundle['label_encoder']
T_cal   = bundle['temperature']

model = TinyGasNet(n_classes=len(le.classes_))
model.load_state_dict(torch.load('models/gasnet.pt', map_location='cpu'))
model.eval()

# ------------------------------------------------------------------
# Prediction API
# ------------------------------------------------------------------
def predict(mq2_v: float, mq9_v: float, mq135_v: float,
            temperature_c: float, humidity_pct: float,
            n_mc: int = 20):
    """
    Returns a dict with:
      gas_class, class_confidence, class_probabilities,
      safety_status, safety_confidence,
      uncertainty (0=very certain, 1=maximum entropy)
    """
    x = np.array([[mq2_v, mq9_v, mq135_v, temperature_c, humidity_pct]],
                 dtype=np.float32)
    x = scaler.transform(x).astype(np.float32)
    x_t = torch.tensor(x)

    # ---- MC-Dropout: keep dropout active ----
    model.train()
    class_probs_runs  = []
    safety_probs_runs = []
    with torch.no_grad():
        for _ in range(n_mc):
            logits_c, logit_s = model(x_t)
            # temperature-scaled softmax
            class_probs_runs.append(
                F.softmax(logits_c / T_cal, dim=1).numpy())
            safety_probs_runs.append(
                torch.sigmoid(logit_s).numpy())

    class_probs  = np.stack(class_probs_runs)[:, 0, :]   # (n_mc, n_classes)
    safety_probs = np.stack(safety_probs_runs)[:, 0]     # (n_mc,)

    mean_class  = class_probs.mean(0)                    # (n_classes,)
    mean_safety = float(safety_probs.mean())

    class_idx  = int(mean_class.argmax())
    class_name = le.classes_[class_idx]
    class_conf = float(mean_class[class_idx])

    # Predictive entropy, normalised to [0,1]
    eps = 1e-12
    entropy = -np.sum(mean_class * np.log(mean_class + eps))
    max_entropy = np.log(len(le.classes_))
    uncertainty = float(entropy / max_entropy)

    safety_status = 'unsafe' if mean_safety > 0.5 else 'safe'
    safety_conf   = mean_safety if mean_safety > 0.5 else 1.0 - mean_safety

    return {
        'gas_class':            class_name,
        'class_confidence':     round(class_conf, 4),
        'class_probabilities':  {le.classes_[i]: round(float(mean_class[i]), 4)
                                 for i in range(len(le.classes_))},
        'safety_status':        safety_status,
        'safety_confidence':    round(float(safety_conf), 4),
        'uncertainty':          round(uncertainty, 4),
    }

# ------------------------------------------------------------------
# CLI demo
# ------------------------------------------------------------------
if __name__ == '__main__':
    if len(sys.argv) == 6:
        mq2, mq9, mq135, tc, rh = map(float, sys.argv[1:])
    else:
        # Fallback demo values (volts on 0–3.3 V ADC after divider)
        mq2, mq9, mq135, tc, rh = 	0.1900	,0.1200	,0.0500	,35	,70
        print("No args supplied — running demo sample.\n"
              "Usage: python infer.py MQ2_V MQ9_V MQ135_V TEMP_C RH_PCT\n")

    result = predict(mq2, mq9, mq135, tc, rh)
    print(json.dumps(result, indent=2))