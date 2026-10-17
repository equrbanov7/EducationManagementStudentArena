"""«Məlumatlarınızı tamamlayın» səhifəsi (sahib 2026-10-17).

``ProfileCompletionMiddleware`` boş vacib sahəsi (FİN, mobil telefon, şəxsi e-poçt) olan istifadəçini bura yönləndirir.
Səhifə YALNIZ boş sahələri göstərir, hər birinin altında «nəyə görə lazımdır» izahı və məxfilik qeydi var.
Siyasət: ``apps/accounts/profile_completion.py``; yazı: ``services/profile_completion.py``.
"""

from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.translation import pgettext

from apps.audit.public import log_action
from core.constants import AuditAction
from core.helpers import _safe_same_origin_redirect_path

from ... import profile_completion as policy
from ...services.profile_completion import complete_profile

_CTX = "accounts.profile_completion"
logger = logging.getLogger(__name__)


def _next_url(request) -> str:
    raw = request.POST.get("next") if request.method == "POST" else request.GET.get("next")
    return _safe_same_origin_redirect_path(request, raw or "")


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
    operator = policy.AZ_MOBILE_OPERATORS[0]
    if request.method == "POST":
        submitted = {spec.key: (request.POST.get(spec.key) or "").strip()[: spec.max_length] for spec in missing}
        posted_operator = (request.POST.get(policy.PHONE_OPERATOR_FIELD) or "").strip()
        if posted_operator in policy.AZ_MOBILE_OPERATORS or posted_operator == policy.OPERATOR_OTHER:
            operator = posted_operator
        result = complete_profile(request, request.POST)
        if result.ok:
            messages.success(request, pgettext(_CTX, "Məlumatlarınız saxlanıldı. Təşəkkür edirik!"))
            return _leave(request)
        errors = result.errors

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
            "phone_operators": policy.AZ_MOBILE_OPERATORS,
            "phone_operator": operator,
            "phone_operator_other": policy.OPERATOR_OTHER,
        },
    )
