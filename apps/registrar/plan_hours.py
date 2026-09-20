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


def plan_hours_for_subject(*, organization, subject, program=None):
    """Fənn üçün təsdiqlənmiş plan sətrinin saat bölgüsü (``{}`` — tapılmadı).

    ``program`` verilibsə həmin ixtisasın planına üstünlük verilir; verilməsə (və
    ya tapılmasa) təşkilatın ən yeni qəbul ilinə aid təsdiqlənmiş planı
    götürülür.  Kredit/saat İXTİSASA görə dəyişdiyi üçün (layihə yaddaşı) proqram
    uyğunluğu ƏHƏMİYYƏTLİDİR — geri çəkilmə yalnız heç nə tapılmayanda işə düşür.
    """
    if subject is None:
        return {}
    base = CurriculumSubject.objects.filter(
        organization=organization,
        subject=subject,
        curriculum__status=PlanStatus.APPROVED,
    ).select_related("curriculum")
    ordered = base.order_by("-curriculum__admission_year", "-curriculum__version")
    if program is not None:
        row = ordered.filter(curriculum__program=program).first()
        if row is not None:
            return _row_hours(row)
    row = ordered.first()
    return _row_hours(row) if row is not None else {}


def plan_hours_for_offering(offering):
    """Açılışdan (``CourseOffering``) saat bölgüsü — ixtisas qrupdan çıxarılır.

    Qrup ``OrgUnit``-dir və onun valideyni adətən İXTİSAS bölməsidir; ixtisas
    bölməsi ilə ``registrar.Program.specialty_unit`` arasındakı bağ proqramı
    verir.  Bağ tapılmasa proqramsız (ən yeni plan) yola davam edilir.
    """
    if offering is None:
        return {}
    hours = plan_hours_for_subject(
        organization=offering.organization,
        subject=offering.subject,
        program=program_for_offering(offering),
    )
    return hours or workload_hours_for_offering(offering)


def workload_hours_for_offering(offering) -> dict:
    """Təsdiqlənmiş plan sətri YOXDURSA — dərs yükü (TAPŞIRIQ) sətrindən bölgü.

    Sahib 2026-09-20: «tədrisdən gələn yük saatı sillabuslarda görünmür».
    Kafedra tapşırığının sətri (eyni fənn + dövr + qrup) mühazirə/seminar/lab
    saatını daşıyır — ``*_plan`` (plan saatı), yoxdursa ``*_total``.  Model
    ``get_model`` ilə həll olunur: registrar → workload Python import kənarı
    yaranmır (modul-sərhəd qapısı; workload onsuz da registrar.public-i oxuyur).
    """
    from django.apps import apps as django_apps

    if offering is None or not (offering.subject_id and offering.period_id):
        return {}
    try:
        TaskRow = django_apps.get_model("workload", "TeachingTaskRow")
    except LookupError:
        return {}
    rows = TaskRow.objects.filter(
        organization_id=offering.organization_id, subject_id=offering.subject_id, period_id=offering.period_id
    )
    if offering.group_id:
        rows = rows.filter(groups=offering.group_id)
    row = (
        rows.order_by("-updated_at")
        .values("lecture_plan", "lecture_total", "seminar_plan", "seminar_total", "lab_plan", "lab_total")
        .first()
    )
    if not row:
        return {}
    hours = {}
    for kind in ("lecture", "seminar", "lab"):
        value = int(row[f"{kind}_plan"] or 0) or int(row[f"{kind}_total"] or 0)
        if value > 0:
            hours[kind] = value
    return hours


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
