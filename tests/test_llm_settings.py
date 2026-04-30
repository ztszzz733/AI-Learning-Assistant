from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from book_agent.config import Settings
from book_agent.db import connect_database
from book_agent.llm_settings import (
    get_public_llm_settings,
    save_llm_settings,
    settings_from_database,
)
from book_agent.schemas import LLMSettingsUpdate


def test_llm_settings_can_be_saved_and_cleared() -> None:
    run_dir = Path("data/test_runs") / f"llm_settings_{uuid.uuid4().hex[:8]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    base_settings = Settings(
        data_dir=run_dir / "data",
        database_path=run_dir / "data" / "test.sqlite3",
        llm_api_key=None,
        llm_base_url=None,
        llm_model="gpt-4.1-mini",
        llm_reasoning_effort=None,
        llm_thinking_type=None,
    )
    connection = connect_database(settings=base_settings)
    try:
        public = save_llm_settings(
            connection,
            LLMSettingsUpdate(
                api_key="sk-test-123456",
                base_url="https://api.deepseek.com",
                model="deepseek-v4-pro",
                reasoning_effort="high",
                thinking_type="enabled",
            ),
        )
        effective = settings_from_database(connection, base_settings)

        assert public.has_api_key is True
        assert public.api_key_preview == "sk-...3456"
        assert effective.llm_api_key == "sk-test-123456"
        assert effective.llm_model == "deepseek-v4-pro"
        assert effective.llm_reasoning_effort == "high"
        assert effective.llm_thinking_type == "enabled"

        save_llm_settings(connection, LLMSettingsUpdate(clear_api_key=True))
        effective_after_clear = settings_from_database(connection, base_settings)

        assert effective_after_clear.llm_api_key is None
        assert get_public_llm_settings(connection).model == "deepseek-v4-pro"
    finally:
        connection.close()
        shutil.rmtree(run_dir, ignore_errors=True)
