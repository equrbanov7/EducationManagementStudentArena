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
from apps.registrar.models import ApprovalStatus, AssessmentScheme

CHAIR_APPROVAL_PERMISSION = "grade.approve_chair"
FINAL_APPROVAL_PERMISSION = "grade.approve_final"


def _permission_scope(user, organization, permission):
    from django.apps import apps as django_apps

    org_unit_model = django_apps.get_model("organizations", "OrgUnit")
    return org_unit_model.user_permission_scope(user, organization, permission)


def offering_in_actor_scope(user, organization, offering, *, permission=CHAIR_APPROVAL_PERMISSION) -> bool:
    """Təsdiqləyənin unit alt-ağacı bu dərs açılışını əhatə edirmi.

    TƏHLÜKƏSİZLİK (2026-07-31 auditi): ``can_chair_approve`` / ``can_dean_approve``
    yalnız rol ADINA baxırdı və offering-in hansı kafedraya/fakültəyə aid
    olduğunu yoxlamırdı. Nəticədə A kafedrasının müdiri B kafedrasının jurnalını
    təsdiqləyə (və dekan təsdiqi ilə ƏBƏDİ kilidləyə) bilirdi.

    İcazə rol adından deyil, rolun mərkəzi permission tərifindən gəlir. UNIT
    rolunda etibarlı ``scope_unit`` yoxdursa nəticə fail-closed-dur.

    MODUL SƏRHƏDİ: registrar ``apps.organizations``-u Python səviyyəsində import
    ETMİR (dövr yaranardı) — model app registry ilə həll olunur, alt-ağac
    yoxlaması isə ``OrgUnit.user_scope_covers`` daxilində, öz modulundadır.
    """
    scope = _permission_scope(user, organization, permission)
    if not scope.has_structure_access:
        return False
    if scope.is_org_wide:
        return True
    group_id = getattr(offering, "group_id", None)
    if group_id is None:
        return False
    from django.apps import apps as django_apps

    org_unit_model = django_apps.get_model("organizations", "OrgUnit")
    return org_unit_model.objects.filter(organization=organization, pk=group_id).filter(scope.unit_subtree_q()).exists()


def permission_scope_q(user, organization, permission, *, path_field, id_field):
    """Fail-closed queryset filter for one permission's structural scope."""
    return _permission_scope(user, organization, permission).unit_subtree_q(
        path_field=path_field,
        id_field=id_field,
    )


def can_view_analytics(user, organization) -> bool:
    return bool(_analytics_scopes(user, organization))


def _analytics_scopes(user, organization):
    all_scope = _permission_scope(user, organization, "analytics.view_all")
    unit_scope = _permission_scope(user, organization, "analytics.view_unit")
    scopes = [all_scope] if all_scope.has_structure_access else []
    if unit_scope.has_structure_access:
        scopes.append(unit_scope)
    return scopes


def analytics_scope_q(user, organization, *, path_field, id_field):
    scopes = _analytics_scopes(user, organization)
    if any(scope.is_org_wide for scope in scopes):
        from django.db.models import Q

        return Q()
    if not scopes:
        from django.db.models import Q

        return Q(pk__in=[])
    query = scopes[0].unit_subtree_q(path_field=path_field, id_field=id_field)
    for scope in scopes[1:]:
        query |= scope.unit_subtree_q(path_field=path_field, id_field=id_field)
    return query


def can_submit(user, offering) -> bool:
    """Instructor (or org owner/superuser) may submit for approval."""
    return (
        getattr(user, "is_superuser", False)
        or offering.instructor_id == getattr(user, "pk", None)
        or offering.organization.owner_id == getattr(user, "pk", None)
    )


def can_chair_approve(user, organization, offering=None) -> bool:
    """Kafedra müdiri təsdiqi.

    ``offering`` verilirsə unit aidiyyəti də yoxlanılır (bax
    :func:`offering_in_actor_scope`). Səhifə-səviyyə görünürlük yoxlamaları
    (məs. analitika paneli) offering-siz çağırır — orada konkret jurnal yoxdur.
    """
    if offering is None:
        return _permission_scope(user, organization, CHAIR_APPROVAL_PERMISSION).has_structure_access
    return offering_in_actor_scope(user, organization, offering, permission=CHAIR_APPROVAL_PERMISSION)


