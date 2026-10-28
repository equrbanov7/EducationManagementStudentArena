"""Strictly read-only structural journal gates, without creating missing schemes.

No network decision, cell/time-window permission, or guarantee of UI access is
claimed. Calling context must already establish the correct tenant/RLS scope.
"""

from django.contrib.auth import get_user_model

from apps.syllabus import public as syllabus_public

from .gradebook import assessment_scheme_is_locked
from .integrity import is_authorized_instructor
from .journal_access import is_direct_editor, offering_accepts_writes
from .journal_policy import require_approved_syllabus
from .journal_shares import journal_scope
from .models import AssessmentScheme


def journal_access_diagnostics(*, offering, teacher_ids):
    """Return scalar metadata for explicit candidate teachers of one offering."""
    organization = offering.organization
    scheme = AssessmentScheme.objects.filter(organization=organization, offering=offering).first()
    locked = assessment_scheme_is_locked(scheme) if scheme is not None else None
    syllabus = syllabus_public.syllabus_for_offering(
        organization=organization,
        offering_id=offering.pk,
        subject_id=offering.subject_id,
        period_id=offering.period_id,
        instructor_id=offering.instructor_id,
        _metadata_only=True,
    )
    version = syllabus_public.approved_version_for(syllabus, metadata_only=True)
    enforced = require_approved_syllabus(organization)
    syllabus_locked = enforced and version is None
    users = get_user_model().objects.filter(pk__in=teacher_ids).only("id", "is_active", "is_superuser")
    results = []
    for user in users.order_by("pk"):
        # The same organization-bound role context used by request middleware;
        # role checks never fall back to legacy profile data.
        user.set_active_organization_context(organization)
        authorized = is_authorized_instructor(organization=organization, instructor=user)
        direct = is_direct_editor(user, offering)
        scope = journal_scope(user, offering)
        blockers = []
        if not user.is_active:
            blockers.append("inactive_account")
        if not offering_accepts_writes(offering):
            blockers.append("offering_inactive")
        if not direct:
            blockers.append("not_direct_editor")
        if locked:
            blockers.append("journal_closed")
        if syllabus_locked:
            blockers.append("approved_syllabus_required")
        unknown = ["network_request_not_checked", "lesson_cell_time_windows_not_checked", "browser_ui_not_checked"]
        if locked is None:
            unknown.append("assessment_scheme_missing_no_creation_attempted")
        results.append(
            {
                "teacher_id": user.pk,
                "offering_id": str(offering.pk),
                "user_active": user.is_active,
                "user_grade_input": authorized,
                "user_is_instructor": user.pk == offering.instructor_id,
                "direct_editor": direct,
                "share_full": scope.full,
                "share_kind_restricted": scope.kinds is not None,
                "share_row_restricted": scope.enrollment_ids is not None,
                "share_can_manage_scores": scope.can_manage_scores,
                "journal_locked": locked,
                "period_locked": bool(getattr(offering.period, "locked_at", None)),
                "syllabus_id": str(syllabus.pk) if syllabus else None,
                "approved_syllabus_version_id": str(version.pk) if version else None,
                "syllabus_enforced": enforced,
                "syllabus_locked": syllabus_locked,
                "structural_write_candidate": False if blockers else None if locked is None else True,
                "runtime_write_verified": False,
                "blocker_codes": blockers,
                "unknown_codes": unknown,
            }
        )
    return results
