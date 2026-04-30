from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import fitz

from book_agent.config import Settings
from book_agent.db import connect_database
from book_agent.ingest import import_book
from book_agent.learning_process import (
    delete_all_learning_sessions,
    delete_learning_session,
    import_book_with_learning_process,
    list_learning_sessions,
)
from book_agent.planner import generate_study_plan
from book_agent.schemas import StartSessionRequest
from book_agent.tutor import (
    advance_session,
    get_lesson_output,
    retreat_session,
    set_session_page_window_size,
    start_session,
    tutor_turn,
)


def _create_sample_pdf(pdf_path: Path) -> None:
    document = fitz.open()
    pages = [
        "Introduction\nLearning means building structure before details.",
        "Core Concepts\nChunking helps a tutor retrieve only relevant passages.",
        "Practice\nA good study agent asks check questions and keeps pace.",
    ]
    for text in pages:
        page = document.new_page()
        page.insert_text((72, 72), text)
    document.set_toc(
        [
            [1, "Introduction", 1],
            [1, "Core Concepts", 2],
            [1, "Practice", 3],
        ]
    )
    document.save(pdf_path)
    document.close()


def test_end_to_end_pipeline(monkeypatch) -> None:
    run_dir = Path("data/test_runs") / f"pipeline_{uuid.uuid4().hex[:8]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = run_dir / "sample.pdf"
    _create_sample_pdf(pdf_path)

    settings = Settings(
        data_dir=run_dir / "data",
        database_path=run_dir / "data" / "test.sqlite3",
    )
    connection = connect_database(settings=settings)
    try:
        monkeypatch.setattr(
            "book_agent.tutor._call_llm",
            lambda settings, prompt, learning_mode: ("模型学习内容", None),
        )
        book = import_book(connection, pdf_path)
        assert book.page_count == 3
        assert book.section_count == 3
        assert book.chunk_count >= 3

        plan = generate_study_plan(connection, book.id, max_lessons=2)
        assert len(plan.lessons) == 2
        assert plan.lessons[0].title

        session = start_session(
            connection,
            StartSessionRequest(book_id=book.id, plan_id=plan.id, learner_name="tester"),
        )
        reply = tutor_turn(connection, session.id, "Teach me lesson one.", settings)

        assert reply.lesson_number == 1
        assert reply.lesson_title
        assert reply.assistant_message
        assert reply.references
    finally:
        connection.close()
        shutil.rmtree(run_dir, ignore_errors=True)


def test_import_book_creates_resumable_learning_process() -> None:
    run_dir = Path("data/test_runs") / f"process_{uuid.uuid4().hex[:8]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = run_dir / "sample.pdf"
    _create_sample_pdf(pdf_path)

    settings = Settings(
        data_dir=run_dir / "data",
        database_path=run_dir / "data" / "test.sqlite3",
    )
    connection = connect_database(settings=settings)
    try:
        result = import_book_with_learning_process(
            connection,
            pdf_path=pdf_path,
            max_lessons=2,
            learner_name="tester",
            learning_mode="programming",
        )

        sessions = list_learning_sessions(connection)

        assert result.book.title
        assert result.plan.lessons
        assert result.session.learning_mode == "programming"
        assert result.session.current_lesson == 1
        assert sessions[0].id == result.session.id
        assert sessions[0].book_title == result.book.title
        assert sessions[0].progress_percent == 50.0

        advanced = advance_session(connection, result.session.id)
        refreshed = list_learning_sessions(connection)[0]

        assert advanced.current_lesson == 2
        assert refreshed.current_lesson == 2
        assert refreshed.progress_percent == 100.0
        assert refreshed.updated_at >= refreshed.created_at
    finally:
        connection.close()
        shutil.rmtree(run_dir, ignore_errors=True)


def test_import_book_defaults_to_page_window_plan() -> None:
    run_dir = Path("data/test_runs") / f"window_{uuid.uuid4().hex[:8]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = run_dir / "sample.pdf"
    _create_sample_pdf(pdf_path)

    settings = Settings(
        data_dir=run_dir / "data",
        database_path=run_dir / "data" / "test.sqlite3",
    )
    connection = connect_database(settings=settings)
    try:
        result = import_book_with_learning_process(
            connection,
            pdf_path=pdf_path,
            page_window_size=2,
        )

        assert len(result.plan.lessons) == 2
        assert result.plan.lessons[0].page_start == 1
        assert result.plan.lessons[0].page_end == 2
        assert result.plan.lessons[1].page_start == 3
        assert "页码窗口" in result.plan.title

        second = advance_session(connection, result.session.id)
        assert second.current_lesson == 2
        first = retreat_session(connection, result.session.id)
        assert first.current_lesson == 1
        assert result.session.page_window_size == 2
        assert result.session.current_page_start == 1
        assert result.session.current_page_end == 2
    finally:
        connection.close()
        shutil.rmtree(run_dir, ignore_errors=True)


