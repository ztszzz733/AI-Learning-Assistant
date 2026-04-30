from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from book_agent.learning_modes.humanities_prompt import build_humanities_prompt
from book_agent.learning_modes.programming_prompt import build_programming_prompt

LearningMode = Literal["programming", "humanities"]

LEARNING_MODES: tuple[LearningMode, ...] = ("programming", "humanities")
DEFAULT_LEARNING_MODE: LearningMode = "humanities"


def normalize_learning_mode(mode: str | None) -> LearningMode:
    if mode is None or not str(mode).strip():
        return DEFAULT_LEARNING_MODE
    normalized = str(mode).strip().lower()
    if normalized not in LEARNING_MODES:
        allowed = ", ".join(LEARNING_MODES)
        raise ValueError(f"Unsupported learning mode: {mode}. Expected one of: {allowed}.")
    return normalized  # type: ignore[return-value]


def get_learning_system_message(mode: str | None) -> str:
    normalized = normalize_learning_mode(mode)
    if normalized == "programming":
        return (
            "You are a programming study coach who teaches through concepts, code reading, "
            "output prediction, small modifications, debugging, and practical projects. "
            "Do not ask the learner questions unless they explicitly request practice, testing, "
            "debugging guidance, or comprehension checks."
        )
    return (
        "You are a humanities and social-science study coach who teaches through problem "
        "awareness, arguments, evidence, real-world links, critical thinking, and expression. "
        "Do not ask the learner questions unless they explicitly request discussion, practice, "
        "testing, or comprehension checks."
    )


def get_learning_prompt(
    *,
    mode: str,
    book_title: str,
    chapter_title: str,
    chapter_content: str,
    user_level: str,
    user_question: str | None = None,
    learner_name: str = "learner",
    lesson_number: int | None = None,
    lesson_goal: str | None = None,
    prerequisites: list[str] | None = None,
    key_concepts: list[str] | None = None,
    check_question: str | None = None,
    conversation_history: str | None = None,
    ask_new_question: bool = True,
) -> str:
    normalized = normalize_learning_mode(mode)
    builder = (
        build_programming_prompt
        if normalized == "programming"
        else build_humanities_prompt
    )
    return builder(
        book_title=book_title,
        chapter_title=chapter_title,
        chapter_content=chapter_content,
        user_level=user_level,
        user_question=user_question,
        learner_name=learner_name,
        lesson_number=lesson_number,
        lesson_goal=lesson_goal,
        prerequisites=prerequisites,
        key_concepts=key_concepts,
        check_question=check_question,
        conversation_history=conversation_history,
        ask_new_question=ask_new_question,
    )


def getLearningPrompt(payload: Mapping[str, object]) -> str:
    """Compatibility wrapper for callers that prefer the camelCase shape."""

    def value(*names: str, default: object = "") -> object:
        for name in names:
            if name in payload and payload[name] is not None:
                return payload[name]
        return default

    return get_learning_prompt(
        mode=str(value("mode", default=DEFAULT_LEARNING_MODE)),
        book_title=str(value("bookTitle", "book_title")),
        chapter_title=str(value("chapterTitle", "chapter_title")),
        chapter_content=str(value("chapterContent", "chapter_content")),
        user_level=str(value("userLevel", "user_level", default="beginner")),
        user_question=str(value("userQuestion", "user_question", default="")) or None,
    )
