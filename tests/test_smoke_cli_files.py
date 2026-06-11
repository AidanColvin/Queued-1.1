from __future__ import annotations
import os

def test_scripts_are_executable(repo_root):
    scripts = [
        "scripts/nextwatch.sh",
        "scripts/train.sh",
        "scripts/test_backend.sh",
        "scripts/test_recommendations.sh",
    ]
    for rel in scripts:
        p = repo_root / rel
        assert p.exists()
        assert os.access(p, os.X_OK)
