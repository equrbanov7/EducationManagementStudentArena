"""RİM — semestr sonu jurnal bağlama/açma + bağlanma xəbərdarlığı (profil bölməsi).

SAHİBİN QƏRARI (2026-08): jurnal təsdiqə getmir. Müəllim balı yazır və bitir;
semestr sonunda RİM dövr üzrə jurnalları — bütün təşkilat / bir fakültə / bir
kafedra əhatəsində — TOPLU bağlayır (məqsəd: giriş balının yekunlaşdırılması).
Bundan başqa RİM «bu tarixdən sonra jurnallar bağlanacaq» xəbərdarlığı göndərir;
o, jurnalda İmtahan Mərkəzinin kollokvium lenti ilə eyni sürüşən zolaqda görünür.

POST action-lar bölməyə redirect edir; GET ``_render_profile_section`` ilə profil
«Jurnal bağlama» bölməsini render edir (``kollokvium_windows`` pattern-i).

İcazə qapısı: ``journal.close`` (bax ``apps/registrar/journal_scope.py``). Faktiki
əhatə yoxlaması servis qatında (``journal_close.assert_unit_in_actor_scope``)
yenidən aparılır — unit-scoped aktor yalnız öz alt-ağacını bağlaya bilər.
"""

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import pgettext

from apps.accounts.forms.journal_close import JournalCloseActionForm, JournalCloseNoticeForm
from apps.registrar import journal_close as journal_close_service
from apps.registrar import journal_scope
from apps.registrar.models import JournalCloseNotice
from core.audit import log_action
from core.constants import AuditAction

from ._helpers import (
    _append_query_params,
    _get_active_organization,
    _is_superadmin_user,
    _render_profile_section,
    _resolve_next_url,
)

logger = logging.getLogger(__name__)

_CTX = "accounts.journal_close"


class JournalCloseAdminError(Exception):
    """Bölmənin istifadəçi-üzlü xətası (dispatcher-də tutulur)."""


def _can_manage(user, organization):
    """`journal.close` icazəsi + superadmin bypass."""
    if not getattr(user, "is_authenticated", False):
        return False
    if _is_superadmin_user(user):
        return True
    if organization is None:
        return False
    return journal_scope.can_close_journals(user, organization)


def _resolve_target_org(request):
    """Bu sorğunun idarə etdiyi təşkilat (superadmin: ?jc_org / POST organization_id)."""
    from apps.organizations.models import Organization

    if _is_superadmin_user(request.user):
        org_id = (request.POST.get("organization_id") or request.GET.get("jc_org") or "").strip()
        if org_id:
            return Organization.objects.filter(pk=org_id).first()
        return Organization.objects.filter(is_active=True).order_by("name").first()
    return _get_active_organization(request)


@login_required
def journal_close(request):
    """Jurnal bağlama/açma + xəbərdarlıq idarəetməsi (profil SPA bölməsi)."""
    organization = _resolve_target_org(request) if request.method == "POST" else _get_active_organization(request)
    if not _can_manage(request.user, organization or _get_active_organization(request)):
        return HttpResponseForbidden(pgettext(_CTX, "Bu bölmə yalnız jurnal bağlama səlahiyyəti olanlar üçündür."))

    fallback_next = _append_query_params(reverse("accounts:profile"), section="journal-close")

    if request.method == "POST":
        next_url = _resolve_next_url(request, fallback_next)
        if organization is None:
            messages.error(request, pgettext(_CTX, "Təşkilat konteksti tapılmadı."))
            return redirect(next_url)
        if _is_superadmin_user(request.user):
            next_url = _append_query_params(next_url, jc_org=str(organization.pk))
        try:
            _dispatch_action(request, (request.POST.get("action") or "").strip(), organization)
        except (JournalCloseAdminError, PermissionDenied) as exc:
            messages.error(request, str(exc) or pgettext(_CTX, "Bu əməliyyat üçün icazəniz yoxdur."))
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        return redirect(next_url)

    return _render_profile_section(request, "journal-close")


def _dispatch_action(request, action, organization):
    if action == "close":
        return _handle_bulk(request, organization, closing=True)
    if action == "reopen":
        return _handle_bulk(request, organization, closing=False)
    if action == "save_notice":
        return _handle_save_notice(request, organization)
    if action == "toggle_notice":
        return _handle_toggle_notice(request, organization)
    if action == "delete_notice":
        return _handle_delete_notice(request, organization)
    raise JournalCloseAdminError(pgettext(_CTX, "Naməlum əməliyyat."))


