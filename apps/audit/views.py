"""
Views for the audit app.
"""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from django.utils.translation import pgettext

from core.permissions import is_superadmin_user, request_has_permission
from core.tenancy import get_request_organization

from .models import AuditLog


def build_audit_log_context(request):
    is_superadmin = is_superadmin_user(request.user)
    organization = get_request_organization(request)

    audit_logs = AuditLog.objects.select_related("user", "organization", "content_type")
    if organization is not None and not is_superadmin:
        audit_logs = audit_logs.filter(organization=organization)

    return {
        "audit_logs": audit_logs[:100],
        "current_organization": organization,
        "is_superadmin": is_superadmin,
    }


@login_required
def audit_log_list(request):
    """Render a lightweight audit log page for authorized users."""
    is_superadmin = is_superadmin_user(request.user)

    if not is_superadmin and not request_has_permission(request, "audit.view"):
        raise PermissionDenied(
            pgettext("audit.view.permission", "required_permission_missing").format(permission="audit.view")
        )

    context = build_audit_log_context(request)
    context["audit_log_section"] = context
    return render(request, "audit/list.html", context)
