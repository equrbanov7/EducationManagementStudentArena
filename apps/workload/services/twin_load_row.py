"""Əkiz birləşməsindən sonra yük sətrinin fənni — sağ qalan jurnalın fənninə (sahib 2026-11-05, MR-161).

Birləşmədə data düzgün fənnin jurnalına (E) köçür, köhnə fənnin jurnalı (D) ləğv olunur. Sətir hələ köhnə fəndədirsə
sinxron onu ləğv olunmuş D-yə tuşlayır və TOXUNMUR (``offering_sync`` ləğv olunmuş açılışı ötürür — köhnə fənnin
jurnalı nə yenidən yaranır, nə aktivləşir). Sətrin fənni yenə də düzəliş axını ilə (``save_row_amended``,
``sync_offerings=True``) E-nin fənninə keçirilir, AMMA:

* həmin sənəddə eyni fənn + ixtisas + semestr + qrup dəsti ilə ARTIQ sətir varsa (məs. rəsmi baxılmış mənbə sətri)
  dəyişmək dublikat olardı (``workload.duplicate_row``) — sayılır (``load_row_target_exists``), yazılmır; o sətir E-nin
  yük sətridir, köhnə sətrin taleyi (silinmə) tədris şöbəsinin qərarıdır;
* sətir başqa qrupları da əhatə edirsə, başqa dövrdədirsə və ya fənni gözləniləndən fərqlidirsə — sayılır;
* sinxron qrup + dövr üzrə açılış dəstini dəyişsə (yeni jurnal yaratsa) və ya E-ni passivləşdirsə — hamısı geri
  qaytarılır (``load_row_sync_changed_offerings``).

İdempotent: sətir artıq E-nin fənnindədirsə ``load_row_already``.
"""

from __future__ import annotations

import re

from django.apps import apps as django_apps
from django.db import transaction

from ..constants import AmendmentReason
from ..models import TeachingTaskRow
from .row_edit import save_row_amended
from .scoping import WorkloadDenied, resolve_actor

NOTE = "Əkiz jurnal birləşməsi: sətrin fənni sağ qalan jurnalın fənninə (repair_twins_20261105b)"


def _offering_ids(offering) -> list:
    CourseOffering = django_apps.get_model("registrar", "CourseOffering")
    rows = CourseOffering.objects.filter(
        organization_id=offering.organization_id, period_id=offering.period_id, group_id=offering.group_id
    )
    return sorted((str(pk), active) for pk, active in rows.values_list("pk", "is_active"))


def _duplicate_on_target(row, subject_id) -> bool:
    groups = set(row.groups.values_list("pk", flat=True))
    others = TeachingTaskRow.objects.filter(
        task_id=row.task_id, season=row.season, specialty_id=row.specialty_id, subject_id=subject_id
    ).exclude(pk=row.pk)
    return any(set(other.groups.values_list("pk", flat=True)) == groups for other in others)


def switch_load_row(*, organization, user, row_id, offering_id, old_subject_id, counts) -> None:
    CourseOffering = django_apps.get_model("registrar", "CourseOffering")
    offering = CourseOffering.objects.filter(organization=organization, pk=offering_id).first()
    if offering is None or not offering.is_active:
        counts["load_row_offering_inactive"] += 1
        return
    row = (
        TeachingTaskRow.objects.select_for_update(of=("self",))
        .select_related("task")
        .filter(organization=organization, pk=row_id)
        .first()
    )
    if row is None:
        counts["load_row_missing"] += 1
        return
    if row.subject_id == offering.subject_id:
        counts["load_row_already"] += 1
        return
    if str(row.subject_id) != str(old_subject_id):
        counts["load_row_subject_mismatch"] += 1
        return
    if row.period_id != offering.period_id or set(row.groups.values_list("pk", flat=True)) != {offering.group_id}:
        counts["load_row_scope_mismatch"] += 1
        return
    if _duplicate_on_target(row, offering.subject_id):
        counts["load_row_target_exists"] += 1
        return
    before = _offering_ids(offering)
    with transaction.atomic():
        try:
            save_row_amended(
                task=row.task,
                row=row,
                actor=resolve_actor(user, organization),
                data={"subject_id": str(offering.subject_id)},
                amend={"reason": AmendmentReason.CORRECTION, "note": NOTE},
                sync_offerings=True,
            )
        except WorkloadDenied as exc:
            transaction.set_rollback(True)
            code = re.sub(r"[^a-z_]", "_", str(exc.code).replace("workload.", "").lower())
            counts[f"load_row_denied_{code}"] += 1
            return
        if _offering_ids(offering) != before:
            transaction.set_rollback(True)
            counts["load_row_sync_changed_offerings"] += 1
            return
    counts["load_row_subject_changed"] += 1


__all__ = ["switch_load_row"]
