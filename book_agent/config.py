from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

try:
    from book_agent import local_settings as _local_settings
except ImportError:
    _local_settings = None


DEEPSEEK_V4_MODELS = ("deepseek-v4-flash", "deepseek-v4-pro")


def _local_value(name: str) -> str | None:
    if _local_settings is None:
        return None
    value = getattr(_local_settings, name, None)
    if isinstance(value, str):
        value = value.strip()
    return value or None


def _first_env(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def _first_configured(*names: str) -> str | None:
    for name in names:
        env_value = os.getenv(name)
        if env_value:
            return env_value
        value = _local_value(name)
        if value:
            return value
    return None


def _deepseek_enabled() -> bool:
    return bool(_first_configured("DEEPSEEK_API_KEY")) and not bool(
        _first_configured("OPENAI_API_KEY")
    )


def _default_llm_base_url() -> str | None:
    openai_base = _first_configured("OPENAI_BASE_URL")
    if openai_base:
        return openai_base
    deepseek_base = _first_configured("DEEPSEEK_BASE_URL")
    if deepseek_base and _deepseek_enabled():
        return deepseek_base
    if _deepseek_enabled():
        return "https://api.deepseek.com"
    return None


def _default_llm_model() -> str:
    explicit = _first_configured("OPENAI_MODEL", "DEEPSEEK_MODEL")
    if explicit:
        return explicit
    if _deepseek_enabled():
        return "deepseek-v4-flash"
    return "gpt-4.1-mini"


def _default_reasoning_effort() -> str | None:
    explicit = _first_configured("OPENAI_REASONING_EFFORT", "DEEPSEEK_REASONING_EFFORT")
    if explicit:
        return explicit
    if _deepseek_enabled():
        return "high"
    return None


def _default_thinking_type() -> str | None:
    explicit = _first_configured("DEEPSEEK_THINKING_TYPE", "OPENAI_THINKING_TYPE")
    if explicit:
        return explicit
    if _deepseek_enabled():
        return "enabled"
    return None


@dataclass(slots=True)
class Settings:
    data_dir: Path = field(
        default_factory=lambda: Path(os.getenv("BOOK_AGENT_DATA_DIR", "data/runtime"))
    )
    database_path: Path = field(
        default_factory=lambda: Path(
            os.getenv("BOOK_AGENT_DB", "data/runtime/book_agent.sqlite3")
        )
    )
    llm_api_key: str | None = field(
        default_factory=lambda: _first_configured("OPENAI_API_KEY", "DEEPSEEK_API_KEY")
    )
    llm_base_url: str | None = field(default_factory=_default_llm_base_url)
    llm_model: str = field(default_factory=_default_llm_model)
    llm_reasoning_effort: str | None = field(default_factory=_default_reasoning_effort)
    llm_thinking_type: str | None = field(default_factory=_default_thinking_type)
    retrieval_limit: int = field(
        default_factory=lambda: int(os.getenv("BOOK_AGENT_RETRIEVAL_LIMIT", "5"))
    )
    lesson_window_chunk_limit: int = field(
        default_factory=lambda: int(os.getenv("BOOK_AGENT_WINDOW_CHUNK_LIMIT", "12"))
    )
    history_limit: int = field(
        default_factory=lambda: int(os.getenv("BOOK_AGENT_HISTORY_LIMIT", "6"))
    )

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def llm_backend_label(self) -> str:
        if self.llm_base_url and "deepseek" in self.llm_base_url:
            return f"DeepSeek ({self.llm_model})"
        if self.llm_api_key or self.llm_base_url:
            return f"OpenAI-compatible ({self.llm_model})"
        return "LLM not configured"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
