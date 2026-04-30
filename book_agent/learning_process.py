from __future__ import annotations

import json
from pathlib import Path

from book_agent.ingest import import_book
from book_agent.learning_modes import DEFAULT_LEARNING_MODE
from book_agent.planner import generate_page_window_study_plan, generate_study_plan
from book_agent.schemas import (
    BookSummary,
    ImportBookResult,
    LearningSessionSummary,
    StartSessionRequest,
    StudyPlan,
)
from book_agent.tutor import start_session


def import_book_with_learning_process(
    connection,
    *,
    pdf_path: str | Path,
    title: str | None = None,
    max_lessons: int | None = None,
    page_window_size: int = 12,
    learner_name: str = "learner",
    learner_level: str = "beginner",
    learning_mode: str = DEFAULT_LEARNING_MODE,
    goals: list[str] | None = None,
) -> ImportBookResult:
    book = import_book(connection, pdf_path, title)
    return create_learning_process_for_book(
        connection,
        book_id=book.id,
        max_lessons=max_lessons,
        page_window_size=page_window_size,
        learner_name=learner_name,
        learner_level=learner_level,
        learning_mode=learning_mode,
        goals=goals or [],
        book=book,
    )


def create_learning_process_for_book(
    connection,
    *,
    book_id: str,
    max_lessons: int | None = None,
    page_window_size: int = 12,
    learner_name: str = "learner",
    learner_level: str = "beginner",
    learning_mode: str = DEFAULT_LEARNING_MODE,
    goals: list[str] | None = None,
    book=None,
) -> ImportBookResult:
    plan = (
        generate_study_plan(connection, book_id, max_lessons)
        if max_lessons is not None
        else generate_page_window_study_plan(connection, book_id, page_window_size)
    )
    session = start_session(
        connection,
        StartSessionRequest(
            book_id=book_id,
            plan_id=plan.id,
            learner_name=learner_name,
            learner_level=learner_level,
            learning_mode=learning_mode,
            page_window_size=page_window_size,
            goals=goals or [],
        ),
    )
    if book is None:
        book = _book_summary(connection, book_id)
    return ImportBookResult(book=book, plan=plan, session=session)


def list_learning_sessions(connection, limit: int = 20) -> list[LearningSessionSummary]:
    rows = connection.execute(
        """
        SELECT
            s.*,
            b.title AS book_title,
            p.title AS plan_title,
            p.plan_json AS plan_json
        FROM sessions s
        JOIN books b ON b.id = s.book_id
        JOIN plans p ON p.id = s.plan_id
        ORDER BY COALESCE(s.updated_at, s.created_at) DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [_learning_session_from_row(row) for row in rows]


def delete_learning_session(connection, session_id: str) -> bool:
    cursor = connection.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    connection.commit()
    return cursor.rowcount > 0


def delete_all_learning_sessions(connection) -> int:
    cursor = connection.execute("DELETE FROM sessions")
    connection.commit()
    return cursor.rowcount


def _book_summary(connection, book_id: str):
    row = connection.execute(
        """
        SELECT
            b.*,
            COUNT(DISTINCT s.id) AS section_count,
            COUNT(DISTINCT c.id) AS chunk_count
        FROM books b
        LEFT JOIN sections s ON s.book_id = b.id
        LEFT JOIN chunks c ON c.book_id = b.id
        WHERE b.id = ?
        GROUP BY b.id
        """,
        (book_id,),
    ).fetchone()
    if not row:
        raise ValueError(f"Book not found: {book_id}")
    return BookSummary(
        id=row["id"],
        title=row["title"],
        source_path=row["source_path"],
        page_count=row["page_count"],
        section_count=row["section_count"],
        chunk_count=row["chunk_count"],
        imported_at=row["imported_at"],
    )


def _learning_session_from_row(row) -> LearningSessionSummary:
    plan = StudyPlan.model_validate(json.loads(row["plan_json"]))
    total_lessons = len(plan.lessons)
    current_lesson = max(1, min(int(row["current_lesson"]), total_lessons or 1))
    lesson_title = (
        plan.lessons[current_lesson - 1].title
        if total_lessons
        else "暂无 lesson"
    )
    progress_percent = round((current_lesson / total_lessons) * 100, 1) if total_lessons else 0.0
    return LearningSessionSummary(
        id=row["id"],
        book_id=row["book_id"],
        plan_id=row["plan_id"],
        learner_name=row["learner_name"],
        learner_level=row["learner_level"],
        learning_mode=row["learning_mode"],
        page_window_size=row["page_window_size"],
        goals=json.loads(row["goals_json"]),
        current_lesson=current_lesson,
        total_lessons=total_lessons,
        current_lesson_title=lesson_title,
        current_page_start=plan.lessons[current_lesson - 1].page_start if total_lessons else 1,
        current_page_end=plan.lessons[current_lesson - 1].page_end if total_lessons else 1,
        created_at=row["created_at"],
        updated_at=row["updated_at"] or row["created_at"],
        book_title=row["book_title"],
        plan_title=row["plan_title"],
        progress_percent=progress_percent,
    )
