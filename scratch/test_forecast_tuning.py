"""
Test Ridge regularization and AR lag tuning on 35-day dataset.
"""

import json
import math
from pathlib import Path
from Simulator.session import load_dataset


def solve_least_squares_ridge(X, y, l2_reg=1e-2):
    n = len(X)
    p = len(X[0]) if n > 0 else 0
    if n == 0 or p == 0 or n < p:
        return None

    XtX = [[0.0] * p for _ in range(p)]
    for i in range(p):
        for j in range(p):
            s = 0.0
            for k in range(n):
                s += X[k][i] * X[k][j]
            XtX[i][j] = s
        # Apply Ridge penalty to lag coefficients (not the intercept at index p-1)
        if i < p - 1:
            XtX[i][i] += l2_reg

    Xty = [0.0] * p
    for i in range(p):
        s = 0.0
        for k in range(n):
            s += X[k][i] * y[k]
        Xty[i] = s

    aug = [row[:] + [Xty[i]] for i, row in enumerate(XtX)]
    for col in range(p):
        pivot = aug[col][col]
        if abs(pivot) < 1e-12:
            return None
        for j in range(col, p + 1):
            aug[col][j] /= pivot
        for row in range(p):
            if row == col:
                continue
            factor = aug[row][col]
            for j in range(col, p + 1):
                aug[row][j] -= factor * aug[col][j]

    return [aug[i][p] for i in range(p)]


def fit_ar_ridge(values, order, l2_reg=1e-2):
    if len(values) < order + 2:
        return None
    X, y = [], []
    for t in range(order, len(values)):
        row = [values[t - lag - 1] for lag in range(order)]
        row.append(1.0)
        X.append(row)
        y.append(values[t])
    beta = solve_least_squares_ridge(X, y, l2_reg=l2_reg)
    if beta is None:
        return None
    return beta[:-1], beta[-1]


def ar_predict_damped(coeffs, intercept, recent, steps, damping=0.98):
    order = len(coeffs)
    buffer = list(recent[-order:])
    predictions = []
    last_val = recent[-1]

    for step_idx in range(steps):
        pred = intercept
        for lag in range(order):
            pred += coeffs[lag] * buffer[-(lag + 1)]
        # Gentle shrinkage towards recent value for multi-step horizons to prevent compounding drift
        weight = damping ** (step_idx + 1)
        stabilized = weight * pred + (1.0 - weight) * last_val
        stabilized = max(0.0, stabilized)
        predictions.append(round(stabilized, 2))
        buffer.append(stabilized)

    return predictions


def run():
    records = load_dataset(Path("test_data/historical_35d.jsonl"))
    pm25 = [r["particulate_matter"]["PM2_5"] for r in records if "particulate_matter" in r]
    pm10 = [r["particulate_matter"]["PM10"] for r in records if "particulate_matter" in r]

    split_idx = int(len(pm25) * 0.8)
    train25, test25 = pm25[:split_idx], pm25[split_idx:]
    train10, test10 = pm10[:split_idx], pm10[split_idx:]

    for l2 in [0.0, 1e-3, 1e-2, 0.1]:
        for damp in [1.0, 0.98, 0.95]:
            coeffs25, b25 = fit_ar_ridge(train25, order=3, l2_reg=l2)
            coeffs10, b10 = fit_ar_ridge(train10, order=3, l2_reg=l2)

            for horizon in [3, 6, 12]:
                actuals25, p_preds25, ar_preds25 = [], [], []
                actuals10, p_preds10, ar_preds10 = [], [], []
                for s in range(len(test25) - horizon):
                    h25 = list(train25) + list(test25[:s])
                    h10 = list(train10) + list(test10[:s])
                    p_preds25.append(h25[-1])
                    p_preds10.append(h10[-1])
                    actuals25.append(test25[s + horizon])
                    actuals10.append(test10[s + horizon])

                    pred25 = ar_predict_damped(coeffs25, b25, h25, horizon, damping=damp)
                    pred10 = ar_predict_damped(coeffs10, b10, h10, horizon, damping=damp)
                    ar_preds25.append(pred25[-1])
                    ar_preds10.append(pred10[-1])

                mae_p25 = sum(abs(p - a) for p, a in zip(p_preds25, actuals25)) / len(actuals25)
                mae_ar25 = sum(abs(p - a) for p, a in zip(ar_preds25, actuals25)) / len(actuals25)
                mae_p10 = sum(abs(p - a) for p, a in zip(p_preds10, actuals10)) / len(actuals10)
                mae_ar10 = sum(abs(p - a) for p, a in zip(ar_preds10, actuals10)) / len(actuals10)

                if l2 == 0.001 and damp == 0.98:
                    rmse_p25 = math.sqrt(sum((p - a)**2 for p, a in zip(p_preds25, actuals25)) / len(actuals25))
                    rmse_ar25 = math.sqrt(sum((p - a)**2 for p, a in zip(ar_preds25, actuals25)) / len(actuals25))
                    rmse_p10 = math.sqrt(sum((p - a)**2 for p, a in zip(p_preds10, actuals10)) / len(actuals10))
                    rmse_ar10 = math.sqrt(sum((p - a)**2 for p, a in zip(ar_preds10, actuals10)) / len(actuals10))
                    print(f"Horizon {horizon*5}m (Damp=0.98):")
                    print(f"  PM2.5 -> Persistence MAE: {mae_p25:.2f}, RMSE: {rmse_p25:.2f} | AR MAE: {mae_ar25:.2f}, RMSE: {rmse_ar25:.2f}")
                    print(f"  PM10  -> Persistence MAE: {mae_p10:.2f}, RMSE: {rmse_p10:.2f} | AR MAE: {mae_ar10:.2f}, RMSE: {rmse_ar10:.2f}")


if __name__ == "__main__":
    run()
