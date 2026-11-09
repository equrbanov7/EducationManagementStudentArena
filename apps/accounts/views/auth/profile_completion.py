"""«Məlumatlarınızı tamamlayın» səhifəsi (sahib 2026-10-17).

``ProfileCompletionMiddleware`` boş vacib sahəsi (FİN, mobil telefon, şəxsi e-poçt) olan istifadəçini bura yönləndirir.
Səhifə YALNIZ boş sahələri göstərir, hər birinin altında «nəyə görə lazımdır» izahı və məxfilik qeydi var.
Siyasət: ``apps/accounts/profile_completion.py``; yazı: ``services/profile_completion.py``.
"""

from __future__ import annotations

import logging
from urllib.parse import urlsplit

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import pgettext

from apps.audit.public import log_action
from core import phone as phone_lib
from core.constants import AuditAction
from core.helpers import _safe_same_origin_redirect_path

from ... import profile_completion as policy
from ... import shared_fin
from ...services.profile_completion import complete_profile, fin_conflict_message

_CTX = "accounts.profile_completion"
logger = logging.getLogger(__name__)


def _next_url(request) -> str:
    raw = request.POST.get("next") if request.method == "POST" else request.GET.get("next")
    target = _safe_same_origin_redirect_path(request, raw or "")
    # «next» özü bu səhifədirsə qapıya geri qayıdırdıq (QA-1 F18) — kabinetə düşsün.
    if target and urlsplit(target).path.rstrip("/") == reverse("accounts:complete_profile").rstrip("/"):
        return ""
    return target


def _audit_skip(request, missing) -> None:
    """Ötürmə audit-ə yalnız sahə adları ilə düşür (RİM kimlərin hələ doldurmadığını görür)."""
    try:
        log_action(
            action=AuditAction.UPDATE,
            user=request.user,
            organization=getattr(request, "organization", None),
            obj=request.user,
            reason="profile_completion_skipped",
            changes={"fields": sorted(spec.key for spec in missing)},
            request=request,
        )
    except Exception:  # noqa: BLE001 — audit xətası istifadəçini bloklamamalıdır
        logger.exception("profile completion skip audit failed")


def _link_offer_context(link_offer, submitted):
    if not link_offer:
        return None
    family = link_offer.get("holder_family")
    label = (
        pgettext(_CTX, "tələbə hesabınız")
        if family == policy.ROLE_STUDENT
        else pgettext(_CTX, "işçi hesabınız") if family == policy.ROLE_STAFF else pgettext(_CTX, "başqa hesabınız")
    )
    return {
        "holder_name": link_offer.get("holder_name", ""),
        "holder_label": label,
        "confirm_field": shared_fin.CONFIRM_FIELD,
        # Təsdiq forması eyni dəyərləri yenidən göndərir (FİN daxil) + gizli təsdiq sahəsi.
        "values": [(key, value) for key, value in submitted.items() if value],
        "conflict_message": fin_conflict_message(),
    }


def _leave(request):
    return redirect(_next_url(request) or "accounts:profile")


@login_required
def complete_profile_view(request):
    # View-as: hədəfin şəxsi məlumatlarını onun adından yazmaq olmaz (POST ViewAsMiddleware-də də bağlıdır).
    if getattr(request, "is_view_as", False):
        return redirect("accounts:profile")

    missing = policy.missing_for_request(request)
    if not missing:
        return _leave(request)

    if request.method == "POST" and request.POST.get("skip") and policy.skip_allowed():
        # «Hələlik keç»: heç nə yazılmır, yalnız bu sessiyada davam edir (sahib 2026-10-17).
        policy.mark_skipped(request)
        _audit_skip(request, missing)
        return _leave(request)

    errors, submitted = {}, {}
    phone_country = ""
    link_offer = None
    if request.method == "POST":
        submitted = {spec.key: (request.POST.get(spec.key) or "").strip()[: spec.max_length] for spec in missing}
        # Xəta ilə yenidən göstərəndə istifadəçinin seçdiyi ölkə saxlanır (boşdursa dəyər nömrədən tanınır).
        phone_country = (request.POST.get(phone_lib.country_field_name(policy.FIELD_PHONE)) or "").strip()
        result = complete_profile(request, request.POST)
        if result.ok:
            messages.success(request, pgettext(_CTX, "Məlumatlarınız saxlanıldı. Təşəkkür edirik!"))
            return _leave(request)
        errors = result.errors
        link_offer = result.link_offer

    user = request.user
    fields = [
        {
            "spec": spec,
            "name": spec.key,
            "value": submitted.get(spec.key, ""),
            "error": errors.get(spec.key, ""),
        }
        for spec in missing
    ]
    return render(
        request,
        "accounts/profile_completion.html",
        {
            "fields": fields,
            "next_url": _next_url(request),
            "user_display": user.get_full_name() or user.username,
            "has_errors": bool(errors),
            "can_skip": policy.skip_allowed(),
            "phone_country": phone_country,
            # Sahib 2026-11-09: FİN eyni adlı tələbə/işçi hesabındadır — «hər iki hesab mənimdir?» modalı.
            "link_offer": _link_offer_context(link_offer, submitted),
        },
    )
