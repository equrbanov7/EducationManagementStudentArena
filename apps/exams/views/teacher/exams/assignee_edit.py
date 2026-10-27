"""teacher exams paketi — «Tapşırıq təyin olunmuşlar» səhifəsindən təyinatın dəyişdirilməsi (sahib 2026-10-27).

Sahib: «oradan da qrup ya da tək tələbə əlavə etmək üçün yer olsun». Bu modul sehrbazın saxlama yolunu
YENİDƏN YAZMIR və ondan YAN KEÇMİR — eyni qapı modullarını eyni ardıcıllıqla çağırır:

* qrup id-ləri — ``unit_assignment.resolve_requested_units`` (tenant + ``exam.edit`` əhatəsi, yanlış id → 400);
  yazı — ``unit_assignment.apply_allowed_units`` (əhatədən kənar mövcud qruplar qorunur);
* nəticəli midtermdə jurnal bağlantısı azalırsa — ``exam_subject_change`` təsdiq + səbəb (409);
* fənnin jurnalında olmayan YENİ qrup — ``unit_coverage.check`` məcburi əlavə + səbəb (400) və audit;
* sonra ``exam_journal_link.after_exam_saved``, PIN provizionu, yeni alıcılara bildiriş, ``AuditLog``,
  metadata keşinin təmizlənməsi və bloklamayan jurnal xəbərdarlıqları (sehrbazdakı kimi);
* fərdi tələbə — sehrbazın ``allowed_users`` scope-u (``lookups._org_user_queryset``); istisna — formanın
  ``excluded_users_within_assignment`` qaydası (yalnız qrupla təyin olunmuş tələbə istisna edilir).

İcazə: ``exam.edit`` + müəllif / superadmin / (midterm-final) imtahan mərkəzi — redaktə ilə eyni.
"""

from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from apps.exams.services import exam_journal_coverage as _journal_coverage
from apps.exams.services import exam_journal_link as _journal_link
from apps.exams.services import exam_subject_change as _exam_subject_change
from apps.exams.services.access_policy import _ensure_teacher

from . import unit_assignment as _units
from . import unit_coverage as _unit_coverage
from ._shared import _ensure_exam_permission, _get_editable_exam_or_404, _resolve_required_organization

logger = logging.getLogger(__name__)

PERMISSION = "exam.edit"
#: Audit səbəbi (``AuditLog.reason``) — imtahan səhifəsindən təyinat dəyişikliyi.
AUDIT_REASON = "exam_assignees_updated"
#: Bir sorğuda əlavə olunan fərdi tələbə həddi.
MAX_USERS = 100

_CTX = "exams.assignees"


class _Reject(Exception):
    """Əməl rədd edildi → JSON cavab (status + payload)."""

    def __init__(self, status, payload):
        super().__init__(status, payload)
        self.status = status
        self.payload = payload


def _error(message, status=400, **extra):
    return _Reject(status, {"success": False, "error": str(message), **extra})


def _int_ids(values) -> list:
    out = []
    for raw in values:
        for piece in str(raw or "").split(","):
            piece = piece.strip()
            if piece.isdigit() and int(piece) not in out:
                out.append(int(piece))
    return out


# ── reyestr qrupları ──────────────────────────────────────────────────────────


def _visible_units(request, organization, exam):
    """İmtahanın istifadəçi əhatəsindəki (silə / saxlaya biləcəyi) mövcud qrupları."""
    existing = list(exam.allowed_units.values_list("pk", flat=True))
    if not existing:
        return []
    return list(_units.exam_unit_candidates(request, organization, permission=PERMISSION).filter(pk__in=existing))


