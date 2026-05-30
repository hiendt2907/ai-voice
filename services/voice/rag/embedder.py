"""Singleton embedding model using fastembed.

Uses sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2:
- 0.22GB ONNX (no external data file), dim=384
- Supports 50+ languages including Vietnamese
- No query/passage prefixes required
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Sequence

import numpy as np

logger = logging.getLogger(__name__)

_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


@lru_cache(maxsize=1)
def _get_model() -> "TextEmbedding":  # type: ignore[name-defined]
    from fastembed import TextEmbedding  # noqa: PLC0415

    logger.info("Loading embedding model %s …", _MODEL_NAME)
    model = TextEmbedding(model_name=_MODEL_NAME)
    logger.info("Embedding model ready")
    return model


def embed_query(text: str) -> list[float]:
    """Embed a search query (STT output)."""
    model = _get_model()
    vec = next(model.embed([text]))
    return vec.tolist()


def embed_passages(texts: Sequence[str]) -> list[list[float]]:
    """Embed KB article passages (question_variants)."""
    model = _get_model()
    return [vec.tolist() for vec in model.embed(list(texts))]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    va, vb = np.array(a, dtype=np.float32), np.array(b, dtype=np.float32)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    if denom < 1e-9:
        return 0.0
    return float(np.dot(va, vb) / denom)
