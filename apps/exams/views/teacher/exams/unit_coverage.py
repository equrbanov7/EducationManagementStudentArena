"""teacher exams paketi — qrup imtahanın fənnini keçmir: JSON yoxlaması + saxlama qapısı (sahib 2026-10-27).

Qayda və audit: ``apps/exams/services/exam_unit_coverage.py``. Bu modul yalnız view yapışqanıdır:

* :func:`unit_journal_coverage` — sehrbaz qrup seçəndə (və fənn / kateqoriya dəyişəndə) çağırır: hər qrup
  üçün tələbə sayı, fənnin cari jurnalında olmayanların sayı + bir neçə adı, qrupun bu fəndən jurnalı varmı.
  Əhatə: istifadəçinin ``exam.create`` / ``exam.edit`` icazəsi və həmin əhatədəki reyestr qrupları (tenant).
* :func:`check` — forma təmizləndikdən SONRA, saxlamadan ƏVVƏL: YENİ əlavə olunan əhatəsiz qrup məcburi əlavə
  + səbəb olmadan saxlanmır (400, sehrbaz «Giriş» addımına qayıdır).
"""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.utils.translation import pgettext
from django.views.decorators.http import require_GET

from apps.exams.services import exam_unit_coverage
from apps.exams.services.access_policy import _ensure_teacher
from core.permissions import request_has_permission

from . import unit_assignment as _units
from ._shared import _resolve_required_organization
from .lookups import _unit_ids_param, _uuid_param

#: Bloklananda sehrbazın fokuslayacağı addım / sahə («Giriş», reyestr qrupları).
ERROR_STEP = 2
ERROR_FIELD = _units.UNITS_FIELD_NAME
#: Bir sorğuda yoxlanan qrup həddi (sehrbaz adətən bir-iki qrup göndərir).
MAX_UNITS = 50

_EMPTY = {"applies": False, "groups": []}


def _permission(request) -> str:
    for permission in ("exam.create", "exam.edit"):
        if request_has_permission(request, permission):
            return permission
    raise PermissionDenied(
        pgettext("exams.view.exams.permission", "missing_required_permission").format(permission="exam.edit")
    )


def _subject(organization, subject_id):
    from apps.registrar.public import exam_journal_link

    return exam_journal_link.organization_subject(organization, subject_id)


@login_required
@require_GET
def unit_journal_coverage(request):
    """``?units=<uuid>,…&subject=<uuid>&category=midterm`` → qrupların fənn jurnalı əhatəsi."""
    _ensure_teacher(request.user)
    organization = _resolve_required_organization(request)
    if organization is None:
        return JsonResponse(_EMPTY)
    permission = _permission(request)
    unit_ids = _unit_ids_param(request)[:MAX_UNITS]
    category = (request.GET.get("category") or "").strip()
    subject = _subject(organization, _uuid_param(request, "subject"))
    if not unit_ids or subject is None or not exam_unit_coverage.applies(subject.pk, category):
        return JsonResponse(_EMPTY)
    by_id = {
        str(unit.pk): unit
        for unit in _units.exam_unit_candidates(request, organization, permission=permission).filter(pk__in=unit_ids)
    }
    units = [by_id[value] for value in unit_ids if value in by_id]
    rows = exam_unit_coverage.coverage(organization, subject.pk, units)
    return JsonResponse(
        {
            "applies": True,
            "subject": _subject_label(subject),
            "groups": [row.as_json() for row in rows],
        }
    )


def _subject_label(subject) -> str:
    from apps.exams.services.exam_subject_change import subject_label

    return subject_label(subject)


def check(request, organization, exam, existing_unit_ids, units):
    """→ :class:`exam_unit_coverage.Check` — ``exam`` forma təmizlədikdən sonrakı (saxlanmamış) instansdır.

    ``existing_unit_ids`` — imtahanın saxlamadan ƏVVƏLKİ qrupları (redaktədə yoxlanmır)."""
    existing = {str(pk) for pk in existing_unit_ids or ()}
    new_units = [unit for unit in units or () if str(unit.pk) not in existing]
    return exam_unit_coverage.check_new_units(
        organization,
        subject_id=getattr(exam, "subject_id", None),
        category=getattr(exam, "exam_type_extended", ""),
        new_units=new_units,
        data=request.POST,
    )


def form_context(existing_unit_ids, result=None, data=None) -> dict:
    """Sehrbaz şablonuna: imtahanın MÖVCUD qrupları (klient onları yoxlamır), göndərilmiş məcburi əlavələr və —
    bloklanmış 400 cavabında — bloklanan qruplar (modal yenidən açılır) + xəta mətni."""
    import json

    context = {
        "unit_coverage_existing_json": json.dumps(sorted(str(pk) for pk in existing_unit_ids or ())),
        "unit_coverage_forced_json": json.dumps(
            exam_unit_coverage.parse_forced(data) if data is not None else {}, ensure_ascii=False
        ),
    }
    if result is not None and result.is_blocked:
        context["unit_coverage_error"] = result.error
        context["unit_coverage_blocked_json"] = json.dumps(
            [row.as_json() for row in result.blocked], ensure_ascii=False
        )
    return context


def record(exam, result, *, user, request=None) -> None:
    if result is None or not result.accepted:
        return
    exam_unit_coverage.record_forced(
        exam,
        result.accepted,
        user=user,
        subject_label=_subject_label(exam.subject if exam.subject_id else None),
        request=request,
    )


__all__ = ["ERROR_FIELD", "ERROR_STEP", "check", "form_context", "record", "unit_journal_coverage"]
