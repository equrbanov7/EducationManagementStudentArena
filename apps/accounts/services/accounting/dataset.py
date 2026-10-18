"""«Mühasibatlıq» — müəllim başına aylıq FAKT (keçirilmiş saat) və PLAN, SQL aqreqatları ilə.

FAKT — keçirilmiş dərs saatı (jurnal)
-------------------------------------
Mənbə: elektron jurnalın ``registrar.Lesson`` sətirləri. Jurnalda dərs sətri YALNIZ keçirilmiş dərs üçün
yaranır («One held session (dərs) on a date»); ləğv olunan dərs sətri silinir. Sayılan dərs:

* açılışı AKTİVDİR (``CourseOffering.is_active``) və seçilmiş semestrin dövrlərindəndir;
* açılışda ən azı bir CANLI qeydiyyat var. Qeydiyyat yalnız «Jurnal təmizliyi»nin geri qaytarılmamış
  «keçirilməyən fənn» / «boş fənn» / «fəndən azad» qərarı ilə ``dropped`` olubsa canlı SAYILMIR
  (``NOT_HELD_CATEGORIES``). Başqa səbəbli ``dropped`` — qrup köçürməsi / birləşmə (``superseded_by``,
  ``transfer.py``, ``guest_merge.py``), tələbənin ayrılması — dərsin keçirildiyini dəyişmir: köçürmədən
  ƏVVƏLKİ ayların saatları itmir. Beləliklə yalnız bütün tələbələri «keçirilməyib» qərarı ilə çıxarılmış
  açılışın dərsləri saya düşmür;
* saat = dərsin öz ``Lesson.hours`` dəyəri (jurnal defolt 2 akademik saat yazır — sillabus qaydası
  «1 dərs = 2 saat»; müəllim/cədvəl başqa saat yazıbsa O sayılır);
* müəllim = dərsin öz müəllimi (``Lesson.instructor`` — fənn iki müəllim arasında bölünəndə, məs. mühazirə
  bir, seminar başqa), boşdursa açılışın müəllimi (``CourseOffering.instructor``) — «Keçilmiş dərslər» və
  «Kadr analitikası» ilə EYNİ atribusiya;
* növ = ``Lesson.kind`` (mühazirə / seminar / laboratoriya), ay = dərsin tarixi.

PLAN — paylanmış dərs yükü
--------------------------
Mənbə: ``workload.TeacherAssignment`` (müəllimə bölünmüş saat), tapşırığın tədris ili = semestrin ili,
sətrin fəsli = semestrin fəsli, tapşırıq statusu «bölüşdürülüb / düzəliş» (``PLANNED_TASK_STATUSES`` —
«Dərs yüküm» ilə eyni), fəaliyyət yalnız auditoriya növləri (mühazirə / seminar / laboratoriya; məsləhət,
imtahan, təcrübə, buraxılış işi jurnalda dərs kimi yazılmadığı üçün tutuşdurmaya daxil DEYİL). Semestr planı
aylara ``periods.apportion`` qaydası ilə bölünür.

Sorğu büdcəsi SABİTDİR (müəllim sayından asılı deyil): fakt 1 (aralıq rejimində +1), plan 1, istifadəçilər 1,
üzvlüklər 1, struktur 1, yük profilləri 1. Filtr / sıralama / səhifələmə bundan sonra yaddaşda gedir (heyət ~10³).
"""

from __future__ import annotations

from collections import defaultdict

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.db.models import Count, Exists, OuterRef, Sum
from django.db.models.functions import Coalesce, TruncMonth

from core.person_names import clean_name_part

from ..hr_analytics.dataset import _pick_membership, _placement, _structure, staff_type
from . import constants as C
from .periods import Semester, month_key

User = get_user_model()

#: «Jurnal təmizliyi» kateqoriyaları (``registrar.models.journal_hygiene.HygieneCategory`` dəyərləri) — qeydiyyatı
#: bu qərarla çıxarılan tələbə üçün fənn KEÇİRİLMƏYİB sayılır. ``left_student`` (tələbə ayrılıb) burada YOXDUR.
NOT_HELD_CATEGORIES = ("not_held", "empty_subject", "subject_exempt")


