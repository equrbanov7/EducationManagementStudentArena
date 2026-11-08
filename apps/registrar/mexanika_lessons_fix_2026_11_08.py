"""Mexanika jurnallarının dərs düzəlişi (sahib 2026-11-08) — ``fix_mexanika_lessons_20261108``.

Sübut köhnə sistemdəndir; plan modulun yanındakı JSON-dur və YALNIZ id / tarix / saat / növdür::

    {"format": "mexanika-lessons/1",
     "kind_changes": [{"offering": uuid, "date": "2026-09-18", "start_time": "10:10", "from": "seminar", "to": "lab"}],
     "moves": [{"source": uuid, "target": uuid, "remove_source_instructor": true,
                "lessons": [{"date": "2026-09-25", "start_time": "13:35", "kind": "lecture"}]}]}

Dərs HƏMİŞƏ (açılış, tarix, başlama saatı, növ) ilə tapılır — prod bazası buradan görünmür, ona görə tapılmayan
dərs ``missing`` sayılır (təxmin YOXDUR), iki uyğun dərs ``*_ambiguous``.

A. **Növ dəyişməsi** — xanalar QALIR. Seminar da, lab da bal götürür (``gradebook.SCORE_LESSON_KINDS``); mühazirə
   götürmür: ballı xanası olan dərs mühazirəyə çevrilmir (``score_conflict``, xana silinmir). Lab qruplarına
   (Lab-1 / Lab-2) bölünmüş jurnalda qrupsuz lab dərsi yaranmır (``kind_lab_split_offering``) — köhnə sistemdə
   bütün qrupun BİR lab jurnalı idi; alt qruplu dərs (``lab_group`` / ``seminar_group``) toxunulmur. Rəsmi dərs
   düzəlişi (``LessonCorrection``) olan dərs toxunulmur. Cədvəl slotlarına toxunulmur (yalnız sayılır).
B. **Səhv jurnala düşmüş dərslər** — ``Lesson.offering`` və ``LessonMark.lesson/enrollment`` DB-də dəyişməzdir
   (0045), ona görə dərs hədəf açılışda YENİ sətir kimi yaradılır (``created_at`` köhnəsi — redaktə pəncərəsi
   açılmır), xanalar :func:`twin_relocate.copy_mark` ilə tələbənin HƏDƏF qeydiyyatına köçür, köhnə dərs silinir.
   Hədəfdə aktiv qeydiyyatı olmayan tələbə dərsi bloklayır (``move_student_not_enrolled``). Müəllim sahələri
   (``instructor`` və doluysa ``created_by``) hədəfin müəllimi olur; sillabus sətri hədəfin planından mövzu ilə
   yenidən tapılır (tapılmasa boş). Sonra mənbədən «yanlış» müəllim çıxarılır: hədəfin də müəllimi olan, mənbənin
   dərs yükündə OLMAYAN YEGANƏ müəllim (müəllim = ``offering.instructor`` ∪ aktiv ``JournalShare``); onun aktiv
   payı passiv olur. Açılışın sahibidirsə, mənbədə hələ dərsi varsa, plan dərsi mənbədə qalıbsa və ya namizəd
   yeganə deyilsə — toxunulmur, sayılır.

Qoruyucular: bağlı / passiv jurnal toxunulmur; hər bənd öz savepoint-indədir; qayıb saatı hər iki açılış üçün
yenidən hesablanır. Bütün dəyişiklik (köhnə dərsin bütün sahələri, xana xəritəsi, pay id-ləri) BİR audit
sətrindədir. ``--undo`` vəziyyətə baxır: düzəlişdən sonra xanası dəyişən dərs geri qaytarılmır
(``undo_marks_changed_blocked``), artıq köhnə vəziyyətdədirsə ``undo_already``. İdempotentdir.
"""

from __future__ import annotations

import datetime
import json
import uuid

from django.apps import apps as django_apps
from django.core.management.base import CommandError
from django.db import DatabaseError, transaction
from django.db.models import ProtectedError, Q
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from . import lab_groups
from .gradebook import SCORE_LESSON_KINDS
from .journal_topics import resolve_syllabus_week
from .schedule_slot_teachers import _workload_teacher_ids
from .twin_relocate import closed, copy_mark, corrected_lesson_ids, corrected_mark_ids, recompute_absences

FORMAT = "mexanika-lessons/1"
REASON = "Sahib 2026-11-08: Mexanika jurnalları — köhnə sistemə görə dərs növü və səhv jurnala düşmüş dərslər"
UNDO_REASON = "Sahib 2026-11-08: Mexanika jurnal düzəlişinin geri qaytarılması"
RESOURCE = "registrar.mexanika_lessons_fix"
KINDS = ("lecture", "seminar", "lab")
#: Dərsin köçürülən sahələri (id / açılış / ``created_at`` ayrıca).
FIELDS = (
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
    "lab_group",
    "seminar_group",
)