def _commit_units(request, organization, exam, units, new_units):
    """Sehrbazın qrup saxlama qapıları: fənn/jurnal təsdiqi → əhatə → yazı → audit → jurnal bağlantısı."""
    snapshot = _exam_subject_change.take_snapshot(exam)
    final_ids = _units.final_unit_ids(request, organization, exam, units, permission=PERMISSION)
    decision = _exam_subject_change.decide(snapshot, exam, unit_ids=final_ids)
    subject_reason = ""
    if decision is not None:
        subject_reason, error = _exam_subject_change.validate_confirmation(request.POST)
        if not subject_reason:
            raise _error(
                error,
                status=409,
                subject_change_required={"students": decision.students, "subject": decision.new_subject_label},
            )
    unit_check = _unit_coverage.check(request, organization, exam, snapshot.unit_ids, new_units)
    if unit_check.is_blocked:
        raise _error(unit_check.error, unit_coverage_required=[row.as_json() for row in unit_check.blocked])

    _units.apply_allowed_units(request, organization, exam, units, permission=PERMISSION)
    change_log = None
    if decision is not None:
        change_log = _exam_subject_change.record_decision(
            exam, decision, reason=subject_reason, user=request.user, request=request
        )
    _unit_coverage.record(exam, unit_check, user=request.user, request=request)
    _journal_link.after_exam_saved(
        exam,
        previous_subject_id=snapshot.subject_id,
        previous_link_ids=snapshot.link_ids,
        by_user=request.user,
        change_log_id=getattr(change_log, "pk", None),
    )


def _add_units(request, organization, exam) -> dict:
    requested, error = _units.resolve_requested_units(request, organization, request.POST, permission=PERMISSION)
    if error:
        raise _error(error)
    existing = set(exam.allowed_units.values_list("pk", flat=True))
    new_units = [unit for unit in requested if unit.pk not in existing]
    if not new_units:
        raise _error(pgettext(_CTX, "Seçilmiş qruplar artıq bu imtahana təyin olunub."))
    _commit_units(request, organization, exam, _visible_units(request, organization, exam) + new_units, new_units)
    return {"units": [_units.unit_display_label(unit) for unit in new_units]}


def _remove_unit(request, organization, exam) -> dict:
    unit_id = str(request.POST.get("unit") or "").strip()
    visible = _visible_units(request, organization, exam)
    target = next((unit for unit in visible if str(unit.pk) == unit_id), None)
    if target is None:
        raise _error(pgettext(_CTX, "Qrup tapılmadı və ya onu çıxarmaq icazəniz yoxdur."))
    _commit_units(request, organization, exam, [unit for unit in visible if unit.pk != target.pk], [])
    return {"units": [_units.unit_display_label(target)]}


# ── fərdi tələbələr və istisnalar ─────────────────────────────────────────────


def _org_student(request, organization, user_id):
    from .lookups import _org_user_queryset

    user = _org_user_queryset(request, organization).filter(pk=user_id).first()
    if user is None:
        raise _error(pgettext(_CTX, "Tələbə tapılmadı."))
    return user


def _add_users(request, organization, exam) -> dict:
    from .lookups import _org_user_queryset

    ids = _int_ids(request.POST.getlist("users"))[: MAX_USERS + 1]
    if not ids:
        raise _error(pgettext(_CTX, "Ən azı bir tələbə seçin."))
    if len(ids) > MAX_USERS:
        raise _error(pgettext(_CTX, "Bir dəfəyə ən çox %(max)d tələbə əlavə etmək olar.") % {"max": MAX_USERS})
    users = list(_org_user_queryset(request, organization).filter(pk__in=ids))
    if len(users) != len(ids):
        raise _error(pgettext(_CTX, "Tələbə tapılmadı."))
    exam.allowed_users.add(*users)
    # Əvvəl istisna edilmiş tələbəni fərdi əlavə etmək — onu yenidən açmaq niyyətidir.
    exam.excluded_users.remove(*users)
    return {"users": [user.pk for user in users]}


def _remove_user(request, organization, exam) -> dict:
    ids = _int_ids([request.POST.get("user")])
    if not ids or not exam.allowed_users.filter(pk=ids[0]).exists():
        raise _error(pgettext(_CTX, "Bu tələbə imtahana fərdi təyin olunmayıb."))
    exam.allowed_users.remove(ids[0])
    return {"users": ids[:1]}


def _exclude_user(request, organization, exam) -> dict:
    from apps.exams.forms.exam_exclusions import excluded_users_within_assignment

    ids = _int_ids([request.POST.get("user")])
    user = _org_student(request, organization, ids[0] if ids else 0)
    within = excluded_users_within_assignment(
        get_user_model().objects.filter(pk=user.pk),
        allowed_groups=exam.allowed_groups.all(),
        unit_ids=[],
        organization=organization,
        instance=exam,
    )
    if not within.exists():
        raise _error(pgettext(_CTX, "Yalnız qrupla təyin olunmuş tələbəni istisna etmək olar."))
    exam.excluded_users.add(user)
    return {"users": [user.pk]}


