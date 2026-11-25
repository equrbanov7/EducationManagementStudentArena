"""«Fərdi tədris planı» — tədris planı boş olanda və ya tələbə başqa qrupun jurnalında oxuyanda sətirlərin ikinci mənbəyi.

Sahib 2026-11-25 («234 SBİO az fərdi plan.docx» nümunəsi): yüklənən sənəddə cədvəllər BOŞ gəlirdi — sənəd yalnız
tələbənin tədris planından (``CurriculumSubject``, semestr 2·kurs−1 / 2·kurs) qurulurdu, həmin semestrlərin sətri
olmayan planda heç nə düşmürdü; «Əlavə olaraq» (əcnəbi qrupu) əlavə olunan tələbənin sənədi də boş idi — o, qrupun
öz siyahısında deyil.

Qayda (semestr üzrə):

* tədris planında həmin semestrin sətirləri VARSA — onlar qalır (rəsmi plan), üstəlik tələbənin həmin semestrdə
  BAŞQA qrupun jurnalındakı fənləri (əlavə qrup / alt qrup) «Qeyd» sütununda qrup adı ilə əlavə olunur;
* sətir YOXDURSA — tələbənin həmin semestrdəki jurnalları (``Enrollment``: qeydiyyatlı / tamamlanmış, tarixçəyə
  keçməmiş) sətir olur; yaz semestrində hələ jurnal yoxdursa — qrupun yaz açılışları.

Sətir: fənnin kodu = planın şifri (varsa), yoxsa fənnin kodu (daxili ``MYEDU-*`` heç vaxt yazılmır); saat = jurnalın
saat cəmi; kredit = fənnin ECTS-i; kafedra = fənnin kafedrası; müəllim = jurnalın sahibi.

Sorğu büdcəsi (perf auditi F-03): qrup sənədində tələbə sayı artanda sorğu sayı ARTMAMALIDIR — bütün tələbələrin
jurnalları :class:`PlanSources` ilə bir sorğuda, planın şifrləri kurikulum üzrə bir dəfə, qrup açılışları qrup cütü
üzrə bir dəfə yüklənir.
"""

from __future__ import annotations

from django.apps import apps as django_apps

_COUNTED_STATUSES = ("enrolled", "completed")


def _code(subject, plan_codes: dict) -> str:
    code = (plan_codes.get(subject.pk) or "").strip()
    if code:
        return code
    raw = (subject.code or "").strip()
    return "" if raw.upper().startswith("MYEDU") else raw


def _teacher(offering) -> str:
    instructor = offering.instructor
    if instructor is None:
        return ""
    return (instructor.get_full_name() or "").strip() or instructor.username


def _chair(subject) -> str:
    return (getattr(getattr(subject, "chair_unit", None), "name", "") or "").strip()


def _first_per_subject(offerings) -> list:
    seen, result = set(), []
    for offering in offerings:
        if offering.subject_id in seen:
            continue
        seen.add(offering.subject_id)
        result.append(offering)
    return result


def offering_row(offering, *, plan_codes_map: dict, note: str = "") -> dict:
    subject = offering.subject
    return {
        "code": _code(subject, plan_codes_map),
        "subject": (subject.name or "").strip(),
        "hours": int(offering.lesson_hours or 0),
        "credits": int(subject.ects or 0),
        "chair": _chair(subject),
        "teacher": _teacher(offering),
        "note": note,
        "subject_id": subject.pk,
    }


