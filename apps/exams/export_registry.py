"""Export job builder registry (C2, 2026-07-03).

Böyük datasetli fayl exportları (xlsx/docx) sorğu yerinə worker-də qurulur.
Hər builder `(filename, content_type, bytes)` qaytarır. İcazə həm job yaradılarkən, həm də worker faylı hazırlayarkən yoxlanılır.

Yeni export əlavə etmək: builder yaz → `_BUILDERS`-ə ad ver → view-da
`start_export_job(request, export_name=..., params=...)` çağır.
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.utils.translation import pgettext

from apps.organizations.public import get_active_memberships

DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _export_source(queryset, pk):
    source = queryset.filter(pk=pk).first()
    if source is None:
        raise ValueError(pgettext("exams.view.export_job.error", "export_failed"))
    return source


def _build_exam_results_xlsx(*, user, organization, params):
    from apps.exams.features import without_disabled_practical_exams
    from apps.exams.models import Exam
    from apps.exams.services.access_policy import _ensure_teacher, manageable_exams_q
    from apps.exams.views.teacher.results._export_builder import build_exam_results_xlsx_export
    from apps.exams.views.teacher.results._helpers import _apply_results_filters_from_params

    _ensure_teacher(user)
    if organization is None:
        raise ValueError(pgettext("exams.view.export_job.error", "export_failed"))
    exams = Exam.objects.filter(manageable_exams_q(user, organization), organization=organization, is_deleted=False)
    exam = _export_source(without_disabled_practical_exams(exams), params["exam_id"])

    attempts_qs, state = _apply_results_filters_from_params(exam, params.get("filters") or {})
    return build_exam_results_xlsx_export(exam, list(attempts_qs), group_index=state["group_index"])


def _build_bank_word(*, user, organization, params):
    from apps.exams.services.access_policy import _ensure_teacher
    from apps.exams.services.question_bank_attach import accessible_banks
    from apps.exams.services.question_word_export import bank_questions_payload, build_questions_docx

    _ensure_teacher(user)
    bank = _export_source(accessible_banks(user, organization), params["bank_id"])

    language = (params.get("language") or "").strip().lower() or None
    payload = bank_questions_payload(bank, language=language)
    if not payload:
        raise ValueError("empty_export")

    subtitle_parts = [pgettext("exams.export", "Sual sayı: %(count)s") % {"count": len(payload)}]
    if bank.subject:
        subtitle_parts.insert(
            0,
            pgettext("exams.export", "Fənn: %(subject)s") % {"subject": bank.subject},
        )
    if language:
        subtitle_parts.append(pgettext("exams.export", "Dil: %(language)s") % {"language": language.upper()})

    buffer = build_questions_docx(
        title=pgettext("exams.export", "Sual bankı — %(name)s") % {"name": bank.name},
        subtitle=" · ".join(subtitle_parts),
        questions=payload,
    )
    filename = f"{bank.name}_suallar.docx"
    return filename, DOCX_CONTENT_TYPE, buffer.read()


#: ``User.is_exam_center`` ilə eyni rollar (``apps/accounts/roles.py``).
_EXAM_CENTER_ROLE_NAMES = ("exam_center", "exam_center_head", "exam_center_staff", "ikt_rehber")


def _build_exam_center_stats_xlsx(*, user, organization, params):
    """«İmtahan statistikaları» böyük ixracı (2026-11-17) — icazə view-da (İmtahan Mərkəzi), burada təkrar."""
    from apps.exams.views.exam_center.statistics_export import build_stats_xlsx

    center_member = (
        organization is not None
        and get_active_memberships(user, organization).filter(role__name__in=_EXAM_CENTER_ROLE_NAMES).exists()
    )
    if organization is None or not (center_member or getattr(user, "is_superadmin", False)):
        raise ValueError("export job permission mismatch")
    return build_stats_xlsx(organization, params.get("filters") or {})


_BUILDERS = {
    "exam_results_xlsx": _build_exam_results_xlsx,
    "exam_center_stats_xlsx": _build_exam_center_stats_xlsx,
    "bank_word": _build_bank_word,
}


def run_export(name, *, user, organization, params):
    """Builder-i icra edir → (filename, content_type, bytes)."""
    try:
        builder = _BUILDERS[name]
    except KeyError:
        raise ValueError(f"Naməlum export: {name!r}")
    # A worker has no request middleware. Resolve current roles for this job's organization.
    actor = get_user_model().objects.filter(pk=user.pk, is_active=True).first()
    if actor is None:
        raise ValueError(pgettext("exams.view.export_job.error", "export_failed"))
    memberships = get_active_memberships(actor, organization) if organization is not None else []
    actor.set_active_organization_context(organization, memberships=memberships)
    try:
        return builder(user=actor, organization=organization, params=params)
    except PermissionDenied as exc:
        raise ValueError(pgettext("exams.view.export_job.error", "export_failed")) from exc
