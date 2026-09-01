"""Sillabus müəllim UI-nın JSON səthi — autosave, əməllər, baxış paneli.

Bütün yazı əməliyyatları :mod:`apps.syllabus.services`-ə DELEQASİYA olunur:
burada nə ``status = …`` yazılır, nə də icazə məntiqi təkrarlanır. Bu qat yalnız
(1) HTTP giriş yoxlaması, (2) JSON gövdəsinin oxunması, (3) domen xəta kodunun
istifadəçi mətninə çevrilməsi ilə məşğuldur.

Səhv kodları ``.labels.TRANSITION_MESSAGES``-dən gəlir — mətn domen qatında
saxlanılmır.
"""

from __future__ import annotations

import json
import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils.translation import pgettext_lazy
from django.views.decorators.http import require_GET, require_POST

from apps.syllabus import services
from apps.syllabus.constants import PERM_EDIT, SECTION_ORDER, SyllabusStatus
from apps.syllabus.models import Syllabus, SyllabusVersion
from apps.syllabus.state_machine import TransitionDenied

from .._helpers import _get_active_organization
from .labels import transition_text
from .lookup import safe_uuid
from .preview import build_preview_payload

logger = logging.getLogger(__name__)

_CTX = "accounts.syllabus"

_NO_ORG = pgettext_lazy(_CTX, "Aktiv təşkilat seçilməyib.")
_NOT_FOUND = pgettext_lazy(_CTX, "Sillabus tapılmadı.")
_BAD_REQUEST = pgettext_lazy(_CTX, "Sorğu düzgün deyil.")
_REASON_REQUIRED = pgettext_lazy(_CTX, "Səbəb ən azı %(min)s simvol olmalıdır.")
_SAVED = pgettext_lazy(_CTX, "Saxlanıldı")
_DRAFT_CREATED = pgettext_lazy(_CTX, "Qaralama yaradıldı — məzmunu doldurub təsdiqə göndərin.")
_COPIED = pgettext_lazy(_CTX, "Keçmiş versiyanın məzmunu köçürüldü, yeni QARALAMA açıldı.")
_VERSION_CREATED = pgettext_lazy(_CTX, "Yeni versiya qaralaması yaradıldı. Təsdiqlənmiş versiya aktiv qalır.")
_SUBMITTED = pgettext_lazy(_CTX, "Sillabus kafedra müdirinin təsdiq növbəsinə göndərildi.")
_WITHDRAWN = pgettext_lazy(_CTX, "Təqdimat geri çağırıldı, status qaralamaya qaytarıldı.")
_RESUMED = pgettext_lazy(_CTX, "Düzəlişə başlandı — bölmələr yenidən redaktə oluna bilər.")

#: «Geri çağır» dialoqunun minimum səbəb uzunluğu (dizayn §3.1).
MIN_REASON_LENGTH = 15


def _body(request) -> dict:
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except ValueError:
        # `UnicodeDecodeError` və `json.JSONDecodeError` — ikisi də `ValueError`
        # alt-sinfidir, ona görə tək tutucu hər iki halı əhatə edir (flake8 B014).
        return {}


def _fail(message, *, status: int = 400, **extra) -> JsonResponse:
    payload = {"ok": False, "error": str(message)}
    payload.update(extra)
    return JsonResponse(payload, status=status)


def _context(request):
    """``(organization, actor)`` — aktiv təşkilat və həll olunmuş aktor."""
    organization = _get_active_organization(request)
    if organization is None:
        return None, None
    return organization, services.resolve_actor(request.user, organization, request=request)


def _version(organization, version_id):
    parsed = safe_uuid(version_id)
    if parsed is None:
        return None
    return (
        SyllabusVersion.objects.filter(organization=organization, pk=parsed)
        .select_related("syllabus", "syllabus__subject", "syllabus__period")
        .first()
    )


@login_required
@require_POST
def syllabus_section_save(request, version_id):
    """Bölmə autosave (PATCH semantikası) — optimistik kilid ilə.

    Cavab: ``{ok, revision, completion:{percent,sections,issues}}``.
    Konflikt (``section.conflict``) 409 ilə qayıdır ki, redaktor «versiya
    konflikti» bannerini göstərsin.
    """
    organization, actor = _context(request)
    if organization is None:
        return _fail(_NO_ORG, status=403)
    version = _version(organization, version_id)
    if version is None:
        return _fail(_NOT_FOUND, status=404)

    payload = _body(request)
    section_id = (payload.get("section") or "").strip()
    if section_id not in SECTION_ORDER:
        return _fail(_BAD_REQUEST)
    data = payload.get("data")
    if not isinstance(data, dict):
        return _fail(_BAD_REQUEST)

    try:
        row, report = services.save_section(
            version=version,
            section_id=section_id,
            data=data,
            actor=actor,
            expected_revision=payload.get("revision"),
            request=request,
        )
    except services.SectionConflict as conflict:
        return _fail(
            transition_text(conflict.code, conflict.params),
            status=409,
            code=conflict.code,
            revision=conflict.current_revision,
        )
    except TransitionDenied as denied:
        return _fail(transition_text(denied.code, denied.params), status=403, code=denied.code)

    return JsonResponse(
        {
            "ok": True,
            "message": str(_SAVED),
            "section": section_id,
            "revision": row.revision,
            "completion": report.as_dict(),
        }
    )


