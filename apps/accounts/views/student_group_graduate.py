"""«Qrupu məzun et» — qrupun bütün qeydiyyatlı tələbələrinə BİR əmrlə məzuniyyət (sahib 2026-11-25).

Sahib: «Məzun etmək də olsun burada — qrupu məzun et ya da tələbəni məzun et kimi hissə olsun».

Tək tələbə: çekmecədəki «Məzun et» düyməsi mövcud hərəkət endpoint-inə (``accounts:student_registry_action``,
``kind=graduation``) gedir. Bütöv qrup: bu endpoint (``accounts:student_group_graduate``) hər tələbə üçün EYNİ
xidməti çağırır (``services.people.movements.create_movement``) — qapı, əhatə (``people.manage_academic`` + ``student.movement``),
əmr № + tarix, audit, bildiriş, ``StudentMovement`` sətri dəyişmir. Hamısı BİR tranzaksiyadadır: bir tələbə rədd
olunsa heç kim məzun edilmir və cavabda kimin niyə keçmədiyi yazılır. «Əlavə üzvlər» (öz qrupu başqadır) daxil
DEYİL — onlar öz qrupları ilə məzun olur. Səhv məzun etmə «Bərpa et» ilə geri qaytarılır.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from apps.organizations.public import get_permission_scope, visible_group

from ..services import people
from ..services.people import movements as movement_service
from ..services.rim.policy import RimAccessError

_CTX = "accounts.groups"
#: Bir əmrlə məzun edilən tələbələrin yuxarı həddi (qrup tutumu ≤ 500).
MAX_RECORDS = 500


class _Rollback(Exception):
    pass


def _error(message, *, status=400, code="invalid"):
    return JsonResponse({"ok": False, "error": code, "message": message}, status=status)


@login_required
@require_POST
def student_group_graduate(request):
    actor = people.resolve_actor(request)
    organization = actor.organization
    if organization is None or not (actor.can_move_students and actor.can_manage_academic):
        return _error(pgettext(_CTX, "Tələbəni məzun etmək səlahiyyətiniz yoxdur."), status=403, code="forbidden")
    # Qrup aktorun «Qruplar» idarə əhatəsində (``unit.group_manage``) — çekmecədəki digər yazı əməlləri kimi.
    scope = get_permission_scope(request.user, organization, "unit.group_manage", request=request)
    unit = visible_group(organization, scope, request.POST.get("id"))
    if unit is None:
        return _error(pgettext(_CTX, "Qrup tapılmadı."), status=404, code="not_found")
    record_model = django_apps.get_model("registrar", "StudentAcademicRecord")
    record_ids = list(
        record_model.objects.filter(organization=organization, group=unit, is_active=True, status="enrolled")
        .order_by("student__last_name", "student__first_name")
        .values_list("pk", flat=True)[:MAX_RECORDS]
    )
    if not record_ids:
        return _error(pgettext(_CTX, "Qrupda məzun ediləcək qeydiyyatlı tələbə yoxdur."), code="no_students")
    failures = []
    try:
        with transaction.atomic():
            for record_id in record_ids:
                try:
                    movement_service.create_movement(
                        actor,
                        record_id=str(record_id),
                        kind="graduation",
                        order_number=request.POST.get("order_number") or "",
                        order_date=request.POST.get("order_date") or "",
                        reason=request.POST.get("reason") or "",
                        request=request,
                    )
                except RimAccessError as exc:
                    name = record_model.objects.filter(pk=record_id).values_list("student__username", flat=True)
                    failures.append(f"{name.first() or record_id}: {exc.message}")
            if failures:
                raise _Rollback
    except _Rollback:
        return _error(
            pgettext(_CTX, "Qrup məzun edilmədi — heç bir dəyişiklik yazılmadı: %s") % "; ".join(failures[:5]),
            status=409,
            code="graduation_rejected",
        )
    return JsonResponse(
        {
            "ok": True,
            "graduated": len(record_ids),
            "message": pgettext(_CTX, "%d tələbə məzun edildi.") % len(record_ids),
        }
    )


__all__ = ["student_group_graduate"]
