"""25% müraciəti — İDARƏ əməlləri: pəncərə (İmtahan mərkəzi) və təhsil haqqı cədvəli (Mühasibatlıq), 2026-10-19.

Qapılar ``retake_views`` ilə eynidir: açar yoxdursa 403, yad / mövcud olmayan sətir 404, view-as rejimində
yazı yoxdur. Cavablar JSON — ``{"ok": bool, "message" | "error": str}``.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from . import retake_fees, retake_window
from .models import RetakeTuition, RetakeWindow
from .retake_views import _block_view_as, _data, _field, _ok, _organization, _run

_CTX = "registrar.retake"


def _period(organization, period_id):
    from django.apps import apps as django_apps

    period_model = django_apps.get_model("organizations", "AcademicPeriod")
    period = period_model.objects.filter(pk=period_id, organization=organization).first() if period_id else None
    if period is None:
        raise Http404
    return period


@login_required
@require_POST
@_block_view_as
def window_open(request):
    organization = _organization(request)
    if not retake_window.can_manage(request.user, organization):
        raise PermissionDenied
    data = _data(request)
    period = _period(organization, _field(data, "period"))
    return _run(
        lambda: retake_window.open_window(
            actor=request.user,
            organization=organization,
            period=period,
            opens_at=_field(data, "opens_at") or None,
            closes_at=_field(data, "closes_at") or None,
            note=_field(data, "note"),
            request=request,
        ),
        success=pgettext(_CTX, "Müraciət pəncərəsi açıldı."),
    )


@login_required
@require_POST
@_block_view_as
def window_close(request, window_id):
    organization = _organization(request)
    if not retake_window.can_manage(request.user, organization):
        raise PermissionDenied
    if not RetakeWindow.objects.filter(pk=window_id, organization=organization).exists():
        raise Http404
    data = _data(request)
    return _run(
        lambda: retake_window.close_window(
            actor=request.user,
            organization=organization,
            window_id=window_id,
            note=_field(data, "note"),
            request=request,
        ),
        success=pgettext(_CTX, "Müraciət pəncərəsi bağlandı."),
    )


@login_required
@require_POST
@_block_view_as
def tuition_save(request):
    organization = _organization(request)
    if not retake_fees.can_manage(request.user, organization):
        raise PermissionDenied
    data = _data(request)
    saved = {}

    def _save():
        saved["row"] = retake_fees.save_tuition(
            actor=request.user,
            organization=organization,
            academic_year=_field(data, "academic_year"),
            admission_year=_field(data, "admission_year"),
            program_id=_field(data, "program") or None,
            annual_amount=_field(data, "annual_amount"),
            note=_field(data, "note"),
            request=request,
        )

    success = pgettext(_CTX, "Təhsil haqqı sətri yadda saxlanıldı.")
    response = _run(_save, success=success)
    warning = getattr(saved.get("row"), "year_warning", "")
    # Dövrdə olmayan (amma formatı düzgün) il — yadda saxlanılır, xəbərdarlıq cavaba qoşulur (LOW-9).
    return _ok(f"{success} {warning}", warning=warning) if warning else response


@login_required
@require_POST
@_block_view_as
def tuition_delete(request, tuition_id):
    organization = _organization(request)
    if not retake_fees.can_manage(request.user, organization):
        raise PermissionDenied
    if not RetakeTuition.objects.filter(pk=tuition_id, organization=organization).exists():
        raise Http404
    return _run(
        lambda: retake_fees.delete_tuition(
            actor=request.user, organization=organization, tuition_id=tuition_id, request=request
        ),
        success=pgettext(_CTX, "Təhsil haqqı sətri silindi."),
    )


__all__ = ["tuition_delete", "tuition_save", "window_close", "window_open"]
