"""Elektron jurnal (davamiyyət/qiymət jurnalı) — services (U3, UNEC modeli).

Müəllim hər dərs (``Lesson``) günü tələbələrin iştirak/qayıbını (iə/qb), seminar
və laboratoriya dərslərində isə balını (``LessonMark``) yazır — mühazirədə yalnız
iə/qb. Sistem keçirilmiş dərsləri, qayıb saatını və "giriş balı"nı (seminar/lab
ballarının cəmi) AVTOMATİK hesablayır. Yekun imtahan burada yoxdur.

Kilid qaydaları (geriyə-dönük dəyişiklik olmasın):
* dərs sətri (tarix/növ/mövzu/saat) yaranışdan ``LESSON_EDIT_WINDOW`` (2 saat)
  içində redaktə/silinə bilər — sonra dondurulur;
* keçmiş tarixə dərs yaratmaq qadağandır;
* YENİ iştirak/bal yalnız dərsin öz günündə yazılır; yazılmış xana
  ``MARK_EDIT_WINDOW`` (2 saat) sonra kilidlənir (DB trigger + servis);
* seminar/lab balı 0-10 aralığında clamp olunur.

Status (görünüş): qayıb saatı proqramın ``absence_limit_percent``-i × fənnin tam
saatını keçirsə → tələbə "kəsilir" (imtahana buraxılmır, sətir qırmızı); limitə
yaxınlaşırsa → xəbərdarlıq (sətir bozarır).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from apps.registrar import grade_audit, services
from apps.registrar.models import (
    AssessmentScheme,
    AttendanceStatus,
    Enrollment,
    Lesson,
    LessonKind,
    LessonMark,
    StudentAcademicRecord,
)

# Redaktə pəncərələri (2 saat — sonra toxunulmazdır; DB trigger də qoruyur).
LESSON_EDIT_WINDOW = timedelta(hours=2)  # dərs sətri yaranışdan sonra
MARK_EDIT_WINDOW = timedelta(hours=2)  # iştirak/bal yazıldıqdan sonra
DATE_EDIT_WINDOW = LESSON_EDIT_WINDOW  # köhnə ad (geriyə-uyğunluq)

DEFAULT_LESSON_HOURS = 2
LESSON_SCORE_MAX = Decimal("10")  # seminar/lab balı: min 0, max 10
_DEFAULT_ABSENCE_LIMIT = 25
_WARN_RATIO = Decimal("0.75")  # limitin bu payına çatanda xəbərdarlıq (bozarır)

SCORE_LESSON_KINDS = frozenset({LessonKind.SEMINAR, LessonKind.LAB})


class LessonRuleError(Exception):
    """Dərs qaydası pozuntusu (keçmiş tarix, pəncərə bitib və s.) — istifadəçiyə
    göstərilə bilən mesaj daşıyır."""


def _to_decimal(raw) -> Decimal:
    try:
        return Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def ensure_assessment_scheme(*, offering):
    """Idempotently return the offering's journal config."""
    scheme, _created = AssessmentScheme.objects.get_or_create(organization=offering.organization, offering=offering)
    return scheme


# Approval-chain statuses that freeze the journal (no mark/score edits) — U7.2.
_APPROVAL_LOCK_STATUSES = frozenset({"submitted", "chair_approved", "approved"})


def journal_is_locked(offering) -> bool:
    """The journal is locked once finalised OR while under grade approval."""
    scheme = ensure_assessment_scheme(offering=offering)
    return scheme.is_published or scheme.approval_status in _APPROVAL_LOCK_STATUSES


def lesson_allows_score(lesson) -> bool:
    """Only seminar / lab lessons carry a score; lectures are attendance-only."""
    return lesson.kind in SCORE_LESSON_KINDS


def can_edit_lesson(lesson, *, now=None) -> bool:
    """Dərs sətri (tarix/növ/mövzu/saat/silmə) yalnız yaranışdan 2 saat içində."""
    now = now or timezone.now()
    return (now - lesson.created_at) <= LESSON_EDIT_WINDOW


# Köhnə ad — mövcud çağırışlar üçün.
can_edit_lesson_date = can_edit_lesson


