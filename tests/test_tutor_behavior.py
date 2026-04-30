from __future__ import annotations

from types import SimpleNamespace

from book_agent.tutor import (
    _assistant_recently_asked_question,
    _user_requested_practice_prompt,
)


def _lesson() -> SimpleNamespace:
    return SimpleNamespace(
        lesson_number=1,
        title="基础概念",
        goal="理解基础概念在全书中的作用。",
        key_concepts=["基础概念"],
        check_question="什么是这一课最核心的概念？",
    )


def test_recent_question_detection() -> None:
    history = [
        {"role": "assistant", "content": "你先试着回答一个问题：什么是核心概念？"},
        {"role": "user", "content": "我理解它是全书主轴。"},
    ]
    assert _assistant_recently_asked_question(history) is True


def test_user_must_explicitly_request_practice_prompt() -> None:
    assert _user_requested_practice_prompt("先讲重点") is False
    assert _user_requested_practice_prompt("给我一道练习检查理解") is True
