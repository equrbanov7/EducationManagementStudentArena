"""Sillabusun təkrar istifadəsinin JSON səthi — dialoq seçimləri + əməllər.

``GET  profile/syllabus/reuse/?offering=<uuid>|syllabus=<uuid>`` — dialoq məlumatı;
``POST profile/syllabus/reuse/action/`` — ``{action, source, offering|syllabus, offerings}``:

* ``link``      — «Eyni sillabusu istifadə et (bağla)»;
* ``copy``      — «Kopyala və uyğunlaşdır»;
* ``bulk``      — «Hamısına tətbiq et» (``offerings``: açılış id-ləri);
* ``unlink``    — «Ayır» (``syllabus``: bağlı dosye);
* ``sync``      — «Mənbədən yenilə» (``syllabus``: bağlı dosye);
* ``propagate`` — «Bağlı sillabuslara tətbiq et» (``syllabus``: mənbə dosye).

Bütün qərarlar ``apps.syllabus.services.reuse``-dadır; burada yalnız giriş yoxlaması,
registrar məlumatının toplanması və xəta kodunun mətnə çevrilməsi var.  Oxuya
bilmədiyi mənbə və ya başqasının açılışı aktora 404 qaytarır (mövcudluq sızmır).
"""

from __future__ import annotations

import logging

from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.http import JsonResponse
from django.utils.translation import pgettext_lazy
from django.views.decorators.http import require_GET, require_POST

from apps.syllabus.public import PERM_EDIT, SyllabusStatus, TransitionDenied, services

from . import reuse_context
from .api import _body, _context, _fail
from .labels import transition_text
from .lookup import safe_uuid

logger = logging.getLogger(__name__)

_CTX = "accounts.syllabus"

_NO_ORG = pgettext_lazy(_CTX, "Aktiv təşkilat seçilməyib.")
_NOT_FOUND = pgettext_lazy(_CTX, "Sillabus tapılmadı.")
_BAD_REQUEST = pgettext_lazy(_CTX, "Sorğu düzgün deyil.")
_LINKED = pgettext_lazy(
    _CTX, "Sillabus bağlandı — %(group)s qrupunun təsdiqlənmiş sillabusu ilə eyni məzmun qüvvəyə mindi."
)
_COPIED = pgettext_lazy(_CTX, "Məzmun kopyalandı və saatlara uyğunlaşdırıldı — qaralamanı yoxlayıb təsdiqə göndərin.")
_BULK = pgettext_lazy(_CTX, "Bağlandı: %(linked)s · kopyalandı: %(copied)s · ötürüldü: %(skipped)s.")
_UNLINKED = pgettext_lazy(
    _CTX, "Bağ ayrıldı — redaktə üçün müstəqil qaralama açıldı. Təsdiqlənmiş nüsxə qüvvədə qalır."
)
_SYNCED = pgettext_lazy(_CTX, "Mənbənin son təsdiqlənmiş versiyası bu sillabusa tətbiq olundu.")
_PROPAGATED = pgettext_lazy(_CTX, "Yeniləndi: %(synced)s · artıq son versiyada: %(already)s · ötürüldü: %(skipped)s.")


def _guard(request):
    organization, actor = _context(request)
    if organization is None:
        return None, None, _fail(_NO_ORG, status=403)
    if not actor.has(PERM_EDIT):
        return None, None, _fail(transition_text("transition.permission_denied"), status=403)
    return organization, actor, None


@login_required
@require_GET
def syllabus_reuse_options(request):
    """Dialoq: hədəf + qonşu sillabuslar + «Hamısına tətbiq et» siyahısı."""
    organization, actor, denied = _guard(request)
    if denied is not None:
        return denied
    target = reuse_context.resolve_target(
        organization,
        actor,
        offering_id=safe_uuid((request.GET.get("offering") or "").strip()),
        syllabus_id=safe_uuid((request.GET.get("syllabus") or "").strip()),
    )
    if target is None:
        return _fail(_NOT_FOUND, status=404)
    return JsonResponse({"ok": True, **reuse_context.build_options(organization, actor, target)})


def _readable_source(organization, actor, raw_id):
    """Mənbə dosye — aktor OXUYA bilmirsə ``None`` (404; mövcudluq sızmır)."""
    source = reuse_context.load_syllabus(organization, safe_uuid(raw_id))
    if source is None or not services.can_view(actor, source):
        return None
    return services.reuse_rules.reuse_root(source)


def _own_syllabus(organization, actor, raw_id):
    syllabus = reuse_context.load_syllabus(organization, safe_uuid(raw_id))
    if syllabus is None or not services.can_view(actor, syllabus):
        return None
    return syllabus


def _version_payload(version, message, **extra):
    payload = {"ok": True, "message": str(message), **extra}
    if version is not None:
        payload.update(
            version=str(version.pk),
            status=version.status,
            status_label=str(SyllabusStatus(version.status).label),
        )
    return JsonResponse(payload)


