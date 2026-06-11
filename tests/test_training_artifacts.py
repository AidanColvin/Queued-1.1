from __future__ import annotations

def test_training_dir_exists(training_dir):
    assert training_dir.exists()

def test_model_file_exists(training_dir):
    assert (training_dir / "svd_model.joblib").exists()

def test_movies_catalog_exists(training_dir):
    assert (training_dir / "movies_catalog.csv").exists()

def test_ratings_catalog_exists(training_dir):
    assert (training_dir / "ratings_catalog.csv").exists()

def test_summary_exists(training_dir):
    assert (training_dir / "serve_model_summary.json").exists()

def test_summary_has_expected_keys(model_summary):
    for key in ["dataset", "n_ratings", "n_movies", "n_users", "model_file"]:
        assert key in model_summary

def test_summary_counts_positive(model_summary):
    assert model_summary["n_ratings"] > 0
    assert model_summary["n_movies"] > 0
    assert model_summary["n_users"] > 0

def test_model_path_matches_summary(model_summary, training_dir):
    assert (training_dir.parent / model_summary["model_file"]).exists()
