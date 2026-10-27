"""Yanlış fənn adı altında qalmış «əkiz» açılışın rəsmi açılışa birləşdirilməsi — ``merge_twin_offerings``.

RİM 2026-10-27 (MR-26, MR-29, MR-30.3; ``LEGACY_DELTA_2026_10`` §10.4 — ~25 hal): fənn KODU toqquşması ilə köhnə
sistemin jurnalı (dərs, xana, sillabus) eyni qrup + dövrdə BAŞQA fənnin kartındakı açılışa (W) düşüb, düzgün fənnin
rəsmi açılışı (T — cədvəl slotları, dərs yükü) isə boşdur. Unikal açar (fənn, dövr, qrup) W-nin fənnini dəyişməyə imkan
vermir (``subject_collisions`` fazası əkizə qəsdən toxunmur) — ona görə data T-yə KÖÇÜRÜLÜR, W ləğv olunur.

Plan (lokal, YALNIZ id-lər): ``{"format": "twin-merge/1", "pairs": [{"source": W uuid, "target": T uuid}]}``.

Qaydalar (hər cüt öz savepoint-ində; hər şey kilid altında yenidən yoxlanılır):

* W və T eyni dövr + qrup, fənləri fərqli, ikisi də aktiv, heç biri bağlı deyil;
* T-də ARTIQ xana varsa (hər iki tərəfdə real data) — birləşdirilmir, sayılır (hesabat: ``both_have_marks``);
* W-də rəsmi düzəlişli xana / dərs, yekun qiymət və ya komponent balı varsa, ya da W-yə registrar/sillabus
  xaricindən istinad (imtahan, qovluq, sorğu …) varsa — toxunulmur, sayılır;
* qeydiyyat: W-nin hər tələbəsi üçün T-də sətir (varsa o, yoxdursa yaradılır — W sətrinin növü/mənbə qrupu ilə);
* dərs: T-də eyni tarix + saat + növdə dərs varsa ona, yoxdursa T-də eyni sahələrlə YENİ dərs (``created_at`` də
  köhnə — müəllimin redaktə pəncərəsi açılmır); xanalar yeni sətir kimi (``created_at`` köhnə), W dərsi silinir;
* sillabus: W-nin sillabusu T-yə (T-nin sillabusu yoxdursa; bağlı «reuse» zənciri yoxdursa) — fənni də T-ninki olur;
* cədvəl: T-nin canlı slotu VARSA W-nin slotları yumşaq silinir; YOXDURSA W-nin slotları T-yə köçürülür (yeni sətir,
  eyni gün/saat/növ/həftə/otaq, W-ninki yumşaq silinir). T-nin dərs yükünə toxunulmur; W adına açılmış yük sətri
  yalnız SAYILIR (``wrong_load_rows`` — kafedra/tədris şöbəsi qərarı);
* W qeydiyyatları ``dropped`` (fənn fərqlidir — ``superseded_by`` mümkün deyil), W ``is_active=False``;
* qayıb saatı yenidən hesablanır; W və T üçün audit.

İdempotentdir: ikinci qaçışda W passivdir → cüt ``already_merged`` sayılır, 0 yazı.
"""

from __future__ import annotations

from collections import Counter

from django.apps import apps as django_apps
from django.db import IntegrityError, transaction
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from .twin_relocate import closed, copy_mark, corrected_lesson_ids, corrected_mark_ids, has_scores, recompute_absences

FORMAT = "twin-merge/1"
REASON = "Əkiz açılış birləşməsi: köhnə sistemin jurnalı yanlış fənn adı altında idi — RİM 2026-10-27 (MR-26/29/30)"
_INTERNAL_APPS = ("registrar", "syllabus", "workload")
_LESSON_FIELDS = (
    "date",
    "kind",
    "topic",
    "syllabus_week",
    "hours",
    "start_time",
    "end_time",
    "created_by_id",
    "instructor_id",
    "room_id",
    "is_legacy_synthesised",
    "off_schedule_reason",
)
_SLOT_FIELDS = ("weekday", "start_time", "end_time", "room", "week_type", "kind", "created_by_id", "instructor_id")


def _model(name: str, app: str = "registrar"):
    return django_apps.get_model(app, name)


def linked_elsewhere(offering) -> str:
    """W-yə registrar / sillabus / dərs yükü xaricindən istinad (imtahan, qovluq, sorğu …) — modelin adı."""

    for relation in offering._meta.related_objects:
        model = relation.related_model
        if model._meta.app_label in _INTERNAL_APPS or model._meta.auto_created:
            continue
        if model._base_manager.filter(**{relation.field.name: offering}).exists():
            return model._meta.model_name
    return ""


