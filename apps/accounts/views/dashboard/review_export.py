"""«Dəyərləndirilmiş nəticələr» — Excel ixracı (sahib 2026-10-27).

İcazə qapısı ``review_results`` ilə EYNİDİR (``can_review_submissions`` + bölmə icazəli olmalıdır);
sətirlər ekrandakı siyahının özüdür (eyni kollektor → eyni əhatə, süzgəc və sıralama, səhifələməsiz).
Sütunlar imtahanın öz nəticə səhifəsinin ixracı ilə eynidir (``apps.exams.public.build_results_xlsx``).
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils.translation import pgettext, pgettext_lazy
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .._dashboard_helpers import _collect_evaluated_review_items
from .._helpers import _role_capabilities


@never_cache
@login_required
@require_GET
def review_results_export(request):
    from apps.exams.public import build_results_xlsx

    from ..profile._sections.review_results_export import build_review_export_rows

    profile = getattr(request.user, "profile", None)
    capabilities = _role_capabilities(request.user, profile)
    if not capabilities["can_review_submissions"] or "review-results" not in capabilities["allowed_sections"]:
        messages.error(request, pgettext_lazy("accounts.pending_review.message", "teacher_only"))
        return redirect("accounts:profile")

    items = _collect_evaluated_review_items(request)[0]
    filename, content_type, data = build_results_xlsx(
        build_review_export_rows(items),
        sheet_title=pgettext("accounts.review_results", "Dəyərləndirilmiş nəticələr"),
        filename_stem="review-results",
    )
    response = HttpResponse(data, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


__all__ = ["review_results_export"]
