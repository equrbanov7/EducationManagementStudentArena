"""Elektron jurnal (davamiyyət/qiymət jurnalı) — services (U3, UNEC modeli).

Müəllim hər dərs günü iştirak/qayıbı (iə/qb), seminar/lab-da isə balı (``LessonMark``)
yazır; sistem keçirilmiş dərsləri, qayıb saatını və "giriş balı"nı avtomatik hesablayır.
Kilid qaydaları (geriyə-dönük dəyişiklik olmasın): dərs sətri + yazılmış xana yaranışdan
2 saat (``LESSON/MARK_EDIT_WINDOW``, DB trigger + servis) sonra dondurulur; keçmiş tarixə
dərs qadağan; yeni işarə yalnız dərsin günündə; bal 0-10 clamp. Qayıb saatı proqramın
``absence_limit_percent``-i × fənn saatını keçirsə tələbə "kəsilir" (imtahana buraxılmır).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from apps.registrar import exam_eligibility, grade_audit, journal_window, services
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

#: "Verilməyib" sentineli — ``None`` özü mənalı dəyərdir (məs. otağı təmizlə),
#: ona görə "dəyişmə" halını ondan ayırmaq lazımdır (gradebook_lessons işlədir).
UNSET = object()
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


# Jurnalı donduran YEGANƏ vəziyyət: RİM-in bağladığı jurnal. Ara statuslar
# artıq yaradılmır — təsdiq zənciri ləğv edilib (registrar.0048 DRAFT-a endirir).
# Tərif ``exam_eligibility``-dən gəlir: buraxılış statusunun donma meyarı da
# EYNİ kilidə söykənir, iki tərif heç vaxt bir-birindən sürüşməməlidir.
_CLOSED_STATUSES = exam_eligibility._LOCKED_STATUSES


def journal_is_locked(offering) -> bool:
    """Jurnal bağlıdırmı — RİM semestr sonunda bağlayıb (yaxud legacy import)."""
    scheme = ensure_assessment_scheme(offering=offering)
    return scheme.is_published or scheme.approval_status in _CLOSED_STATUSES


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


# ── Mark (iştirak/bal) yazma ─────────────────────────────────────────────────


@transaction.atomic
def save_marks(*, offering, entries, by_user=None, enforce_day=True, report=False):
    """Persist attendance/score cells for an offering (bulk, from the grid).

    ``entries``: iterable of ``{"lesson_id", "enrollment_id", "status", "score"}``.
    Each cell is validated against the offering's own lessons/enrollments
    (cross-offering/tenant injection rejected), honours the per-mark edit window
    (locked cells are skipped) and the lesson type (lecture cells never store a
    score). Blocked entirely when the journal is locked. Returns cells written.
    ``enforce_day=False`` YALNIZ seed/test üçündür — HTTP qatı heç vaxt ötürmür.
    ``report=True`` → ``{"written", "rejected"}`` (yazılmayan xanaların sayı ilə;
    çağıran istifadəçiyə xəbərdarlıq göstərir — bax P3-10).
    """
    if journal_is_locked(offering):
        return {"written": 0, "rejected": 0} if report else 0

    # Çağırış vaxtı idxal: `gradebook_lessons` bu moduldan idxal edir (dövr).
    from apps.registrar.gradebook_lessons import parse_lesson_score as _parse_score

    lessons = {str(latt.id): latt for latt in offering.lessons.all()}
    enrollments = {str(e.id): e for e in offering.enrollments.filter(status=Enrollment.Status.ENROLLED)}
    existing = {(m.lesson_id, m.enrollment_id): m for m in LessonMark.objects.filter(lesson__offering=offering)}
    # Rəsmi (sənədli) düzəliş almış xanalar müəllim tərəfindən DƏYİŞİLƏ BİLMƏZ —
    # yalnız yeni rəsmi düzəliş (apps/registrar/corrections.py) dəyişə bilər.
    from .models import JournalCorrection

    corrected_ids = set(
        JournalCorrection.objects.filter(lesson_mark__lesson__offering=offering, reversal__isnull=True).values_list(
            "lesson_mark_id", flat=True
        )
    )
    # Bildiriş keçidləri üçün yazıdan ƏVVƏLKİ qayıb saatları.
    prior_hours = {e.id: e.absence_hours for e in enrollments.values()}

    written = 0
    rejected = 0
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
        if status != AttendanceStatus.ABSENT and lesson_allows_score(lesson) and entry.get("score") not in (None, ""):
            # Seminar/lab balı: tam ədəd, 0..10. Qayıb tələbəyə bal yazılmır —
            # «q/b + 8 bal» xanası mümkün idi (QA 2026-09-05 JOURNAL-TEACHER-09).
            score = _parse_score(entry.get("score"))
            if score is None:
                # Səhv dəyər SƏSSİZ 0-a çevrilmir — xana toxunulmadan qalır (P3-10).
                rejected += 1
                continue

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
    return {"written": written, "rejected": rejected} if report else written


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
    """Recompute Enrollment.absence_hours from the student's lesson marks (qb).

    ALT QRUP BİRLƏŞMƏSİ: tələbə öz jurnalından azad edilib bura köçürülübsə,
    əvvəlki jurnalda yığdığı qayıb saatı da ÜSTƏGƏLdir — 25% buraxılış həddi
    dərsə yox, FƏNNƏ + SEMESTRƏ aiddir, birləşmə onu sıfırlamamalıdır
    (bax :mod:`apps.registrar.guest_merge`). Adi sətirlərdə ƏLAVƏ SORĞU OLMUR.
    """
    from apps.registrar import guest_merge

    hours = sum(
        m.lesson.hours
        for m in LessonMark.objects.filter(enrollment=enrollment, status=AttendanceStatus.ABSENT).select_related(
            "lesson"
        )
    ) + guest_merge.carried_absence_hours(enrollment)
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


def _allowed_absence_hours(offering, lessons, *, limit_percent=None):
    """İcazəli qayıb saatı.

    ``limit_percent`` verilibsə TƏKRAR sorğu edilmir — çağıran onu artıq
    oxuyubsa (``get_offering_journal``), ``absence_limit_percent_for`` ikinci
    dəfə ``StudentAcademicRecord``-a getməməlidir.
    """
    total_hours = exam_eligibility.lesson_hours_for(offering, lessons)
    if limit_percent is None:
        limit_percent = absence_limit_percent_for(offering)
    return Decimal(total_hours) * Decimal(limit_percent) / Decimal(100)


def get_offering_journal(*, offering, newest_first=False, lesson_limit=None, lesson_offset=0, lesson_kind=""):
    """Full journal grid: lessons (columns) × enrolled students (rows) + summary.

    One pass over the marks (no per-cell query). Each row carries the running
    absence hours, the accumulated entry score (giriş balı, capped) and the
    barred / warning status used to grey or redden the row.
    ``newest_first=True`` → sütun sırası tərs (ən yeni dərs adların yanında) —
    müəllim grid-i üçün; export xronoloji qalır.

    DƏRS PƏNCƏRƏSİ (QA 2026-09-05 P1-8): 555 tələbə × 226 dərs açılışında bütün
    xanalar bir səhifəyə render olunurdu — 41.5 MB HTML / 6.3 s, brauzer donurdu.
    ``lesson_limit``/``lesson_offset`` YALNIZ göstərilən SÜTUNLARI kəsir:

    * qayıb saatı, giriş balı, buraxılış qərarı və q/b sayğacı HƏMİŞƏ BÜTÜN
      dərslər üzrə hesablanır (pəncərə rəqəmləri təhrif etmir);
    * ``lessons``/``lesson_meta`` və sətirlərin ``cells`` sahəsi pəncərəyə aiddir;
    * ``lesson_window`` açarı şablona naviqasiya üçün meta qaytarır.

    ``lesson_limit=None`` → bütün dərslər (export, düzəliş rejimi, «hamısını göstər»).

    ``lesson_kind`` — dərs tipi süzgəci: pəncərə kimi YALNIZ SÜTUNLARA aiddir.
    """
    scheme = ensure_assessment_scheme(offering=offering)
    all_lessons = list(offering.lessons.order_by("date", "created_at"))
    lessons = [lesson for lesson in all_lessons if lesson.kind == lesson_kind] if lesson_kind else list(all_lessons)
    if newest_first:
        lessons.reverse()
    total_lessons = len(lessons)
    window_size, window_offset = journal_window.resolve_window(total_lessons, limit=lesson_limit, offset=lesson_offset)
    if lesson_limit:
        lessons = lessons[window_offset : window_offset + window_size]
    # `source_group` — «alt qrupdan əlavə olunub» çipi üçün (bax guest_roster.py).
    enrollments = list(
        offering.enrollments.filter(status=Enrollment.Status.ENROLLED)
        .select_related("student", "source_group")
        .order_by("student__last_name", "student__username")
    )
    mark_map = {(m.enrollment_id, m.lesson_id): m for m in LessonMark.objects.filter(lesson__offering=offering)}
    # Giriş balının komponent/bal/sərbəst-iş oxumaları BİR dəfə (sətir-sətir
    # 4 sorğu idi; 555 tələbəli açılışda 2 220 — bax finals_batch).
    from apps.registrar import finals_batch

    entry_batch = finals_batch.entry_batch(enrollments)
    # «Alt qrup» çipi CARİ iddiadır: rəsmi köçürmədən sonra tələbə artıq bu qrupun
    # üzvüdürsə provenans qalsa da çip yalan danışmamalıdır (bax guest_roster).
    from apps.registrar import guest_merge, guest_roster

    guest_ids = [e.id for e in enrollments if e.source_group_id]
    current_groups = guest_roster.current_group_map(
        organization_id=offering.organization_id,
        student_ids=[e.student_id for e in enrollments if e.source_group_id],
    )
    # Birləşmə ilə gələn əvvəlki jurnal işi (yalnız qonaq sətirlər üçün, tək sorğu).
    carry_map = guest_merge.carry_over_map(guest_ids)
    # Rəsmi düzəliş almış xanalar (sarı + kilidli göstəriş üçün).
    from .models import JournalCorrection

    corrected_mark_ids = set(
        JournalCorrection.objects.filter(lesson_mark__lesson__offering=offering, reversal__isnull=True).values_list(
            "lesson_mark_id", flat=True
        )
    )

    now = timezone.now()
    today = timezone.localdate()
    limit_percent = absence_limit_percent_for(offering)
    # Hədd BÜTÜN dərslər üzrədir — pəncərə onu dəyişməməlidir.
    allowed_absence = _allowed_absence_hours(offering, all_lessons, limit_percent=limit_percent)
    # TƏK MƏNBƏ (bax :mod:`apps.registrar.exam_eligibility`): qrid buraxılış
    # qaydasını təkrar yazmır. Açılış üzrə bir dəfə həll olunur — sətir başına
    # yoxlama N+1 olardı.
    frozen = exam_eligibility.is_frozen(offering)
    # Məxrəc + idmançı istisnası da TƏK mənbədən; istisna toplu oxunur (tək
    # sorğu), sətir-sətir N+1 olardı (2026-08-31 düşmən baxışı, 3-cü bloker).
    # Məxrəc də BÜTÜN dərslər üzrədir — pəncərə buraxılış faizini dəyişməməlidir.
    total_hours = exam_eligibility.lesson_hours_for(offering, all_lessons)
    exempt_ids = exam_eligibility.exempt_student_ids(offering.organization, [e.student_id for e in enrollments])
    warn_at = allowed_absence * _WARN_RATIO

    # Per-lesson özət (sütun başlığındakı gün özəti) — `journal_window`-dadır.
    total_students = len(enrollments)
    lesson_summary = journal_window.lesson_summaries(lessons, enrollments, mark_map, total_students)

    lesson_meta = [
        {
            "lesson": lesson,
            "is_today": lesson.date == today,
            "editable": can_edit_lesson(lesson, now=now),  # sütun redaktə/silmə (2 saat)
            "markable": lesson.date == today,  # yeni işarə yalnız bu gün
            # xronoloji nömrə (köhnədən yeniyə) — sıra tərs olsa da nömrə sabitdir
            "seq": (total_lessons - (window_offset + idx)) if newest_first else (window_offset + idx + 1),
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
        # Qayıb BÜTÜN dərslər üzrə (pəncərədən asılı deyil).
        for lesson in all_lessons:
            mark = mark_map.get((enrollment.id, lesson.id))
            if mark is not None and mark.status == AttendanceStatus.ABSENT:
                absence_hours += lesson.hours
                absence_count += 1
        for lesson in lessons:
            mark = mark_map.get((enrollment.id, lesson.id))
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
        # Birləşmədən gələn qayıb saatı buraxılış həddinə DAXİLDİR (bax
        # guest_merge): əks halda alt qrup birləşməsi hədd sayğacını sıfırlayardı.
        carry = carry_map.get(enrollment.id)
        own_absence_hours = absence_hours
        if carry:
            absence_hours += carry["absence_hours"]
            absence_count += carry["absence_count"]
        # Canonical entry score (component-weighted when defined, else lesson sum).
        entry_score = entry_score_for(enrollment, scheme.entry_score_max, **entry_batch.entry_kwargs(enrollment))
        eligibility = exam_eligibility.resolve(
            absence_hours=absence_hours,
            lesson_hours=total_hours,
            allowed_hours=allowed_absence,
            limit_percent=limit_percent,
            exempt=enrollment.student_id in exempt_ids,
            frozen=frozen,
        )
        barred = eligibility["barred"]
        # Xəbərdarlıq zolağı da donmuş dilimdə susur: «həddə yaxınlaşır» xəbəri
        # yalnız hələ qərar verilə bilən semestrdə mənalıdır.
        warning = (not frozen) and (not barred) and allowed_absence > 0 and Decimal(absence_hours) >= warn_at
        rows.append(
            {
                "enrollment": enrollment,
                "student": enrollment.student,
                "cells": cells,
                "absence_hours": absence_hours,
                # q/b (qayıb) SAYı — UI saat əvəzinə bunu göstərir (barred saat-limitinə görə).
                "absence_count": absence_count,
                "entry_score": entry_score,
                "barred": barred,
                "warning": warning,
                "eligibility": eligibility,
                # Alt qrupdan əlavə olunmuş tələbə: sətirdə çip + geri götürmə.
                # Şərt CARİ vəziyyətə baxır — rəsmi köçürmədən sonra çip susur.
                "is_guest": guest_roster.row_is_guest(
                    enrollment,
                    offering=offering,
                    current_group_id=current_groups.get(enrollment.student_id),
                ),
                "source_group": enrollment.source_group,
                # Birləşmədən gələn əvvəlki jurnal işi (yoxdursa None).
                "carry_over": carry,
                "own_absence_hours": own_absence_hours,
            }
        )

    return {
        "offering": offering,
        "scheme": scheme,
        "lessons": lessons,
        "lesson_meta": lesson_meta,
        "rows": rows,
        # Alt qrupdan əlavə olunmuş sətirlər (idarəetmə modalının siyahısı).
        "guest_rows": [row for row in rows if row["is_guest"]],
        "today": today,
        "limit_percent": limit_percent,
        "allowed_absence": allowed_absence,
        # İcazə verilən maksimum q/b sayı (1 q/b=2 saat; 25% həddi) — UI "limit N q/b".
        "limit_qb": int(allowed_absence // DEFAULT_LESSON_HOURS) if allowed_absence else 0,
        "entry_score_max": scheme.entry_score_max,
        # Dərs pəncərəsi (P1-8) — şablondakı naviqasiya zolağı üçün.
        "lesson_window": journal_window.window_meta(
            total=total_lessons,
            shown=len(lessons),
            size=window_size,
            offset=window_offset,
            newest_first=newest_first,
        ),
    }


# ── Tələbə görünüşü ("Qiymətlərim") ──────────────────────────────────────────


def get_student_journal_summary(*, record, period, semester_number):
    """Per-subject entry score + attendance for the student view.

    ⚠️ **9-cu səth — QAYIB SAATI DENORMALLAŞMIŞ SAYĞACDAN GƏLİR.**
    Bu funksiya qayıb saatını tələbənin ÖZ işarələrindən yığırdı
    (``sum(m.lesson.hours for m in marks if ABSENT)``) və məhz buna görə
    :func:`recompute_absence_hours` ilə ZİDD idi: o, ``öz işarələr +
    guest_merge.carried_absence_hours(...)`` yazır. Alt qrup birləşməsindən
    sonra hədəf jurnalda tələbənin öz işarəsi hələ yoxdur, yəni bu səth 0 saat
    görüb «buraxılır ✓, davamiyyət 10.00» yazırdı, ``exam_bridge`` isə eyni
    tələbəni imtahandan BLOKLAYIRDI. Üstəlik ``registrar.public`` EYNİ səhifədə
    hər iki rəqəmi göstərirdi (fənn kartı 0, detal paneli 6).

    İndi mənbə digər səkkiz səthlə eynidir: ``Enrollment.absence_hours``.
    İşarələr yalnız giriş balı üçün oxunur (bal dərsə bağlıdır, sayğac deyil).
    """
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
    # Buraxılış statusu donmuş açılışlar — toplu dəst (iki sabit sorğu).
    frozen_ids = exam_eligibility.frozen_offering_ids(offering_ids)
    hours_map = exam_eligibility.lesson_hours_map(offering_ids)
    lesson_counts = {
        row["offering_id"]: row["c"]
        for row in Lesson.objects.filter(offering_id__in=offering_ids).values("offering_id").annotate(c=Count("id"))
    }

    subjects = []
    for enrollment in enrollments:
        offering = enrollment.offering
        marks = marks_by_enr.get(enrollment.id, [])
        # TƏK MƏNBƏ: birləşmə ilə köçürülən saat da buradadır (bax yuxarıdakı şərh).
        absence_hours = enrollment.absence_hours or 0
        scheme = getattr(offering, "assessment_scheme", None)
        cap = scheme.entry_score_max if scheme else 50
        entry_score = entry_score_for(enrollment, cap, marks=marks, components=comps_by_off.get(offering.id, []))
        lessons_held = lesson_counts.get(offering.id, 0)
        total_hours = exam_eligibility.lesson_hours_for(offering, hours_map=hours_map)
        allowed = Decimal(total_hours) * Decimal(limit_percent) / Decimal(100)
        eligibility = exam_eligibility.resolve(
            absence_hours=absence_hours,
            lesson_hours=total_hours,
            allowed_hours=allowed,
            limit_percent=limit_percent,
            # Tək tələbəlik səth — istisna onsuz da qeyddədir (əlavə sorğu yox).
            exempt=bool(record and record.national_athlete_exemption),
            frozen=offering.id in frozen_ids,
        )
        barred = eligibility["barred"]
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
                    "eligibility": eligibility,
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
    round_score,
    save_component_scores,
    save_components,
)

# ── Dərs CRUD ayrıca modulda (modul-ölçü büdcəsi) — re-eksport ──────────────
from apps.registrar.gradebook_lessons import (  # noqa: E402,F401
    _coerce_date,
    create_lesson,
    delete_lesson,
    update_lesson,
    update_lesson_date,
)
