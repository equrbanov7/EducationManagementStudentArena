"""MR-000686 / MR-000687 (2026-11-23): 935 BM «İxtisasyönümlü xarici dil-2» — iki müəllimin payında olan 2 tələbə.

Jurnal (``bde3ea2e``) iki müəllim arasında tələbə üzrə bölünüb (``JournalShare``): Aytac Salmanlı (8361) və Günay
Əmirova (8373), hər birində 15 tələbə, jurnalda 28. İki tələbə HƏR İKİ payda idi:

* Məmmədtağıyev Musa — Aytac xanım: «bu tələbə Günay Əmirovanın qrupunda olmalıdır» (MR-000687) → Aytacın payından
  çıxır, Günayın payında qalır;
* Kərimli Mədinə — Günay xanım: «diger müəllimənin qrupuna keçirin, mənim tələbəm deyil» (MR-000686) → Günayın payından
  çıxır, Aytacın payında qalır.

Qaydalar (hər şey kilid altında yoxlanır; bir şərt pozulsa heç nə yazılmır):

* açılış təşkilatda var, aktivdir, fənni «İxtisasyönümlü xarici dil»dir;
* hər müəllimin bu açılışda AKTİV, sətir-məhdud payı var (boş siyahı = hamısı — onda çıxarmaq mənasızdır, blok);
* hər qeydiyyat (id prefiksi ilə, açılışın ``enrolled`` sətirləri arasında) DƏQİQ bir sətrə uyğun gəlir;
* çıxarılan tələbə DİGƏR aktiv payda qalmalıdır (tələbə heç bir müəllimsiz qalmasın);
* artıq çıxarılmış sətir sayılır, toxunulmur (idempotent). Jurnal xanalarına / qeydiyyata toxunulmur.

``undo`` — yalnız həmin ``batch``-ın çıxardığı sətirləri öz payına qaytarır.
"""

from __future__ import annotations

import secrets
from collections import Counter

from django.apps import apps as django_apps
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

RESOURCE = "registrar.share_students_remove_20261123"
REASON = "MR-000686/687: 935 BM «İxtisasyönümlü xarici dil-2» — iki payda olan tələbə səhv müəllimin payından çıxarıldı"
UNDO_REASON = "MR-000686/687: paydan çıxarılmış tələbələrin geri qaytarılması"

OFFERING_ID = "bde3ea2e-2cf4-4733-8dff-0547350b8776"  # 935 BM «İxtisasyönümlü xarici dil-2»
SUBJECT_MARK = "xtisasyönümlü xarici dil"  # «İ».casefold() = «i̇» — baş hərf daxil edilmir
#: (müəllim id, qeydiyyat id prefiksi) — həmin müəllimin payından çıxan tələbə.
REMOVALS = (
    (8361, "cb21d9a7"),  # Aytac Salmanlı ← Məmmədtağıyev Musa (Günayda qalır)
    (8373, "82a6907f"),  # Günay Əmirova ← Kərimli Mədinə (Aytacda qalır)
)


def _model(name: str, app: str = "registrar"):
    return django_apps.get_model(app, name)


def new_batch() -> str:
    return f"shrem-{timezone.localtime():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def _match(roster, prefix):
    matches = [pk for pk in roster if str(pk).startswith(str(prefix).lower())]
    return matches[0] if len(matches) == 1 else None


def _plan(organization, offering, removals, counts: Counter):
    """``[(pay, qeydiyyat_id)]`` və ya ``None`` (blok)."""
    JournalShare = _model("JournalShare")
    Enrollment = _model("Enrollment")
    shares = {
        share.teacher_id: share
        for share in JournalShare.objects.select_for_update().filter(
            organization=organization, offering=offering, is_active=True
        )
    }
    members = {teacher_id: set(share.enrollments.values_list("pk", flat=True)) for teacher_id, share in shares.items()}
    roster = set(
        Enrollment.objects.filter(offering=offering, status=Enrollment.Status.ENROLLED).values_list("pk", flat=True)
    )
    plan = []
    for teacher_id, prefix in removals:
        share = shares.get(teacher_id)
        if share is None:
            counts["share_missing"] += 1
            return None
        if not members[teacher_id]:
            counts["share_all_students"] += 1
            return None
        enrollment_id = _match(roster, prefix)
        if enrollment_id is None:
            counts["enrollment_not_found"] += 1
            return None
        if enrollment_id not in members[teacher_id]:
            counts["already_removed"] += 1
            continue
        if not any(enrollment_id in rows for other, rows in members.items() if other != teacher_id):
            counts["would_orphan"] += 1
            return None
        plan.append((share, enrollment_id))
    return plan


def run(*, organization, actor, counts: Counter, batch: str, offering_id=None, removals=None) -> str:
    batch = batch or new_batch()
    offering = (
        _model("CourseOffering")
        .objects.select_for_update()
        .filter(organization=organization, pk=offering_id or OFFERING_ID)
        .select_related("subject")
        .first()
    )
    if offering is None:
        counts["offering_missing"] += 1
        return batch
    if SUBJECT_MARK not in str(offering.subject.name).casefold() or not offering.is_active:
        counts["offering_invalid"] += 1
        return batch
    plan = _plan(organization, offering, removals or REMOVALS, counts)
    if plan is None:
        counts["blocked"] += 1
        return batch
    if not plan:
        counts["nothing_to_remove"] += 1
        return batch
    for share, enrollment_id in plan:
        share.enrollments.remove(enrollment_id)
        counts["students_removed"] += 1
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            reason=REASON,
            resource_type=RESOURCE,
            resource_id=str(share.pk),
            resource_repr="İki payda olan tələbə səhv müəllimin payından çıxarıldı",
            old_values={"enrollment": str(enrollment_id)},
            new_values={"batch": batch, "share": str(share.pk), "offering": str(offering.pk)},
        )
    return batch


def undo(*, organization, actor, counts: Counter, batch: str) -> None:
    AuditLog = _model("AuditLog", "audit")
    JournalShare = _model("JournalShare")
    for row in AuditLog.objects.filter(organization=organization, resource_type=RESOURCE, new_values__batch=batch):
        counts["undo_rows"] += 1
        share = JournalShare.objects.select_for_update().filter(pk=(row.new_values or {}).get("share")).first()
        enrollment_id = (row.old_values or {}).get("enrollment")
        if share is None or not enrollment_id:
            counts["undo_share_missing"] += 1
            continue
        share.enrollments.add(enrollment_id)
        counts["undo_students_restored"] += 1
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            reason=UNDO_REASON,
            resource_type=f"{RESOURCE}.undo",
            resource_id=str(share.pk),
            resource_repr="Paydan çıxarılmış tələbə geri qaytarıldı",
            old_values={"batch": batch, "enrollment": str(enrollment_id)},
        )
    if not counts["undo_rows"]:
        counts["undo_batch_unknown"] += 1


__all__ = ["OFFERING_ID", "REMOVALS", "new_batch", "run", "undo"]
