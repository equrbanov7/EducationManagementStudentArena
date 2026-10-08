"""Düzgün cavab markerləri — cavab açarı bölməsi və «düzgün cavab həmişə A» idxal seçimi.

Müəllim rəyi S1 (2026-10-08): 50 sual yüklənib, hər birində düzgün cavab A idi; hamısı
«Xətalı — düzgün cavab işarəsi tapılmadı, müvəqqəti A seçildi» oldu. Burada:

* :func:`split_answer_key` — sənədin sonundakı CAVAB AÇARI («Cavablar:», «Düzgün
  cavablar:», «Answer key:», «Ответы:», «Cevaplar:» + «1-A 2-B …» / «1) A» sətirləri)
  mətndən ayrılır (əks halda «1. A» sətri yeni sual kimi oxunurdu);
* :func:`apply_answer_key` — açar işarəsiz suallara tətbiq olunur;
* :func:`mark_default_correct_a` — idxal seçimi «Düzgün cavab həmişə A variantıdır»:
  işarəsiz sualın A variantı mətndə ``*A)`` olur (bullet formatında ``√``). Mətn
  dəyişdiyi üçün nəticə redaktorda GÖRÜNÜR və sonrakı bütün parse-larda (yadda
  saxlama, kafedra/mərkəz baxışı, yenidən göndəriş) eyni qalır.
"""

from __future__ import annotations

import re

from apps.exams.constants import ANSWERLINE_RE, LABELS, OPTION_RE, QUESTION_RE

from .extraction import END_QUESTION_RE
from .extraction.constants import _BULLET_OPTION_LINE_RE, _CHECK_OPTION_LINE_RE
from .option_markers import _option_from_match

ANSWER_KEY_HEADER_RE = re.compile(
    r"^\s*(?:düzgün\s+cavablar|duzgun\s+cavablar|doğru\s+cavablar|cavablar|cavab\s+açarı|cavab\s+acari|"
    r"answer\s+key|answers|correct\s+answers|key|"
    r"ответы|правильные\s+ответы|ключ(?:\s+ответов)?|"
    r"cevaplar|doğru\s+cevaplar|cevap\s+anahtarı)\s*[:\-–—]?\s*(?P<rest>.*)$",
    re.IGNORECASE,
)
_KEY_PAIR_RE = re.compile(r"(\d{1,4})\s*[\)\.\-:–—=]?\s*([A-Ea-e])(?![A-Za-z0-9])")
_KEY_SEPARATORS_RE = re.compile(r"[\s,;|/]+")


def _key_pairs(line: str) -> list[tuple[str, str]] | None:
    """Sətir YALNIZ «nömrə-etiket» cütlərindən ibarətdirsə onları qaytarır, əks halda ``None``."""
    text = (line or "").strip()
    if not text:
        return None
    pairs = _KEY_PAIR_RE.findall(text)
    if not pairs:
        return None
    leftover = _KEY_SEPARATORS_RE.sub("", _KEY_PAIR_RE.sub("", text))
    return [(number, label.upper()) for number, label in pairs] if not leftover else None


def _answer_key_spans(lines: list[str]) -> tuple[dict[str, list[str]], set[int]]:
    """Açar bölmələri: ``({sual_nömrəsi: [etiketlər]}, açara aid sətir indeksləri)``."""
    key: dict[str, list[str]] = {}
    removed: set[int] = set()
    index = 0
    while index < len(lines):
        header = ANSWER_KEY_HEADER_RE.match(lines[index])
        rest = header.group("rest").strip() if header else ""
        rest_pairs = _key_pairs(rest) if rest else None
        if header and (not rest or rest_pairs):
            block_pairs = list(rest_pairs or [])
            span = {index}
            probe = index + 1
            while probe < len(lines):
                if not lines[probe].strip():
                    span.add(probe)
                    probe += 1
                    continue
                pairs = _key_pairs(lines[probe])
                if pairs is None:
                    break
                block_pairs.extend(pairs)
                span.add(probe)
                probe += 1
            if block_pairs:
                for number, label in block_pairs:
                    labels = key.setdefault(number, [])
                    if label not in labels:
                        labels.append(label)
                removed |= span
                index = probe
                continue
        index += 1
    return key, removed


