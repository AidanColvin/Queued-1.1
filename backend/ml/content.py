"""Content-based signal: TF-IDF over genres + mood tags + plot keywords.

A compact, well-documented TF-IDF implementation (smoothed IDF, sublinear TF,
L2-normalized rows — the same formulation as scikit-learn's ``TfidfVectorizer``)
lives here so the sample pipeline and the real pipeline build *identical*
artifacts and the served API needs no scikit-learn at runtime.

At inference, content similarity is the cosine between the centroid of the seed
rows and every catalog row — cheap because the rows are precomputed and
L2-normalized.
"""

from __future__ import annotations

import math
import re
from collections import Counter

import numpy as np
import scipy.sparse as sp

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# A small, deliberately conservative English stopword list. Kept short so genre
# and plot keywords (the real signal) dominate the vocabulary.
_STOPWORDS = frozenset(
    """a an and are as at be by for from has have in into is it its of on or
    that the their them they this to was were what when which who will with
    you your his her he she him their our""".split()
)


def _tokenize(text: str) -> list[str]:
    """Lowercase, split on non-alphanumerics, drop stopwords and 1-char tokens."""
    return [
        tok
        for tok in _TOKEN_RE.findall(text.lower())
        if len(tok) > 1 and tok not in _STOPWORDS
    ]


class TfidfBuilder:
    """Fit a TF-IDF matrix over a corpus of short documents.

    The fitted vocabulary and IDF vector are retained so the same transform can
    be reapplied (e.g. to enrich the catalog later). For Phase 1 inference all
    inputs are existing catalog rows, so only :meth:`fit_transform` is used at
    build time.

    Args:
        min_df: Minimum document frequency for a term to enter the vocabulary.
        sublinear_tf: Apply ``1 + log(tf)`` term-frequency scaling.
    """

    def __init__(self, min_df: int = 1, sublinear_tf: bool = True) -> None:
        self.min_df = min_df
        self.sublinear_tf = sublinear_tf
        self.vocabulary_: dict[str, int] = {}
        self.idf_: np.ndarray | None = None

    def fit_transform(self, documents: list[str]) -> sp.csr_matrix:
        """Learn the vocabulary + IDF and return the L2-normalized TF-IDF matrix.

        Args:
            documents: One string per catalog item (genres + tags + overview).

        Returns:
            A CSR matrix of shape ``(len(documents), n_terms)``.
        """
        tokenized = [_tokenize(doc) for doc in documents]

        # Document frequency per term, then prune by min_df and assign columns.
        doc_freq: Counter[str] = Counter()
        for tokens in tokenized:
            doc_freq.update(set(tokens))
        vocab = sorted(term for term, df in doc_freq.items() if df >= self.min_df)
        self.vocabulary_ = {term: i for i, term in enumerate(vocab)}

        n_docs = len(documents)
        # Smoothed IDF (sklearn default): idf = ln((1 + n) / (1 + df)) + 1.
        self.idf_ = np.array(
            [math.log((1 + n_docs) / (1 + doc_freq[t])) + 1.0 for t in vocab],
            dtype=np.float64,
        )

        rows, cols, data = [], [], []
        for row, tokens in enumerate(tokenized):
            counts = Counter(tok for tok in tokens if tok in self.vocabulary_)
            for term, count in counts.items():
                col = self.vocabulary_[term]
                tf = 1.0 + math.log(count) if self.sublinear_tf else float(count)
                rows.append(row)
                cols.append(col)
                data.append(tf * self.idf_[col])

        matrix = sp.csr_matrix(
            (data, (rows, cols)), shape=(n_docs, len(vocab)), dtype=np.float64
        )
        return _l2_normalize_rows(matrix)


def _l2_normalize_rows(matrix: sp.csr_matrix) -> sp.csr_matrix:
    """Scale each row to unit L2 norm (zero rows are left untouched)."""
    norms = np.sqrt(matrix.multiply(matrix).sum(axis=1)).A1
    norms[norms == 0] = 1.0
    inv = sp.diags(1.0 / norms)
    return (inv @ matrix).tocsr()


def content_scores(tfidf: sp.csr_matrix, seed_indices: list[int]) -> np.ndarray:
    """Cosine similarity of every row to the centroid of the seed rows.

    Args:
        tfidf: L2-normalized TF-IDF matrix ``(n, n_terms)``.
        seed_indices: Rows of the seed titles.

    Returns:
        A length-``n`` array of similarities in ``[0, 1]``.
    """
    if not seed_indices:
        return np.zeros(tfidf.shape[0], dtype=np.float64)

    centroid = tfidf[seed_indices].mean(axis=0)  # dense (1, n_terms) matrix
    centroid = np.asarray(centroid).ravel()
    norm = np.linalg.norm(centroid)
    if norm == 0:
        return np.zeros(tfidf.shape[0], dtype=np.float64)
    centroid /= norm

    # Rows are unit-normalized, so the dot product is the cosine similarity.
    scores = tfidf @ centroid
    return np.asarray(scores).ravel()
