from __future__ import annotations

import json
import re
import uuid
from collections import Counter
from pathlib import Path
from typing import Iterable

import fitz

from book_agent.db import utcnow_iso
from book_agent.schemas import BookSummary


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _normalize_text(text: str) -> str:
    cleaned_lines: list[str] = []
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if line:
            cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


def _approx_token_count(text: str) -> int:
    terms = re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]", text)
    return max(1, len(terms))


def _extract_page_texts(document: fitz.Document) -> list[tuple[int, str]]:
    return [
        (page_number + 1, _normalize_text(document.load_page(page_number).get_text("text", sort=True)))
        for page_number in range(document.page_count)
    ]


def _build_sections_from_toc(
    toc_entries: list[list[int | str]], page_count: int
) -> list[dict[str, object]]:
    sections: list[dict[str, object]] = []
    stack: list[dict[str, object]] = []

    for ordinal, entry in enumerate(toc_entries, start=1):
        level = int(entry[0])
        title = str(entry[1]).strip() or f"Section {ordinal}"
        start_page = max(1, min(page_count, int(entry[2])))

        end_page = page_count
        for next_entry in toc_entries[ordinal:]:
            next_level = int(next_entry[0])
            next_page = int(next_entry[2])
            if next_level <= level:
                end_page = max(start_page, next_page - 1)
                break

        while stack and int(stack[-1]["level"]) >= level:
            stack.pop()

        section_id = _new_id("sec")
        parent_id = stack[-1]["id"] if stack else None
        section = {
            "id": section_id,
            "parent_id": parent_id,
            "title": title,
            "level": level,
            "start_page": start_page,
            "end_page": end_page,
            "ordinal": ordinal,
        }
        sections.append(section)
        stack.append(section)

    return sections


def _build_synthetic_sections(page_count: int, window_size: int = 5) -> list[dict[str, object]]:
    sections: list[dict[str, object]] = []
    ordinal = 1
    for start_page in range(1, page_count + 1, window_size):
        end_page = min(page_count, start_page + window_size - 1)
        sections.append(
            {
                "id": _new_id("sec"),
                "parent_id": None,
                "title": f"Pages {start_page}-{end_page}",
                "level": 1,
                "start_page": start_page,
                "end_page": end_page,
                "ordinal": ordinal,
            }
        )
        ordinal += 1
    return sections


def _leaf_sections(sections: list[dict[str, object]]) -> list[dict[str, object]]:
    parent_ids = {str(section["parent_id"]) for section in sections if section["parent_id"]}
    return [section for section in sections if str(section["id"]) not in parent_ids]


def _chunk_pages(
    page_texts: Iterable[tuple[int, str]],
    *,
    target_chars: int = 1400,
    overlap_chars: int = 220,
) -> list[dict[str, object]]:
    paragraphs: list[tuple[int, str]] = []
    for page_number, text in page_texts:
        for paragraph in text.split("\n"):
            cleaned = paragraph.strip()
            if cleaned:
                paragraphs.append((page_number, cleaned))

    if not paragraphs:
        return []

    chunks: list[dict[str, object]] = []
    buffer: list[tuple[int, str]] = []
    buffer_chars = 0

    def flush() -> None:
        nonlocal buffer, buffer_chars
        if not buffer:
            return
        content = "\n".join(paragraph for _, paragraph in buffer).strip()
        pages = [page for page, _ in buffer]
        chunks.append(
            {
                "page_start": min(pages),
                "page_end": max(pages),
                "content": content,
                "token_count": _approx_token_count(content),
            }
        )
        overlap: list[tuple[int, str]] = []
        overlap_total = 0
        for item in reversed(buffer):
            overlap.insert(0, item)
            overlap_total += len(item[1])
            if overlap_total >= overlap_chars:
                break
        buffer = overlap
        buffer_chars = sum(len(paragraph) for _, paragraph in buffer)

    for page_number, paragraph in paragraphs:
        projected = buffer_chars + len(paragraph)
        if buffer and projected > target_chars:
            flush()
        buffer.append((page_number, paragraph))
        buffer_chars += len(paragraph)

    if buffer:
        flush()

    deduped: list[dict[str, object]] = []
    seen = Counter()
    for chunk in chunks:
        content = str(chunk["content"])
        seen[content] += 1
        if seen[content] == 1:
            deduped.append(chunk)
    return deduped


def import_book(connection, pdf_path: str | Path, title: str | None = None) -> BookSummary:
    source_path = Path(pdf_path).expanduser().resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"PDF not found: {source_path}")

    document = fitz.open(source_path)
    page_count = document.page_count
    try:
        page_texts = _extract_page_texts(document)
        toc_entries = document.get_toc(simple=True)
        sections = (
            _build_sections_from_toc(toc_entries, page_count)
            if toc_entries
            else _build_synthetic_sections(page_count)
        )
        leaf_sections = _leaf_sections(sections)
        book_id = _new_id("book")
        book_title = title or document.metadata.get("title") or source_path.stem
        imported_at = utcnow_iso()

        connection.execute(
            """
            INSERT INTO books (id, title, source_path, page_count, toc_json, imported_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                book_id,
                book_title,
                str(source_path),
                page_count,
                json.dumps(
                    [
                        {"level": int(level), "title": str(name), "page": int(page)}
                        for level, name, page in toc_entries
                    ],
                    ensure_ascii=False,
                ),
                imported_at,
            ),
        )

        for section in sections:
            connection.execute(
                """
                INSERT INTO sections (id, book_id, parent_id, title, level, start_page, end_page, ordinal)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    section["id"],
                    book_id,
                    section["parent_id"],
                    section["title"],
                    section["level"],
                    section["start_page"],
                    section["end_page"],
                    section["ordinal"],
                ),
            )

        chunk_count = 0
        for section in leaf_sections:
            pages = [
                (page_number, text)
                for page_number, text in page_texts
                if int(section["start_page"]) <= page_number <= int(section["end_page"]) and text
            ]
            for ordinal, chunk in enumerate(_chunk_pages(pages), start=1):
                chunk_id = _new_id("chk")
                connection.execute(
                    """
                    INSERT INTO chunks (
                        id, book_id, section_id, section_title, page_start, page_end, ordinal, content, token_count
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk_id,
                        book_id,
                        section["id"],
                        section["title"],
                        chunk["page_start"],
                        chunk["page_end"],
                        ordinal,
                        chunk["content"],
                        chunk["token_count"],
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO chunks_fts (chunk_id, book_id, section_title, content)
                    VALUES (?, ?, ?, ?)
                    """,
                    (chunk_id, book_id, section["title"], chunk["content"]),
                )
                chunk_count += 1

        connection.commit()
    finally:
        document.close()

    return BookSummary(
        id=book_id,
        title=book_title,
        source_path=str(source_path),
        page_count=page_count,
        section_count=len(sections),
        chunk_count=chunk_count,
        imported_at=imported_at,
    )
