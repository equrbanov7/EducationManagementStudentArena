"""audit modulunun PUBLIC API fasadı (M3-B, 2026-07-02).

Yazma tərəfi shared kernel-dədir: core.audit.log_action /
log_superadmin_cross_org_action (app-lardan da oradan istifadə edin).
Bu fasad oxu/görüntüləmə tərəfini təqdim edir.
"""

from apps.audit.views import (  # noqa: F401
    build_audit_log_context,
)
from core.audit import (  # noqa: F401
    log_action,
    log_superadmin_cross_org_action,
)

__all__ = [
    "build_audit_log_context",
    "log_action",
    "log_superadmin_cross_org_action",
]
