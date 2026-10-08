"""
Pytest configuration for NavosEdge Manager test suites.
Ensures repository root and Manager directories are in sys.path.
"""

import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent.parent
manager_dir = repo_root / "Manager"

for p in [str(manager_dir), str(repo_root)]:
    if p not in sys.path:
        sys.path.insert(0, p)
