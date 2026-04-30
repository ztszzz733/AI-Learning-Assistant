from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from book_agent.learning_modes import DEFAULT_LEARNING_MODE, LearningMode


class ImportBookRequest(BaseModel):
    pdf_path: str
    title: str | None = None
    max_lessons: int | None = None
    page_window_size: int = Field(default=12, ge=1, le=60)
    learner_name: str = "learner"
    learner_level: str = "beginner"
    learning_mode: LearningMode = DEFAULT_LEARNING_MODE
    goals: list[str] = Field(default_factory=list)


class BookSummary(BaseModel):
    id: str
    title: str
    source_path: str
    page_count: int
    section_count: int
    chunk_count: int
    imported_at: str


class ChunkReference(BaseModel):
    chunk_id: str
    section_title: str
    page_start: int
    page_end: int
    excerpt: str
    score: float


class LessonPlan(BaseModel):
    lesson_number: int
    title: str
    section_ids: list[str] = Field(default_factory=list)
    section_titles: list[str] = Field(default_factory=list)
    page_start: int
    page_end: int
    goal: str
    prerequisites: list[str] = Field(default_factory=list)
    key_concepts: list[str] = Field(default_factory=list)
    practice_tasks: list[str] = Field(default_factory=list)
    check_question: str


class StudyPlan(BaseModel):
    id: str
    book_id: str
    title: str
    created_at: str
    lessons: list[LessonPlan] = Field(default_factory=list)


class GeneratePlanRequest(BaseModel):
    book_id: str
    max_lessons: int | None = None


class StartSessionRequest(BaseModel):
    book_id: str
    plan_id: str | None = None
    learner_name: str = "learner"
    learner_level: str = "beginner"
    learning_mode: LearningMode = DEFAULT_LEARNING_MODE
    page_window_size: int = Field(default=12, ge=1, le=60)
    goals: list[str] = Field(default_factory=list)


class SessionSummary(BaseModel):
    id: str
    book_id: str
    plan_id: str
    learner_name: str
    learner_level: str
    learning_mode: LearningMode = DEFAULT_LEARNING_MODE
    goals: list[str] = Field(default_factory=list)
    current_lesson: int
    total_lessons: int
    current_lesson_title: str
    current_page_start: int
    current_page_end: int
    page_window_size: int
    created_at: str
    updated_at: str


class LearningSessionSummary(SessionSummary):
    book_title: str
    plan_title: str
    progress_percent: float


class ImportBookResult(BaseModel):
    book: BookSummary
    plan: StudyPlan
    session: SessionSummary


class TutorMessageRequest(BaseModel):
    message: str
    learning_mode: LearningMode | None = None


class SetLearningModeRequest(BaseModel):
    learning_mode: LearningMode


class SetPageWindowSizeRequest(BaseModel):
    page_window_size: int = Field(ge=1, le=60)


class LLMSettingsUpdate(BaseModel):
    api_key: str | None = None
    clear_api_key: bool = False
    base_url: str | None = None
    model: str | None = None
    reasoning_effort: str | None = None
    thinking_type: str | None = None


class LLMSettingsPublic(BaseModel):
    has_api_key: bool
    api_key_preview: str | None = None
    base_url: str | None = None
    model: str
    reasoning_effort: str | None = None
    thinking_type: str | None = None
    backend_label: str


class TutorReply(BaseModel):
    session_id: str
    lesson_number: int
    lesson_title: str
    learning_mode: LearningMode = DEFAULT_LEARNING_MODE
    reply_kind: str = "lesson"
    llm_used: bool = False
    llm_error: str | None = None
    assistant_message: str
    references: list[ChunkReference] = Field(default_factory=list)
    suggested_next_action: str
    can_advance: bool
    adapted_page_window_size: int | None = None
    prompt_preview: str | None = None


class LessonOutput(BaseModel):
    session_id: str
    lesson_number: int
    lesson_title: str
    learning_mode: LearningMode = DEFAULT_LEARNING_MODE
    llm_used: bool = False
    llm_error: str | None = None
    assistant_message: str
    references: list[ChunkReference] = Field(default_factory=list)
    created_at: str


class BookDetail(BaseModel):
    book: BookSummary
    sections: list[dict[str, Any]] = Field(default_factory=list)
    plans: list[dict[str, Any]] = Field(default_factory=list)