def _handle_bulk(request, organization, *, closing):
    form = JournalCloseActionForm(request.POST, organization=organization, require_reason=not closing)
    if not form.is_valid():
        raise JournalCloseAdminError(_first_form_error(form))
    unit = form.cleaned_data.get("org_unit")
    period = form.cleaned_data["period"]
    reason = form.cleaned_data.get("reason") or ""

    if closing:
        result = journal_close_service.close_journals(
            organization=organization,
            period=period,
            unit=unit,
            by_user=request.user,
            reason=reason,
            request=request,
        )
        messages.success(request, _result_message(result["scope_label"], result["closed"], result["already"], True))
        return None

    result = journal_close_service.reopen_journals(
        organization=organization,
        period=period,
        unit=unit,
        by_user=request.user,
        reason=reason,
        request=request,
    )
    messages.success(request, _result_message(result["scope_label"], result["reopened"], result["already"], False))
    return None


def _result_message(scope_label, changed, already, closing):
    """Nəticə mesajı — msgid-lərdə `%` yoxdur (i18n qapısı tələbi)."""
    verb = pgettext(_CTX, "jurnal bağlandı") if closing else pgettext(_CTX, "jurnal açıldı")
    tail = pgettext(_CTX, "artıq bağlı idi") if closing else pgettext(_CTX, "onsuz da açıq idi")
    return f"{scope_label} · {changed} {verb} · {already} {tail}."


def _notice_or_404(organization, notice_id):
    return get_object_or_404(JournalCloseNotice, pk=notice_id, organization=organization)


def _handle_save_notice(request, organization):
    notice_id = (request.POST.get("notice_id") or "").strip()
    instance = _notice_or_404(organization, notice_id) if notice_id else None
    form = JournalCloseNoticeForm(request.POST, instance=instance, organization=organization)
    if not form.is_valid():
        raise JournalCloseAdminError(_first_form_error(form))
    notice = form.save(commit=False)
    notice.organization = organization
    if instance is None:
        notice.created_by = request.user
    _assert_scope(request.user, organization, notice.org_unit)
    from django.db import IntegrityError

    try:
        notice.save()
    except IntegrityError:
        raise JournalCloseAdminError(pgettext(_CTX, "Bu dövr və əhatə üçün artıq xəbərdarlıq var."))
    log_action(
        AuditAction.CREATE if instance is None else AuditAction.UPDATE,
        user=request.user,
        organization=organization,
        obj=notice,
        reason="journal_close_notice_saved",
        request=request,
        resource_type="registrar.journal_close_notice",
        resource_id=str(notice.pk),
    )
    messages.success(request, pgettext(_CTX, "Xəbərdarlıq yadda saxlanıldı."))


def _handle_toggle_notice(request, organization):
    notice = _notice_or_404(organization, request.POST.get("notice_id"))
    _assert_scope(request.user, organization, notice.org_unit)
    notice.is_active = not notice.is_active
    notice.save(update_fields=["is_active", "updated_at"])
    log_action(
        AuditAction.UPDATE,
        user=request.user,
        organization=organization,
        obj=notice,
        reason="journal_close_notice_toggled",
        request=request,
        resource_type="registrar.journal_close_notice",
        resource_id=str(notice.pk),
    )
    messages.success(request, pgettext(_CTX, "Xəbərdarlığın statusu dəyişdirildi."))


def _handle_delete_notice(request, organization):
    notice = _notice_or_404(organization, request.POST.get("notice_id"))
    _assert_scope(request.user, organization, notice.org_unit)
    notice_pk = str(notice.pk)
    notice.delete()
    log_action(
        AuditAction.DELETE,
        user=request.user,
        organization=organization,
        obj=None,
        reason="journal_close_notice_deleted",
        request=request,
        resource_type="registrar.journal_close_notice",
        resource_id=notice_pk,
    )
    messages.success(request, pgettext(_CTX, "Xəbərdarlıq silindi."))


def _assert_scope(user, organization, unit):
    """Xəbərdarlıq da bağlama ilə eyni əhatə qapısından keçir (fail-closed)."""
    if _is_superadmin_user(user):
        return
    journal_close_service.assert_unit_in_actor_scope(user, organization, unit)


def _first_form_error(form):
    for _field, errors in form.errors.items():
        if errors:
            return errors[0]
    return pgettext(_CTX, "Form məlumatları düzgün deyil.")


__all__ = ["journal_close"]
