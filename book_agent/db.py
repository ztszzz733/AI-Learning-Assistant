from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from book_agent.config import Settings, get_settings


def utcnow_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def connect_database(
    database_path: Path | None = None, settings: Settings | None = None
) -> sqlite3.Connection:
    active_settings = settings or get_settings()
    active_settings.ensure_directories()
    db_path = database_path or active_settings.database_path
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    # MEMORY journaling is more tolerant in sandboxed Windows workspaces than WAL.
    connection.execute("PRAGMA journal_mode = MEMORY;")
    connection.execute("PRAGMA synchronous = NORMAL;")
    initialize_database(connection)
    return connection


def initialize_database(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS books (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            source_path TEXT NOT NULL,
            page_count INTEGER NOT NULL,
            toc_json TEXT NOT NULL,
            imported_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sections (
            id TEXT PRIMARY KEY,
            book_id TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
            parent_id TEXT REFERENCES sections(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            level INTEGER NOT NULL,
            start_page INTEGER NOT NULL,
            end_page INTEGER NOT NULL,
            ordinal INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS chunks (
            id TEXT PRIMARY KEY,
            book_id TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
            section_id TEXT NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
            section_title TEXT NOT NULL,
            page_start INTEGER NOT NULL,
            page_end INTEGER NOT NULL,
            ordinal INTEGER NOT NULL,
            content TEXT NOT NULL,
            token_count INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS plans (
            id TEXT PRIMARY KEY,
            book_id TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            plan_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            book_id TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
            plan_id TEXT NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
            learner_name TEXT NOT NULL,
            learner_level TEXT NOT NULL,
            learning_mode TEXT NOT NULL DEFAULT 'humanities',
            page_window_size INTEGER NOT NULL DEFAULT 12,
            goals_json TEXT NOT NULL,
            current_lesson INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            retrieval_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS lesson_outputs (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            lesson_number INTEGER NOT NULL,
            lesson_title TEXT NOT NULL,
            learning_mode TEXT NOT NULL,
            assistant_message TEXT NOT NULL,
            references_json TEXT NOT NULL,
            llm_used INTEGER NOT NULL,
            llm_error TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_sections_book_ordinal ON sections(book_id, ordinal);
        CREATE INDEX IF NOT EXISTS idx_chunks_book_section ON chunks(book_id, section_id, ordinal);
        CREATE INDEX IF NOT EXISTS idx_plans_book ON plans(book_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_sessions_book ON sessions(book_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_messages_session_created ON messages(session_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_lesson_outputs_session_lesson
            ON lesson_outputs(session_id, lesson_number, created_at DESC);

        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            chunk_id UNINDEXED,
            book_id UNINDEXED,
            section_title,
            content
        );
        """
    )
    _ensure_session_learning_mode_column(connection)
    _ensure_session_updated_at_column(connection)
    _ensure_session_page_window_size_column(connection)
    connection.commit()


def _ensure_session_learning_mode_column(connection: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(sessions)").fetchall()
    }
    if "learning_mode" not in columns:
        connection.execute(
            "ALTER TABLE sessions ADD COLUMN learning_mode TEXT NOT NULL DEFAULT 'humanities'"
        )


def _ensure_session_updated_at_column(connection: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(sessions)").fetchall()
    }
    if "updated_at" not in columns:
        connection.execute("ALTER TABLE sessions ADD COLUMN updated_at TEXT")
    connection.execute(
        """
        UPDATE sessions
        SET updated_at = created_at
        WHERE updated_at IS NULL OR updated_at = ''
        """
    )


def _ensure_session_page_window_size_column(connection: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(sessions)").fetchall()
    }
    if "page_window_size" not in columns:
        connection.execute(
            "ALTER TABLE sessions ADD COLUMN page_window_size INTEGER NOT NULL DEFAULT 12"
        )
    connection.execute(
        """
        UPDATE sessions
        SET page_window_size = 12
        WHERE page_window_size IS NULL OR page_window_size < 1
        """
    )
