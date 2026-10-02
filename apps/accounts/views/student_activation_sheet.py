"""Qrupun «ilk giriş» çap vərəqi — hesab aktivləşdirmə kampaniyası (sahib 2026-10-03).

Dekanlıq / kurator vərəqi çap edib qrupa paylayır: addım-addım təlimat (sadə dildə), giriş
səhifəsinin QR kodu və hələ aktivləşdirməyən tələbələrin ADI + İSTİFADƏÇİ ADI. Parol, e-poçt,
vəsiqə nömrəsi YOXDUR — vərəq itsə də hesaba giriş vermir.

Qapı reyestrlə EYNİDİR (`student.registry_view` + əhatə): qrup aktorun əhatəsində deyilsə 404.
"""

from __future__ import annotations

import uuid

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

import qrcode
import qrcode.image.svg

from apps.accounts.services import people
from apps.accounts.services.people import activation as activation_service


def _login_qr_svg(url: str) -> str:
    """Giriş səhifəsinin QR kodu — inline SVG (şəkil sorğusu yox, CSP-yə uyğun, çapda kəskin)."""
    image = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2)
    return image.to_string(encoding="unicode")


@never_cache
@login_required
@require_GET
def student_activation_sheet(request):
    actor = people.resolve_actor(request)
    try:
        group_id = str(uuid.UUID((request.GET.get("group") or "").strip()))
    except ValueError as exc:
        raise Http404 from exc
    sheet = activation_service.activation_sheet(actor=actor, group_id=group_id, request=request)
    if sheet is None:
        raise Http404

    login_url = request.build_absolute_uri(reverse("accounts:student_login"))
    context = {
        "sheet": sheet,
        "organization": actor.organization,
        "login_url": login_url,
        "login_host": request.get_host(),
        # Kitabxananın öz SVG çıxışıdır (istifadəçi mətni daxil deyil) — təhlükəsiz.
        "login_qr": mark_safe(_login_qr_svg(login_url)),  # noqa: S308
        "printed_at": timezone.localtime(),
        "back_url": f"{reverse('accounts:profile')}?section=student-registry&sr_view=activation",
    }
    response = render(request, "accounts/people/activation_sheet.html", context)
    response["Cache-Control"] = "private, no-store"
    return response


__all__ = ["student_activation_sheet"]