def split_answer_key(raw_text: str) -> tuple[str, dict[str, list[str]]]:
    """Mətndən cavab açarı bölməsini ayırır: ``(açarsız mətn, {sual_nömrəsi: [etiketlər]})``.

    Açar başlıq sətri ilə başlayır; davamı yalnız «nömrə-etiket» cütlərindən ibarət
    sətirlərdir (ilk uyğunsuz sətirdə bölmə bitir). Başlıqsız «1-A» sətirləri açar
    sayılmır — sual mətni ilə qarışmasın.
    """
    lines = (raw_text or "").splitlines()
    key, removed = _answer_key_spans(lines)
    if not key:
        return raw_text or "", {}
    return "\n".join(line for i, line in enumerate(lines) if i not in removed), key


def apply_answer_key(questions: list[dict], key: dict[str, list[str]]) -> list[dict]:
    """Açarı yalnız işarəsiz suallara (``correct_defaulted``) tətbiq edir; xəbərdarlıq silinir."""
    if not key:
        return questions
    for question in questions:
        labels = key.get(str(question.get("q_no") or ""))
        warnings = question.get("warnings") or []
        if not labels or not any(w.get("type") == "correct_defaulted" for w in warnings):
            continue
        question["correct"] = list(labels)
        question["answer_mode"] = "multiple" if len(labels) > 1 else "single"
        question["warnings"] = [w for w in warnings if w.get("type") != "correct_defaulted"]
    return questions


def _block_has_marker(block: list[str]) -> bool:
    for line in block:
        if ANSWERLINE_RE.match(line) or _CHECK_OPTION_LINE_RE.match(line):
            return True
        m_opt = OPTION_RE.match(line)
        if m_opt and _option_from_match(m_opt)[2]:
            return True
    return False


def _mark_block(lines: list[str], indexes: list[int]) -> bool:
    """Blokun A variantını (və ya ilk bullet variantını) düzgün kimi işarələyir."""
    block = [lines[i] for i in indexes]
    if not block or _block_has_marker(block):
        return False
    for i in indexes:
        m_opt = OPTION_RE.match(lines[i])
        if m_opt and m_opt.group(2).upper() == LABELS[0]:
            lines[i] = re.sub(r"^(\s*)", r"\1*", lines[i], count=1)
            return True
    for i in indexes:
        m_bullet = _BULLET_OPTION_LINE_RE.match(lines[i])
        if m_bullet:
            lines[i] = "√ " + m_bullet.group(1).strip()
            return True
    return False


def mark_default_correct_a(raw_text: str) -> tuple[str, int]:
    """«Düzgün cavab həmişə A variantıdır»: işarəsiz hər sualda A-nı ``*A)`` edir.

    Qaytarır: (yeni mətn, işarələnən sual sayı). END_QUESTION formatında A onsuz da
    razılaşdırılmış cavabdır — mətnə toxunulmur. Cavab açarı bölməsindəki suallar
    (``split_answer_key``) işarələnmir: açar üstündür.
    """
    text = raw_text or ""
    if any(END_QUESTION_RE.match(line.strip()) for line in text.splitlines()):
        return text, 0
    lines = text.splitlines()
    key, removed = _answer_key_spans(lines)
    blocks: list[tuple[str, list[int]]] = []
    for index, line in enumerate(lines):
        if index in removed:
            continue
        m_q = QUESTION_RE.match(line)
        if m_q and not OPTION_RE.match(line):
            blocks.append((m_q.group(1), []))
        elif blocks:
            blocks[-1][1].append(index)
    marked = 0
    for number, indexes in blocks:
        if number in key:
            continue
        if _mark_block(lines, indexes):
            marked += 1
    if not marked:
        return text, 0
    return "\n".join(lines) + ("\n" if text.endswith("\n") else ""), marked


def count_defaulted(questions) -> int:
    """Düzgün cavabı A-ya defolt edilmiş (işarəsiz) sual sayı — «Hamısını təsdiqlə» üçün."""
    return sum(
        1
        for question in questions or []
        if any(w.get("type") == "correct_defaulted" for w in question.get("warnings") or [])
    )


__all__ = [
    "ANSWER_KEY_HEADER_RE",
    "apply_answer_key",
    "count_defaulted",
    "mark_default_correct_a",
    "split_answer_key",
]
