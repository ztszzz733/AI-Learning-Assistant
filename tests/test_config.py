from __future__ import annotations

import book_agent.config as config_module
from book_agent.config import Settings


def test_settings_pick_deepseek_defaults(monkeypatch) -> None:
    if config_module._local_settings is not None:
        monkeypatch.setattr(config_module._local_settings, "DEEPSEEK_API_KEY", "", raising=False)
        monkeypatch.setattr(
            config_module._local_settings, "DEEPSEEK_BASE_URL", "https://api.deepseek.com", raising=False
        )
        monkeypatch.setattr(
            config_module._local_settings, "DEEPSEEK_MODEL", "deepseek-v4-flash", raising=False
        )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    settings = Settings()

    assert settings.llm_api_key == "test-key"
    assert settings.llm_base_url == "https://api.deepseek.com"
    assert settings.llm_model == "deepseek-v4-flash"
    assert settings.llm_reasoning_effort == "high"
    assert settings.llm_thinking_type == "enabled"
    assert settings.llm_backend_label == "DeepSeek (deepseek-v4-flash)"


def test_settings_without_key_is_not_configured(monkeypatch) -> None:
    if config_module._local_settings is not None:
        monkeypatch.setattr(config_module._local_settings, "DEEPSEEK_API_KEY", "", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    settings = Settings()

    assert settings.llm_api_key is None
    assert settings.llm_base_url is None
    assert settings.llm_backend_label == "LLM not configured"