def _model(name, app="registrar"):
    return django_apps.get_model(app, name)


def load_plan(path) -> dict:
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        raise CommandError("mexanika_lessons_file_unreadable") from None
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise CommandError("mexanika_lessons_format_unknown")
    return data


def _slot(spec):
    try:
        return datetime.date.fromisoformat(str(spec.get("date"))), datetime.time.fromisoformat(
            str(spec.get("start_time"))
        )
    except (TypeError, ValueError):
        return None


def _find(organization, offering_id, day, start, kind) -> list:
    return list(
        _model("Lesson")
        .objects.select_for_update(of=("self",))
        .filter(organization=organization, offering_id=offering_id, date=day, start_time=start, kind=kind)
        .order_by("created_at")[:2]
    )


def _offerings(organization, ids) -> dict:
    rows = (
        _model("CourseOffering")
        .objects.select_for_update(of=("self",))
        .filter(organization=organization, pk__in=[value for value in ids if value])
        .order_by("pk")
    )
    return {str(row.pk): row for row in rows}


def _open(*offerings) -> bool:
    return all(row is not None and row.is_active for row in offerings) and not closed([row.pk for row in offerings])


def marks_state(lesson_id) -> dict:
    """``{xana id: [status, bal]}`` — geri qaytarmada «sonradan dəyişib?» yoxlaması üçün."""
    rows = _model("LessonMark").objects.filter(lesson_id=lesson_id).values_list("pk", "status", "score")
    return {str(pk): [status, None if score is None else str(score)] for pk, status, score in rows}


def _json(value):
    if isinstance(value, (datetime.date, datetime.time)):
        return value.isoformat()
    return str(value) if isinstance(value, uuid.UUID) else value


def _snapshot(lesson) -> dict:
    data = {name: _json(getattr(lesson, name)) for name in FIELDS}
    data.update(id=str(lesson.pk), offering=str(lesson.offering_id), created_at=lesson.created_at.isoformat())
    return data


def _fields(snapshot) -> dict:
    data = {name: snapshot.get(name) for name in FIELDS}
    data["date"] = datetime.date.fromisoformat(data["date"])
    for name in ("start_time", "end_time"):
        data[name] = datetime.time.fromisoformat(data[name]) if data[name] else None
    return data


def _rebuild(lesson, offering, fields, created_at, marks) -> tuple:
    """``lesson`` → ``offering``-də yeni sətir (``fields``), ``marks`` = ``[(xana, hədəf qeydiyyat)]``; köhnəsi silinir."""
    Lesson = _model("Lesson")
    new = Lesson.objects.create(organization_id=lesson.organization_id, offering=offering, **fields)
    Lesson.objects.filter(pk=new.pk).update(created_at=created_at)
    pairs = [(mark, copy_mark(mark, lesson=new, enrollment=enrollment)) for mark, enrollment in marks]
    lesson.delete()
    return new, pairs


def _seminar_slots(offering) -> int:
    return _model("ScheduleSlot").objects.filter(offering=offering, kind="seminar").count()


