"""
Sentence embeddings, multilingual by default (multilingual-e5-small, 384-d, 100+ languages including
all major Indian languages), so a Hindi FIR and an English FIR describing the same modus operandi land
close together. Loaded lazily once per process; callers in async code use a thread.
"""
from __future__ import annotations

import threading

import numpy as np

from app.core.config import settings
from app.core.exceptions import MLServiceError
from app.core.logging import get_logger

logger = get_logger(__name__)

_MAX_CHARS = 1000
_model = None
_lock = threading.Lock()


def _get_model():
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                try:
                    from sentence_transformers import SentenceTransformer
                except ImportError as exc:
                    raise MLServiceError("sentence-transformers is not installed in this process") from exc
                logger.info("embedding_model_loading", model=settings.EMBEDDING_MODEL)
                _model = SentenceTransformer(settings.EMBEDDING_MODEL, device="cpu")
    return _model


def _prepare(text: str, kind: str) -> str:
    body = (text or "unknown crime incident").strip()[:_MAX_CHARS]
    # E5 models are trained with role prefixes; without them retrieval quality drops sharply.
    return f"{kind}: {body}" if "e5" in settings.EMBEDDING_MODEL.lower() else body


def embed_text(text: str, kind: str = "query") -> list[float]:
    return embed_batch([text], kind=kind)[0]


def embed_batch(texts: list[str], batch_size: int = 64, kind: str = "passage") -> list[list[float]]:
    if not texts:
        return []
    try:
        vectors = _get_model().encode(
            [_prepare(t, kind) for t in texts], batch_size=batch_size, normalize_embeddings=True, show_progress_bar=False
        )
    except MLServiceError:
        raise
    except Exception as exc:
        raise MLServiceError(f"Embedding failed: {exc}") from exc
    return [v.astype(np.float32).tolist() for v in vectors]


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    a, b = np.asarray(vec_a), np.asarray(vec_b)
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(a @ b / denom) if denom else 0.0
