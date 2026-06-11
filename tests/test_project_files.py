from __future__ import annotations

def test_backend_main_exists(repo_root):
    assert (repo_root / "backend/app/main.py").exists()

def test_recommender_exists(repo_root):
    assert (repo_root / "backend/app/ml/recommender.py").exists()

def test_train_script_exists(repo_root):
    assert (repo_root / "scripts/train_and_serve_movielens.py").exists()

def test_script_wrapper_exists(repo_root):
    assert (repo_root / "scripts/nextwatch.sh").exists()
