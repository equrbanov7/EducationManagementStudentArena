"""Dəqiqləşdirmənin YAZMA endpoint-i — TƏK POST marşrutu + ``action`` allow-list-i.

``handover`` naxışının eynisi və eyni səbəbdən: hər əməl eyni ön-şərt
zəncirindən keçir (aktor → icazə → tenant → fakt → audit). Marşrutları
parçalasaq zəncir üç yerdə təkrarlanardı.

⚠️ MULTIPART QƏBUL EDİLİR. «Düzəlt» əməli SƏNƏD (PDF/şəkil) daşıyır — mövcud
``exam_score_entry`` müqaviləsi artıq yazılmış balın dəyişdirilməsini sənədsiz
QƏBUL ETMİR. Ona görə bu endpoint JSON deyil, forma POST-u ilə işləyir və
cavabı JSON qaytarır (səth SPA-dır, səhifə yenilənmir).
"""

from __future__ import annotations

import logging

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.registrar import legacy_grade_review_actions as review_write
from core.logging_utils import safe_log_value

from .policy import resolve_actor

logger = logging.getLogger(__name__)

# Tərcümə konteksti hər çağırışda HƏRFİ sətirdir, dəyişən DEYİL: ``xgettext``
# ``pgettext``-in kontekst arqumentini yalnız hərfi sətir olanda oxuya bilir —
# dəyişən verilsə sətri SƏSSİZCƏ atır və mətn heç bir dilə çıxmır.

#: Allow-list — naməlum `action` 400 verir (səssiz keçid yoxdur).
ALLOWED_ACTIONS = frozenset({"verify", "dispute", "correct"})


def _error(code, message, status=400):
    return JsonResponse({"ok": False, "error": code, "message": message}, status=status)


@never_cache
@login_required
@require_POST
def legacy_review_action(request):
    """«Təsdiqlə» / «Mübahisələndir» / «Düzəlt» — vahid giriş nöqtəsi."""
    actor = resolve_actor(request)
    # ⚠️ `has_access` KİFAYƏT DEYİL: `journal.correct` daşıyan aktor növbəni
    # OXUYA bilir, amma köhnə rəsmi balın qərarını VERƏ bilmir. Yazı qapısı
    # ayrıca `can_review`-dur.
    if not actor.can_review:
        return _error(
            "permission_denied",
            pgettext("accounts.legacy_review", "Köhnə imtahan nəticəsini dəqiqləşdirmək üçün səlahiyyətiniz yoxdur."),
            status=403,
        )

    action = (request.POST.get("action") or "").strip()
    if action not in ALLOWED_ACTIONS:
        return _error("unknown_action", pgettext("accounts.legacy_review", "Naməlum əməliyyat."))

    fact_id = (request.POST.get("fact_id") or "").strip()
    if not fact_id:
        return _error(
            "missing_fact", pgettext("accounts.legacy_review", "Hansı sətrin dəqiqləşdirildiyi göstərilməyib.")
        )

    try:
        if action == "correct":
            result = review_write.apply_correction(
                organization=actor.organization,
                fact_id=fact_id,
                score=request.POST.get("score"),
                reason=(request.POST.get("reason") or "").strip(),
                note=request.POST.get("note") or "",
                evidence=request.FILES.get("evidence"),
                actor=actor.user,
                request=request,
            )
            payload = {"status": "corrected", "new_score": str(result["entry"].new_score)}
        else:
            review_write.record_decision(
                organization=actor.organization,
                fact_id=fact_id,
                action=action,
                note=request.POST.get("note") or "",
                actor=actor.user,
                request=request,
            )
            payload = {"status": "verified" if action == "verify" else "disputed"}
    except PermissionDenied:
        # ⚠️ `str(exc)` KLİENTƏ QAYTARILMIR: `PermissionDenied` Django-nun daxili
        # qatlarından da gələ bilər və mətni daxili təfərrüat sızdırır (CodeQL
        # `py/stack-trace-exposure`). Səbəb server tərəfdə loglanır.
        logger.warning("legacy review action denied: action=%s", safe_log_value(action), exc_info=True)
        return _error("permission_denied", pgettext("accounts.legacy_review", "İcazəniz yoxdur."), status=403)
    except ValidationError as exc:
        # Servis mesajları istifadəçi-üzlüdür (səbəb/sənəd tələbi, eyni bal,
        # passiv qeydiyyat) — olduğu kimi göstərilir.
        return _error("invalid", " ".join(exc.messages))
    except ValueError as exc:  # pragma: no cover — gözlənilməz giriş formatı
        logger.warning("legacy review action failed: %s", safe_log_value(exc))
        return _error("invalid", pgettext("accounts.legacy_review", "Əməliyyat yerinə yetirilmədi."))

    return JsonResponse({"ok": True, **payload})


__all__ = ["ALLOWED_ACTIONS", "legacy_review_action"]
