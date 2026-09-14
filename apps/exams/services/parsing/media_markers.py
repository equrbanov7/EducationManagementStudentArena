"""``[[img:N]]`` şəkil markerləri — parse olunmuş sualdan ``media_refs``-ə çıxarma.

W3 2026-09-14. DOCX oxuyucusu şəkilin yerinə mətn markeri qoyur ki, lövbər
sətir-əsaslı parser-dən keçib düz suala/varianta düşsün (PDF axınındakı
q_no lövbəri ilə eyni ideya, amma mətnin özündə). Parser sonda markerləri
mətn/variantlardan ÇIXARIR (bazaya, fingerprint-ə düşmür) və
``question["media_refs"] = {"stem": [1], "A": [2], …}`` kimi saxlayır;
``import_media`` DOCX bağlaması bu istinadlarla şəkilləri modelə bağlayır.
"""

from __future__ import annotations

import re

MARKER_RE = re.compile(r"\s*\[\[img:(\d{1,4})\]\]\s*")


def split_media_markers(text: str) -> tuple[str, list[int]]:
    """Mətndən markerləri çıxar → ``(təmiz_mətn, [indekslər])`` (sıra qorunur)."""

    if not text or "[[img:" not in text:
        return text or "", []
    refs: list[int] = []

    def _take(match):
        refs.append(int(match.group(1)))
        return " "

    cleaned = MARKER_RE.sub(_take, text)
    return " ".join(cleaned.split()), refs


def extract_media_refs(question: dict) -> dict:
    """Sualın mətn + variantlarından markerləri çıxarıb ``media_refs`` doldur.

    Marker yoxdursa açar əlavə olunmur (mövcud testlərin dict müqayisələri
    dəyişməsin). Boş qalan variant mətni (yalnız şəkil idi) «—» olur ki,
    struktur validasiyası «boş variant» xətası verməsin — şəkil bağlanacaq.
    """

    refs: dict[str, list[int]] = {}
    text, stem_refs = split_media_markers(question.get("text") or "")
    if stem_refs:
        refs["stem"] = stem_refs
        question["text"] = text
    options = question.get("options") or {}
    for label, option_text in list(options.items()):
        cleaned, option_refs = split_media_markers(option_text or "")
        if option_refs:
            refs[str(label)] = option_refs
            options[label] = cleaned or "—"
    if refs:
        question["media_refs"] = refs
    return refs


__all__ = ["MARKER_RE", "extract_media_refs", "split_media_markers"]
