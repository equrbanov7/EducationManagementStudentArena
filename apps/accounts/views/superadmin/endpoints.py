"""
Superadmin views for organization oversight and AI settings.
"""

import logging

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext, pgettext_lazy

from apps.notifications.models import NotificationType
from apps.notifications.public import create_notification
from apps.organizations.models import REVIEW_VISIBILITY_FEATURES, Organization
from apps.organizations.public import ensure_owner_membership

from .._helpers import (
    _append_query_params,
    _is_superadmin_user,
    _render_profile_section,
    _resolve_next_url,
)

logger = logging.getLogger(__name__)
User = get_user_model()


def build_superadmin_ai_settings_context():
    """Return reusable context for the superadmin AI settings screen."""
    from apps.exams.models import AIConfiguration
    from apps.exams.public import get_ai_rate_limit as _get_rate_limit
    from core.rate_limit import parse_rate

    config = AIConfiguration.load()
    parsed = parse_rate(_get_rate_limit())

    return {
        "config": config,
        "model_choices": AIConfiguration.MODEL_CHOICES,
        "rate_info": {
            "limit": parsed.limit if parsed else 0,
            "window_seconds": parsed.window_seconds if parsed else 0,
        },
        "cost_estimates": _estimate_monthly_cost(config),
    }


def _notify_org_owner_of_approval(org, approved_by, *, approved: bool, reason: str = ""):
    """Send an in-app notification to the organization owner about approval outcome."""
    try:
        if approved:
            title = pgettext("accounts.superadmin_orgs.notification", "Təşkilatınız təsdiqləndi: {org}").format(
                org=org.name
            )
            message = pgettext(
                "accounts.superadmin_orgs.notification",
                '"{org}" təşkilatı superadmin tərəfindən təsdiqləndi. '
                "İndi bütün funksiyalardan istifadə edə bilərsiniz.",
            ).format(org=org.name)
        else:
            title = pgettext("accounts.superadmin_orgs.notification", "Təşkilat müraciəti rədd edildi: {org}").format(
                org=org.name
            )
            message = pgettext(
                "accounts.superadmin_orgs.notification", '"{org}" təşkilatı superadmin tərəfindən rədd edildi.'
            ).format(org=org.name)
            if reason:
                message = pgettext("accounts.superadmin_orgs.notification", "{message} Səbəb: {reason}").format(
                    message=message, reason=reason
                )

        create_notification(
            recipient=org.owner,
            title=title,
            message=message,
            link=reverse("accounts:profile"),
            notification_type=NotificationType.APPROVAL,
        )
    except Exception:
        logger.exception(
            "Failed to send org approval notification to owner %s for org %s",
            org.owner_id,
            org.pk,
        )


def _notify_superadmins_of_pending_org(org):
    """Notify all superadmin users that a new organization is awaiting approval."""
    try:
        superadmins = list(User.objects.filter(is_superuser=True, is_active=True))
        if not superadmins:
            return

        link = _append_query_params(
            reverse("accounts:profile"),
            section="superadmin-organizations",
        )
        title = pgettext("accounts.superadmin_orgs.notification", "Yeni təşkilat müraciəti: {org}").format(org=org.name)
        message = pgettext(
            "accounts.superadmin_orgs.notification",
            '"{org}" adlı yeni təşkilat superadmin təsdiqi gözləyir. Növ: {org_type}.',
        ).format(org=org.name, org_type=org.get_org_type_display())

        for superadmin in superadmins:
            create_notification(
                recipient=superadmin,
                title=title,
                message=message,
                link=link,
                notification_type=NotificationType.APPROVAL,
            )
    except Exception:
        logger.exception("Failed to send pending-org notifications for org %s", org.pk)


