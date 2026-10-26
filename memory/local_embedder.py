"""One process-local provider for the deployed semantic retrieval model."""

from __future__ import annotations

from memory.embedder import SentenceTransformerEmbedder


_LOCAL_EMBEDDER: SentenceTransformerEmbedder | None = None


def get_local_embedder() -> SentenceTransformerEmbedder:
    """Return the shared deployed MiniLM embedder for all production retrieval."""
    global _LOCAL_EMBEDDER
    if _LOCAL_EMBEDDER is None:
        # Import lazily to keep unit tests independent from model loading.
        from config import EMBEDDING_DEVICE, LOCAL_EMBEDDING_MODEL_DIR

        if not LOCAL_EMBEDDING_MODEL_DIR.is_dir():
            raise FileNotFoundError(f"deployed local embedding model was not found: {LOCAL_EMBEDDING_MODEL_DIR}")
        _LOCAL_EMBEDDER = SentenceTransformerEmbedder(
            LOCAL_EMBEDDING_MODEL_DIR,
            device=EMBEDDING_DEVICE,
        )
    return _LOCAL_EMBEDDER
