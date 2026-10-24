"""teacher exams paketi — müəllim → fənn asılı seçimi üçün JSON endpoint (sahib 2026-10-24).

İmtahan sehrbazında «Müəllim (jurnal)» seçiləndə fənn siyahısı YALNIZ həmin müəllimin cari dövrdə
tədris etdiyi fənlərdən gəlir (``registrar.exam_journal_link.teacher_subject_ids``: jurnal sahibi və ya
həmin jurnalda dərs aparan). Müəllim boşdursa klient adi ``exams:subject_search``-ə qayıdır.

Əhatə: müəllim təşkilatın aktiv müəllim-rol üzvü olmalıdır (``journal_teacher_queryset`` — formanın
yoxlaması ilə EYNİ dəst); ``units`` verilibsə yalnız istifadəçinin ``exam.create`` əhatəsindəki reyestr
qrupları sayılır; unit-skoplu (dekan / kafedra) istifadəçi qrupsuz sorğuda da yalnız öz alt-ağacının
qruplarının açılışlarını görür. Cavab ``subject_search`` ilə eyni formadadır (+ ``selected_ok``).
"""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from apps.exams.forms.exam_journal_teacher import journal_teacher_queryset
from apps.exams.services.access_policy import _ensure_teacher
from apps.exams.services.subject_labels import subject_option
from apps.organizations.public import get_permission_scope

from . import unit_assignment as _units
from ._shared import _resolve_required_organization
from .lookups import _page_bounds, _paginate, _unit_ids_param, ranked_subject_queryset

_EMPTY = {"results": [], "has_more": False, "selected_ok": False}


def _scoped_group_ids(request, organization):
    """``None`` — qrup süzgəci yoxdur; siyahı — yalnız bu reyestr qruplarının açılışları."""
    candidates = _units.exam_unit_candidates(request, organization)
    unit_ids = _unit_ids_param(request)
    if unit_ids:
        return list(candidates.filter(pk__in=unit_ids).values_list("pk", flat=True))
    if get_permission_scope(request.user, organization, "exam.create", request=request).is_unit_scoped:
        return list(candidates.values_list("pk", flat=True))
    return None


@login_required
@require_GET
def journal_teacher_subjects(request):
    """Seçilmiş müəllimin cari dövrdə tədris etdiyi fənlər (axtarış + səhifələmə)."""
    _ensure_teacher(request.user)
    organization = _resolve_required_organization(request)
    teacher_id = (request.GET.get("teacher") or "").strip()
    if organization is None or not teacher_id.isdigit():
        return JsonResponse(_EMPTY)
    teacher = journal_teacher_queryset(organization).filter(pk=int(teacher_id)).first()
    if teacher is None:
        return JsonResponse(_EMPTY)

    from apps.registrar.public import exam_journal_link

    subjects = exam_journal_link.teacher_subjects(
        organization, teacher, group_ids=_scoped_group_ids(request, organization)
    )
    selected = (request.GET.get("selected") or "").strip()
    subject_ids = {str(pk) for pk in subjects.values_list("pk", flat=True)}
    qs = ranked_subject_queryset(subjects, (request.GET.get("q") or "").strip()[:120])
    offset, limit = _page_bounds(request)
    results, has_more = _paginate(qs, offset, limit, subject_option)
    return JsonResponse(
        {
            "results": results,
            "has_more": has_more,
            "selected_ok": bool(selected) and selected in subject_ids,
        }
    )


__all__ = ["journal_teacher_subjects"]
