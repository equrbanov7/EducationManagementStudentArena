"""«Kopyala» əməlinin MÖVCUD dosyeyə yazılması (QA 2026-09-05 P2-20).

Ayrı modul: `drafts.py` 600 sətir büdcəsinin həddindədir.
"""

from __future__ import annotations

from django.db import transaction

from core.audit import log_action
from core.constants import AuditAction

from ..constants import OPEN_STATUSES, PERM_EDIT, SyllabusStatus
from ..models import ChangeKind, Syllabus, SyllabusSection, SyllabusVersion
from ..state_machine import TransitionDenied
from .scoping import is_author


def copy_into_existing(target, *, base, actor, request=None):
    """Mövcud dosyeyə köçürmə: növbəti minor qaralama + mənbənin bölmələri."""
    from .drafts import recompute_completion

    latest = target.versions.order_by("-major", "-minor").first()
    major, minor = (latest.major, latest.minor + 1) if latest is not None else (1, 0)
    version = SyllabusVersion.objects.create(
        organization=target.organization,
        syllabus=target,
        major=major,
        minor=minor,
        status=SyllabusStatus.DRAFT,
        change_kind=ChangeKind.COPIED,
        applies_to_period=target.period,
        source_version=base,
        plan_hours=dict(base.plan_hours or {}),
        created_by=actor.user,
    )
    # `_create_sections` `drafts`-dədir; dövri idxaldan qaçmaq üçün çağırış vaxtı.
    # `_create_sections` / `create_draft` / `ensure_chair_unit` `drafts`-dədir;
    # dövri idxaldan qaçmaq üçün çağırış vaxtı idxal edilir.
    from .drafts import _create_sections

    SyllabusSection.objects.filter(version=version).delete()
    _create_sections(version, source=base, actor_user=actor.user)
    Syllabus.objects.filter(pk=target.pk).update(current_version=version)
    target.current_version = version
    recompute_completion(version)
    log_action(
        AuditAction.CREATE,
        user=actor.user,
        organization=target.organization,
        obj=version,
        request=request,
        resource_type="syllabus.version",
        resource_id=str(version.pk),
        resource_repr=f"{target.subject_id} {version.label}",
        new_values={"status": version.status, "version": version.label, "kind": ChangeKind.COPIED},
        changes={"source_version": base.label, "copied_into_existing": True},
    )
    return version


@transaction.atomic
def copy_from_previous(*, source_syllabus, target_period, actor, offering=None, request=None):
    """«Keçən ildən köçür» — nəticə HƏR ZAMAN QARALAMADIR, avtomatik təsdiqlənmir.

    ƏHATƏ QAPISI ``create_next_version`` ilə EYNİDİR (2026-09-02 audit, P1-2):
    əvvəl bu funksiya MƏNBƏ sillabusu heç yoxlamırdı, ona görə istənilən müəllim
    ``{"action": "copy", "syllabus": <yad id>}`` göndərib başqasının məzmununu
    öz adına klonlaya bilirdi (auditor bunu canlı klonda icra etdi).
    """
    if not actor.has(PERM_EDIT):
        raise TransitionDenied("transition.permission_denied", params={"permission": PERM_EDIT})
    if not is_author(actor, source_syllabus) and not actor.covers_unit(source_syllabus.chair_unit_id, PERM_EDIT):
        raise TransitionDenied("transition.out_of_scope", params={"transition": "copy"})

    from .drafts import _create_sections, create_draft, ensure_chair_unit, recompute_completion

    ensure_chair_unit(source_syllabus)
    base = source_syllabus.approved_version or source_syllabus.versions.order_by("-major", "-minor").first()
    if base is None:
        raise TransitionDenied("version.base_missing")

    # QA 2026-09-05 (P2-20, sahib qərarı): köçürmə MÖVCUD dosyeyə yazır —
    # əvvəl eyni fənn/dövr üçün açılışsız İKİNCİ dosye yaranırdı (paralel iki
    # sillabus, kafedra müdiri hansına qərar verəcəyini bilmirdi). Təsdiqlənmiş
    # və ya açıq versiyalı dosye ÜSTÜNDƏN YAZILMIR — səbəb kodu qaytarılır.
    target = (
        Syllabus.objects.filter(
            organization=source_syllabus.organization,
            subject=source_syllabus.subject,
            period=target_period,
            offering=offering,
        )
        .exclude(pk=source_syllabus.pk)
        .first()
    )
    if target is not None:
        if target.approved_version_id is not None:
            raise TransitionDenied("copy.target_approved", params={"syllabus": str(target.pk)})
        open_version = target.versions.filter(status__in=sorted(OPEN_STATUSES)).first()
        if open_version is not None:
            raise TransitionDenied("copy.target_has_open_version", params={"version": open_version.label})
        return target, copy_into_existing(target, base=base, actor=actor, request=request)

    syllabus, version = create_draft(
        organization=source_syllabus.organization,
        subject=source_syllabus.subject,
        period=target_period,
        actor=actor,
        offering=offering,
        program=source_syllabus.program,
        chair_unit=source_syllabus.chair_unit,
        author=actor.user,
        plan_hours=base.plan_hours,
        request=request,
    )
    SyllabusVersion.objects.filter(pk=version.pk).update(change_kind=ChangeKind.COPIED, source_version=base)
    version.change_kind = ChangeKind.COPIED
    version.source_version = base
    SyllabusSection.objects.filter(version=version).delete()
    _create_sections(version, source=base, actor_user=actor.user)
    recompute_completion(version)
    return syllabus, version
