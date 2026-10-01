#!/usr/bin/env python3
"""
Export script for TinyGasNet model weights & metadata (PyTorch-Free / Pure NumPy).

Copies and validates gasnet_weights.npz, model_metadata.json, and preprocess.pkl
between Training/models and Intelligence/Server/artifacts without requiring PyTorch.
"""

import os
import sys
import json
import joblib
import numpy as np
import shutil
from datetime import datetime

def find_files():
    search_paths = [
        "Training/models/",
        "Intelligence/Server/artifacts/",
        "Intelligence/Server/models/"
    ]
    
    npz_path = None
    meta_path = None
    pkl_path = None
    
    for path in search_paths:
        if npz_path is None and os.path.exists(os.path.join(path, "gasnet_weights.npz")):
            npz_path = os.path.join(path, "gasnet_weights.npz")
        if meta_path is None and os.path.exists(os.path.join(path, "model_metadata.json")):
            meta_path = os.path.join(path, "model_metadata.json")
        if pkl_path is None and os.path.exists(os.path.join(path, "preprocess.pkl")):
            pkl_path = os.path.join(path, "preprocess.pkl")
            
    return npz_path, meta_path, pkl_path

def main():
    npz_path, meta_path, pkl_path = find_files()
    if not npz_path or not meta_path:
        print("Could not find gasnet_weights.npz or model_metadata.json")
        sys.exit(1)
        
    print(f"Validating NumPy weights from {npz_path}")
    weights = np.load(npz_path)
    
    print(f"Validating metadata from {meta_path}")
    with open(meta_path) as f:
        meta = json.load(f)
        
    # Create directories
    os.makedirs("Training/models", exist_ok=True)
    os.makedirs("Intelligence/Server/models", exist_ok=True)
    os.makedirs("Intelligence/Server/artifacts", exist_ok=True)
    
    dest_npz = "Training/models/gasnet_weights.npz"
    dest_meta = "Training/models/model_metadata.json"
    
    print(f"Deploying artifacts...")
    shutil.copy2(npz_path, "Intelligence/Server/artifacts/gasnet_weights.npz")
    shutil.copy2(meta_path, "Intelligence/Server/artifacts/model_metadata.json")
    shutil.copy2(npz_path, "Intelligence/Server/models/gasnet_weights.npz")
    shutil.copy2(meta_path, "Intelligence/Server/models/model_metadata.json")
    if pkl_path and os.path.exists(pkl_path):
        shutil.copy2(pkl_path, "Intelligence/Server/artifacts/preprocess.pkl")
        shutil.copy2(pkl_path, "Training/models/preprocess.pkl")
    
    print("PyTorch-Free export completed successfully.")

if __name__ == "__main__":
    main()
