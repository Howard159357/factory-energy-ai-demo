"""RAG settings from environment variables. No secret has a default; all are optional."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from factory_energy.paths import ROOT

REPO_ROOT = ROOT
COLLECTION = "plant-knowledge"


@dataclass(frozen=True)
class RagSettings:
    chroma_path: Path
    chroma_host: str
    chroma_port: int
    chroma_wait_seconds: float
    collection: str
    embedding_provider: str
    embedding_model: str
    embedding_base_url: str
    embedding_api_key: str
    embedding_model_dir: Path  # local models: <dir>/<model>/model.onnx and tokenizer.json

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> RagSettings:
        values = os.environ if env is None else env
        path = Path(values.get("CHROMA_PATH", "data/chroma"))
        models = Path(values.get("EMBEDDING_MODEL_DIR", "models/embeddings"))
        return cls(
            chroma_path=path if path.is_absolute() else REPO_ROOT / path,
            chroma_host=values.get("CHROMA_HOST", ""),
            chroma_port=int(values.get("CHROMA_PORT", "8000")),
            chroma_wait_seconds=float(values.get("CHROMA_WAIT_SECONDS", "60")),
            collection=values.get("CHROMA_COLLECTION", COLLECTION),
            embedding_provider=values.get("EMBEDDING_PROVIDER", "hash"),
            embedding_model=values.get("EMBEDDING_MODEL", ""),
            embedding_base_url=values.get("EMBEDDING_BASE_URL", ""),
            embedding_api_key=values.get("EMBEDDING_API_KEY", ""),
            embedding_model_dir=models if models.is_absolute() else REPO_ROOT / models,
        )
