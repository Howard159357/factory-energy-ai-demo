"""Choose the backend from environment variables."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from factory_energy.llm.base import LLMClient
from factory_energy.llm.codex_cli import CodexCLIClient
from factory_energy.llm.fake import FakeClient
from factory_energy.llm.openai_compatible import OpenAICompatibleClient


def key_from_file(path: str) -> str:
    """The API key from a file kept outside the repository (``LLM_API_KEY_FILE``): the first
    line that is not empty and not a ``#`` comment. Keeps the key itself out of .env."""
    if not path:
        return ""
    file = Path(path).expanduser()
    try:
        lines = file.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ValueError(f"LLM_API_KEY_FILE {file} cannot be read: {error}") from error
    return next((line.strip() for line in lines
                 if line.strip() and not line.strip().startswith("#")), "")


@dataclass(frozen=True)
class LLMSettings:
    provider: str
    base_url: str
    model: str
    api_key: str = field(repr=False)
    temperature: float
    max_tokens: int
    extra_body: dict[str, Any]
    codex_model: str = "gpt-6-luna"
    codex_effort: str = "low"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> LLMSettings:
        values = os.environ if env is None else env
        extra = values.get("LLM_EXTRA_BODY", "")
        return cls(
            provider=values.get("LLM_PROVIDER", "fake"),
            base_url=values.get("LLM_BASE_URL", ""),
            model=values.get("LLM_MODEL", ""),
            api_key=values.get("LLM_API_KEY", "") or key_from_file(values.get("LLM_API_KEY_FILE",
                                                                               "")),
            temperature=float(values.get("LLM_TEMPERATURE", "0.2")),
            max_tokens=int(values.get("LLM_MAX_TOKENS", "2048")),
            # e.g. {"chat_template_kwargs": {"enable_thinking": false}} for a vLLM reasoning model
            extra_body=json.loads(extra) if extra else {},
            codex_model=values.get("CODEX_MODEL", "gpt-6-luna"),
            codex_effort=values.get("CODEX_EFFORT", "low"),
        )


def make_client(settings: LLMSettings) -> LLMClient:
    if settings.provider == "fake":
        return FakeClient()
    if settings.provider == "openai_compatible":
        return OpenAICompatibleClient(settings.base_url, settings.model, settings.api_key,
                                      settings.temperature, settings.max_tokens,
                                      extra_body=settings.extra_body)
    if settings.provider == "codex_cli":  # temporary stand-in while the GPU host is down
        return CodexCLIClient(settings.codex_model, settings.codex_effort)
    raise ValueError(f"unknown LLM_PROVIDER {settings.provider!r}: "
                     "use fake, openai_compatible or codex_cli")
