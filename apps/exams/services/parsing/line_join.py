"""Sual/variant davam sətirlərinin birləşdirilməsi (sahib 2026-11-20: kod nümunəsi bir sətrə düşürdü)."""

from __future__ import annotations

import re

#: Tək etiket sətri («A)» / «*B.») — variant mətni (kod) NÖVBƏTİ sətirlərdədir (sahib 2026-11-20, sual 63).
_BARE_OPTION_RE = re.compile(r"^\s*([*+])?\s*([A-E])\s*[\)\.]\s*$")


def _join_line(base: str, line: str) -> str:
    """Sual/variant davam sətri — SƏTİR SONU və girinti saxlanılır (sahib 2026-11-20: kod nümunəsi birləşirdi).

    Göstərmə ``core.code_text.render_code_text`` (kod bloku + ``pre-wrap``) sətirləri alt-alta saxlayır; əvvəl
    burada boşluqla birləşdirildiyi üçün «values = [...]\nprint(values[2])» bir sətrə düşürdü.
    """
    line = line.rstrip()
    if not base.strip():
        return line.strip()
    return f"{base}\n{line}"


def _join_option(current: dict, label: str, line: str) -> str:
    """Variant davamı: adi mətn boşluqla (əvvəlki kimi), tək «A)» etiketindən sonrakı kod bloku sətir-sətir."""
    base = current["options"][label]
    if label in current.get("_block_options", ()):
        return _join_line(base, line)
    return f"{base} {line.strip()}" if base else line.strip()


def _start_block_option(current: dict, line: str) -> str | None:
    """Tək «A)» sətri → boş variant açılır, kod növbəti sətirlərdən gəlir; etiketi qaytarır (yoxsa ``None``)."""
    m_bare = _BARE_OPTION_RE.match(line)
    if not m_bare:
        return None
    label = m_bare.group(2).upper()
    current["options"][label] = ""
    current.setdefault("_block_options", set()).add(label)
    if m_bare.group(1) and label not in current["correct"]:
        current["correct"].append(label)
    return label
