"""«Əkiz jurnal» xanalarının düzgün açılışa köçürülməsi (RİM 2026-10-27, MR-11/15) — ``relocate_twin_enrollment``.

Köhnə delta (``legacy_import.delta.journals``) tələbəni fənn üzrə «ilk emal olunan» legacy jurnalın açılışına (W)
yazırdı; əsl jurnalın (T) xanaları W-də T-nin tarix/saatında 1–3 xanalı «fantom dərs» kimi qalıb. Plan faylı lokal
qurulur (``build_twin_repair_plans`` — köhnə sistem + prod nüsxəsi), YALNIZ id-lərdir::

    {"format": "twin-relocate/1", "items": [{"student": int, "source": enrollment uuid, "target_offering": uuid,
      "moves": [{"mark": uuid, "lesson": uuid}], "restore": [{"lesson": uuid, "status": "absent"|"excused"}],
      "drop_source": bool}]}

Hər bənd öz savepoint-ində, HƏR ŞEY kilid altında yenidən yoxlanılır (plan köhnəlibsə sətir atlanır və sayılır):

* bağlı / passiv jurnal (W və ya T) — toxunulmur; W və T eyni fənn + dövr olmalıdır;
* tələbənin reyestr qrupu W-nin qrupudursa (T-ninki deyil) — yeni sistemin qərarıdır, toxunulmur;
* T-də qeydiyyat: varsa (aktiv) o, yoxdursa yaradılır (qrupu fərqlidirsə «alt qrupdan əlavə» forması);
* xana: W-dəki xana T-nin EYNİ tarixli dərsinə (plan dərsi göstərir) YENİ sətir kimi yazılır, W-dəki silinir
  (``LessonMark.lesson``/``enrollment`` dəyişməz identikdir; ``trg_journal_mark_guard`` yalnız UPDATE-dədir).
  ``created_at`` köhnə xananınkı saxlanılır — müəllimin 15 dəqiqəlik pəncərəsi yenidən açılmır. Rəsmi düzəlişi
  (``JournalCorrection``) olan xanaya və T-də artıq dolu xanaya toxunulmur;
* ``restore`` — köhnə delta-nın «yalnız qb» fantom dərsi atanda itən əsl qayıblar T-nin mövcud dərsinə (boşdursa);
* W-də xanası qalmayan, köçürmənin yaratdığı (``created_by`` boş), düzəlişsiz dərs silinir;
* ``drop_source`` — W qeydiyyatı ``dropped`` olur, ``superseded_by`` YAZILMIR: W-də qalan «siyahıda qaldı» qayıbları
  (yalnız yanlış jurnalda olan) T-yə DAŞINMIR (``guest_merge.carried_absence_hours`` yalnız əvəzləmə zəncirini
  sayır). Yekun qiyməti / komponent balı olan W qeydiyyatı düşürülmür;
* qayıb saatı hər iki qeydiyyat üçün yenidən hesablanır; hər bənd üçün audit sətri.

İdempotentdir: ikinci qaçışda köçürülmüş xana W-də yoxdur, qeydiyyat artıq ``dropped``-dır → 0 yazı.
"""

from __future__ import annotations

from collections import Counter

from django.apps import apps as django_apps
from django.db import IntegrityError, transaction
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

FORMAT = "twin-relocate/1"
REASON = "Əkiz jurnal düzəlişi: köhnə sistemin əsl jurnalının xanaları düzgün açılışa — RİM 2026-10-27 (MR-11/15)"
RESTORE_STATUSES = ("absent", "excused")


def _model(name: str):
    return django_apps.get_model("registrar", name)


def corrected_mark_ids(mark_ids) -> set:
    """Rəsmi düzəlişi olan xanalar (``JournalCorrection.lesson_mark_ref``)."""

    ids = [value for value in mark_ids if value]
    if not ids:
        return set()
    rows = _model("JournalCorrection").objects.filter(lesson_mark_ref__in=ids).values_list("lesson_mark_ref", flat=True)
    return {str(value) for value in rows}


def corrected_lesson_ids(lesson_ids) -> set:
    ids = [value for value in lesson_ids if value]
    if not ids:
        return set()
    rows = _model("LessonCorrection").objects.filter(lesson_id__in=ids).values_list("lesson_id", flat=True)
    return {str(value) for value in rows}


def has_scores(enrollment_ids) -> bool:
    """Yekun qiymət / komponent (Midterm …) balı — belə qeydiyyat düşürülmür və birləşdirilmir."""

    ids = list(enrollment_ids)
    return (
        _model("FinalGrade").objects.filter(enrollment_id__in=ids).exists()
        or _model("ComponentScore").objects.filter(enrollment_id__in=ids).exists()
    )


