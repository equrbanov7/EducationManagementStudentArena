"""Dəqiqləşdirmə növbəsinin SƏTİR təqdimatı (data → JSON lüğəti).

Ayrı modul, çünki :mod:`apps.registrar.legacy_grade_review` sorğu qatıdır və
modul-ölçü büdcəsi (600 sətir) bir faylda hər ikisini saxlamağa imkan vermir.
Burada şəbəkə çağırışı və yazı YOXDUR — yalnız təmiz çevirmə.

⚠️ XAM DƏYƏR OLDUĞU KİMİ QALIR. Bal sahələri mənbənin mətn proyeksiyasından
oxunur (``*_score_text``); clamp, round və ya yenidən hesablama YOXDUR. Məhz
buna görə ``final_score_text='117'`` kimi diapazondan kənar dəyər səthdə
GÖRÜNƏN olur — problemi gizlətmək onu həll etmək deyil.

⚠️ KATEQORİYA UYĞUNLUĞU DA BAZADA HESABLANIR. Sətrin hansı kateqoriyalara
düşdüyünü Python-da yenidən hesablamırıq: eyni ``Q`` şərtləri ``Case/When`` ilə
annotasiyaya çevrilir. Beləliklə süzgəcin tapdığı sətirlə nişanladığı sətir
eyni məntiqdən çıxır — ikinci həqiqət mənbəyi yaranmır.
"""

from __future__ import annotations

from decimal import Decimal

from django.db.models import BooleanField, Case, IntegerField, Prefetch, Q, Value, When
from django.utils.translation import pgettext_lazy

from .legacy_grade_review import SEVERITY_LABELS, category_specs
from .models import FinalGrade, LegacyGradeEvidenceKind, LegacyGradeReview, LegacyGradeReviewDecision

# Tərcümə konteksti hər çağırışda HƏRFİ sətirdir, dəyişən DEYİL: ``xgettext``
# ``pgettext``-in kontekst arqumentini yalnız hərfi sətir olanda oxuya bilir —
# dəyişən verilsə sətri SƏSSİZCƏ atır və mətn heç bir dilə çıxmır.

_KIND_LABELS = {
    LegacyGradeEvidenceKind.SUMMARY: pgettext_lazy("registrar.legacy_grade_review", "Köhnə yekun cədvəli"),
    LegacyGradeEvidenceKind.EXAM: pgettext_lazy("registrar.legacy_grade_review", "Köhnə imtahan xanası"),
    LegacyGradeEvidenceKind.RESIT: pgettext_lazy("registrar.legacy_grade_review", "Köhnə təkrar imtahan xanası"),
    LegacyGradeEvidenceKind.EXAM_ENTRY_EXIT: pgettext_lazy(
        "registrar.legacy_grade_review", "Köhnə imtahan giriş/çıxış cəhdi"
    ),
    LegacyGradeEvidenceKind.OTHER: pgettext_lazy("registrar.legacy_grade_review", "Köhnə sistemin xüsusi bal kodu"),
}

_DECISION_LABELS = {
    LegacyGradeReviewDecision.VERIFIED: pgettext_lazy("registrar.legacy_grade_review", "Təsdiqlənib"),
    LegacyGradeReviewDecision.DISPUTED: pgettext_lazy("registrar.legacy_grade_review", "Mübahisəli"),
    LegacyGradeReviewDecision.CORRECTION_REQUIRED: pgettext_lazy(
        "registrar.legacy_grade_review", "Düzəliş tələb olunur"
    ),
}

_PENDING_LABEL = pgettext_lazy("registrar.legacy_grade_review", "Baxılmayıb")
_NO_STUDENT_LABEL = pgettext_lazy("registrar.legacy_grade_review", "Qeydiyyata bağlanmayıb")

#: Annotasiya adının prefiksi — sətir lüğətində kateqoriya kodlarına açılır.
_CATEGORY_PREFIX = "cat_"


def annotate_categories(queryset, organization):
    """Hər kateqoriya üçün bir bool annotasiyası (süzgəclə EYNİ ``Q`` şərtindən)."""
    annotations = {}
    for spec in category_specs(organization):
        annotations[f"{_CATEGORY_PREFIX}{spec.code}"] = Case(
            When(spec.condition, then=Value(True)),
            default=Value(False),
            output_field=BooleanField(),
        )
    return queryset.annotate(**annotations)