def can_edit_mark(mark, *, now=None) -> bool:
    """A missing mark is always writable; an existing one only within the window."""
    if mark is None:
        return True
    now = now or timezone.now()
    return (now - mark.created_at) <= MARK_EDIT_WINDOW


def absence_limit_percent_for(offering) -> int:
    record = (
        StudentAcademicRecord.objects.filter(organization=offering.organization, group=offering.group)
        .select_related("program")
        .first()
    )
    if record and record.program:
        return record.program.absence_limit_percent
    return _DEFAULT_ABSENCE_LIMIT


# ── Lesson (dərs) CRUD ───────────────────────────────────────────────────────


def _coerce_date(value):
    import datetime

    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


@transaction.atomic
def create_lesson(
    *,
    offering,
    date,
    kind=LessonKind.LECTURE,
    topic="",
    hours=None,
    start_time=None,
    end_time=None,
    created_by=None,
    allow_past=False,
):
    """Add a held session (a new journal column).

    Qaydalar: jurnal kilidli olmamalıdır; KEÇMİŞ tarixə dərs açmaq olmaz
    (geriyə-dönük doldurma qadağandır) — bu gün və gələcək (planlama) olar.
    ``allow_past`` YALNIZ seed/test dəstəyi üçündür — HTTP qatı heç vaxt ötürmür."""
    if journal_is_locked(offering):
        raise LessonRuleError("Jurnal kilidlidir — dərs əlavə etmək olmaz.")
    parsed = _coerce_date(date)
    if parsed is None:
        raise LessonRuleError("Dərs tarixi düzgün deyil.")
    if not allow_past and parsed < timezone.localdate():
        raise LessonRuleError("Keçmiş tarixə dərs əlavə etmək olmaz.")
    # Eyni gündə eyni dərs saatına iki dərs yazıla bilməz (üst-üstə düşməsin).
    # Yalnız saat verildikdə yoxlanır — seed/vaxtsız dərslər təsirlənmir.
    if start_time and Lesson.objects.filter(offering=offering, date=parsed, start_time=start_time).exists():
        raise LessonRuleError("Eyni gündə eyni dərs saatına artıq dərs var — üst-üstə düşür.")
    ensure_assessment_scheme(offering=offering)
    return Lesson.objects.create(
        organization=offering.organization,
        offering=offering,
        date=parsed,
        kind=kind,
        topic=topic or "",
        hours=hours or DEFAULT_LESSON_HOURS,
        start_time=start_time,
        end_time=end_time,
        created_by=created_by,
    )


@transaction.atomic
def update_lesson(
    *,
    lesson,
    date=None,
    kind=None,
    topic=None,
    hours=None,
    start_time=None,
    end_time=None,
    allow_past=False,
    allow_locked=False,
) -> bool:
    """Səhv açılmış dərsi düzəlt — yalnız yaranışdan 2 saat içində.

    ``allow_locked`` 2 saatlıq redaktə pəncərəsini, ``allow_past`` isə keçmiş-tarix
    qadağasını keçir — YALNIZ İKT Rəhbəri/superuser üçün (HTTP qatında rol-yoxlaması
    ilə ötürülür). Yayımlanmış/təsdiqlənmiş jurnal (``journal_is_locked``) yenə də
    kilidlidir."""
    if journal_is_locked(lesson.offering) or (not can_edit_lesson(lesson) and not allow_locked):
        return False
    fields = []
    if date is not None:
        parsed = _coerce_date(date)
        if parsed is None:
            raise LessonRuleError("Dərs tarixi düzgün deyil.")
        if parsed < timezone.localdate() and not allow_past:
            raise LessonRuleError("Dərs tarixi bu gündən əvvəl ola bilməz.")
        lesson.date = parsed
        fields.append("date")
    if kind is not None and kind in dict(LessonKind.choices):
        lesson.kind = kind
        fields.append("kind")
    if topic is not None:
        lesson.topic = topic
        fields.append("topic")
    if hours is not None:
        lesson.hours = hours
        fields.append("hours")
    if start_time is not None:
        lesson.start_time = start_time or None
        fields.append("start_time")
    if end_time is not None:
        lesson.end_time = end_time or None
        fields.append("end_time")
    if fields:
        lesson.save(update_fields=fields)
    return True


