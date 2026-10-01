#!/usr/bin/env python3
"""
Train TinyGasNet for gas classification and safety detection (PyTorch-Free / Pure NumPy).
"""

import numpy as np
import pandas as pd
import joblib
import json
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.metrics import classification_report, f1_score, accuracy_score

try:
    from Training.constants import RANDOM_SEED as SEED, FEATURES, DATASET_FILENAME
except ImportError:
    from constants import RANDOM_SEED as SEED, FEATURES, DATASET_FILENAME

np.random.seed(SEED)

# ------------------------------------------------------------------
# Pure NumPy TinyGasNet MLP
# ------------------------------------------------------------------
class NumPyTinyGasNet:
    def __init__(self, n_features: int = 5, n_classes: int = 8, hidden1: int = 32, hidden2: int = 16):
        self.n_features = n_features
        self.n_classes = n_classes
        self.hidden1 = hidden1
        self.hidden2 = hidden2

        rng = np.random.RandomState(SEED)
        self.W1 = (rng.randn(hidden1, n_features) * np.sqrt(2.0 / n_features)).astype(np.float32)
        self.b1 = np.zeros(hidden1, dtype=np.float32)
        self.W2 = (rng.randn(hidden2, hidden1) * np.sqrt(2.0 / hidden1)).astype(np.float32)
        self.b2 = np.zeros(hidden2, dtype=np.float32)
        self.Wc = (rng.randn(n_classes, hidden2) * np.sqrt(2.0 / hidden2)).astype(np.float32)
        self.bc = np.zeros(n_classes, dtype=np.float32)
        self.Ws = (rng.randn(1, hidden2) * np.sqrt(2.0 / hidden2)).astype(np.float32)
        self.bs = np.zeros(1, dtype=np.float32)

    def forward(self, x: np.ndarray, train: bool = False, p_drop: float = 0.1, rng: np.random.RandomState = None):
        h1 = np.maximum(0, x @ self.W1.T + self.b1)
        if train and p_drop > 0:
            mask1 = (rng.rand(*h1.shape) >= p_drop).astype(np.float32) / (1.0 - p_drop)
            h1 = h1 * mask1

        h2 = np.maximum(0, h1 @ self.W2.T + self.b2)
        if train and p_drop > 0:
            mask2 = (rng.rand(*h2.shape) >= p_drop).astype(np.float32) / (1.0 - p_drop)
            h2 = h2 * mask2

        logits_c = h2 @ self.Wc.T + self.bc
        logit_s = (h2 @ self.Ws.T + self.bs).squeeze(-1)
        return h1, h2, logits_c, logit_s

    def state_dict(self) -> dict:
        return {
            "fc1.weight": self.W1.copy(), "fc1.bias": self.b1.copy(),
            "fc2.weight": self.W2.copy(), "fc2.bias": self.b2.copy(),
            "class_head.weight": self.Wc.copy(), "class_head.bias": self.bc.copy(),
            "safety_head.weight": self.Ws.copy(), "safety_head.bias": self.bs.copy(),
        }

    def load_state_dict(self, state_dict: dict):
        self.W1 = state_dict["fc1.weight"].astype(np.float32)
        self.b1 = state_dict["fc1.bias"].astype(np.float32)
        self.W2 = state_dict["fc2.weight"].astype(np.float32)
        self.b2 = state_dict["fc2.bias"].astype(np.float32)
        self.Wc = state_dict["class_head.weight"].astype(np.float32)
        self.bc = state_dict["class_head.bias"].astype(np.float32)
        self.Ws = state_dict["safety_head.weight"].astype(np.float32)
        self.bs = state_dict["safety_head.bias"].astype(np.float32)

    def fit(self, X_train: np.ndarray, yc_train: np.ndarray, ys_train: np.ndarray,
            X_val: np.ndarray, yc_val: np.ndarray, ys_val: np.ndarray,
            epochs: int = 40, lr: float = 0.005, batch_size: int = 64):
        rng = np.random.RandomState(SEED)
        counts = np.bincount(yc_train, minlength=self.n_classes)
        cw = 1.0 / np.maximum(counts, 1)
        class_weights = (cw / cw.sum() * len(cw)).astype(np.float32)

        pos = ys_train.sum()
        neg = len(ys_train) - pos
        pos_weight = float(neg / max(pos, 1.0))

        m = {k: np.zeros_like(v) for k, v in self.state_dict().items()}
        v = {k: np.zeros_like(val) for k, val in self.state_dict().items()}
        beta1, beta2, eps = 0.9, 0.999, 1e-8
        t_step = 0
        best_loss = float("inf")
        best_weights = None

        n = len(X_train)
        for epoch in range(1, epochs + 1):
            indices = rng.permutation(n)
            for i in range(0, n, batch_size):
                idx = indices[i:i + batch_size]
                xb, ycb, ysb = X_train[idx], yc_train[idx], ys_train[idx]
                batch_len = len(xb)

                h1, h2, logits_c, logit_s = self.forward(xb, train=True, rng=rng)

                exp_c = np.exp(logits_c - np.max(logits_c, axis=-1, keepdims=True))
                probs_c = exp_c / np.sum(exp_c, axis=-1, keepdims=True)
                prob_s = 1.0 / (1.0 + np.exp(-np.clip(logit_s, -15.0, 15.0)))

                dlogits_c = probs_c.copy()
                dlogits_c[np.arange(batch_len), ycb] -= 1.0
                dlogits_c *= class_weights[ycb][:, None]
                dlogits_c /= batch_len

                w_s = np.where(ysb == 1.0, pos_weight, 1.0)
                dlogit_s = ((prob_s - ysb) * w_s / batch_len * 0.5)

                dWc = dlogits_c.T @ h2
                dbc = np.sum(dlogits_c, axis=0)

                dWs = dlogit_s[:, None].T @ h2
                dbs = np.sum(dlogit_s, axis=0, keepdims=True)

                dh2 = dlogits_c @ self.Wc + dlogit_s[:, None] @ self.Ws
                dh2[h2 <= 0] = 0.0

                dW2 = dh2.T @ h1
                db2 = np.sum(dh2, axis=0)

                dh1 = dh2 @ self.W2
                dh1[h1 <= 0] = 0.0

                dW1 = dh1.T @ xb
                db1 = np.sum(dh1, axis=0)

                grads = {
                    "fc1.weight": dW1, "fc1.bias": db1,
                    "fc2.weight": dW2, "fc2.bias": db2,
                    "class_head.weight": dWc, "class_head.bias": dbc,
                    "safety_head.weight": dWs, "safety_head.bias": dbs,
                }

                t_step += 1
                curr_state = self.state_dict()
                for key in grads:
                    g = grads[key] + 1e-4 * curr_state[key]
                    m[key] = beta1 * m[key] + (1.0 - beta1) * g
                    v[key] = beta2 * v[key] + (1.0 - beta2) * (g ** 2)
                    m_hat = m[key] / (1.0 - beta1 ** t_step)
                    v_hat = v[key] / (1.0 - beta2 ** t_step)
                    curr_state[key] -= lr * m_hat / (np.sqrt(v_hat) + eps)
                self.load_state_dict(curr_state)

            _, _, val_logits_c, val_logit_s = self.forward(X_val, train=False)
            val_exp_c = np.exp(val_logits_c - np.max(val_logits_c, axis=-1, keepdims=True))
            val_probs_c = val_exp_c / np.sum(val_exp_c, axis=-1, keepdims=True)
            val_prob_s = 1.0 / (1.0 + np.exp(-np.clip(val_logit_s, -15.0, 15.0)))

            v_loss_c = -np.mean(np.log(val_probs_c[np.arange(len(X_val)), yc_val] + 1e-12))
            v_loss_s = -np.mean(ys_val * np.log(val_prob_s + 1e-12) + (1 - ys_val) * np.log(1 - val_prob_s + 1e-12))
            val_loss = v_loss_c + 0.5 * v_loss_s

            if val_loss < best_loss:
                best_loss = val_loss
                best_weights = self.state_dict()

        if best_weights:
            self.load_state_dict(best_weights)

