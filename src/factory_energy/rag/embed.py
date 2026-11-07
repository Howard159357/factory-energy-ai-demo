"""Text embedders. Everything runs on-premises; nothing here calls a cloud service.

- ``hash``: deterministic hashed bag of words and word pairs. No download, no network, used by
  the tests and by default on machines that cannot fetch model files.
- ``onnx``: the all-MiniLM-L6-v2 sentence embedding model run by onnxruntime (bundled with
  chromadb); the model file is downloaded once and cached.
- ``openai_compatible``: any ``/v1/embeddings`` endpoint, for example an embedding model served
  by vLLM on the GPU host.
- ``local``: a multilingual embedding model (multilingual-e5-small, bge-m3 or nomic-embed-text)
  exported to ONNX and copied into a folder by hand, run by onnxruntime and tokenizers (both
  installed with chromadb). Nothing is downloaded. If the folder or the model is missing, the
  hash embedder is used instead and a warning is logged.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import urllib.request
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from factory_energy.rag.settings import RagSettings

log = logging.getLogger(__name__)

TOKEN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "by", "do", "does", "for", "from", "has", "have",
    "how", "if", "in", "into", "is", "it", "its", "of", "on", "or", "that", "the", "then",
    "there", "these", "this", "to", "was", "were", "what", "when", "which", "while", "will",
    "with",
})


class Embedder(Protocol):
    @property
    def name(self) -> str: ...

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Vectors for documents (passages to index)."""
        ...

    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        """Vectors for search queries; differs from ``embed`` for models trained with
        query and passage prefixes (e5, nomic)."""
        ...


def tokens(text: str) -> list[str]:
    """Lower-case words; ids such as ``rf-02`` stay whole and also yield their parts."""
    found: list[str] = []
    for word in TOKEN.findall(text.lower()):
        if word in STOPWORDS:
            continue
        found.append(word)
        if "-" in word:
            found.extend(part for part in word.split("-") if part not in STOPWORDS)
    return found


class HashEmbedder:
    """Feature hashing of unigrams and bigrams with a sign bit and log term frequency."""

    def __init__(self, dimensions: int = 1024) -> None:
        if dimensions < 16:
            raise ValueError("dimensions must be at least 16")
        self.dimensions = dimensions

    @property
    def name(self) -> str:
        return f"hash-{self.dimensions}"

    def _vector(self, text: str) -> list[float]:
        words = tokens(text)
        features = Counter(words + [f"{a} {b}" for a, b in zip(words, words[1:], strict=False)])
        vector = [0.0] * self.dimensions
        for feature, count in features.items():
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            value = int.from_bytes(digest, "little")
            sign = 1.0 if value & 1 else -1.0
            vector[(value >> 1) % self.dimensions] += sign * (1.0 + math.log(count))
        norm = math.sqrt(sum(x * x for x in vector)) or 1.0
        return [x / norm for x in vector]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        return self.embed(texts)


class OnnxEmbedder:
    """all-MiniLM-L6-v2 through chromadb's bundled onnxruntime wrapper (384 dimensions)."""

    def __init__(self) -> None:
        from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2

        self._model = ONNXMiniLM_L6_V2()

    @property
    def name(self) -> str:
        return "onnx-all-MiniLM-L6-v2"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(x) for x in row] for row in self._model(texts)]

    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        return self.embed(texts)


class OpenAICompatibleEmbedder:
    """POST /v1/embeddings on a self-hosted server (vLLM, llama.cpp, ...)."""

    def __init__(self, base_url: str, model: str, api_key: str = "", timeout: float = 60.0) -> None:
        if not base_url or not model:
            raise ValueError("EMBEDDING_BASE_URL and EMBEDDING_MODEL are required")
        self.url = base_url.rstrip("/") + "/embeddings"
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    @property
    def name(self) -> str:
        return f"openai-compatible-{self.model}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        body = json.dumps({"model": self.model, "input": texts}).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(self.url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310
            payload = json.load(response)
        rows = sorted(payload["data"], key=lambda item: item["index"])
        return [[float(x) for x in row["embedding"]] for row in rows]

    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        return self.embed(texts)


@dataclass(frozen=True)
class LocalModel:
    """How a model turns token states into one vector, and the prefixes it was trained with."""

    pooling: str  # "mean" over real tokens, or "cls" (the first token)
    query_prefix: str = ""
    document_prefix: str = ""
    max_tokens: int = 512  # longer inputs are cut; the chunks are about 400 tokens