def _include_user(request, organization, exam) -> dict:
    ids = _int_ids([request.POST.get("user")])
    if not ids or not exam.excluded_users.filter(pk=ids[0]).exists():
        raise _error(pgettext(_CTX, "Bu tələbə istisna siyahısında deyil."))
    exam.excluded_users.remove(ids[0])
    return {"users": ids[:1]}


ACTIONS = {
    "add_units": _add_units,
    "remove_unit": _remove_unit,
    "add_users": _add_users,
    "remove_user": _remove_user,
    "exclude_user": _exclude_user,
    "include_user": _include_user,
}


def _success_message(action) -> str:
    return {
        "add_units": pgettext(_CTX, "Qrup imtahana əlavə olundu."),
        "remove_unit": pgettext(_CTX, "Qrup imtahandan çıxarıldı."),
        "add_users": pgettext(_CTX, "Tələbə imtahana əlavə olundu."),
        "remove_user": pgettext(_CTX, "Fərdi icazə çıxarıldı."),
        "exclude_user": pgettext(_CTX, "Tələbə imtahandan istisna edildi."),
        "include_user": pgettext(_CTX, "Tələbə yenidən imtahana daxil edildi."),
    }[action]


def _after_access_change(request, organization, exam, *, action, previous_recipient_ids, details):
    """Sehrbaz saxlamasından sonrakı yan təsirlər: PIN, bildiriş, audit, keş."""
    from apps.audit.public import log_action
    from apps.exams.services.student_pins import provision_exam_student_pins
    from apps.notifications.public import get_exam_assigned_user_ids, notify_task_assignment
    from core.constants import AuditAction

    provision_exam_student_pins(exam)
    current_ids = get_exam_assigned_user_ids(exam)
    new_ids = current_ids - previous_recipient_ids
    if new_ids and exam.is_active:
        notify_task_assignment(task=exam, user_ids=new_ids, task_kind="exam")
    log_action(
        action=AuditAction.UPDATE,
        user=request.user,
        organization=organization,
        obj=exam,
        new_values={"title": exam.title, "action": action},
        changes={"action": action, **{key: [str(value) for value in values] for key, values in details.items()}},
        reason=AUDIT_REASON,
        request=request,
    )
    try:
        from core.cache import invalidate_exam_metadata_cache

        invalidate_exam_metadata_cache(exam.pk)
    except Exception:  # noqa: BLE001 — sehrbazdakı kimi: keş xətası saxlamanı sındırmır
        logger.warning("Exam metadata cache invalidation failed for exam %s", exam.pk, exc_info=True)


@login_required
@require_POST
def exam_assignees_update(request, slug):
    """POST ``action`` = add_units | remove_unit | add_users | remove_user | exclude_user | include_user."""
    organization = _resolve_required_organization(request)
    if organization is None:
        return JsonResponse({"success": False, "error": ""}, status=400)
    _ensure_teacher(request.user)
    _ensure_exam_permission(request, PERMISSION)
    exam = _get_editable_exam_or_404(request, slug)
    action = str(request.POST.get("action") or "").strip()
    handler = ACTIONS.get(action)
    if handler is None:
        return JsonResponse({"success": False, "error": pgettext(_CTX, "Naməlum əməliyyat.")}, status=400)

    from apps.notifications.public import get_exam_assigned_user_ids

    try:
        with transaction.atomic():
            previous_recipient_ids = get_exam_assigned_user_ids(exam)
            details = handler(request, organization, exam)
            _after_access_change(
                request,
                organization,
                exam,
                action=action,
                previous_recipient_ids=previous_recipient_ids,
                details=details,
            )
    except _Reject as reject:
        return JsonResponse(reject.payload, status=reject.status)

    messages.success(request, _success_message(action))
    for warning in _journal_coverage.exam_coverage_warnings(exam):
        messages.warning(request, warning)
    return JsonResponse({"success": True, "message": _success_message(action)})


__all__ = ["ACTIONS", "AUDIT_REASON", "exam_assignees_update"]
