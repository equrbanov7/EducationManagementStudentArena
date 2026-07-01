"""extraction paketi — normalize."""

import re

from apps.exams.constants import LABELS, OPTION_RE, QUESTION_RE
from apps.exams.services.pdf_math import remap_symbol_pua

from .constants import (
    _BARE_QNO_RE,
    _BULLET_CHARS,
    _BULLET_OPTION_LINE_RE,
    _CHECK_CHARS,
    _CHECK_OPTION_LINE_RE,
    _CYR_ANSWERLINE_RE,
    _CYR_OPTION_LABEL_RE,
    _CYRILLIC_LOOKALIKE_MAP,
    _CYRILLIC_SEQ_MAP,
)


def _normalize_cyrillic_option_labels(text: str) -> str:
    """Kiril variant etiketlərini (А Б В …) latın A–E etiketlərinə çevirir."""
    if not text:
        return text

    used = {m.group(2).upper() for m in _CYR_OPTION_LABEL_RE.finditer(text)}
    if not used:
        return text

    mapping = _CYRILLIC_SEQ_MAP if used & {"Б", "Г"} else _CYRILLIC_LOOKALIKE_MAP

    def _label_repl(match):
        latin = mapping.get(match.group(2).upper())
        if latin is None:
            return match.group(0)
        return match.group(1) + latin + match.group(3)

    def _answer_repl(match):
        translated = "".join(mapping.get(ch.upper(), ch) if ch.upper() in mapping else ch for ch in match.group(2))
        return match.group(1) + translated

    text = _CYR_OPTION_LABEL_RE.sub(_label_repl, text)
    return _CYR_ANSWERLINE_RE.sub(_answer_repl, text)


def _merge_bare_question_numbers(text: str) -> str:
    """
    Tək sual nömrəsi sətrini növbəti mətn sətri ilə birləşdirir ki, QUESTION_RE
    onu sual başlanğıcı kimi tanısın. Növbəti sətir variant/işarə sətridirsə
    (sual mətni tamam yoxdursa) toxunulmur.
    """
    if not text:
        return text

    lines = text.splitlines()
    out_lines: list[str] = []
    i = 0
    while i < len(lines):
        m = _BARE_QNO_RE.match(lines[i])
        if m:
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if (
                j < len(lines)
                and not OPTION_RE.match(lines[j])
                and not _BARE_QNO_RE.match(lines[j])
                and not _BULLET_OPTION_LINE_RE.match(lines[j])
                and not _CHECK_OPTION_LINE_RE.match(lines[j])
            ):
                out_lines.append(f"{m.group(1)}{m.group(2)} {lines[j].strip()}")
                i = j + 1
                continue
        out_lines.append(lines[i])
        i += 1
    return "\n".join(out_lines)


def _convert_marker_options(text: str) -> str:
    """
    Bullet (•) variantlarını "A) ..." formasına, √-li sətrləri isə "*X) ..."
    (düz cavab) formasına çevirir. Etiket sayğacı hər sual sətrində sıfırlanır.
    Mövcud A–E etiketli sətrlərə toxunulmur; marker yoxdursa mətn olduğu kimi qalır.
    """
    if not text or not any(ch in text for ch in _BULLET_CHARS + _CHECK_CHARS):
        return text

    out_lines = []
    label_idx = 0
    for line in text.splitlines():
        if QUESTION_RE.match(line):
            label_idx = 0
            out_lines.append(line)
            continue

        m_check = _CHECK_OPTION_LINE_RE.match(line)
        m_bullet = None if m_check else _BULLET_OPTION_LINE_RE.match(line)
        match = m_check or m_bullet
        if match and label_idx < len(LABELS):
            label = LABELS[label_idx]
            label_idx += 1
            prefix = "*" if m_check else ""
            out_lines.append(f"{prefix}{label}) {match.group(1).strip()}")
        else:
            out_lines.append(line)

    return "\n".join(out_lines)


def normalize_pdf_extracted_text(text: str) -> str:
    """
    PDF-dən çıxan mətni parser üçün uyğun formaya salır:
    - Symbol fontunun PUA glyph-lərini əsl Unicode-a çevirir (düstur mətni)
    - sual nömrələrinin qabağına boş sətir əlavə edir (… \n\n12) …)
    - A–E variantlarının qabağına newline əlavə edir (… \nA) …)
    - "Cavab:" sətrini yeni sətrə keçirir
    - '*' işarəsi ilə variant arasında boşluğu düzəldir (*A) kimi)
    - bullet (•) və işarə (√) markerlərini yeni sətirdən başladır
    """
    if not text:
        return ""

    # Mathcad/MathType düsturlarının Symbol-font glyph-lərini bərpa et:
    # "rowsm" → "rows(m)". Adi mətnə təsir etmir.
    t = remap_symbol_pua(text).replace("\r", "\n")

    # çoxlu boşluqları normallaşdır
    t = re.sub(r"[ \t]+", " ", t)

    # "Cavab:" həmişə yeni sətirdən başlasın (az/en/ru/tr açar sözləri)
    t = re.sub(r"(?i)\s+((?:cavab|correct|answer|ответ|cevap)\s*:)", r"\n\1", t)

    # "* A)" kimi çıxırsa "*A)" et
    t = re.sub(r"\*\s+([A-E])", r"*\1", t, flags=re.IGNORECASE)

    # Sual nömrələri: " 12)" və ya " 12." -> yeni blok kimi başlasın
    # (Variant daxilində 1) 2) olsa belə parser artıq IN_OPT-də bunu sual saymır, problem olmur.)
    t = re.sub(r"(?<!\n)\s+(\d{1,4})\s*(\)|\.(?!\d))", r"\n\n\1\2", t)

    # Variantlar: " A)" / " *A)" / " B." və s -> yeni sətirdən başlasın
    t = re.sub(r"(?<!\n)\s+(\*?[A-E])\s*([\)\.])", r"\n\1\2", t, flags=re.IGNORECASE)

    # Bullet/işarə markerləri (• variant, √ düz cavab) yeni sətirdən başlasın
    t = re.sub(rf"(?<!\n)\s+([{_BULLET_CHARS}{_CHECK_CHARS}])\s*", r"\n\1 ", t)

    # 3+ boş sətiri 2-yə sal
    t = re.sub(r"\n{3,}", "\n\n", t)

    return t.strip()
