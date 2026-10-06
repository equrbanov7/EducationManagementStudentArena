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
from decimal import Decimal, InvalidOperation

from django.db.models import Count
from django.utils import timezone

from apps.registrar import absence_limit, exam_eligibility, journal_window, services
from apps.registrar.models import (
    AssessmentScheme,
    AttendanceStatus,
    Enrollment,
    Lesson,
    LessonKind,
    LessonMark,
)

# Redaktə pəncərələri (defolt 2 saat; RİM rəhbəri «Sistem tənzimləmələri»ndən dəyişir; DB trigger də qoruyur).
from .journal_edit_windows import LESSON_EDIT_WINDOW, lesson_edit_window, mark_edit_window  # noqa: E402,F401

DEFAULT_LESSON_HOURS = 2

#: "Verilməyib" sentineli — ``None`` özü mənalı dəyərdir (məs. otağı təmizlə),
#: ona görə "dəyişmə" halını ondan ayırmaq lazımdır (gradebook_lessons işlədir).
UNSET = object()
LESSON_SCORE_MAX = Decimal("10")  # seminar/lab balı: min 0, max 10
_DEFAULT_ABSENCE_LIMIT = absence_limit.DEFAULT_LIMIT_PERCENT  # tək mənbə (F-06, 2026-09-14)
_WARN_RATIO = absence_limit.WARN_RATIO  # limitin bu payına çatanda xəbərdarlıq (bozarır)

SCORE_LESSON_KINDS = frozenset({LessonKind.SEMINAR, LessonKind.LAB})


class LessonRuleError(Exception):
    """Dərs qaydası pozuntusu (keçmiş tarix, pəncərə bitib və s.) — istifadəçiyə
    göstərilə bilən mesaj daşıyır."""


def _to_decimal(raw) -> Decimal:
    try:
        return Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


_SCHEME_MEMO_ATTR = "_assessment_scheme_memo"


def ensure_assessment_scheme(*, offering):
    """Idempotently return the offering's journal config.

    Oxu yolunda (`preload_assessment_scheme`) eyni offering obyektinə memo
    qoyulubsa təkrar ``get_or_create`` getmir — jurnal səhifəsi bunu 4 dəfə
    çağırırdı (journal_is_locked, roster_block_reason, get_offering_journal…)."""
    memo = getattr(offering, _SCHEME_MEMO_ATTR, None)
    if memo is not None:
        return memo
    scheme, _created = AssessmentScheme.objects.get_or_create(organization=offering.organization, offering=offering)
    return scheme


def preload_assessment_scheme(offering):
    """YALNIZ oxu yolu (journal_detail GET): sxemi bir dəfə oxuyub obyektə yapışdırır.
    Yazı yolları memo qoymur — testlər/servislər həmişə canlı sorğu görür."""
    setattr(offering, _SCHEME_MEMO_ATTR, ensure_assessment_scheme(offering=offering))


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
    """Dərs sətri (tarix/növ/mövzu/saat/silmə) yalnız yaranışdan sonra pəncərə (defolt 2 saat) içində."""
    now = now or timezone.now()
    return (now - lesson.created_at) <= lesson_edit_window()


# Köhnə ad — mövcud çağırışlar üçün.
can_edit_lesson_date = can_edit_lesson


def can_edit_mark(mark, *, now=None) -> bool:
    """A missing mark is always writable; an existing one only within the window."""
    if mark is None:
        return True
    now = now or timezone.now()
    return (now - mark.created_at) <= mark_edit_window()


# Hədd resolver-ləri TƏK mənbədədir (:mod:`apps.registrar.absence_limit`, F-06 / 2026-09-14);
# köhnə adlar geriyə-uyğunluq üçün qalır (açılış-səviyyəli başlıq dəyəri).
absence_limit_percent_for = absence_limit.limit_percent_for_offering
_allowed_absence_hours = absence_limit.allowed_absence_hours


# ── Mark (iştirak/bal) yazma + qayıb sayğacı ayrıca modulda (modul-ölçü büdcəsi) ──
# Tutum 2026-10-06: yazı redaktə olunan xanalara mütənasibdir (bax gradebook_marks).
# ⚠️ Bu re-eksport ``gradebook_lessons``-dan ƏVVƏL olmalıdır: o, ``recompute_absence_hours``-u
# buradan idxal edir. ``gradebook_marks`` bu modulu yalnız çağırış vaxtı idxal edir (dövr yox).
from apps.registrar.gradebook_marks import (  # noqa: E402,F401
    recompute_absence_hours,
    recompute_absence_hours_many,
    save_marks,
)


def _lesson_parity(offering, lesson) -> str:
    """Dərs tarixinin üst/alt həftə pariteti ('odd'/'even') — başlıq etiketləri."""
    from datetime import timedelta as _td

    from apps.registrar import schedule as _schedule

    monday = lesson.date - _td(days=lesson.date.weekday())
    return _schedule.week_parity(offering.period, monday)


# ── Jurnal görünüşü (müəllim grid) ───────────────────────────────────────────


