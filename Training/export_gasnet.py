import os
import sys
import json
import joblib
import numpy as np
import time
from datetime import datetime
import shutil

try:
    import torch
except ImportError:
    print("PyTorch is required to run the export script.")
    sys.exit(1)

def find_files():
    search_paths = [
        "Training/models/",
        "Intelligence/Server/artifacts/"
    ]
    
    pt_path = None
    pkl_path = None
    
    for path in search_paths:
        if pt_path is None and os.path.exists(os.path.join(path, "gasnet.pt")):
            pt_path = os.path.join(path, "gasnet.pt")
        if pkl_path is None and os.path.exists(os.path.join(path, "preprocess.pkl")):
            pkl_path = os.path.join(path, "preprocess.pkl")
            
    return pt_path, pkl_path

def main():
    pt_path, pkl_path = find_files()
    if not pt_path or not pkl_path:
        print("Could not find gasnet.pt or preprocess.pkl")
        sys.exit(1)
        
    print(f"Loading weights from {pt_path}")
    state_dict = torch.load(pt_path, map_location='cpu')
    
    print(f"Loading preprocessing from {pkl_path}")
    bundle = joblib.load(pkl_path)
    
    scaler = bundle['scaler']
    le = bundle['label_encoder']
    t_cal = bundle.get('temperature', 1.0)
    
    # Extract weights to numpy
    weights = {}
    for key, tensor in state_dict.items():
        weights[key] = tensor.numpy()
        
    # Create directories
    os.makedirs("Training/models", exist_ok=True)
    os.makedirs("Intelligence/Server/models", exist_ok=True)
    os.makedirs("Intelligence/Server/artifacts", exist_ok=True)
    
    npz_path = "Training/models/gasnet_weights.npz"
    meta_path = "Training/models/model_metadata.json"
    
    print(f"Saving weights to {npz_path}")
    np.savez_compressed(npz_path, **weights)
    
    metadata = {
        "model_version": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "architecture": {
            "n_features": 5,
            "hidden1": 32,
            "hidden2": 16,
            "n_classes": len(le.classes_),
            "p_drop": 0.1
        },
        "feature_order": ['MQ2_V', 'MQ9_V', 'MQ135_V', 'temperature_C', 'humidity_pct'],
        "class_labels": le.classes_.tolist(),
        "calibration_temperature": float(t_cal),
        "preprocessing": {
            "scaler_mean": scaler.mean_.tolist(),
            "scaler_scale": scaler.scale_.tolist()
        },
        "expected_input_ranges": {
            "MQ2_V": [0.0, 5.0],
            "MQ9_V": [0.0, 5.0],
            "MQ135_V": [0.0, 5.0],
            "temperature_C": [-20.0, 80.0],
            "humidity_pct": [0.0, 100.0]
        },
        "export_timestamp": datetime.now().isoformat(),
        "source_weights_file": pt_path
    }
    
    print(f"Saving metadata to {meta_path}")
    with open(meta_path, 'w') as f:
        json.dump(metadata, f, indent=2)
        
    # Copy to artifacts
    shutil.copy2(npz_path, "Intelligence/Server/artifacts/gasnet_weights.npz")
    shutil.copy2(meta_path, "Intelligence/Server/artifacts/model_metadata.json")
    
    # Copy to models
    shutil.copy2(npz_path, "Intelligence/Server/models/gasnet_weights.npz")
    shutil.copy2(meta_path, "Intelligence/Server/models/model_metadata.json")
    
    print("Export completed successfully.")

if __name__ == "__main__":
    main()
