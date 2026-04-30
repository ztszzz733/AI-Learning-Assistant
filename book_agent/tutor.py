from __future__ import annotations

import json
import re
import uuid

from openai import OpenAI

from book_agent.config import Settings
from book_agent.db import utcnow_iso
from book_agent.learning_modes import (
    DEFAULT_LEARNING_MODE,
    LearningMode,
    get_learning_prompt,
    get_learning_system_message,
    normalize_learning_mode,
)
from book_agent.planner import (
    generate_page_window_study_plan,
    get_plan,
    rebuild_page_window_plan_after_lesson,
)
from book_agent.retrieval import retrieve_chunks, retrieve_page_window_chunks
from book_agent.schemas import (
    ChunkReference,
    LessonOutput,
    SessionSummary,
    StartSessionRequest,
    TutorReply,
)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


MIN_PAGE_WINDOW_SIZE = 1
MAX_PAGE_WINDOW_SIZE = 60


def _clamp_page_window_size(value: int) -> int:
    return max(MIN_PAGE_WINDOW_SIZE, min(MAX_PAGE_WINDOW_SIZE, int(value)))


def _load_session(connection, session_id: str):
    row = connection.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if not row:
        raise ValueError(f"Session not found: {session_id}")
    return row


def _load_book_title(connection, book_id: str) -> str:
    row = connection.execute("SELECT title FROM books WHERE id = ?", (book_id,)).fetchone()
    if not row:
        raise ValueError(f"Book not found: {book_id}")
    return str(row["title"])


def _session_learning_mode(session, override: str | None = None) -> LearningMode:
    if override is not None:
        return normalize_learning_mode(override)
    return normalize_learning_mode(session["learning_mode"] or DEFAULT_LEARNING_MODE)


def _touch_session(connection, session_id: str) -> str:
    updated_at = utcnow_iso()
    connection.execute(
        "UPDATE sessions SET updated_at = ? WHERE id = ?", (updated_at, session_id)
    )
    return updated_at


def _insert_message(connection, session_id: str, role: str, content: str, retrieval_payload: list[dict]) -> None:
    connection.execute(
        """
        INSERT INTO messages (id, session_id, role, content, retrieval_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            _new_id("msg"),
            session_id,
            role,
            content,
            json.dumps(retrieval_payload, ensure_ascii=False),
            utcnow_iso(),
        ),
    )
    _touch_session(connection, session_id)


def _save_lesson_output(
    connection,
    *,
    session_id: str,
    lesson_number: int,
    lesson_title: str,
    learning_mode: str,
    assistant_message: str,
    references: list[ChunkReference],
    llm_used: bool,
    llm_error: str | None,
) -> LessonOutput:
    created_at = utcnow_iso()
    connection.execute(
        """
        INSERT INTO lesson_outputs (
            id, session_id, lesson_number, lesson_title, learning_mode,
            assistant_message, references_json, llm_used, llm_error, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _new_id("out"),
            session_id,
            lesson_number,
            lesson_title,
            learning_mode,
            assistant_message,
            json.dumps(
                [reference.model_dump() for reference in references],
                ensure_ascii=False,
            ),
            1 if llm_used else 0,
            llm_error,
            created_at,
        ),
    )
    return LessonOutput(
        session_id=session_id,
        lesson_number=lesson_number,
        lesson_title=lesson_title,
        learning_mode=normalize_learning_mode(learning_mode),
        llm_used=llm_used,
        llm_error=llm_error,
        assistant_message=assistant_message,
        references=references,
        created_at=created_at,
    )


def get_lesson_output(
    connection, session_id: str, lesson_number: int
) -> LessonOutput | None:
    _load_session(connection, session_id)
    row = connection.execute(
        """
        SELECT *
        FROM lesson_outputs
        WHERE session_id = ? AND lesson_number = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (session_id, lesson_number),
    ).fetchone()
    if not row:
        return None
    references = [
        ChunkReference(**item)
        for item in json.loads(row["references_json"] or "[]")
    ]
    return LessonOutput(
        session_id=row["session_id"],
        lesson_number=row["lesson_number"],
        lesson_title=row["lesson_title"],
        learning_mode=normalize_learning_mode(row["learning_mode"]),
        llm_used=bool(row["llm_used"]),
        llm_error=row["llm_error"],
        assistant_message=row["assistant_message"],
        references=references,
        created_at=row["created_at"],
    )


def _reply_from_lesson_output(
    output: LessonOutput, *, can_advance: bool
) -> TutorReply:
    return TutorReply(
        session_id=output.session_id,
        lesson_number=output.lesson_number,
        lesson_title=output.lesson_title,
        learning_mode=output.learning_mode,
        reply_kind="lesson",
        llm_used=output.llm_used,
        llm_error=output.llm_error,
        assistant_message=output.assistant_message,
        references=output.references,
        suggested_next_action="review_saved_lesson",
        can_advance=can_advance,
        prompt_preview=None,
    )


def _recent_history(connection, session_id: str, limit: int) -> list[dict[str, str]]:
    rows = connection.execute(
        """
        SELECT role, content
        FROM messages
        WHERE session_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (session_id, limit),
    ).fetchall()
    return [dict(row) for row in reversed(rows)]