@transaction.atomic
def delete_lesson(*, lesson, by_user=None, allow_locked=False) -> bool:
    """Səhv açılmış dərsi sil — yalnız yaranışdan 2 saat içində.

    ``allow_locked`` 2 saatlıq pəncərəni keçir (yalnız İKT Rəhbəri/superuser).
    Sütunun (təzə) işarələri kaskadla silinir; əməliyyat audit tarixçəsinə düşür."""
    if journal_is_locked(lesson.offering) or (not can_edit_lesson(lesson) and not allow_locked):
        return False
    offering = lesson.offering
    label = f"{lesson.date} · {lesson.get_kind_display()}"
    touched = [m.enrollment for m in LessonMark.objects.filter(lesson=lesson).select_related("enrollment")]
    lesson.delete()
    for enrollment in touched:
        recompute_absence_hours(enrollment=enrollment)
    grade_audit.log_grade_changes(
        offering=offering,
        by_user=by_user,
        kind="mark",
        changes=[{"student": "—", "item": label, "old": "dərs sütunu", "new": "silindi"}],
    )
    return True


# Köhnə ad — mövcud çağırışlar üçün (yalnız tarix dəyişən variant).
def update_lesson_date(*, lesson, date) -> bool:
    try:
        return update_lesson(lesson=lesson, date=date)
    except LessonRuleError:
        return False


# ── Mark (iştirak/bal) yazma ─────────────────────────────────────────────────


