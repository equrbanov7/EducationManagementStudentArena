"""İmtahan Mərkəzi — kollokvium bal-yazma pəncərələri (profil SPA bölməsi).

İmtahan Mərkəzi hər semestr (AcademicPeriod) üçün K1/K2/K3 üzrə bal-yazma
aralığı təyin edib aktivləşdirir; RƏHBƏR əlavə gün verə bilər (org/fakültə/
kafedra əhatəsində). Müəllim tərəfi bunu ``registrar.kollokvium_windows``
servisi ilə oxuyur — bu view yalnız pəncərə/grant sətirlərini mutasiya edir.

POST action-lar bölməyə redirect edir; GET ``_render_profile_section`` ilə
profil "Kollokvium pəncərələri" bölməsini render edir. (``superadmin_exam_rooms``
pattern-i.)
"""

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import pgettext

from apps.accounts.forms.kollokvium_windows import KollokviumExtraGrantForm, KollokviumWindowForm
from apps.exams.public import is_exam_center_user
from apps.registrar import kollokvium_notifications
from apps.registrar.models import KollokviumExtraGrant, KollokviumWindow
from core.audit import log_action
from core.constants import AuditAction

from ._helpers import (
    _append_query_params,
    _is_superadmin_user,
    _render_profile_section,
    _resolve_next_url,
    _resolve_superadmin_target_org,
)

logger = logging.getLogger(__name__)


class KollokviumAdminError(Exception):
    """Pəncərə/grant əməliyyatının istifadəçi-üzlü xətası (yuxarıda tutulur)."""


def _uuid_or_404(raw):
    """Qeyri-UUID id `get_object_or_404(pk=...)`-də ValidationError → 500 verirdi (QA 2026-09-05 EXAMS-02)."""
    import uuid

    from django.http import Http404

    try:
        return uuid.UUID(str(raw or "").strip())
    except ValueError:
        raise Http404 from None


def _reject_if_period_past(period, user=None):
    """Keçmiş akademik dövr (semestr) üçün kollokvium mutasiyalarını rədd et.

    Adi istifadəçilər köhnə il/semestr üçün pəncərə tarixi, aktivləşdirmə və ya
    əlavə gün dəyişə bilməz — server-side məcburidir (yalnız UI gizlətməsi kifayət
    deyil). Qayda ``AcademicPeriod.is_past`` (end_date < bugün) ilə eynidir.

    İSTİSNA: İKT Rəhbəri və superadmin bitmiş semestr üçün də düzəliş edə bilər
    (səhv yazıları düzəltmək üçün) — bu əməllər onsuz da audit olunur.
    """
    if user is not None and (
        getattr(user, "is_superuser", False)
        or getattr(user, "is_superadmin", False)
        or getattr(user, "is_ikt_rehber", False)
    ):
        return
    if period is not None and period.is_past:
        raise KollokviumAdminError(
            pgettext(
                "accounts.kollokvium_windows",
                "Bitmiş akademik dövr (köhnə il/semestr) üçün dəyişiklik edilə bilməz.",
            )
        )


def _can_manage(user):
    """İmtahan Mərkəzi (head OR staff) və ya superadmin pəncərələri idarə edə bilər."""
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser or getattr(user, "is_superadmin", False):
        return True
    return bool(is_exam_center_user(user))


def _is_head(user):
    """Əlavə gün YALNIZ İmtahan Mərkəzi RƏHBƏRİ (və ya superadmin)."""
    if user.is_superuser or getattr(user, "is_superadmin", False):
        return True
    return bool(getattr(user, "is_exam_center_head", False))


def _resolve_target_org(request):
    """Bu sorğunun idarə etdiyi təşkilat (superadmin: ?win_org / POST organization_id).

    Həll paylaşılan ``_resolve_superadmin_target_org``-a həvalə olunur: id yalnız
    superadmin üçün oxunur, AKTİV təşkilatlar arasında validasiya edilir və
    parse olunmayan dəyər 500 vermir (2026-09-02 audit, P2-3).
    """
    return _resolve_superadmin_target_org(request, query_param="win_org")


