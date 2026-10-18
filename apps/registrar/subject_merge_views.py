"""«Fənləri birləşdir» — HTTP qatı (JSON), fənn kataloqu dialoqu üçün (2026-10-19).

İCAZƏ: ``catalog.manage`` + TƏŞKİLAT-GENİŞ əhatə (Tədris şöbəsinin rəhbəri/əməkdaşı, RİM).
* açar yoxdur → **403**;
* açar var, amma əhatə unit-lə məhduddur (dekan/kafedra) → **404** (mövcudluğu açıqlanmır).

Məntiq: :mod:`.subject_merge` (önizləmə), :mod:`.subject_merge_apply` (yazı).
"""

from __future__ import annotations

import uuid

from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import JsonResponse
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from core.search_text import tolerant_q

from .catalog_registry import can_manage_catalog, can_merge_subjects
from .models import Subject
from .subject_duplicates import find_duplicate_subject_groups
from .subject_merge import MergeError, preview
from .subject_merge_apply import apply

_CTX = "registrar.subject_merge"
LOOKUP_LIMIT = 30


def _error(message, *, status=400, code="invalid", **extra):
    return JsonResponse({"ok": False, "error": code, "message": message, **extra}, status=status)


def _gate(request):
    organization = getattr(request, "organization", None)
    if organization is None:
        return None, _error(pgettext(_CTX, "Aktiv təşkilat konteksti yoxdur."), status=403, code="no_org")
    if not can_manage_catalog(request):
        return None, _error(pgettext(_CTX, "Fənləri birləşdirmək səlahiyyətiniz yoxdur."), status=403, code="forbidden")
    if not can_merge_subjects(request):
        return None, _error(pgettext(_CTX, "Səhifə tapılmadı."), status=404, code="not_found")
    return organization, None


def _sources(request) -> list:
    values = request.POST.getlist("sources") or request.POST.getlist("source")
    return [value for value in values if str(value or "").strip()]


def _merge_error(exc: MergeError):
    return _error(exc.message, status=exc.status, code=exc.code, **({"details": exc.details} if exc.details else {}))


@login_required
@never_cache
@require_GET
def subject_lookup(request):
    """Axtarışlı seçici (``EMSSearchableSelect``): ``q``, ``limit``, ``offset`` → ``results``/``has_more``."""
    organization, failure = _gate(request)
    if failure is not None:
        return failure
    try:
        limit = max(1, min(LOOKUP_LIMIT, int(request.GET.get("limit") or LOOKUP_LIMIT)))
        offset = max(0, int(request.GET.get("offset") or 0))
    except (TypeError, ValueError):
        limit, offset = LOOKUP_LIMIT, 0
    queryset = Subject.objects.filter(organization=organization)
    if request.GET.get("archived") != "1":
        queryset = queryset.filter(is_archived=False)
    search_q = tolerant_q((request.GET.get("q") or "").strip()[:120], ("name",), compact_fields=("code",))
    if search_q is not None:
        queryset = queryset.filter(search_q)
    window = list(queryset.order_by("name", "code")[offset : offset + limit + 1])
    results = [
        {
            "id": str(subject.pk),
            "text": f"{subject.code} — {subject.name} ({subject.ects} ECTS)"
            + (f" · {pgettext(_CTX, 'arxivdə')}" if subject.is_archived else ""),
        }
        for subject in window[:limit]
    ]
    return JsonResponse({"results": results, "has_more": len(window) > limit})


@login_required
@never_cache
@require_GET
def duplicate_groups(request):
    """Ehtimal dublikat qrupları — dialoqda «hazır təklif» (saxlanılacaq = ən çox açılışı olan)."""
    organization, failure = _gate(request)
    if failure is not None:
        return failure
    groups = find_duplicate_subject_groups(organizations=[organization])
    ids = [subject["id"] for group in groups for subject in group.subjects]
    stats = {
        pk: (usage, ects)
        for pk, usage, ects in Subject.objects.filter(pk__in=ids)
        .annotate(n=Count("curriculum_rows", distinct=True))
        .values_list("pk", "n", "ects")
    }
    plan_usage = {pk: usage for pk, (usage, _ects) in stats.items()}
    payload = []
    for group in groups:
        subjects = sorted(
            group.subjects,
            key=lambda item: (-item["offerings"], -plan_usage.get(_uuid(item["id"]), 0), item["code"]),
        )
        payload.append(
            {
                "key": group.key,
                "target": subjects[0]["id"],
                "subjects": [
                    {
                        **subject,
                        "plan_usage": plan_usage.get(_uuid(subject["id"]), 0),
                        "ects": stats.get(_uuid(subject["id"]), (0, ""))[1],
                    }
                    for subject in subjects
                ],
            }
        )
    return JsonResponse({"ok": True, "groups": payload})


def _uuid(value):
    return uuid.UUID(str(value))


@login_required
@never_cache
@require_POST
def merge_preview(request):
    organization, failure = _gate(request)
    if failure is not None:
        return failure
    try:
        payload = preview(organization, request.POST.get("target"), _sources(request))
    except MergeError as exc:
        return _merge_error(exc)
    return JsonResponse({"ok": True, "preview": payload})


@login_required
@never_cache
@require_POST
def merge_apply(request):
    organization, failure = _gate(request)
    if failure is not None:
        return failure
    try:
        result = apply(
            organization=organization,
            actor=request.user,
            target_ref=request.POST.get("target"),
            source_refs=_sources(request),
            reason=request.POST.get("reason"),
            expected_digest=request.POST.get("digest"),
            request=request,
        )
    except MergeError as exc:
        return _merge_error(exc)
    message = pgettext(_CTX, "Birləşdirildi: %(sources)s → %(target)s.") % {
        "sources": ", ".join(result["sources"]),
        "target": result["target"]["code"],
    }
    return JsonResponse({"ok": True, "message": message, **result})


__all__ = ["duplicate_groups", "merge_apply", "merge_preview", "subject_lookup"]
