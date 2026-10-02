# Phase 3: Source Classification

## Overview
The Source Classification module adds explainable, multi-class pattern matching to NavosEdge. It uses a Decision Tree alongside feature-range similarity scores to compare incoming sensor data against broad environmental source hypotheses.

## Features
- **Categories**: `CLEAN_OR_BACKGROUND`, `TRAFFIC`, `HEAVY_DUST`, `CONSTRUCTION_ACTIVITY`, `BIOMASS_OR_WASTE_BURNING`, `INDUSTRIAL_OR_GENERATOR_EMISSIONS`, `COOKING_OR_FUEL_COMBUSTION`, `INDOOR_ACTIVITY`, `MIXED_POLLUTION`, `UNKNOWN`.
- **Hybrid Scoring**: Combines Decision Tree probabilities (if trained) with IQR-based similarity scoring (which operates without a trained model, provided reference statistics are available).
- **Graceful Fallback**: If no artifacts are present, it safely returns `UNKNOWN` without breaking the pipeline.

## Implementation Details
1. **Schema & Config**: Extracted features (raw and derived ratios) mapped against predefined `SourceCategory`. Configurations include `tolerance_fraction` (±10%) to expand bounds, avoiding hardcoded zero-thresholds.
2. **Model Training (`train.py`)**: Generates synthetic urban Indian scenarios and trains a shallow `DecisionTreeClassifier` for explainability, exporting `gasnet.pt` (legacy/if applicable) and a `.pkl` for Phase 3.
3. **Processing Pipeline Integration**: Fits directly into `ModularPipeline` and `ProcessingService`. Source hypotheses are stored alongside readings and included in SSE events.
4. **Data Quality**: Flags degraded measurements (stale, missing features) before scoring.
5. **Uncertainty**: Distinguishes between pattern match similarity (`match_score`) and calibrated model probability (`confidence`). Flags low-gap or mixed pollution scenarios.

## Usage
Train the synthetic model (from `Intelligence/Server`):
```bash
python -m app.source_classifier.train --output-dir ./artifacts
```

Run tests:
```bash
pytest tests/test_source_classifier.py
```
