"""DOCX-də formatla işarələnmiş düzgün cavab (qalın / vurğulanmış / altı xətli / rəngli).

Müəllim rəyi S1 (2026-10-08): Word sənədlərində düzgün variant tez-tez ``*`` ilə yox,
FORMATLA göstərilir (qalın şrift, sarı vurğu, rəngli mətn). Oxuyucu formatı atırdı →
hər sual «düzgün cavab işarəsi tapılmadı». İndi variant paraqrafının BÜTÜN mətni
vurğulanıbsa sətir «vurğulu» sayılır; sualın variantlarından BƏZİLƏRİ (hamısı yox)
vurğuludursa onlar ``*X)`` ilə işarələnir. Hamısı eyni formatdadırsa (bütün sənəd
qalındır) heç nə dəyişmir — yalan-müsbət olmasın. Mətnə ``*`` yazıldığı üçün nəticə
redaktorda görünür və müəllim düzəldə bilər.
"""

from __future__ import annotations

import re

from apps.exams.constants import ANSWERLINE_RE, OPTION_RE, QUESTION_RE
from apps.exams.services.parsing.omml import W_NS

_OFF_VALUES = {"0", "false", "off", "none"}
_PLAIN_FILLS = {"", "auto", "ffffff", "none"}
_PLAIN_COLORS = {"", "auto", "000000"}


def _w(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


def _val(node) -> str:
    return (node.get(_w("val")) or "").strip().lower() if node is not None else ""


def _run_is_emphasized(run_props) -> bool:
    if run_props is None:
        return False
    bold = run_props.find(_w("b"))
    if bold is not None and _val(bold) not in _OFF_VALUES:
        return True
    highlight = run_props.find(_w("highlight"))
    if highlight is not None and _val(highlight) not in _OFF_VALUES:
        return True
    shading = run_props.find(_w("shd"))
    if shading is not None and (shading.get(_w("fill")) or "").strip().lower() not in _PLAIN_FILLS:
        return True
    underline = run_props.find(_w("u"))
    if underline is not None and _val(underline) not in _OFF_VALUES:
        return True
    color = run_props.find(_w("color"))
    return color is not None and _val(color) not in _PLAIN_COLORS


def paragraph_is_emphasized(paragraph) -> bool:
    """Paraqrafın görünən mətninin HAMISI vurğulanmış run-lardadırmı?"""
    seen_text = False
    for run in paragraph.iter(_w("r")):
        text = "".join(node.text or "" for node in run.findall(_w("t")))
        if not text.strip():
            continue
        seen_text = True
        if not _run_is_emphasized(run.find(_w("rPr"))):
            return False
    return seen_text


def mark_emphasized_options(lines: list[str], flags: list[bool]) -> list[str]:
    """Sualın bəzi (hamısı yox) vurğulu variantlarını ``*`` ilə düzgün kimi işarələyir."""
    if not any(flags):
        return lines
    out = list(lines)
    block: list[int] = []

    def flush():
        options = [i for i in block if OPTION_RE.match(out[i])]
        if not options or any(ANSWERLINE_RE.match(out[i]) for i in block):
            return
        if any(OPTION_RE.match(out[i]).group(1) for i in options):
            return  # müəllim artıq açıq marker yazıb
        emphasized = [i for i in options if i < len(flags) and flags[i]]
        if emphasized and len(emphasized) < len(options):
            for i in emphasized:
                out[i] = re.sub(r"^(\s*)", r"\1*", out[i], count=1)

    for index, line in enumerate(out):
        if QUESTION_RE.match(line) and not OPTION_RE.match(line):
            flush()
            block = []
        block.append(index)
    flush()
    return out


__all__ = ["mark_emphasized_options", "paragraph_is_emphasized"]
