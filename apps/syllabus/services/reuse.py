"""Sillabusun TƏKRAR İSTİFADƏSİ — YAZI tərəfi: bağla / kopyala / toplu / sinxron / ayır.

Qaydalar (kim, nəyi, nə vaxt) :mod:`.reuse_rules`-dadır; burada yalnız icra var.
Modul ``apps.registrar``-ı İDXAL ETMİR: hədəf açılışın saatı, ixtisası və struktur
işarəsi çağıran tərəfdən (accounts glue) :class:`ReuseTarget` ilə gəlir.

QƏRARLAR (sahib tələbi 2026-10-08, təhlükəsiz forma)
====================================================
1. **Təsdiq uydurulmur.** Bağlanan hədəfin versiyası ``APPROVED`` olur, amma
   ``approved_by`` NULL qalır, ``approval_source = reuse``, ``source_version`` isə
   mənbənin İNSAN tərəfindən təsdiqlənmiş versiyasını göstərir.  UI təsdiqi
   «Təsdiq: <qrup> sillabusundan (eyni məzmun, eyni saatlar)» kimi yazır
   (``ApprovalSource`` docstring-i, sahibin 2026-08 qərarı ilə eyni ruh).
2. **State maşınından keçir.** Hədəf əvvəl adi QARALAMA kimi yaranır (və ya mövcud
   qaralaması götürülür), sonra ``Transition.REUSE`` (DRAFT → APPROVED, müəllif,
   ``syllabus.edit``) ilə kilidli sətirdə keçid edir; köhnə təsdiqlənmiş nüsxə adi
   təsdiqdə olduğu kimi ARXİVLƏNİR, hər addım ``audit_auditlog``-a yazılır.  Mövcud
   qaralamanın əvəzlənən məzmunu audit qeydinin ``old_values.sections``-ındadır.
3. **Mənbə təsdiqlənməyibsə bağlama YOXDUR** (ən sadə təhlükəsiz seçim): «bağlı
   qaralama» kafedranın görmədiyi ikinci məzmunu gizli təsdiqə aparardı.  Belə
   halda yalnız «Kopyala və uyğunlaşdır» (qaralama → adi təsdiq) açıqdır; mənbə
   təsdiqlənəndən sonra hədəf hələ qaralamadırsa onu da bağlamaq olar.
4. **Sinxron avtomatik DEYİL** — mənbədə yeni versiya təsdiqlənəndə bağlı hədəflər
   özbaşına dəyişmir; müəllif «Bağlı sillabuslara tətbiq et» (və ya hədəfdə «Mənbədən
   yenilə») düyməsi ilə tətbiq edir.  Səbəb: hədəfin həftəlik mövzuları həmin qrupun
   jurnal mövzu siyahısını yaradır — başqa qrupun jurnalını SƏSSİZ dəyişmək
   olmaz, audit qeydində isə əməli edən konkret şəxs olmalıdır.  Gecikmə zərərsizdir:
   hədəf o vaxta qədər əvvəlki (yenə də insan təsdiqli) məzmunu göstərir.
5. **Ayır** — bağ silinir; qüvvədə olan nüsxə tələbələr üçün QALIR (məzmun hələ də
   təsdiqlənmiş məzmundur), redaktə üçün ondan müstəqil QARALAMA (v*.+1) açılır və
   adi təsdiq axınına düşür.  Bağlı dosyedə «Yeni versiya» qadağandır — əvvəl «Ayır».
6. **Toplu** — hər hədəf öz SAVEPOINT-ində: biri uğursuz olsa qalanlar yazılır.
   İdempotentdir: artıq bu mənbəyə bağlı hədəf «already», başqa dosyesi olan hədəf
   «exists» qaytarır və heç vaxt üstündən yazılmır.
"""

from __future__ import annotations

import copy as _copy
from dataclasses import dataclass, field

from django.db import IntegrityError, transaction
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from ..constants import OPEN_STATUSES, PERM_EDIT, SECTION_ORDER, SectionKey, SyllabusStatus
from ..models import ApprovalSource, ChangeKind, Syllabus, SyllabusSection, SyllabusVersion
from ..state_machine import Transition, TransitionDenied, check
from ..week_plan import fit_rows_to_hours
from . import reuse_rules as rules
from .scoping import is_author


@dataclass(frozen=True)
class ReuseTarget:
    """Bağlama/kopyalama hədəfi — ya YENİ açılış, ya da mövcud (qaralama) dosye.

    ``plan_hours`` hədəf açılışın RƏSMİ saatıdır (tədris planı / dərs yükü); tapılmasa
    mövcud dosyenin əl ilə daxil edilmiş saatı ötürülə bilər.  ``unit_hint`` —
    ``offering.group.parent`` (kafedra həlli ``create_draft`` ilə eyni qaydadır).
    """

    offering: object = None
    plan_hours: dict = field(default_factory=dict)
    program: object = None
    unit_hint: object = None
    syllabus: object = None

    @property
    def offering_id(self):
        if self.offering is not None:
            return self.offering.pk
        return getattr(self.syllabus, "offering_id", None)


