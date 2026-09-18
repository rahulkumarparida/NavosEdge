"""
Tiny client for mq_service. Import this everywhere you need a prediction.

    from mq_client import classify
    classify(1.10, 2.80, 0.95)
    # -> {'class': 'CO', 'confidence': 0.992, 'safety': 'UNSAFE'}
"""

import json
import socket

SOCK_PATH = "/tmp/mq_service.sock"

def classify(mq2, mq9, mq135, t=25.0, h=45.0):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.connect(SOCK_PATH)
        s.sendall(json.dumps({
            "mq2": float(mq2), "mq9": float(mq9), "mq135": float(mq135),
            "t":   float(t),   "h":   float(h),
        }).encode())
        return json.loads(s.recv(1024))