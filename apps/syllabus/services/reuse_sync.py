"""Bağlı sillabusların SİNXRONU — «Bağlı sillabuslara tətbiq et», «Mənbədən yenilə», «Ayır».

``reuse.py``-dan ayrılıb (modul ölçüsü büdcəsi).  Qərarlar (əl ilə sinxron, ayırmada
təsdiqlənmiş nüsxənin qalması) :mod:`.reuse` modul docstring-indədir (qərar 4–5).
"""

from __future__ import annotations

from django.db import transaction

from core.audit import log_action
from core.constants import AuditAction

from ..constants import OPEN_STATUSES, PERM_EDIT
from ..models import ChangeKind, Syllabus
from ..state_machine import TransitionDenied
from . import reuse_rules as rules
from .reuse import _approve_as_reuse, _denied, _new_draft
from .scoping import is_author


def is_behind(target) -> bool:
    """Bağlı hədəf mənbənin QÜVVƏDƏ olan təsdiqindən geri qalıbmı."""
    if target is None or not target.reused_from_id:
        return False
    base = rules.link_base(target.reused_from)
    current = target.approved_version
    return base is not None and (current is None or current.source_version_id != base.pk)


def linked_summary(sources) -> dict:
    """``{mənbə_id: {"linked": n, "behind": m}}`` — səhifə üçün TƏK sorğu."""
    by_id = {row.pk: row for row in sources}
    if not by_id:
        return {}
    summary: dict = {}
    pairs = Syllabus.objects.filter(reused_from_id__in=list(by_id), is_active=True).values_list(
        "reused_from_id", "approved_version__source_version_id"
    )
    for source_id, mirrored in pairs:
        entry = summary.setdefault(source_id, {"linked": 0, "behind": 0})
        entry["linked"] += 1
        base = rules.link_base(by_id[source_id])
        if base is not None and mirrored != base.pk:
            entry["behind"] += 1
    return summary


@transaction.atomic
def sync_from_source(*, target_syllabus, actor, plan_hours=None, request=None):
    """Bağlı hədəfi mənbənin YENİ təsdiqlənmiş versiyasına çəkir (qərar 4 — əl ilə)."""
    target = (
        Syllabus.objects.select_for_update(of=("self",))
        .select_related("offering", "reused_from", "reused_from__approved_version", "approved_version")
        .get(pk=target_syllabus.pk)
    )
    if not target.reused_from_id:
        raise _denied(rules.CODE_NOT_LINKED)
    if not actor.has(PERM_EDIT):
        raise _denied("transition.permission_denied", permission=PERM_EDIT)
    if not is_author(actor, target):
        raise _denied("transition.author_only", transition="reuse_sync")
    source = target.reused_from
    current = target.approved_version
    hours = rules.normalize_hours(plan_hours) or rules.normalize_hours(getattr(current, "plan_hours", None))
    open_exists = target.versions.filter(status__in=sorted(OPEN_STATUSES)).exists()
    code = rules.link_code(
        source,
        actor=actor,
        target_hours=hours,
        target_chair_unit_id=rules.effective_chair_unit_id(target),
        target_code=rules.CODE_TARGET_LOCKED if open_exists else "",
    )
    if code:
        raise _denied(code)
    base = rules.link_base(source)
    if current is not None and current.source_version_id == base.pk:
        raise _denied(rules.CODE_UP_TO_DATE)
    previous = current.source_version if current is not None and current.source_version_id else None
    draft = _new_draft(
        target,
        actor=actor,
        plan_hours=hours,
        bump_major=previous is not None and base.major > previous.major,
        request=request,
    )
    return _approve_as_reuse(
        draft, syllabus=target, source=source, base=base, actor=actor, plan_hours=hours, request=request
    )


def propagate(*, source, actor, hours_for=None, request=None) -> list:
    """«Bağlı sillabuslara tətbiq et» — mənbə müəllifinin əməli; hər hədəf ayrıca SAVEPOINT."""
    if not is_author(actor, source):
        raise _denied("transition.out_of_scope", transition="reuse_propagate")
    targets = Syllabus.objects.filter(
        organization_id=source.organization_id, reused_from=source, is_active=True
    ).select_related("offering", "chair_unit", "approved_version")
    results = []
    for target in targets:
        entry = {"syllabus": str(target.pk), "offering": str(target.offering_id or ""), "version": "", "code": ""}
        try:
            with transaction.atomic():
                version = sync_from_source(
                    target_syllabus=target,
                    actor=actor,
                    plan_hours=hours_for(target) if hours_for is not None else None,
                    request=request,
                )
            entry.update(status="synced", version=str(version.pk))
        except TransitionDenied as denied:
            entry.update(status="already" if denied.code == rules.CODE_UP_TO_DATE else "skipped", code=denied.code)
        results.append(entry)
    return results


@transaction.atomic
def unlink(*, target_syllabus, actor, request=None):
    """«Ayır» — bağ silinir, redaktə üçün müstəqil QARALAMA açılır (qərar 5)."""
    from .drafts import create_next_version, open_version_for

    target = Syllabus.objects.select_for_update(of=("self",)).select_related("offering").get(pk=target_syllabus.pk)
    if not target.reused_from_id:
        raise _denied(rules.CODE_NOT_LINKED)
    if not actor.has(PERM_EDIT):
        raise _denied("transition.permission_denied", permission=PERM_EDIT)
    if not is_author(actor, target):
        raise _denied("transition.author_only", transition="reuse_unlink")
    source_id = target.reused_from_id
    Syllabus.objects.filter(pk=target.pk).update(reused_from=None)
    target.reused_from = None
    version = open_version_for(target)
    if version is None and target.approved_version_id is not None:
        version = create_next_version(syllabus=target, actor=actor, kind=ChangeKind.MINOR.value, request=request)
    log_action(
        AuditAction.UPDATE,
        user=actor.user,
        organization=target.organization,
        obj=target,
        request=request,
        resource_type="syllabus.syllabus",
        resource_id=str(target.pk),
        resource_repr=f"{target.subject_id} {target.period_id}",
        old_values={"reused_from": str(source_id)},
        new_values={"reused_from": None, "draft_version": version.label if version is not None else ""},
        changes={"reuse": "unlink"},
    )
    target_syllabus.reused_from = None
    return version


__all__ = ["is_behind", "linked_summary", "propagate", "sync_from_source", "unlink"]
