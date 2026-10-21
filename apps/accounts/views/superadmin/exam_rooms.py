"""Superadmin — imtahan zalı + kompüter/MAC idarəsi.

Zal/kompüter qeydiyyatı yalnız superadmin (yaxud ``UserProfile.can_manage_exam_rooms``
bayrağı verilmiş istifadəçi) tərəfindən idarə olunur. Superadmin cross-org
işləyir (RLS bypass — middleware); bayraqlı qeyri-superadmin yalnız öz aktiv
təşkilatının zallarını idarə edir.

POST action-lar zaldan/kompüterdən sonra profil bölməsinə redirect edir;
GET ``_render_profile_section`` ilə profil "İmtahan zalları" bölməsini render edir.

2026-10-21 (sahib: «Kompüter əlavə edərkən səhv edəndə səhvi göstərmir, yazdığım tabdan atır — modalda
göstərsin»): əvvəl xəta da redirect idi — fraqmentsiz/vurğusuz, yəni dialoq bağlanır, yazılanlar itir, zalın
çekmecəsi də yenidən açılmırdı (yalnız tost qalırdı). İndi:

* AJAX (``X-Requested-With: XMLHttpRequest``) → JSON ``{ok, message, errors: {sahə: mesaj}}``; validasiya
  xətası 400, uğur 200. Kabinet JS-i (``superadmin_exam_rooms*.js``) xətanı dialoqda sahənin yanında göstərir,
  uğurda dialoqu bağlayıb çekmecəni YERİNDƏ yeniləyir.
* Adi POST (JS-siz / köhnə yol) → mesaj + redirect qalır, AMMA xətada forma vəziyyəti (dialoq, yazılan
  dəyərlər, sahə xətaları) sessiyaya yazılır və bölmə render olunanda dialoq yenidən açılır.
"""

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import pgettext

from apps.exams.public import (
    ExamRoom,
    ExamRoomComputer,
    ExamRoomForm,
    RoomAdminError,
    add_computer,
    bulk_add_computers,
    can_manage_exam_rooms,
    delete_room,
    update_computer,
)
from core.audit import log_action
from core.constants import AuditAction
from core.http_ids import parse_int

from .._helpers import (
    _append_query_params,
    _get_active_organization,
    _is_superadmin_user,
    _render_profile_section,
    _resolve_next_url,
)
from ..profile._sections.exam_rooms import FORM_STATE_SESSION_KEY

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


#: Hansı əməl hansı dialoqdan gəlir — JS-siz xətada həmin dialoq yenidən açılır.
_DIALOG_FOR_ACTION = {
    "create_room": "sarRoomDialog",
    "update_room": "sarRoomDialog",
    "add_computer": "sarComputerDialog",
    "update_computer": "sarComputerDialog",
    "bulk_add_computers": "sarBulkDialog",
    "grant_room_manager": "sarManagersDrawer",
}
#: Sessiyaya YAZILMAYAN sahələr (token, yönləndirmə) və dəyər uzunluğu həddi.
_STATE_SKIP_FIELDS = {"csrfmiddlewaretoken", "next"}
_STATE_MAX_VALUE = 20000
_BULK_SHOWN_ERRORS = 10


def _wants_json(request):
    """Kabinet JS-inin AJAX göndərişi (``EMSCore.fetchJSON`` bu başlığı həmişə qoyur)."""
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


@login_required
def superadmin_exam_rooms(request):
    """İmtahan zalı + kompüter/MAC idarəsi (profil SPA bölməsi)."""
    if not can_manage_exam_rooms(request.user):
        message = pgettext("accounts.superadmin_exam_rooms", "Bu bölmə yalnız zal idarəçiləri üçündür.")
        if _wants_json(request):
            return JsonResponse({"ok": False, "message": message, "errors": {"__all__": message}}, status=403)
        return HttpResponseForbidden(message)

    fallback_next = _append_query_params(reverse("accounts:profile"), section="superadmin-exam-rooms")

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        organization = _resolve_target_org(request)
        next_url = _resolve_next_url(request, fallback_next)
        if organization is None:
            return _respond_error(
                request,
                action,
                RoomAdminError(pgettext("accounts.superadmin_exam_rooms", "Təşkilat konteksti tapılmadı.")),
                next_url,
            )
        # room_org GET parametrini redirect-də saxla (superadmin seçdiyi org);
        # `next` onsuz da ehtiva edirsə təkrarlama.
        if _is_superadmin_user(request.user) and "room_org=" not in next_url:
            next_url = _append_query_params(next_url, room_org=str(organization.pk))

        try:
            outcome = _dispatch_action(request, action, organization)
        except RoomAdminError as exc:
            return _respond_error(request, action, exc, next_url)
        return _respond_success(request, action, outcome, next_url)

    return _render_profile_section(request, "superadmin-exam-rooms")