def can_dean_approve(user, organization, offering=None) -> bool:
    if offering is None:
        return _permission_scope(user, organization, FINAL_APPROVAL_PERMISSION).has_structure_access
    return offering_in_actor_scope(user, organization, offering, permission=FINAL_APPROVAL_PERMISSION)


def _locked_scheme(offering):
    scheme = gradebook.ensure_assessment_scheme(offering=offering)
    return AssessmentScheme.objects.select_for_update().get(pk=scheme.pk)


def _audit(offering, by_user, action_label, reason):
    """Write the mandatory audit row in the transition's transaction."""
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


@transaction.atomic
def submit_for_approval(*, offering, by_user):
    """Teacher submits the journal → SUBMITTED (awaiting chair). Locks edits."""
    if not can_submit(by_user, offering):
        raise PermissionDenied("Bu jurnalı təqdim etmək icazəniz yoxdur.")
    scheme = _locked_scheme(offering)
    if scheme.is_published or scheme.approval_status not in (ApprovalStatus.DRAFT, ApprovalStatus.RETURNED):
        return scheme
    scheme.approval_status = ApprovalStatus.SUBMITTED
    scheme.submitted_by = by_user
    scheme.chair_approved_by = None
    scheme.dean_approved_by = None
    scheme.is_published = False
    scheme.returned_reason = ""
    scheme.save(
        update_fields=[
            "approval_status",
            "submitted_by",
            "chair_approved_by",
            "dean_approved_by",
            "is_published",
            "returned_reason",
            "updated_at",
        ]
    )
    _audit(offering, by_user, "təqdim edildi", "Jurnal təsdiq üçün təqdim olundu (kafedra gözlənilir).")
    return scheme


@transaction.atomic
def chair_approve(*, offering, by_user):
    """Kafedra müdiri approves → CHAIR_APPROVED (awaiting dean)."""
    scheme = _locked_scheme(offering)
    if not can_chair_approve(by_user, offering.organization, offering=offering):
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
    scheme = _locked_scheme(offering)
    if not can_dean_approve(by_user, offering.organization, offering=offering):
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
    scheme = _locked_scheme(offering)
    if not can_chair_approve(by_user, offering.organization, offering=offering):
        raise PermissionDenied("Jurnalı geri qaytarmaq üçün icazəniz yoxdur.")
    if scheme.approval_status not in (ApprovalStatus.SUBMITTED, ApprovalStatus.CHAIR_APPROVED):
        return scheme
    scheme.approval_status = ApprovalStatus.RETURNED
    scheme.returned_reason = (reason or "").strip()[:1000]
    scheme.chair_approved_by = None
    scheme.dean_approved_by = None
    scheme.is_published = False
    scheme.save(
        update_fields=[
            "approval_status",
            "returned_reason",
            "chair_approved_by",
            "dean_approved_by",
            "is_published",
            "updated_at",
        ]
    )
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
    # Scope yoxlaması bir dəfə hesablanır (üç bayraq eyni nəticəni paylaşır).
    chair_ok = can_chair_approve(user, offering.organization, offering=offering)
    dean_ok = can_dean_approve(user, offering.organization, offering=offering)
    return {
        "status": status,
        "status_label": ApprovalStatus(status).label,
        "is_locked": gradebook.journal_is_locked(offering),
        "returned_reason": scheme.returned_reason,
        "can_submit": can_submit(user, offering) and status in (ApprovalStatus.DRAFT, ApprovalStatus.RETURNED),
        "can_chair_approve": chair_ok and status == ApprovalStatus.SUBMITTED,
        "can_dean_approve": dean_ok and status == ApprovalStatus.CHAIR_APPROVED,
        "can_return": chair_ok and status in (ApprovalStatus.SUBMITTED, ApprovalStatus.CHAIR_APPROVED),
        "submitted_at": scheme.updated_at if status != ApprovalStatus.DRAFT else None,
        "now": timezone.now(),
    }
