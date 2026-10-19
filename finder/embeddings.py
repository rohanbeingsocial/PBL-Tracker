"""Turns text into 384 numbers with the all-MiniLM-L6-v2 model.

Texts with similar meaning get similar numbers, even when they share no words.
The database stores and searches the numbers; this module only makes them.
"""
import os
import threading

# transformers also tries to import TensorFlow if it is installed, which fails with
# a "Keras 3" error on some laptops. We only need PyTorch.
os.environ.setdefault("USE_TF", "0")

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
# Pinned to one commit of the model repo, so a change upstream can't silently change
# every similarity score (or swap in different weights).
MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
DIMENSIONS = 384

_model = None
_lock = threading.Lock()


def _get_model():
    global _model
    with _lock:
        if _model is None:
            from sentence_transformers import SentenceTransformer

            # Use the copy in ~/.cache/huggingface if there is one, so the app starts
            # without internet. Otherwise download it once (~90 MB).
            try:
                _model = SentenceTransformer(MODEL_NAME, revision=MODEL_REVISION, device="cpu",
                                             local_files_only=True)
            except OSError:
                _model = SentenceTransformer(MODEL_NAME, revision=MODEL_REVISION, device="cpu")
        return _model


def project_text(title: str, abstract: str) -> str:
    return f"{title.strip()}. {abstract.strip()}"


def embed(texts: list[str]) -> list[list[float]]:
    """One vector per text, scaled to length 1 so cosine similarity is just a dot product."""
    vectors = _get_model().encode(texts, normalize_embeddings=True, batch_size=32)
    return vectors.tolist()
