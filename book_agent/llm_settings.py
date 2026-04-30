from __future__ import annotations

from dataclasses import replace

from book_agent.config import Settings, get_settings
from book_agent.db import utcnow_iso
from book_agent.schemas import LLMSettingsPublic, LLMSettingsUpdate

SETTING_KEYS = {
    "api_key": "llm_api_key",
    "base_url": "llm_base_url",
    "model": "llm_model",
    "reasoning_effort": "llm_reasoning_effort",
    "thinking_type": "llm_thinking_type",
}


def load_llm_settings(connection) -> dict[str, str]:
    rows = connection.execute(
        "SELECT key, value FROM app_settings WHERE key LIKE 'llm_%'"
    ).fetchall()
    return {row["key"]: row["value"] for row in rows}


def save_llm_settings(connection, request: LLMSettingsUpdate) -> LLMSettingsPublic:
    fields = request.model_fields_set
    if request.clear_api_key:
        _delete_setting(connection, "llm_api_key")
    elif "api_key" in fields and request.api_key is not None:
        _upsert_or_delete(connection, "llm_api_key", request.api_key)

    if "base_url" in fields:
        _upsert_or_delete(connection, "llm_base_url", request.base_url)
    if "model" in fields:
        _upsert_or_delete(connection, "llm_model", request.model)
    if "reasoning_effort" in fields:
        _upsert_or_delete(connection, "llm_reasoning_effort", request.reasoning_effort)
    if "thinking_type" in fields:
        _upsert_or_delete(connection, "llm_thinking_type", request.thinking_type)

    connection.commit()
    return get_public_llm_settings(connection)


def settings_from_database(connection, base_settings: Settings | None = None) -> Settings:
    base = base_settings or get_settings()
    stored = load_llm_settings(connection)
    overrides = {}
    for db_key, settings_key in SETTING_KEYS.items():
        value = stored.get(settings_key)
        if value is not None:
            overrides[settings_key] = value
    return replace(base, **overrides) if overrides else base


def get_public_llm_settings(connection) -> LLMSettingsPublic:
    settings = settings_from_database(connection)
    return LLMSettingsPublic(
        has_api_key=bool(settings.llm_api_key),
        api_key_preview=_preview_key(settings.llm_api_key),
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        reasoning_effort=settings.llm_reasoning_effort,
        thinking_type=settings.llm_thinking_type,
        backend_label=settings.llm_backend_label,
    )


def _upsert_or_delete(connection, key: str, value: str | None) -> None:
    cleaned = value.strip() if isinstance(value, str) else None
    if not cleaned:
        _delete_setting(connection, key)
        return
    connection.execute(
        """
        INSERT INTO app_settings (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = excluded.updated_at
        """,
        (key, cleaned, utcnow_iso()),
    )


def _delete_setting(connection, key: str) -> None:
    connection.execute("DELETE FROM app_settings WHERE key = ?", (key,))


def _preview_key(api_key: str | None) -> str | None:
    if not api_key:
        return None
    if len(api_key) <= 8:
        return "已配置"
    return f"{api_key[:3]}...{api_key[-4:]}"
