"""Turns text into 384 numbers with the all-MiniLM-L6-v2 model.

Texts with similar meaning get similar numbers, even when they share no words.
The database stores and searches the numbers; this module only makes them.

The model runs through onnxruntime, from the ONNX copy in the model's own repo. It gives
the same numbers as sentence-transformers (to about 1e-7) without PyTorch, so the web
server needs about 200 MB instead of 700 MB.
"""
import threading

import numpy as np

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
# Pinned to one commit of the model repo, so a change upstream can't silently change
# every similarity score (or swap in different weights).
MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
DIMENSIONS = 384
MAX_TOKENS = 256    # the model's limit; longer text is cut off, as sentence-transformers does
BATCH = 8           # small batches keep the peak memory low

_session = None
_tokenizer = None
_lock = threading.Lock()


def _model_file(name: str) -> str:
    from huggingface_hub import hf_hub_download

    # Use the copy in ~/.cache/huggingface if there is one, so the app starts without
    # internet. Otherwise download it once (~90 MB).
    try:
        return hf_hub_download(MODEL_NAME, name, revision=MODEL_REVISION, local_files_only=True)
    except OSError:
        return hf_hub_download(MODEL_NAME, name, revision=MODEL_REVISION)


def _get_model():
    global _session, _tokenizer
    with _lock:
        if _session is None:
            import onnxruntime
            from tokenizers import Tokenizer

            tokenizer = Tokenizer.from_file(_model_file("tokenizer.json"))
            tokenizer.enable_truncation(MAX_TOKENS)
            tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")
            options = onnxruntime.SessionOptions()
            options.enable_cpu_mem_arena = False    # hand memory back after each batch
            _session = onnxruntime.InferenceSession(_model_file("onnx/model.onnx"), options,
                                                    providers=["CPUExecutionProvider"])
            _tokenizer = tokenizer
        return _session, _tokenizer


def project_text(title: str, abstract: str) -> str:
    return f"{title.strip()}. {abstract.strip()}"


def embed(texts: list[str]) -> list[list[float]]:
    """One vector per text, scaled to length 1 so cosine similarity is just a dot product."""
    session, tokenizer = _get_model()
    vectors = []
    for start in range(0, len(texts), BATCH):
        encoded = tokenizer.encode_batch(texts[start:start + BATCH])
        mask = np.array([e.attention_mask for e in encoded], dtype=np.int64)
        tokens = session.run(None, {
            "input_ids": np.array([e.ids for e in encoded], dtype=np.int64),
            "attention_mask": mask,
            "token_type_ids": np.array([e.type_ids for e in encoded], dtype=np.int64),
        })[0]
        # Average the token vectors, leaving out the padding, then scale to length 1:
        # the pooling and normalising the model was trained with.
        weights = mask[:, :, None].astype(np.float32)
        mean = (tokens * weights).sum(axis=1) / np.clip(weights.sum(axis=1), 1e-9, None)
        mean /= np.clip(np.linalg.norm(mean, axis=1, keepdims=True), 1e-12, None)
        vectors.extend(mean.tolist())
    return vectors
