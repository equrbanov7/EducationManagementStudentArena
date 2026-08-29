"""Tələbə səthi üçün köhnə qiymət faktlarının tenant-scoped read modeli.

Bu qat kanonik balı hesablamır və xam dəyəri dəyişmir. Bir qeydiyyata aid bütün
``LegacyGradeFact`` sətirlərini (ziddiyyətli/dublikat mənbələr daxil) saxlayır,
son append-only İmtahan Mərkəzi qərarını isə yalnız təqdimat statusuna çevirir.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.db.models import Prefetch

from apps.registrar.models import (
    LegacyGradeEvidenceKind,
    LegacyGradeFact,
    LegacyGradeReview,
    LegacyGradeReviewDecision,
)

_KIND_LABELS = {
    LegacyGradeEvidenceKind.SUMMARY: "Köhnə yekun cədvəli",
    LegacyGradeEvidenceKind.EXAM: "Köhnə imtahan xanası",
    LegacyGradeEvidenceKind.RESIT: "Köhnə təkrar imtahan xanası",
    LegacyGradeEvidenceKind.EXAM_ENTRY_EXIT: "Köhnə imtahan giriş/çıxış cəhdi",
    LegacyGradeEvidenceKind.OTHER: "Köhnə sistemin xüsusi bal kodu",
}

_REVIEW_LABELS = {
    LegacyGradeReviewDecision.VERIFIED: "İmtahan Mərkəzi tərəfindən təsdiqlənib",
    LegacyGradeReviewDecision.DISPUTED: "İmtahan Mərkəzi tərəfindən mübahisələndirilib",
    LegacyGradeReviewDecision.CORRECTION_REQUIRED: "Düzəliş tələb olunur",
}

_MAPPING_LABELS = {
    "linked": "Qeydiyyatla uyğunlaşdırılıb",
    "group_mismatch": "Tarixi qrup uyğunsuzluğu var",
    "discarded_source": "Köhnə sistemdə silinmiş jurnal mənbəyidir",
    "unresolved": "Qeydiyyatla avtomatik uyğunlaşdırılmayıb",
    "conflict": "Mənbə sətirləri arasında ziddiyyət var",
}


def _decimal_text(value: Decimal | None) -> str:
    """Mətn snapshot-u yoxdursa Decimal-i elmi notasiyasız göstər."""

    if value is None:
        return ""
    return format(value, "f")


def _score_text(fact, text_field: str, decimal_field: str) -> str:
    # Mənbənin orijinal mətn proyeksiyası birinci seçimdir: burada round/clamp
    # qadağandır. Decimal yalnız köhnə materializasiyada mətn boş qalıbsa fallback-dir.
    return getattr(fact, text_field) or _decimal_text(getattr(fact, decimal_field))


def _latest_review(fact):
    history = getattr(fact, "_student_review_history", ())
    return history[-1] if history else None


def _fact_dict(fact) -> dict:
    latest = _latest_review(fact)
    decision = latest.decision if latest else "pending"
    review_required = latest is None or latest.decision != LegacyGradeReviewDecision.VERIFIED
    return {
        "source_table": fact.source_table,
        "source_pk": fact.source_pk,
        "source_reference": f"{fact.source_table} #{fact.source_pk}",
        "kind": fact.evidence_kind,
        "kind_label": _KIND_LABELS.get(fact.evidence_kind, _KIND_LABELS[LegacyGradeEvidenceKind.OTHER]),
        "score_code": fact.score_code,
        "is_archive": fact.is_archive,
        "entry_score": _score_text(fact, "entry_score_text", "entry_score"),
        "exam_score": _score_text(fact, "exam_score_text", "exam_score"),
        "resit_score": _score_text(fact, "resit_score_text", "resit_score"),
        "final_score": _score_text(fact, "final_score_text", "final_score"),
        "raw_score": fact.raw_score_text,
        "legacy_attempt_type": fact.legacy_attempt_type,
        "legacy_recorded_at": fact.legacy_recorded_at_text,
        "mapping_status": fact.mapping_status,
        "mapping_label": _MAPPING_LABELS.get(fact.mapping_status, "Uyğunlaşdırma yoxlanmalıdır"),
        "review_status": decision,
        "review_label": _REVIEW_LABELS.get(decision, "İmtahan Mərkəzinin yoxlaması gözlənilir"),
        "review_required": review_required,
    }


def legacy_grade_facts_for_enrollments(*, organization, enrollment_ids) -> dict[object, list[dict]]:
    """``enrollment_id -> bütün xam faktlar`` xəritəsi, iki sabit sorğu ilə.

    Həm ``organization``, həm enrollment ID tətbiq olunur. Bu ikiqat scope RLS-i
    əvəz etmir; tətbiq qatında səhv kontekst ötürüləndə də başqa tenant faktını
    qaytarmayan fail-closed müdafiədir.
    """

    # Enrollment UUID-dir; tipini integer/string-ə çevirmək natural-key-i
    # korlayar. Django trusted UUID/string dəyərlərini özü təhlükəsiz normallaşdırır.
    ids = {value for value in enrollment_ids if value is not None}
    if organization is None or not ids:
        return {}

    reviews = LegacyGradeReview.objects.filter(organization=organization).order_by("created_at", "id")
    facts = (
        LegacyGradeFact.objects.filter(organization=organization, enrollment_id__in=ids)
        .prefetch_related(Prefetch("reviews", queryset=reviews, to_attr="_student_review_history"))
        .order_by("enrollment_id", "source_table", "source_pk")
    )
    grouped: dict[object, list[dict]] = defaultdict(list)
    for fact in facts:
        grouped[fact.enrollment_id].append(_fact_dict(fact))
    return dict(grouped)


__all__ = ["legacy_grade_facts_for_enrollments"]
