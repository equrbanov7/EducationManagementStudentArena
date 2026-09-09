"""«Cədvəl idarəetməsi» redaktorunun JSON səthi (`schedule.manage`).

Panel özü SERVER-RENDER-lidir (dövr/qrup seçimi fraqmenti yenidən yükləyir);
burada YALNIZ redaktorun interaktiv əməlləri var:

* ``check``    — saxlamadan əvvəl konflikt + tövsiyə (heç nə yazmır);
* ``save``     — boş hüceyrədə yeni slot / mövcud slotun redaktəsi;
* ``move``     — sürüklə-burax köçürməsi (təsdiqdən sonra);
* ``place``    — parklanmış slotun yenidən yerləşdirilməsi;
* ``delete``   — YUMŞAQ silmə (sətir bazada qalır);
* ``suggest``  — «hara boşdur» tövsiyələri (səhər/günorta növbəsi);
* ``options``  — seçilmiş qrupun fənn + müəllim seçiciləri.

Domen məntiqi registrar-dadır (``apps.registrar.schedule_editor*``); bu fayl
yalnız tenant/icazə qapısı + JSON çevirmədir. Hamısı FAIL-CLOSED: icazəsi
olmayan aktor 403 alır, naməlum `action` 400.
"""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.registrar import schedule_editor
from apps.registrar import schedule_editor_actions as editor
from apps.registrar import schedule_manage
from apps.registrar import schedule_manage_actions as base

_CTX = "accounts.schedule_editor"

ALLOWED_ACTIONS = frozenset({"check", "save", "move", "place", "delete", "suggest", "options"})


def _organization(request):
    from apps.accounts.views._helpers.tenant import _get_active_organization

    return _get_active_organization(request)


def _payload(request) -> dict:
    if "application/json" in (request.content_type or "").lower():
        try:
            data = json.loads(request.body.decode("utf-8") or "{}")
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}
    return {key: value for key, value in request.POST.items()}


def _denied():
    return JsonResponse(
        {
            "ok": False,
            "error": "permission_denied",
            "message": pgettext(_CTX, "Dərs cədvəlini idarə etmək üçün icazəniz yoxdur."),
        },
        status=403,
    )


def _error(exc):
    payload = {"ok": False, "error": exc.code, "message": exc.message, "errors": exc.errors}
    payload.update(exc.extra or {})
    return JsonResponse(payload, status=exc.status)


def _group(request, organization, data):
    """Seçilmiş qrup — YALNIZ aktorun əhatəsindən (fail-closed)."""
    group_id = str(data.get("group_id") or "").strip()
    if not group_id:
        return None
    return schedule_manage.scoped_groups(request.user, organization).filter(pk=group_id).first()


def _period(organization, data):
    from apps.organizations.models import AcademicPeriod

    period_id = str(data.get("period_id") or "").strip()
    if not period_id:
        return None
    return AcademicPeriod.objects.filter(organization=organization, pk=period_id).first()


def _slot(request, organization, data):
    slot = editor.get_slot(organization, data.get("slot_id"))
    if slot is None or not schedule_manage.can_manage_offering(request.user, organization, slot.offering):
        return None
    return slot


def _check(request, organization, data):
    group = _group(request, organization, data)
    period = _period(organization, data)
    cleaned, errors = schedule_editor.parse_cell(data, organization=organization)
    if errors:
        return JsonResponse({"ok": False, "errors": errors, "conflicts": [], "suggestions": []})
    from django.contrib.auth import get_user_model

    from apps.registrar.models import Subject

    subject = Subject.objects.filter(organization=organization, pk=str(data.get("subject_id") or "").strip()).first()
    instructor_id = str(data.get("instructor_id") or "").strip()
    instructor = get_user_model().objects.filter(pk=instructor_id).first() if instructor_id else None
    try:
        # `create=False`: quru yoxlama bazaya HEÇ NƏ yazmır (açılış yaranmır).
        offering, _c, _a = schedule_editor.resolve_offering(
            actor=request.user,
            organization=organization,
            group=group,
            period=period,
            subject=subject,
            instructor=instructor,
            create=False,
        )
    except schedule_editor.CellError as exc:
        return _error(exc)
    verdict = schedule_editor.check_cell(
        organization=organization,
        offering=offering,
        cleaned=cleaned,
        exclude_id=str(data.get("slot_id") or "").strip() or None,
    )
    return JsonResponse(verdict)


def _options(request, organization, data):
    group = _group(request, organization, data)
    period = _period(organization, data)
    return JsonResponse(
        {
            "ok": True,
            "subjects": schedule_editor.allowed_subjects(organization=organization, group=group, period=period),
            "teachers": schedule_editor.teacher_choices(organization),
        }
    )


def _suggest(request, organization, data):
    slot = _slot(request, organization, data) if data.get("slot_id") else None
    group = _group(request, organization, data)
    return JsonResponse(
        {
            "ok": True,
            "suggestions": editor.suggestions_for(
                organization=organization,
                slot=slot,
                group=group,
                instructor_id=str(data.get("instructor_id") or "").strip() or None,
                shift=str(data.get("shift") or "").strip(),
                week_type=str(data.get("week_type") or "").strip() or None,
            ),
        }
    )


def _write(request, organization, action, data):
    if action == "save":
        group = _group(request, organization, data)
        period = _period(organization, data)
        if group is None or period is None:
            return _denied()
        return JsonResponse(
            {
                "ok": True,
                **editor.save_cell(
                    actor=request.user,
                    organization=organization,
                    group=group,
                    period=period,
                    data=data,
                    request=request,
                ),
            }
        )
    slot = _slot(request, organization, data)
    if slot is None:
        return _denied()
    if action == "delete":
        row = base.delete_slot(actor=request.user, organization=organization, slot=slot, request=request)
        return JsonResponse({"ok": True, "slot": row})
    handler = editor.place_parked if action == "place" else editor.move_slot
    return JsonResponse(
        {"ok": True, **handler(actor=request.user, organization=organization, slot=slot, data=data, request=request)}
    )


@never_cache
@login_required
@require_POST
def schedule_editor_action(request):
    """Redaktorun vahid giriş nöqtəsi (allow-list + fail-closed qapı)."""
    organization = _organization(request)
    if organization is None or not schedule_manage.can_manage(request.user, organization):
        return _denied()

    data = _payload(request)
    action = str(data.get("action") or "").strip()
    if action not in ALLOWED_ACTIONS:
        return JsonResponse(
            {"ok": False, "error": "unknown_action", "message": pgettext(_CTX, "Naməlum əməliyyat.")}, status=400
        )
    try:
        if action == "check":
            return _check(request, organization, data)
        if action == "options":
            return _options(request, organization, data)
        if action == "suggest":
            return _suggest(request, organization, data)
        return _write(request, organization, action, data)
    except schedule_editor.CellError as exc:
        return _error(exc)
    except base.ScheduleManageError as exc:
        conflict = exc.errors.pop("conflict_slot", None)
        payload = {"ok": False, "error": exc.code, "message": exc.message, "errors": exc.errors}
        if conflict:
            payload["conflict"] = conflict
        return JsonResponse(payload, status=exc.status)


__all__ = ["ALLOWED_ACTIONS", "schedule_editor_action"]
