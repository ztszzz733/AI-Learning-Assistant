from __future__ import annotations

from types import SimpleNamespace

from book_agent.learning_modes import getLearningPrompt, get_learning_prompt
from book_agent.tutor import _extract_page_window_directive


def _lesson() -> SimpleNamespace:
    return SimpleNamespace(
        lesson_number=1,
        title="函数和返回值",
        goal="理解函数如何接收输入并返回结果。",
        key_concepts=["函数"],
        check_question="函数为什么需要返回值？",
    )


def test_programming_prompt_contains_code_learning_flow() -> None:
    prompt = get_learning_prompt(
        mode="programming",
        book_title="Python 入门",
        chapter_title="函数和返回值",
        chapter_content="def add(a, b): return a + b",
        user_level="beginner",
        user_question="带我学这一节",
    )

    assert "标题：本节学习目标" in prompt
    assert "模块 2：代码拆解" in prompt
    assert "模块 3：运行结果预测" in prompt
    assert "模块 4：动手修改" in prompt
    assert "模块 7：小项目实践" in prompt


def test_humanities_prompt_contains_argument_learning_flow() -> None:
    prompt = getLearningPrompt(
        {
            "mode": "humanities",
            "bookTitle": "社会学导论",
            "chapterTitle": "现代社会",
            "chapterContent": "本章讨论现代社会的组织方式。",
            "userLevel": "beginner",
            "userQuestion": "这章怎么学？",
        }
    )

    assert "标题：本章思考主线" in prompt
    assert "模块 1：本章问题意识" in prompt
    assert "模块 3：论证结构" in prompt
    assert "模块 6：批判性思考" in prompt
    assert "模块 8：讨论题 / 写作题" not in prompt
    assert "不要主动向用户提问题" in prompt


def test_page_window_directive_is_removed_from_visible_reply() -> None:
    clean, page_window_size = _extract_page_window_directive(
        "模块 1：核心概念\n内容太密，需要放慢。\n[[NEXT_PAGE_WINDOW: 4]]"
    )

    assert page_window_size == 4
    assert "NEXT_PAGE_WINDOW" not in clean