LOCAL_MODELS = {
    "multilingual-e5-small": LocalModel("mean", "query: ", "passage: "),
    "bge-m3": LocalModel("cls"),
    "nomic-embed-text": LocalModel("mean", "search_query: ", "search_document: "),
}
MODEL_FILES = ("model.onnx", "onnx/model.onnx")  # the layout of an ONNX export or a model repo


def pool(states: Any, mask: Any, method: str) -> list[list[float]]:
    """Token states (batch, tokens, dims) to unit vectors, by mean over real tokens or CLS."""
    import numpy as np

    states, mask = np.asarray(states, dtype=np.float32), np.asarray(mask, dtype=np.float32)
    if method == "cls":
        vectors = states[:, 0, :]
    else:
        weights = mask[:, :, None]
        vectors = (states * weights).sum(axis=1) / np.clip(weights.sum(axis=1), 1e-9, None)
    norms = np.clip(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12, None)
    return [[float(x) for x in row] for row in vectors / norms]


class LocalOnnxEmbedder:
    """A multilingual embedding model from a local folder: ``<dir>/<model>/model.onnx`` (or
    ``onnx/model.onnx``) and ``tokenizer.json``. Never downloads anything."""

    def __init__(self, model: str, model_dir: Path) -> None:
        if model not in LOCAL_MODELS:
            raise ValueError(f"unknown local model {model!r}: use {', '.join(LOCAL_MODELS)}")
        folder = model_dir / model
        onnx_file = next((folder / f for f in MODEL_FILES if (folder / f).is_file()), None)
        tokenizer_file = folder / "tokenizer.json"
        if onnx_file is None or not tokenizer_file.is_file():
            raise FileNotFoundError(f"{folder} needs model.onnx (or onnx/model.onnx) and "
                                    "tokenizer.json")
        import onnxruntime
        from tokenizers import Tokenizer

        self.model = model
        self.spec = LOCAL_MODELS[model]
        self._tokenizer = Tokenizer.from_file(str(tokenizer_file))
        self._tokenizer.enable_truncation(self.spec.max_tokens)
        self._tokenizer.enable_padding()
        self._session = onnxruntime.InferenceSession(str(onnx_file),
                                                     providers=["CPUExecutionProvider"])
        self._inputs = {i.name for i in self._session.get_inputs()}

    @property
    def name(self) -> str:
        return f"local-{self.model}"

    def _run(self, texts: list[str]) -> list[list[float]]:
        import numpy as np

        encoded = self._tokenizer.encode_batch(texts)
        feed = {"input_ids": np.array([e.ids for e in encoded], dtype=np.int64),
                "attention_mask": np.array([e.attention_mask for e in encoded], dtype=np.int64)}
        if "token_type_ids" in self._inputs:
            feed["token_type_ids"] = np.array([e.type_ids for e in encoded], dtype=np.int64)
        outputs = self._session.run(None, {k: v for k, v in feed.items() if k in self._inputs})
        return pool(outputs[0], feed["attention_mask"], self.spec.pooling)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._run([self.spec.document_prefix + t for t in texts])

    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        return self._run([self.spec.query_prefix + t for t in texts])


def make_embedder(
    provider: str, model: str = "", base_url: str = "", api_key: str = "",
    model_dir: Path | None = None,
) -> Embedder:
    if provider == "hash":
        return HashEmbedder()
    if provider == "onnx":
        return OnnxEmbedder()
    if provider == "openai_compatible":
        return OpenAICompatibleEmbedder(base_url, model, api_key)
    if provider == "local":
        folder = model_dir or Path("models/embeddings")
        try:
            embedder: Embedder = LocalOnnxEmbedder(model or "multilingual-e5-small", folder)
        except (FileNotFoundError, ImportError, OSError) as error:
            log.warning("local embedding model not usable (%s); falling back to the hash "
                        "embedder. Copy the model files there and run `rag ingest --rebuild`.",
                        error)
            return HashEmbedder()
        log.info("embedder: %s from %s", embedder.name, folder)
        return embedder
    raise ValueError(
        f"unknown EMBEDDING_PROVIDER {provider!r}: use hash, onnx, openai_compatible or local"
    )


def embedder_from(settings: RagSettings) -> Embedder:
    return make_embedder(settings.embedding_provider, settings.embedding_model,
                         settings.embedding_base_url, settings.embedding_api_key,
                         settings.embedding_model_dir)