def _do_create(request, organization, actor, payload):
    from apps.registrar.models import CourseOffering

    offering = (
        CourseOffering.objects.filter(
            organization=organization, pk=safe_uuid(payload.get("offering")), instructor=request.user, is_active=True
        )
        .select_related("subject", "period", "group")
        .first()
    )
    if offering is None:
        return None, _NOT_FOUND
    syllabus, version = services.create_draft(
        organization=organization,
        subject=offering.subject,
        period=offering.period,
        actor=actor,
        offering=offering,
        chair_unit=getattr(offering.group, "parent", None) if offering.group_id else None,
        author=request.user,
        # BOŞ ÖTÜRÜLÜR VƏ BU DOĞRUDUR: ``CourseOffering`` yalnız `lesson_hours`
        # CƏMİNİ daşıyır, `lecture/seminar/lab` bölgüsünü yox.  Uydurma bölgü
        # yazmaqdansa boş buraxırıq; `completion._check_week` plan verilməyəndə
        # saat balansını yoxlamır (bax `test_completion_plan_hours.py`).
        # Bölgü modelləşəndə (apps/workload ↔ apps/syllabus müqaviləsi) burada
        # ötürülməlidir və qayda öz-özünə yenidən işə düşəcək.
        plan_hours={},
        request=request,
    )
    return version, _DRAFT_CREATED


def _do_copy(request, organization, actor, payload):
    syllabus = Syllabus.objects.filter(organization=organization, pk=safe_uuid(payload.get("syllabus"))).first()
    if syllabus is None:
        return None, _NOT_FOUND
    _new, version = services.copy_from_previous(
        source_syllabus=syllabus,
        target_period=syllabus.period,
        actor=actor,
        request=request,
    )
    return version, _COPIED


def _do_new_version(request, organization, actor, payload):
    syllabus = Syllabus.objects.filter(organization=organization, pk=safe_uuid(payload.get("syllabus"))).first()
    if syllabus is None:
        return None, _NOT_FOUND
    kind = payload.get("kind") if payload.get("kind") in {"minor", "major"} else "minor"
    return services.create_next_version(syllabus=syllabus, actor=actor, kind=kind, request=request), _VERSION_CREATED


@login_required
@require_POST
def syllabus_action(request):
    """Müəllim əməlləri: qaralama yarat / köçür / yeni versiya / göndər / geri çağır.

    ⚠️ Qərar əməlləri (təsdiq / düzəliş / rədd) BURADA YOXDUR — onlar kafedra
    müdiri səthinə aiddir və ayrıca icazə açarları ilə qorunur.
    """
    organization, actor = _context(request)
    if organization is None:
        return _fail(_NO_ORG, status=403)
    if not actor.has(PERM_EDIT):
        return _fail(transition_text("transition.permission_denied"), status=403)

    payload = _body(request)
    action = (payload.get("action") or "").strip()

    try:
        if action == "create":
            version, message = _do_create(request, organization, actor, payload)
        elif action == "copy":
            version, message = _do_copy(request, organization, actor, payload)
        elif action == "new_version":
            version, message = _do_new_version(request, organization, actor, payload)
        elif action in {"submit", "withdraw", "resume"}:
            version = _version(organization, payload.get("version"))
            if version is None:
                return _fail(_NOT_FOUND, status=404)
            if action == "submit":
                version = services.submit(version=version, actor=actor, request=request)
                message = _SUBMITTED
            elif action == "resume":
                version = services.resume_editing(version=version, actor=actor, request=request)
                message = _RESUMED
            else:
                reason = (payload.get("reason") or "").strip()
                if len(reason) < MIN_REASON_LENGTH:
                    return _fail(str(_REASON_REQUIRED) % {"min": MIN_REASON_LENGTH})
                version = services.withdraw(version=version, actor=actor, reason=reason, request=request)
                message = _WITHDRAWN
        else:
            return _fail(_BAD_REQUEST)
    except TransitionDenied as denied:
        return _fail(transition_text(denied.code, denied.params), status=409, code=denied.code)

    if version is None:
        return _fail(message, status=404)
    return JsonResponse(
        {
            "ok": True,
            "message": str(message),
            "version": str(version.pk),
            "status": version.status,
            "status_label": str(SyllabusStatus(version.status).label),
        }
    )


@login_required
@require_GET
def syllabus_preview(request, syllabus_id):
    """Siyahının sağdan açılan BAXIŞ panelinin məzmunu (oxu-rejimi + tarixçə)."""
    organization, actor = _context(request)
    if organization is None:
        return _fail(_NO_ORG, status=403)
    syllabus = (
        Syllabus.objects.filter(organization=organization, pk=syllabus_id)
        .select_related("subject", "period", "program", "current_version", "approved_version", "offering")
        .first()
    )
    if syllabus is None:
        return _fail(_NOT_FOUND, status=404)
    if not services.can_view(actor, syllabus):
        return _fail(transition_text("transition.out_of_scope"), status=403)
    return JsonResponse({"ok": True, **build_preview_payload(syllabus)})


__all__ = ["MIN_REASON_LENGTH", "syllabus_action", "syllabus_preview", "syllabus_section_save"]