class PlanSources:
    """Bir sənəd üçün toplu mənbə: tələbələrin jurnalları, kurikulum şifrləri, qrup açılışları (keşlə)."""

    def __init__(self, organization, period_ids):
        self.organization = organization
        self.period_ids = list(period_ids or ())
        self._offerings_by_student: dict | None = None
        self._student_ids: set = set()
        self._codes: dict = {}
        self._group_offerings: dict = {}

    def prime(self, student_ids) -> None:
        """Sənədin bütün tələbələrinin jurnalları BİR sorğuda (çağırılmasa ilk ehtiyacda tək tələbə üçün)."""
        self._student_ids = {sid for sid in student_ids if sid}
        self._offerings_by_student = {}
        if not self._student_ids or not self.period_ids:
            return
        Enrollment = django_apps.get_model("registrar", "Enrollment")
        enrollments = (
            Enrollment.objects.filter(
                organization=self.organization,
                student_id__in=list(self._student_ids),
                status__in=_COUNTED_STATUSES,
                superseded_by__isnull=True,
                offering__period_id__in=self.period_ids,
                offering__is_active=True,
            )
            .select_related(
                "offering",
                "offering__subject",
                "offering__subject__chair_unit",
                "offering__instructor",
                "offering__group",
            )
            .order_by("offering__subject__name", "offering__created_at")
        )
        for enrollment in enrollments:
            self._offerings_by_student.setdefault(enrollment.student_id, []).append(enrollment.offering)

    def student_offerings(self, student_id, period_ids) -> list:
        if self._offerings_by_student is None or student_id not in self._student_ids:
            known = set(self._student_ids)
            self.prime(known | {student_id})
        wanted = set(period_ids or ())
        offerings = [item for item in self._offerings_by_student.get(student_id, []) if item.period_id in wanted]
        return _first_per_subject(offerings)

    def student_teachers(self, student_id, period_ids) -> dict:
        """``subject_id → müəllim`` — tələbənin həmin semestrdəki öz jurnallarından (keçmiş illər üçün əsas mənbə)."""
        if not period_ids:
            return {}
        return {
            offering.subject_id: name
            for offering in self.student_offerings(student_id, period_ids)
            if (name := _teacher(offering))
        }

    def plan_codes(self, curriculum_id) -> dict:
        """``subject_id → row_code`` kurikulumdan (fənn başqa semestrdə olsa da kod eynidir) — kurikulum üzrə bir dəfə."""
        if not curriculum_id:
            return {}
        if curriculum_id not in self._codes:
            CurriculumSubject = django_apps.get_model("registrar", "CurriculumSubject")
            codes: dict = {}
            for subject_id, row_code in CurriculumSubject.objects.filter(curriculum_id=curriculum_id).values_list(
                "subject_id", "row_code"
            ):
                if row_code and subject_id not in codes:
                    codes[subject_id] = row_code
            self._codes[curriculum_id] = codes
        return self._codes[curriculum_id]

    def group_offerings(self, group_ids, period_ids) -> list:
        """Qrup(lar)ın aktiv açılışları — yaz jurnalı hələ qeydiyyatsız olanda (qrup/dövr cütü üzrə bir dəfə)."""
        key = (tuple(sorted(str(gid) for gid in group_ids if gid)), tuple(sorted(str(pid) for pid in period_ids)))
        if not key[0] or not key[1]:
            return []
        if key not in self._group_offerings:
            CourseOffering = django_apps.get_model("registrar", "CourseOffering")
            self._group_offerings[key] = _first_per_subject(
                CourseOffering.objects.filter(
                    organization=self.organization,
                    group_id__in=[gid for gid in group_ids if gid],
                    period_id__in=list(period_ids),
                    is_active=True,
                )
                .select_related("subject", "subject__chair_unit", "instructor", "group")
                .order_by("subject__name", "created_at")
            )
        return self._group_offerings[key]

    def semester_extra_rows(self, record, *, period_ids, curriculum_subject_ids, home_group_id, fallback_groups):
        """Semestrin əlavə sətirləri (dict-lər).

        ``curriculum_subject_ids`` boşdursa (planda bu semestr yoxdur) tələbənin bütün jurnalları; doludursa yalnız
        planda OLMAYAN və başqa qrupun jurnalı olan fənlər (qeyddə həmin qrupun adı). Jurnal yoxdursa
        ``fallback_groups``-un açılışları (yalnız plan boş olanda).
        """
        codes = self.plan_codes(getattr(record, "curriculum_id", None))
        offerings = self.student_offerings(record.student_id, period_ids)
        if not offerings and not curriculum_subject_ids:
            offerings = self.group_offerings(fallback_groups, period_ids)
        rows = []
        for offering in offerings:
            foreign_group = bool(offering.group_id) and offering.group_id != home_group_id
            if curriculum_subject_ids and (offering.subject_id in curriculum_subject_ids or not foreign_group):
                continue
            note = getattr(offering.group, "name", "") if foreign_group else ""
            rows.append(offering_row(offering, plan_codes_map=codes, note=note))
        return rows


def extra_member_records(organization, group, period_ids) -> list:
    """Qrupun «əlavə üzvləri»: öz qrupu başqadır, bu qrupun həmin dövrlərdəki jurnalında qeydiyyatlıdır."""
    if group is None or not period_ids:
        return []
    Enrollment = django_apps.get_model("registrar", "Enrollment")
    StudentAcademicRecord = django_apps.get_model("registrar", "StudentAcademicRecord")
    student_ids = set(
        Enrollment.objects.filter(
            organization=organization,
            status__in=_COUNTED_STATUSES,
            superseded_by__isnull=True,
            offering__group=group,
            offering__period_id__in=list(period_ids),
            offering__is_active=True,
        ).values_list("student_id", flat=True)
    )
    if not student_ids:
        return []
    return list(
        StudentAcademicRecord.objects.filter(organization=organization, student_id__in=student_ids, is_active=True)
        .exclude(group=group)
        .select_related(
            "student", "student__profile", "program", "program__specialty_unit", "curriculum", "group", "group__parent"
        )
        .order_by("student__last_name", "student__first_name", "student__username")
    )


__all__ = ["PlanSources", "extra_member_records", "offering_row"]