@transaction.atomic
def save_marks(*, offering, entries, by_user=None, enforce_day=True):
    """Persist attendance/score cells for an offering (bulk, from the grid).

    ``entries``: iterable of ``{"lesson_id", "enrollment_id", "status", "score"}``.
    Each cell is validated against the offering's own lessons/enrollments
    (cross-offering/tenant injection rejected), honours the per-mark edit window
    (locked cells are skipped) and the lesson type (lecture cells never store a
    score). Blocked entirely when the journal is locked. Returns cells written.
    ``enforce_day=False`` YALNIZ seed/test üçündür — HTTP qatı heç vaxt ötürmür.
    """
    if journal_is_locked(offering):
        return 0

    lessons = {str(latt.id): latt for latt in offering.lessons.all()}
    enrollments = {str(e.id): e for e in offering.enrollments.filter(status=Enrollment.Status.ENROLLED)}
    existing = {(m.lesson_id, m.enrollment_id): m for m in LessonMark.objects.filter(lesson__offering=offering)}
    # Rəsmi (sənədli) düzəliş almış xanalar müəllim tərəfindən DƏYİŞİLƏ BİLMƏZ —
    # yalnız yeni rəsmi düzəliş (apps/registrar/corrections.py) dəyişə bilər.
    from .models import JournalCorrection

    corrected_ids = set(
        JournalCorrection.objects.filter(lesson_mark__lesson__offering=offering).values_list(
            "lesson_mark_id", flat=True
        )
    )
    # Bildiriş keçidləri üçün yazıdan ƏVVƏLKİ qayıb saatları.
    prior_hours = {e.id: e.absence_hours for e in enrollments.values()}

    written = 0
    touched = set()
    audit_changes = []
    notify_events = []
    now = timezone.now()
    today = timezone.localdate()
    for entry in entries or []:
        lesson = lessons.get(str(entry.get("lesson_id")))
        enrollment = enrollments.get(str(entry.get("enrollment_id")))
        if lesson is None or enrollment is None:
            continue
        mark = existing.get((lesson.id, enrollment.id))
        if mark is not None and mark.pk and mark.pk in corrected_ids:
            continue  # rəsmi düzəlişli xana — müəllim üçün kilidli
        if not can_edit_mark(mark, now=now):
            continue  # locked — no back-dated tampering
        if enforce_day and mark is None and lesson.date != today:
            continue  # YENİ işarə yalnız dərsin öz günündə yazılır

        status = entry.get("status")
        if status not in (AttendanceStatus.PRESENT, AttendanceStatus.ABSENT):
            status = AttendanceStatus.PRESENT
        score = None
        if lesson_allows_score(lesson) and entry.get("score") not in (None, ""):
            # Seminar/lab balı: min 0, max 10 (sərt tavan).
            score = min(max(Decimal("0"), _to_decimal(entry.get("score"))), LESSON_SCORE_MAX)

        old = _mark_repr(mark.status, mark.score) if mark is not None and mark.pk else None
        old_status = mark.status if mark is not None and mark.pk else None
        old_score = mark.score if mark is not None and mark.pk else None
        if mark is None:
            mark = LessonMark(organization=offering.organization, lesson=lesson, enrollment=enrollment)
        new = _mark_repr(status, score)
        mark.status = status
        mark.score = score
        mark.entered_by = by_user
        mark.save()
        if old != new:
            audit_changes.append(
                {
                    "student": grade_audit.student_label(enrollment),
                    "item": f"{lesson.date} · {lesson.get_kind_display()}",
                    "old": old or "—",
                    "new": new,
                }
            )
            # Tələbə bildirişləri: q/b qeydi və yeni/dəyişmiş bal.
            from apps.registrar import journal_notifications as jn

            if status == AttendanceStatus.ABSENT and old_status != AttendanceStatus.ABSENT:
                notify_events.append({"enrollment": enrollment, "kind": jn.EVENT_ABSENT})
            if score is not None and score != old_score:
                notify_events.append({"enrollment": enrollment, "kind": jn.EVENT_SCORE, "score": score})
        touched.add(enrollment)
        written += 1

    # Keep the denormalised Enrollment.absence_hours (used by the "Fənlərim"
    # exam-eligibility badge) in sync with the journal — the single source of truth.
    allowed = _allowed_absence_hours(offering, list(lessons.values()))
    warn_at = allowed * _WARN_RATIO
    for enrollment in touched:
        new_hours = recompute_absence_hours(enrollment=enrollment)
        prev = Decimal(prior_hours.get(enrollment.id, 0))
        cur = Decimal(new_hours)
        if allowed > 0 and cur > prev:
            from apps.registrar import journal_notifications as jn

            if prev <= allowed < cur:
                notify_events.append({"enrollment": enrollment, "kind": jn.EVENT_BARRED})
            elif prev < warn_at <= cur <= allowed:
                notify_events.append({"enrollment": enrollment, "kind": jn.EVENT_LIMIT_WARNING, "hours": new_hours})

    grade_audit.log_grade_changes(offering=offering, by_user=by_user, kind="mark", changes=audit_changes)

    if notify_events:
        from django.db import transaction as _tx

        from apps.registrar import journal_notifications as jn

        _tx.on_commit(lambda: jn.send_journal_events(offering=offering, events=notify_events))
    return written


def _mark_repr(status, score) -> str:
    """Compact attendance+score label for the audit trail (e.g. ``qb`` / ``iə 8``)."""
    if status == AttendanceStatus.ABSENT:
        att = "qb"
    elif status == AttendanceStatus.EXCUSED:
        att = "üq"  # üzrlü qayıb (rəsmi düzəliş yolu ilə)
    else:
        att = "iə"
    return f"{att} {grade_audit.score_repr(score)}" if score is not None else att


def recompute_absence_hours(*, enrollment):
    """Recompute Enrollment.absence_hours from the student's lesson marks (qb)."""
    hours = sum(
        m.lesson.hours
        for m in LessonMark.objects.filter(enrollment=enrollment, status=AttendanceStatus.ABSENT).select_related(
            "lesson"
        )
    )
    if enrollment.absence_hours != hours:
        enrollment.absence_hours = hours
        enrollment.save(update_fields=["absence_hours"])
    return hours


def _lesson_parity(offering, lesson) -> str:
    """Dərs tarixinin üst/alt həftə pariteti ('odd'/'even') — başlıq etiketləri."""
    from datetime import timedelta as _td

    from apps.registrar import schedule as _schedule

    monday = lesson.date - _td(days=lesson.date.weekday())
    return _schedule.week_parity(offering.period, monday)


# ── Jurnal görünüşü (müəllim grid) ───────────────────────────────────────────


