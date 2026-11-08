"""``fix_mexanika_lessons_20261108`` — C. dublikat dərs (sahib 2026-11-08 audit).

Plan bölməsi ``duplicates``: ``[{"offering", "date", "start_time", "kind", "twin_offering"?, "twin_date"?,
"twin_start_time"}]``. Dərs silinir YALNIZ onun hər xanası əkiz dərsdə HƏMİN tələbədə eyni (status, bal) ilə
varsa (tələbə id-si ilə müqayisə — əkiz başqa jurnalda da ola bilər); rəsmi düzəlişli dərs/xana toxunulmur. Əkizin
boş mövzu / otağı silinən dərsdən doldurulur. Silinən dərs və xanalar audit bəndində tam saxlanılır — geri qaytarma
onları eyni sahələrlə (``created_at`` daxil) yenidən yaradır.
"""

from __future__ import annotations

import datetime

from django.utils import timezone

from .mexanika_lessons_fix_2026_11_08 import KINDS, _fields, _find, _json, _model, _offerings, _open, _slot, _snapshot
from .twin_relocate import corrected_lesson_ids, corrected_mark_ids


def remove_duplicate(self, spec) -> None:
    """Dərs silinir YALNIZ hər xanası əkiz dərsdə həmin tələbədə EYNİ (status, bal) ilədirsə; boş əkizə mövzu/otaq."""
    counts = self.counts
    counts["dup_in_plan"] += 1
    twin_id = spec.get("twin_offering") or spec.get("offering")
    pair = _offerings(self.organization, [spec.get("offering"), twin_id])
    source, other = pair.get(str(spec.get("offering"))), pair.get(str(twin_id))
    slot = _slot(spec)
    twin_slot = _slot({"date": spec.get("twin_date") or spec.get("date"), "start_time": spec.get("twin_start_time")})
    kind = spec.get("kind")
    if slot is None or twin_slot is None or kind not in KINDS:
        counts["dup_invalid"] += 1
        return
    if not _open(source, other):
        counts["dup_offering_closed"] += 1
        return
    lessons = _find(self.organization, source.pk, *slot, kind)
    twins = _find(self.organization, other.pk, *twin_slot, kind)
    if not lessons or not twins:
        counts["dup_missing"] += 1
        return
    if len(lessons) > 1 or len(twins) > 1 or lessons[0].pk == twins[0].pk:
        counts["dup_ambiguous"] += 1
        return
    lesson, twin = lessons[0], twins[0]
    marks = list(lesson.marks.select_related("enrollment"))
    if corrected_lesson_ids([lesson.pk]) or corrected_mark_ids([mark.pk for mark in marks]):
        counts["dup_corrected_kept"] += 1
        return
    theirs = {mark.enrollment.student_id: (mark.status, mark.score) for mark in twin.marks.select_related("enrollment")}
    if any(theirs.get(mark.enrollment.student_id) != (mark.status, mark.score) for mark in marks):
        counts["dup_marks_differ_kept"] += 1
        return
    filled = {}
    for name in ("topic", "room_id"):
        if getattr(lesson, name) and not getattr(twin, name):
            filled[name] = _json(getattr(lesson, name))
    if filled:
        _model("Lesson").objects.filter(pk=twin.pk).update(**filled, updated_at=timezone.now())
        counts["dup_twin_topic_room_filled"] += 1
    item = {
        "type": "duplicate",
        "lesson": _snapshot(lesson),
        "twin": str(twin.pk),
        "twin_filled": filled,
        "marks": [
            {
                "enrollment": str(mark.enrollment_id),
                "status": mark.status,
                "score": None if mark.score is None else str(mark.score),
                "entered_by": mark.entered_by_id,
                "created_at": mark.created_at.isoformat(),
            }
            for mark in marks
        ],
    }
    self._touch([mark.enrollment for mark in marks])
    lesson.delete()
    counts["dup_lessons_deleted"] += 1
    counts["dup_marks_deleted_same_in_twin"] += len(marks)
    self.items.append(item)


