"""Sahib 2026-11-19 («Bəli, belə et»): birləşdirilmiş tələbə dublikatının jurnalda qalan ikinci sətri.

``merge_duplicate_student`` (``apps.accounts.services.student_merge``) dublikatın xanalarını əsas hesabın eyni
açılışdakı qeydiyyatına YALNIZ boş hədəfə daşıyırdı; fərqli dəyərli xana (``*_conflict``) dublikat qeydiyyatda
qalırdı və həmin qeydiyyat ``enrolled`` qalırdı → tələbə jurnalda İKİ dəfə görünür. Bu əmr həmin sətirləri bağlayır.

Cütlər (dublikat → əsas) birləşdirmə paketlərinin audit manifestindən (``accounts.student_merge_batch``) oxunur —
yalnız ``SOURCE_BATCHES`` / ``SOURCE_BATCH_PREFIXES`` paketləri, yalnız BLOKLANMIŞ dublikat hesablar,
``EXCLUDED_DUPLICATES`` istisna (11740 ≠ 8737 — ata adı fərqlidir, eyni şəxs təsdiqlənməyib).

Hər «qalıq sətir» (dublikatın ``enrolled`` qeydiyyatı + əsas hesabın EYNİ açılışda ``enrolled`` qeydiyyatı) öz
savepoint-ində, kilid altında:

* bağlı / passiv jurnal, dublikat xanasında rəsmi düzəliş (``JournalCorrection``), dublikatda başqa data (yekun,
  imtahan balı, …) → sətrə toxunulmur, sayılır;
* xana: əsasda həmin dərsdə xana YOXDUR → dublikatın xanası (status + bal, köhnə ``created_at``) əsasa yazılır;
  əsasda xana var, balı boş, dublikatda bal var və davamiyyət eynidir → bal əsasın xanasına yazılır;
  qalan hallar (əsasda bal var, davamiyyət fərqlidir, eyni dəyər) → əsasın dəyəri qalır, dublikatınkı atılır;
* komponent balı: əsasda yoxdur → köçürülür (köhnə ``created_at``, ``exam_source``), var → əsasınkı qalır;
* dublikat qeydiyyat ``dropped`` olur (birləşdirmə alətinin boş dublikata etdiyi kimi), xanaları SİLİNMİR;
* qayıb saatı hər iki qeydiyyat üçün yenidən hesablanır.

Manifest (köhnə dəyərlər) paketin BİR audit sətrindədir; ``undo`` yaradılanı silir, yenilənəni qaytarır, sətri
``enrolled`` edir — sonradan dəyişdirilmiş xanaya toxunmur.
"""

from __future__ import annotations

import secrets
from collections import Counter
from decimal import Decimal

from django.apps import apps as django_apps
from django.db import transaction
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from .twin_relocate import closed, copy_mark, recompute_absences

RESOURCE = "registrar.duplicate_rows_resolve_20261119"
REASON = "Sahib 2026-11-19: birləşdirilmiş dublikat tələbənin jurnaldakı ikinci sətri əsas sətrə yığıldı"
UNDO_REASON = "Dublikat sətir yığımının geri qaytarılması"
#: ``apps.accounts.services.student_merge.apply.BATCH_RESOURCE`` — modul sərhədi üçün sətir kimi.
MERGE_RESOURCE = "accounts.student_merge_batch"
#: 16.11 əsas paket + 18.11 paketi; 16.11-in ikinci (``allow_name``) planı prefikslə tutulur.
SOURCE_BATCHES = ("stmerge-20261116-025036-52cd", "stmerge-20261118-221823-994c")
SOURCE_BATCH_PREFIXES = ("stmerge-20261116-",)
EXCLUDED_DUPLICATES = frozenset({11740})
#: Bu modellərdə datası olan dublikat sətri bağlanmır (yekun / imtahan / köhnə nəticə — əl ilə baxılmalıdır).
BLOCKING_MODELS = (
    "CriterionScore",
    "FinalGrade",
    "ResitRecord",
    "CourseWork",
    "SelfWorkMark",
    "ExamScoreEntry",
    "LegacyGradeFact",
    "ExternalCreditRecognition",
    "RetakeApplication",
)


def _model(name: str):
    return django_apps.get_model("registrar", name)


def new_batch() -> str:
    return f"dupres-{timezone.localtime():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def _text(value):
    return None if value is None else str(value)