def _denied(code: str, **params):
    return TransitionDenied(code, params=params)


def _slot(target):
    holder = target.syllabus if target.syllabus is not None else target.offering
    return (
        getattr(holder, "organization_id", None),
        getattr(holder, "subject_id", None),
        getattr(holder, "period_id", None),
    )


def _validate_target(source, target, actor):
    """Hədəf mənbənin qonşusudurmu və aktor onun müəllimidirmi (fail-closed)."""
    if not actor.has(PERM_EDIT):
        raise _denied("transition.permission_denied", permission=PERM_EDIT)
    if target.syllabus is None and target.offering is None:
        raise _denied(rules.CODE_NOT_SIBLING)
    organization_id, subject_id, period_id = _slot(target)
    if not rules.same_slot(source, organization_id=organization_id, subject_id=subject_id, period_id=period_id):
        raise _denied(rules.CODE_NOT_SIBLING)
    if target.syllabus is not None:
        if target.syllabus.pk == source.pk:
            raise _denied(rules.CODE_NOT_SIBLING)
        if not is_author(actor, target.syllabus):
            raise _denied("transition.author_only", transition="reuse")
        return
    if source.offering_id is not None and source.offering_id == target.offering.pk:
        raise _denied(rules.CODE_NOT_SIBLING)
    if target.offering.instructor_id != actor.user_id:
        raise _denied("transition.author_only", transition="reuse")


def target_chair_unit_id(target, actor):
    """Hədəfin təsdiq kafedrası — mövcud dosyedə onun öz bağı, yenidə ``create_draft`` qaydası."""
    if target.syllabus is not None:
        return target.syllabus.chair_unit_id
    from .units import resolve_syllabus_chair_unit

    unit = resolve_syllabus_chair_unit(unit=target.unit_hint, author=actor.user, organization=actor.organization)
    return getattr(unit, "pk", None)


def planned_mode(source, target, actor, *, chair_unit_id=None) -> str:
    """Toplu əməl bu hədəf üçün nə edəcək: ``link`` | ``copy`` | ``""`` (heç nə)."""
    source = rules.reuse_root(source)
    chair_id = target_chair_unit_id(target, actor) if chair_unit_id is None else chair_unit_id
    if not rules.link_code(
        source, actor=actor, target_hours=target.plan_hours, target_chair_unit_id=chair_id, target=target.syllabus
    ):
        return "link"
    return "" if rules.copy_code(source, actor=actor, target=target.syllabus) else "copy"


def _audit(actor, version, *, action=AuditAction.UPDATE, request=None, old=None, new=None, changes=None):
    log_action(
        action,
        user=actor.user,
        organization=version.organization,
        obj=version,
        request=request,
        resource_type="syllabus.version",
        resource_id=str(version.pk),
        resource_repr=f"{version.syllabus_id} {version.label}",
        old_values=old,
        new_values=new,
        changes=changes,
    )


def _new_draft(syllabus, *, actor, plan_hours, bump_major=False, request=None):
    """Dosyedə növbəti nömrəli BOŞ qaralama (məzmun çağıran tərəfindən yazılır)."""
    from .drafts import _create_sections

    numbers = list(syllabus.versions.values_list("major", "minor"))
    if not numbers:
        major, minor = 1, 0
    elif bump_major:
        major, minor = max(row_major for row_major, _minor in numbers) + 1, 0
    else:
        major = max(numbers)[0]
        minor = max(row_minor for row_major, row_minor in numbers if row_major == major) + 1
    version = SyllabusVersion.objects.create(
        organization_id=syllabus.organization_id,
        syllabus=syllabus,
        major=major,
        minor=minor,
        status=SyllabusStatus.DRAFT,
        change_kind=ChangeKind.REUSED,
        applies_to_period_id=syllabus.period_id,
        plan_hours=dict(plan_hours or {}),
        created_by=actor.user,
    )
    _create_sections(version, actor_user=actor.user)
    _audit(
        actor,
        version,
        action=AuditAction.CREATE,
        request=request,
        new={"status": version.status, "version": version.label, "kind": ChangeKind.REUSED},
    )
    return version


def _working_draft(syllabus, *, actor, plan_hours, request=None):
    """Mövcud dosyenin yazıla bilən qaralaması — açıq DRAFT, yoxdursa yenisi."""
    open_version = syllabus.versions.filter(status__in=sorted(OPEN_STATUSES)).first()
    if open_version is not None:
        if open_version.status != SyllabusStatus.DRAFT.value:
            raise _denied(rules.CODE_TARGET_LOCKED)
        return open_version
    return _new_draft(syllabus, actor=actor, plan_hours=plan_hours, request=request)