def restore_duplicate(self, item) -> None:
    Lesson, LessonMark, Enrollment = _model("Lesson"), _model("LessonMark"), _model("Enrollment")
    snapshot = item.get("lesson") or {}
    offering = _offerings(self.organization, [snapshot.get("offering")]).get(str(snapshot.get("offering")))
    if Lesson.objects.filter(pk=snapshot.get("id")).exists():
        self.counts["undo_already"] += 1
        return
    if not _open(offering):
        self.counts["undo_offering_closed"] += 1
        return
    homes = {
        str(row.pk): row
        for row in Enrollment.objects.filter(
            pk__in=[row["enrollment"] for row in item.get("marks") or []], offering=offering
        )
    }
    if len(homes) != len({row["enrollment"] for row in item.get("marks") or []}):
        self.counts["undo_enrollment_missing"] += 1
        return
    lesson = Lesson.objects.create(organization=self.organization, offering=offering, **_fields(snapshot))
    Lesson.objects.filter(pk=lesson.pk).update(created_at=datetime.datetime.fromisoformat(snapshot["created_at"]))
    for row in item.get("marks") or []:
        mark = LessonMark.objects.create(
            organization=self.organization,
            lesson=lesson,
            enrollment=homes[row["enrollment"]],
            status=row["status"],
            score=row["score"],
            entered_by_id=row.get("entered_by"),
        )
        LessonMark.objects.filter(pk=mark.pk).update(created_at=datetime.datetime.fromisoformat(row["created_at"]))
    twin = Lesson.objects.filter(pk=item.get("twin")).first()
    filled = item.get("twin_filled") or {}
    if twin is not None and filled and all(str(getattr(twin, name) or "") == str(v) for name, v in filled.items()):
        Lesson.objects.filter(pk=twin.pk).update(**{name: None if name == "room_id" else "" for name in filled})
    self.touched.update((row.pk, row) for row in homes.values())
    self.counts["undo_duplicates_restored"] += 1
    self.done.append({"type": "duplicate", "restored_lesson": str(lesson.pk)})


def remove_share(self, spec) -> None:
    """D. Yükdə OLMAYAN müəllimin aktiv payı passiv olur (jurnal sahibi deyilsə, dərsi yoxdursa) — data qalır."""
    from django.db.models import Q

    from .schedule_slot_teachers import _workload_teacher_ids

    counts = self.counts
    counts["share_in_plan"] += 1
    JournalShare = _model("JournalShare")
    offering = _offerings(self.organization, [spec.get("offering")]).get(str(spec.get("offering")))
    teacher_id = spec.get("teacher")
    if not _open(offering):
        counts["share_offering_closed"] += 1
        return
    workload = _workload_teacher_ids(offering)
    if not workload or teacher_id in workload:
        counts["share_teacher_in_workload_kept"] += 1
        return
    if offering.instructor_id == teacher_id:
        counts["share_teacher_is_owner_kept"] += 1
        return
    if offering.lessons.filter(Q(instructor_id=teacher_id) | Q(created_by_id=teacher_id)).exists():
        counts["share_teacher_has_lessons_kept"] += 1
        return
    shares = [
        str(pk)
        for pk in JournalShare.objects.select_for_update()
        .filter(offering=offering, teacher_id=teacher_id, is_active=True)
        .values_list("pk", flat=True)
    ]
    if not shares:
        counts["share_already_inactive"] += 1
        return
    JournalShare.objects.filter(pk__in=shares).update(is_active=False, updated_at=timezone.now())
    counts["share_removed"] += 1
    self.items.append({"type": "instructor", "offering": str(offering.pk), "teacher": teacher_id, "shares": shares})


def trim_roster(self, spec) -> None:
    """E. Jurnalda yalnız ``keep`` qeydiyyatları qalır; qalanlar ``dropped`` olur — YALNIZ heç bir xanası, balı,
    yekun nəticəsi yoxdursa (data itmir); xanalı sətir qalır və sayılır."""
    counts = self.counts
    Enrollment = _model("Enrollment")
    offering = _offerings(self.organization, [spec.get("offering")]).get(str(spec.get("offering")))
    keep = {str(pk) for pk in spec.get("keep") or []}
    if not _open(offering) or not keep:
        counts["trim_invalid"] += 1
        return
    rows = list(Enrollment.objects.select_for_update().filter(offering=offering, status="enrolled"))
    if not keep <= {str(row.pk) for row in rows}:
        counts["trim_keep_missing"] += 1
        return
    dropped = []
    for row in rows:
        if str(row.pk) in keep:
            continue
        if any(
            _model(name).objects.filter(enrollment=row).exists()
            for name in ("LessonMark", "ComponentScore", "FinalGrade", "CourseWork", "CriterionScore")
        ):
            counts["trim_row_has_data_kept"] += 1
            continue
        dropped.append(str(row.pk))
    Enrollment.objects.filter(pk__in=dropped).update(status="dropped", updated_at=timezone.now())
    counts["trim_dropped"] += len(dropped)
    if dropped:
        self.items.append({"type": "trim", "offering": str(offering.pk), "dropped": dropped})


def restore_trim(self, item) -> None:
    Enrollment = _model("Enrollment")
    offering = _offerings(self.organization, [item.get("offering")]).get(str(item.get("offering")))
    if not _open(offering):
        self.counts["undo_offering_closed"] += 1
        return
    restored = Enrollment.objects.filter(
        pk__in=item.get("dropped") or [], offering=offering, status="dropped", superseded_by__isnull=True
    ).update(status="enrolled", updated_at=timezone.now())
    self.counts["undo_trim_restored"] += restored
    self.done.append(item)