# ─── Cavablar: JSON (AJAX) və ya mesaj + redirect (adi POST) ──────────────────


def _room_fragment(request):
    room_id = parse_int(request.POST.get("room_id"))
    return f"sar-room-{room_id}" if room_id else ""


def _store_form_state(request, action, errors, message, *, values=None):
    """JS-siz xətada dialoqun vəziyyətini sessiyaya yazır (bölmə render olunanda bir dəfə oxunur)."""
    dialog = _DIALOG_FOR_ACTION.get(action)
    if not dialog:
        return
    posted = {
        key: request.POST.get(key, "")[:_STATE_MAX_VALUE] for key in request.POST if key not in _STATE_SKIP_FIELDS
    }
    posted.update(values or {})
    request.session[FORM_STATE_SESSION_KEY] = {
        "dialog": dialog,
        "action": action,
        "room_id": str(parse_int(request.POST.get("room_id")) or ""),
        "computer_id": str(parse_int(request.POST.get("computer_id")) or ""),
        "values": posted,
        "errors": dict(errors),
        "message": str(message),
    }


def _respond_error(request, action, exc, next_url):
    message = str(exc)
    errors = dict(getattr(exc, "errors", None) or {}) or {"__all__": message}
    extra = dict(getattr(exc, "payload", None) or {})
    if _wants_json(request):
        return JsonResponse({"ok": False, "message": message, "errors": errors, **extra}, status=400)
    messages.error(request, message)
    _store_form_state(request, action, errors, message)
    fragment = _room_fragment(request)
    return redirect(f"{next_url}#{fragment}" if fragment else next_url)


def _respond_success(request, action, outcome, next_url):
    message = outcome.get("message", "")
    warnings = outcome.get("warnings") or []
    if _wants_json(request):
        payload = {"ok": True, "message": message, "level": outcome.get("level", "success")}
        payload.update(outcome.get("json") or {})
        if warnings:
            payload["warnings"] = warnings
        return JsonResponse(payload)

    getattr(messages, outcome.get("level", "success"))(request, message)
    for warning in warnings:
        messages.warning(request, warning)
    keep_open = outcome.get("keep_open")
    if keep_open:
        # Toplu əlavənin qismən uğuru: dialoq yalnız uğursuz sətirlərlə yenidən açılır.
        _store_form_state(request, action, keep_open["errors"], keep_open["message"], values=keep_open["values"])
    extras = dict(outcome.get("extras") or {})
    fragment = extras.pop("_fragment", "")
    if extras:
        next_url = _append_query_params(next_url, **extras)
    return redirect(f"{next_url}#{fragment}" if fragment else next_url)


def _get_org_room(organization, room_id):
    # F-01 (2026-09-14): pozuq tam ədəd (`room_id="abc"`) → 404 (əvvəl `ValueError` → 500).
    return get_object_or_404(ExamRoom, pk=parse_int(room_id), organization=organization)


def _get_room_computer(room, computer_id):
    return get_object_or_404(ExamRoomComputer, pk=parse_int(computer_id), room=room)


def _success(message, *, room=None, extras=None, json=None, **more):
    """Uğur nəticəsi: mesaj + (adi POST üçün) vurğu parametrləri + (AJAX üçün) əlavə JSON."""
    body = {"room_id": room.pk if room is not None else None, **(json or {})}
    return {"message": message, "extras": extras or {}, "json": body, **more}