def order_by_severity(queryset, organization):
    """Ən pis hal ƏVVƏLDƏ. Sıralama süzgəclə eyni ``Q`` şərtlərindən qurulur.

    Növbə iş siyahısıdır: operator birinci ekranda kritik sətirləri görməlidir,
    yoxsa 20 min «izlənilir» sətri arxasında 20 dənə itmiş imtahan balı gizlənir.
    İkinci açar mənbə sırasıdır — eyni şiddətdə səhifələmə determinist qalsın.
    """
    from .legacy_grade_review import SEVERITY_ORDER, category_specs

    branches = []
    for rank, severity in enumerate(SEVERITY_ORDER):
        condition = Q(pk__in=())
        matched = False
        for spec in category_specs(organization):
            if spec.severity == severity:
                condition |= spec.condition
                matched = True
        if matched:
            branches.append(When(condition, then=Value(rank)))
    ranked = queryset.annotate(
        severity_rank=Case(*branches, default=Value(len(SEVERITY_ORDER)), output_field=IntegerField())
    )
    return ranked.order_by("severity_rank", "source_table", "source_pk")


def prepared_page_queryset(queryset, organization):
    """Səhifə üçün hazır queryset: annotasiyalar + join-lar + yoxlama tarixçəsi."""
    reviews = LegacyGradeReview.objects.select_related("reviewed_by").order_by("created_at", "id")
    return (
        annotate_categories(queryset, organization)
        .select_related(
            "enrollment__student",
            "enrollment__offering__subject",
            "enrollment__offering__group",
            "enrollment__offering__period",
            "enrollment__offering__instructor",
        )
        .prefetch_related(Prefetch("reviews", queryset=reviews, to_attr="_review_history"))
    )


def _person(user):
    if user is None:
        return ""
    return user.get_full_name() or user.get_username()


def _matched_categories(fact, specs):
    rows = []
    for spec in specs:
        if getattr(fact, f"{_CATEGORY_PREFIX}{spec.code}", False):
            rows.append(
                {
                    "code": spec.code,
                    "label": str(spec.label),
                    "hint": str(spec.hint),
                    "severity": spec.severity,
                    "severity_label": str(SEVERITY_LABELS[spec.severity]),
                }
            )
    return rows


def _worst_severity(categories):
    for severity in ("critical", "warn", "watch"):
        if any(row["severity"] == severity for row in categories):
            return severity
    return "watch"


def _review_state(fact):
    """Sonuncu append-only qərar → təqdimat statusu (köhnə qərarlar silinmir)."""
    from .legacy_grade_review import STATUS_CORRECTED, STATUS_DISPUTED, STATUS_PENDING, STATUS_VERIFIED
    from .legacy_grade_review_actions import REASON_CORRECTED

    history = getattr(fact, "_review_history", ()) or ()
    if not history:
        return {
            "status": STATUS_PENDING,
            "status_label": str(_PENDING_LABEL),
            "decision": "",
            "reviewed_by": "",
            "reviewed_at": "",
            "note": "",
            "history_count": 0,
        }
    latest = history[-1]
    if latest.reason_code == REASON_CORRECTED:
        status = STATUS_CORRECTED
    elif latest.decision == LegacyGradeReviewDecision.VERIFIED:
        status = STATUS_VERIFIED
    else:
        status = STATUS_DISPUTED
    from .legacy_grade_review import STATUS_LABELS

    return {
        "status": status,
        "status_label": str(STATUS_LABELS[status]),
        "decision": latest.decision,
        "decision_label": str(_DECISION_LABELS.get(latest.decision, "")),
        "reviewed_by": latest.reviewed_by_name or _person(latest.reviewed_by),
        "reviewed_at": latest.created_at.date().isoformat() if latest.created_at else "",
        "note": latest.note,
        "history_count": len(history),
    }


def _score_text(fact, text_field, decimal_field):
    """Mətn snapshot-u birinci seçimdir — burada round/clamp QADAĞANDIR."""
    text = getattr(fact, text_field, "") or ""
    if text:
        return text
    value = getattr(fact, decimal_field, None)
    return format(value, "f") if value is not None else ""


