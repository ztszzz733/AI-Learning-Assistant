from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import fitz

from book_agent.db import connect_database, utcnow_iso
from book_agent.ingest import import_book
from book_agent.planner import generate_study_plan
from book_agent.retrieval import retrieve_chunks


def _create_focus_pdf(pdf_path: Path) -> None:
    document = fitz.open()
    pages = [
        "Preface page. This is context about why the book was written.",
        "Core ideas page. Core definitions and mental models live here.",
        "Practice page. Practice methods and worked examples live here.",
        "Appendix page. Reference tables live here.",
    ]
    for text in pages:
        page = document.new_page()
        page.insert_text((72, 72), text)
    document.set_toc(
        [
            [1, "序言", 1],
            [1, "第一章 基础概念", 2],
            [1, "第二章 练习方法", 3],
            [1, "附录", 4],
        ]
    )
    document.save(pdf_path)
    document.close()


def test_study_plan_deemphasizes_preface_and_appendix() -> None:
    run_dir = Path("data/test_runs") / f"focus_{uuid.uuid4().hex[:8]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = run_dir / "focus.pdf"
    _create_focus_pdf(pdf_path)

    connection = connect_database(database_path=run_dir / "focus.sqlite3")
    try:
        book = import_book(connection, pdf_path)
        plan = generate_study_plan(connection, book.id, max_lessons=4)

        lesson_titles = [lesson.title for lesson in plan.lessons]
        covered_titles = [title for lesson in plan.lessons for title in lesson.section_titles]

        assert lesson_titles
        assert lesson_titles[0] == "第一章 基础概念"
        assert "序言" not in covered_titles
        assert "附录" not in covered_titles
        assert plan.lessons[0].prerequisites[0].startswith("本计划默认弱化")
    finally:
        connection.close()
        shutil.rmtree(run_dir, ignore_errors=True)


def test_retrieval_downweights_supporting_material_unless_requested() -> None:
    run_dir = Path("data/test_runs") / f"retrieval_{uuid.uuid4().hex[:8]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    connection = connect_database(database_path=run_dir / "retrieval.sqlite3")
    try:
        book_id = "book_focus"
        imported_at = utcnow_iso()
        connection.execute(
            """
            INSERT INTO books (id, title, source_path, page_count, toc_json, imported_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (book_id, "focus", str(run_dir / "focus.pdf"), 3, "[]", imported_at),
        )
        connection.execute(
            """
            INSERT INTO sections (id, book_id, parent_id, title, level, start_page, end_page, ordinal)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("sec_preface", book_id, None, "序言", 1, 1, 1, 1),
        )
        connection.execute(
            """
            INSERT INTO sections (id, book_id, parent_id, title, level, start_page, end_page, ordinal)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("sec_core", book_id, None, "第一章 基础概念", 1, 2, 2, 2),
        )
        connection.execute(
            """
            INSERT INTO chunks (
                id, book_id, section_id, section_title, page_start, page_end, ordinal, content, token_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "chk_preface",
                book_id,
                "sec_preface",
                "序言",
                1,
                1,
                1,
                "基础概念会在后文详细展开，这里只是写作缘起。",
                16,
            ),
        )
        connection.execute(
            """
            INSERT INTO chunks (
                id, book_id, section_id, section_title, page_start, page_end, ordinal, content, token_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "chk_core",
                book_id,
                "sec_core",
                "第一章 基础概念",
                2,
                2,
                1,
                "基础概念定义了本书后续所有推理和练习的共同语言。",
                18,
            ),
        )
        connection.execute(
            """
            INSERT INTO chunks_fts (chunk_id, book_id, section_title, content)
            VALUES (?, ?, ?, ?)
            """,
            ("chk_preface", book_id, "序言", "基础概念会在后文详细展开，这里只是写作缘起。"),
        )
        connection.execute(
            """
            INSERT INTO chunks_fts (chunk_id, book_id, section_title, content)
            VALUES (?, ?, ?, ?)
            """,
            (
                "chk_core",
                book_id,
                "第一章 基础概念",
                "基础概念定义了本书后续所有推理和练习的共同语言。",
            ),
        )
        connection.commit()

        generic_results = retrieve_chunks(connection, book_id=book_id, query="基础概念是什么", limit=2)
        explicit_results = retrieve_chunks(connection, book_id=book_id, query="序言主要讲了什么", limit=2)

        assert generic_results[0]["section_title"] == "第一章 基础概念"
        assert explicit_results[0]["section_title"] == "序言"
    finally:
        connection.close()
        shutil.rmtree(run_dir, ignore_errors=True)
