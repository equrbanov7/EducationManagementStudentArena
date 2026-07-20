"""``seed_stress_exam_journal --seed-past-years`` üçün keçmiş illər datası.

Sahibin "Ümumi tədris məlumatı" (overall-academic) bölməsini VİZUAL test edə
bilməsi üçün ≥2 keçmiş tədris ili (2022/2023, 2023/2024 Payız) + hər ildə 4
fənn yaradır. HƏDƏF tələbədə (``students[0]``) TAM qarışıq nəticə dəsti
əmələ gəlir: A/B/C/D/E keçən fənlər + BİR barred (25% qayıb) + BİR q/b-dan
kəsilmə + BİR imtahandan kəsilmə — eyni tələbədə, beləliklə "İmtahana
buraxılmayan (25%)" və "Q/b-dan kəsilən" filtrləri AYRI-AYRI sətir qaytarır
(bax: ``apps.registrar.transcript._fail_reason_code`` — barred/exam/qb/total
prioritet zənciri, və ``apps.registrar.finals.compute_final_result``).

Komanda modulunun ölçü büdcəsini (``scripts/check_module_size.py``) aşmamaq
üçün ayrıca fayla çıxarılıb (``_seed_helpers``/``_final_exam_demo_data.py``
ilə eyni naming pattern) — ``seed_stress_exam_journal.py`` yalnız bu faylın
``seed_past_years``-ini çağırır.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from apps.organizations.models import AcademicPeriod, OrgUnit
from core.constants import AcademicPeriodType, OrgUnitType

PAST_YEAR_SPECS = [
    {
        "academic_year": "2022/2023",
        "period_name": "Payız semestri",
        "start_date": datetime.date(2022, 9, 1),
        "end_date": datetime.date(2023, 1, 31),
        "semester_number": 3,
        "subjects": [
            ("STR201", "Stress Fənni IV", "A"),
            ("STR202", "Stress Fənni V", "B"),
            ("STR203", "Stress Fənni VI", "C"),
            ("STR204", "Stress Fənni VII", "barred"),
        ],
    },
    {
        "academic_year": "2023/2024",
        "period_name": "Payız semestri",
        "start_date": datetime.date(2023, 9, 1),
        "end_date": datetime.date(2024, 1, 31),
        "semester_number": 4,
        "subjects": [
            ("STR301", "Stress Fənni VIII", "D"),
            ("STR302", "Stress Fənni IX", "E"),
            ("STR303", "Stress Fənni X", "qb"),
            ("STR304", "Stress Fənni XI", "exam"),
        ],
    },
]

# Hədəf tələbə üçün: 5 seminar dərsinin balları (giriş balı cəmi), yekun imtahan
# faizi (0-100 xam, None = imtahan verilmir — barred) və qeybə buraxılan dərs
# sayı. barred/qb/exam fərqi ``finals.compute_final_result``-un eyni məntiqi ilə
# canlı yaranır (bura yalnız XAM giriş verir, hərf/fail_reason burada YAZILMIR):
#   barred → başqa heç nə yoxlanmır; exam → exam_score < min_final_exam_score (17);
#   qb     → exam_ok=True AMMA total < pass_threshold (51, aşağı giriş balına görə).
OUTCOME_PLAN = {
    "A": {"entry": [10, 10, 10, 10, 5], "exam_percent": 100, "absent": 0},
    "B": {"entry": [10, 10, 10, 10, 0], "exam_percent": 90, "absent": 0},
    "C": {"entry": [10, 10, 10, 5, 0], "exam_percent": 80, "absent": 0},
    "D": {"entry": [10, 10, 10, 0, 0], "exam_percent": 70, "absent": 0},
    "E": {"entry": [10, 10, 5, 0, 0], "exam_percent": 60, "absent": 0},
    "qb": {"entry": [5, 0, 0, 0, 0], "exam_percent": 40, "absent": 0},
    "exam": {"entry": [10, 10, 5, 0, 0], "exam_percent": 20, "absent": 0},
    "barred": {"entry": [8, 8, 8, 8, 8], "exam_percent": None, "absent": 3},
}

# Bütün yeni offering-lər üçün ümumi dərs saatı (qayıb % hesabı bazası) — 20 saat
# + 25% limit = 5 saat icazəli; "barred" 3 dərs × 2 saat = 6 > 5.
LESSON_HOURS = 20
BASELINE_SCORE = Decimal("6")  # hədəf olmayan tələbələr üçün hər dərsdə sabit bal
BASELINE_EXAM_PERCENT = 70


def _seed_offering(*, org, teacher, offering, target, outcome_key):
    """Bir keçmiş-il offering-i: 5 seminar dərsi + qeydlər + imtahan balı."""
    from apps.registrar.gradebook import recompute_absence_hours
    from apps.registrar.models import AttendanceStatus, Lesson, LessonKind, LessonMark
    from apps.registrar.public import record_exam_result

    plan = OUTCOME_PLAN[outcome_key]
    enrollments = list(offering.enrollments.select_related("student"))
    target_enr = next((e for e in enrollments if e.student_id == target.id), None)
    start = offering.period.start_date + datetime.timedelta(days=14)

    for i in range(5):
        lesson, created = Lesson.objects.get_or_create(
            organization=org,
            offering=offering,
            date=start + datetime.timedelta(days=i * 7),
            defaults={"kind": LessonKind.SEMINAR, "hours": 2},
        )
        if not created:
            continue
        marks = []
        for enr in enrollments:
            if enr.student_id == target.id:
                absent = i < plan["absent"]
                status = AttendanceStatus.ABSENT if absent else AttendanceStatus.PRESENT
                score = None if absent else Decimal(plan["entry"][i])
            else:
                status, score = AttendanceStatus.PRESENT, BASELINE_SCORE
            marks.append(LessonMark(organization=org, lesson=lesson, enrollment=enr, status=status, score=score))
        LessonMark.objects.bulk_create(marks, batch_size=500, ignore_conflicts=True)

    if plan["absent"] and target_enr is not None:
        recompute_absence_hours(enrollment=target_enr)
    if plan["exam_percent"] is not None:
        record_exam_result(
            student=target,
            subject_id=offering.subject_id,
            organization=org,
            score_percent=plan["exam_percent"],
            by_user=teacher,
        )
    for enr in enrollments:
        if enr.student_id != target.id:
            record_exam_result(
                student=enr.student,
                subject_id=offering.subject_id,
                organization=org,
                score_percent=BASELINE_EXAM_PERCENT,
                by_user=teacher,
            )


def seed_past_years(*, org, teacher, students) -> dict:
    """≥2 keçmiş tədris ili + hər ildə 4 fənn; ``students[0]`` bütün nəticə
    kodlarını (A-E/barred/qb/exam) əhatə edir. Qaytarır ``{subject_code:
    CourseOffering}`` (boş dict → proqram/kurikulum/qrup tapılmadı; STR-i bu
    faylın ``_seed_journal``-ı artıq yaratmışdır)."""
    from apps.registrar import services
    from apps.registrar.models import (
        CourseOffering,
        Curriculum,
        CurriculumSubject,
        Program,
        StudentAcademicRecord,
        Subject,
    )

    program = Program.objects.filter(organization=org, code="STR").first()
    curriculum = Curriculum.objects.filter(organization=org, program=program).first() if program else None
    unit = OrgUnit.objects.filter(organization=org, unit_type=OrgUnitType.GROUP).first()
    if program is None or curriculum is None or unit is None or not students:
        return {}

    target = students[0]
    offerings: dict = {}
    for year in PAST_YEAR_SPECS:
        period, _created = AcademicPeriod.objects.get_or_create(
            organization=org,
            name=year["period_name"],
            academic_year=year["academic_year"],
            defaults={
                "period_type": AcademicPeriodType.SEMESTER,
                "start_date": year["start_date"],
                "end_date": year["end_date"],
                "is_current": False,
            },
        )
        subjects = []
        for code, name, outcome in year["subjects"]:
            subject, _ = Subject.objects.get_or_create(organization=org, code=code, defaults={"name": name})
            CurriculumSubject.objects.get_or_create(
                organization=org, curriculum=curriculum, subject=subject, semester_number=year["semester_number"]
            )
            subjects.append((subject, outcome))

        for student in students:
            record = StudentAcademicRecord.objects.filter(organization=org, student=student).first()
            if record is not None:
                services.enroll_mandatory_subjects(
                    record=record, period=period, semester_number=year["semester_number"]
                )

        for subject, outcome in subjects:
            offering = CourseOffering.objects.filter(
                organization=org, subject=subject, period=period, group=unit
            ).first()
            if offering is None:
                continue
            changed = []
            if offering.instructor_id != teacher.id:
                offering.instructor = teacher
                changed.append("instructor")
            if offering.lesson_hours != LESSON_HOURS:
                offering.lesson_hours = LESSON_HOURS
                changed.append("lesson_hours")
            if changed:
                offering.save(update_fields=changed)
            _seed_offering(org=org, teacher=teacher, offering=offering, target=target, outcome_key=outcome)
            offerings[subject.code] = offering
    return offerings