def _live_score_text(value):
    """Canlı bal güzgüsü — HƏMİŞƏ sütunun öz miqyasında.

    ⚠️ Bu YEGANƏ kvantlaşdırmadır və o, yalnız CANLI ``FinalGrade.exam_score``
    güzgüsünə aiddir. Köhnə XAM dəyərlərə (``_score_text``) toxunmur: modulun
    başındakı «clamp/round yoxdur» qaydası orada olduğu kimi qalır.

    Miqyas sütunun özündən götürülür, çünki backend-lər annotasiya Decimal-ını
    fərqli miqyasda qaytarır; burada sabitləməsək eyni bal iki mühitdə fərqli
    görünərdi (Postgres ``10.00``, SQLite ``10``).
    """
    if value is None:
        return ""
    column = FinalGrade._meta.get_field("exam_score")
    return format(value.quantize(Decimal(1).scaleb(-column.decimal_places)), "f")


def _structure(offering):
    """Qrup → ixtisas/kafedra/fakültə zənciri (ad kimi; ağac sorğusu YOX)."""
    group = getattr(offering, "group", None)
    if group is None:
        return {"group": "", "group_id": "", "unit_path": ""}
    return {
        "group": group.name,
        "group_id": str(group.pk),
        # `path` OrgUnit ağacının materiallaşdırılmış yoludur; UI onu yalnız
        # tooltip-də göstərir, süzgəc isə alt-ağac id-ləri ilə işləyir.
        "unit_path": group.path or "",
    }


def serialize(fact, specs, *, can_correct=False):
    """Bir faktı JSON sətrinə çevirir (səth bundan başqa heç nə oxumur)."""
    enrollment = fact.enrollment
    offering = getattr(enrollment, "offering", None) if enrollment is not None else None
    student = getattr(enrollment, "student", None) if enrollment is not None else None
    categories = _matched_categories(fact, specs)
    live = getattr(fact, "live_exam_score", None)
    structure = _structure(offering) if offering is not None else {"group": "", "group_id": "", "unit_path": ""}
    return {
        "id": str(fact.pk),
        "source_reference": f"{fact.source_table} #{fact.source_pk}",
        "source_system": fact.source_system,
        "source_student_ref": fact.source_student_ref,
        "source_journal_ref": fact.source_journal_ref,
        "kind": fact.evidence_kind,
        "kind_label": str(_KIND_LABELS.get(fact.evidence_kind, _KIND_LABELS[LegacyGradeEvidenceKind.OTHER])),
        "score_code": fact.score_code,
        "recorded_at": fact.legacy_recorded_at_text,
        # ── Xam mənbə dəyərləri (clamp/round YOXDUR) ──
        "entry_score": _score_text(fact, "entry_score_text", "entry_score"),
        "exam_score": _score_text(fact, "exam_score_text", "exam_score"),
        "resit_score": _score_text(fact, "resit_score_text", "resit_score"),
        "final_score": _score_text(fact, "final_score_text", "final_score"),
        # ── Canlı sistem güzgüsü ──
        "live_exam_score": _live_score_text(live),
        "is_live": live is not None,
        # ── Kim / hara ──
        "student": _person(student) if student is not None else str(_NO_STUDENT_LABEL),
        "student_username": student.get_username() if student is not None else "",
        "enrollment_id": str(enrollment.pk) if enrollment is not None else "",
        "subject": getattr(getattr(offering, "subject", None), "name", "") if offering else "",
        "subject_code": getattr(getattr(offering, "subject", None), "code", "") if offering else "",
        "teacher": _person(getattr(offering, "instructor", None)) if offering else "",
        "period": getattr(getattr(offering, "period", None), "name", "") if offering else "",
        **structure,
        # ── Nə üçün burada ──
        "categories": categories,
        "severity": _worst_severity(categories) if categories else "watch",
        "review": _review_state(fact),
        # Düzəliş YALNIZ qeydiyyata bağlı faktda mümkündür: bağlanmamış sətrin
        # hədəfi yoxdur, ona görə səth orada düyməni GÖSTƏRMİR (səssiz 403 yox).
        "can_correct": bool(can_correct and enrollment is not None and offering is not None),
    }


def serialize_page(facts, organization, *, can_correct=False):
    specs = category_specs(organization)
    return [serialize(fact, specs, can_correct=can_correct) for fact in facts]


__all__ = [
    "annotate_categories",
    "order_by_severity",
    "prepared_page_queryset",
    "serialize",
    "serialize_page",
]