def _write_sections(version, data_map: dict, actor_user):
    """10 bölməni ``data_map`` ilə əvəzləyir; ``revision`` artır (açıq redaktor konflikt alır)."""
    from .drafts import blank_section_data

    rows = {row.section_id: row for row in SyllabusSection.objects.filter(version=version)}
    now = timezone.now()
    to_update, to_create = [], []
    for section_id in SECTION_ORDER:
        data = data_map.get(section_id)
        data = _copy.deepcopy(data) if data else blank_section_data(section_id, version.organization)
        row = rows.get(section_id)
        if row is None:
            to_create.append(
                SyllabusSection(
                    organization_id=version.organization_id,
                    version=version,
                    section_id=section_id,
                    data=data,
                    updated_by=actor_user,
                )
            )
            continue
        row.data, row.revision, row.updated_by, row.updated_at = data, row.revision + 1, actor_user, now
        to_update.append(row)
    if to_update:
        SyllabusSection.objects.bulk_update(to_update, ["data", "revision", "updated_by", "updated_at"])
    if to_create:
        SyllabusSection.objects.bulk_create(to_create)


def _approve_as_reuse(draft, *, syllabus, source, base, actor, plan_hours, request=None, replaced=False):
    """QARALAMA → APPROVED (``Transition.REUSE``) — məzmun ``base``-in EYNİ nüsxəsi."""
    from .drafts import recompute_completion, section_data_map
    from .workflow import _archive_superseded

    locked = SyllabusVersion.objects.select_for_update(of=("self",)).get(pk=draft.pk)
    locked.syllabus = syllabus
    author = is_author(actor, syllabus)
    check(
        name=Transition.REUSE,
        status=locked.status,
        permissions=actor.permissions if not actor.is_superadmin else ["*"],
        is_author=author,
        in_scope=author,
    )
    snapshot = section_data_map(locked) if replaced else None
    _write_sections(locked, {row.section_id: row.data for row in base.sections.all()}, actor.user)
    now = timezone.now()
    _archive_superseded(locked, actor=actor, request=request, now=now)
    old_status = locked.status
    locked.status = SyllabusStatus.APPROVED
    locked.change_kind = ChangeKind.REUSED
    locked.approval_source = ApprovalSource.REUSE
    locked.approved_by = None
    locked.approved_at = locked.decided_at = locked.locked_at = now
    locked.decision_reason = ""
    locked.source_version = base
    locked.plan_hours = dict(plan_hours or base.plan_hours or {})
    locked.save()
    recompute_completion(locked)
    Syllabus.objects.filter(pk=syllabus.pk).update(reused_from=source, approved_version=locked, current_version=locked)
    syllabus.reused_from, syllabus.approved_version, syllabus.current_version = source, locked, locked
    old_values = {"status": old_status}
    if snapshot is not None:
        old_values["sections"] = snapshot
    _audit(
        actor,
        locked,
        request=request,
        old=old_values,
        new={"status": locked.status, "approval_source": ApprovalSource.REUSE.value, "version": locked.label},
        changes={
            "transition": Transition.REUSE,
            "source_syllabus": str(source.pk),
            "source_version": str(base.pk),
            "source_version_label": base.label,
            "source_approved_by": str(base.approved_by_id or ""),
        },
    )
    return locked


def _lock(syllabus):
    Syllabus.objects.select_for_update(of=("self",)).filter(pk=syllabus.pk).first()
    return syllabus


def _link(source, target, actor, *, chair_unit_id, request=None):
    code = rules.link_code(
        source,
        actor=actor,
        target_hours=target.plan_hours,
        target_chair_unit_id=chair_unit_id,
        target=target.syllabus,
    )
    if code:
        raise _denied(code)
    base = rules.link_base(source)
    hours = rules.normalize_hours(target.plan_hours)
    if target.syllabus is None:
        from .drafts import create_draft

        syllabus, draft = create_draft(
            organization=source.organization,
            subject=source.subject,
            period=source.period,
            actor=actor,
            offering=target.offering,
            program=target.program,
            chair_unit=target.unit_hint,
            author=actor.user,
            plan_hours=hours,
            request=request,
        )
    else:
        syllabus = _lock(target.syllabus)
        draft = _working_draft(syllabus, actor=actor, plan_hours=hours, request=request)
    version = _approve_as_reuse(
        draft,
        syllabus=syllabus,
        source=source,
        base=base,
        actor=actor,
        plan_hours=hours,
        request=request,
        replaced=target.syllabus is not None,
    )
    return syllabus, version


@transaction.atomic
def link(*, source, target, actor, request=None):
    """«Eyni sillabusu istifadə et (bağla)» — bax modul docstring-i (qərar 1–3)."""
    source = rules.reuse_root(source)
    _validate_target(source, target, actor)
    return _link(source, target, actor, chair_unit_id=target_chair_unit_id(target, actor), request=request)


