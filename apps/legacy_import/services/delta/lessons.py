"""Dərslər (``Lesson``) + jurnal xanaları (``LessonMark``) — YALNIZ ƏLAVƏ, heç vaxt üzərinə yazmır.

Dərs
    Legacy dərs tarixi (``journals_dates_added_by_teacher``: ay, gün, saat) + jurnalın semestri → tarix.
    Növ cutover J3 qaydası ilə: eyni slotdakı xanaların ``lab``/``sem_muh`` səsverməsi (lab → laboratoriya,
    1 → mühazirə, 0/2/3 → seminar); xana yoxdursa dərs sətrinin ``sem_muh``-u. Saat 2 (1 dərs = 2 saat).
    Açılışda eyni tarix + saatda dərs VARSA o istifadə olunur; yeni sistemdə əvvəlcədən açılmış eyni gün +
    eyni növ dərs (başqa saatda) bir legacy slotunu udur — ikiqat qayıb saatının qarşısı alınır.
    ``--lessons-until``-dan SONRAKI tarixlər (gələcək) atılır. Xanası olub dərs sətri olmayan slot cutover
    J12 kimi ``is_legacy_synthesised=True`` ilə bərpa olunur.

Xana
    ``ie`` → iştirak, ``qb`` → qayıb (``excusable=1`` və ya üzrlü pəncərədə → üzrlü), 0–10 → iştirak + bal.
    Boş xana yazılmır; 10-dan böyük / naməlum dəyər karantindir (sayılır). Eyni xananın təkrarlarından J-V4
    qalibi (``update_counter`` → ``updated_at`` → ``id``). (dərs, qeydiyyat) üçün xana VARSA toxunulmur.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.apps import apps as django_apps

from ..rehearsal_journal_lesson_kinds import LECTURE, cell_kind
from .resolve import lesson_date

CALENDAR = {f"{month:02d}" for month in range(1, 13)}
MAX_SCORE = 10


def _time(value):
    text = str(value or "")[:5]
    try:
        return datetime.time.fromisoformat(text) if len(text) == 5 else None
    except ValueError:
        return None


def _int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def winning_cells(points) -> list:
    """J-V4: (jurnal, ay, gün, tələbə, saat) üzrə bir qalib — ``update_counter`` → ``updated_at`` → ``id``."""

    best: dict = {}
    for row in points:
        key = (row["journal_uniqid"], row["month_id"], str(row["day_number"]), row["student_id"], str(row["time"])[:5])
        rank = (_int(row.get("update_counter")), str(row.get("updated_at") or ""), row["id"])
        if key not in best or rank > best[key][0]:
            best[key] = (rank, row)
    return [row for _rank, row in best.values()]


def mark_value(point: str):
    """``(status, score, outcome)``; ``status`` boşdursa xana yazılmır."""

    token = str(point or "").strip().lower()
    if not token:
        return "", None, "blank"
    if token == "ie":
        return "present", None, "present"
    if token == "qb":
        return "absent", None, "absent"
    if token.isdigit():
        value = int(token)
        if value > MAX_SCORE:
            return "", None, "score_out_of_range"
        return "present", Decimal(value), "score"
    return "", None, "unknown_token"


class LessonBook:
    """(açılış, tarix, saat) → ``Lesson``; mövcudu tapır, çatışmayanı növbəyə qoyur.

    Eyni gün + eyni növdə, amma BAŞQA saatda olan dərs yalnız YENİ SİSTEMDƏ ƏVVƏLCƏDƏN VAR olan dərsdirsə
    (müəllim jurnalı yeni sistemdə açıb) legacy slotu ona bağlanır — hər mövcud dərs ən çox BİR legacy
    slotunu udur. Legacy-nin öz cüt dərsləri (eyni gün iki para) ayrı-ayrı dərs kimi qalır.
    """

    def __init__(self, run, offering_ids):
        Lesson = django_apps.get_model("registrar", "Lesson")
        self.run = run
        self.Lesson = Lesson
        self.by_slot: dict = {}
        self.unclaimed: dict = {}
        for lesson in Lesson.objects.filter(organization=run.organization, offering_id__in=list(offering_ids)).order_by(
            "date", "start_time", "created_at"
        ):
            self.by_slot[(lesson.offering_id, lesson.date, lesson.start_time)] = lesson
            self.unclaimed.setdefault((lesson.offering_id, lesson.date, lesson.kind), []).append(lesson)
        self.pending: list = []

    def ensure(self, offering_id, date, start, kind, *, synthesised: bool):
        found = self.by_slot.get((offering_id, date, start))
        if found is not None:
            self._claim(found)
            return found
        same_day = self.unclaimed.get((offering_id, date, kind))
        if same_day:
            found = same_day.pop(0)
            self.run.count("lesson.merged_existing_same_day")
            self.by_slot[(offering_id, date, start)] = found
            return found
        lesson = self.Lesson(
            organization=self.run.organization,
            offering_id=offering_id,
            date=date,
            kind=kind,
            hours=2,
            start_time=start,
            topic="",
            is_legacy_synthesised=synthesised,
        )
        self.by_slot[(offering_id, date, start)] = lesson
        self.pending.append(lesson)
        self.run.count("lesson.created_synthesised" if synthesised else "lesson.created")
        return lesson

    def _claim(self, lesson) -> None:
        bucket = self.unclaimed.get((lesson.offering_id, lesson.date, lesson.kind))
        if bucket and lesson in bucket:
            bucket.remove(lesson)

    def flush(self) -> None:
        self.run.bulk_create(self.Lesson, self.pending, "lessons")
        self.pending = []


def build_lessons_and_marks(run, slices: dict, enrollments: dict, *, until: datetime.date) -> None:
    LessonMark = django_apps.get_model("registrar", "LessonMark")
    journals_by_id = {entry.journal["id"]: entry for entry in slices.values()}
    cells = winning_cells(run.bundle["points"])
    run.count("cell.duplicates_dropped", len(run.bundle["points"]) - len(cells))
    votes: dict = {}
    for row in cells:
        if row["month_id"] in CALENDAR:
            kind = cell_kind(lab=_int(row.get("lab")), sem_muh=_int(row.get("sem_muh")))
            if kind:
                slot = (row["journal_uniqid"], int(row["month_id"]), _int(row["day_number"]), str(row["time"])[:5])
                votes.setdefault(slot, {}).setdefault(kind, 0)
                votes[slot][kind] += 1

    def slot_kind(slot, fallback_sem_muh=None):
        counts = votes.get(slot)
        if counts:
            return max(sorted(counts), key=lambda kind: (counts[kind], kind == "lab", kind == "seminar"))
        if fallback_sem_muh is not None:
            return cell_kind(lab=0, sem_muh=_int(fallback_sem_muh)) or LECTURE
        return LECTURE

    old_enrollments = run.ledger_enrollments(
        {(row["journal_uniqid"], row["student_id"]) for row in cells if row["journal_uniqid"] not in slices}
    )
    offering_ids = {offering.pk for entry in slices.values() for offering in entry.offerings}
    offering_ids |= {enrollment.offering_id for enrollment in enrollments.values()}
    offering_ids |= {enrollment.offering_id for enrollment in old_enrollments.values()}
    book = LessonBook(run, offering_ids)
    writable = run.writable_offerings(offering_ids)
    dated_slots = set()
    # 1) legacy dərs cədvəli — jurnalın HƏR dilimində
    for row in run.bundle["lesson_dates"]:
        entry = journals_by_id.get(row["journal_id"])
        if entry is None:
            continue
        period = run.period_of(entry.journal["semestr"])
        date = lesson_date(period, _int(row["month"]), _int(row["day"])) if period else None
        start = _time(row["time"])
        if date is None or start is None:
            run.count("lesson.date_invalid")
            continue
        if date > until:
            run.count("lesson.future_skipped")
            continue
        slot = (entry.journal["uniqid"], _int(row["month"]), _int(row["day"]), str(row["time"])[:5])
        dated_slots.add(slot)
        for offering in entry.offerings:
            if offering.pk in writable:
                book.ensure(offering.pk, date, start, slot_kind(slot, row.get("sem_muh")), synthesised=False)
    # 2) xanalar
    existing_marks = {
        (lesson_id, enrollment_id): (status, score)
        for lesson_id, enrollment_id, status, score in LessonMark.objects.filter(
            organization=run.organization, lesson__offering_id__in=list(offering_ids)
        ).values_list("lesson_id", "enrollment_id", "status", "score")
    }
    excuse = run.excuse_index()
    pending, touched = [], {}
    for row in cells:
        month = row["month_id"]
        if month not in CALENDAR:
            run.count(f"cell.non_calendar.{month}")
            continue
        uniqid, legacy_sid = row["journal_uniqid"], row["student_id"]
        enrollment = enrollments.get((uniqid, legacy_sid)) or old_enrollments.get((uniqid, legacy_sid))
        if enrollment is None:
            run.count("cell.enrollment_unresolved")
            continue
        if enrollment.offering_id not in writable:
            run.count("cell.offering_closed")
            continue
        status, score, outcome = mark_value(row["point"])
        run.count(f"cell.{outcome}")
        if not status:
            continue
        period = run.period_of_offering(enrollment.offering_id)
        date = lesson_date(period, int(month), _int(row["day_number"])) if period else None
        start = _time(row["time"])
        if date is None or start is None:
            run.count("cell.date_invalid")
            continue
        if date > until:
            run.count("cell.future_skipped")
            continue
        slot = (uniqid, int(month), _int(row["day_number"]), str(row["time"])[:5])
        lesson = book.ensure(enrollment.offering_id, date, start, slot_kind(slot), synthesised=slot not in dated_slots)
        if status == "absent" and (_int(row.get("excusable")) == 1 or excuse(legacy_sid, date)):
            status = "excused"
        key = (lesson.pk, enrollment.pk)
        if key in existing_marks:
            stored = existing_marks[key]
            run.count("mark.same" if stored[0] == status and _same(stored[1], score) else "mark.conflict_kept")
            continue
        existing_marks[key] = (status, score)
        pending.append(
            LessonMark(
                organization=run.organization,
                lesson=lesson,
                enrollment=enrollment,
                status=status,
                score=score,
                entered_by=None,
            )
        )
        touched[enrollment.pk] = enrollment
        run.count(f"mark.created_{status}")
    book.flush()
    run.bulk_create(LessonMark, pending, "marks")
    if touched:
        from apps.registrar.public import gradebook

        gradebook.recompute_absence_hours_many(list(touched.values()))
        run.count("enrollment.absence_recomputed", len(touched))


def _same(stored, incoming) -> bool:
    if stored is None or incoming is None:
        return stored is None and incoming is None
    return Decimal(stored) == Decimal(incoming)


__all__ = ["LessonBook", "build_lessons_and_marks", "mark_value", "winning_cells"]
