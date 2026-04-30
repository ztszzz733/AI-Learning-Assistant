from __future__ import annotations

import re


_FRONT_MATTER_EXACT = {
    "preface",
    "foreword",
    "序",
    "序言",
    "前言",
    "导读",
}

_FRONT_MATTER_PREFIXES = (
    "author'snote",
    "authorsnote",
    "forewordto",
    "howtousethisbook",
    "prefaceto",
    "readingguide",
    "使用说明",
    "内容提要",
    "内容简介",
    "再版序",
    "写在前面",
    "出版说明",
    "前言与致谢",
    "前言和致谢",
    "前言说明",
    "前言导读",
    "导读",
    "序言",
    "推荐序",
    "本书导读",
    "修订说明",
    "作者序",
    "译者序",
)

_BACK_MATTER_EXACT = {
    "appendix",
    "appendices",
    "afterword",
    "acknowledgments",
    "acknowledgements",
    "bibliography",
    "glossary",
    "index",
    "references",
    "后记",
    "后记与致谢",
    "参考文献",
    "参考书目",
    "致谢",
    "术语表",
    "索引",
    "跋",
    "附录",
}

_BACK_MATTER_PREFIXES = (
    "appendix",
    "bibliography",
    "glossary",
    "index",
    "references",
    "solutionsto",
    "习题答案",
    "参考文献",
    "参考书目",
    "名词解释",
    "后记",
    "常见问题",
    "术语表",
    "索引",
    "练习答案",
    "致谢",
    "附录",
)

_SUPPLEMENTARY_QUERY_TERMS = {
    "preface",
    "foreword",
    "afterword",
    "appendix",
    "bibliography",
    "glossary",
    "index",
    "references",
    "前言",
    "后记",
    "参考文献",
    "导读",
    "序",
    "序言",
    "索引",
    "致谢",
    "附录",
}


def normalize_section_title(title: str) -> str:
    return re.sub(r"[\s\-_:.：,，/、()（）【】\[\]<>《》'\"·]+", "", title).lower()


def classify_section_role(title: str) -> str:
    normalized = normalize_section_title(title)
    if not normalized:
        return "core"

    if normalized in _FRONT_MATTER_EXACT:
        return "front_matter"
    if any(normalized.startswith(prefix) for prefix in _FRONT_MATTER_PREFIXES):
        return "front_matter"

    if normalized in _BACK_MATTER_EXACT:
        return "back_matter"
    if any(normalized.startswith(prefix) for prefix in _BACK_MATTER_PREFIXES):
        return "back_matter"

    return "core"


def is_core_learning_section(title: str) -> bool:
    return classify_section_role(title) == "core"


def query_explicitly_targets_section(query: str, title: str) -> bool:
    normalized_query = normalize_section_title(query)
    normalized_title = normalize_section_title(title)
    if not normalized_query:
        return False
    if normalized_title and normalized_title in normalized_query:
        return True
    return any(term in normalized_query for term in _SUPPLEMENTARY_QUERY_TERMS)
