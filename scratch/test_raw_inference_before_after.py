import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Intelligence" / "Server"))

from app.services.numpy_inference import NumpyGasNetAdapter

artifacts = Path("Intelligence/Server/artifacts")
adapter = NumpyGasNetAdapter(artifacts_dir=artifacts)
adapter.load()

test_cases = [
    ("GND Rail Short (0.0V on all MQ)", 0.0, 0.0, 0.0, 25.0, 50.0),
    ("Single Sensor GND Rail Short (MQ2=0.0V)", 0.0, 1.2, 1.3, 25.0, 50.0),
    ("Supply Rail Short (5.0V on all MQ)", 5.0, 5.0, 5.0, 25.0, 50.0),
    ("Extreme Freezing (-30.0°C)", 1.2, 1.2, 1.2, -30.0, 50.0),
    ("Extreme Furnace (75.0°C)", 1.2, 1.2, 1.2, 75.0, 50.0),
    ("Saturated Humidity (105%)", 1.2, 1.2, 1.2, 25.0, 105.0),
    ("Normal Clean Air (0.85V, 0.75V, 0.80V)", 0.85, 0.75, 0.80, 25.0, 50.0),
    ("Normal Smoke Event (3.2V, 2.4V, 2.8V)", 3.2, 2.4, 2.8, 25.0, 50.0),
]

print("=" * 90)
print("BEFORE VS AFTER SAFETY GATE BEHAVIOR EVALUATION")
print("=" * 90)

for label, mq2, mq9, mq135, temp, hum in test_cases:
    # 1. Raw forward pass (simulate before Phase 2A - no safety gate)
    x_raw = np.array([[mq2, mq9, mq135, temp, hum]], dtype=np.float32)
    x_scaled = (x_raw - adapter._scaler_mean) / adapter._scaler_scale
    h1 = np.maximum(0, x_scaled @ adapter._W1.T + adapter._b1)
    h2 = np.maximum(0, h1 @ adapter._W2.T + adapter._b2)
    logits_c = (h2 @ adapter._Wc.T + adapter._bc) / adapter._calibration_temp
    exp_c = np.exp(logits_c - np.max(logits_c))
    probs_c = exp_c / np.sum(exp_c)
    raw_class = adapter._class_labels[int(np.argmax(probs_c))]
    raw_conf = float(np.max(probs_c))

    logits_s = h2 @ adapter._Ws.T + adapter._bs
    safety_prob = 1.0 / (1.0 + np.exp(-float(logits_s[0, 0])))
    raw_safety = "unsafe" if safety_prob > 0.5 else "safe"
    raw_safety_conf = float(safety_prob if safety_prob > 0.5 else 1.0 - safety_prob)

    # 2. Gated forward pass (with Phase 2A Safety Gate)
    gated_res = adapter._sync_predict(
        mq2_v=mq2, mq9_v=mq9, mq135_v=mq135, temperature_c=temp, humidity_pct=hum
    )

    print(f"\nScenario: {label}")
    print(f"  Inputs: MQ2={mq2}V, MQ9={mq9}V, MQ135={mq135}V, T={temp}°C, H={hum}%")
    print(f"  BEFORE (Raw NN):")
    print(f"    Status: SUCCESS | Gas Class: {raw_class} ({raw_conf*100:.2f}%) | Safety: {raw_safety} ({raw_safety_conf*100:.2f}%) | Uncertainty: None")
    print(f"  AFTER (With Safety Gate):")
    print(f"    Status: {gated_res.status.value} | Gas Class: {gated_res.gas_class} | Safety: {gated_res.safety_status} | Uncertainty: {gated_res.uncertainty} | Reason: {gated_res.error_message}")