@login_required
def superadmin_organizations(request):
    """
    Superadmin-only view showing all organizations with filtering, search and bulk operations.
    """
    if not _is_superadmin_user(request.user):
        return HttpResponseForbidden("Bu bölməyə yalnız superadminlər daxil ola bilər.")

    fallback_next_url = reverse("accounts:superadmin_organizations")

    if request.method == "POST":
        organization = get_object_or_404(Organization, id=request.POST.get("organization_id"))
        action = request.POST.get("action")
        reason = (request.POST.get("reason") or "").strip()
        next_url = _resolve_next_url(request, fallback_next_url)

        if action == "approve":
            # Approve a pending organization: set status to active.
            if organization.status != "pending":
                messages.warning(
                    request,
                    pgettext_lazy("accounts.superadmin_orgs.message", "Bu təşkilat artıq gözləmə vəziyyətində deyil."),
                )
            else:
                organization.status = "active"
                organization.is_active = True
                organization.save(update_fields=["status", "is_active", "updated_at"])
                ensure_owner_membership(organization.owner, organization)
                _notify_org_owner_of_approval(organization, request.user, approved=True)
                messages.success(
                    request,
                    pgettext_lazy(
                        "accounts.superadmin_orgs.message",
                        '"%(organization_name)s" təşkilatı uğurla təsdiqləndi.',
                    )
                    % {"organization_name": organization.name},
                )

        elif action == "reject":
            # Reject and deactivate a pending organization.
            if organization.status not in {"pending", "active"}:
                messages.warning(
                    request,
                    pgettext_lazy(
                        "accounts.superadmin_orgs.message",
                        "Bu əməliyyat mövcud vəziyyətdə tətbiq oluna bilməz.",
                    ),
                )
            else:
                organization.status = "suspended"
                organization.is_active = False
                organization.suspended_at = timezone.now()
                organization.suspension_reason = reason or "Superadmin tərəfindən rədd edildi."
                organization.save(
                    update_fields=[
                        "status",
                        "is_active",
                        "suspended_at",
                        "suspension_reason",
                        "updated_at",
                    ]
                )
                _notify_org_owner_of_approval(organization, request.user, approved=False, reason=reason)
                messages.success(
                    request,
                    pgettext_lazy(
                        "accounts.superadmin_orgs.message",
                        '"%(organization_name)s" təşkilatı rədd edildi.',
                    )
                    % {"organization_name": organization.name},
                )

        elif action == "suspend":
            organization.status = "suspended"
            organization.is_active = False
            organization.suspended_at = timezone.now()
            organization.suspension_reason = reason
            organization.save(
                update_fields=[
                    "status",
                    "is_active",
                    "suspended_at",
                    "suspension_reason",
                    "updated_at",
                ]
            )
            messages.success(
                request,
                pgettext_lazy("accounts.superadmin_orgs.message", "organization_suspended")
                % {"organization_name": organization.name},
            )
        elif action == "unsuspend":
            organization.status = "active"
            organization.is_active = True
            organization.suspended_at = None
            organization.suspension_reason = ""
            organization.save(
                update_fields=[
                    "status",
                    "is_active",
                    "suspended_at",
                    "suspension_reason",
                    "updated_at",
                ]
            )
            messages.success(
                request,
                pgettext_lazy("accounts.superadmin_orgs.message", "organization_unsuspended")
                % {"organization_name": organization.name},
            )
        elif action == "set_cabinet_module":
            # U16 — kabinet modul görünürlüyü (superadmin aç/bağla paneli).
            from apps.organizations.cabinet_modules import CABINET_MODULES, set_module_enabled

            module_key = (request.POST.get("module_key") or "").strip()
            if module_key not in CABINET_MODULES:
                messages.error(
                    request,
                    pgettext_lazy("accounts.superadmin_orgs.message", "Naməlum kabinet modulu seçildi."),
                )
                return redirect(next_url)
            module_enabled = request.POST.get("enabled") == "1"
            set_module_enabled(organization, module_key, module_enabled)
            module_label = CABINET_MODULES[module_key]["label"]
            if module_enabled:
                module_msg = pgettext_lazy(
                    "accounts.superadmin_orgs.message",
                    '"%(organization_name)s" üçün "%(module)s" modulu aktiv edildi.',
                )
            else:
                module_msg = pgettext_lazy(
                    "accounts.superadmin_orgs.message",
                    '"%(organization_name)s" üçün "%(module)s" modulu gizlədildi.',
                )
            messages.success(request, module_msg % {"organization_name": organization.name, "module": module_label})
        elif action == "set_letter_bands":
            # U17 — tenant hərf qiyməti şkalası (hədd:hərf:gpa siyahısı).
            from apps.registrar import grading_scale

            try:
                bands = grading_scale.parse_bands_text(request.POST.get("letter_bands") or "")
                grading_scale.set_bands(organization, bands)
            except ValueError as exc:
                bands_err = pgettext_lazy("accounts.superadmin_orgs.message", "Hərf şkalası qəbul edilmədi: %(error)s")
                messages.error(request, bands_err % {"error": exc})
                return redirect(next_url)
            bands_ok = pgettext_lazy(
                "accounts.superadmin_orgs.message",
                '"%(organization_name)s" üçün hərf qiyməti şkalası yeniləndi.',
            )
            messages.success(request, bands_ok % {"organization_name": organization.name})
        elif action == "reset_letter_bands":
            # U17 — şkalanı AZ Boloniya default-una qaytar.
            from apps.registrar import grading_scale

            grading_scale.reset_bands(organization)
            bands_reset = pgettext_lazy(
                "accounts.superadmin_orgs.message",
                '"%(organization_name)s" üçün hərf qiyməti şkalası default-a qaytarıldı.',
            )
            messages.success(request, bands_reset % {"organization_name": organization.name})
        elif action in {"set_written_exam_identity_reveal", "set_review_identity_reveal"}:
            feature_name = (request.POST.get("feature_name") or "").strip() or "written_exam"
            feature_config = REVIEW_VISIBILITY_FEATURES.get(feature_name)
            if feature_config is None:
                messages.error(
                    request,
                    pgettext_lazy("accounts.superadmin_orgs.message", "Naməlum review visibility feature seçildi."),
                )
                return redirect(next_url)

            reveal_enabled = request.POST.get("enabled") == "1"
            organization.set_review_identity_reveal_enabled(feature_name, reveal_enabled)
            organization.save(update_fields=["settings", "updated_at"])
            feature_label = feature_config["short_label"].lower()
            # Ayrı tam mesajlar (şərti "söndürüldü/yenidən aktiv edildi" cümlə
            # daxilinə yerləşdirilmir — tərcümə oluna bilməsi üçün).
            if reveal_enabled:
                anonymity_msg = pgettext_lazy(
                    "accounts.superadmin_orgs.message",
                    '"%(organization_name)s" üçün %(feature)s anonimliyi söndürüldü.',
                )
            else:
                anonymity_msg = pgettext_lazy(
                    "accounts.superadmin_orgs.message",
                    '"%(organization_name)s" üçün %(feature)s anonimliyi yenidən aktiv edildi.',
                )
            messages.success(
                request,
                anonymity_msg % {"organization_name": organization.name, "feature": feature_label},
            )
        else:
            messages.error(request, pgettext_lazy("accounts.superadmin_orgs.message", "unknown_action"))

        return redirect(next_url)

    return _render_profile_section(request, "superadmin-organizations")


