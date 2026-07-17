"""Superadmin — imtahan zalı + kompüter/MAC idarəsi.

Zal/kompüter qeydiyyatı yalnız superadmin (yaxud ``UserProfile.can_manage_exam_rooms``
bayrağı verilmiş istifadəçi) tərəfindən idarə olunur. Superadmin cross-org
işləyir (RLS bypass — middleware); bayraqlı qeyri-superadmin yalnız öz aktiv
təşkilatının zallarını idarə edir.

POST action-lar zaldan/kompüterdən sonra profil bölməsinə redirect edir;
GET ``_render_profile_section`` ilə profil "İmtahan zalları" bölməsini render edir.
"""

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import pgettext

from apps.exams.forms import ExamRoomForm
from apps.exams.public import (
    ExamRoom,
    ExamRoomComputer,
    RoomAdminError,
    add_computer,
    bulk_add_computers,
    can_manage_exam_rooms,
    delete_room,
    update_computer,
)
from core.audit import log_action
from core.constants import AuditAction

from .._helpers import (
    _append_query_params,
    _get_active_organization,
    _is_superadmin_user,
    _render_profile_section,
    _resolve_next_url,
)

logger = logging.getLogger(__name__)


def _resolve_target_org(request):
    """Bu sorğunun idarə etdiyi təşkilat.

    Superadmin: ``?room_org=<id>`` və ya POST ``organization_id`` ilə istənilən
    təşkilat. Bayraqlı qeyri-superadmin: yalnız öz aktiv təşkilatı.
    """
    from apps.organizations.models import Organization

    is_super = _is_superadmin_user(request.user)
    if is_super:
        org_id = (request.POST.get("organization_id") or request.GET.get("room_org") or "").strip()
        if org_id:
            return Organization.objects.filter(pk=org_id).first()
        return Organization.objects.filter(is_active=True).order_by("name").first()
    # Bayraqlı qeyri-superadmin — aktiv təşkilat konteksti (RLS özü məhdudlaşdırır).
    return _get_active_organization(request)


@login_required
def superadmin_exam_rooms(request):
    """İmtahan zalı + kompüter/MAC idarəsi (profil SPA bölməsi)."""
    if not can_manage_exam_rooms(request.user):
        return HttpResponseForbidden(
            pgettext("accounts.superadmin_exam_rooms", "Bu bölmə yalnız zal idarəçiləri üçündür.")
        )

    fallback_next = _append_query_params(reverse("accounts:profile"), section="superadmin-exam-rooms")

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        organization = _resolve_target_org(request)
        next_url = _resolve_next_url(request, fallback_next)
        if organization is None:
            messages.error(request, pgettext("accounts.superadmin_exam_rooms", "Təşkilat konteksti tapılmadı."))
            return redirect(next_url)
        # room_org GET parametrini redirect-də saxla (superadmin seçdiyi org);
        # `next` onsuz da ehtiva edirsə təkrarlama.
        if _is_superadmin_user(request.user) and "room_org=" not in next_url:
            next_url = _append_query_params(next_url, room_org=str(organization.pk))

        try:
            extras = _dispatch_action(request, action, organization)
        except RoomAdminError as exc:
            messages.error(request, str(exc))
        else:
            # Uğurlu əməliyyatdan sonra təsirlənən sətri/zalı vurğula (JS flash).
            if extras:
                fragment = extras.pop("_fragment", "")
                if extras:
                    next_url = _append_query_params(next_url, **extras)
                if fragment:
                    next_url = f"{next_url}#{fragment}"
        return redirect(next_url)

    return _render_profile_section(request, "superadmin-exam-rooms")


def _get_org_room(organization, room_id):
    return get_object_or_404(ExamRoom, pk=room_id, organization=organization)