@login_required
def kollokvium_windows(request):
    """Kollokvium bal-yazma pəncərələrinin idarəetməsi (profil SPA bölməsi)."""
    if not _can_manage(request.user):
        return HttpResponseForbidden(
            pgettext("accounts.kollokvium_windows", "Bu bölmə yalnız İmtahan Mərkəzi üçündür.")
        )

    fallback_next = _append_query_params(reverse("accounts:profile"), section="kollokvium-windows")

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        organization = _resolve_target_org(request)
        next_url = _resolve_next_url(request, fallback_next)
        if organization is None:
            messages.error(request, pgettext("accounts.kollokvium_windows", "Təşkilat konteksti tapılmadı."))
            return redirect(next_url)
        if _is_superadmin_user(request.user):
            next_url = _append_query_params(next_url, win_org=str(organization.pk))

        try:
            _dispatch_action(request, action, organization)
        except KollokviumAdminError as exc:
            messages.error(request, str(exc))
        return redirect(next_url)

    return _render_profile_section(request, "kollokvium-windows")


def _dispatch_action(request, action, organization):
    user = request.user

    if action == "save_window":
        form = KollokviumWindowForm(request.POST, organization=organization)
        if not form.is_valid():
            raise KollokviumAdminError(_first_form_error(form))
        k_index = form.cleaned_data["k_index"]
        period = form.cleaned_data["period"]
        _reject_if_period_past(period, user)  # köhnə il/semestr üçün yazma qadağan (İKT Rəhbəri istisna)
        # Sıra qaydası: K{n} yalnız K{n-1} təyin olunduqdan sonra (İmtahan Mərkəzi
        # tələbi — K1 qoyulmamış K2/K3 təyin edilə bilməz).
        if (
            k_index > 0
            and not KollokviumWindow.objects.filter(
                organization=organization, period=period, k_index=k_index - 1
            ).exists()
        ):
            raise KollokviumAdminError(
                pgettext("accounts.kollokvium_windows", "Əvvəlcə K%(n)s təyin edilməlidir.") % {"n": k_index}
            )
        existing = KollokviumWindow.objects.filter(organization=organization, period=period, k_index=k_index).first()
        window, created = KollokviumWindow.objects.update_or_create(
            organization=organization,
            period=period,
            k_index=k_index,
            defaults={
                "opens_on": form.cleaned_data["opens_on"],
                "closes_on": form.cleaned_data["closes_on"],
                "created_by": user,
            },
        )
        # Yalnız AKTİV pəncərənin tarixi HƏQİQƏTƏN dəyişəndə xəbərdarlıq —
        # yaradılış (defolt qeyri-aktiv) və ya eyni tarixlərlə yenidən saxlama
        # bildiriş yaratmır (toggle_window_active açılışı elan edir).
        if (
            not created
            and window.is_active
            and existing is not None
            and (existing.opens_on != window.opens_on or existing.closes_on != window.closes_on)
        ):
            kollokvium_notifications.notify_window_extended(window)
        log_action(
            AuditAction.CREATE if created else AuditAction.UPDATE,
            user=user,
            organization=organization,
            obj=window,
            reason="kollokvium_window_saved",
            request=request,
            resource_type="kollokvium_window",
            resource_id=str(window.pk),
        )
        messages.success(request, pgettext("accounts.kollokvium_windows", "Pəncərə yadda saxlanıldı."))
        return

    if action == "toggle_window_active":
        window = get_object_or_404(
            KollokviumWindow, pk=_uuid_or_404(request.POST.get("window_id")), organization=organization
        )
        _reject_if_period_past(window.period, user)
        window.is_active = not window.is_active
        window.save(update_fields=["is_active", "updated_at"])
        if window.is_active:
            kollokvium_notifications.notify_window_opened(window)
        else:
            kollokvium_notifications.notify_window_closed(window)
        log_action(
            AuditAction.UPDATE,
            user=user,
            organization=organization,
            obj=window,
            reason="kollokvium_window_toggled",
            request=request,
            resource_type="kollokvium_window",
            resource_id=str(window.pk),
        )
        messages.success(request, pgettext("accounts.kollokvium_windows", "Pəncərə statusu dəyişdirildi."))
        return

    if action == "delete_window":
        window = get_object_or_404(
            KollokviumWindow, pk=_uuid_or_404(request.POST.get("window_id")), organization=organization
        )
        _reject_if_period_past(window.period, user)
        window.delete()
        messages.success(request, pgettext("accounts.kollokvium_windows", "Pəncərə silindi."))
        return

    if action == "grant_extra_days":
        if not _is_head(user):
            raise KollokviumAdminError(
                pgettext("accounts.kollokvium_windows", "Əlavə gün yalnız İmtahan Mərkəzi rəhbərinə məxsusdur.")
            )
        window = get_object_or_404(
            KollokviumWindow, pk=_uuid_or_404(request.POST.get("window_id")), organization=organization
        )
        _reject_if_period_past(window.period, user)
        form = KollokviumExtraGrantForm(request.POST, organization=organization, window=window)
        if not form.is_valid():
            raise KollokviumAdminError(_first_form_error(form))
        grant, created = KollokviumExtraGrant.objects.update_or_create(
            window=window,
            scope=form.cleaned_data["scope"],
            org_unit=form.cleaned_data.get("org_unit"),
            defaults={
                "organization": organization,
                "extra_days": form.cleaned_data["extra_days"],
                "granted_by": user,
            },
        )
        # Eyni əhatə yenidən verilirsə bu UPDATE-dir (audit dəqiqliyi).
        log_action(
            AuditAction.CREATE if created else AuditAction.UPDATE,
            user=user,
            organization=organization,
            obj=grant,
            reason="kollokvium_extra_days_granted" if created else "kollokvium_extra_days_regranted",
            request=request,
            resource_type="kollokvium_extra_grant",
            resource_id=str(grant.pk),
        )
        messages.success(request, pgettext("accounts.kollokvium_windows", "Əlavə gün verildi."))
        return

    if action == "edit_extra_days":
        if not _is_head(user):
            raise KollokviumAdminError(
                pgettext("accounts.kollokvium_windows", "Əlavə gün yalnız İmtahan Mərkəzi rəhbərinə məxsusdur.")
            )
        grant = get_object_or_404(
            KollokviumExtraGrant.objects.select_related("window__period"),
            pk=_uuid_or_404(request.POST.get("grant_id")),
            organization=organization,
        )
        _reject_if_period_past(grant.window.period, user)
        # Redaktədə mövcud bölmə artıq deaktivdirsə də (soft-delete) qəbul et.
        form = KollokviumExtraGrantForm(
            request.POST, organization=organization, window=grant.window, include_unit_id=grant.org_unit_id
        )
        if not form.is_valid():
            raise KollokviumAdminError(_first_form_error(form))
        new_scope = form.cleaned_data["scope"]
        new_unit = form.cleaned_data.get("org_unit")
        dup_msg = pgettext("accounts.kollokvium_windows", "Bu əhatə üçün artıq əlavə gün mövcuddur.")
        # Unikallıq (window, scope, org_unit): başqa qrantla toqquşmasın. Check + save
        # atomik + IntegrityError-i dostyana xətaya çevir (nadir yarış halı → 500 yox).
        try:
            with transaction.atomic():
                clash = (
                    KollokviumExtraGrant.objects.select_for_update()
                    .filter(window=grant.window, scope=new_scope, org_unit=new_unit)
                    .exclude(pk=grant.pk)
                    .exists()
                )
                if clash:
                    raise KollokviumAdminError(dup_msg)
                grant.scope = new_scope
                grant.org_unit = new_unit
                grant.extra_days = form.cleaned_data["extra_days"]
                grant.save(update_fields=["scope", "org_unit", "extra_days", "updated_at"])
        except IntegrityError:
            raise KollokviumAdminError(dup_msg)
        log_action(
            AuditAction.UPDATE,
            user=user,
            organization=organization,
            obj=grant,
            reason="kollokvium_extra_days_edited",
            request=request,
            resource_type="kollokvium_extra_grant",
            resource_id=str(grant.pk),
        )
        messages.success(request, pgettext("accounts.kollokvium_windows", "Əlavə gün yeniləndi."))
        return

    if action == "delete_extra_days":
        if not _is_head(user):
            raise KollokviumAdminError(
                pgettext("accounts.kollokvium_windows", "Əlavə gün yalnız İmtahan Mərkəzi rəhbərinə məxsusdur.")
            )
        grant = get_object_or_404(
            KollokviumExtraGrant.objects.select_related("window__period"),
            pk=_uuid_or_404(request.POST.get("grant_id")),
            organization=organization,
        )
        _reject_if_period_past(grant.window.period, user)
        grant_pk = str(grant.pk)
        grant.delete()
        log_action(
            AuditAction.DELETE,
            user=user,
            organization=organization,
            obj=None,
            reason="kollokvium_extra_days_deleted",
            request=request,
            resource_type="kollokvium_extra_grant",
            resource_id=grant_pk,
        )
        messages.success(request, pgettext("accounts.kollokvium_windows", "Əlavə gün silindi."))
        return

    raise KollokviumAdminError(pgettext("accounts.kollokvium_windows", "Naməlum əməliyyat."))


def _first_form_error(form):
    for _field, errors in form.errors.items():
        if errors:
            return errors[0]
    return pgettext("accounts.kollokvium_windows", "Form məlumatları düzgün deyil.")


__all__ = ["kollokvium_windows"]
