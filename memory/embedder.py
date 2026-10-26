"""Embedding providers used by long-term-memory retrieval."""

from __future__ import annotations

from abc import ABC, abstractmethod
import hashlib
import math
from pathlib import Path
import re


Embedding = list[float]


class Embedder(ABC):
    """Abstract interface for converting text into a dense vector."""

    @abstractmethod
    def embed(self, text: str) -> Embedding:
        """Convert one text value into a normalized vector."""

    def embed_many(self, texts: list[str]) -> list[Embedding]:
        """Convert multiple text values into vectors.

        Args:
            texts: Source text values.

        Returns:
            One embedding for every source text.
        """
        return [self.embed(text) for text in texts]


class HashingEmbedder(Embedder):
    """Offline deterministic embedder based on word and Chinese-character features.

    This lightweight default permits retrieval without a network connection. Replace
    this class with an API or local-model implementation without changing callers.
    """

    def __init__(self, dimensions: int = 256) -> None:
        """Initialize the vector dimensionality.

        Args:
            dimensions: Number of dimensions in each output vector.

        Raises:
            ValueError: If ``dimensions`` is not positive.
        """
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        self._dimensions = dimensions

    def embed(self, text: str) -> Embedding:
        """Create a normalized feature vector for text.

        Args:
            text: Source text to represent.

        Returns:
            Unit-length vector, or an all-zero vector for empty input.
        """
        vector = [0.0] * self._dimensions
        for token in self._tokens(text):
            index = self._index(token)
            vector[index] += 1.0

        magnitude = math.sqrt(sum(value * value for value in vector))
        if magnitude == 0:
            return vector
        return [value / magnitude for value in vector]

    def _index(self, token: str) -> int:
        """Return a stable vector index for one feature."""
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        return int.from_bytes(digest, byteorder="big") % self._dimensions

    @staticmethod
    def _tokens(text: str) -> list[str]:
        """Extract English terms and Chinese character bigrams."""
        normalized = text.lower()
        words = re.findall(r"[a-z0-9_]+", normalized)
        chinese = "".join(re.findall(r"[\u4e00-\u9fff]", normalized))
        bigrams = [chinese[index:index + 2] for index in range(len(chinese) - 1)]
        return words + bigrams


class SentenceTransformerEmbedder(Embedder):
    """Local Sentence Transformers embedder with lazy model loading.

    The model is loaded only when an embedding is requested. This keeps module
    import and offline tests independent from model downloads and GPU settings.
    """

    def __init__(self, model_path: str | Path, device: str | None = None) -> None:
        """Configure a locally available Sentence Transformers model.

        Args:
            model_path: Local directory containing the downloaded model files.
            device: Optional PyTorch device such as ``cpu`` or ``cuda``.
        """
        self._model_path = Path(model_path)
        self._device = device
        self._model: object | None = None

    @property
    def model_id(self) -> str:
        """Return a stable identifier for vector-index compatibility checks."""
        return str(self._model_path.resolve())

    def embed(self, text: str) -> Embedding:
        """Embed one text value with L2 normalization.

        Args:
            text: Source text to represent.

        Returns:
            Normalized dense embedding.
        """
        return self.embed_many([text])[0]

    def embed_many(self, texts: list[str]) -> list[Embedding]:
        """Embed multiple texts in one local-model call.

        Args:
            texts: Source text values.

        Returns:
            Normalized dense embeddings.

        Raises:
            FileNotFoundError: If the configured local model directory is absent.
        """
        if not texts:
            return []

        model = self._get_model()
        vectors = model.encode(
            texts,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return [vector.tolist() for vector in vectors]

    def _get_model(self) -> object:
        """Load and cache the local model on first use."""
        if self._model is not None:
            return self._model
        if not self._model_path.is_dir():
            raise FileNotFoundError(
                f"Local embedding model was not found: {self._model_path}"
            )

        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(
            str(self._model_path),
            device=self._device,
            local_files_only=True,
        )
        return self._model