def _dispatch_action(request, action, organization):
    """POST action-larını icra edir; RoomAdminError yuxarıda tutulur."""
    user = request.user

    if action == "create_room":
        form = ExamRoomForm(request.POST, organization=organization)
        if not form.is_valid():
            raise RoomAdminError(_first_form_error(form))
        room = form.save(commit=False)
        room.organization = organization
        room.created_by = user
        room.save()
        log_action(
            AuditAction.CREATE,
            user=user,
            organization=organization,
            obj=room,
            reason="final_room_created",
            request=request,
            resource_type="exam_room",
            resource_id=str(room.pk),
        )
        messages.success(request, pgettext("accounts.superadmin_exam_rooms", "Zal yaradıldı."))
        return {"hl_room": str(room.pk), "_fragment": f"sar-room-{room.pk}"}

    if action == "update_room":
        room = _get_org_room(organization, request.POST.get("room_id"))
        form = ExamRoomForm(request.POST, instance=room, organization=organization)
        if not form.is_valid():
            raise RoomAdminError(_first_form_error(form))
        form.save()
        log_action(
            AuditAction.UPDATE,
            user=user,
            organization=organization,
            obj=room,
            reason="final_room_updated",
            request=request,
            resource_type="exam_room",
            resource_id=str(room.pk),
        )
        messages.success(request, pgettext("accounts.superadmin_exam_rooms", "Zal yeniləndi."))
        return {"hl_room": str(room.pk), "_fragment": f"sar-room-{room.pk}"}

    if action == "toggle_room_active":
        room = _get_org_room(organization, request.POST.get("room_id"))
        room.is_active = not room.is_active
        room.save(update_fields=["is_active", "updated_at"])
        messages.success(request, pgettext("accounts.superadmin_exam_rooms", "Zal statusu dəyişdirildi."))
        return

    if action == "add_computer":
        room = _get_org_room(organization, request.POST.get("room_id"))
        computer = add_computer(
            room=room,
            label=request.POST.get("label", ""),
            mac=request.POST.get("mac_address", ""),
            seat_number=request.POST.get("seat_number", ""),
            ip_address=request.POST.get("ip_address", ""),
            notes=request.POST.get("notes", ""),
            user=user,
        )
        messages.success(request, pgettext("accounts.superadmin_exam_rooms", "Kompüter əlavə edildi."))
        return {"hl_comp": str(computer.pk), "_fragment": f"sar-room-{room.pk}"}

    if action == "update_computer":
        room = _get_org_room(organization, request.POST.get("room_id"))
        computer = get_object_or_404(ExamRoomComputer, pk=request.POST.get("computer_id"), room=room)
        update_computer(
            computer=computer,
            label=request.POST.get("label", ""),
            mac=request.POST.get("mac_address", ""),
            seat_number=request.POST.get("seat_number", ""),
            ip_address=request.POST.get("ip_address", ""),
            notes=request.POST.get("notes", ""),
            is_active=request.POST.get("is_active") == "1",
        )
        messages.success(request, pgettext("accounts.superadmin_exam_rooms", "Kompüter yeniləndi."))
        return {"hl_comp": str(computer.pk), "_fragment": f"sar-room-{room.pk}"}

    if action == "delete_computer":
        room = _get_org_room(organization, request.POST.get("room_id"))
        computer = get_object_or_404(ExamRoomComputer, pk=request.POST.get("computer_id"), room=room)
        computer.delete()
        messages.success(request, pgettext("accounts.superadmin_exam_rooms", "Kompüter silindi."))
        return

    if action == "delete_room":
        room = _get_org_room(organization, request.POST.get("room_id"))
        room_pk, room_name = room.pk, room.name
        delete_room(room=room)
        log_action(
            AuditAction.DELETE,
            user=user,
            organization=organization,
            reason="final_room_deleted",
            request=request,
            resource_type="exam_room",
            resource_id=str(room_pk),
        )
        messages.success(
            request,
            pgettext("accounts.superadmin_exam_rooms", "«%(room)s» zalı silindi.") % {"room": room_name},
        )
        return

    if action == "bulk_add_computers":
        room = _get_org_room(organization, request.POST.get("room_id"))
        created, errors = bulk_add_computers(room=room, text=request.POST.get("bulk_text", ""), user=user)
        if created:
            messages.success(
                request,
                pgettext("accounts.superadmin_exam_rooms", "%(n)s kompüter əlavə edildi.") % {"n": created},
            )
        for err in errors[:10]:
            messages.warning(request, err)
        if not created and not errors:
            messages.info(request, pgettext("accounts.superadmin_exam_rooms", "Əlavə ediləcək sətir tapılmadı."))
        return {"_fragment": f"sar-room-{room.pk}"} if created else None

    if action in {"grant_room_manager", "revoke_room_manager"}:
        # Yalnız superadmin başqasına icazə verə/geri ala bilər (bayraqlı user yox).
        if not _is_superadmin_user(user):
            raise RoomAdminError(
                pgettext("accounts.superadmin_exam_rooms", "İcazə vermək yalnız superadminə məxsusdur.")
            )
        _set_room_manager(request, grant=action == "grant_room_manager")
        return

    raise RoomAdminError(pgettext("accounts.superadmin_exam_rooms", "Naməlum əməliyyat."))


def _set_room_manager(request, *, grant):
    from django.contrib.auth import get_user_model

    from core.rls import bypass_rls

    User = get_user_model()
    identifier = (request.POST.get("username") or request.POST.get("user_id") or "").strip()
    if not identifier:
        raise RoomAdminError(pgettext("accounts.superadmin_exam_rooms", "İstifadəçi göstərilməyib."))
    with bypass_rls():
        target = (
            User.objects.filter(pk=identifier).first()
            if identifier.isdigit()
            else User.objects.filter(username=identifier).first()
            or User.objects.filter(email__iexact=identifier).first()
        )
    if target is None:
        raise RoomAdminError(
            pgettext("accounts.superadmin_exam_rooms", "İstifadəçi tapılmadı: %(u)s") % {"u": identifier}
        )
    profile = getattr(target, "profile", None)
    if profile is None:
        raise RoomAdminError(pgettext("accounts.superadmin_exam_rooms", "İstifadəçi profili yoxdur."))
    profile.can_manage_exam_rooms = grant
    profile.save(update_fields=["can_manage_exam_rooms", "updated_at"])
    if grant:
        messages.success(
            request,
            pgettext("accounts.superadmin_exam_rooms", "%(u)s zal idarəçisi təyin edildi.") % {"u": target.username},
        )
    else:
        messages.success(
            request,
            pgettext("accounts.superadmin_exam_rooms", "%(u)s zal idarəçiliyindən çıxarıldı.") % {"u": target.username},
        )


def _first_form_error(form):
    for _field, errors in form.errors.items():
        if errors:
            return errors[0]
    return pgettext("accounts.superadmin_exam_rooms", "Form məlumatları düzgün deyil.")


__all__ = ["superadmin_exam_rooms"]
