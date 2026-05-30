"""Semantic signal: dense embeddings of plot overviews.

Two interchangeable backends produce **L2-normalized vectors of the same
dimension** (384, matching ``all-MiniLM-L6-v2``), so an artifact bundle works
the same regardless of which built it:

* :class:`SentenceTransformerEmbedder` — the real model (``sentence-transformers``),
  lazily imported so it is needed only by the training pipeline.
* :class:`HashingEmbedder` — a deterministic, dependency-free feature-hashing
  embedder used by the sample pipeline and as a graceful fallback.

At inference, semantic similarity is the cosine between the seed centroid and
every catalog row.
"""

from __future__ import annotations

import hashlib
import re
from typing import Protocol

import numpy as np

EMBED_DIM = 384
_TOKEN_RE = re.compile(r"[a-z0-9]+")


class Embedder(Protocol):
    """Anything that maps a list of texts to a ``(n, dim)`` float array."""

    dim: int

    def encode(self, texts: list[str]) -> np.ndarray:
        """Return L2-normalized embeddings for ``texts``."""
        ...


def _l2_normalize(matrix: np.ndarray) -> np.ndarray:
    """Row-wise L2 normalization; zero rows are left as zeros."""
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


class HashingEmbedder:
    """Deterministic feature-hashing embedder (no external dependencies).

    Word unigrams, word bigrams and character trigrams are hashed into a
    fixed-width vector using the signed hashing trick (a second hash decides the
    sign, which reduces collisions). Purely lexical — it will not capture
    paraphrase the way a transformer does — but it is fully reproducible and
    gives genuine text-driven similarity for the sample bundle.

    Args:
        dim: Output dimension (defaults to :data:`EMBED_DIM`).
    """

    def __init__(self, dim: int = EMBED_DIM) -> None:
        self.dim = dim

    def _features(self, text: str) -> list[str]:
        """Extract word unigrams, word bigrams and character trigrams."""
        tokens = _TOKEN_RE.findall(text.lower())
        feats: list[str] = list(tokens)
        feats += [f"{a}_{b}" for a, b in zip(tokens, tokens[1:])]
        joined = " ".join(tokens)
        feats += [joined[i : i + 3] for i in range(max(0, len(joined) - 2))]
        return feats

    @staticmethod
    def _hash(token: str, salt: str) -> int:
        """Stable 8-byte hash of ``token`` (Python's ``hash`` is salted per run)."""
        digest = hashlib.md5(f"{salt}:{token}".encode()).digest()
        return int.from_bytes(digest[:8], "big")

    def encode(self, texts: list[str]) -> np.ndarray:
        """Return L2-normalized hashed embeddings for ``texts``."""
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            for feat in self._features(text):
                col = self._hash(feat, "idx") % self.dim
                sign = 1.0 if (self._hash(feat, "sign") & 1) else -1.0
                out[row, col] += sign
        return _l2_normalize(out)


class SentenceTransformerEmbedder:
    """Wrapper around a ``sentence-transformers`` model (real pipeline only).

    The heavy import happens in ``__init__`` so the module stays importable
    without torch installed.

    Args:
        model_name: Any sentence-transformers model id.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        from sentence_transformers import SentenceTransformer  # lazy, heavy

        self._model = SentenceTransformer(model_name)
        self.dim = self._model.get_sentence_embedding_dimension()

    def encode(self, texts: list[str]) -> np.ndarray:
        """Encode ``texts`` and L2-normalize."""
        vecs = self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return np.asarray(vecs, dtype=np.float32)


def get_embedder(prefer_semantic: bool = True, dim: int = EMBED_DIM) -> Embedder:
    """Return the best available embedder.

    Args:
        prefer_semantic: Try the transformer model first when true.
        dim: Dimension for the hashing fallback.

    Returns:
        A :class:`SentenceTransformerEmbedder` if available and requested,
        otherwise a :class:`HashingEmbedder`.
    """
    if prefer_semantic:
        try:
            return SentenceTransformerEmbedder()
        except Exception:  # noqa: BLE001 — any import/runtime failure → fallback
            pass
    return HashingEmbedder(dim=dim)


def semantic_scores(embeddings: np.ndarray, seed_indices: list[int]) -> np.ndarray:
    """Cosine similarity of every row to the centroid of the seed embeddings.

    Args:
        embeddings: L2-normalized embedding matrix ``(n, dim)``.
        seed_indices: Rows of the seed titles.

    Returns:
        A length-``n`` array of similarities in ``[-1, 1]``.
    """
    if not seed_indices:
        return np.zeros(embeddings.shape[0], dtype=np.float64)
    centroid = embeddings[seed_indices].mean(axis=0)
    norm = np.linalg.norm(centroid)
    if norm == 0:
        return np.zeros(embeddings.shape[0], dtype=np.float64)
    return embeddings @ (centroid / norm)
