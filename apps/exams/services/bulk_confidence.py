"""Toplu sual preview-u — sual meta/inam nişanları və kateqoriya sayğacları.

W3 2026-09-14. Əvvəl eyni «meta» bloku ``bulk_workbench.analyze_mcq_bulk`` və
``analyze_written_bulk``-da təkrarlanırdı (fayl 600 sətir tavanında idi).
Burada tək mənbədə toplandı və sahibin istədiyi «inam» göstəriciləri əlavə
olundu: mətn OK / düstur çevrildi / düstur fallback / şəkil bağlı.

``refresh_question_meta`` idempotentdir — bağlama (``bind_import_manifest``)
xəbərdarlıq əlavə etdikdən sonra yenidən çağırıla bilər.
"""

from __future__ import annotations

from apps.exams.services.parsing.math_text import math_summary

# Hansı warning tipləri hansı kateqoriyaya düşür (filter çipləri üçün)
DUP_TYPES = {"duplicate_in_import", "already_in_exam"}
STRUCTURE_TYPES = {"missing_option", "option_count_recommend_5", "option_count_too_low", "empty_option_text"}
BALANCE_TYPES = {"correct_too_long", "correct_too_short"}
FORMULA_ISSUE_TYPES = {"formula_too_long", "formula_denied", "formula_fallback"}
MEDIA_ISSUE_TYPES = {"image_ref_unknown"}


def _formula_count(question: dict) -> int:
    total = math_summary(question.get("text") or "")["count"]
    for option_text in (question.get("options") or {}).values():
        total += math_summary(option_text or "")["count"]
    return total


def refresh_question_meta(question: dict) -> dict:
    """Sualın ``warnings``/``media``/düstur vəziyyətindən ``meta`` qur (yenidən)."""

    warnings = question.get("warnings") or []
    counts = {"error": 0, "warning": 0, "info": 0}
    dup_refs = []
    types = set()
    for warning in warnings:
        severity = warning.get("severity", "warning")
        if severity in counts:
            counts[severity] += 1
        types.add(warning.get("type"))
        if warning.get("type") == "duplicate_in_import" and warning.get("ref"):
            dup_refs.append({"kind": "import", "index": warning["ref"]})
        if warning.get("type") == "already_in_exam":
            dup_refs.append({"kind": "db", "index": warning.get("ref_db_order"), "db_id": warning.get("ref_db_id")})

    top_severity = "none"
    for severity in ("error", "warning", "info"):
        if counts[severity]:
            top_severity = severity
            break

    has_duplicate = bool(DUP_TYPES & types)
    has_structure = bool(STRUCTURE_TYPES & types)
    has_balance = bool(BALANCE_TYPES & types)
    formula_count = _formula_count(question)
    formula_fallback = bool(question.get("formula_fallback")) or bool(FORMULA_ISSUE_TYPES & types)
    has_image = bool(question.get("has_media")) or bool(question.get("has_visual_source"))
    media_refs = question.get("media_refs") or {}
    image_pending = bool(media_refs) and not question.get("has_media")

    # İnam: image > formula_fallback > formula_ok > text (kartın nişanı üçün)
    if formula_fallback:
        confidence = "formula_fallback"
    elif formula_count:
        confidence = "formula_ok"
    else:
        confidence = "text"

    question["meta"] = {
        "top_severity": top_severity,
        "error_count": counts["error"],
        "warning_count": counts["warning"],
        "info_count": counts["info"],
        "total_count": counts["error"] + counts["warning"] + counts["info"],
        "has_duplicate": has_duplicate,
        "has_structure_issue": has_structure,
        "has_balance_issue": has_balance,
        "dup_refs": dup_refs,
        "formula_count": formula_count,
        "formula_fallback": formula_fallback,
        "has_image": has_image,
        "image_pending": image_pending,
        "confidence": confidence,
        "flags": " ".join(
            filter(
                None,
                [
                    f"sev-{top_severity}" if top_severity != "none" else "sev-clean",
                    "has-dup" if has_duplicate else "",
                    "has-structure" if has_structure else "",
                    "has-balance" if has_balance else "",
                    "has-error" if counts["error"] else "",
                    "has-warning" if counts["warning"] else "",
                    "has-info" if counts["info"] else "",
                    "is-clean" if not warnings else "",
                    "has-formula" if formula_count else "",
                    "has-formula-fallback" if formula_fallback else "",
                    "has-image" if has_image else "",
                ],
            )
        ),
    }
    return question["meta"]


def finalize_analysis(parsed: list, test_level_warnings: list | None = None) -> dict:
    """Bütün sualların meta-sını qur, kateqoriya sayğaclarını hesabla."""

    test_level_warnings = list(test_level_warnings or [])
    category_counts = {
        "errors": 0,
        "warnings": 0,
        "duplicates": 0,
        "structure": 0,
        "balance": 0,
        "clean": 0,
        "formula": 0,
        "image": 0,
    }
    for question in parsed:
        question.setdefault("warnings", [])
        meta = refresh_question_meta(question)
        if meta["error_count"]:
            category_counts["errors"] += 1
        if meta["warning_count"]:
            category_counts["warnings"] += 1
        if meta["has_duplicate"]:
            category_counts["duplicates"] += 1
        if meta["has_structure_issue"]:
            category_counts["structure"] += 1
        if meta["has_balance_issue"]:
            category_counts["balance"] += 1
        if meta["formula_count"]:
            category_counts["formula"] += 1
        if meta["has_image"]:
            category_counts["image"] += 1
        if not question["warnings"]:
            category_counts["clean"] += 1

    warning_count = sum(
        1
        for question in parsed
        for warning in question.get("warnings", [])
        if warning.get("severity", "warning") != "info"
    )
    warning_count += sum(1 for warning in test_level_warnings if warning.get("severity", "warning") != "info")

    return {
        "parsed": parsed,
        "category_counts": category_counts,
        "warning_count": warning_count,
        "duplicate_count": category_counts["duplicates"],
        "error_count": category_counts["errors"],
        "test_level_warnings": test_level_warnings,
    }


__all__ = [
    "BALANCE_TYPES",
    "DUP_TYPES",
    "STRUCTURE_TYPES",
    "finalize_analysis",
    "refresh_question_meta",
]
