from __future__ import annotations

import json
import math
import re
import uuid
from collections import defaultdict

from book_agent.db import utcnow_iso
from book_agent.section_rules import is_core_learning_section
from book_agent.schemas import LessonPlan, StudyPlan


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _split_title_to_concepts(title: str) -> list[str]:
    fragments = [
        part.strip()
        for part in re.split(r"[:：,，/、\-|()（）]", title)
        if part.strip()
    ]
    concepts: list[str] = []
    for fragment in fragments:
        if fragment not in concepts:
            concepts.append(fragment)
    return concepts[:5] or [title]


def _fetch_book(connection, book_id: str):
    row = connection.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
    if not row:
        raise ValueError(f"Book not found: {book_id}")
    return row


def _fetch_sections(connection, book_id: str) -> list[dict[str, object]]:
    rows = connection.execute(
        "SELECT * FROM sections WHERE book_id = ? ORDER BY ordinal", (book_id,)
    ).fetchall()
    return [dict(row) for row in rows]


def _leaf_sections(sections: list[dict[str, object]]) -> list[dict[str, object]]:
    children = defaultdict(list)
    for section in sections:
        parent_id = section["parent_id"]
        if parent_id:
            children[parent_id].append(section["id"])
    return [section for section in sections if section["id"] not in children]


def _group_sections(
    sections: list[dict[str, object]], max_lessons: int | None
) -> list[list[dict[str, object]]]:
    if not sections:
        return []
    if not max_lessons or len(sections) <= max_lessons:
        return [[section] for section in sections]

    group_size = math.ceil(len(sections) / max_lessons)
    return [sections[index : index + group_size] for index in range(0, len(sections), group_size)]


