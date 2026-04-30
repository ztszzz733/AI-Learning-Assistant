from __future__ import annotations

import re
import sqlite3
from collections import Counter

from book_agent.section_rules import classify_section_role, query_explicitly_targets_section

try:
    import jieba
except ImportError:  # pragma: no cover - optional dependency for better Chinese tokenization
    jieba = None


_HIGH_VALUE_MARKERS = (
    "definition",
    "example",
    "formula",
    "key idea",
    "method",
    "mistake",
    "proof",
    "step",
    "summary",
    "why",
    "例题",
    "公式",
    "原理",
    "定义",
    "定理",
    "小结",
    "总结",
    "推导",
    "方法",
    "步骤",
    "注意",
    "误区",
    "证明",
    "解释",
    "核心",
    "结论",
    "规律",
)

_LOW_VALUE_MARKERS = (
    "about the author",
    "acknowledgment",
    "history",
    "motivation",
    "publishing",
    "thanks",
    "作者",
    "写作背景",
    "勘误",
    "历史背景",
    "出版",
    "前言",
    "动机",
    "后记",
    "导读",
    "序言",
    "致谢",
    "说明",
)


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for match in re.finditer(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+", text.lower()):
        part = match.group(0)
        if re.fullmatch(r"[\u4e00-\u9fff]+", part):
            if jieba is not None:
                tokens.extend(token.strip() for token in jieba.lcut(part) if token.strip())
            else:
                tokens.extend(list(part))
        else:
            tokens.append(part)
    return tokens


def _build_match_query(query: str) -> str:
    terms: list[str] = []
    for token in _tokenize(query):
        if token not in terms:
            terms.append(token)
    return " OR ".join(f'"{term}"' for term in terms[:8])


def _score(query: str, section_title: str, content: str) -> float:
    query_terms = _tokenize(query)
    if not query_terms:
        return 0.0

    title_terms = Counter(_tokenize(section_title))
    content_terms = Counter(_tokenize(content))
    score = 0.0

    for term in query_terms:
        if term in title_terms:
            score += 2.5
        if term in content_terms:
            score += 1.0 + min(content_terms[term] * 0.2, 1.0)

    query_lower = query.lower().strip()
    if query_lower and query_lower in content.lower():
        score += 3.0
    if query_lower and query_lower in section_title.lower():
        score += 4.0

    role = classify_section_role(section_title)
    if role != "core" and not query_explicitly_targets_section(query, section_title):
        score *= 0.3
    score += _teaching_value(section_title, content)
    return score


def _teaching_value(section_title: str, content: str) -> float:
    normalized = f"{section_title}\n{content}".lower()
    score = 0.0

    for marker in _HIGH_VALUE_MARKERS:
        if marker in normalized:
            score += 0.8

    for marker in _LOW_VALUE_MARKERS:
        if marker in normalized:
            score -= 0.5

    paragraph_count = max(1, content.count("\n") + 1)
    if paragraph_count >= 2:
        score += 0.3
    if any(char.isdigit() for char in content):
        score += 0.2

    return score


def _fetch_candidates(connection, book_id: str, section_ids: list[str] | None, query: str):
    base_params: list[object] = [book_id]
    section_clause = ""
    if section_ids:
        placeholders = ", ".join("?" for _ in section_ids)
        section_clause = f" AND c.section_id IN ({placeholders})"
        base_params.extend(section_ids)

    match_query = _build_match_query(query)
    if match_query:
        try:
            rows = connection.execute(
                f"""
                SELECT c.*
                FROM chunks_fts f
                JOIN chunks c ON c.id = f.chunk_id
                WHERE f.book_id = ?
                {section_clause}
                AND chunks_fts MATCH ?
                LIMIT 50
                """,
                (*base_params, match_query),
            ).fetchall()
            if rows:
                return rows
        except sqlite3.OperationalError:
            pass

    fallback_query = "SELECT * FROM chunks c WHERE c.book_id = ?"
    fallback_params: list[object] = [book_id]
    if section_ids:
        placeholders = ", ".join("?" for _ in section_ids)
        fallback_query += f" AND c.section_id IN ({placeholders})"
        fallback_params.extend(section_ids)
    fallback_query += " ORDER BY c.ordinal"
    return connection.execute(fallback_query, fallback_params).fetchall()


def retrieve_chunks(
    connection,
    *,
    book_id: str,
    query: str,
    section_ids: list[str] | None = None,
    limit: int = 5,
):
    candidates = _fetch_candidates(connection, book_id, section_ids, query)
    ranked = []
    for row in candidates:
        row_dict = dict(row)
        score = _score(query, row_dict["section_title"], row_dict["content"])
        if score > 0 or not query.strip():
            row_dict["score"] = round(score, 3)
            ranked.append(row_dict)

    ranked.sort(key=lambda item: (item["score"], -item["page_start"]), reverse=True)
    return ranked[:limit]


def retrieve_page_window_chunks(
    connection,
    *,
    book_id: str,
    page_start: int,
    page_end: int,
    limit: int = 12,
):
    rows = connection.execute(
        """
        SELECT *
        FROM chunks
        WHERE book_id = ?
          AND page_end >= ?
          AND page_start <= ?
        ORDER BY page_start, ordinal
        LIMIT ?
        """,
        (book_id, page_start, page_end, limit),
    ).fetchall()
    results = []
    for row in rows:
        row_dict = dict(row)
        row_dict["score"] = 1.0
        results.append(row_dict)
    return results