def test_lesson_outputs_are_saved_separately_from_free_questions(monkeypatch) -> None:
    run_dir = Path("data/test_runs") / f"lesson_output_{uuid.uuid4().hex[:8]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = run_dir / "sample.pdf"
    _create_sample_pdf(pdf_path)

    settings = Settings(
        data_dir=run_dir / "data",
        database_path=run_dir / "data" / "test.sqlite3",
    )
    connection = connect_database(settings=settings)
    try:
        monkeypatch.setattr(
            "book_agent.tutor._call_llm",
            lambda settings, prompt, learning_mode: ("模型学习内容", None),
        )
        result = import_book_with_learning_process(
            connection,
            pdf_path=pdf_path,
            page_window_size=1,
        )

        reply = tutor_turn(connection, result.session.id, "Teach this lesson.", settings)
        saved = get_lesson_output(connection, result.session.id, 1)
        output_count = connection.execute(
            "SELECT COUNT(*) AS count FROM lesson_outputs WHERE session_id = ?",
            (result.session.id,),
        ).fetchone()["count"]

        assert reply.reply_kind == "lesson"
        assert saved is not None
        assert saved.assistant_message == reply.assistant_message
        assert output_count == 1

        question_reply = tutor_turn(
            connection,
            result.session.id,
            "【随时提问】What does chunking mean?",
            settings,
        )
        output_count_after_question = connection.execute(
            "SELECT COUNT(*) AS count FROM lesson_outputs WHERE session_id = ?",
            (result.session.id,),
        ).fetchone()["count"]

        assert question_reply.reply_kind == "question"
        assert output_count_after_question == 1

        advance_session(connection, result.session.id)
        review = tutor_turn(connection, result.session.id, "上一课", settings)
        assert review.suggested_next_action == "review_saved_lesson"
        assert review.assistant_message == reply.assistant_message
    finally:
        connection.close()
        shutil.rmtree(run_dir, ignore_errors=True)


def test_llm_failure_does_not_create_learning_output() -> None:
    run_dir = Path("data/test_runs") / f"llm_failure_{uuid.uuid4().hex[:8]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = run_dir / "sample.pdf"
    _create_sample_pdf(pdf_path)

    settings = Settings(
        data_dir=run_dir / "data",
        database_path=run_dir / "data" / "test.sqlite3",
    )
    connection = connect_database(settings=settings)
    try:
        result = import_book_with_learning_process(
            connection,
            pdf_path=pdf_path,
            page_window_size=1,
        )

        reply = tutor_turn(connection, result.session.id, "Teach this lesson.", settings)
        saved = get_lesson_output(connection, result.session.id, 1)

        assert reply.reply_kind == "error"
        assert reply.llm_used is False
        assert "模型调用失败" in reply.assistant_message
        assert saved is None
    finally:
        connection.close()
        shutil.rmtree(run_dir, ignore_errors=True)


def test_session_page_window_can_rebuild_future_lessons() -> None:
    run_dir = Path("data/test_runs") / f"adaptive_window_{uuid.uuid4().hex[:8]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = run_dir / "sample.pdf"
    _create_sample_pdf(pdf_path)

    settings = Settings(
        data_dir=run_dir / "data",
        database_path=run_dir / "data" / "test.sqlite3",
    )
    connection = connect_database(settings=settings)
    try:
        result = import_book_with_learning_process(
            connection,
            pdf_path=pdf_path,
            page_window_size=1,
        )
        assert len(result.plan.lessons) == 3

        summary = set_session_page_window_size(connection, result.session.id, 2)
        plan = connection.execute(
            "SELECT plan_json FROM plans WHERE id = ?", (summary.plan_id,)
        ).fetchone()

        assert summary.page_window_size == 2
        assert summary.current_page_start == 1
        assert summary.current_page_end == 1
        assert summary.total_lessons == 2
        assert '"page_start":2' in plan["plan_json"]
        assert '"page_end":3' in plan["plan_json"]
    finally:
        connection.close()
        shutil.rmtree(run_dir, ignore_errors=True)


def test_delete_learning_sessions() -> None:
    run_dir = Path("data/test_runs") / f"delete_{uuid.uuid4().hex[:8]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = run_dir / "sample.pdf"
    _create_sample_pdf(pdf_path)

    settings = Settings(
        data_dir=run_dir / "data",
        database_path=run_dir / "data" / "test.sqlite3",
    )
    connection = connect_database(settings=settings)
    try:
        first = import_book_with_learning_process(
            connection,
            pdf_path=pdf_path,
            max_lessons=2,
            learner_name="tester",
        )
        second = import_book_with_learning_process(
            connection,
            pdf_path=pdf_path,
            max_lessons=2,
            learner_name="tester",
        )

        assert len(list_learning_sessions(connection)) == 2
        assert delete_learning_session(connection, first.session.id) is True
        assert delete_learning_session(connection, first.session.id) is False
        remaining = list_learning_sessions(connection)
        assert len(remaining) == 1
        assert remaining[0].id == second.session.id

        assert delete_all_learning_sessions(connection) == 1
        assert list_learning_sessions(connection) == []
    finally:
        connection.close()
        shutil.rmtree(run_dir, ignore_errors=True)