def copy_mark(mark, *, lesson, enrollment):
    """Xananın yeni sətri (``created_at`` köhnəsi kimi — redaktə pəncərəsi yenidən açılmır)."""

    LessonMark = _model("LessonMark")
    created = LessonMark.objects.create(
        organization_id=lesson.organization_id,
        lesson=lesson,
        enrollment=enrollment,
        status=mark.status,
        score=mark.score,
        entered_by_id=mark.entered_by_id,
    )
    # INSERT-dən dərhal sonra: trigger-in pəncərəsi ``OLD.created_at``-dan (indi) sayılır — UPDATE keçir.
    LessonMark.objects.filter(pk=created.pk).update(created_at=mark.created_at)
    return created


def delete_empty_lessons(lesson_ids, counts: Counter, key: str = "lessons_deleted") -> list:
    """Xanası qalmayan, köçürmənin yaratdığı (``created_by`` boş), rəsmi düzəlişsiz dərsləri sil."""

    Lesson = _model("Lesson")
    ids = [value for value in lesson_ids if value]
    if not ids:
        return []
    corrected = corrected_lesson_ids(ids)
    rows = (
        Lesson.objects.select_for_update(of=("self",))
        .filter(pk__in=ids, created_by__isnull=True, marks__isnull=True)
        .values_list("pk", flat=True)
    )
    doomed = [pk for pk in rows if str(pk) not in corrected]
    if doomed:
        Lesson.objects.filter(pk__in=doomed).delete()
    counts[key] += len(doomed)
    counts["lessons_kept_corrected"] += sum(1 for pk in ids if str(pk) in corrected)
    return [str(pk) for pk in doomed]


def target_enrollment(*, organization, actor, student_id, offering, counts: Counter):
    """T-də tələbənin qeydiyyatı: mövcud aktiv sətir və ya yeni (fərqli qrup → «alt qrupdan əlavə» forması)."""

    Enrollment = _model("Enrollment")
    Record = _model("StudentAcademicRecord")
    found = Enrollment.objects.select_for_update().filter(student_id=student_id, offering=offering).first()
    if found is not None:
        return found, False
    group_id = (
        Record.objects.filter(organization=organization, student_id=student_id, is_active=True)
        .values_list("group_id", flat=True)
        .first()
    )
    guest = group_id is not None and group_id != offering.group_id
    try:
        with transaction.atomic():
            created = Enrollment.objects.create(
                organization=organization,
                student_id=student_id,
                offering=offering,
                kind="mandatory",
                status="enrolled",
                source_group_id=group_id if guest else None,
                added_by=actor if guest else None,
                added_at=timezone.now() if guest else None,
            )
    except IntegrityError:
        counts["target_enrollment_blocked"] += 1
        return None, False
    counts["enrollments_created"] += 1
    return created, True


def closed(offering_ids) -> set:
    from .handover import closed_offering_ids

    return {str(pk) for pk in closed_offering_ids(list(offering_ids))}


def recompute_absences(enrollments) -> None:
    from .gradebook import recompute_absence_hours_many

    rows = [row for row in enrollments if row is not None]
    if rows:
        recompute_absence_hours_many(rows)