def _single(request, organization, actor, payload, action):
    source = _readable_source(organization, actor, payload.get("source"))
    if source is None:
        return _fail(_NOT_FOUND, status=404)
    target = reuse_context.resolve_target(
        organization,
        actor,
        offering_id=safe_uuid(payload.get("offering")),
        syllabus_id=safe_uuid(payload.get("syllabus")),
    )
    if target is None:
        return _fail(_NOT_FOUND, status=404)
    if action == "link":
        syllabus, version = services.reuse.link(source=source, target=target, actor=actor, request=request)
        message = str(_LINKED) % {"group": reuse_context.group_label(source)}
    else:
        syllabus, version = services.reuse.copy_adjust(source=source, target=target, actor=actor, request=request)
        message = _COPIED
    return _version_payload(version, message, syllabus=str(syllabus.pk), mode=action)


def _bulk(request, organization, actor, payload):
    source = _readable_source(organization, actor, payload.get("source"))
    if source is None:
        return _fail(_NOT_FOUND, status=404)
    raw = payload.get("offerings")
    if not isinstance(raw, list) or not raw or len(raw) > reuse_context.MAX_BULK_TARGETS:
        return _fail(_BAD_REQUEST)
    wanted = {parsed for parsed in (safe_uuid(item) for item in raw) if parsed is not None}
    if not wanted:
        return _fail(_BAD_REQUEST)
    # Yalnız aktorun ÖZ açılışları — başqasının id-si sakitcə atılır (fail-closed).
    pairs = reuse_context.candidate_targets(
        organization,
        actor,
        subject_id=source.subject_id,
        period_id=source.period_id,
        exclude_offering_id=source.offering_id,
        only_ids=wanted,
    )
    results = services.reuse.apply_bulk(
        source=source, targets=[target for target, _chair in pairs], actor=actor, request=request
    )
    for row in results:
        if row["code"]:
            row["message"] = transition_text(row["code"])
    counts = {key: sum(1 for row in results if row["status"] == key) for key in ("linked", "copied")}
    counts["skipped"] = len(results) - counts["linked"] - counts["copied"]
    return JsonResponse({"ok": True, "message": str(_BULK) % counts, "results": results, "counts": counts})


def _hours_for(syllabus) -> dict:
    """Bağlı hədəfin CARİ rəsmi saatı (yoxdursa qüvvədə olan nüsxənin saatı)."""
    from apps.registrar.public import plan_hours_for_offering

    hours = plan_hours_for_offering(syllabus.offering) if syllabus.offering_id else {}
    if not hours and syllabus.approved_version_id:
        hours = syllabus.approved_version.plan_hours or {}
    return hours


def _link_maintenance(request, organization, actor, payload, action):
    syllabus = _own_syllabus(organization, actor, payload.get("syllabus"))
    if syllabus is None:
        return _fail(_NOT_FOUND, status=404)
    if action == "unlink":
        version = services.reuse.unlink(target_syllabus=syllabus, actor=actor, request=request)
        return _version_payload(version, _UNLINKED, syllabus=str(syllabus.pk))
    if action == "sync":
        version = services.reuse.sync_from_source(
            target_syllabus=syllabus, actor=actor, plan_hours=_hours_for(syllabus), request=request
        )
        return _version_payload(version, _SYNCED, syllabus=str(syllabus.pk))
    results = services.reuse.propagate(source=syllabus, actor=actor, hours_for=_hours_for, request=request)
    for row in results:
        if row["code"] and row["status"] == "skipped":
            row["message"] = transition_text(row["code"])
    counts = {key: sum(1 for row in results if row["status"] == key) for key in ("synced", "already", "skipped")}
    return JsonResponse({"ok": True, "message": str(_PROPAGATED) % counts, "results": results, "counts": counts})


@login_required
@require_POST
def syllabus_reuse_action(request):
    """Təkrar istifadə əməlləri — bax modul docstring-i."""
    organization, actor, denied = _guard(request)
    if denied is not None:
        return denied
    payload = _body(request)
    action = (payload.get("action") or "").strip()
    try:
        if action in {"link", "copy"}:
            return _single(request, organization, actor, payload, action)
        if action == "bulk":
            return _bulk(request, organization, actor, payload)
        if action in {"unlink", "sync", "propagate"}:
            return _link_maintenance(request, organization, actor, payload, action)
    except IntegrityError:
        # İkiqat klik / köhnə tab: açılışa paralel dosye yarandı — 500 əvəzinə 409.
        logger.info("syllabus reuse race on %s", action)
        return _fail(transition_text("syllabus.exists"), status=409, code="syllabus.exists")
    except TransitionDenied as exc:
        status = 404 if exc.code == "transition.out_of_scope" else 409
        return _fail(transition_text(exc.code, exc.params), status=status, code=exc.code)
    return _fail(_BAD_REQUEST)


__all__ = ["syllabus_reuse_action", "syllabus_reuse_options"]
