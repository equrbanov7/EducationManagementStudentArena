"""Tələbənin fənn KREDİTİ — sistemdə YEGANƏ həlledici (R01, sahib qərarı 2026-10-21).

Problem (xarici baxış, Postgres-də təsdiqlənib): semestr kredit yükü (``credit_load``) tələbənin tədris planı
sətrinin kreditini, transkript / ÜOMG / qazanılmış kredit / 25% haqqı isə yalnız kataloq ``Subject.ects``-ni
oxuyurdu. Kataloq 5, plan 8 olan fəndə yük 8, transkript 5 sayırdı (ÜOMG 71.00 ↔ 75.85).

QAYDA (sahib: «tövsiyə olunan kimi et»)
───────────────────────────────────────
Kanonik kredit = tələbənin TƏDRİS PLANI sətri — həmin FƏNN və həmin SEMESTR — ``CurriculumSubject.credits > 0``;
belə sətir yoxdursa kataloq ``Subject.ects``.

* **Hansı plan.** Tələbənin akademik qeydinin (``StudentAcademicRecord.curriculum``) planı. Qeyd bir neçədirsə
  (iki ixtisas): aktiv → ``enrolled`` → ən yeni sırası ilə, fənni planında OLAN ilk qeyd.
* **Hansı semestr.** Açılışın dövrünün plan semestri: ``kurs = dövrün tədris ili başlanğıcı − planın qəbul ili + 1``,
  payız → ``2·kurs − 1``, yaz → ``2·kurs`` (``cohort_plans.semester_number_for`` / ``cohort_for_semester`` ilə
  eyni qayda, qrupsuz — tələbəyə bağlı plan üzrə).
* **Seçim** (:func:`pick_credit`, determinist):
  1. gözlənilən semestrdə sətir VARSA — onun krediti (> 0); 0-dırsa kataloq;
  2. yoxdursa (təkrar keçid sonrakı semestrdə, yay dövrü, kurs hesablanmır) — krediti > 0 olan sətirlərdən
     gözlənilən semestrə ƏN YAXIN olanı, bərabərlikdə KİÇİK semestr; semestr ümumiyyətlə bilinmirsə ən kiçik
     semestr (köhnə ``plan_credit_map``-in «ilk sətir» davranışı);
  3. planda fənn yoxdursa — kataloq.
  Fənn planda TƏK sətirdirsə semestr hesablanmır (dövr oxunmur): sətrin krediti (> 0) və ya kataloq.

Kataloq səviyyəli səthlər (fənn kataloqu, birləşmə, cədvəl matrisi — fənnin NOMİNAL krediti) bura GƏLMİR.
Artıq buraxılmış möhürlü sənədlər (``verification.DocumentSeal``) dəyişmir — faktlar buraxılış anında
``payload``-a yazılıb; yenidən buraxılan sənəd yeni rəqəmlərlə yeni möhür alır. 25% müraciətinin
məbləği müraciət anının snapshot-udur (``RetakeApplication.expected_fee`` / ``fee_inputs.credits``) —
bax :mod:`apps.registrar.retake_fees`.

Sorğu büdcəsi: toplu həlledici 2 sabit sorğu (qeydlər + plan sətirləri; qeydlər hazırdırsa 1), sətir sayından
asılı deyil. Dövr yalnız fənn planda bir neçə semestrdə olanda oxunur — dövr başına ən çox bir dəfə (keş).
"""

from __future__ import annotations

import datetime
import re

from django.apps import apps as django_apps

from .models import AcademicStatus, CurriculumSubject, PlanStatus, StudentAcademicRecord

_YEAR_RE = re.compile(r"(\d{4})")
_FALL, _SPRING = 1, 2


def _key(value) -> str:
    return str(value) if value is not None else ""


def _start_year(academic_year) -> int:
    match = _YEAR_RE.search(str(academic_year or ""))
    return int(match.group(1)) if match else 0