class Fixer:
    def __init__(self, *, organization, counts):
        self.organization = organization
        self.counts = counts
        self.items: list = []
        self.touched: dict = {}
        self.slot_checked: set = set()

    # ── A. növ ───────────────────────────────────────────────────────────────
    def kind(self, spec) -> None:
        counts = self.counts
        slot, frm, to = _slot(spec), spec.get("from"), spec.get("to")
        if slot is None or frm not in KINDS or to not in KINDS or frm == to:
            counts["kind_plan_invalid"] += 1
            return
        offering = _offerings(self.organization, [spec.get("offering")]).get(str(spec.get("offering")))
        if offering is None:
            counts["missing"] += 1
            counts["kind_offering_missing"] += 1
            return
        if not _open(offering):
            counts["kind_offering_closed"] += 1
            return
        found = _find(self.organization, offering.pk, *slot, frm)
        if not found:
            if _find(self.organization, offering.pk, *slot, to):
                counts["kind_already_done"] += 1
            else:
                counts["missing"] += 1
                counts["kind_missing"] += 1
            return
        if len(found) > 1:
            counts["kind_ambiguous"] += 1
            return
        lesson = found[0]
        if corrected_lesson_ids([lesson.pk]):
            counts["kind_lesson_corrected"] += 1
        elif lesson.lab_group or lesson.seminar_group:
            counts["kind_split_lesson_blocked"] += 1
        elif to == "lab" and lab_groups.offering_groups(offering):
            counts["kind_lab_split_offering"] += 1
        elif to not in SCORE_LESSON_KINDS and lesson.marks.filter(score__isnull=False).exists():
            counts["score_conflict"] += 1
        else:
            self._set_kind(lesson, offering, frm, to)

    def _set_kind(self, lesson, offering, frm, to) -> None:
        marks = marks_state(lesson.pk)
        try:
            with transaction.atomic():
                _model("Lesson").objects.filter(pk=lesson.pk).update(kind=to, updated_at=timezone.now())
        except DatabaseError:  # məs. dil kohortunun saat qoruyucusu (0111)
            self.counts["kind_db_rejected"] += 1
            return
        self.counts["kind_changed"] += 1
        self.counts[f"kind_changed_to_{to}"] += 1
        self.counts["kind_marks_kept"] += len(marks)
        if to == "lab" and offering.pk not in self.slot_checked:  # cədvəl slotu toxunulmur — açılış başına say
            self.slot_checked.add(offering.pk)
            self.counts["kind_seminar_slots_left"] += _seminar_slots(offering)
        self._touch(_model("Enrollment").objects.filter(lesson_marks__lesson_id=lesson.pk))
        self.items.append(
            {
                "type": "kind",
                "lesson": str(lesson.pk),
                "offering": str(offering.pk),
                "from": frm,
                "to": to,
                "marks": marks,
            }
        )

    # ── B. səhv jurnal ───────────────────────────────────────────────────────
    def move(self, spec) -> None:
        counts = self.counts
        rows = [row for row in spec.get("lessons") or [] if isinstance(row, dict)]
        counts["move_in_plan"] += len(rows)
        pair = _offerings(self.organization, [spec.get("source"), spec.get("target")])
        source, target = pair.get(str(spec.get("source"))), pair.get(str(spec.get("target")))
        if source is None or target is None or source.pk == target.pk:
            counts["missing"] += 1
            counts["move_offering_missing"] += 1
            return
        if (source.group_id, source.period_id) != (target.group_id, target.period_id):
            counts["move_offering_mismatch"] += 1
            return
        if not _open(source, target):
            counts["move_offering_closed"] += 1
            return
        roster = {
            row.student_id: row
            for row in _model("Enrollment")
            .objects.select_for_update(of=("self",))
            .filter(offering=target, status="enrolled")
        }
        pending = 0
        for row in rows:
            pending += self._move_one(row, source, target, roster)
        if spec.get("remove_source_instructor"):
            if pending:
                counts["instructor_kept_moves_pending"] += 1
            else:
                self._drop_instructor(source, target)

    def _move_one(self, row, source, target, roster) -> int:
        """Bir plan dərsi; dərs mənbədə QALIBSA 1 qaytarır."""
        counts = self.counts
        slot, kind = _slot(row), row.get("kind")
        if slot is None or kind not in KINDS:
            counts["move_plan_invalid"] += 1
            return 0
        found = _find(self.organization, source.pk, *slot, kind)
        taken = _find(self.organization, target.pk, *slot, kind)
        if not found:
            if taken:
                counts["move_already_done"] += 1
            else:
                counts["missing"] += 1
                counts["move_missing"] += 1
            return 0
        lesson = found[0]
        marks = list(lesson.marks.select_for_update(of=("self",)).select_related("enrollment"))
        unmapped = sum(1 for mark in marks if mark.enrollment.student_id not in roster)
        if len(found) > 1:
            counts["move_ambiguous"] += 1
        elif taken:
            counts["move_target_slot_taken"] += 1
        elif lesson.lab_group or lesson.seminar_group:
            counts["move_split_lesson_blocked"] += 1
        elif corrected_lesson_ids([lesson.pk]) or corrected_mark_ids([mark.pk for mark in marks]):
            counts["move_corrected_blocked"] += 1
        elif unmapped:
            counts["move_student_not_enrolled"] += unmapped
            counts["move_lessons_blocked"] += 1
        else:
            return 0 if self._relocate(lesson, target, marks, roster) else 1
        return 1

    def _relocate(self, lesson, target, marks, roster) -> bool:
        snapshot = _snapshot(lesson)
        fields = _fields(snapshot)
        fields.update(
            instructor_id=target.instructor_id,
            created_by_id=target.instructor_id if lesson.created_by_id else None,
            syllabus_week=resolve_syllabus_week(target, lesson.topic) if lesson.topic else None,
            lab_group=None,
            seminar_group=None,
        )
        try:
            with transaction.atomic():
                new, pairs = _rebuild(
                    lesson, target, fields, lesson.created_at, [(m, roster[m.enrollment.student_id]) for m in marks]
                )
        except (DatabaseError, ProtectedError):
            self.counts["move_db_rejected"] += 1
            return False
        counts = self.counts
        counts["moved_lessons"] += 1
        counts["moved_marks"] += len(pairs)
        if lesson.syllabus_week and fields["syllabus_week"] is None:
            counts["move_syllabus_week_cleared"] += 1
        self._touch([mark.enrollment for mark, _copy in pairs] + [copy.enrollment for _mark, copy in pairs])
        self.items.append(
            {
                "type": "move",
                "lesson": snapshot,
                "new_lesson": str(new.pk),
                "target": str(target.pk),
                "marks": [
                    {
                        "old": str(mark.pk),
                        "new": str(copy.pk),
                        "from_enrollment": str(mark.enrollment_id),
                        "to_enrollment": str(copy.enrollment_id),
                        "status": mark.status,
                        "score": None if mark.score is None else str(mark.score),
                    }
                    for mark, copy in pairs
                ],
            }
        )
        return True

    def _drop_instructor(self, source, target) -> None:
        counts = self.counts
        JournalShare = _model("JournalShare")

        def teachers(offering) -> set:
            shares = JournalShare.objects.filter(offering=offering, is_active=True).values_list("teacher_id", flat=True)
            return set(shares) | ({offering.instructor_id} if offering.instructor_id else set())

        workload = _workload_teacher_ids(source)
        if not workload:
            counts["instructor_source_no_workload"] += 1
            return
        candidates = (teachers(target) & teachers(source)) - workload
        if len(candidates) != 1:
            counts["instructor_ambiguous" if candidates else "instructor_not_found"] += 1
            return
        teacher_id = candidates.pop()
        if source.instructor_id == teacher_id:
            counts["instructor_is_owner_blocked"] += 1
        elif source.lessons.filter(Q(instructor_id=teacher_id) | Q(created_by_id=teacher_id)).exists():
            counts["instructor_has_lessons_kept"] += 1
        else:
            shares = [
                str(pk)
                for pk in JournalShare.objects.select_for_update()
                .filter(offering=source, teacher_id=teacher_id, is_active=True)
                .values_list("pk", flat=True)
            ]
            JournalShare.objects.filter(pk__in=shares).update(is_active=False, updated_at=timezone.now())
            counts["instructor_removed"] += 1
            counts["instructor_source_slots_left"] += (
                _model("ScheduleSlot").objects.filter(offering=source, instructor_id=teacher_id).count()
            )
            self.items.append(
                {"type": "instructor", "offering": str(source.pk), "teacher": teacher_id, "shares": shares}
            )

    def duplicate(self, spec) -> None:
        from .mexanika_lessons_dup_2026_11_08 import remove_duplicate

        remove_duplicate(self, spec)

    def _touch(self, enrollments) -> None:
        self.touched.update((row.pk, row) for row in enrollments)

    def finish(self, actor) -> None:
        recompute_absences(list(self.touched.values()))
        if not self.items:
            return
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=self.organization,
            new_values={key: value for key, value in sorted(self.counts.items())},
            changes={"items": self.items},
            reason=REASON,
            resource_type=RESOURCE,
            resource_id=timezone.now().strftime("%Y%m%d%H%M%S%f"),
        )