@transaction.atomic
def copy_adjust(*, source, target, actor, request=None):
    """«Kopyala və uyğunlaşdır» — məzmun QARALAMA kimi yazılır, həftə hədəfin saatına uyğunlaşır."""
    from .drafts import _inherited_data, create_draft, recompute_completion, section_data_map

    source = rules.reuse_root(source)
    _validate_target(source, target, actor)
    code = rules.copy_code(source, actor=actor, target=target.syllabus)
    if code:
        raise _denied(code)
    base = rules.copy_base(source)
    if base is None:
        raise _denied(rules.CODE_BASE_MISSING)
    hours = rules.normalize_hours(target.plan_hours)
    if target.syllabus is None:
        syllabus, version = create_draft(
            organization=source.organization,
            subject=source.subject,
            period=source.period,
            actor=actor,
            offering=target.offering,
            program=target.program,
            chair_unit=target.unit_hint,
            author=actor.user,
            plan_hours=hours,
            request=request,
        )
        snapshot = None
    else:
        syllabus = _lock(target.syllabus)
        version = _working_draft(syllabus, actor=actor, plan_hours=hours, request=request)
        snapshot = section_data_map(version)
    hours = hours or rules.normalize_hours(version.plan_hours)
    base_map = {row.section_id: row.data for row in base.sections.all()}
    data_map = {
        section_id: _inherited_data(section_id, base_map, syllabus.organization) for section_id in SECTION_ORDER
    }
    week = dict(data_map.get(SectionKey.WEEK.value) or {})
    rows, adjusted = fit_rows_to_hours(week.get("rows") or [], hours)
    if adjusted:
        data_map[SectionKey.WEEK.value] = {**week, "rows": rows}
    _write_sections(version, data_map, actor.user)
    SyllabusVersion.objects.filter(pk=version.pk).update(
        change_kind=ChangeKind.COPIED, source_version=base, plan_hours=dict(hours)
    )
    version.change_kind, version.source_version, version.plan_hours = ChangeKind.COPIED, base, dict(hours)
    recompute_completion(version)
    old_values = {"sections": snapshot} if snapshot is not None else None
    _audit(
        actor,
        version,
        request=request,
        old=old_values,
        new={"status": version.status, "version": version.label, "kind": ChangeKind.COPIED},
        changes={
            "reuse": "copy",
            "source_syllabus": str(source.pk),
            "source_version": base.label,
            "week_adjusted": adjusted,
        },
    )
    return syllabus, version


def _result(target, status, *, syllabus=None, version=None, code=""):
    return {
        "offering": str(target.offering_id or ""),
        "status": status,
        "syllabus": str(getattr(syllabus, "pk", "") or ""),
        "version": str(getattr(version, "pk", "") or ""),
        "code": code,
    }


def apply_bulk(*, source, targets, actor, request=None) -> list:
    """«Hamısına tətbiq et» — saat eynidirsə bağla, deyilsə kopyala; hər hədəf ayrıca.

    Nəticə: ``[{offering, status, syllabus, version, code}]``; ``status`` ∈
    ``linked | copied | already | exists | skipped``.
    """
    root = rules.reuse_root(source)
    results = []
    for target in targets:
        if target.syllabus is not None:
            status = "already" if target.syllabus.reused_from_id == root.pk else "exists"
            results.append(_result(target, status, syllabus=target.syllabus))
            continue
        try:
            _validate_target(root, target, actor)
            chair_id = target_chair_unit_id(target, actor)
            mode = planned_mode(root, target, actor, chair_unit_id=chair_id)
            if not mode:
                raise _denied(rules.copy_code(root, actor=actor) or rules.CODE_COPY_OUT_OF_SCOPE)
            with transaction.atomic():
                if mode == "link":
                    syllabus, version = _link(root, target, actor, chair_unit_id=chair_id, request=request)
                else:
                    syllabus, version = copy_adjust(source=root, target=target, actor=actor, request=request)
            results.append(
                _result(target, "linked" if mode == "link" else "copied", syllabus=syllabus, version=version)
            )
        except IntegrityError:
            # Yarış: eyni açılışa paralel sorğu dosye yaratdı — üstündən yazılmır.
            results.append(_result(target, "exists"))
        except TransitionDenied as denied:
            results.append(_result(target, "skipped", code=denied.code))
    return results


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
        target_chair_unit_id=target.chair_unit_id,
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


__all__ = [
    "ReuseTarget",
    "apply_bulk",
    "copy_adjust",
    "is_behind",
    "link",
    "linked_summary",
    "planned_mode",
    "propagate",
    "sync_from_source",
    "target_chair_unit_id",
    "unlink",
]