def _model(app_label: str, name: str):
    return django_apps.get_model(app_label, name)


def period_catalog(organization) -> list:
    """Təşkilatın akademik dövrləri (1 sorğu)."""
    return list(
        _model("organizations", "AcademicPeriod")
        .objects.filter(organization=organization)
        .only("id", "academic_year", "start_date", "end_date", "exam_session_start", "is_current")
        .order_by("-start_date")
    )


def held_lessons(organization, semester: Semester):
    """Semestrin SAYILAN dərsləri (modul sənədindəki qayda) + ``teacher`` annotasiyası — queryset."""
    lesson_model = _model("registrar", "Lesson")
    enrollment_model = _model("registrar", "Enrollment")
    not_held_decision = _model("registrar", "JournalHygieneDecision").objects.filter(
        enrollment_id=OuterRef("pk"), category__in=NOT_HELD_CATEGORIES, reverted_at__isnull=True
    )
    live_enrollment = (
        enrollment_model.objects.filter(offering_id=OuterRef("offering_id"))
        .annotate(not_held=Exists(not_held_decision))
        .exclude(status=enrollment_model.Status.DROPPED, not_held=True)
    )
    return (
        lesson_model.objects.filter(
            organization=organization,
            offering__is_active=True,
            offering__period_id__in=list(semester.period_ids),
        )
        .filter(Exists(live_enrollment))
        .annotate(teacher=Coalesce("instructor_id", "offering__instructor_id"))
        .filter(teacher__isnull=False)
    )


def held_matrix(organization, semester: Semester, *, start=None, end=None, teacher=None) -> dict:
    """{müəllim: {ay: {növ: [saat, dərs]}}} — BİR GROUP BY sorğusu.

    ``start`` / ``end`` verilsə yalnız həmin tarix aralığının dərsləri (sərbəst aralıq rejimi, ``ranges.py``);
    ``teacher`` verilsə yalnız həmin müəllimin dərsləri (müəllim pəncərəsi — bütün təşkilat yığılmır).
    """
    queryset = held_lessons(organization, semester)
    if teacher is not None:
        queryset = queryset.filter(teacher=teacher)
    if start and end:
        queryset = queryset.filter(date__range=(start, end))
    rows = (
        queryset.annotate(month=TruncMonth("date"))
        .values("teacher", "month", "kind")
        .annotate(hours=Sum("hours"), lessons=Count("id"))
        .order_by()
    )
    out: dict = defaultdict(lambda: defaultdict(dict))
    for row in rows:
        month = row["month"]
        key = month_key(month.year, month.month)
        out[row["teacher"]][key][row["kind"]] = [int(row["hours"] or 0), int(row["lessons"] or 0)]
    return out


def planned_matrix(organization, semester: Semester, *, teacher=None) -> dict:
    """{müəllim: {növ: semestr saatı}} — BİR GROUP BY sorğusu (``teacher`` — yalnız bir müəllim)."""
    queryset = _model("workload", "TeacherAssignment").objects.all()
    if teacher is not None:
        queryset = queryset.filter(teacher_id=teacher)
    rows = (
        queryset.filter(
            organization=organization,
            teacher__isnull=False,
            activity__in=C.KIND_KEYS,
            row__task__status__in=C.PLANNED_TASK_STATUSES,
            row__task__academic_year=semester.year,
            row__season=semester.season,
        )
        .values("teacher_id", "activity")
        .annotate(hours=Sum("hours"))
        .order_by()
    )
    out: dict = defaultdict(dict)
    for row in rows:
        out[row["teacher_id"]][row["activity"]] = int(row["hours"] or 0)
    return out


def _memberships(organization, user_ids) -> dict:
    rows = (
        _model("organizations", "Membership")
        .objects.filter(organization=organization, is_active=True, user_id__in=user_ids, role__is_active=True)
        .exclude(role__name__in=("student", "lead_student", "alumni"))
        .values(
            "user_id",
            "role__name",
            "role__level",
            "is_primary",
            "created_at",
            "scope_unit_id",
            "scope_unit__path",
            "scope_unit__unit_type",
        )
        .order_by()
    )
    grouped: dict = defaultdict(list)
    for row in rows:
        grouped[row["user_id"]].append(row)
    return grouped


