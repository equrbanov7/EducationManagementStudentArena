"""HTTP endpoint-ləri: tək əməl POST-u, yoxlama çekməcəsinin HTML fraqmenti, jurnal önizləməsi.

* ``action`` — bütün mutasiyalar (``action`` sahəsi handler seçir; müəllim, baxış və
  tələbə handler-ləri eyni cədvəldədir, icazə servisdə yoxlanılır). Rate-limit: yazı
  endpoint-lərinin ortaq vedrəsi (``core.write_rate_limit``).
* ``review_detail`` — göndərişin tam görünüşü (cəhdlər, fayllar, tarixçə, oxşarlıqlar,
  əməl formaları) SERVERDƏ render olunur; çekməcə onu olduğu kimi yerləşdirir
  (inline skript yoxdur — davranış ``review.js``-in sənəd səviyyəli delegasiyasıdır).
* ``review_preview`` — «Bu bal jurnala düşəcək: …» zolağı (yazı yoxdur).

Anonim sorğu login səhifəsinə, aktiv təşkilat konteksti olmayan sorğu 403 JSON alır.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.template.loader import render_to_string
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from core.write_rate_limit import score_write_rate_limited

from .. import public
from ..errors import FolderError
from . import review_actions, student_actions, teacher_actions
from .base import ActionError, folder_error_response, get_submission, json_error, json_ok, request_organization

_CTX = "subject_folder.ui"

HANDLERS = {**teacher_actions.HANDLERS, **review_actions.HANDLERS, **student_actions.HANDLERS}


def _no_org():
    return json_error("no_org", pgettext(_CTX, "Aktiv təşkilat konteksti yoxdur."), status=403)


@login_required
@require_POST
@never_cache
@score_write_rate_limited("subject_folder_action")
def action(request):
    """Fənn qovluğunun bütün yazı əməlləri (tək endpoint, fail-closed)."""
    organization = request_organization(request)
    if organization is None:
        return _no_org()
    handler = HANDLERS.get(str(request.POST.get("action") or "").strip())
    if handler is None:
        return json_error("unknown_action", pgettext(_CTX, "Naməlum əməl."))
    try:
        return handler(request, organization, request.user)
    except FolderError as exc:
        return folder_error_response(exc)
    except ActionError as exc:
        return json_error(exc.code, exc.message, status=exc.status)


@login_required
@require_GET
@never_cache
def review_detail(request, submission_id):
    """Yoxlama çekməcəsinin gövdəsi (HTML) — görmə hüququ olmayan aktora 404."""
    from ..cabinet.review import detail_context

    organization = request_organization(request)
    if organization is None:
        return _no_org()
    try:
        submission = get_submission(organization, submission_id)
        context = detail_context(submission, request.user)
    except ActionError as exc:
        return json_error(exc.code, exc.message, status=exc.status)
    except FolderError:
        return json_error("not_found", pgettext(_CTX, "Obyekt tapılmadı və ya artıq mövcud deyil."), status=404)
    html = render_to_string("subject_folder/cabinet/review/_detail.html", context, request=request)
    return json_ok(html=html, title=context["title"], subtitle=context["subtitle"])


@login_required
@require_GET
@never_cache
def review_preview(request, submission_id):
    """Qəbuldan əvvəl jurnal zolağı: ``?points=4.5`` → mətn / xəta (yazı yoxdur)."""
    organization = request_organization(request)
    if organization is None:
        return _no_org()
    try:
        submission = get_submission(organization, submission_id)
    except ActionError as exc:
        return json_error(exc.code, exc.message, status=exc.status)
    if not public.can_review_assignment(request.user, submission.assignment):
        return json_error("not_found", pgettext(_CTX, "Obyekt tapılmadı və ya artıq mövcud deyil."), status=404)
    raw = str(request.GET.get("points") or "").strip()[:12]
    preview = public.journal_preview(submission, points=raw or None)
    journal = preview.get("journal") or {}
    return json_ok(
        text=preview.get("text", ""),
        error=(preview.get("error") or {}).get("message", ""),
        remaining=str(preview.get("remaining", "")),
        max_points=str(preview.get("max_points", "")),
        journal_blocked=bool(journal.get("blocked")),
        journal_reason=str(journal.get("reason") or ""),
    )


__all__ = ["HANDLERS", "action", "review_detail", "review_preview"]
