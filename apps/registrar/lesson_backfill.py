"""Keçmiş dərslərin cədvəldən bərpası — ``backfill_teacher_lessons`` əmrinin xidməti (sahib 2026-10-15).

Sahib (müəllim): «jurnallarıma heç nə yazmamışam — 15.09-dan bu günə qədər cədvəlimə görə dərsləri
yarat və hamıya i/e qoy; qiymətləri sonra özüm dəyişəcəyəm». Bu modul ümumidir (istənilən müəllim):

* SLOTLAR (:mod:`lesson_backfill_slots`): müəllimin canlı cədvəl slotları və ya JSON spesifikasiya (öz
  açılışlarına TƏK uyğunluq); ``replace_slots`` → digər slotları yumşaq silinir, çatışmayanlar yaranır.
* DƏRSLƏR: [from, to] (bu gündən sonra yox; dövr sərhədi daxilində) hər gün üçün o gün keçirilən slotlar —
  ``dashboard_data.lessons_on`` (həftə günü + üst/alt paritet ``schedule.week_parity``: dövrün ilk həftəsi
  = üst/odd + dövr sərhədi; jurnalın «Aktivləşdir» qaydası ilə EYNİ). Bu gün üçün yalnız başlamış slotlar.
  Bayram təqvimi sistemdə YOXDUR (bax ``lessons_log_unrecorded``) — heç bir gün çıxılmır.
* İDEMPOTENTLİK: açılış + tarix üzrə mövcud dərs əvvəl eyni başlama saatı ilə, sonra eyni NÖV ilə
  (fərqli saatda — məs. köhnə səhv slotdan açılmış dərs) tutuşdurulur; tutuşan dərs YENİDƏN YARADILMIR.
* YARATMA: ``gradebook_lessons.create_lesson(slot=…, allow_past=True)`` — saat/növ/otaq slotdan, müəllim
  = slotun effektiv müəllimi; mövzu = təsdiqlənmiş sillabusun bu NÖV üçün növbəti keçilməmiş mövzusu
  (``journal_activation.next_topic`` — «Aktivləşdir» ilə eyni). Kilidli jurnal, sillabus qapısı, fənnin
  saat həddi (``hours_cap_error``) və digər dərs qaydaları qüvvədədir — pozulan dərs ötürülür.
* İŞARƏ: tutuşan/yaradılan hər dərsdə hələ işarəsi OLMAYAN aktiv (``enrolled``) tələbələrə «iə»
  (``AttendanceStatus.PRESENT``) — ``gradebook.save_marks`` ilə (grid yazısı ilə eyni qaydalar, audit).
  Mövcud işarəyə TOXUNULMUR. Tarixdən sonra qoşulan sətir işarələnmir: alt qrupdan əlavə
  (``added_at``) və köçürmə ilə gələn (əvəz etdiyi qeydiyyatı olan, ``created_at``) qeydiyyatlar.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone

from apps.registrar import dashboard_data, schedule
from apps.registrar.lesson_backfill_slots import (  # noqa: F401 — ictimai adlar buradan da
    SLOT_ACTIONS,
    SLOT_REPORT_HEADER,
    SlotRow,
    SlotSpec,
    SpecError,
    live_slots,
    load_slot_spec,
    match_offering,
    sync_spec_slots,
)
from apps.registrar.models import AttendanceStatus, CourseOffering, Enrollment, Lesson, LessonMark

# Dərs sətrinin əməlləri
CREATE = "create"
EXISTS = "exists"
EXISTS_OTHER_TIME = "exists_other_time"
SKIPPED = "skipped"
LESSON_ACTIONS = (CREATE, EXISTS, EXISTS_OTHER_TIME, SKIPPED)

LESSON_REPORT_HEADER = (
    "subject_code",
    "subject",
    "group",
    "date",
    "time",
    "kind",
    "week_type",
    "action",
    "reason",
    "marks_written",
)


@dataclass
class LessonRow:
    offering: object
    day: dt.date
    slot: object
    action: str
    reason: str = ""
    lesson: object = None
    marks_written: int = 0

    def csv_row(self) -> list:
        slot = self.slot
        return [
            self.offering.subject.code,
            self.offering.subject.name,
            self.offering.group.name if self.offering.group_id else "",
            self.day.isoformat(),
            f"{slot.start_time:%H:%M}-{slot.end_time:%H:%M}",
            slot.kind,
            slot.week_type,
            self.action,
            self.reason,
            self.marks_written,
        ]


@dataclass
class Result:
    date_from: dt.date
    date_to: dt.date
    slot_rows: list[SlotRow] = field(default_factory=list)
    lesson_rows: list[LessonRow] = field(default_factory=list)
    marks_rejected: int = 0
    #: Qoşulmadan əvvəlki dərs üçün buraxılan (tələbə, dərs) cütləri (``include_late_joiners`` sönülü olanda).
    late_skipped: int = 0

    @property
    def lesson_counts(self) -> Counter:
        return Counter(row.action for row in self.lesson_rows)

    @property
    def slot_counts(self) -> Counter:
        return Counter(row.action for row in self.slot_rows)

    @property
    def skip_reasons(self) -> Counter:
        return Counter(row.reason.split(":")[0] for row in self.lesson_rows if row.action == SKIPPED)

    @property
    def marks_written(self) -> int:
        return sum(row.marks_written for row in self.lesson_rows)

    def per_offering(self) -> list[tuple[str, Counter]]:
        """``[(«fənn · qrup», Counter(əməl…, marks=N))]`` — fənn/qrup adı şəxsi məlumat deyil."""
        buckets: dict = {}
        for row in self.lesson_rows:
            offering = row.offering
            label = f"{offering.subject.name} · {offering.group.name if offering.group_id else '—'}"
            counter = buckets.setdefault(label, Counter())
            counter[row.action] += 1
            counter["marks"] += row.marks_written
        return sorted(buckets.items())


# ── Dərslər + işarələr ───────────────────────────────────────────────────────


def _days(date_from: dt.date, date_to: dt.date):
    day = date_from
    while day <= date_to:
        yield day
        day += dt.timedelta(days=1)


def _match_existing(todays, existing) -> dict:
    """``{slot.pk: (dərs, əməl)}`` — əvvəl eyni başlama saatı, sonra eyni növ (fərqli saat)."""
    free = list(existing)
    matched = {}
    for slot in todays:
        hit = next((lesson for lesson in free if lesson.start_time == slot.start_time), None)
        if hit is not None:
            free.remove(hit)
            matched[slot.pk] = (hit, EXISTS)
    for slot in todays:
        if slot.pk in matched:
            continue
        hit = next((lesson for lesson in free if lesson.kind == slot.kind), None)
        if hit is not None:
            free.remove(hit)
            matched[slot.pk] = (hit, EXISTS_OTHER_TIME)
    return matched


def _create(offering, day, slot, actor, topic_rows, covered) -> tuple[object, str]:
    from apps.registrar import journal_activation
    from apps.registrar.gradebook import LessonRuleError
    from apps.registrar.gradebook_lessons import create_lesson
    from apps.registrar.journal_policy import SyllabusGateError

    error = journal_activation.hours_cap_error(offering, journal_activation.slot_hours(slot))
    if error:
        return None, "hours_cap"
    topic = journal_activation.next_topic(topic_rows, covered, slot.kind)
    try:
        with transaction.atomic():
            lesson = create_lesson(
                offering=offering,
                date=day,
                slot=slot,
                topic=topic,
                created_by=actor,
                instructor=schedule.effective_instructor(slot),
                allow_past=True,
            )
    except SyllabusGateError as exc:
        return None, f"syllabus_gate:{getattr(exc, 'reason_code', '')}"
    except LessonRuleError as exc:
        return None, f"lesson_rule:{str(exc)[:120]}"
    if topic:
        covered.setdefault(topic, set()).add(lesson.kind)
    return lesson, ""


def _joined_on(enrollment):
    """Qeydiyyatın jurnala qoşulma günü (ondan əvvəlki dərs işarələnmir); adi sətir üçün ``None``."""
    if enrollment.source_group_id and enrollment.added_at:
        return timezone.localdate(enrollment.added_at)
    if getattr(enrollment, "has_predecessor", False):
        return timezone.localdate(enrollment.created_at)
    return None


def _mark_present(offering, lesson_rows, actor, result: Result, *, include_late_joiners: bool = False) -> None:
    from django.db.models import Exists, OuterRef

    from apps.registrar.gradebook import save_marks

    lessons = [row.lesson for row in lesson_rows if row.lesson is not None]
    if not lessons:
        return
    enrollments = list(
        Enrollment.objects.filter(offering=offering, status=Enrollment.Status.ENROLLED).annotate(
            has_predecessor=Exists(Enrollment.objects.filter(superseded_by=OuterRef("pk")))
        )
    )
    marked = set(
        LessonMark.objects.filter(lesson__in=lessons, enrollment__in=enrollments).values_list(
            "lesson_id", "enrollment_id"
        )
    )
    entries = []
    for row in lesson_rows:
        lesson = row.lesson
        if lesson is None:
            continue
        for enrollment in enrollments:
            if (lesson.pk, enrollment.pk) in marked:
                continue
            joined = _joined_on(enrollment)
            if joined and joined > lesson.date and not include_late_joiners:
                result.late_skipped += 1
                continue
            entries.append(
                {
                    "lesson_id": str(lesson.pk),
                    "enrollment_id": str(enrollment.pk),
                    "status": AttendanceStatus.PRESENT,
                    "score": "",
                }
            )
    if not entries:
        return
    outcome = save_marks(offering=offering, entries=entries, by_user=actor, enforce_day=False, report=True)
    written = Counter(
        lesson_id
        for lesson_id, enrollment_id in LessonMark.objects.filter(
            lesson__in=lessons, enrollment__in=enrollments
        ).values_list("lesson_id", "enrollment_id")
        if (lesson_id, enrollment_id) not in marked
    )
    for row in lesson_rows:
        if row.lesson is not None:
            row.marks_written = written.get(row.lesson.pk, 0)
    result.marks_rejected += max(0, len(entries) - int(outcome.get("written", 0)))


def plan_lessons(
    *, organization, period, slots, actor, date_from, date_to, result: Result, include_late_joiners: bool = False
) -> None:
    """Hər gün × o gün keçirilən slot → mövcud dərsə bağla və ya yarat; sonra açılış üzrə «iə»."""
    from apps.registrar import gradebook, journal_topics

    now = timezone.localtime()
    by_offering = defaultdict(list)
    for slot in slots:
        by_offering[slot.offering_id].append(slot)
    offerings = {
        offering.pk: offering
        for offering in CourseOffering.objects.filter(pk__in=list(by_offering)).select_related(
            "organization", "period", "subject", "group", "instructor"
        )
    }
    for offering_id in sorted(by_offering, key=lambda pk: (offerings[pk].subject.name, str(pk))):
        offering = offerings[offering_id]
        own_slots = by_offering[offering_id]
        existing = defaultdict(list)
        for lesson in Lesson.objects.filter(offering=offering, date__range=(date_from, date_to)).order_by(
            "start_time", "created_at"
        ):
            existing[lesson.date].append(lesson)
        locked = gradebook.journal_is_locked(offering)
        topic_rows = journal_topics.lesson_topic_meta(offering, [])
        covered: dict = {}
        for topic, kind in offering.lessons.exclude(topic="").values_list("topic", "kind"):
            covered.setdefault(topic, set()).add(kind)
        rows = []
        for day in _days(date_from, date_to):
            todays = dashboard_data.lessons_on(own_slots, day, period=period)
            if day == now.date():
                todays = [slot for slot in todays if slot.start_time <= now.time()]
            if not todays:
                continue
            matched = _match_existing(todays, existing.get(day, []))
            for slot in todays:
                if slot.pk in matched:
                    lesson, action = matched[slot.pk]
                    rows.append(LessonRow(offering, day, slot, action, lesson=lesson))
                elif locked:
                    rows.append(LessonRow(offering, day, slot, SKIPPED, "journal_locked"))
                else:
                    lesson, reason = _create(offering, day, slot, actor, topic_rows, covered)
                    action = CREATE if lesson is not None else SKIPPED
                    rows.append(LessonRow(offering, day, slot, action, reason, lesson=lesson))
        if not locked:
            _mark_present(offering, rows, actor, result, include_late_joiners=include_late_joiners)
        result.lesson_rows.extend(rows)


def run_backfill(
    *,
    organization,
    period,
    teacher,
    date_from: dt.date,
    date_to: dt.date,
    actor,
    specs=None,
    replace_slots: bool = False,
    include_late_joiners: bool = False,
    apply: bool = False,
) -> Result:
    """Bir tranzaksiya: ``apply=False`` (defolt) → hər şey hesablanır və GERİ QAYTARILIR (dry-run)."""
    today = timezone.localdate()
    date_from = max(date_from, period.start_date)
    date_to = min(date_to, today, period.end_date)
    result = Result(date_from=date_from, date_to=date_to)
    with transaction.atomic():
        if specs is not None:
            slots = sync_spec_slots(
                organization=organization,
                period=period,
                teacher=teacher,
                specs=specs,
                actor=actor,
                replace=replace_slots,
                rows=result.slot_rows,
            )
        else:
            slots = live_slots(organization, period, teacher, result.slot_rows)
        if date_from <= date_to and slots:
            plan_lessons(
                organization=organization,
                period=period,
                slots=slots,
                actor=actor,
                date_from=date_from,
                date_to=date_to,
                result=result,
                include_late_joiners=include_late_joiners,
            )
        if not apply:
            transaction.set_rollback(True)
    return result


__all__ = [
    "LESSON_ACTIONS",
    "LESSON_REPORT_HEADER",
    "SLOT_ACTIONS",
    "SLOT_REPORT_HEADER",
    "Result",
    "SlotSpec",
    "SpecError",
    "load_slot_spec",
    "match_offering",
    "run_backfill",
]
