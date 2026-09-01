"""State maşınının İCRASI — bütün status keçidləri BURADAN keçir.

View qatı heç bir yerdə ``version.status = ...`` yazmır: o, buradakı funksiyanı
çağırır, funksiya isə :mod:`apps.syllabus.state_machine`-dən icazə alır. Beləliklə
qayda bir yerdə qalır və HTTP səthi artsa da pozula bilmir.

Hər keçid: (1) state maşını yoxlaması → (2) atomik DB yazısı → (3) domen qeydi
(``SyllabusReview``) → (4) mövcud audit jurnalına (``audit_auditlog``) yazı.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from ..constants import (
    PERM_APPROVE,
    PERM_MANAGE,
    PERM_REJECT,
    PERM_REVIEW,
    PERM_REVISE,
    SyllabusStatus,
)
from ..models import ApprovalSource, ReviewDecision, Syllabus, SyllabusReview, SyllabusVersion
from ..state_machine import Transition, TransitionDenied, check
from .drafts import recompute_completion, refresh_pointers
from .scoping import is_author

#: Keçid → domen qeydinin qərar dəyəri.
_DECISION_BY_TRANSITION = {
    Transition.SUBMIT: ReviewDecision.SUBMITTED.value,
    Transition.WITHDRAW: ReviewDecision.WITHDRAWN.value,
    Transition.START_REVIEW: ReviewDecision.OPENED.value,
    Transition.APPROVE: ReviewDecision.APPROVED.value,
    Transition.REQUEST_REVISION: ReviewDecision.REVISION.value,
    Transition.REJECT: ReviewDecision.REJECTED.value,
}

#: Kafedra tərəfindən icra olunan keçidlərdə əhatə hansı icazə üzrə yoxlanılır.
_SCOPE_PERMISSION = {
    Transition.START_REVIEW: PERM_REVIEW,
    Transition.APPROVE: PERM_APPROVE,
    Transition.REQUEST_REVISION: PERM_REVISE,
    Transition.REJECT: PERM_REJECT,
    Transition.ARCHIVE: PERM_MANAGE,
}


def _in_scope(actor, syllabus, name: str) -> bool:
    """Müəllif öz sillabusunda həmişə «əhatədədir»; kafedra tərəfi scope ilə."""
    permission = _SCOPE_PERMISSION.get(name)
    if permission is None:
        return is_author(actor, syllabus)
    return actor.covers_unit(syllabus.chair_unit_id, permission)


def _guard(*, version, actor, name: str, reason: str = ""):
    syllabus = version.syllabus
    return check(
        name=name,
        status=version.status,
        permissions=actor.permissions if not actor.is_superadmin else ["*"],
        reason=reason,
        is_author=is_author(actor, syllabus),
        completion_percent=version.completion_percent,
        in_scope=_in_scope(actor, syllabus, name),
    )


def _record(*, version, actor, name: str, reason: str, comment: str, section_comments):
    decision = _DECISION_BY_TRANSITION.get(name)
    if decision is None:
        return None
    return SyllabusReview.objects.create(
        organization_id=version.organization_id,
        version=version,
        decision=decision,
        reason=reason or "",
        comment=comment or "",
        section_comments=dict(section_comments or {}),
        actor=actor.user,
    )


def _audit(*, version, actor, name: str, old_status: str, reason: str, request):
    log_action(
        AuditAction.UPDATE,
        user=actor.user,
        organization=version.organization,
        obj=version,
        request=request,
        resource_type="syllabus.version",
        resource_id=str(version.pk),
        resource_repr=f"{version.syllabus_id} {version.label}",
        old_values={"status": old_status},
        new_values={"status": version.status},
        changes={"transition": name},
        reason=reason or "",
    )


def _apply(
    *,
    version,
    actor,
    name: str,
    reason="",
    comment="",
    section_comments=None,
    request=None,
    before_save=None,
    **updates,
):
    """Ortaq icra gövdəsi: yoxla → (hazırlıq) → yaz → qeyd et → audit.

    ``before_save`` yoxlamadan SONRA, yazıdan ƏVVƏL, EYNİ tranzaksiyada işləyir —
    təsdiq zamanı köhnə APPROVED versiyanın arxivlənməsi məhz burada baş verir,
    əks halda ``uniq_syllabus_approved_version`` məhdudiyyəti pozulardı.
    """
    with transaction.atomic():
        locked = SyllabusVersion.objects.select_for_update(of=("self",)).get(pk=version.pk)
        locked.syllabus = version.syllabus
        rule = _guard(version=locked, actor=actor, name=name, reason=reason)
        old_status = locked.status
        if before_save is not None:
            before_save(locked)
        locked.status = rule.target
        for field, value in updates.items():
            setattr(locked, field, value)
        locked.save()
        _record(
            version=locked,
            actor=actor,
            name=name,
            reason=reason,
            comment=comment,
            section_comments=section_comments,
        )
        _audit(version=locked, actor=actor, name=name, old_status=old_status, reason=reason, request=request)
    return locked


def submit(*, version, actor, request=None):
    """DRAFT/REVISION → SUBMITTED. Versiya kilidlənir."""
    recompute_completion(version)
    version.refresh_from_db(fields=["completion_percent"])
    now = timezone.now()
    updated = _apply(
        version=version,
        actor=actor,
        name=Transition.SUBMIT,
        request=request,
        submitted_at=now,
        submitted_by=actor.user,
        locked_at=now,
        decision_reason="",
        reviewer=None,
        review_started_at=None,
    )
    Syllabus.objects.filter(pk=updated.syllabus_id).update(current_version=updated)
    return updated


def withdraw(*, version, actor, reason: str, request=None):
    """SUBMITTED/REVIEW → DRAFT. Səbəb MƏCBURİDİR (README §3.1 dialoqu)."""
    return _apply(
        version=version,
        actor=actor,
        name=Transition.WITHDRAW,
        reason=reason,
        request=request,
        submitted_at=None,
        submitted_by=None,
        review_started_at=None,
        reviewer=None,
        locked_at=None,
    )


def start_review(*, version, actor, request=None):
    """SUBMITTED → REVIEW (kafedra müdiri təsdiq növbəsindən açır)."""
    return _apply(
        version=version,
        actor=actor,
        name=Transition.START_REVIEW,
        request=request,
        review_started_at=timezone.now(),
        reviewer=actor.user,
    )


def approve(*, version, actor, comment: str = "", section_comments=None, request=None):
    """SUBMITTED/REVIEW → APPROVED. Versiya ƏBƏDİ kilidlənir.

    Köhnə təsdiqlənmiş versiya bu anda ARXİVLƏNİR və dosyenin
    ``approved_version`` göstəricisi yenisinə keçir.
    """
    now = timezone.now()

    def _supersede(locked):
        _archive_superseded(locked, actor=actor, request=request, now=now)

    updated = _apply(
        version=version,
        actor=actor,
        name=Transition.APPROVE,
        comment=comment,
        section_comments=section_comments,
        request=request,
        before_save=_supersede,
        approved_at=now,
        approved_by=actor.user,
        approval_source=ApprovalSource.HUMAN,
        decided_at=now,
        locked_at=now,
        decision_reason="",
    )
    Syllabus.objects.filter(pk=updated.syllabus_id).update(approved_version=updated, current_version=updated)
    return updated


def request_revision(*, version, actor, reason: str, comment: str = "", section_comments=None, request=None):
    """SUBMITTED/REVIEW → REVISION. Səbəb MƏCBURİDİR (DB check ilə də)."""
    return _apply(
        version=version,
        actor=actor,
        name=Transition.REQUEST_REVISION,
        reason=reason,
        comment=comment,
        section_comments=section_comments,
        request=request,
        decided_at=timezone.now(),
        decision_reason=reason,
        locked_at=None,
    )


def reject(*, version, actor, reason: str, comment: str = "", section_comments=None, request=None):
    """SUBMITTED/REVIEW → REJECTED. Səbəb MƏCBURİDİR (DB check ilə də)."""
    return _apply(
        version=version,
        actor=actor,
        name=Transition.REJECT,
        reason=reason,
        comment=comment,
        section_comments=section_comments,
        request=request,
        decided_at=timezone.now(),
        decision_reason=reason,
    )


def resume_editing(*, version, actor, request=None):
    """REVISION → DRAFT (müəllim düzəlişə başlayır)."""
    return _apply(
        version=version,
        actor=actor,
        name=Transition.RESUME_EDITING,
        request=request,
        locked_at=None,
        decision_reason="",
    )


def archive(*, version, actor, request=None):
    """APPROVED → ARCHIVED (əl ilə; adətən sistem yeni təsdiqdə çağırır).

    Arxivlənən versiya adətən dosyenin ``current_version``/``approved_version``
    göstəricisidir — ``approve`` onu məhz oraya yazmışdı.  Göstəricini olduğu
    kimi qoymaq dosyeni «Arxivlənib» kimi dondurardı, ona görə keçiddən sonra
    göstəricilər statusa görə YENİDƏN həll olunur.
    """
    updated = _apply(
        version=version,
        actor=actor,
        name=Transition.ARCHIVE,
        request=request,
        archived_at=timezone.now(),
    )
    refresh_pointers(updated.syllabus)
    return updated


def _archive_superseded(new_version, *, actor, request=None, now=None):
    """Yeni versiya təsdiqlənəndə köhnə APPROVED-ları arxivləyir."""
    stale = SyllabusVersion.objects.filter(syllabus_id=new_version.syllabus_id, status=SyllabusStatus.APPROVED).exclude(
        pk=new_version.pk
    )
    now = now or timezone.now()
    for old in stale:
        old_status = old.status
        old.status = SyllabusStatus.ARCHIVED
        old.archived_at = now
        old.save(update_fields=["status", "archived_at", "updated_at"])
        log_action(
            AuditAction.UPDATE,
            user=actor.user,
            organization=old.organization,
            obj=old,
            request=request,
            resource_type="syllabus.version",
            resource_id=str(old.pk),
            resource_repr=f"{old.syllabus_id} {old.label}",
            old_values={"status": old_status},
            new_values={"status": old.status},
            changes={"transition": Transition.ARCHIVE, "superseded_by": new_version.label},
        )


def available_actions(*, version, actor) -> tuple:
    """Aktorun bu versiyada icra edə biləcəyi keçidlər (UI düymələri üçün)."""
    names = []
    for name in (
        Transition.SUBMIT,
        Transition.WITHDRAW,
        Transition.START_REVIEW,
        Transition.APPROVE,
        Transition.REQUEST_REVISION,
        Transition.REJECT,
        Transition.RESUME_EDITING,
        Transition.ARCHIVE,
    ):
        try:
            _guard(version=version, actor=actor, name=name, reason="probe")
        except TransitionDenied:
            continue
        names.append(name)
    return tuple(names)


__all__ = [
    "approve",
    "archive",
    "available_actions",
    "reject",
    "request_revision",
    "resume_editing",
    "start_review",
    "submit",
    "withdraw",
]