@login_required
def superadmin_ai_settings(request):
    """SuperAdmin page for managing platform-wide AI configuration."""
    if not _is_superadmin_user(request.user):
        return HttpResponseForbidden("Bu bölməyə yalnız superadminlər daxil ola bilər.")

    from apps.exams.models import AIConfiguration

    config = AIConfiguration.load()
    fallback_next_url = reverse("accounts:superadmin_ai_settings")

    if request.method == "POST":
        action = request.POST.get("action", "save")

        if action == "save":
            valid_models = {choice[0] for choice in AIConfiguration.MODEL_CHOICES}

            def _pick_model(field_name: str, current: str) -> str:
                """Accept only a model from MODEL_CHOICES; otherwise keep current."""
                submitted = (request.POST.get(field_name) or "").strip()
                return submitted if submitted in valid_models else current

            config.enabled = request.POST.get("enabled") == "on"
            config.rate_limit = (request.POST.get("rate_limit") or "100/1h").strip()
            config.summary_model = _pick_model("summary_model", config.summary_model)
            config.grading_model = _pick_model("grading_model", config.grading_model)
            config.assistant_model = _pick_model("assistant_model", config.assistant_model)

            budget_raw = request.POST.get("monthly_budget", "5.00")
            try:
                config.monthly_budget = max(0, float(budget_raw))
            except (ValueError, TypeError):
                pass

            config.save()
            messages.success(
                request,
                pgettext_lazy("accounts.superadmin_ai.message", "ai_settings_saved"),
            )

        return redirect(_resolve_next_url(request, fallback_next_url))

    return _render_profile_section(request, "superadmin-ai")


def _estimate_monthly_cost(config):
    """Rough cost estimate based on model selection and rate limit.

    Based on Google AI Studio Paid Tier 1 pricing (April 2026):
        - gemini-2.5-flash:       $0.15 / 1M input,  $0.60 / 1M output
        - gemini-2.5-flash-lite:  $0.075 / 1M input,  $0.30 / 1M output
        - gemini-2.5-pro:         $1.25 / 1M input,  $10.00 / 1M output
    """
    pricing = {
        "gemini-2.5-flash": {"input": 0.15, "output": 0.60},
        "gemini-2.5-flash-lite": {"input": 0.075, "output": 0.30},
        "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
    }

    summary_price = pricing.get(config.summary_model, pricing["gemini-2.5-flash"])
    grading_price = pricing.get(config.grading_model, pricing["gemini-2.5-flash-lite"])

    # Estimate: ~2K input + ~1K output tokens per summary, ~500 input + ~200 output per grade
    summary_cost_per_req = (2000 * summary_price["input"] + 1000 * summary_price["output"]) / 1_000_000
    grading_cost_per_req = (500 * grading_price["input"] + 200 * grading_price["output"]) / 1_000_000

    budget = float(config.monthly_budget)
    max_summaries = int(budget / summary_cost_per_req) if summary_cost_per_req > 0 else 0
    max_gradings = int(budget / grading_cost_per_req) if grading_cost_per_req > 0 else 0

    return {
        "summary_cost": round(summary_cost_per_req * 1000, 2),  # per 1K requests
        "grading_cost": round(grading_cost_per_req * 1000, 2),
        "max_summaries": max_summaries,
        "max_gradings": max_gradings,
    }