class Merger:
    def __init__(self, *, organization, actor, counts: Counter):
        self.organization = organization
        self.actor = actor
        self.counts = counts

    def run(self, pairs) -> None:
        for pair in pairs:
            self.counts["pairs_in_file"] += 1
            try:
                with transaction.atomic():
                    self._pair(pair if isinstance(pair, dict) else {})
            except IntegrityError:
                self.counts["pair_integrity_error"] += 1

    # ── yoxlamalar ────────────────────────────────────────────────────────
    def _blocked(self, source, target) -> str:
        Lesson, LessonMark, Enrollment = _model("Lesson"), _model("LessonMark"), _model("Enrollment")
        if (
            source.pk == target.pk
            or source.period_id != target.period_id
            or source.group_id != target.group_id
            or source.subject_id == target.subject_id
        ):
            return "pair_invalid"
        if not source.is_active:
            return "already_merged"
        if not target.is_active or closed([source.pk, target.pk]):
            return "closed_or_inactive"
        if LessonMark.objects.filter(lesson__offering=target).exists():
            return "both_have_marks"
        lesson_ids = list(Lesson.objects.filter(offering=source).values_list("pk", flat=True))
        mark_ids = LessonMark.objects.filter(lesson__offering=source).values_list("pk", flat=True)
        if corrected_lesson_ids(lesson_ids) or corrected_mark_ids(list(mark_ids)):
            return "source_corrected"
        if has_scores(Enrollment.objects.filter(offering=source).values_list("pk", flat=True)):
            return "source_has_scores"
        if linked_elsewhere(source):
            return "source_linked_elsewhere"
        return ""

    def _pair(self, pair) -> None:
        CourseOffering = _model("CourseOffering")
        offerings = {
            str(row.pk): row
            for row in CourseOffering.objects.select_for_update(of=("self",)).filter(
                organization=self.organization, pk__in=[pair.get("source"), pair.get("target")]
            )
        }
        source, target = offerings.get(str(pair.get("source"))), offerings.get(str(pair.get("target")))
        if source is None or target is None:
            self.counts["pair_missing"] += 1
            return
        blocked = self._blocked(source, target)
        if blocked:
            self.counts[blocked] += 1
            return
        enrollments, created = self._enrollments(source, target)
        if enrollments is None:
            self.counts["target_enrollment_blocked"] += 1
            transaction.set_rollback(True)
            return
        lessons_new, lessons_reused, marks = self._lessons(source, target, enrollments)
        syllabus = self._syllabus(source, target)
        slots = self._slots(source, target)
        dropped = self._drop(source)
        wrong_rows = self._wrong_load_rows(source)
        recompute_absences(list({row.pk: row for row in enrollments.values()}.values()))
        self.counts["pairs_merged"] += 1
        summary = {
            "source": str(source.pk),
            "target": str(target.pk),
            "source_subject": str(source.subject_id),
            "target_subject": str(target.subject_id),
            "enrollments_created": created,
            "lessons_created": lessons_new,
            "lessons_reused": lessons_reused,
            "marks_moved": marks,
            "syllabus": syllabus,
            "slots": slots,
            "source_enrollments_dropped": dropped,
            "wrong_load_rows_kept": wrong_rows,
        }
        for obj, old in ((source, {"is_active": True}), (target, {})):
            log_action(
                action=AuditAction.UPDATE,
                user=self.actor,
                organization=self.organization,
                obj=obj,
                reason=f"registrar: twin offering merge — {REASON}",
                old_values=old,
                new_values=summary,
            )

    # ── köçürmə ───────────────────────────────────────────────────────────
    def _enrollments(self, source, target):
        """``{W qeydiyyat id → T qeydiyyatı}`` + yaradılanların sayı (DB qapısı rədd etsə ``None``)."""

        Enrollment = _model("Enrollment")
        existing = {row.student_id: row for row in Enrollment.objects.select_for_update().filter(offering=target)}
        out, created = {}, 0
        for row in Enrollment.objects.select_for_update().filter(offering=source).order_by("created_at", "pk"):
            if row.status != "enrolled" and not row.lesson_marks.exists():
                continue
            found = existing.get(row.student_id)
            if found is None:
                guest = row.source_group_id is not None and row.source_group_id != target.group_id
                try:
                    with transaction.atomic():
                        found = Enrollment.objects.create(
                            organization=self.organization,
                            student_id=row.student_id,
                            offering=target,
                            kind=row.kind,
                            status="enrolled" if row.status == "enrolled" else row.status,
                            source_group_id=row.source_group_id if guest else None,
                            added_by=self.actor if guest else None,
                            added_at=timezone.now() if guest else None,
                        )
                except IntegrityError:
                    return None, 0
                existing[row.student_id] = found
                created += 1
            out[row.pk] = found
        self.counts["enrollments_created"] += created
        return out, created

    def _lessons(self, source, target, enrollments) -> tuple[int, int, int]:
        Lesson = _model("Lesson")
        by_slot = {}
        for lesson in Lesson.objects.select_for_update().filter(offering=target).order_by("created_at"):
            by_slot.setdefault((lesson.date, lesson.start_time, lesson.kind), lesson)
        created = reused = moved = 0
        for lesson in Lesson.objects.select_for_update().filter(offering=source).order_by("date", "start_time"):
            key = (lesson.date, lesson.start_time, lesson.kind)
            twin = by_slot.get(key)
            if twin is None:
                twin = Lesson.objects.create(
                    organization=self.organization,
                    offering=target,
                    **{name: getattr(lesson, name) for name in _LESSON_FIELDS},
                )
                Lesson.objects.filter(pk=twin.pk).update(created_at=lesson.created_at)
                by_slot[key] = twin
                created += 1
            else:
                reused += 1
            for mark in lesson.marks.all().order_by("created_at"):
                enrollment = enrollments.get(mark.enrollment_id)
                if enrollment is None:
                    self.counts["mark_without_target_enrollment"] += 1
                    continue
                copy_mark(mark, lesson=twin, enrollment=enrollment)
                moved += 1
            lesson.delete()  # qalan (hədəfsiz) xanalar kaskadla — sayılıb
        self.counts["lessons_created"] += created
        self.counts["lessons_reused"] += reused
        self.counts["marks_moved"] += moved
        return created, reused, moved

    def _syllabus(self, source, target) -> str:
        Syllabus = _model("Syllabus", "syllabus")
        rows = list(Syllabus.objects.select_for_update().filter(organization=self.organization, offering=source))
        if not rows:
            return "none"
        if Syllabus.objects.filter(organization=self.organization, offering=target).exists():
            self.counts["syllabus_target_exists_kept"] += 1
            return "target_exists"
        row = rows[0]
        if row.reused_from_id is not None or Syllabus.objects.filter(reused_from=row).exists():
            self.counts["syllabus_reuse_chain_kept"] += 1
            return "reuse_chain"
        Syllabus.objects.filter(pk=row.pk).update(
            offering=target, subject_id=target.subject_id, updated_at=timezone.now()
        )
        self.counts["syllabi_moved"] += 1
        return "moved"

    def _slots(self, source, target) -> str:
        from .schedule_lock import lock_schedule

        ScheduleSlot = _model("ScheduleSlot")
        own = list(ScheduleSlot.objects.select_for_update().filter(offering=source))
        if not own:
            return "none"
        lock_schedule(self.organization.pk, source.period_id)
        now = timezone.now()
        keep_target = ScheduleSlot.objects.filter(offering=target).exists()
        ScheduleSlot.all_objects.filter(pk__in=[slot.pk for slot in own]).update(
            is_deleted=True, deleted_at=now, updated_at=now
        )
        self.counts["slots_soft_deleted"] += len(own)
        if keep_target:
            return "target_kept"
        for slot in own:
            ScheduleSlot.objects.create(
                organization=self.organization,
                offering=target,
                is_parked=slot.is_parked,
                **{name: getattr(slot, name) for name in _SLOT_FIELDS},
            )
        self.counts["slots_moved"] += len(own)
        return "moved"

    def _drop(self, source) -> int:
        Enrollment = _model("Enrollment")
        dropped = Enrollment.objects.filter(offering=source, status="enrolled").update(
            status="dropped", updated_at=timezone.now()
        )
        source.is_active = False
        source.save(update_fields=["is_active", "updated_at"])
        self.counts["source_enrollments_dropped"] += dropped
        self.counts["offerings_cancelled"] += 1
        return dropped

    def _wrong_load_rows(self, source) -> int:
        Row = _model("TeachingTaskRow", "workload")
        count = (
            Row.objects.filter(
                organization=self.organization,
                subject_id=source.subject_id,
                period_id=source.period_id,
                groups=source.group_id,
            )
            .distinct()
            .count()
        )
        self.counts["wrong_load_rows_kept"] += count
        return count


__all__ = ["FORMAT", "Merger", "linked_elsewhere"]