def _allowed_absence_hours(offering, lessons):
    total_hours = offering.lesson_hours or sum(latt.hours for latt in lessons)
    return Decimal(total_hours) * Decimal(absence_limit_percent_for(offering)) / Decimal(100)


def get_offering_journal(*, offering, newest_first=False):
    """Full journal grid: lessons (columns) × enrolled students (rows) + summary.

    One pass over the marks (no per-cell query). Each row carries the running
    absence hours, the accumulated entry score (giriş balı, capped) and the
    barred / warning status used to grey or redden the row.
    ``newest_first=True`` → sütun sırası tərs (ən yeni dərs adların yanında) —
    müəllim grid-i üçün; export xronoloji qalır."""
    scheme = ensure_assessment_scheme(offering=offering)
    lessons = list(offering.lessons.order_by("date", "created_at"))
    if newest_first:
        lessons.reverse()
    enrollments = list(
        offering.enrollments.filter(status=Enrollment.Status.ENROLLED)
        .select_related("student")
        .order_by("student__last_name", "student__username")
    )
    mark_map = {(m.enrollment_id, m.lesson_id): m for m in LessonMark.objects.filter(lesson__offering=offering)}
    # Rəsmi düzəliş almış xanalar (sarı + kilidli göstəriş üçün).
    from .models import JournalCorrection

    corrected_mark_ids = set(
        JournalCorrection.objects.filter(lesson_mark__lesson__offering=offering).values_list(
            "lesson_mark_id", flat=True
        )
    )

    now = timezone.now()
    today = timezone.localdate()
    allowed_absence = _allowed_absence_hours(offering, lessons)
    warn_at = allowed_absence * _WARN_RATIO

    # Per-lesson özət (müəllim: redaktə pəncərəsi keçmiş sütun başlığına klik →
    # oxu-rejimi gün özəti). Əlavə sorğu yox — mark_map yaddaşdadır.
    total_students = len(enrollments)
    lesson_summary: dict = {}
    for lesson in lessons:
        ie = qb = uq = scored = 0
        for enrollment in enrollments:
            m = mark_map.get((enrollment.id, lesson.id))
            if m is None:
                continue
            if m.status == AttendanceStatus.ABSENT:
                qb += 1
            elif m.status == AttendanceStatus.EXCUSED:
                uq += 1
            else:
                ie += 1
            if m.score is not None:
                scored += 1
        lesson_summary[lesson.id] = {
            "ie": ie,
            "qb": qb,
            "uq": uq,
            "scored": scored,
            "total": total_students,
            "marked": ie + qb + uq,
        }

    lesson_meta = [
        {
            "lesson": lesson,
            "is_today": lesson.date == today,
            "editable": can_edit_lesson(lesson, now=now),  # sütun redaktə/silmə (2 saat)
            "markable": lesson.date == today,  # yeni işarə yalnız bu gün
            # xronoloji nömrə (köhnədən yeniyə) — sıra tərs olsa da nömrə sabitdir
            "seq": (len(lessons) - idx) if newest_first else (idx + 1),
            "parity": _lesson_parity(offering, lesson),  # Ü/A başlıq etiketi
            "summary": lesson_summary.get(lesson.id, {}),
        }
        for idx, lesson in enumerate(lessons)
    ]

    rows = []
    for enrollment in enrollments:
        cells = []
        absence_hours = 0
        absence_count = 0
        for lesson in lessons:
            mark = mark_map.get((enrollment.id, lesson.id))
            if mark is not None and mark.status == AttendanceStatus.ABSENT:
                absence_hours += lesson.hours
                absence_count += 1
            corrected = mark is not None and mark.id in corrected_mark_ids
            locked = corrected or (mark is not None and not can_edit_mark(mark, now=now))
            cells.append(
                {
                    "lesson": lesson,
                    "mark": mark,
                    "allows_score": lesson_allows_score(lesson),
                    "locked": locked,
                    # Rəsmi düzəlişli xana müəllim üçün kilidli (yalnız admin düzəlişi dəyişir).
                    "corrected": corrected,
                    # yazıla bilən: mövcud işarə pəncərə içində, YA boş xana bu günün dərsində
                    "writable": (not corrected)
                    and ((mark is not None and not locked) or (mark is None and lesson.date == today)),
                }
            )
        # Canonical entry score (component-weighted when defined, else lesson sum).
        entry_score = entry_score_for(enrollment, scheme.entry_score_max)
        barred = allowed_absence > 0 and Decimal(absence_hours) > allowed_absence
        warning = (not barred) and allowed_absence > 0 and Decimal(absence_hours) >= warn_at
        rows.append(
            {
                "enrollment": enrollment,
                "student": enrollment.student,
                "cells": cells,
                "absence_hours": absence_hours,
                # q/b (qayıb) SAYı — UI saat əvəzinə bunu göstərir; barred/warning
                # isə akademik saat-limitinə görə qalır (Enrollment.absence_hours).
                "absence_count": absence_count,
                "entry_score": entry_score,
                "barred": barred,
                "warning": warning,
            }
        )

    return {
        "offering": offering,
        "scheme": scheme,
        "lessons": lessons,
        "lesson_meta": lesson_meta,
        "rows": rows,
        "today": today,
        "limit_percent": absence_limit_percent_for(offering),
        "allowed_absence": allowed_absence,
        "entry_score_max": scheme.entry_score_max,
    }


