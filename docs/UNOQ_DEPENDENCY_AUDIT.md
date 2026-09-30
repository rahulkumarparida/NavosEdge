# NavosEdge — UNO Q Dependency Audit

**Target:** Arduino UNO Q (ARM Cortex-A53, 2 GB RAM, 16 GB eMMC, Debian Linux)  
**Date:** September 2026

---

## Summary

| Category | Package | Runtime on UNO Q? | Verdict |
|:---|:---|:---|:---|
| **ML Framework** | `torch>=2.0.0` | **NO** | Replace with NumPy backend |
| **ML Utility** | `numpy>=1.24.0` | YES | Required (~30 MB) |
| **ML Utility** | `joblib>=1.3.0` | YES | Required for model loading |
| **ML Utility** | `scikit-learn>=1.3.0` | YES (lightweight) | Used by source classifier |
| **Data** | `pandas>=2.0.0` | Training only | **NOT** required on UNO Q |
| **Web** | `fastapi>=0.115.0` | YES | Core server framework |
| **Web** | `uvicorn[standard]>=0.30.0` | YES | ASGI server |
| **Web** | `pydantic>=2.9.0` | YES | Schema validation |
| **Web** | `pydantic-settings>=2.5.0` | YES | Configuration management |
| **SSE** | `sse-starlette>=2.0.0` | YES | Server-Sent Events |
| **Testing** | `pytest>=8.0.0` | Dev only | **NOT** required on UNO Q |
| **Testing** | `pytest-asyncio>=0.24.0` | Dev only | **NOT** required on UNO Q |
| **Testing** | `httpx>=0.27.0` | Dev only | **NOT** required on UNO Q |

---

## Detailed Audit

### 1. `torch` (PyTorch)

| Attribute | Detail |
|:---|:---|
| **Where imported** | `Intelligence/Server/app/services/inference.py` (lines 21-23) |
| **Also used in** | `Training/mq_train.py`, `Training/mq_infer.py` (training scripts) |
| **What for** | Defines and runs `TinyGasNet` — a 5→32→16→[8,1] MLP for gas classification and safety detection |
| **Runtime required?** | Currently yes, but **replaceable** |
| **Training only?** | Training scripts absolutely require torch. Server inference can use NumPy backend |
| **Suitable for UNO Q?** | **NO** — 1.2-1.8 GB install, >200 MB RAM idle |
| **Replacement** | Pure NumPy inference backend (`numpy_inference.py`) |
| **Resource impact** | Removing saves ~1.5 GB storage, ~250 MB RAM |
| **Decision** | **REPLACE with NumPy inference on UNO Q** |

**Technical detail:** The model has only 873 parameters (3.5 KB of weights). The forward pass is two matrix multiplications with ReLU + dropout, softmax, and sigmoid — all trivially implementable in NumPy.

### 2. `numpy`

| Attribute | Detail |
|:---|:---|
| **Where imported** | `inference.py`, `anomaly/baseline.py`, `anomaly/residuals.py`, `source_classifier/classifier.py` |
| **What for** | Array operations, linear algebra (OLS), feature scaling, MC-Dropout aggregation |
| **Runtime required?** | YES |
| **Suitable for UNO Q?** | YES — ~30 MB, ARM64 wheels available |
| **Decision** | **KEEP** |

### 3. `joblib`

| Attribute | Detail |
|:---|:---|
| **Where imported** | `inference.py` (line 25), `source_classifier/classifier.py` (line 37) |
| **What for** | Loading serialized model artifacts (`preprocess.pkl`, `source_classifier_model.pkl`) |
| **Runtime required?** | YES |
| **Suitable for UNO Q?** | YES — lightweight, pure Python with optional C acceleration |
| **Decision** | **KEEP** |

### 4. `scikit-learn`

| Attribute | Detail |
|:---|:---|
| **Where imported** | `source_classifier/classifier.py` (via joblib bundle containing `DecisionTreeClassifier`) |
| **Also used in** | `source_classifier/train.py` (training only), `Training/mq_train.py` (training only: `StandardScaler`, `LabelEncoder`) |
| **What for** | Source classifier uses `predict_proba()` on a loaded `DecisionTreeClassifier`. Preprocessing uses `StandardScaler.transform()` |
| **Runtime required?** | YES — needed to unpickle and call sklearn models |
| **Suitable for UNO Q?** | YES with caveats — ~80 MB install, ARM64 wheels available via apt or pip |
| **Decision** | **KEEP** (required for source classifier and scaler deserialization) |

