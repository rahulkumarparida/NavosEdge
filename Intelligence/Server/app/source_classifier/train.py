"""
Training pipeline for the Phase 3 Source Classifier.

Generates synthetic source-scenario training data, trains a lightweight
DecisionTreeClassifier, computes per-class reference statistics, and
saves all artifacts.

IMPORTANT: This uses SYNTHETIC data modeled after sensor characteristics
observed in urban Indian environments.  The resulting classifier is
UNVALIDATED against real-world ground-truth source labels.  Do NOT
interpret its outputs as confirmed source identities.

Usage:
    cd Intelligence/Server
    python -m app.source_classifier.train [--output-dir ./artifacts]
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------
# Synthetic scenario definitions
#
# Each scenario models plausible sensor patterns for an urban Indian city
# like Bhubaneswar.  Parameters are distributions (mean, std) for each
# feature.  These are NOT calibrated measurements — they encode relative
# patterns that help the classifier learn which features are discriminative.
#
# The voltage values model MQ-series sensor response across a 10-bit ADC
# with 5V reference.  PM values model PMS-series particulate sensors.
# -----------------------------------------------------------------------

SCENARIOS: Dict[str, Dict[str, Any]] = {
    "CLEAN_OR_BACKGROUND": {
        "description": "Baseline ambient with low PM and gas response",
        "n_samples": 300,
        "features": {
            "mq2_v":  {"mean": 0.9,  "std": 0.20},
            "mq9_v":  {"mean": 0.7,  "std": 0.15},
            "mq135_v": {"mean": 0.8, "std": 0.18},
            "temp_c":  {"mean": 28.0, "std": 4.0},
            "hum_pct": {"mean": 60.0, "std": 12.0},
            "pm1_0":   {"mean": 8.0,  "std": 4.0},
            "pm2_5":   {"mean": 18.0, "std": 8.0},
            "pm10":    {"mean": 30.0, "std": 12.0},
        },
    },
    "TRAFFIC": {
        "description": "Vehicle emissions: elevated CO (MQ9), moderate PM with fine enrichment",
        "n_samples": 250,
        "features": {
            "mq2_v":  {"mean": 1.4,  "std": 0.30},
            "mq9_v":  {"mean": 1.8,  "std": 0.35},  # CO-sensitive → higher
            "mq135_v": {"mean": 1.6, "std": 0.28},
            "temp_c":  {"mean": 33.0, "std": 4.0},
            "hum_pct": {"mean": 50.0, "std": 12.0},
            "pm1_0":   {"mean": 20.0, "std": 10.0},
            "pm2_5":   {"mean": 50.0, "std": 20.0},
            "pm10":    {"mean": 80.0, "std": 25.0},
        },
    },
    "HEAVY_DUST": {
        "description": "Resuspended dust: very high PM10/PM2.5 ratio, low MQ response",
        "n_samples": 200,
        "features": {
            "mq2_v":  {"mean": 1.0,  "std": 0.22},
            "mq9_v":  {"mean": 0.8,  "std": 0.18},
            "mq135_v": {"mean": 0.9, "std": 0.20},
            "temp_c":  {"mean": 35.0, "std": 3.5},
            "hum_pct": {"mean": 38.0, "std": 10.0},
            "pm1_0":   {"mean": 15.0, "std": 8.0},
            "pm2_5":   {"mean": 45.0, "std": 18.0},
            "pm10":    {"mean": 180.0, "std": 60.0},  # Very high coarse fraction
        },
    },
    "CONSTRUCTION_ACTIVITY": {
        "description": "Construction: high PM10, moderate MQ9 from diesel equipment",
        "n_samples": 200,
        "features": {
            "mq2_v":  {"mean": 1.1,  "std": 0.25},
            "mq9_v":  {"mean": 1.3,  "std": 0.30},  # Diesel exhaust
            "mq135_v": {"mean": 1.2, "std": 0.25},
            "temp_c":  {"mean": 34.0, "std": 3.0},
            "hum_pct": {"mean": 42.0, "std": 10.0},
            "pm1_0":   {"mean": 22.0, "std": 10.0},
            "pm2_5":   {"mean": 65.0, "std": 25.0},
            "pm10":    {"mean": 200.0, "std": 70.0},
        },
    },
    "BIOMASS_OR_WASTE_BURNING": {
        "description": "Burning: very high MQ2 (smoke), high PM1.0 enrichment",
        "n_samples": 250,
        "features": {
            "mq2_v":  {"mean": 2.8,  "std": 0.50},  # Smoke-dominant
            "mq9_v":  {"mean": 2.0,  "std": 0.40},
            "mq135_v": {"mean": 2.5, "std": 0.45},
            "temp_c":  {"mean": 35.0, "std": 5.0},
            "hum_pct": {"mean": 45.0, "std": 12.0},
            "pm1_0":   {"mean": 60.0, "std": 25.0},  # Fine particle enrichment
            "pm2_5":   {"mean": 120.0, "std": 45.0},
            "pm10":    {"mean": 150.0, "std": 50.0},
        },
    },
    "INDUSTRIAL_OR_GENERATOR_EMISSIONS": {
        "description": "Industrial/generators: high MQ9 and MQ135, moderate PM",
        "n_samples": 200,
        "features": {
            "mq2_v":  {"mean": 1.8,  "std": 0.35},
            "mq9_v":  {"mean": 2.5,  "std": 0.45},  # CO/combustible
            "mq135_v": {"mean": 2.3, "std": 0.40},  # NH3/NOx
            "temp_c":  {"mean": 33.0, "std": 4.0},
            "hum_pct": {"mean": 48.0, "std": 11.0},
            "pm1_0":   {"mean": 25.0, "std": 12.0},
            "pm2_5":   {"mean": 55.0, "std": 22.0},
            "pm10":    {"mean": 85.0, "std": 30.0},
        },
    },
    "COOKING_OR_FUEL_COMBUSTION": {
        "description": "Cooking: high MQ2 (smoke), elevated PM1.0, moderate MQ9",
        "n_samples": 200,
        "features": {
            "mq2_v":  {"mean": 2.2,  "std": 0.45},  # Smoke
            "mq9_v":  {"mean": 1.5,  "std": 0.30},
            "mq135_v": {"mean": 1.8, "std": 0.35},
            "temp_c":  {"mean": 30.0, "std": 3.0},
            "hum_pct": {"mean": 55.0, "std": 10.0},
            "pm1_0":   {"mean": 40.0, "std": 18.0},
            "pm2_5":   {"mean": 80.0, "std": 30.0},
            "pm10":    {"mean": 95.0, "std": 32.0},
        },
    },
    "INDOOR_ACTIVITY": {
        "description": "Indoor: moderate PM, low MQ, stable temperature",
        "n_samples": 200,
        "features": {
            "mq2_v":  {"mean": 1.0,  "std": 0.20},
            "mq9_v":  {"mean": 0.85, "std": 0.18},
            "mq135_v": {"mean": 1.1, "std": 0.22},  # Slightly elevated (VOCs)
            "temp_c":  {"mean": 26.0, "std": 2.0},   # More stable
            "hum_pct": {"mean": 55.0, "std": 8.0},
            "pm1_0":   {"mean": 12.0, "std": 5.0},
            "pm2_5":   {"mean": 28.0, "std": 10.0},
            "pm10":    {"mean": 38.0, "std": 12.0},
        },
    },
}


def generate_synthetic_dataset(seed: int = 42) -> pd.DataFrame:
    """
    Generate synthetic training data from scenario definitions.

    Returns a DataFrame with all raw + derived features and a 'label' column.
    """
    np.random.seed(seed)
    all_rows: List[Dict[str, Any]] = []

    for label, scenario in SCENARIOS.items():
        n = scenario["n_samples"]
        feats = scenario["features"]

        for _ in range(n):
            row: Dict[str, Any] = {"label": label}

            for feat_name, params in feats.items():
                val = np.random.normal(params["mean"], params["std"])
                # Clip to physical bounds
                if feat_name in ("mq2_v", "mq9_v", "mq135_v"):
                    val = np.clip(val, 0.0, 5.0)
                elif feat_name == "temp_c":
                    val = np.clip(val, -40.0, 85.0)
                elif feat_name == "hum_pct":
                    val = np.clip(val, 0.0, 100.0)
                elif feat_name.startswith("pm"):
                    val = max(val, 0.0)
                row[feat_name] = round(float(val), 4)

            # Ensure PM hierarchy: PM1.0 <= PM2.5 <= PM10
            row["pm1_0"] = min(row["pm1_0"], row["pm2_5"])
            row["pm2_5"] = min(row["pm2_5"], row["pm10"])

            # Compute derived features
            pm10 = row["pm10"]
            pm25 = row["pm2_5"]
            pm1 = row["pm1_0"]
            mq2 = row["mq2_v"]
            mq9 = row["mq9_v"]
            mq135 = row["mq135_v"]

            row["pm_coarse_ratio"] = round(pm10 / pm25, 4) if pm25 > 0.1 else 0.0
            row["pm_fine_ratio"] = round(pm25 / pm1, 4) if pm1 > 0.1 else 0.0
            row["mq_mean_v"] = round((mq2 + mq9 + mq135) / 3, 4)
            row["mq_max_v"] = round(max(mq2, mq9, mq135), 4)
            row["mq2_mq9_ratio"] = round(mq2 / mq9, 4) if mq9 > 0.01 else 0.0
            row["mq135_mq2_ratio"] = round(mq135 / mq2, 4) if mq2 > 0.01 else 0.0

            all_rows.append(row)

    df = pd.DataFrame(all_rows)
    logger.info(
        "Generated %d synthetic samples across %d categories",
        len(df),
        df["label"].nunique(),
    )
    return df


def compute_reference_statistics(df: pd.DataFrame) -> Dict[str, Dict[str, Dict[str, float]]]:
    """
    Compute per-class feature distributions using robust statistics.

    For each (class, feature) pair, computes:
      - median, MAD (median absolute deviation)
      - q25, q75 (interquartile range)
      - min, max, count
    """
    feature_cols = [c for c in df.columns if c != "label"]
    stats: Dict[str, Dict[str, Dict[str, float]]] = {}

    for label in df["label"].unique():
        class_df = df[df["label"] == label]
        class_stats: Dict[str, Dict[str, float]] = {}

        for feat in feature_cols:
            values = class_df[feat].dropna().values
            if len(values) == 0:
                continue

            median = float(np.median(values))
            mad = float(np.median(np.abs(values - median)))

            class_stats[feat] = {
                "median": round(median, 4),
                "mad": round(mad, 4),
                "q25": round(float(np.percentile(values, 25)), 4),
                "q75": round(float(np.percentile(values, 75)), 4),
                "min": round(float(np.min(values)), 4),
                "max": round(float(np.max(values)), 4),
                "count": int(len(values)),
            }

        stats[label] = class_stats

    return stats


def train_decision_tree(
    df: pd.DataFrame,
    feature_cols: List[str],
    test_size: float = 0.2,
    random_state: int = 42,
) -> Tuple[Any, Any, Dict[str, Any]]:
    """
    Train a DecisionTreeClassifier on the synthetic dataset.

    Returns (model, scaler, evaluation_metrics).
    """
    from sklearn.tree import DecisionTreeClassifier
    from sklearn.preprocessing import StandardScaler, LabelEncoder
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import (
        classification_report,
        confusion_matrix,
        accuracy_score,
    )

    X = df[feature_cols].values.astype(np.float32)
    y = df["label"].values

    # Split — stratified to preserve class proportions
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=random_state, stratify=y
    )

    # Fit scaler on training data only
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # Train Decision Tree — keep shallow for explainability and edge deployment
    dt = DecisionTreeClassifier(
        max_depth=8,
        min_samples_split=10,
        min_samples_leaf=5,
        class_weight="balanced",  # Handle class imbalance
        random_state=random_state,
    )
    dt.fit(X_train_scaled, y_train)

    # Evaluate
    y_pred = dt.predict(X_test_scaled)
    accuracy = float(accuracy_score(y_test, y_pred))
    report = classification_report(y_test, y_pred, output_dict=True)
    cm = confusion_matrix(y_test, y_pred, labels=dt.classes_)

    logger.info("Decision Tree accuracy: %.4f", accuracy)
    logger.info(
        "Classification report:\n%s",
        classification_report(y_test, y_pred),
    )

    evaluation = {
        "accuracy": accuracy,
        "classification_report": report,
        "confusion_matrix": cm.tolist(),
        "n_train": len(X_train),
        "n_test": len(X_test),
        "classes": list(dt.classes_),
        "tree_depth": dt.get_depth(),
        "n_leaves": dt.get_n_leaves(),
    }

    return dt, scaler, evaluation


def save_artifacts(
    output_dir: Path,
    model: Any,
    scaler: Any,
    class_names: List[str],
    feature_names: List[str],
    reference_stats: Dict[str, Dict[str, Dict[str, float]]],
    evaluation: Dict[str, Any],
    config_values: Dict[str, Any],
) -> None:
    """Save all classifier artifacts to disk."""
    import joblib

    output_dir.mkdir(parents=True, exist_ok=True)

    # Save model bundle
    model_bundle = {
        "model": model,
        "scaler": scaler,
        "class_names": class_names,
        "feature_names": feature_names,
    }
    model_path = output_dir / "source_classifier_model.pkl"
    joblib.dump(model_bundle, model_path)
    logger.info("Saved model to %s", model_path)

    # Save reference statistics
    stats_path = output_dir / "source_classifier_stats.json"
    with open(stats_path, "w") as f:
        json.dump(reference_stats, f, indent=2)
    logger.info("Saved reference stats to %s", stats_path)

    # Save metadata
    metadata = {
        "version": "0.1.0-synthetic",
        "created_at": datetime.utcnow().isoformat(),
        "model_type": "DecisionTreeClassifier",
        "training_data": "SYNTHETIC — not validated against real-world sources",
        "classes": class_names,
        "features": feature_names,
        "evaluation": {
            "accuracy": float(evaluation["accuracy"]),
            "tree_depth": int(evaluation["tree_depth"]),
            "n_leaves": int(evaluation["n_leaves"]),
            "n_train": int(evaluation["n_train"]),
            "n_test": int(evaluation["n_test"]),
        },
        "per_class_metrics": {
            cls: {
                "precision": evaluation["classification_report"].get(cls, {}).get("precision"),
                "recall": evaluation["classification_report"].get(cls, {}).get("recall"),
                "f1_score": evaluation["classification_report"].get(cls, {}).get("f1-score"),
                "support": evaluation["classification_report"].get(cls, {}).get("support"),
            }
            for cls in class_names
        },
        "config": config_values,
        "warnings": [
            "Trained on synthetic data only",
            "Source classifications are hypotheses, not confirmed identities",
            "MQ-series sensors cannot uniquely identify gases",
            "Requires validation with labelled field data",
        ],
    }
    metadata_path = output_dir / "source_classifier_metadata.json"
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)
    logger.info("Saved metadata to %s", metadata_path)


def main(output_dir: Path) -> None:
    """Run the full training pipeline."""
    from app.source_classifier.categories import (
        ALL_SOURCE_CLASSIFIER_FEATURES,
        SourceClassifierConfig,
    )

    config = SourceClassifierConfig()

    logger.info("=" * 60)
    logger.info("Phase 3 Source Classifier — Training Pipeline")
    logger.info("=" * 60)

    # Step 1: Generate synthetic data
    logger.info("\nStep 1: Generating synthetic training data...")
    df = generate_synthetic_dataset()

    # Step 2: Compute reference statistics (on full dataset — no leakage
    # since these are simple per-class descriptive statistics, not model params)
    logger.info("\nStep 2: Computing per-class reference statistics...")
    feature_cols = [c for c in df.columns if c != "label"]
    reference_stats = compute_reference_statistics(df)

    # Step 3: Train Decision Tree
    logger.info("\nStep 3: Training DecisionTreeClassifier...")
    model, scaler, evaluation = train_decision_tree(df, feature_cols)

    # Step 4: Save artifacts
    logger.info("\nStep 4: Saving artifacts to %s...", output_dir)
    config_dict = {
        k: v
        for k, v in vars(config).items()
        if not k.startswith("_")
    }
    save_artifacts(
        output_dir=output_dir,
        model=model,
        scaler=scaler,
        class_names=list(evaluation["classes"]),
        feature_names=feature_cols,
        reference_stats=reference_stats,
        evaluation=evaluation,
        config_values=config_dict,
    )

    logger.info("\n" + "=" * 60)
    logger.info("Training complete!")
    logger.info("  Model accuracy: %.4f", evaluation["accuracy"])
    logger.info("  Tree depth: %d", evaluation["tree_depth"])
    logger.info("  Leaves: %d", evaluation["n_leaves"])
    logger.info("  Classes: %s", evaluation["classes"])
    logger.info("  WARNING: Trained on SYNTHETIC data — not field-validated")
    logger.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Train the Phase 3 Source Classifier"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).parent.parent.parent / "artifacts",
        help="Directory to save model artifacts",
    )
    args = parser.parse_args()
    main(args.output_dir)
