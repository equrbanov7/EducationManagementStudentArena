"""Aktiv təşkilatın SON üzvlük/rol dəyişiklikləri — «Təşkilat paneli» vidceti (2026-10-01).

Audit jurnalının kiçik, oxu-only kəsiyi: panel tam jurnal bölməsini əvəz etmir,
yalnız son N qeydi göstərir və «Audit jurnalı»na keçid verir. Qapı jurnal
bölməsinin ÖZ qapısıdır (``can_view_audit`` — superadmin · sahib · ``audit.view``);
qapı bağlıdırsa boş siyahı qaytarılır (FAIL-CLOSED, sorğu yoxdur). Qeydlər HƏMİŞƏ
aktiv təşkilata daralır — superadmin də başqa təşkilatın izini burada görmür.
"""

from __future__ import annotations

from django.utils import timezone

from core.permissions import is_superadmin_user
from core.tenancy import get_request_organization

from .models import AuditLog
from .views_filters import _run_scoped, can_view_audit
from .views_serializers import _display_name, _initials, _resource_bits, action_label

#: Panel üçün maraqlı resurs tipləri — üzvlük, dəvət və rol dəyişiklikləri.
MEMBERSHIP_RESOURCE_TYPES = ("membership", "membership_invite", "role")


def recent_org_changes(request, *, limit: int = 6, resource_types=MEMBERSHIP_RESOURCE_TYPES) -> list[dict]:
    """Son dəyişikliklər (materiallaşdırılmış sətirlər); qapı bağlıdırsa ``[]``."""
    organization = get_request_organization(request)
    if organization is None or not can_view_audit(request):
        return []
    is_superadmin = is_superadmin_user(request.user)

    def _materialize():
        queryset = (
            AuditLog.objects.filter(organization=organization, resource_type__in=list(resource_types))
            .select_related("user", "content_type")
            .order_by("-created_at")
        )
        rows = []
        for log in queryset[: max(1, int(limit))]:
            user = log.user if log.user_id else None
            name = _display_name(user) if user is not None else ""
            type_label, _identifier, repr_text = _resource_bits(log)
            rows.append(
                {
                    "created_at": timezone.localtime(log.created_at),
                    "actor_name": name,
                    "actor_initials": _initials(name) if name else "",
                    "action": log.action,
                    "action_label": action_label(log.action),
                    "resource_type": type_label,
                    "resource": repr_text,
                    "resource_key": log.resource_type or "",
                    "reason": log.reason or "",
                }
            )
        return rows

    return _run_scoped(is_superadmin, _materialize)


__all__ = ["MEMBERSHIP_RESOURCE_TYPES", "recent_org_changes"]