def merge_pairs(organization, counts: Counter) -> dict:
    """Paket manifestlərindən ``{dublikat: əsas}``; ziddiyyətli (iki fərqli əsas) dublikat atılır."""

    AuditLog = django_apps.get_model("audit", "AuditLog")
    pairs: dict = {}
    ambiguous = set()
    for entry in AuditLog.objects.filter(organization=organization, resource_type=MERGE_RESOURCE).order_by("pk"):
        batch = str(entry.resource_id or "")
        if batch not in SOURCE_BATCHES and not batch.startswith(SOURCE_BATCH_PREFIXES):
            continue
        counts["merge_batches_read"] += 1
        for row in (entry.new_values or {}).get("pairs") or []:
            duplicate, keep = row.get("duplicate"), row.get("keep")
            if not duplicate or not keep:
                continue
            if pairs.get(duplicate, keep) != keep:
                ambiguous.add(duplicate)
            pairs[duplicate] = keep
    for duplicate in ambiguous:
        pairs.pop(duplicate, None)
    counts["pairs_ambiguous"] += len(ambiguous)
    counts["pairs_in_batches"] = len(pairs)
    return pairs


def _blocked_pairs(pairs: dict, counts: Counter) -> list:
    User = django_apps.get_model("auth", "User")
    active = dict(User.objects.filter(pk__in=set(pairs) | set(pairs.values())).values_list("pk", "is_active"))
    out = []
    for duplicate, keep in sorted(pairs.items()):
        if duplicate in EXCLUDED_DUPLICATES:
            counts["pairs_excluded"] += 1
        elif active.get(duplicate) is not False:
            counts["pairs_duplicate_not_blocked"] += 1
        elif not active.get(keep):
            counts["pairs_keep_inactive"] += 1
        else:
            out.append((duplicate, keep))
    return out


def _leftover_rows(organization, duplicate, keep, counts: Counter) -> list:
    Enrollment = _model("Enrollment")
    keep_rows = {
        row.offering_id: row
        for row in Enrollment.objects.filter(organization=organization, student_id=keep).select_related("offering")
    }
    rows = []
    for row in Enrollment.objects.filter(organization=organization, student_id=duplicate, status="enrolled"):
        target = keep_rows.get(row.offering_id)
        if target is None:
            continue
        if target.status != "enrolled":
            counts["rows_keep_not_enrolled"] += 1
            continue
        rows.append((row, target))
    return rows


def _skip_reason(dup, offering) -> str:
    if not offering.is_active or closed([offering.pk]):
        return "closed_or_inactive"
    if _model("JournalCorrection").objects.filter(enrollment_ref=dup.pk).exists():
        return "corrected_cells"
    for name in BLOCKING_MODELS:
        if _model(name).objects.filter(enrollment_id=dup.pk).exists():
            return f"has_{name.lower()}"
    return ""


def _resolve_marks(dup, keep, entry: dict, counts: Counter) -> None:
    LessonMark = _model("LessonMark")
    kept = {row.lesson_id: row for row in LessonMark.objects.select_for_update(of=("self",)).filter(enrollment=keep)}
    corrected = {
        str(pk)
        for pk in _model("JournalCorrection")
        .objects.filter(enrollment_ref=keep.pk)
        .values_list("lesson_ref", flat=True)
    }
    for mark in LessonMark.objects.select_for_update(of=("self",)).select_related("lesson").filter(enrollment=dup):
        target = kept.get(mark.lesson_id)
        if target is None:
            created = copy_mark(mark, lesson=mark.lesson, enrollment=keep)
            entry["marks_created"].append(
                {"id": str(created.pk), "status": created.status, "score": _text(created.score)}
            )
            counts["marks_copied"] += 1
        elif target.score is None and mark.score is not None and target.status == mark.status:
            if str(target.lesson_id) in corrected:
                counts["marks_keep_corrected_kept"] += 1
                continue
            LessonMark.objects.filter(pk=target.pk).update(score=mark.score, updated_at=timezone.now())
            entry["marks_updated"].append(
                {"id": str(target.pk), "old_score": None, "new_score": _text(mark.score), "status": target.status}
            )
            counts["scores_copied_onto_kept_mark"] += 1
        elif target.status == mark.status and target.score == mark.score:
            counts["marks_same"] += 1
        elif target.status != mark.status:
            counts["marks_attendance_kept"] += 1
        else:
            counts["marks_kept_value_wins"] += 1


def _resolve_components(dup, keep, entry: dict, counts: Counter) -> None:
    ComponentScore = _model("ComponentScore")
    taken = set(ComponentScore.objects.filter(enrollment=keep).values_list("component_id", flat=True))
    for score in ComponentScore.objects.select_for_update(of=("self",)).filter(enrollment=dup):
        if score.component_id in taken:
            counts["components_kept_value_wins"] += 1
            continue
        created = ComponentScore.objects.create(
            organization_id=keep.organization_id,
            component_id=score.component_id,
            enrollment=keep,
            score=score.score,
            entered_by_id=score.entered_by_id,
        )
        ComponentScore.objects.filter(pk=created.pk).update(created_at=score.created_at, exam_source=score.exam_source)
        entry["scores_created"].append({"id": str(created.pk), "score": _text(score.score)})
        counts["component_scores_copied"] += 1


