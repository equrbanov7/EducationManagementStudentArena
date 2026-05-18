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
from django.utils.translation import pgettext_lazy

from apps.notifications.models import NotificationType
from apps.notifications.services import create_notification
from apps.organizations.models import REVIEW_VISIBILITY_FEATURES, Organization
from apps.organizations.services import ensure_owner_membership

from ._helpers import (
    _append_query_params,
    _is_superadmin_user,
    _render_profile_section,
    _resolve_next_url,
)

logger = logging.getLogger(__name__)
User = get_user_model()


def build_superadmin_ai_settings_context():
    """Return reusable context for the superadmin AI settings screen."""
    from apps.exams.domain.ai_config import AIConfiguration
    from apps.exams.services.ai_summary import _get_rate_limit
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
            title = f"Təşkilatınız təsdiqləndi: {org.name}"
            message = (
                f'"{org.name}" təşkilatı superadmin tərəfindən təsdiqləndi. '
                "İndi bütün funksiyalardan istifadə edə bilərsiniz."
            )
        else:
            title = f"Təşkilat müraciəti rədd edildi: {org.name}"
            message = f'"{org.name}" təşkilatı superadmin tərəfindən rədd edildi.'
            if reason:
                message += f" Səbəb: {reason}"

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
        title = f"Yeni təşkilat müraciəti: {org.name}"
        message = f'"{org.name}" adlı yeni təşkilat superadmin təsdiqi gözləyir. ' f"Növ: {org.get_org_type_display()}."

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
                messages.warning(request, "Bu təşkilat artıq gözləmə vəziyyətində deyil.")
            else:
                organization.status = "active"
                organization.is_active = True
                organization.save(update_fields=["status", "is_active", "updated_at"])
                ensure_owner_membership(organization.owner, organization)
                _notify_org_owner_of_approval(organization, request.user, approved=True)
                messages.success(
                    request,
                    f'"{organization.name}" təşkilatı uğurla təsdiqləndi.',
                )

        elif action == "reject":
            # Reject and deactivate a pending organization.
            if organization.status not in {"pending", "active"}:
                messages.warning(request, "Bu əməliyyat mövcud vəziyyətdə tətbiq oluna bilməz.")
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
                    f'"{organization.name}" təşkilatı rədd edildi.',
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
        elif action in {"set_written_exam_identity_reveal", "set_review_identity_reveal"}:
            feature_name = (request.POST.get("feature_name") or "").strip() or "written_exam"
            feature_config = REVIEW_VISIBILITY_FEATURES.get(feature_name)
            if feature_config is None:
                messages.error(request, "Naməlum review visibility feature seçildi.")
                return redirect(next_url)

            reveal_enabled = request.POST.get("enabled") == "1"
            organization.set_review_identity_reveal_enabled(feature_name, reveal_enabled)
            organization.save(update_fields=["settings", "updated_at"])
            messages.success(
                request,
                (
                    f'"{organization.name}" üçün {feature_config["short_label"].lower()} anonimliyi '
                    f'{"söndürüldü" if reveal_enabled else "yenidən aktiv edildi"}.'
                ),
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

    from apps.exams.domain.ai_config import AIConfiguration

    config = AIConfiguration.load()
    fallback_next_url = reverse("accounts:superadmin_ai_settings")

    if request.method == "POST":
        action = request.POST.get("action", "save")

        if action == "save":
            config.enabled = request.POST.get("enabled") == "on"
            config.rate_limit = (request.POST.get("rate_limit") or "100/1h").strip()
            config.summary_model = request.POST.get("summary_model", config.summary_model)
            config.grading_model = request.POST.get("grading_model", config.grading_model)

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
