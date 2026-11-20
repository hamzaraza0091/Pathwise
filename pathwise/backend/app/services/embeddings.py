import logging
import threading
import time

import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer

from app.core.config import settings

logger = logging.getLogger("pathwise.embeddings")

_hasher = HashingVectorizer(n_features=2**18, alternate_sign=False, norm="l2", ngram_range=(1, 2), stop_words="english", lowercase=True)
_lock = threading.Lock()
_state = {"model": None, "failed_at": 0.0}


def _load_sbert():
    if settings.embedding_backend == "tfidf":
        return None
    if _state["model"] is not None:
        return _state["model"]
    if _state["failed_at"] and time.time() - _state["failed_at"] < 900:
        return None
    with _lock:
        if _state["model"] is not None:
            return _state["model"]
        try:
            from sentence_transformers import SentenceTransformer

            _state["model"] = SentenceTransformer(settings.embedding_model)
            logger.info("loaded embedding model %s", settings.embedding_model)
        except Exception as error:
            _state["failed_at"] = time.time()
            logger.warning("sentence-transformers unavailable (%s); using hashed TF fallback", str(error)[:120])
            _state["model"] = None
    return _state["model"]


def backend_name() -> str:
    return settings.embedding_model if _load_sbert() is not None else "hashed-tf-v1"


def has_dense() -> bool:
    return _load_sbert() is not None


def embed_dense(texts: list[str]) -> np.ndarray | None:
    model = _load_sbert()
    if model is None:
        return None
    return np.asarray(model.encode([t[:3000] for t in texts], normalize_embeddings=True, show_progress_bar=False), dtype=np.float32)


def to_blob(vector: np.ndarray) -> bytes:
    return np.asarray(vector, dtype=np.float32).tobytes()


def from_blob(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


def calibrate(cosine: float, dense: bool) -> float:
    low, high = (0.15, 0.65) if dense else (0.0, 0.40)
    return float(max(0.0, min(100.0, (cosine - low) / (high - low) * 100)))


def similarity(candidate_text: str, job_text: str, job_vector: bytes | None = None, job_model: str | None = None) -> float:
    if not candidate_text.strip() or not job_text.strip():
        return 0.0
    model = _load_sbert()
    if model is not None:
        vectors = embed_dense([candidate_text])
        if job_vector is not None and job_model == settings.embedding_model:
            jv = from_blob(job_vector)
        else:
            jv = embed_dense([job_text])[0]
        return calibrate(float(np.dot(vectors[0], jv)), True)
    pair = _hasher.transform([candidate_text[:6000], job_text[:6000]])
    cosine = float(pair[0].multiply(pair[1]).sum())
    return calibrate(cosine, False)