# ------------------------------------------------------------------
# Main execution
# ------------------------------------------------------------------
if __name__ == "__main__":
    df = pd.read_csv(DATASET_FILENAME)
    df = df.sort_values("timestamp").reset_index(drop=True)

    X = df[FEATURES].values.astype(np.float32)

    le = LabelEncoder()
    y_class = le.fit_transform(df["gas_label"].values)
    y_safety = (df["safety_status"] == "unsafe").astype(np.float32).values

    n = len(df)
    n_train = int(0.70 * n)
    n_val = int(0.15 * n)

    X_train, X_val, X_test = X[:n_train], X[n_train:n_train + n_val], X[n_train + n_val:]
    yc_train, yc_val, yc_test = y_class[:n_train], y_class[n_train:n_train + n_val], y_class[n_train + n_val:]
    ys_train, ys_val, ys_test = y_safety[:n_train], y_safety[n_train:n_train + n_val], y_safety[n_train + n_val:]

    scaler = StandardScaler().fit(X_train)
    X_train_s = scaler.transform(X_train).astype(np.float32)
    X_val_s = scaler.transform(X_val).astype(np.float32)
    X_test_s = scaler.transform(X_test).astype(np.float32)

    model = NumPyTinyGasNet(n_classes=len(le.classes_))
    model.fit(X_train_s, yc_train, ys_train, X_val_s, yc_val, ys_val, epochs=40)

    # Temperature Scaling
    _, _, val_logits_c, _ = model.forward(X_val_s, train=False)
    best_T = 1.0
    best_nll = float("inf")
    for T_cand in np.linspace(0.2, 5.0, 97):
        scaled_c = val_logits_c / T_cand
        exp_c = np.exp(scaled_c - np.max(scaled_c, axis=-1, keepdims=True))
        probs_c = exp_c / np.sum(exp_c, axis=-1, keepdims=True)
        nll = -np.mean(np.log(probs_c[np.arange(len(X_val_s)), yc_val] + 1e-12))
        if nll < best_nll:
            best_nll = nll
            best_T = float(T_cand)
    optimal_T = float(best_T)

    # Test set evaluation
    _, _, test_logits_c, test_logit_s = model.forward(X_test_s, train=False)
    scaled_test = test_logits_c / optimal_T
    pc = scaled_test.argmax(axis=1)
    prob_s = 1.0 / (1.0 + np.exp(-np.clip(test_logit_s, -15.0, 15.0)))
    ps = (prob_s > 0.5).astype(int)

    print("\n=== Test — Gas Classification ===")
    print(classification_report(yc_test, pc, target_names=le.classes_, zero_division=0))
    print(f"Test — Safety:  acc={accuracy_score(ys_test, ps):.4f}  F1={f1_score(ys_test, ps, zero_division=0):.4f}")
    print(f"\nCalibration temperature: T = {optimal_T:.4f}")

    joblib.dump({"scaler": scaler, "label_encoder": le, "temperature": optimal_T}, "preprocess.pkl")
    np.savez_compressed("gasnet_weights.npz", **model.state_dict())
    print("Saved: gasnet_weights.npz, preprocess.pkl (PyTorch-Free)")