def _room_outcome(room, message):
    return _success(
        message,
        room=room,
        extras={"hl_room": str(room.pk), "_fragment": f"sar-room-{room.pk}"},
        json={"hl_room": room.pk},
    )


def _computer_outcome(room, computer, message):
    return _success(
        message,
        room=room,
        extras={"hl_comp": str(computer.pk), "_fragment": f"sar-room-{room.pk}"},
        json={"hl_comp": computer.pk},
    )


def _computer_fields(request):
    return {
        "label": request.POST.get("label", ""),
        "mac": request.POST.get("mac_address", ""),
        "seat_number": request.POST.get("seat_number", ""),
        "ip_address": request.POST.get("ip_address", ""),
        "notes": request.POST.get("notes", ""),
    }


def _dispatch_action(request, action, organization):
    """POST action-larını icra edir və nəticəni qaytarır; RoomAdminError yuxarıda tutulur."""
    user = request.user

    if action == "create_room":
        form = ExamRoomForm(request.POST, organization=organization)
        if not form.is_valid():
            raise _form_invalid(form)
        room = form.save(commit=False)
        room.organization = organization
        room.created_by = user
        # Zal bayrağı (2026-10-01): dialoq checkbox-u daşıyırsa onu oxu, yoxsa model
        # defoltu (zal). Mövcud otaqda bayraq yalnız AJAX düyməsi ilə dəyişir.
        if request.POST.get("is_exam_hall_field") == "1":
            room.is_exam_hall = request.POST.get("is_exam_hall") == "1"
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
        return _room_outcome(room, pgettext("accounts.superadmin_exam_rooms", "Zal yaradıldı."))

    if action == "update_room":
        room = _get_org_room(organization, request.POST.get("room_id"))
        form = ExamRoomForm(request.POST, instance=room, organization=organization)
        if not form.is_valid():
            raise _form_invalid(form)
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
        return _room_outcome(room, pgettext("accounts.superadmin_exam_rooms", "Zal yeniləndi."))

    if action == "toggle_room_active":
        room = _get_org_room(organization, request.POST.get("room_id"))
        room.is_active = not room.is_active
        room.save(update_fields=["is_active", "updated_at"])
        # Fraqment → kabinet JS-i həmin zalın çekmecəsini yenidən açır (əməl oradan edilir).
        return _success(
            pgettext("accounts.superadmin_exam_rooms", "Zal statusu dəyişdirildi."),
            room=room,
            extras={"_fragment": f"sar-room-{room.pk}"},
        )

    if action == "add_computer":
        room = _get_org_room(organization, request.POST.get("room_id"))
        computer = add_computer(room=room, user=user, **_computer_fields(request))
        return _computer_outcome(room, computer, pgettext("accounts.superadmin_exam_rooms", "Kompüter əlavə edildi."))

    if action == "update_computer":
        room = _get_org_room(organization, request.POST.get("room_id"))
        computer = _get_room_computer(room, request.POST.get("computer_id"))
        update_computer(computer=computer, is_active=request.POST.get("is_active") == "1", **_computer_fields(request))
        return _computer_outcome(room, computer, pgettext("accounts.superadmin_exam_rooms", "Kompüter yeniləndi."))

    if action == "delete_computer":
        room = _get_org_room(organization, request.POST.get("room_id"))
        computer = _get_room_computer(room, request.POST.get("computer_id"))
        computer.delete()
        return _success(
            pgettext("accounts.superadmin_exam_rooms", "Kompüter silindi."),
            room=room,
            extras={"_fragment": f"sar-room-{room.pk}"},
        )

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
        return _success(
            pgettext("accounts.superadmin_exam_rooms", "«%(room)s» zalı silindi.") % {"room": room_name},
            json={"removed_room": room_pk},
        )

    if action == "bulk_add_computers":
        room = _get_org_room(organization, request.POST.get("room_id"))
        return _bulk_add(request, room)

    if action in {"grant_room_manager", "revoke_room_manager"}:
        # Yalnız superadmin başqasına icazə verə/geri ala bilər (bayraqlı user yox).
        if not _is_superadmin_user(user):
            raise RoomAdminError(
                pgettext("accounts.superadmin_exam_rooms", "İcazə vermək yalnız superadminə məxsusdur.")
            )
        return _success(_set_room_manager(request, grant=action == "grant_room_manager"))

    raise RoomAdminError(pgettext("accounts.superadmin_exam_rooms", "Naməlum əməliyyat."))