def get_offering_journal(*, offering, newest_first=False, lesson_limit=None, lesson_offset=0, lesson_kind=""):
    """Full journal grid: lessons (columns) × enrolled students (rows) + summary.

    One pass over the marks (no per-cell query). Each row carries the running
    absence hours, the accumulated entry score (giriş balı, capped) and the
    barred / warning status used to grey or redden the row.
    ``newest_first=True`` → sütun sırası tərs (ən yeni dərs adların yanında) —
    müəllim grid-i üçün; export xronoloji qalır.

    DƏRS PƏNCƏRƏSİ (QA 2026-09-05 P1-8): ``lesson_limit``/``lesson_offset`` YALNIZ
    göstərilən SÜTUNLARI kəsir — qayıb saatı, giriş balı və buraxılış qərarı
    HƏMİŞƏ bütün dərslər üzrədir; ``lesson_window`` şablona naviqasiya metası verir.

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

    entry_batch = finals_batch.entry_batch(enrollments, marks_by_enrollment=finals_batch.group_marks(mark_map.values()))
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
    guest_docs = guest_roster.guest_document_map(guest_ids)  # alt-qrup sənədi (təqdimat)
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
    # Sətir üzrə qərar TƏLƏBƏNİN ÖZ həddi ilə (F-06 / 2026-09-14) — bir toplu sorğu.
    row_limits = absence_limit.row_limits(
        organization_id=offering.organization_id, enrollments=enrollments, total_hours=total_hours
    )
    entry_batch.provide_attendance(hours_map={offering.id: total_hours}, limits=row_limits, exempt_ids=exempt_ids)

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
        row_limit = row_limits[enrollment.student_id]
        eligibility = exam_eligibility.resolve(
            absence_hours=absence_hours,
            lesson_hours=total_hours,
            allowed_hours=row_limit.allowed_hours,
            limit_percent=row_limit.percent,
            exempt=enrollment.student_id in exempt_ids,
            frozen=frozen,
        )
        barred = eligibility["barred"]
        # Xəbərdarlıq zolağı da donmuş dilimdə susur: «həddə yaxınlaşır» xəbəri
        # yalnız hələ qərar verilə bilən semestrdə mənalıdır.
        warning = absence_limit.near_limit(absence_hours, row_limit, frozen=frozen, barred=barred)
        rows.append(
            {
                "enrollment": enrollment,
                "student": enrollment.student,
                "cells": cells,
                "absence_hours": absence_hours,
                # q/b (qayıb) SAYı — UI saat əvəzinə bunu göstərir (barred saat-limitinə görə).
                "absence_count": absence_count,
                "allowed_absence": row_limit.allowed_hours,  # tələbənin ÖZ həddi (F-06)
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
                "guest_document": guest_docs.get(enrollment.id),  # (sənəd, qorunan URL) və ya None
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


def get_student_journal_summary(*, record, period, semester_number, enrollments=None, hours_map=None, frozen_ids=None):
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
    # Tutum 2026-10-06: yalnız yazılışlar lazımdır (seçmə blokları/qərarları yox); «Fənlərim»
    # onları + saat/donma dəstlərini ARTIQ oxuyub ötürür (eyni sorğular təkrarlanmırdı).
    if enrollments is None:
        enrollments = services.get_student_semester_enrollments(record=record, period=period)
    limit_percent = absence_limit.limit_percent_for_record(record)
    if not enrollments:
        return {"subjects": []}

    # ── Toplu (batch) sorğular — per-subject N+1-i aradan qaldırır ──────────────
    enr_ids = [e.id for e in enrollments]
    offering_ids = list({e.offering_id for e in enrollments})
    marks_by_enr: dict = defaultdict(list)
    for m in LessonMark.objects.filter(enrollment_id__in=enr_ids).select_related("lesson"):
        marks_by_enr[m.enrollment_id].append(m)
    from apps.registrar import finals_batch

    if hours_map is None:
        hours_map = exam_eligibility.lesson_hours_map(offering_ids)
    # Giriş balı oxumaları BİR dəfə (fənn başına 1–3 sorğu idi); Midterm davamiyyəti eyni saat/hədd ilə.
    entry_batch = finals_batch.student_entry_batch(enrollments, record, period, marks_by_enr, hours_map)
    # Buraxılış statusu donmuş açılışlar — toplu dəst (iki sabit sorğu).
    if frozen_ids is None:
        frozen_ids = exam_eligibility.frozen_offering_ids(offering_ids)
    lesson_counts = {
        row["offering_id"]: row["c"]
        for row in Lesson.objects.filter(offering_id__in=offering_ids).values("offering_id").annotate(c=Count("id"))
    }

    subjects = []
    for enrollment in enrollments:
        offering = enrollment.offering
        # TƏK MƏNBƏ: birləşmə ilə köçürülən saat da buradadır (bax yuxarıdakı şərh).
        absence_hours = enrollment.absence_hours or 0
        scheme = getattr(offering, "assessment_scheme", None)
        cap = scheme.entry_score_max if scheme else 50
        entry_score = entry_score_for(enrollment, cap, **entry_batch.entry_kwargs(enrollment))
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