def run(*, organization, actor, counts, plan) -> None:
    fixer = Fixer(organization=organization, counts=counts)
    for spec in plan.get("kind_changes") or []:
        counts["kind_in_plan"] += 1
        with transaction.atomic():
            fixer.kind(spec if isinstance(spec, dict) else {})
    for spec in plan.get("moves") or []:
        with transaction.atomic():
            fixer.move(spec if isinstance(spec, dict) else {})
    for spec in plan.get("duplicates") or []:
        with transaction.atomic():
            fixer.duplicate(spec if isinstance(spec, dict) else {})
    fixer.finish(actor)


# ── geri qaytarma ────────────────────────────────────────────────────────────
class Undoer:
    def __init__(self, *, organization, counts):
        self.organization = organization
        self.counts = counts
        self.touched: dict = {}
        self.done: list = []

    def item(self, item) -> None:
        handler = {
            "kind": self._kind,
            "move": self._move,
            "instructor": self._instructor,
            "duplicate": self._duplicate,
        }.get(item.get("type"))
        if handler is None:
            self.counts["undo_item_unknown"] += 1
            return
        try:
            with transaction.atomic():
                handler(item)
        except (DatabaseError, ProtectedError):
            self.counts["undo_db_rejected"] += 1

    def _kind(self, item) -> None:
        Lesson = _model("Lesson")
        lesson = Lesson.objects.select_for_update(of=("self",)).filter(pk=item.get("lesson")).first()
        offering = _offerings(self.organization, [item.get("offering")]).get(str(item.get("offering")))
        if lesson is None:
            self.counts["undo_lesson_missing"] += 1
        elif lesson.kind == item.get("from"):
            self.counts["undo_already"] += 1
        elif not _open(offering):
            self.counts["undo_offering_closed"] += 1
        elif lesson.kind != item.get("to") or marks_state(lesson.pk) != item.get("marks"):
            self.counts["undo_marks_changed_blocked"] += 1
        else:
            Lesson.objects.filter(pk=lesson.pk).update(kind=item["from"], updated_at=timezone.now())
            self.counts["undo_kind_restored"] += 1
            self.done.append(item)

    def _move(self, item) -> None:
        Lesson, Enrollment = _model("Lesson"), _model("Enrollment")
        snapshot = item.get("lesson") or {}
        pair = _offerings(self.organization, [snapshot.get("offering"), item.get("target")])
        source, target = pair.get(str(snapshot.get("offering"))), pair.get(str(item.get("target")))
        lesson = Lesson.objects.select_for_update(of=("self",)).filter(pk=item.get("new_lesson")).first()
        expected = {row["new"]: [row["status"], row["score"]] for row in item.get("marks") or []}
        if lesson is None:
            self.counts["undo_already"] += 1
            return
        if source is None or target is None or not _open(source, target):
            self.counts["undo_offering_closed"] += 1
            return
        if marks_state(lesson.pk) != expected:
            self.counts["undo_marks_changed_blocked"] += 1
            return
        back = {row["new"]: row["from_enrollment"] for row in item.get("marks") or []}
        homes = {str(row.pk): row for row in Enrollment.objects.filter(pk__in=list(back.values()), offering=source)}
        marks = list(lesson.marks.select_related("enrollment"))
        if any(back[str(mark.pk)] not in homes for mark in marks):
            self.counts["undo_enrollment_missing"] += 1
            return
        created_at = datetime.datetime.fromisoformat(snapshot["created_at"])
        old, pairs = _rebuild(
            lesson, source, _fields(snapshot), created_at, [(m, homes[back[str(m.pk)]]) for m in marks]
        )
        self.counts["undo_lessons_moved_back"] += 1
        self.counts["undo_marks_moved_back"] += len(pairs)
        self.touched.update((row.pk, row) for row in homes.values())
        self.touched.update((mark.enrollment_id, mark.enrollment) for mark in marks)
        self.done.append({"type": "move", "lesson": str(lesson.pk), "restored_lesson": str(old.pk)})

    def _instructor(self, item) -> None:
        JournalShare = _model("JournalShare")
        offering = _offerings(self.organization, [item.get("offering")]).get(str(item.get("offering")))
        if not _open(offering):
            self.counts["undo_offering_closed"] += 1
            return
        if JournalShare.objects.filter(offering=offering, teacher_id=item.get("teacher"), is_active=True).exists():
            self.counts["undo_already"] += 1
            return
        restored = JournalShare.objects.filter(pk__in=item.get("shares") or [], is_active=False).update(
            is_active=True, updated_at=timezone.now()
        )
        if not restored:
            self.counts["undo_shares_missing"] += 1
            return
        self.counts["undo_instructor_restored"] += 1
        self.done.append(item)

    def _duplicate(self, item) -> None:
        from .mexanika_lessons_dup_2026_11_08 import restore_duplicate

        restore_duplicate(self, item)


def undo(*, organization, actor, counts) -> None:
    AuditLog = _model("AuditLog", app="audit")
    rows = AuditLog.objects.filter(organization=organization, resource_type=RESOURCE, reason=REASON).order_by(
        "-created_at"
    )
    undoer = Undoer(organization=organization, counts=counts)
    for row in rows:
        for item in reversed((row.changes or {}).get("items") or []):
            undoer.item(item if isinstance(item, dict) else {})
    recompute_absences(list(undoer.touched.values()))
    if undoer.done:
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            new_values={key: value for key, value in sorted(counts.items())},
            changes={"items": undoer.done},
            reason=UNDO_REASON,
            resource_type=RESOURCE,
            resource_id=timezone.now().strftime("%Y%m%d%H%M%S%f"),
        )


__all__ = ["FORMAT", "REASON", "RESOURCE", "load_plan", "marks_state", "run", "undo"]
