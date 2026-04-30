from __future__ import annotations

import argparse
import json
from contextlib import closing
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from book_agent.config import get_settings
from book_agent.db import connect_database
from book_agent.learning_process import (
    delete_all_learning_sessions,
    delete_learning_session,
    import_book_with_learning_process,
    list_learning_sessions,
)
from book_agent.llm_settings import (
    get_public_llm_settings,
    save_llm_settings,
    settings_from_database,
)
from book_agent.planner import generate_study_plan, get_plan
from book_agent.schemas import (
    BookDetail,
    BookSummary,
    GeneratePlanRequest,
    ImportBookResult,
    ImportBookRequest,
    LearningSessionSummary,
    LessonOutput,
    LLMSettingsPublic,
    LLMSettingsUpdate,
    SetLearningModeRequest,
    SetPageWindowSizeRequest,
    SessionSummary,
    StartSessionRequest,
    StudyPlan,
    TutorMessageRequest,
    TutorReply,
)
from book_agent.tutor import (
    advance_session,
    get_lesson_output,
    get_session_summary,
    retreat_session,
    set_session_learning_mode,
    set_session_page_window_size,
    start_session,
    tutor_turn,
)

app = FastAPI(title="Book-Grounded Learning Agent", version="0.1.0")
WEB_DIR = Path(__file__).resolve().parent / "web"
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