def _bulk_add(request, room):
    """Toplu əlavə: heç nə alınmasa — XƏTA (dialoq açıq qalır); qismən — uğur + uğursuz sətirlər dialoqda."""
    failed_lines = []
    created, errors = bulk_add_computers(
        room=room, text=request.POST.get("bulk_text", ""), user=request.user, failed_lines=failed_lines
    )
    shown = errors[:_BULK_SHOWN_ERRORS]
    field_error = "\n".join(shown)
    if not created:
        if not errors:
            raise RoomAdminError(
                pgettext("accounts.superadmin_exam_rooms", "Əlavə ediləcək sətir tapılmadı."), field="bulk_text"
            )
        exc = RoomAdminError(
            pgettext("accounts.superadmin_exam_rooms", "Heç bir kompüter əlavə edilmədi — %(n)s sətirdə xəta var.")
            % {"n": len(errors)},
            errors={"bulk_text": field_error},
        )
        exc.payload = {"error_list": shown}
        raise exc
    message = pgettext("accounts.superadmin_exam_rooms", "%(n)s kompüter əlavə edildi.") % {"n": created}
    outcome = _success(message, room=room, extras={"_fragment": f"sar-room-{room.pk}"})
    if errors:
        summary = pgettext(
            "accounts.superadmin_exam_rooms", "%(n)s sətir əlavə edilmədi — düzəldib yenidən göndərin."
        ) % {"n": len(errors)}
        remaining = "\n".join(failed_lines)
        outcome["json"].update(
            {
                "keep_open": True,
                "summary": summary,
                "errors": {"bulk_text": field_error},
                "error_list": shown,
                "remaining_text": remaining,
            }
        )
        outcome["keep_open"] = {
            "errors": {"bulk_text": field_error},
            "message": summary,
            "values": {"bulk_text": remaining},
        }
    return outcome


def _set_room_manager(request, *, grant):
    from django.contrib.auth import get_user_model

    from core.rls import bypass_rls

    User = get_user_model()
    identifier = (request.POST.get("username") or request.POST.get("user_id") or "").strip()
    if not identifier:
        raise RoomAdminError(pgettext("accounts.superadmin_exam_rooms", "İstifadəçi göstərilməyib."), field="username")
    with bypass_rls():
        target = (
            User.objects.filter(pk=identifier).first()
            if identifier.isdigit()
            else User.objects.filter(username=identifier).first()
            or User.objects.filter(email__iexact=identifier).first()
        )
    if target is None:
        raise RoomAdminError(
            pgettext("accounts.superadmin_exam_rooms", "İstifadəçi tapılmadı: %(u)s") % {"u": identifier},
            field="username",
        )
    profile = getattr(target, "profile", None)
    if profile is None:
        raise RoomAdminError(pgettext("accounts.superadmin_exam_rooms", "İstifadəçi profili yoxdur."), field="username")
    profile.can_manage_exam_rooms = grant
    profile.save(update_fields=["can_manage_exam_rooms", "updated_at"])
    if grant:
        return pgettext("accounts.superadmin_exam_rooms", "%(u)s zal idarəçisi təyin edildi.") % {"u": target.username}
    return pgettext("accounts.superadmin_exam_rooms", "%(u)s zal idarəçiliyindən çıxarıldı.") % {"u": target.username}


def _form_invalid(form):
    """ModelForm xətaları → sahə-sahə ``RoomAdminError`` (əsas mesaj — birinci xəta)."""
    errors = {name: str(errs[0]) for name, errs in form.errors.items() if errs}
    first = next(iter(errors.values()), pgettext("accounts.superadmin_exam_rooms", "Form məlumatları düzgün deyil."))
    return RoomAdminError(first, errors=errors or {"__all__": first})


__all__ = ["superadmin_exam_rooms"]
