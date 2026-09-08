"""Şəxs səhifəsi (müəllim / tələbə) — «Ətraflı», yeni tabda (2026-09-08).

Qapı çekmecə JSON-u ilə EYNİDİR: aktor kataloqu görməli, hədəf onun əhatəsində
olmalıdır (`build_person_page` → `assert_in_catalog_scope`). Əhatədən kənar
hesab 404, kataloq icazəsi olmayan aktor 403.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import render

from apps.accounts.services import people
from apps.accounts.services.rim.policy import RimAccessError


@login_required
def people_person_page(request, user_id):
    actor = people.resolve_actor(request)
    try:
        page = people.build_person_page(actor=actor, user_id=user_id, request=request)
    except RimAccessError as exc:
        if exc.status == 403:
            raise PermissionDenied(exc.message) from exc
        raise Http404(exc.message) from exc
    return render(request, "accounts/people/person_page.html", {"page": page})


__all__ = ["people_person_page"]