def _partition_learning_sections(
    sections: list[dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    core_sections: list[dict[str, object]] = []
    supplementary_sections: list[dict[str, object]] = []
    for section in sections:
        if is_core_learning_section(str(section["title"])):
            core_sections.append(section)
        else:
            supplementary_sections.append(section)
    return core_sections, supplementary_sections


def generate_study_plan(
    connection, book_id: str, max_lessons: int | None = None
) -> StudyPlan:
    book = _fetch_book(connection, book_id)
    sections = _fetch_sections(connection, book_id)
    leaf_sections = _leaf_sections(sections) or sections
    core_sections, supplementary_sections = _partition_learning_sections(leaf_sections)
    prioritized_sections = core_sections or leaf_sections
    groups = _group_sections(prioritized_sections, max_lessons)
    created_at = utcnow_iso()

    lessons: list[LessonPlan] = []
    previous_titles: list[str] = []
    deemphasize_supporting_material = bool(core_sections and supplementary_sections)
    for lesson_number, group in enumerate(groups, start=1):
        group_titles = [str(section["title"]) for section in group]
        group_concepts = []
        for title in group_titles:
            for concept in _split_title_to_concepts(title):
                if concept not in group_concepts:
                    group_concepts.append(concept)

        lesson_title = group_titles[0] if len(group_titles) == 1 else f"{group_titles[0]} -> {group_titles[-1]}"
        prerequisites = (
            ["先确认你能用自己的话复述上一课的关键点。"]
            if previous_titles
            else ["无硬性前置要求，先建立整体认识即可。"]
        )
        if lesson_number == 1 and deemphasize_supporting_material:
            prerequisites.insert(0, "本计划默认弱化序言、导读、附录等辅助材料，优先聚焦正文知识。")
        if previous_titles:
            prerequisites.append(f"尤其注意和上一课《{previous_titles[-1]}》的衔接。")

        key_concepts = group_concepts[:6] or [lesson_title]
        practice_tasks = [
            f"用自己的话解释本课的 {key_concepts[0]}。",
            "在原书对应页码中找出最关键的定义或结论。",
            "写一个 3 句话的小总结，说明这课解决了什么问题。",
        ]
        lesson = LessonPlan(
            lesson_number=lesson_number,
            title=lesson_title,
            section_ids=[str(section["id"]) for section in group],
            section_titles=group_titles,
            page_start=min(int(section["start_page"]) for section in group),
            page_end=max(int(section["end_page"]) for section in group),
            goal=f"理解《{lesson_title}》这部分在全书中的作用，并能讲清核心概念与它们的关系。",
            prerequisites=prerequisites,
            key_concepts=key_concepts,
            practice_tasks=practice_tasks,
            check_question=f"如果让你给初学者讲《{lesson_title}》，你会先讲哪两个关键点，为什么？",
        )
        lessons.append(lesson)
        previous_titles.append(lesson_title)

    plan = StudyPlan(
        id=_new_id("plan"),
        book_id=book_id,
        title=f"{book['title']} 学习路线图",
        created_at=created_at,
        lessons=lessons,
    )

    connection.execute(
        "INSERT INTO plans (id, book_id, title, plan_json, created_at) VALUES (?, ?, ?, ?, ?)",
        (plan.id, book_id, plan.title, plan.model_dump_json(), created_at),
    )
    connection.commit()
    return plan


def generate_page_window_study_plan(
    connection, book_id: str, window_pages: int = 12
) -> StudyPlan:
    book = _fetch_book(connection, book_id)
    sections = _fetch_sections(connection, book_id)
    leaf_sections = _leaf_sections(sections) or sections
    page_count = int(book["page_count"])
    safe_window_pages = max(1, window_pages)
    created_at = utcnow_iso()

    lessons: list[LessonPlan] = []
    previous_title: str | None = None
    for lesson_number, page_start in enumerate(
        range(1, page_count + 1, safe_window_pages), start=1
    ):
        page_end = min(page_count, page_start + safe_window_pages - 1)
        group = [
            section
            for section in leaf_sections
            if int(section["start_page"]) <= page_end
            and int(section["end_page"]) >= page_start
        ]
        group_titles = [str(section["title"]) for section in group]
        title_start = group_titles[0] if group_titles else f"p.{page_start}"
        title_end = group_titles[-1] if group_titles and group_titles[-1] != title_start else f"p.{page_end}"
        lesson_title = f"p.{page_start}-{page_end}：{title_start} -> {title_end}"

        concepts: list[str] = []
        for title in group_titles:
            for concept in _split_title_to_concepts(title):
                if concept not in concepts:
                    concepts.append(concept)
        key_concepts = concepts[:6] or [f"p.{page_start}-{page_end}"]
        prerequisites = (
            [f"先回顾上一段《{previous_title}》的关键结论。"]
            if previous_title
            else ["先建立本书的学习节奏：每次阅读一个连续页码窗口。"]
        )

        lessons.append(
            LessonPlan(
                lesson_number=lesson_number,
                title=lesson_title,
                section_ids=[str(section["id"]) for section in group],
                section_titles=group_titles,
                page_start=page_start,
                page_end=page_end,
                goal=(
                    f"先阅读 p.{page_start}-{page_end} 的材料，由 AI 根据这十几页内容"
                    "自主决定讲解顺序、模块划分、重点和练习。"
                ),
                prerequisites=prerequisites,
                key_concepts=key_concepts,
                practice_tasks=[
                    "跟随 AI 对本页码窗口的拆分学习，不需要提前固定整本书课数。",
                    "学完后用自己的话复述本窗口最重要的 1 到 3 个点。",
                ],
                check_question=f"p.{page_start}-{page_end} 这一段最值得掌握的主线是什么？",
            )
        )
        previous_title = lesson_title

    plan = StudyPlan(
        id=_new_id("plan"),
        book_id=book_id,
        title=f"{book['title']} 页码窗口学习路线图",
        created_at=created_at,
        lessons=lessons,
    )

    connection.execute(
        "INSERT INTO plans (id, book_id, title, plan_json, created_at) VALUES (?, ?, ?, ?, ?)",
        (plan.id, book_id, plan.title, plan.model_dump_json(), created_at),
    )
    connection.commit()
    return plan


def _build_page_window_lessons(
    connection,
    book_id: str,
    *,
    start_page: int,
    window_pages: int,
    starting_lesson_number: int,
    previous_title: str | None = None,
) -> list[LessonPlan]:
    book = _fetch_book(connection, book_id)
    sections = _fetch_sections(connection, book_id)
    leaf_sections = _leaf_sections(sections) or sections
    page_count = int(book["page_count"])
    safe_window_pages = max(1, int(window_pages))
    safe_start_page = max(1, int(start_page))

    lessons: list[LessonPlan] = []
    last_title = previous_title
    lesson_number = starting_lesson_number
    for page_start in range(safe_start_page, page_count + 1, safe_window_pages):
        page_end = min(page_count, page_start + safe_window_pages - 1)
        group = [
            section
            for section in leaf_sections
            if int(section["start_page"]) <= page_end
            and int(section["end_page"]) >= page_start
        ]
        group_titles = [str(section["title"]) for section in group]
        title_start = group_titles[0] if group_titles else f"p.{page_start}"
        title_end = (
            group_titles[-1]
            if group_titles and group_titles[-1] != title_start
            else f"p.{page_end}"
        )
        lesson_title = f"p.{page_start}-{page_end}: {title_start} -> {title_end}"

        concepts: list[str] = []
        for title in group_titles:
            for concept in _split_title_to_concepts(title):
                if concept not in concepts:
                    concepts.append(concept)
        key_concepts = concepts[:6] or [f"p.{page_start}-{page_end}"]
        prerequisites = (
            [f"Review the previous window first: {last_title}"]
            if last_title
            else ["Start with this page window and build a stable reading rhythm."]
        )

        lessons.append(
            LessonPlan(
                lesson_number=lesson_number,
                title=lesson_title,
                section_ids=[str(section["id"]) for section in group],
                section_titles=group_titles,
                page_start=page_start,
                page_end=page_end,
                goal=(
                    f"Read p.{page_start}-{page_end} as one adaptive learning window. "
                    "The tutor should decide the teaching order from the actual text and "
                    "cover every important knowledge point without overloading the learner."
                ),
                prerequisites=prerequisites,
                key_concepts=key_concepts,
                practice_tasks=[
                    "Learn the current page window through the tutor's module breakdown.",
                    "After studying, restate the 1-3 most important points in your own words.",
                ],
                check_question=(
                    f"What is the main knowledge thread in p.{page_start}-{page_end}?"
                ),
            )
        )
        last_title = lesson_title
        lesson_number += 1
    return lessons


def rebuild_page_window_plan_after_lesson(
    connection,
    plan_id: str,
    *,
    keep_lesson_number: int,
    window_pages: int,
) -> StudyPlan:
    """Keep completed/current lessons, then rebuild future lessons with a new page window."""
    plan = get_plan(connection, plan_id)
    keep_count = max(0, min(int(keep_lesson_number), len(plan.lessons)))
    kept_lessons = [
        lesson.model_copy(update={"lesson_number": index})
        for index, lesson in enumerate(plan.lessons[:keep_count], start=1)
    ]

    book = _fetch_book(connection, plan.book_id)
    page_count = int(book["page_count"])
    next_page = kept_lessons[-1].page_end + 1 if kept_lessons else 1
    future_lessons: list[LessonPlan] = []
    if next_page <= page_count:
        future_lessons = _build_page_window_lessons(
            connection,
            plan.book_id,
            start_page=next_page,
            window_pages=window_pages,
            starting_lesson_number=len(kept_lessons) + 1,
            previous_title=kept_lessons[-1].title if kept_lessons else None,
        )

    rebuilt = plan.model_copy(update={"lessons": kept_lessons + future_lessons})
    connection.execute(
        "UPDATE plans SET plan_json = ? WHERE id = ?",
        (rebuilt.model_dump_json(), plan_id),
    )
    connection.commit()
    return rebuilt


def get_plan(connection, plan_id: str) -> StudyPlan:
    row = connection.execute("SELECT plan_json FROM plans WHERE id = ?", (plan_id,)).fetchone()
    if not row:
        raise ValueError(f"Plan not found: {plan_id}")
    return StudyPlan.model_validate(json.loads(row["plan_json"]))


def get_latest_plan_for_book(connection, book_id: str) -> StudyPlan | None:
    row = connection.execute(
        "SELECT plan_json FROM plans WHERE book_id = ? ORDER BY created_at DESC LIMIT 1",
        (book_id,),
    ).fetchone()
    if not row:
        return None
    return StudyPlan.model_validate(json.loads(row["plan_json"]))
