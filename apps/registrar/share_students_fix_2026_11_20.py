"""MR-000607 (2026-11-20): 235 EKO «Bitki ekologiyası» — seminarçının payına çatışmayan 3 oxuyan tələbə.

Seminarçının (müəllim id 8313) bu jurnaldakı payı sadalanan tələbə siyahısı ilə məhdudlaşıb; 3 tələbə jurnalda
``enrolled``-dir, amma siyahıda yoxdur — onun 6 seminarında boş sətirdir. Sadalanan siyahı QƏSDƏN açıq icazədir (boş =
hamısı): jurnala sonra düşən tələbə ora avtomatik düşmür (``workload`` reviewed təmirləri bunu test ilə qoruyur —
«future enrollment is not automatically granted»), ona görə əlavə ayrıca, adlı qərarla edilir. ``source=manual`` pay
``apply_journal_shares`` ilə heç vaxt üzərinə yazılmır, ona görə bu əmr yalnız həmin 3 qeydiyyatı əlavə edir.

Qaydalar (hər şey kilid altında yoxlanır, bir şərt pozulsa heç nə yazılmır):

* açılış təşkilatda var, aktivdir və fənni «Bitki ekologiyası»dır;
* müəllim aktivdir və bu açılışda AKTİV payı var; pay sətir-məhduddur (boş siyahı = hamısı — onda iş yoxdur);
* hər qeydiyyat (id prefiksi ilə, açılışın ``enrolled`` sətirləri arasında) DƏQİQ bir sətrə uyğun gəlir;
* artıq siyahıda olan qeydiyyat sayılır, toxunulmur; başqa heç bir sətir / pay dəyişmir.

``undo`` — yalnız həmin ``batch``-ın əlavə etdiyi (hələ siyahıda olan) qeydiyyatları siyahıdan çıxarır.
"""

from __future__ import annotations

import secrets
from collections import Counter

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

RESOURCE = "registrar.share_students_fix_20261120"
REASON = "MR-000607: 235 EKO «Bitki ekologiyası» — seminarçının payına jurnalda oxuyan 3 tələbə əlavə edildi"
UNDO_REASON = "MR-000607: seminarçının payına əlavə edilmiş tələbələrin geri qaytarılması"

OFFERING_ID = "b9fc8208-b32a-46fc-b0fe-019596247c6e"  # 235 EKO «Bitki ekologiyası»
SUBJECT_MARK = "bitki ekologiyas"
TEACHER_ID = 8313  # seminarçı
#: Qeydiyyat id prefiksləri (açılışın ``enrolled`` sətirləri arasında hər biri dəqiq bir sətir).
ENROLLMENT_PREFIXES = ("c2bc57d7", "d0eee1ad", "4235b2bc")


def _model(name: str, app: str = "registrar"):
    return django_apps.get_model(app, name)


def new_batch() -> str:
    return f"shstud-{timezone.localtime():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def _resolve(roster, prefixes, counts: Counter):
    """Prefiks → tək qeydiyyat id; uyğunsuzluqda ``None``."""
    found = []
    for prefix in prefixes:
        matches = [pk for pk in roster if str(pk).startswith(str(prefix).lower())]
        if len(matches) != 1:
            counts["enrollment_not_found" if not matches else "enrollment_ambiguous"] += 1
            return None
        found.append(matches[0])
    return found


def run(*, organization, actor, counts: Counter, batch: str, offering_id=None, teacher_id=None, prefixes=None) -> str:
    batch = batch or new_batch()
    offering_id = offering_id or OFFERING_ID
    teacher_id = teacher_id or TEACHER_ID
    prefixes = prefixes or ENROLLMENT_PREFIXES
    offering = (
        _model("CourseOffering")
        .objects.select_for_update()
        .filter(organization=organization, pk=offering_id)
        .select_related("subject")
        .first()
    )
    if offering is None:
        counts["offering_missing"] += 1
        return batch
    if SUBJECT_MARK not in str(offering.subject.name).casefold() or not offering.is_active:
        counts["offering_invalid"] += 1
        return batch
    teacher = get_user_model().objects.filter(pk=teacher_id, is_active=True).first()
    if teacher is None:
        counts["teacher_inactive"] += 1
        return batch
    share = (
        _model("JournalShare")
        .objects.select_for_update()
        .filter(organization=organization, offering=offering, teacher=teacher, is_active=True)
        .first()
    )
    if share is None:
        counts["share_missing"] += 1
        return batch
    counts[f"share_source_{share.source}"] = 1
    current = set(share.enrollments.values_list("pk", flat=True))
    if not current:
        counts["share_all_students"] += 1
        return batch
    Enrollment = _model("Enrollment")
    roster = set(
        Enrollment.objects.filter(offering=offering, status=Enrollment.Status.ENROLLED).values_list("pk", flat=True)
    )
    wanted = _resolve(roster, prefixes, counts)
    if wanted is None:
        counts["blocked"] += 1
        return batch
    added = [pk for pk in wanted if pk not in current]
    counts["already_in_share"] += len(wanted) - len(added)
    counts["roster_students"] = len(roster)
    counts["share_students_before"] = len(current)
    counts["other_missing"] = len(roster - current - set(wanted))
    if not added:
        counts["nothing_to_add"] += 1
        return batch
    share.enrollments.add(*added)
    counts["students_added"] += len(added)
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        reason=REASON,
        resource_type=RESOURCE,
        resource_id=str(share.pk),
        resource_repr="Seminarçının payına çatışmayan tələbələr",
        old_values={"students": len(current)},
        new_values={
            "batch": batch,
            "share": str(share.pk),
            "offering": str(offering.pk),
            "added": [str(pk) for pk in added],
        },
    )
    return batch


def undo(*, organization, actor, counts: Counter, batch: str) -> None:
    AuditLog = _model("AuditLog", "audit")
    JournalShare = _model("JournalShare")
    for row in AuditLog.objects.filter(organization=organization, resource_type=RESOURCE, new_values__batch=batch):
        counts["undo_rows"] += 1
        values = row.new_values or {}
        share = JournalShare.objects.select_for_update().filter(pk=values.get("share")).first()
        if share is None:
            counts["undo_share_missing"] += 1
            continue
        present = set(
            str(pk) for pk in share.enrollments.filter(pk__in=values.get("added") or []).values_list("pk", flat=True)
        )
        if present:
            share.enrollments.remove(*sorted(present))
        counts["undo_students_removed"] += len(present)
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            reason=UNDO_REASON,
            resource_type=f"{RESOURCE}.undo",
            resource_id=str(share.pk),
            resource_repr="Seminarçının payına əlavə edilmiş tələbələr geri",
            old_values={"batch": batch, "removed": sorted(present)},
        )
    if not counts["undo_rows"]:
        counts["undo_batch_unknown"] += 1


__all__ = ["ENROLLMENT_PREFIXES", "OFFERING_ID", "TEACHER_ID", "new_batch", "run", "undo"]