def _profiles(organization, user_ids, academic_year: str) -> dict:
    return {
        row["teacher_id"]: row
        for row in _model("workload", "TeacherWorkloadProfile")
        .objects.filter(organization=organization, teacher_id__in=user_ids, academic_year=academic_year)
        .values("teacher_id", "staff_fraction", "is_external", "position")
    }


def _position_labels() -> dict:
    """Yük profilinin vəzifə açarı → etiket (``TeacherPosition``; statik import yoxdur — modul sərhədi)."""
    field = _model("workload", "TeacherWorkloadProfile")._meta.get_field("position")
    return {key: str(label) for key, label in field.flatchoices}


def _display_name(values) -> str:
    parts = (values["last_name"], values["first_name"], clean_name_part(values["profile__patronymic"]))
    return " ".join(part for part in parts if part).strip() or values["username"]


def people(actor, teacher_ids, academic_year: str, *, units: dict | None = None) -> dict:
    """{müəllim id: {ad, fakültə, kafedra, ştat}} — əhatədən kənar müəllim QAYTARILMIR (3–4 sorğu).

    ``units`` — çağıranın artıq oxuduğu struktur xəritəsi (``hr_analytics.dataset._structure``); verilməsə oxunur.
    """
    organization = actor.organization
    ids = [pk for pk in teacher_ids if pk]
    if not ids:
        return {}
    users = User.objects.filter(pk__in=ids, is_superuser=False).values(
        "pk", "username", "first_name", "last_name", "profile__patronymic"
    )
    memberships = _memberships(organization, ids)
    profiles = _profiles(organization, ids, academic_year)
    units = units if units is not None else _structure(organization)
    positions = _position_labels()
    out = {}
    for values in users:
        picked = _pick_membership(memberships.get(values["pk"], []))
        unit_id = (picked or {}).get("scope_unit_id")
        unit_path = (picked or {}).get("scope_unit__path") or ""
        if not actor.unit_visible(unit_id, unit_path):
            continue
        faculty_id, faculty, chair_id, chair = _placement(
            unit_id, unit_path, (picked or {}).get("scope_unit__unit_type") or "", units
        )
        profile = profiles.get(values["pk"])
        out[values["pk"]] = {
            "id": values["pk"],
            "username": values["username"],
            "name": _display_name(values),
            "faculty_id": faculty_id,
            "faculty": faculty,
            "chair_id": chair_id,
            "chair": chair,
            "staff_type": staff_type(profile),
            "staff_fraction": float(profile["staff_fraction"] or 0) if profile else None,
            "position": positions.get((profile or {}).get("position") or "", ""),
        }
    return out


def lesson_rows(organization, semester: Semester, teacher_id, *, start=None, end=None):
    """Bir müəllimin sayılan dərsləri (tarix, qrup, fənn, növ, saat) — queryset (səhifələnir)."""
    queryset = held_lessons(organization, semester).filter(teacher=teacher_id)
    if start and end:
        queryset = queryset.filter(date__range=(start, end))
    return queryset.values(
        "id", "date", "start_time", "kind", "hours", "topic", "offering__subject__name", "offering__group__name"
    ).order_by("date", "start_time", "id")


def subject_breakdown(organization, semester: Semester, teacher_ids, *, start=None, end=None) -> list[dict]:
    """Müəllim × fənn × qrup × növ üzrə keçirilmiş saat — BİR GROUP BY (drill-down və ixrac üçün)."""
    queryset = held_lessons(organization, semester).filter(teacher__in=list(teacher_ids))
    if start and end:
        queryset = queryset.filter(date__range=(start, end))
    return list(
        queryset.values("teacher", "offering__subject__name", "offering__group__name", "kind")
        .annotate(hours=Sum("hours"), lessons=Count("id"))
        .order_by("offering__subject__name", "offering__group__name")
    )


__all__ = [
    "held_lessons",
    "held_matrix",
    "lesson_rows",
    "people",
    "period_catalog",
    "planned_matrix",
    "subject_breakdown",
]