class Relocator:
    def __init__(self, *, organization, actor, counts: Counter):
        self.organization = organization
        self.actor = actor
        self.counts = counts

    def run(self, items) -> None:
        for item in items:
            self.counts["items_in_file"] += 1
            try:
                with transaction.atomic():
                    self._item(item if isinstance(item, dict) else {})
            except IntegrityError:
                self.counts["item_integrity_error"] += 1

    def _item(self, item) -> None:
        Enrollment = _model("Enrollment")
        CourseOffering = _model("CourseOffering")
        Record = _model("StudentAcademicRecord")
        counts = self.counts
        source = (
            Enrollment.objects.select_for_update(of=("self",))
            .select_related("offering")
            .filter(organization=self.organization, pk=item.get("source"))
            .first()
        )
        if source is None or str(source.student_id) != str(item.get("student")):
            counts["source_missing"] += 1
            return
        target = CourseOffering.objects.filter(organization=self.organization, pk=item.get("target_offering")).first()
        if (
            target is None
            or target.pk == source.offering_id
            or target.subject_id != source.offering.subject_id
            or target.period_id != source.offering.period_id
        ):
            counts["target_invalid"] += 1
            return
        if not (target.is_active and source.offering.is_active) or closed([target.pk, source.offering_id]):
            counts["closed_or_inactive"] += 1
            return
        registry = set(
            Record.objects.filter(
                organization=self.organization, student_id=source.student_id, is_active=True
            ).values_list("group_id", flat=True)
        )
        if source.offering.group_id in registry and target.group_id not in registry:
            counts["registry_group_is_source"] += 1
            return
        moves = [row for row in item.get("moves") or [] if isinstance(row, dict)]
        restore = [row for row in item.get("restore") or [] if isinstance(row, dict)]
        pending_moves = self._live_moves(source, moves)
        if not pending_moves and not restore and (source.status != "enrolled" or not item.get("drop_source")):
            counts["item_already_done"] += 1
            return
        enrollment, created = target_enrollment(
            organization=self.organization,
            actor=self.actor,
            student_id=source.student_id,
            offering=target,
            counts=counts,
        )
        if enrollment is None:
            return
        if enrollment.status != "enrolled":
            counts["target_enrollment_not_enrolled"] += 1
            return
        moved, emptied = self._move(pending_moves, target, enrollment)
        restored = self._restore(restore, target, enrollment)
        deleted = delete_empty_lessons(emptied, counts)
        dropped = self._drop(source, item)
        if not (moved or restored or deleted or dropped or created):
            counts["item_noop"] += 1
            return
        recompute_absences([source, enrollment])
        counts["items_applied"] += 1
        log_action(
            action=AuditAction.UPDATE,
            user=self.actor,
            organization=self.organization,
            obj=source,
            reason=f"registrar: twin journal relocation — {REASON}",
            old_values={"offering": str(source.offering_id), "status": "enrolled" if dropped else source.status},
            new_values={
                "target_offering": str(target.pk),
                "target_enrollment": str(enrollment.pk),
                "target_enrollment_created": created,
                "marks_moved": moved,
                "absences_restored": restored,
                "lessons_deleted": deleted,
                "source_dropped": dropped,
                "absences_not_carried": True,
            },
        )

    def _live_moves(self, source, moves) -> list:
        LessonMark = _model("LessonMark")
        ids = [row.get("mark") for row in moves if row.get("mark")]
        marks = {
            str(mark.pk): mark
            for mark in LessonMark.objects.select_for_update(of=("self",))
            .select_related("lesson")
            .filter(pk__in=ids, enrollment=source)
        }
        self.counts["marks_already_moved"] += sum(1 for value in ids if str(value) not in marks)
        return [(marks[str(row["mark"])], row.get("lesson")) for row in moves if str(row.get("mark")) in marks]

    def _move(self, pending, target, enrollment) -> tuple[int, set]:
        LessonMark = _model("LessonMark")
        Lesson = _model("Lesson")
        counts = self.counts
        corrected = corrected_mark_ids([mark.pk for mark, _lesson in pending])
        lessons = {
            str(lesson.pk): lesson
            for lesson in Lesson.objects.filter(offering=target, pk__in=[pk for _mark, pk in pending if pk])
        }
        filled = set(
            LessonMark.objects.filter(enrollment=enrollment, lesson_id__in=list(lessons)).values_list(
                "lesson_id", flat=True
            )
        )
        filled = {str(pk) for pk in filled}
        moved, emptied = 0, set()
        for mark, lesson_id in pending:
            lesson = lessons.get(str(lesson_id))
            if str(mark.pk) in corrected:
                counts["mark_corrected_kept"] += 1
            elif lesson is None or lesson.date != mark.lesson.date:
                counts["target_lesson_invalid"] += 1
            elif str(lesson.pk) in filled:
                counts["target_cell_filled_kept"] += 1
            else:
                copy_mark(mark, lesson=lesson, enrollment=enrollment)
                filled.add(str(lesson.pk))
                emptied.add(mark.lesson_id)
                mark.delete()
                moved += 1
        counts["marks_moved"] += moved
        return moved, emptied

    def _restore(self, rows, target, enrollment) -> int:
        LessonMark = _model("LessonMark")
        Lesson = _model("Lesson")
        lessons = {
            str(lesson.pk): lesson
            for lesson in Lesson.objects.filter(offering=target, pk__in=[row.get("lesson") for row in rows])
        }
        taken = {
            str(pk)
            for pk in LessonMark.objects.filter(enrollment=enrollment, lesson_id__in=list(lessons)).values_list(
                "lesson_id", flat=True
            )
        }
        corrected = {
            str(pk)
            for pk in _model("JournalCorrection")
            .objects.filter(enrollment_ref=enrollment.pk, lesson_ref__in=list(lessons))
            .values_list("lesson_ref", flat=True)
        }
        restored = 0
        for row in rows:
            lesson = lessons.get(str(row.get("lesson")))
            status = row.get("status")
            if lesson is None or status not in RESTORE_STATUSES:
                self.counts["restore_invalid"] += 1
                continue
            if str(lesson.pk) in taken or str(lesson.pk) in corrected:
                self.counts["restore_cell_filled"] += 1
                continue
            created = LessonMark.objects.create(
                organization_id=lesson.organization_id, lesson=lesson, enrollment=enrollment, status=status
            )
            LessonMark.objects.filter(pk=created.pk).update(created_at=lesson.created_at)
            taken.add(str(lesson.pk))
            restored += 1
        self.counts["absences_restored"] += restored
        return restored

    def _drop(self, source, item) -> bool:
        if not item.get("drop_source") or source.status != "enrolled":
            return False
        if has_scores([source.pk]):
            self.counts["source_has_scores_kept"] += 1
            return False
        source.status = "dropped"
        source.save(update_fields=["status", "updated_at"])
        self.counts["sources_dropped"] += 1
        return True


__all__ = [
    "FORMAT",
    "RESTORE_STATUSES",
    "Relocator",
    "copy_mark",
    "corrected_lesson_ids",
    "corrected_mark_ids",
    "delete_empty_lessons",
    "has_scores",
    "target_enrollment",
]