# ── Tələbə görünüşü ("Qiymətlərim") ──────────────────────────────────────────


def get_student_journal_summary(*, record, period, semester_number):
    """Per-subject entry score + attendance for the student view.

    Computes each enrolled subject's absence hours and accumulated entry score
    from this student's own lesson marks (only their row — never the roster)."""
    plan = services.get_student_semester_plan(record=record, period=period, semester_number=semester_number)
    limit_percent = record.program.absence_limit_percent if record.program else _DEFAULT_ABSENCE_LIMIT
    enrollments = plan["enrollments"]
    if not enrollments:
        return {"subjects": []}

    # ── Toplu (batch) sorğular — per-subject N+1-i aradan qaldırır ──────────────
    enr_ids = [e.id for e in enrollments]
    offering_ids = list({e.offering_id for e in enrollments})
    marks_by_enr: dict = defaultdict(list)
    for m in LessonMark.objects.filter(enrollment_id__in=enr_ids).select_related("lesson"):
        marks_by_enr[m.enrollment_id].append(m)
    from apps.registrar.models import AssessmentComponent

    comps_by_off: dict = defaultdict(list)
    for c in AssessmentComponent.objects.filter(offering_id__in=offering_ids):
        comps_by_off[c.offering_id].append(c)
    lesson_counts = {
        row["offering_id"]: row["c"]
        for row in Lesson.objects.filter(offering_id__in=offering_ids).values("offering_id").annotate(c=Count("id"))
    }

    subjects = []
    for enrollment in enrollments:
        offering = enrollment.offering
        marks = marks_by_enr.get(enrollment.id, [])
        absence_hours = sum(m.lesson.hours for m in marks if m.status == AttendanceStatus.ABSENT)
        scheme = getattr(offering, "assessment_scheme", None)
        cap = scheme.entry_score_max if scheme else 50
        entry_score = entry_score_for(enrollment, cap, marks=marks, components=comps_by_off.get(offering.id, []))
        lessons_held = lesson_counts.get(offering.id, 0)
        total_hours = offering.lesson_hours or 0
        allowed = Decimal(total_hours) * Decimal(limit_percent) / Decimal(100)
        barred = allowed > 0 and Decimal(absence_hours) > allowed
        subjects.append(
            {
                "enrollment": enrollment,
                "subject": offering.subject,
                "ects": offering.subject.ects,
                "kind": enrollment.kind,
                "journal": {
                    "lessons_held": lessons_held,
                    "absence_hours": absence_hours,
                    "allowed_absence": allowed,
                    "entry_score": entry_score,
                    "entry_score_max": cap,
                    "barred": barred,
                },
            }
        )
    return {"subjects": subjects}


# ── Komponent funksiyaları ayrıca modulda (modul-ölçü büdcəsi) — re-eksport ──
from apps.registrar.gradebook_components import (  # noqa: E402,F401
    entry_score_for,
    get_component_breakdown,
    get_component_grid,
    get_components,
    save_component_scores,
    save_components,
)
