"""Sual / variant mətnindəki KOD NÜMUNƏSİ — server tərəfi (sahib 2026-10-19).

Sahib: «Kod nümunəsi ora yerləşdirəndə alt-alta görünsün, birləşməsin — necə var o formada göstərək.»

``apps/live_exam/static/js/host_lobby/code_text.js``-in Python ƏKİZİDİR (eyni qaydalar, eyni nəticə):

1. ``` ```…``` ``` (istəyə bağlı dil adı ilə: ```` ```python ````) — AÇIQ kod bloku;
2. çəpərsiz yapışdırılmış kod — ən azı 2 sətirlik, içində ən azı bir «güclü» kod əlaməti olan ardıcıl
   sətirlər (``{ } ;`` ilə bitən, açar söz, mənimsətmə, funksiya çağırışı); girintili sətirlər yalnız
   ona qoşulur. Qalan mətn olduğu kimi qalır (CSS ``white-space: pre-wrap``).

``render_code_text`` ƏVVƏLCƏ hər seqmenti ``escape`` edir, sonra yalnız öz sabit teqlərimizi
(``<span>`` / ``<code>``) əlavə edir — istifadəçi mətni HTML kimi şərh olunmur.
"""

from __future__ import annotations

import re

from django.utils.html import escape
from django.utils.safestring import SafeString, mark_safe

_FENCE_OPEN = re.compile(r"^\s*```\s*([\w#+.-]*)\s*$", re.ASCII)
_FENCE_CLOSE = re.compile(r"^\s*```\s*$")
_INDENTED = re.compile(r"^(?:\t| {2,})\S")
_LEADING_WS = re.compile(r"^[ \t]*")
_STRONG = tuple(
    re.compile(pattern, re.ASCII)
    for pattern in (
        r"[{};]\s*$",
        r"^\s*[}\])]",
        r"^\s*(?:def|class|import|from|return|for|while|if|elif|else|try|except|finally|with|lambda|print|"
        r"function|const|let|var|public|private|protected|static|void|int|float|double|char|bool|boolean|"
        r"string|struct|using|namespace|package|begin|end|echo|printf|cout|cin|System)\b",
        r"^\s*#\s*(?:include|define|import)\b",
        r"^\s*(?:SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|FROM|WHERE|JOIN|GROUP BY|ORDER BY)\b",
        r"^\s*[A-Za-z_$][\w$.\[\]]*\s*(?:[+\-*/%]?=)(?!=)\s*\S",
        r"^\s*[A-Za-z_$][\w$.]*\(.*\)\s*;?\s*$",
    )
)


def _is_blank(line: str) -> bool:
    return not line.strip()


def _trim_blank(lines: list[str]) -> list[str]:
    start, end = 0, len(lines)
    while start < end and _is_blank(lines[start]):
        start += 1
    while end > start and _is_blank(lines[end - 1]):
        end -= 1
    return lines[start:end]


def _dedent(lines: list[str]) -> list[str]:
    widths = [len(_LEADING_WS.match(line).group(0)) for line in lines if not _is_blank(line)]
    cut = min(widths) if widths else 0
    if not cut:
        return lines
    return [line[min(cut, len(_LEADING_WS.match(line).group(0))) :] for line in lines]


def _push_text(segments: list[dict], lines: list[str]) -> None:
    kept = _trim_blank(lines)
    if kept:
        segments.append({"type": "text", "text": "\n".join(kept)})


def _push_code(segments: list[dict], lines: list[str], lang: str) -> None:
    kept = _dedent(_trim_blank(lines))
    if kept:
        segments.append({"type": "code", "text": "\n".join(kept), "lang": lang or ""})


def _kind(line: str) -> str:
    if _is_blank(line):
        return "blank"
    if any(pattern.search(line) for pattern in _STRONG):
        return "strong"
    return "weak" if _INDENTED.search(line) else "text"


def _split_plain(segments: list[dict], lines: list[str]) -> None:
    kinds = [_kind(line) for line in lines]
    code_like = ("strong", "weak")
    for i in range(1, len(kinds) - 1):
        if kinds[i] != "text":
            continue
        prev = next((k for k in reversed(kinds[:i]) if k != "blank"), None)
        after = next((k for k in kinds[i + 1 :] if k != "blank"), None)
        if prev in code_like and after in code_like:
            kinds[i] = "weak"
    text_buf: list[str] = []
    i = 0
    while i < len(lines):
        if kinds[i] not in code_like:
            text_buf.append(lines[i])
            i += 1
            continue
        j = last = i
        strong = count = 0
        while j < len(lines) and kinds[j] != "text":
            if kinds[j] != "blank":
                last = j
                count += 1
                strong += kinds[j] == "strong"
            j += 1
        if count >= 2 and strong >= 1:
            _push_text(segments, text_buf)
            text_buf = []
            _push_code(segments, lines[i : last + 1], "")
        else:
            text_buf.extend(lines[i : last + 1])
        i = last + 1
    _push_text(segments, text_buf)


def split_code_segments(value) -> list[dict]:
    """Mətni seqmentlərə bölür: ``[{"type": "text" | "code", "text": ..., "lang"?: ...}]``."""
    text = "" if value is None else str(value)
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    segments: list[dict] = []
    plain: list[str] = []
    i = 0
    while i < len(lines):
        opened = _FENCE_OPEN.match(lines[i])
        if not opened:
            plain.append(lines[i])
            i += 1
            continue
        j = i + 1
        while j < len(lines) and not _FENCE_CLOSE.match(lines[j]):
            j += 1
        _split_plain(segments, plain)
        plain = []
        _push_code(segments, lines[i + 1 : j], opened.group(1))
        i = j + 1
    _split_plain(segments, plain)
    return segments


def has_code_block(value) -> bool:
    return any(segment["type"] == "code" for segment in split_code_segments(value))


def render_code_text(value) -> SafeString:
    """Escape → seqment teqləri. Kod yoxdursa yalnız escape olunmuş mətn (``pre-wrap`` sətirləri saxlayır)."""
    segments = split_code_segments(value)
    if not any(segment["type"] == "code" for segment in segments):
        return mark_safe(escape("" if value is None else str(value).replace("\r\n", "\n")))  # noqa: S308
    parts = []
    for segment in segments:
        body = escape(segment["text"])
        if segment["type"] == "code":
            lang = f' data-lang="{escape(segment["lang"])}"' if segment["lang"] else ""
            parts.append(f'<code class="ems-code" translate="no"{lang}>{body}</code>')
        else:
            parts.append(f'<span class="ems-code-text">{body}</span>')
    return mark_safe("".join(parts))  # noqa: S308 — hər seqment yuxarıda escape olunub


__all__ = ["has_code_block", "render_code_text", "split_code_segments"]
