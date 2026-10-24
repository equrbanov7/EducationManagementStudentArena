"""TƏSDİQLƏNMİŞ tədris planından auditoriya saatı bölgüsü.

README §8/11: «Auditoriya saatlarının cəmi tədris planındakı saatla üst-üstə
düşməlidir; uyğunsuzluq təsdiqə göndərməni bloklayır.»  Sillabusun həftəlik
cədvəli məhz bu bölgü ilə tutuşdurulur (``SyllabusVersion.plan_hours``).

Mənbə YALNIZ təsdiqlənmiş plandır (``Curriculum.status == APPROVED``): qaralama
plan sətri hələ rəsmi deyil, ona görə sillabusa qapı olaraq qoyulmur.  Bölgü
tapılmasa BOŞ dict qaytarılır — uydurma saat yazılmır və sillabus qaydası öz
növbəsində «plan yoxdursa məhdudiyyət də yoxdur» semantikası ilə işləyir
(bax ``apps/syllabus/completion.py::_check_week``).

Niyə burada: ``apps.syllabus`` registrar-ı import ETMİR (modul sərhədi), ona görə
bölgünü sillabusa ÖTÜRƏN tərəf registrar/accounts qatıdır.
"""

from __future__ import annotations

from .models import Curriculum, CurriculumSubject, PlanStatus
from .plan_hours_load import workload_hours_for_offering  # noqa: F401 — köhnə idxal yolu (public_services)

#: Plan sətrindəki saat sahəsi → sillabusun saat növü açarı.
HOUR_FIELDS = (
    ("lecture_hours", "lecture"),
    ("seminar_hours", "seminar"),
    ("lab_hours", "lab"),
)


def _row_hours(row) -> dict:
    hours = {}
    for field, kind in HOUR_FIELDS:
        value = int(getattr(row, field, 0) or 0)
        if value > 0:
            hours[kind] = value
    return hours


def plan_hours_for_subject(*, organization, subject, program=None, admission_year=None, program_only=False):
    """Fənn üçün təsdiqlənmiş plan sətrinin saat bölgüsü (``{}`` — tapılmadı).

    ``program`` verilibsə həmin ixtisasın planına üstünlük verilir; ``admission_year`` (qrupun kohortu,
    2026-10-19 qaydası — ``cohort_plans``) da verilibsə ƏVVƏL həmin qəbul ilinin planı; verilməsə (və
    ya tapılmasa) təşkilatın ən yeni qəbul ilinə aid təsdiqlənmiş planı
    götürülür.  Kredit/saat İXTİSASA görə dəyişdiyi üçün (layihə yaddaşı) proqram
    uyğunluğu ƏHƏMİYYƏTLİDİR — geri çəkilmə yalnız heç nə tapılmayanda işə düşür.
    ``program_only`` — geri çəkilmə YOXDUR: yalnız qrupun öz ixtisasının planı (sahib 2026-10-25).
    """
    if subject is None or (program_only and program is None):
        return {}
    base = CurriculumSubject.objects.filter(
        organization=organization,
        subject=subject,
        curriculum__status=PlanStatus.APPROVED,
    ).select_related("curriculum")
    ordered = base.order_by("-curriculum__admission_year", "-curriculum__version")
    if program is not None and admission_year:
        row = ordered.filter(curriculum__program=program, curriculum__admission_year=admission_year).first()
        if row is not None:
            return _row_hours(row)
    if program is not None:
        row = ordered.filter(curriculum__program=program).first()
        if row is not None:
            return _row_hours(row)
    if program_only:
        return {}
    row = ordered.first()
    return _row_hours(row) if row is not None else {}


def plan_hours_for_offering(offering):
    """Açılışın sillabus saatı — BİR QRUPUN bölgüsü (müəllimin ümumi yükü DEYİL).

    Qrup ``OrgUnit``-dir və onun valideyni adətən İXTİSAS bölməsidir; ixtisas
    bölməsi ilə ``registrar.Program.specialty_unit`` arasındakı bağ proqramı
    verir.  Bağ tapılmasa proqramsız (ən yeni plan) yola davam edilir.
    """
    if offering is None:
        return {}
    from core.academic_rules import syllabus_hours_from_load

    def from_plan(program_only=False):
        from .cohort_plans import group_cohort_year

        program = program_for_offering(offering)
        if program_only and program is None:
            return {}
        return plan_hours_for_subject(
            organization=offering.organization,
            subject=offering.subject,
            program=program,
            admission_year=group_cohort_year(offering.group) if offering.group_id else None,
            program_only=program_only,
        )

    # Sahib 2026-10-12: «sillabus dərs saatı YÜKƏ görə tənzimlənsin — müəllim əl ilə yazmasın» (RİM açarı
    # `syllabus.hours_from_load`, defolt yanılı). Sahib 2026-10-25: sillabus fənnin BİR QRUP üçün saatıdır —
    # (1) qrupun ÖZ ixtisasının təsdiqlənmiş planı (fənn + ixtisas + kohort), (2) yük sətirlərində bir qrupa düşən
    # pay (``plan_hours_load``: birgə mühazirə bir dəfə, seminar/lab bir qrupun payı), (3) fənnin istənilən
    # təsdiqlənmiş planı. Söndürülüdə əvvəlki sıra (plan → yük).
    if syllabus_hours_from_load():
        return from_plan(program_only=True) or workload_hours_for_offering(offering) or from_plan()
    return from_plan() or workload_hours_for_offering(offering)


def program_for_offering(offering):
    """Açılışın ixtisası — qrupun valideyn bölməsi üzərindən (tapılmasa ``None``)."""
    from .models import Program

    group = offering.group if offering.group_id else None
    unit_id = getattr(group, "parent_id", None) if group is not None else None
    if unit_id is None:
        return None
    return Program.objects.filter(organization_id=offering.organization_id, specialty_unit_id=unit_id).first()


def curriculum_is_approved(*, organization, program) -> bool:
    """İxtisasın təsdiqlənmiş planı varmı (semestr açılışı qapısı ilə eyni qayda)."""
    if program is None:
        return False
    return Curriculum.objects.filter(organization=organization, program=program, status=PlanStatus.APPROVED).exists()


__all__ = [
    "HOUR_FIELDS",
    "curriculum_is_approved",
    "plan_hours_for_offering",
    "plan_hours_for_subject",
    "program_for_offering",
    "workload_hours_for_offering",
]
