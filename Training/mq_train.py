#!/usr/bin/env python3
"""
Train a tiny two-head MLP for gas classification and safety detection
using MQ-2/MQ-9/MQ-135 voltages + T + RH.
"""

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, TensorDataset
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.metrics import classification_report, f1_score, accuracy_score
import joblib

# ------------------------------------------------------------------
# Reproducibility
# ------------------------------------------------------------------
SEED = 42
np.random.seed(SEED)
torch.manual_seed(SEED)

# ------------------------------------------------------------------
# Load & prepare data
# ------------------------------------------------------------------
df = pd.read_csv('mq_synthetic_dataset.csv')
df = df.sort_values('timestamp').reset_index(drop=True)

FEATURES = ['MQ2_V', 'MQ9_V', 'MQ135_V', 'temperature_C', 'humidity_pct']
X = df[FEATURES].values.astype(np.float32)

le = LabelEncoder()
y_class  = le.fit_transform(df['gas_label'].values)                 # 0..7
y_safety = (df['safety_status'] == 'unsafe').astype(np.float32).values

# Chronological split (avoids temporal leakage)
n = len(df)
n_train = int(0.70 * n)
n_val   = int(0.15 * n)

X_train, X_val, X_test = X[:n_train], X[n_train:n_train+n_val], X[n_train+n_val:]
yc_train, yc_val, yc_test = y_class[:n_train], y_class[n_train:n_train+n_val], y_class[n_train+n_val:]
ys_train, ys_val, ys_test = y_safety[:n_train], y_safety[n_train:n_train+n_val], y_safety[n_train+n_val:]

# Feature scaling (fit ONLY on train)
scaler = StandardScaler().fit(X_train)
X_train = scaler.transform(X_train).astype(np.float32)
X_val   = scaler.transform(X_val).astype(np.float32)
X_test  = scaler.transform(X_test).astype(np.float32)

# Class weights (handles clean-air over-representation)
counts = np.bincount(yc_train, minlength=len(le.classes_))
cw = 1.0 / np.maximum(counts, 1)
cw = cw / cw.sum() * len(cw)
class_weights = torch.tensor(cw, dtype=torch.float32)

# Safety pos_weight (handles safe/unsafe imbalance)
pos = ys_train.sum()
neg = len(ys_train) - pos
pos_weight = torch.tensor([neg / max(pos, 1.0)], dtype=torch.float32)

# ------------------------------------------------------------------
# Model
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

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
model = TinyGasNet(n_classes=len(le.classes_)).to(device)
n_params = sum(p.numel() for p in model.parameters())
print(f"Model parameters: {n_params}")

# ------------------------------------------------------------------
# DataLoaders
# ------------------------------------------------------------------
train_ds = TensorDataset(torch.tensor(X_train),
                         torch.tensor(yc_train, dtype=torch.long),
                         torch.tensor(ys_train))
val_ds   = TensorDataset(torch.tensor(X_val),
                         torch.tensor(yc_val, dtype=torch.long),
                         torch.tensor(ys_val))
test_ds  = TensorDataset(torch.tensor(X_test),
                         torch.tensor(yc_test, dtype=torch.long),
                         torch.tensor(ys_test))

train_loader = DataLoader(train_ds, batch_size=64,  shuffle=True)
val_loader   = DataLoader(val_ds,   batch_size=256, shuffle=False)
test_loader  = DataLoader(test_ds,  batch_size=256, shuffle=False)

# ------------------------------------------------------------------
# Training loop
# ------------------------------------------------------------------
opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
EPOCHS = 60
best_val_f1 = -1.0

