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


def offering_in_actor_scope(user, organization, offering) -> bool:
    """Təsdiqləyənin unit alt-ağacı bu dərs açılışını əhatə edirmi.

    TƏHLÜKƏSİZLİK (2026-07-31 auditi): ``can_chair_approve`` / ``can_dean_approve``
    yalnız rol ADINA baxırdı və offering-in hansı kafedraya/fakültəyə aid
    olduğunu yoxlamırdı. Nəticədə A kafedrasının müdiri B kafedrasının jurnalını
    təsdiqləyə (və dekan təsdiqi ilə ƏBƏDİ kilidləyə) bilirdi.

    Org-wide rollar (owner/admin/rektorat/superuser) həmişə keçir — onların
    səlahiyyəti onsuz da bütün təşkilatı əhatə edir.

    QAYDA: yoxlama YALNIZ istifadəçiyə unit scope-u TƏYİN OLUNUBSA tətbiq edilir.
    Scope-u olmayan kafedra müdiri/dekan köhnə davranışı saxlayır — əks halda
    strukturu hələ qurmamış təşkilatlarda bütün təsdiq zənciri dayanardı. Yəni
    bu, mövcud icazəni daraltmır, düzgün qurulmuş iyerarxiyada isə kənar unitin
    jurnalını bağlayır.

    QALIQ RİSK (sənədləşdirilir): ``scope_unit`` təyin edilməmiş kafedra müdiri
    hələ də bütün təşkilatın jurnallarını təsdiqləyə bilir. Bu, provisionlaşdırma
    məsələsidir — struktur qurulandan sonra hər idarəetmə üzvlüyünə ``scope_unit``
    verilməlidir.

    MODUL SƏRHƏDİ: registrar ``apps.organizations``-u Python səviyyəsində import
    ETMİR (dövr yaranardı) — model app registry ilə həll olunur, alt-ağac
    yoxlaması isə ``OrgUnit.user_scope_covers`` daxilində, öz modulundadır.
    """
    from django.apps import apps as django_apps

    if getattr(user, "is_superuser", False) or organization.owner_id == getattr(user, "pk", None):
        return True
    if _has_role(user, organization, _ADMIN_ROLES):
        return True

    org_unit_model = django_apps.get_model("organizations", "OrgUnit")
    return org_unit_model.user_scope_covers(user, organization, getattr(offering, "group_id", None))


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
    if not _has_role(user, organization, _CHAIR_ROLES):
        return False
    if offering is None:
        return True
    return offering_in_actor_scope(user, organization, offering)


def can_dean_approve(user, organization, offering=None) -> bool:
    if not _has_role(user, organization, _DEAN_ROLES):
        return False
    if offering is None:
        return True
    return offering_in_actor_scope(user, organization, offering)


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
    scheme = gradebook.ensure_assessment_scheme(offering=offering)
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
    scheme = gradebook.ensure_assessment_scheme(offering=offering)
    if not can_chair_approve(by_user, offering.organization, offering=offering):
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
