"""Qiymət təsdiq zənciri — grade-approval chain (U7.2).

The electronic journal moves through a multi-step approval workflow before grades
become official:

    DRAFT ─submit→ SUBMITTED ─chair_approve→ CHAIR_APPROVED ─dean_approve→ APPROVED
      ▲                │                          │
      └──── return_for_revision ◄─────────────────┘   (→ RETURNED → back to DRAFT on next submit)

* The teacher edits freely in DRAFT/RETURNED, then *submits* the journal.
* The kafedra müdiri (chair / department head) reviews and either approves or
  returns it for revision.
* The dekan (dean) gives the final approval, which publishes the journal
  (``is_published=True`` — transcript-ready) and locks it permanently.

While a journal is SUBMITTED / CHAIR_APPROVED / APPROVED it is locked against
mark edits (see :func:`apps.registrar.gradebook.journal_is_locked`).
"""

from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from apps.registrar import gradebook
from apps.registrar.models import ApprovalStatus

# Roles that may act as chair (kafedra müdiri) / dean (dekan). Organisation
# owner + admin roles can always act (small-org / bootstrap convenience).
_ADMIN_ROLES = frozenset({"org_admin", "org_owner", "rector", "vice_rector"})
_CHAIR_ROLES = _ADMIN_ROLES | {"department_head", "chair_head", "dean"}
_DEAN_ROLES = _ADMIN_ROLES | {"dean"}


def _has_role(user, organization, role_names) -> bool:
    from django.apps import apps as django_apps

    if getattr(user, "is_superuser", False) or organization.owner_id == getattr(user, "pk", None):
        return True
    Membership = django_apps.get_model("organizations", "Membership")
    return Membership.objects.filter(
        organization=organization, user=user, is_active=True, role__name__in=list(role_names)
    ).exists()


def can_submit(user, offering) -> bool:
    """Instructor (or org owner/superuser) may submit for approval."""
    return (
        getattr(user, "is_superuser", False)
        or offering.instructor_id == getattr(user, "pk", None)
        or offering.organization.owner_id == getattr(user, "pk", None)
    )


def can_chair_approve(user, organization) -> bool:
    return _has_role(user, organization, _CHAIR_ROLES)


def can_dean_approve(user, organization) -> bool:
    return _has_role(user, organization, _DEAN_ROLES)


def _audit(offering, by_user, action_label, reason):
    """Best-effort audit trail entry (never blocks the domain action)."""
    try:
        from django.apps import apps as django_apps

        from core.constants import AuditAction

        AuditLog = django_apps.get_model("audit", "AuditLog")
        AuditLog.objects.create(
            user=by_user if getattr(by_user, "pk", None) else None,
            organization=offering.organization,
            action=AuditAction.UPDATE,
            resource_type="registrar.journal_approval",
            resource_id=str(offering.pk),
            resource_repr=f"{offering.subject.code} jurnalı — {action_label}",
            reason=reason,
        )
    except Exception:  # noqa: BLE001 — audit must never block the domain action
        pass


@transaction.atomic
def submit_for_approval(*, offering, by_user):
    """Teacher submits the journal → SUBMITTED (awaiting chair). Locks edits."""
    if not can_submit(by_user, offering):
        raise PermissionDenied("Bu jurnalı təqdim etmək icazəniz yoxdur.")
    scheme = gradebook.ensure_assessment_scheme(offering=offering)
    if scheme.is_published or scheme.approval_status not in (ApprovalStatus.DRAFT, ApprovalStatus.RETURNED):
        return scheme
    scheme.approval_status = ApprovalStatus.SUBMITTED
    scheme.submitted_by = by_user
    scheme.returned_reason = ""
    scheme.save(update_fields=["approval_status", "submitted_by", "returned_reason", "updated_at"])
    _audit(offering, by_user, "təqdim edildi", "Jurnal təsdiq üçün təqdim olundu (kafedra gözlənilir).")
    return scheme


@transaction.atomic
def chair_approve(*, offering, by_user):
    """Kafedra müdiri approves → CHAIR_APPROVED (awaiting dean)."""
    scheme = gradebook.ensure_assessment_scheme(offering=offering)
    if not can_chair_approve(by_user, offering.organization):
        raise PermissionDenied("Kafedra təsdiqi üçün icazəniz yoxdur.")
    if scheme.approval_status != ApprovalStatus.SUBMITTED:
        return scheme
    scheme.approval_status = ApprovalStatus.CHAIR_APPROVED
    scheme.chair_approved_by = by_user
    scheme.save(update_fields=["approval_status", "chair_approved_by", "updated_at"])
    _audit(offering, by_user, "kafedra təsdiqi", "Kafedra müdiri jurnalı təsdiqlədi (dekan gözlənilir).")
    return scheme


@transaction.atomic
def dean_approve(*, offering, by_user):
    """Dekan gives final approval → APPROVED + publishes (locks permanently)."""
    scheme = gradebook.ensure_assessment_scheme(offering=offering)
    if not can_dean_approve(by_user, offering.organization):
        raise PermissionDenied("Dekan təsdiqi üçün icazəniz yoxdur.")
    if scheme.approval_status != ApprovalStatus.CHAIR_APPROVED:
        return scheme
    scheme.approval_status = ApprovalStatus.APPROVED
    scheme.dean_approved_by = by_user
    scheme.is_published = True
    scheme.save(update_fields=["approval_status", "dean_approved_by", "is_published", "updated_at"])
    _audit(offering, by_user, "dekan təsdiqi", "Dekan jurnalı təsdiqlədi — qiymətlər rəsmiləşdi (finalizasiya).")
    return scheme


@transaction.atomic
def return_for_revision(*, offering, by_user, reason=""):
    """Chair/dean returns the journal to the teacher → RETURNED (edits re-open)."""
    scheme = gradebook.ensure_assessment_scheme(offering=offering)
    if not can_chair_approve(by_user, offering.organization):
        raise PermissionDenied("Jurnalı geri qaytarmaq üçün icazəniz yoxdur.")
    if scheme.approval_status not in (ApprovalStatus.SUBMITTED, ApprovalStatus.CHAIR_APPROVED):
        return scheme
    scheme.approval_status = ApprovalStatus.RETURNED
    scheme.returned_reason = (reason or "").strip()[:1000]
    scheme.is_published = False
    scheme.save(update_fields=["approval_status", "returned_reason", "is_published", "updated_at"])
    _audit(
        offering,
        by_user,
        "geri qaytarıldı",
        f"Jurnal düzəliş üçün geri qaytarıldı. Səbəb: {scheme.returned_reason or '—'}",
    )
    return scheme


def approval_context(*, offering, user):
    """Status + capability flags for the journal-detail action bar."""
    scheme = gradebook.ensure_assessment_scheme(offering=offering)
    status = scheme.approval_status
    return {
        "status": status,
        "status_label": ApprovalStatus(status).label,
        "is_locked": gradebook.journal_is_locked(offering),
        "returned_reason": scheme.returned_reason,
        "can_submit": can_submit(user, offering) and status in (ApprovalStatus.DRAFT, ApprovalStatus.RETURNED),
        "can_chair_approve": can_chair_approve(user, offering.organization) and status == ApprovalStatus.SUBMITTED,
        "can_dean_approve": can_dean_approve(user, offering.organization) and status == ApprovalStatus.CHAIR_APPROVED,
        "can_return": can_chair_approve(user, offering.organization)
        and status in (ApprovalStatus.SUBMITTED, ApprovalStatus.CHAIR_APPROVED),
        "submitted_at": scheme.updated_at if status != ApprovalStatus.DRAFT else None,
        "now": timezone.now(),
    }
