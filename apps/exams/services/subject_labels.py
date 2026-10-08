"""Fənn görünüş etiketi — AD əvvəl, kod ikinci dərəcəli (müəllim rəyi Q1, 2026-10-08).

«QKU-1234 — Verilənlər bazası» kimi kod-əvvəl etiket müəllimə heç nə demirdi; seçicilərdə
indi «Verilənlər bazası (QKU-1234)» göstərilir, kod isə siyahıda solğun «meta» kimidir.
"""

from __future__ import annotations


def subject_label_parts(name: str, code: str) -> str:
    name = (name or "").strip()
    code = (code or "").strip()
    if name and code:
        return f"{name} ({code})"
    return name or code


def subject_label(subject) -> str:
    """``registrar.Subject`` → «Ad (KOD)»."""
    return subject_label_parts(getattr(subject, "name", ""), getattr(subject, "code", ""))


def subject_option(subject) -> dict:
    """Axtarışlı seçici (``EMSSearchableSelect``) üçün nəticə: ``text`` + ``label``/``meta``."""
    return {
        "id": str(subject.pk),
        "text": subject_label(subject),
        "label": (subject.name or subject.code or "").strip(),
        "meta": (subject.code or "").strip() if subject.name else "",
    }


__all__ = ["subject_label", "subject_label_parts", "subject_option"]