### 5. `pandas`

| Attribute | Detail |
|:---|:---|
| **Where imported** | `Training/mq_train.py` (line 8), `source_classifier/train.py` (line 27) |
| **What for** | CSV loading during training only |
| **Runtime required?** | **NO** — never imported at server runtime |
| **Suitable for UNO Q?** | Unnecessary (~100 MB) |
| **Decision** | **EXCLUDE from UNO Q requirements** |

### 6. `fastapi`

| Attribute | Detail |
|:---|:---|
| **Where imported** | `app/main.py`, `app/api/routes/*.py`, `app/aqi/router.py` |
| **What for** | HTTP API framework for the Intelligence Server |
| **Runtime required?** | YES |
| **Suitable for UNO Q?** | YES — lightweight, pure Python |
| **Decision** | **KEEP** |

### 7. `uvicorn[standard]`

| Attribute | Detail |
|:---|:---|
| **Where imported** | Server startup command |
| **What for** | ASGI server to run FastAPI |
| **Runtime required?** | YES |
| **Suitable for UNO Q?** | YES |
| **Decision** | **KEEP** |

### 8. `pydantic` / `pydantic-settings`

| Attribute | Detail |
|:---|:---|
| **Where imported** | All schema files, `app/core/config.py` |
| **What for** | Data validation, configuration management |
| **Runtime required?** | YES |
| **Suitable for UNO Q?** | YES |
| **Decision** | **KEEP** |

### 9. `sse-starlette`

| Attribute | Detail |
|:---|:---|
| **Where imported** | `app/api/routes/hardware.py`, `app/services/events.py` |
| **What for** | Server-Sent Events for real-time hardware communication |
| **Runtime required?** | YES |
| **Suitable for UNO Q?** | YES — lightweight |
| **Decision** | **KEEP** |

### 10. `pytest` / `pytest-asyncio` / `httpx`

| Attribute | Detail |
|:---|:---|
| **Where imported** | Test files only |
| **What for** | Unit and integration testing |
| **Runtime required?** | **NO** |
| **Decision** | **Development only — exclude from UNO Q** |

---

## Dependencies NOT Found

The following were explicitly searched for and **NOT found** anywhere in the codebase:

| Package | Status |
|:---|:---|
| `torchvision` | Not used |
| `tensorflow` / `tensorflow-lite` | Not used |
| `onnx` / `onnxruntime` | Not used |
| `scipy` | Not used |
| `matplotlib` | Not used |
| `cv2` (OpenCV) | Not used |
| `requests` | Not used (C++ uses libcurl) |
| `flask` | Not used |
| `aiohttp` | Not used |
| `redis` | Not used |
| `celery` | Not used |
| `PostgreSQL` / `MySQL` drivers | Not used |
| `boto3` / cloud SDKs | Not used |
| `CUDA` / `cuDNN` | Not used at runtime |

---

## C++ Dependencies (Hardware Bridge)

| Dependency | Source | Suitable for UNO Q? |
|:---|:---|:---|
| `libcurl` | System package (`libcurl4-openssl-dev`) | YES — available via apt |
| `nlohmann/json` | Bundled in `Hardware/third_party/` | YES — header-only |
| `CMake` | Build tool | YES — available via apt |
| `g++` (C++17) | Compiler | YES — available via apt |

---

## Final UNO Q Dependency Footprint

| Component | Estimated Size |
|:---|:---|
| Python 3.11+ | ~50 MB |
| numpy | ~30 MB |
| scikit-learn | ~80 MB |
| joblib | ~2 MB |
| fastapi + uvicorn + pydantic | ~25 MB |
| sse-starlette | ~1 MB |
| Model artifacts | ~50 KB |
| Application code | ~500 KB |
| **Total** | **~190 MB** |

Compared to **~1.7 GB** with PyTorch included — a **~90% reduction**.