def _book_summary_from_row(row) -> BookSummary:
    return BookSummary(
        id=row["id"],
        title=row["title"],
        source_path=row["source_path"],
        page_count=row["page_count"],
        section_count=row["section_count"],
        chunk_count=row["chunk_count"],
        imported_at=row["imported_at"],
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/app", response_class=FileResponse)
def web_app() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/settings/llm", response_model=LLMSettingsPublic)
def get_llm_settings_endpoint() -> LLMSettingsPublic:
    with closing(connect_database()) as connection:
        return get_public_llm_settings(connection)


@app.patch("/settings/llm", response_model=LLMSettingsPublic)
def update_llm_settings_endpoint(request: LLMSettingsUpdate) -> LLMSettingsPublic:
    with closing(connect_database()) as connection:
        return save_llm_settings(connection, request)


@app.post("/books/import", response_model=ImportBookResult)
def import_book_endpoint(request: ImportBookRequest) -> ImportBookResult:
    with closing(connect_database()) as connection:
        try:
            return import_book_with_learning_process(
                connection,
                pdf_path=request.pdf_path,
                title=request.title,
                max_lessons=request.max_lessons,
                page_window_size=request.page_window_size,
                learner_name=request.learner_name,
                learner_level=request.learner_level,
                learning_mode=request.learning_mode,
                goals=request.goals,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/books", response_model=list[BookSummary])
def list_books() -> list[BookSummary]:
    with closing(connect_database()) as connection:
        rows = connection.execute(
            """
            SELECT
                b.*,
                COUNT(DISTINCT s.id) AS section_count,
                COUNT(DISTINCT c.id) AS chunk_count
            FROM books b
            LEFT JOIN sections s ON s.book_id = b.id
            LEFT JOIN chunks c ON c.book_id = b.id
            GROUP BY b.id
            ORDER BY b.imported_at DESC
            """
        ).fetchall()
        return [_book_summary_from_row(row) for row in rows]


@app.get("/books/{book_id}", response_model=BookDetail)
def get_book(book_id: str) -> BookDetail:
    with closing(connect_database()) as connection:
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
            raise HTTPException(status_code=404, detail="Book not found.")

        sections = connection.execute(
            "SELECT * FROM sections WHERE book_id = ? ORDER BY ordinal", (book_id,)
        ).fetchall()
        plans = connection.execute(
            "SELECT id, title, created_at FROM plans WHERE book_id = ? ORDER BY created_at DESC",
            (book_id,),
        ).fetchall()
        return BookDetail(
            book=_book_summary_from_row(row),
            sections=[dict(section) for section in sections],
            plans=[dict(plan) for plan in plans],
        )


@app.post("/plans/generate", response_model=StudyPlan)
def generate_plan_endpoint(request: GeneratePlanRequest) -> StudyPlan:
    with closing(connect_database()) as connection:
        try:
            return generate_study_plan(connection, request.book_id, request.max_lessons)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/plans/{plan_id}", response_model=StudyPlan)
def get_plan_endpoint(plan_id: str) -> StudyPlan:
    with closing(connect_database()) as connection:
        try:
            return get_plan(connection, plan_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/sessions", response_model=SessionSummary)
def start_session_endpoint(request: StartSessionRequest) -> SessionSummary:
    with closing(connect_database()) as connection:
        try:
            return start_session(connection, request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/sessions", response_model=list[LearningSessionSummary])
def list_sessions_endpoint(limit: int = 20) -> list[LearningSessionSummary]:
    with closing(connect_database()) as connection:
        return list_learning_sessions(connection, limit)


@app.delete("/sessions")
def delete_all_sessions_endpoint() -> dict[str, int]:
    with closing(connect_database()) as connection:
        deleted = delete_all_learning_sessions(connection)
        return {"deleted": deleted}


@app.get("/sessions/{session_id}", response_model=SessionSummary)
def get_session_endpoint(session_id: str) -> SessionSummary:
    with closing(connect_database()) as connection:
        try:
            return get_session_summary(connection, session_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get(
    "/sessions/{session_id}/lessons/{lesson_number}/output",
    response_model=LessonOutput | None,
)
def get_lesson_output_endpoint(
    session_id: str, lesson_number: int
) -> LessonOutput | None:
    with closing(connect_database()) as connection:
        try:
            return get_lesson_output(connection, session_id, lesson_number)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/sessions/{session_id}")
def delete_session_endpoint(session_id: str) -> dict[str, str | bool]:
    with closing(connect_database()) as connection:
        deleted = delete_learning_session(connection, session_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Session not found.")
        return {"deleted": True, "session_id": session_id}


@app.post("/sessions/{session_id}/messages", response_model=TutorReply)
def tutor_message_endpoint(session_id: str, request: TutorMessageRequest) -> TutorReply:
    with closing(connect_database()) as connection:
        try:
            return tutor_turn(
                connection,
                session_id,
                request.message,
                settings_from_database(connection, get_settings()),
                learning_mode=request.learning_mode,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.patch("/sessions/{session_id}/learning-mode", response_model=SessionSummary)
def set_session_learning_mode_endpoint(
    session_id: str, request: SetLearningModeRequest
) -> SessionSummary:
    with closing(connect_database()) as connection:
        try:
            return set_session_learning_mode(connection, session_id, request.learning_mode)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.patch("/sessions/{session_id}/page-window", response_model=SessionSummary)
def set_session_page_window_endpoint(
    session_id: str, request: SetPageWindowSizeRequest
) -> SessionSummary:
    with closing(connect_database()) as connection:
        try:
            return set_session_page_window_size(
                connection, session_id, request.page_window_size
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/sessions/{session_id}/advance", response_model=SessionSummary)
def advance_session_endpoint(session_id: str) -> SessionSummary:
    with closing(connect_database()) as connection:
        try:
            return advance_session(connection, session_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/sessions/{session_id}/retreat", response_model=SessionSummary)
def retreat_session_endpoint(session_id: str) -> SessionSummary:
    with closing(connect_database()) as connection:
        try:
            return retreat_session(connection, session_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/")
def root() -> dict[str, object]:
    with closing(connect_database()) as connection:
        books = connection.execute("SELECT COUNT(*) AS count FROM books").fetchone()["count"]
        plans = connection.execute("SELECT COUNT(*) AS count FROM plans").fetchone()["count"]
        sessions = connection.execute("SELECT COUNT(*) AS count FROM sessions").fetchone()["count"]
    return {
        "name": "Book-Grounded Learning Agent",
        "books": books,
        "plans": plans,
        "sessions": sessions,
    }


def run(host: str = "127.0.0.1", port: int = 8001) -> None:
    uvicorn.run("book_agent.main:app", host=host, port=port, reload=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Book Agent web/API server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    run(args.host, args.port)


if __name__ == "__main__":
    main()
