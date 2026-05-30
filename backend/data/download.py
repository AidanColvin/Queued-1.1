"""Download the raw public datasets for the REAL pipeline.

Pulls MovieLens 25M and the IMDb ``title.basics`` dump into ``data/raw/``. TMDB
metadata is fetched later, per-movie, in :mod:`data.preprocess` (it needs the
filtered movie list first). Requires the training dependencies:

    pip install -r requirements-train.txt
    python -m data.download

Everything here is idempotent: existing files are skipped.
"""

from __future__ import annotations

import gzip
import shutil
import tarfile
import zipfile
from pathlib import Path

import requests
from tqdm import tqdm

RAW_DIR = Path(__file__).resolve().parent / "raw"
MOVIELENS_URL = "https://files.grouplens.org/datasets/movielens/ml-25m.zip"
IMDB_BASICS_URL = "https://datasets.imdbws.com/title.basics.tsv.gz"
CMU_URL = "http://www.cs.cmu.edu/~ark/personas/data/MovieSummaries.tar.gz"

_CHUNK = 1 << 20  # 1 MiB


def _stream_download(url: str, dest: Path) -> Path:
    """Stream ``url`` to ``dest`` with a progress bar; skip if already present.

    Args:
        url: Source URL.
        dest: Destination file path.

    Returns:
        The destination path.
    """
    if dest.exists():
        print(f"✓ {dest.name} already present, skipping")
        return dest

    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=60) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        with open(dest, "wb") as fh, tqdm(
            total=total, unit="B", unit_scale=True, desc=dest.name
        ) as bar:
            for chunk in resp.iter_content(chunk_size=_CHUNK):
                fh.write(chunk)
                bar.update(len(chunk))
    return dest


def download_movielens(raw_dir: Path = RAW_DIR) -> Path:
    """Download and extract MovieLens 25M.

    Args:
        raw_dir: Directory to download into.

    Returns:
        Path to the extracted ``ml-25m`` directory.
    """
    extracted = raw_dir / "ml-25m"
    if extracted.exists():
        print(f"✓ {extracted} already extracted, skipping")
        return extracted

    archive = _stream_download(MOVIELENS_URL, raw_dir / "ml-25m.zip")
    print("Extracting MovieLens 25M...")
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(raw_dir)
    return extracted


def download_imdb_basics(raw_dir: Path = RAW_DIR) -> Path:
    """Download and decompress IMDb ``title.basics`` (canonical titles/years).

    Args:
        raw_dir: Directory to download into.

    Returns:
        Path to the decompressed TSV.
    """
    tsv = raw_dir / "title.basics.tsv"
    if tsv.exists():
        print(f"✓ {tsv.name} already present, skipping")
        return tsv

    gz = _stream_download(IMDB_BASICS_URL, raw_dir / "title.basics.tsv.gz")
    print("Decompressing IMDb basics...")
    with gzip.open(gz, "rb") as src, open(tsv, "wb") as dst:
        shutil.copyfileobj(src, dst)
    return tsv


def download_cmu(raw_dir: Path = RAW_DIR) -> Path:
    """Download and extract the CMU Movie Summary Corpus (42K plot summaries).

    Provides the richest free plot text for the semantic embedding layer — no
    API key required.

    Args:
        raw_dir: Directory to download into.

    Returns:
        Path to the extracted ``MovieSummaries`` directory.
    """
    extracted = raw_dir / "MovieSummaries"
    if extracted.exists():
        print(f"✓ {extracted} already extracted, skipping")
        return extracted

    archive = _stream_download(CMU_URL, raw_dir / "MovieSummaries.tar.gz")
    print("Extracting CMU Movie Summary Corpus...")
    with tarfile.open(archive) as tf:
        tf.extractall(raw_dir)  # noqa: S202 — trusted academic source
    return extracted


def main() -> None:
    """Download every raw dataset needed by the real pipeline."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    download_movielens()
    download_imdb_basics()
    download_cmu()
    print(f"\nDone. Raw data in {RAW_DIR}\nNext: python -m data.preprocess")


if __name__ == "__main__":
    main()