def _season(start_date):
    """Payız (avqust–dekabr) / yaz (yanvar–may); yay və bilinməyən — ``None`` (``period_semester_parity`` güzgüsü)."""
    if start_date is None:
        return None
    if isinstance(start_date, str):  # yaddaşda yaradılmış (hələ DB-dən oxunmamış) dövr obyekti
        try:
            start_date = datetime.date.fromisoformat(start_date[:10])
        except ValueError:
            return None
    if start_date.month >= 8:
        return _FALL
    if start_date.month <= 5:
        return _SPRING
    return None


def plan_semester(admission_year, *, academic_year, start_date):
    """Dövrün planın qəbul ilinə görə semestr nömrəsi; hesablanmırsa ``None``."""
    start = _start_year(academic_year)
    season = _season(start_date)
    if not admission_year or not start or season is None:
        return None
    course = start - int(admission_year) + 1
    if course < 1:
        return None
    return course * 2 - 1 if season == _FALL else course * 2


def pick_credit(rows, expected, catalogue) -> int:
    """``rows`` — ``[(semestr, kredit), …]`` (bir plan + bir fənn). Qayda modul şərhindədir."""
    catalogue = int(catalogue or 0)
    if not rows:
        return catalogue
    if expected is not None:
        for semester, credits in rows:
            if semester == expected:
                return int(credits) if credits and credits > 0 else catalogue
    positive = [(semester, credits) for semester, credits in rows if credits and credits > 0]
    if not positive:
        return catalogue
    if expected is None:
        return int(min(positive)[1])
    return int(min(positive, key=lambda row: (abs(row[0] - expected), row[0]))[1])


def _period_ref(offering):
    """Açılışın keşlənmiş dövr obyekti, yoxsa ``period_id`` (sorğu açmadan)."""
    descriptor = type(offering).__dict__.get("period")
    if descriptor is not None and descriptor.is_cached(offering):
        return offering.period
    return getattr(offering, "period_id", None)


def _catalogue(offering) -> int:
    return int(getattr(offering.subject, "ects", 0) or 0)


class CreditResolver:
    """Toplu həlledici: ``credit(student, subject, period=…, catalogue=…)`` — sorğusuz (dövr keşi istisna)."""

    def __init__(self, records, rows, admission):
        self._records = records  # {student_key: [curriculum_key, …]} — üstünlük sırası ilə
        self._rows = rows  # {(curriculum_key, subject_key): [(semestr, kredit), …]} — semestr sırası ilə
        self._admission = admission  # {curriculum_key: qəbul ili}
        self._periods: dict = {}

    def _period_fields(self, period):
        if period is None:
            return None, None
        if hasattr(period, "academic_year"):
            return period.academic_year, period.start_date
        key = _key(period)
        if key not in self._periods:
            AcademicPeriod = django_apps.get_model("organizations", "AcademicPeriod")
            self._periods[key] = AcademicPeriod.objects.filter(pk=period).values_list(
                "academic_year", "start_date"
            ).first() or (None, None)
        return self._periods[key]

    def _pick(self, curriculum_key, rows, period, catalogue) -> int:
        expected = None
        if len(rows) > 1:
            academic_year, start_date = self._period_fields(period)
            expected = plan_semester(
                self._admission.get(curriculum_key), academic_year=academic_year, start_date=start_date
            )
        return pick_credit(rows, expected, catalogue)

    def curriculum_credit(self, curriculum_id, subject_id, *, period=None, catalogue=0) -> int:
        """Konkret planın krediti (tələbə yox, plan verilib — semestr yükü, yerləşdirmə)."""
        curriculum_key = _key(curriculum_id)
        rows = self._rows.get((curriculum_key, _key(subject_id)))
        if not rows:
            return int(catalogue or 0)
        return self._pick(curriculum_key, rows, period, catalogue)

    def _lookup(self, student_id, subject_id):
        subject_key = _key(subject_id)
        for curriculum_key in self._records.get(_key(student_id), ()):
            rows = self._rows.get((curriculum_key, subject_key))
            if rows:
                return curriculum_key, rows
        return None, None

    def credit(self, student_id, subject_id, *, period=None, catalogue=0) -> int:
        curriculum_key, rows = self._lookup(student_id, subject_id)
        if not rows:
            return int(catalogue or 0)
        return self._pick(curriculum_key, rows, period, catalogue)

    def for_enrollment(self, enrollment) -> int:
        offering = enrollment.offering
        curriculum_key, rows = self._lookup(enrollment.student_id, offering.subject_id)
        if not rows:
            return _catalogue(offering)
        # Dövr YALNIZ fənn planda bir neçə semestrdə olanda lazımdır — ``only()`` ilə çəkilmiş açılışda belə
        # təxirə salınmış sahəni boş yerə açmırıq.
        period = _period_ref(offering) if len(rows) > 1 else None
        return self._pick(curriculum_key, rows, period, _catalogue(offering))