def run(*, organization, actor, counts: Counter, batch: str = "") -> str:
    from core.rls import journal_unlock

    batch = batch or new_batch()
    Enrollment = _model("Enrollment")
    manifest = []
    with transaction.atomic(), journal_unlock(local=True):
        for duplicate, keep in _blocked_pairs(merge_pairs(organization, counts), counts):
            counts["pairs_checked"] += 1
            for dup, target in _leftover_rows(organization, duplicate, keep, counts):
                counts["rows_found"] += 1
                with transaction.atomic():
                    dup = Enrollment.objects.select_for_update(of=("self",)).select_related("offering").get(pk=dup.pk)
                    reason = _skip_reason(dup, dup.offering)
                    if reason:
                        counts["rows_skipped"] += 1
                        counts[f"rows_skipped_{reason}"] += 1
                        continue
                    entry = {"duplicate": duplicate, "keep": keep, "dup_enrollment": str(dup.pk),
                             "keep_enrollment": str(target.pk), "offering": str(dup.offering_id),
                             "old_status": dup.status, "marks_created": [], "marks_updated": [],
                             "scores_created": []}  # fmt: skip
                    _resolve_marks(dup, target, entry, counts)
                    _resolve_components(dup, target, entry, counts)
                    Enrollment.objects.filter(pk=dup.pk).update(status="dropped", updated_at=timezone.now())
                    recompute_absences(list(Enrollment.objects.filter(pk__in=[dup.pk, target.pk])))
                    manifest.append(entry)
                    counts["rows_resolved"] += 1
        if not manifest:
            counts["nothing_to_resolve"] += 1
            return batch
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            reason=REASON,
            resource_type=RESOURCE,
            resource_id=batch,
            resource_repr="Dublikat tələbənin jurnaldakı ikinci sətri",
            new_values={"batch": batch, "counts": dict(counts), "rows": manifest},
        )
    return batch


def _same(current, stored) -> bool:
    if current is None or stored is None:
        return current is None and stored is None
    return Decimal(current) == Decimal(stored)


def undo(*, organization, actor, counts: Counter, batch: str) -> None:
    from core.rls import journal_unlock

    AuditLog = django_apps.get_model("audit", "AuditLog")
    Enrollment = _model("Enrollment")
    LessonMark = _model("LessonMark")
    ComponentScore = _model("ComponentScore")
    entry = AuditLog.objects.filter(organization=organization, resource_type=RESOURCE, resource_id=batch).first()
    if entry is None:
        counts["undo_batch_not_found"] += 1
        return
    with transaction.atomic(), journal_unlock(local=True):
        for row in (entry.new_values or {}).get("rows") or []:
            counts["undo_rows"] += 1
            marks = {str(m.pk): m for m in LessonMark.objects.filter(pk__in=[x["id"] for x in row["marks_created"]])}
            for item in row["marks_created"]:
                mark = marks.get(item["id"])
                if mark is None or mark.status != item["status"] or not _same(mark.score, item["score"]):
                    counts["undo_mark_changed_kept"] += 1
                    continue
                mark.delete()
                counts["undo_marks_deleted"] += 1
            for item in row["marks_updated"]:
                mark = LessonMark.objects.filter(pk=item["id"]).first()
                if mark is None or mark.status != item["status"] or not _same(mark.score, item["new_score"]):
                    counts["undo_mark_changed_kept"] += 1
                    continue
                LessonMark.objects.filter(pk=mark.pk).update(score=item["old_score"], updated_at=timezone.now())
                counts["undo_marks_restored"] += 1
            for item in row["scores_created"]:
                score = ComponentScore.objects.filter(pk=item["id"]).first()
                if score is None or not _same(score.score, item["score"]):
                    counts["undo_score_changed_kept"] += 1
                    continue
                score.delete()
                counts["undo_scores_deleted"] += 1
            counts["undo_rows_reenrolled"] += Enrollment.objects.filter(
                pk=row["dup_enrollment"], status="dropped"
            ).update(status=row["old_status"], updated_at=timezone.now())
            recompute_absences(list(Enrollment.objects.filter(pk__in=[row["dup_enrollment"], row["keep_enrollment"]])))
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            reason=UNDO_REASON,
            resource_type=f"{RESOURCE}.undo",
            resource_id=batch,
            resource_repr="Dublikat sətir yığımının geri qaytarılması",
            old_values={"batch": batch},
            new_values={"undone_batch": batch, "counts": dict(counts)},
        )


__all__ = [
    "EXCLUDED_DUPLICATES",
    "MERGE_RESOURCE",
    "RESOURCE",
    "SOURCE_BATCHES",
    "SOURCE_BATCH_PREFIXES",
    "merge_pairs",
    "new_batch",
    "run",
    "undo",
]
