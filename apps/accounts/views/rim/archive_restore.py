"""RİM — «Arxivdən çıxar» endpoint-i (sahib 2026-10-27: «Mən özüm də arxivdən çıxara bilim»).

YALNIZ POST + CSRF (Django middleware; ``csrf_exempt`` yoxdur), ``never_cache``, cavab JSON. Zəncir RİM-in
digər yazı əməliyyatları ilə eynidir: aktor → ``member.edit`` (403) → hədəf aktorun idarə sahəsindən
(``manageable_users_queryset``; kənardırsa 404 — başqa tenantın hesabının mövcudluğu sızmır) → iyerarxiya
(403) → ortaq servis ``restore_wrongly_archived_student`` (uyğunluq 409, səbəb / qəbul ili 400).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.accounts.services.archive_restore import (
    ArchiveRestoreError,
    actor_can_restore,
    restore_wrongly_archived_student,
)
from apps.accounts.services.rim import RimAccessError, assert_can_manage, manageable_users_queryset, resolve_actor
from apps.accounts.services.rim.archive import restore_organization
from apps.accounts.services.rim.detail import serialize_detail
from core.write_rate_limit import score_write_rate_limited

from .actions import _read_payload

_CTX = "accounts.archive_restore"


def _error(exc: ArchiveRestoreError) -> JsonResponse:
    return JsonResponse({"ok": False, "error": exc.code, "message": exc.message}, status=exc.status)


def _target(actor, user_id):
    try:
        return manageable_users_queryset(actor).filter(pk=int(user_id)).first()
    except (TypeError, ValueError):
        return None


@never_cache
@login_required
@require_POST
@score_write_rate_limited("rim_archive_restore")
def rim_archive_restore(request):
    """Səhvən arxivlənmiş cari tələbənin hesabını aktiv edir (+ yer-tutucu qəbul ili, istənilibsə)."""
    if getattr(request, "is_view_as", False):
        return _error(ArchiveRestoreError("view_as_forbidden", status=403))
    actor = resolve_actor(request)
    payload = _read_payload(request)
    user_id = payload.get("user_id")
    if not user_id:
        return _error(ArchiveRestoreError("target_required", status=400))

    target = _target(actor, user_id)
    organization = restore_organization(actor, target)
    if not actor_can_restore(actor.user, organization):
        return _error(ArchiveRestoreError("permission_denied", status=403))
    if target is None:
        return _error(ArchiveRestoreError("target_not_found", status=404))
    try:
        assert_can_manage(actor, target)
    except RimAccessError:
        return _error(ArchiveRestoreError("permission_denied", status=403))

    try:
        outcome = restore_wrongly_archived_student(
            user=target,
            organization=organization,
            actor=actor.user,
            reason=payload.get("reason"),
            admission_year=payload.get("admission_year"),
            request=request,
        )
    except ArchiveRestoreError as exc:
        return _error(exc)

    message = pgettext(_CTX, "Hesab arxivdən çıxarıldı — tələbə yenidən daxil ola bilər. Lazım olsa parolu sıfırlayın.")
    if outcome.admission_year_fixed:
        message = f"{message} " + pgettext(_CTX, "Qəbul ili düzəldildi: %(year)s.") % {"year": outcome.admission_year}
    fresh = get_user_model().objects.select_related("profile").filter(pk=target.pk).first() or target
    return JsonResponse(
        {
            "ok": True,
            "message": message,
            "restored": outcome.restored,
            "admission_year_fixed": outcome.admission_year_fixed,
            "user": serialize_detail(fresh, actor),
        }
    )


__all__ = ["rim_archive_restore"]