def _plan_rows(curriculum_ids, subject_ids=None):
    """``(rows, admission)`` — verilmiş planların sətirləri (TƏK sorğu; ``subject_ids`` list və ya queryset)."""
    curriculum_ids = [value for value in curriculum_ids if value]
    if not curriculum_ids:
        return {}, {}
    queryset = CurriculumSubject.objects.filter(curriculum_id__in=curriculum_ids)
    if subject_ids is not None:
        queryset = queryset.filter(subject_id__in=subject_ids)
    rows: dict = {}
    admission: dict = {}
    for curriculum_id, admission_year, subject_id, semester, credits in queryset.order_by().values_list(
        "curriculum_id", "curriculum__admission_year", "subject_id", "semester_number", "credits"
    ):
        curriculum_key = _key(curriculum_id)
        admission[curriculum_key] = admission_year
        rows.setdefault((curriculum_key, _key(subject_id)), []).append((int(semester or 0), int(credits or 0)))
    for value in rows.values():
        value.sort()
    return rows, admission


def _ordered_records(items) -> dict:
    """``items`` — ``(student_id, curriculum_id, is_active, status, created_at)``; üstünlük sırası modul şərhində."""
    ordered = sorted(items, key=lambda item: (item[4] is not None, item[4]), reverse=True)  # ən yeni əvvəl
    ordered.sort(key=lambda item: (not item[2], item[3] != AcademicStatus.ENROLLED))  # sabit sıralama
    result: dict = {}
    for student_id, curriculum_id, *_rest in ordered:
        bucket = result.setdefault(_key(student_id), [])
        if curriculum_id and _key(curriculum_id) not in bucket:
            bucket.append(_key(curriculum_id))
    return result


def resolver_from_records(records, *, subject_ids=None) -> CreditResolver:
    """Hazır ``StudentAcademicRecord`` obyektlərindən (əlavə qeyd sorğusu yox) — 1 sorğu."""
    items = [
        (r.student_id, r.curriculum_id, bool(r.is_active), r.status, getattr(r, "created_at", None)) for r in records
    ]
    by_student = _ordered_records(items)
    rows, admission = _plan_rows({c for bucket in by_student.values() for c in bucket}, subject_ids)
    return CreditResolver(by_student, rows, admission)


def resolver_for_students(organization, student_ids, *, subject_ids=None) -> CreditResolver:
    """Tələbələrin qeydləri + planlarının sətirləri — 2 sorğu (``student_ids`` / ``subject_ids`` queryset ola bilər)."""
    queryset = StudentAcademicRecord.objects.filter(student_id__in=student_ids)
    organization_id = getattr(organization, "pk", organization)
    if organization_id is not None:
        queryset = queryset.filter(organization_id=organization_id)
    items = list(queryset.values_list("student_id", "curriculum_id", "is_active", "status", "created_at"))
    by_student = _ordered_records(items)
    rows, admission = _plan_rows({c for bucket in by_student.values() for c in bucket}, subject_ids)
    return CreditResolver(by_student, rows, admission)


def resolver_for_curriculum(curriculum, subject_ids=None) -> CreditResolver:
    """Tək plan (obyekt və ya id) — 1 sorğu; ``curriculum_credit`` ilə oxunur."""
    rows, admission = _plan_rows([getattr(curriculum, "pk", curriculum)], subject_ids)
    return CreditResolver({}, rows, admission)


