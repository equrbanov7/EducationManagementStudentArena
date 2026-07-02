"""Audit yazma helper-ləri (shared kernel).

M2/M3 (2026-07-02): `log_action` və `log_superadmin_cross_org_action`
apps/audit/utils.py-dən köçürülüb — core/admin_* və core/tasks bunları
istifadə etdiyi üçün core→audit kənarı yaranırdı. AuditLog modeli audit
app-ında qalır (lazy `get_model` ilə tapılır); apps/audit/utils.py
geriyə-uyğun re-export saxlayır (AGENTS §1).
"""

from django.apps import apps as django_apps
from django.contrib.contenttypes.models import ContentType

from core.utils import get_client_ip


def log_action(
    action,
    user=None,
    organization=None,
    obj=None,
    old_values=None,
    new_values=None,
    changes=None,
    reason="",
    request=None,
    resource_type="",
    resource_id="",
    resource_repr="",
):
    """
    Create an audit log entry.

    Args:
        action: Action constant from AuditAction
        user: User performing the action
        organization: Organization context
        obj: Object being acted upon
        old_values: Dictionary of old values (for updates)
        new_values: Dictionary of new values (for updates/creates)
        changes: Dictionary of specific changes
        reason: Reason for the action
        request: HTTP request object (for IP and user agent)

    Returns:
        Created AuditLog instance
    """
    AuditLog = django_apps.get_model("audit", "AuditLog")

    log_data = {
        "action": action,
        "user": user,
        "organization": organization,
        "old_values": old_values,
        "new_values": new_values,
        "changes": changes,
        "reason": reason,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "resource_repr": resource_repr,
    }

    # Add object information if provided
    if obj:
        log_data["content_type"] = ContentType.objects.get_for_model(obj)
        log_data["object_id"] = str(obj.pk)

    # Add request information if provided
    if request:
        log_data["ip_address"] = get_client_ip(request)
        log_data["user_agent"] = request.META.get("HTTP_USER_AGENT", "")[:500]
        request_id = getattr(request, "request_id", None)
        if request_id:
            log_data["request_id"] = request_id

    return AuditLog.objects.create(**log_data)


def log_superadmin_cross_org_action(request, action: str, *, target_org=None, obj=None, reason: str = "") -> None:
    """
    Record an audit trail entry whenever a Superadmin performs an action in an
    organization they are **not** a direct member of (cross-org access).

    This function is a no-op when:
    * The requesting user is not a superadmin/superuser.
    * No ``target_org`` can be resolved (no active org context on the request).
    * The superadmin **does** have an active membership in the target org
      (same-org access does not need special logging).

    Args:
        request: The current HTTP request (provides user, IP, user-agent).
        action: A short action label – use ``AuditAction.*`` constants, or any
                descriptive string that identifies the operation being performed.
        target_org: The Organization instance being accessed.  When *None*, the
                    value is taken from ``request.organization``.
        obj: Optional Django model instance that was acted upon (sets the
             Generic FK on the log entry).
        reason: Free-text explanation stored in the log's ``reason`` field.
    """
    from core.permissions import is_superadmin_user

    user = getattr(request, "user", None)
    if not is_superadmin_user(user):
        return

    org = target_org or getattr(request, "organization", None)
    if org is None:
        return

    # Superadmin acting within their own membership is not a cross-org event.
    memberships = getattr(request, "org_memberships", []) or []
    if any(m.organization_id == org.id for m in memberships):
        return

    log_action(
        action=action,
        user=user,
        organization=org,
        obj=obj,
        reason=reason or f"Superadmin cross-org access to organization '{org.name}' ({org.pk})",
        request=request,
    )
