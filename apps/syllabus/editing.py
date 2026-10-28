"""Avtomatik təsdiq rejimində müəllifin təsdiqlənmiş sillabus düzəlişləri."""

from django.utils import timezone

from core import runtime_settings_syllabus
from core.audit import log_action
from core.constants import AuditAction

from .constants import SyllabusStatus
from .models import ApprovalSource


def approved_edits_enabled(version):
    return bool(
        version is not None
        and version.status == SyllabusStatus.APPROVED.value
        and not version.syllabus.reused_from_id
        and not runtime_settings_syllabus.approval_required()
    )


def record_approved_edit(*, version, row, old_data, actor, request=None):
    """Status/pointer dəyişmir; əvvəlki məzmun və təsdiq mənşəyi auditdə saxlanılır."""
    old_approval = {
        "source": version.approval_source,
        "approved_by": version.approved_by_id,
        "approved_at": version.approved_at.isoformat() if version.approved_at else None,
    }
    version.approval_source = ApprovalSource.AUTO
    version.approved_by = None
    version.approved_at = timezone.now()
    version.locked_at = version.approved_at
    version.save(update_fields=["approval_source", "approved_by", "approved_at", "locked_at", "updated_at"])
    log_action(
        AuditAction.UPDATE,
        user=actor.user,
        organization=version.organization,
        obj=version,
        request=request,
        resource_type="syllabus.approved_edit",
        resource_id=f"{version.pk}:{row.section_id}",
        old_values={"data": old_data, "approval": old_approval},
        new_values={"data": row.data, "status": SyllabusStatus.APPROVED.value, "revision": row.revision},
        reason="Təsdiqlənmiş sillabusun müəllif düzəlişi — avtomatik təsdiq rejimi",
    )