for epoch in range(1, EPOCHS + 1):
    model.train()
    for xb, ycb, ysb in train_loader:
        xb, ycb, ysb = xb.to(device), ycb.to(device), ysb.to(device)
        opt.zero_grad()
        logits_c, logit_s = model(xb)

        loss_c = F.cross_entropy(logits_c, ycb, weight=class_weights.to(device))
        loss_s = F.binary_cross_entropy_with_logits(
            logit_s, ysb, pos_weight=pos_weight.to(device))
        loss = loss_c + 0.5 * loss_s
        loss.backward()
        opt.step()

    # ---- validation (macro-F1 on class, F1 on safety) ----
    model.eval()
    pred_c_all, true_c_all, pred_s_all, true_s_all = [], [], [], []
    with torch.no_grad():
        for xb, ycb, ysb in val_loader:
            xb = xb.to(device)
            logits_c, logit_s = model(xb)
            pred_c_all.append(logits_c.argmax(1).cpu().numpy())
            true_c_all.append(ycb.numpy())
            pred_s_all.append((torch.sigmoid(logit_s) > 0.5).cpu().numpy().astype(int))
            true_s_all.append(ysb.numpy().astype(int))
    pc = np.concatenate(pred_c_all); tc = np.concatenate(true_c_all)
    ps = np.concatenate(pred_s_all); ts = np.concatenate(true_s_all)
    val_f1_c = f1_score(tc, pc, average='macro', zero_division=0)
    val_f1_s = f1_score(ts, ps, zero_division=0)
    score = 0.7 * val_f1_c + 0.3 * val_f1_s

    if score > best_val_f1:
        best_val_f1 = score
        torch.save(model.state_dict(), 'gasnet.pt')

    if epoch % 10 == 0 or epoch == 1:
        print(f"Epoch {epoch:3d} | val macroF1(class)={val_f1_c:.4f} "
              f"| val F1(safety)={val_f1_s:.4f}")

# ------------------------------------------------------------------
# Test set evaluation
# ------------------------------------------------------------------
model.load_state_dict(torch.load('gasnet.pt', map_location=device))
model.eval()

pred_c_all, true_c_all, pred_s_all, true_s_all = [], [], [], []
with torch.no_grad():
    for xb, ycb, ysb in test_loader:
        xb = xb.to(device)
        logits_c, logit_s = model(xb)
        pred_c_all.append(logits_c.argmax(1).cpu().numpy())
        true_c_all.append(ycb.numpy())
        pred_s_all.append((torch.sigmoid(logit_s) > 0.5).cpu().numpy().astype(int))
        true_s_all.append(ysb.numpy().astype(int))

pc = np.concatenate(pred_c_all); tc = np.concatenate(true_c_all)
ps = np.concatenate(pred_s_all); ts = np.concatenate(true_s_all)

print("\n=== Test — Gas Classification ===")
print(classification_report(tc, pc, target_names=le.classes_, zero_division=0))
print(f"Test — Safety:  acc={accuracy_score(ts, ps):.4f}  F1={f1_score(ts, ps):.4f}")

# ------------------------------------------------------------------
# Temperature scaling for calibrated confidence
# ------------------------------------------------------------------
val_logits_c, val_labels_c = [], []
with torch.no_grad():
    for xb, ycb, _ in val_loader:
        xb = xb.to(device)
        logits_c, _ = model(xb)
        val_logits_c.append(logits_c.cpu())
        val_labels_c.append(ycb)
val_logits_c = torch.cat(val_logits_c)
val_labels_c = torch.cat(val_labels_c)

T_param = nn.Parameter(torch.ones(1))
opt_T = torch.optim.LBFGS([T_param], lr=0.1, max_iter=60)

def closure():
    opt_T.zero_grad()
    loss = F.cross_entropy(val_logits_c / T_param, val_labels_c)
    loss.backward()
    return loss

opt_T.step(closure)
optimal_T = float(T_param.item())
print(f"\nCalibration temperature: T = {optimal_T:.4f}")

# ------------------------------------------------------------------
# Persist artifacts
# ------------------------------------------------------------------
joblib.dump(
    {'scaler': scaler, 'label_encoder': le, 'temperature': optimal_T},
    'preprocess.pkl'
)
print("Saved: gasnet.pt, preprocess.pkl")