def _is_next_lesson_request(message: str) -> bool:
    lowered = message.lower()
    triggers = ["下一课", "下一节", "继续下一课", "next lesson", "advance lesson"]
    return any(trigger in lowered for trigger in triggers)


def _is_previous_lesson_request(message: str) -> bool:
    lowered = message.lower()
    triggers = ["上一课", "上一节", "回到上一课", "previous lesson", "prev lesson"]
    return any(trigger in lowered for trigger in triggers)


def _is_free_question(message: str) -> bool:
    return message.startswith("【随时提问】")


def start_session(connection, request: StartSessionRequest) -> SessionSummary:
    plan = None
    if request.plan_id:
        plan = get_plan(connection, request.plan_id)
    else:
        plan = generate_page_window_study_plan(
            connection, request.book_id, request.page_window_size
        )

    if not plan.lessons:
        raise ValueError("Plan has no lessons.")

    learning_mode = normalize_learning_mode(request.learning_mode)
    session_id = _new_id("ses")
    created_at = utcnow_iso()
    connection.execute(
        """
        INSERT INTO sessions (
            id, book_id, plan_id, learner_name, learner_level, learning_mode,
            page_window_size, goals_json, current_lesson, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            request.book_id,
            plan.id,
            request.learner_name,
            request.learner_level,
            learning_mode,
            _clamp_page_window_size(request.page_window_size),
            json.dumps(request.goals, ensure_ascii=False),
            1,
            created_at,
            created_at,
        ),
    )
    connection.commit()

    current_lesson = plan.lessons[0]
    return SessionSummary(
        id=session_id,
        book_id=request.book_id,
        plan_id=plan.id,
        learner_name=request.learner_name,
        learner_level=request.learner_level,
        learning_mode=learning_mode,
        goals=request.goals,
        current_lesson=1,
        total_lessons=len(plan.lessons),
        current_lesson_title=current_lesson.title,
        current_page_start=current_lesson.page_start,
        current_page_end=current_lesson.page_end,
        page_window_size=_clamp_page_window_size(request.page_window_size),
        created_at=created_at,
        updated_at=created_at,
    )


def get_session_summary(connection, session_id: str) -> SessionSummary:
    session = _load_session(connection, session_id)
    plan = get_plan(connection, session["plan_id"])
    lesson = plan.lessons[session["current_lesson"] - 1]
    return SessionSummary(
        id=session["id"],
        book_id=session["book_id"],
        plan_id=session["plan_id"],
        learner_name=session["learner_name"],
        learner_level=session["learner_level"],
        learning_mode=_session_learning_mode(session),
        goals=json.loads(session["goals_json"]),
        current_lesson=session["current_lesson"],
        total_lessons=len(plan.lessons),
        current_lesson_title=lesson.title,
        current_page_start=lesson.page_start,
        current_page_end=lesson.page_end,
        page_window_size=_clamp_page_window_size(session["page_window_size"] or 12),
        created_at=session["created_at"],
        updated_at=session["updated_at"] or session["created_at"],
    )


def advance_session(connection, session_id: str) -> SessionSummary:
    session = _load_session(connection, session_id)
    plan = get_plan(connection, session["plan_id"])
    next_lesson = min(session["current_lesson"] + 1, len(plan.lessons))
    updated_at = utcnow_iso()
    connection.execute(
        "UPDATE sessions SET current_lesson = ?, updated_at = ? WHERE id = ?",
        (next_lesson, updated_at, session_id),
    )
    connection.commit()
    return get_session_summary(connection, session_id)


def retreat_session(connection, session_id: str) -> SessionSummary:
    session = _load_session(connection, session_id)
    previous_lesson = max(session["current_lesson"] - 1, 1)
    updated_at = utcnow_iso()
    connection.execute(
        "UPDATE sessions SET current_lesson = ?, updated_at = ? WHERE id = ?",
        (previous_lesson, updated_at, session_id),
    )
    connection.commit()
    return get_session_summary(connection, session_id)


def set_session_learning_mode(
    connection, session_id: str, learning_mode: str
) -> SessionSummary:
    _load_session(connection, session_id)
    normalized = normalize_learning_mode(learning_mode)
    updated_at = utcnow_iso()
    connection.execute(
        "UPDATE sessions SET learning_mode = ?, updated_at = ? WHERE id = ?",
        (normalized, updated_at, session_id),
    )
    connection.commit()
    return get_session_summary(connection, session_id)


def set_session_page_window_size(
    connection, session_id: str, page_window_size: int
) -> SessionSummary:
    session = _load_session(connection, session_id)
    normalized_size = _clamp_page_window_size(page_window_size)
    rebuild_page_window_plan_after_lesson(
        connection,
        session["plan_id"],
        keep_lesson_number=session["current_lesson"],
        window_pages=normalized_size,
    )
    updated_at = utcnow_iso()
    connection.execute(
        "DELETE FROM lesson_outputs WHERE session_id = ? AND lesson_number > ?",
        (session_id, session["current_lesson"]),
    )
    connection.execute(
        "UPDATE sessions SET page_window_size = ?, updated_at = ? WHERE id = ?",
        (normalized_size, updated_at, session_id),
    )
    connection.commit()
    return get_session_summary(connection, session_id)


def _build_prompt(
    learner_name: str,
    learner_level: str,
    learning_mode: str,
    book_title: str,
    current_lesson,
    history: list[dict[str, str]],
    references: list[ChunkReference],
    user_message: str,
    ask_new_question: bool,
) -> str:
    history_text = "\n".join(f"{item['role']}: {item['content']}" for item in history)
    reference_text = "\n\n".join(
        (
            f"[{ref.section_title}] p.{ref.page_start}-{ref.page_end}\n"
            f"{ref.excerpt}"
        )
        for ref in references
    )
    return get_learning_prompt(
        mode=learning_mode,
        book_title=book_title,
        chapter_title=current_lesson.title,
        chapter_content=reference_text or "暂无检索结果",
        user_level=learner_level,
        user_question=user_message,
        learner_name=learner_name,
        lesson_number=current_lesson.lesson_number,
        lesson_goal=current_lesson.goal,
        prerequisites=current_lesson.prerequisites,
        key_concepts=current_lesson.key_concepts,
        check_question=current_lesson.check_question,
        conversation_history=history_text or "暂无",
        ask_new_question=ask_new_question,
    )


def _lesson_references(
    connection,
    *,
    book_id: str,
    current_lesson,
    user_message: str,
    settings: Settings,
) -> list[ChunkReference]:
    if _is_free_question(user_message):
        query = " ".join([current_lesson.title, *current_lesson.key_concepts, user_message]).strip()
        retrieved = retrieve_chunks(
            connection,
            book_id=book_id,
            query=query,
            section_ids=current_lesson.section_ids,
            limit=settings.retrieval_limit,
        )
        excerpt_limit = 420
    else:
        retrieved = retrieve_page_window_chunks(
            connection,
            book_id=book_id,
            page_start=current_lesson.page_start,
            page_end=current_lesson.page_end,
            limit=settings.lesson_window_chunk_limit,
        )
        excerpt_limit = 900
        if not retrieved:
            query = " ".join([current_lesson.title, *current_lesson.key_concepts]).strip()
            retrieved = retrieve_chunks(
                connection,
                book_id=book_id,
                query=query,
                section_ids=current_lesson.section_ids,
                limit=settings.retrieval_limit,
            )
            excerpt_limit = 420

    return [
        ChunkReference(
            chunk_id=item["id"],
            section_title=item["section_title"],
            page_start=item["page_start"],
            page_end=item["page_end"],
            excerpt=item["content"][:excerpt_limit],
            score=item["score"],
        )
        for item in retrieved
    ]


def _call_llm(settings: Settings, prompt: str, learning_mode: str) -> tuple[str | None, str | None]:
    if not settings.llm_api_key and not settings.llm_base_url:
        return None, "未配置 LLM API Key 或 Base URL，无法生成学习内容。请先在网页左侧保存模型配置。"

    try:
        client = OpenAI(
            api_key=settings.llm_api_key or "dummy-key",
            base_url=settings.llm_base_url,
        )
        request_kwargs = dict(
            model=settings.llm_model,
            temperature=0.2,
            messages=[
                {
                    "role": "system",
                    "content": get_learning_system_message(learning_mode),
                },
                {"role": "user", "content": prompt},
            ],
        )
        if settings.llm_reasoning_effort:
            request_kwargs["reasoning_effort"] = settings.llm_reasoning_effort
        if settings.llm_thinking_type:
            request_kwargs["extra_body"] = {
                "thinking": {"type": settings.llm_thinking_type}
            }
        response = client.chat.completions.create(**request_kwargs)
        message = response.choices[0].message.content
        if isinstance(message, str):
            return message.strip(), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {str(exc)[:240]}"
    return None, "LLM 返回为空，未生成学习内容。"


def _format_reference_lines(references: list[ChunkReference]) -> list[str]:
    if not references:
        return ["- 这轮没有检索到很强的原文命中，我会先按当前 lesson 的目标搭框架。"]
    lines = ["- 书中可参考的片段："]
    for reference in references[:2]:
        excerpt = reference.excerpt.replace("\n", " ")
        lines.append(
            f"  - p.{reference.page_start}-{reference.page_end}《{reference.section_title}》：{excerpt}"
        )
    return lines


def _assistant_recently_asked_question(history: list[dict[str, str]]) -> bool:
    for item in reversed(history):
        if item["role"] != "assistant":
            continue
        content = item["content"]
        return "？" in content or "?" in content
    return False


def _user_requested_practice_prompt(message: str) -> bool:
    lowered = message.lower()
    triggers = [
        "quiz",
        "test me",
        "practice",
        "exercise",
        "debug",
        "练习",
        "习题",
        "提问",
        "问我",
        "测验",
        "测试",
        "检查",
        "考我",
        "讨论",
        "写作题",
        "debug",
        "报错",
    ]
    return any(trigger in lowered for trigger in triggers)


def _extract_page_window_directive(message: str) -> tuple[str, int | None]:
    pattern = re.compile(
        r"^\s*\[\[\s*NEXT_PAGE_WINDOW\s*:\s*(\d{1,3})\s*\]\]\s*$",
        re.MULTILINE,
    )
    match = pattern.search(message)
    if not match:
        return message, None
    page_window_size = _clamp_page_window_size(int(match.group(1)))
    cleaned = pattern.sub("", message).strip()
    return cleaned, page_window_size


def tutor_turn(
    connection,
    session_id: str,
    user_message: str,
    settings: Settings,
    learning_mode: str | None = None,
) -> TutorReply:
    session = _load_session(connection, session_id)
    plan = get_plan(connection, session["plan_id"])
    active_learning_mode = _session_learning_mode(session, learning_mode)

    _insert_message(connection, session_id, "user", user_message, [])

    if _is_next_lesson_request(user_message):
        summary = advance_session(connection, session_id)
        lesson = plan.lessons[summary.current_lesson - 1]
        saved_output = get_lesson_output(connection, session_id, summary.current_lesson)
        if saved_output is not None:
            connection.commit()
            return _reply_from_lesson_output(
                saved_output,
                can_advance=summary.current_lesson < summary.total_lessons,
            )
        assistant_message = (
            f"我们现在进入第{summary.current_lesson}课《{lesson.title}》。\n"
            f"这课的目标是：{lesson.goal}\n"
            f"我会围绕这个检查点带你推进：{lesson.check_question}"
        )
        reply = TutorReply(
            session_id=session_id,
            lesson_number=summary.current_lesson,
            lesson_title=lesson.title,
            learning_mode=active_learning_mode,
            reply_kind="navigation",
            llm_used=False,
            llm_error=None,
            assistant_message=assistant_message,
            references=[],
            suggested_next_action="answer_check_question",
            can_advance=summary.current_lesson < summary.total_lessons,
            prompt_preview=None,
        )
        _insert_message(connection, session_id, "assistant", assistant_message, [])
        connection.commit()
        return reply

    if _is_previous_lesson_request(user_message):
        summary = retreat_session(connection, session_id)
        lesson = plan.lessons[summary.current_lesson - 1]
        saved_output = get_lesson_output(connection, session_id, summary.current_lesson)
        if saved_output is not None:
            connection.commit()
            return _reply_from_lesson_output(
                saved_output,
                can_advance=summary.current_lesson < summary.total_lessons,
            )
        assistant_message = (
            f"我们回到第{summary.current_lesson}课《{lesson.title}》。\n"
            f"这课覆盖 p.{lesson.page_start}-{lesson.page_end}，目标是：{lesson.goal}"
        )
        reply = TutorReply(
            session_id=session_id,
            lesson_number=summary.current_lesson,
            lesson_title=lesson.title,
            learning_mode=active_learning_mode,
            reply_kind="navigation",
            llm_used=False,
            llm_error=None,
            assistant_message=assistant_message,
            references=[],
            suggested_next_action="continue_lesson",
            can_advance=summary.current_lesson < summary.total_lessons,
            prompt_preview=None,
        )
        _insert_message(connection, session_id, "assistant", assistant_message, [])
        connection.commit()
        return reply

    lesson_index = session["current_lesson"] - 1
    current_lesson = plan.lessons[lesson_index]
    is_free_question = _is_free_question(user_message)
    references = _lesson_references(
        connection,
        book_id=session["book_id"],
        current_lesson=current_lesson,
        user_message=user_message,
        settings=settings,
    )
    history = _recent_history(connection, session_id, settings.history_limit)
    ask_new_question = (
        _user_requested_practice_prompt(user_message)
        and not _assistant_recently_asked_question(history)
    )
    book_title = _load_book_title(connection, session["book_id"])
    prompt = _build_prompt(
        session["learner_name"],
        session["learner_level"],
        active_learning_mode,
        book_title,
        current_lesson,
        history,
        references,
        user_message,
        ask_new_question,
    )
    llm_message, llm_error = _call_llm(settings, prompt, active_learning_mode)
    llm_used = llm_message is not None
    if llm_message is None:
        assistant_message = (
            "模型调用失败，未生成本课学习内容。\n\n"
            f"错误信息：{llm_error or '未知错误'}\n\n"
            "请在网页左侧检查 API Key、Base URL、模型名称和推理参数，保存后重新发送。"
        )
        _insert_message(
            connection,
            session_id,
            "assistant",
            assistant_message,
            [reference.model_dump() for reference in references],
        )
        connection.commit()
        return TutorReply(
            session_id=session_id,
            lesson_number=current_lesson.lesson_number,
            lesson_title=current_lesson.title,
            learning_mode=active_learning_mode,
            reply_kind="error",
            llm_used=False,
            llm_error=llm_error,
            assistant_message=assistant_message,
            references=references,
            suggested_next_action="fix_llm_settings",
            can_advance=current_lesson.lesson_number < len(plan.lessons),
            prompt_preview=prompt,
        )

    assistant_message = llm_message
    adapted_page_window_size = None
    if llm_message:
        assistant_message, recommended_page_window_size = _extract_page_window_directive(
            assistant_message
        )
        if recommended_page_window_size is not None:
            summary = set_session_page_window_size(
                connection, session_id, recommended_page_window_size
            )
            adapted_page_window_size = summary.page_window_size
    latest_total_lessons = (
        get_session_summary(connection, session_id).total_lessons
        if adapted_page_window_size is not None
        else len(plan.lessons)
    )

    _insert_message(
        connection,
        session_id,
        "assistant",
        assistant_message,
        [reference.model_dump() for reference in references],
    )
    if not is_free_question:
        _save_lesson_output(
            connection,
            session_id=session_id,
            lesson_number=current_lesson.lesson_number,
            lesson_title=current_lesson.title,
            learning_mode=active_learning_mode,
            assistant_message=assistant_message,
            references=references,
            llm_used=llm_used,
            llm_error=None if llm_used else llm_error,
        )
    connection.commit()

    return TutorReply(
        session_id=session_id,
        lesson_number=current_lesson.lesson_number,
        lesson_title=current_lesson.title,
        learning_mode=active_learning_mode,
        reply_kind="question" if is_free_question else "lesson",
        llm_used=llm_used,
        llm_error=None if llm_used else llm_error,
        assistant_message=assistant_message,
        references=references,
        suggested_next_action="answer_check_question",
        can_advance=current_lesson.lesson_number < latest_total_lessons,
        adapted_page_window_size=adapted_page_window_size,
        prompt_preview=prompt,
    )