def credits_for_enrollments(enrollments, *, organization=None) -> dict:
    """``{enrollment_id: kredit}`` — N+1-siz (2 sorğu). Queryset verilsə açılış/fənn/dövr birlikdə çəkilir."""
    if hasattr(enrollments, "select_related"):
        enrollments = enrollments.select_related("offering__subject", "offering__period")
    enrollments = list(enrollments)
    if not enrollments:
        return {}
    resolver = resolver_for_students(
        organization if organization is not None else enrollments[0].organization_id,
        {e.student_id for e in enrollments},
        subject_ids={e.offering.subject_id for e in enrollments},
    )
    return {e.pk: resolver.for_enrollment(e) for e in enrollments}


def credit_for_enrollment(enrollment) -> int:
    """Bir yazılışın krediti (tələbənin planı → kataloq)."""
    return credits_for_enrollments([enrollment], organization=enrollment.organization_id)[enrollment.pk]


def credits_for_offerings_and_curriculum(offerings, curriculum, *, period=None) -> dict:
    """``{offering_id: kredit}`` — verilmiş planda (1 sorğu). ``period`` verilməsə açılışın öz dövrü."""
    offerings = list(offerings)
    if not offerings:
        return {}
    resolver = resolver_for_curriculum(curriculum, {o.subject_id for o in offerings})
    curriculum_id = getattr(curriculum, "pk", curriculum)
    return {
        o.pk: resolver.curriculum_credit(
            curriculum_id, o.subject_id, period=period or _period_ref(o), catalogue=_catalogue(o)
        )
        for o in offerings
    }


def credit_for_offering_and_curriculum(offering, curriculum, *, period=None) -> int:
    """Bir açılışın verilmiş plandakı krediti; plan yoxdursa (``None``) kataloq."""
    if curriculum is None:
        return _catalogue(offering)
    return credits_for_offerings_and_curriculum([offering], curriculum, period=period)[offering.pk]


def plan_row_credit(plan_row) -> int:
    """Plan sətrinin özünün krediti (> 0), yoxsa fənnin kataloq dəyəri — dərs yükü təklifləri üçün."""
    credits = int(getattr(plan_row, "credits", 0) or 0)
    return credits if credits > 0 else int(getattr(plan_row.subject, "ects", 0) or 0)


def plan_credit_for_offering(offering) -> int:
    """Qrup açılışının (tələbəsiz — sillabus) krediti: qrupun ixtisası + kohortunun TƏSDİQLƏNMİŞ planı.

    ``plan_hours.plan_hours_for_subject`` ilə eyni plan seçimi (ixtisas + kohort, sonra ixtisasın ən yeni planı);
    başqa ixtisasın planına GERİ ÇƏKİLMİR (kredit ixtisasa görə dəyişir) — tapılmasa kataloq.
    """
    if offering is None:
        return 0
    from apps.organizations.public import group_cohort_year

    from .models import Curriculum
    from .plan_hours import program_for_offering

    program = program_for_offering(offering)
    if program is None:
        return _catalogue(offering)
    plans = list(
        Curriculum.objects.filter(
            organization_id=offering.organization_id,
            program=program,
            status=PlanStatus.APPROVED,
            rows__subject_id=offering.subject_id,
        )
        .order_by("-admission_year", "-version")
        .values_list("pk", "admission_year")
        .distinct()
    )
    if not plans:
        return _catalogue(offering)
    cohort = group_cohort_year(offering.group) if offering.group_id else None
    chosen = next((pk for pk, year in plans if cohort and int(year) == int(cohort)), plans[0][0])
    return credit_for_offering_and_curriculum(offering, chosen)


__all__ = [
    "CreditResolver",
    "credit_for_enrollment",
    "credit_for_offering_and_curriculum",
    "credits_for_enrollments",
    "credits_for_offerings_and_curriculum",
    "pick_credit",
    "plan_credit_for_offering",
    "plan_row_credit",
    "plan_semester",
    "resolver_for_curriculum",
    "resolver_for_students",
    "resolver_from_records",
]
