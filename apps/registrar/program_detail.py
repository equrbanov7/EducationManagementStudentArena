"""İxtisasın «Ətraflı» görünüşü — qruplar, tələbələr, plan və semestr açılışları.

Sahib (2026-09-09): «ixtisasın üzərinə vuranda ətraflı nə isə açıla bilər;
açılan yerdə o ixtisasda aktiv oxuyan qrupları, qruplardan həmin ixtisasdakı
tələbələri və s. görmək olsun».

Sorğu profili (sətir sayından ASILI DEYİL — hamısı toplu/aqreqat):
  1) proqramın özü,               2) qrup adları (bir `in` sorğusu),
  3) qrup üzrə tələbə sayları (GROUP BY),  4) status paylanması (GROUP BY),
  5) tədris planı sətir sayı,     6) cari semestr açılışları (GROUP BY),
  7) tələbə önizləməsi (LIMIT).
Yəni ~7 sorğu — qrup və ya tələbə sayı artdıqca dəyişmir (N+1 yoxdur).

Əhatə: çağıran qat (`accounts.views.programs`) aktoru onsuz da `catalog.view`
ilə qapılayır; burada YALNIZ tenant süzgəci var (`organization=`).
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.db.models import Count

from .models import CourseOffering, CurriculumSubject, Program, StudentAcademicRecord

#: Çekmecədə göstərilən tələbə önizləməsinin həddi — tam siyahı «Tələbə
#: reyestri»ndədir, burada məqsəd «kimlərdir» sualına cavabdır.
STUDENT_PREVIEW = 12


def _org_unit_model():
    return django_apps.get_model("organizations", "OrgUnit")


def _person(user) -> str:
    if user is None:
        return ""
    return user.get_full_name() or user.username


def _current_period(organization):
    AcademicPeriod = django_apps.get_model("organizations", "AcademicPeriod")
    return AcademicPeriod.objects.filter(organization=organization, is_current=True).first()


def build_program_detail(organization, program_id: str) -> dict | None:
    """İxtisasın çekmecə məlumatı; tapılmasa ``None``."""
    program = Program.objects.filter(organization=organization, pk=program_id).select_related("specialty_unit").first()
    if program is None:
        return None

    records = StudentAcademicRecord.objects.filter(organization=organization, program=program)

    # ── Qruplar: AKTİV tələbə qeydi olanlar (ixtisasın «canlı» qrupları) ──────
    group_rows = (
        records.filter(group__isnull=False).order_by().values("group_id").annotate(total=Count("id")).order_by("-total")
    )
    group_counts = {row["group_id"]: row["total"] for row in group_rows}
    names = {}
    if group_counts:
        OrgUnit = _org_unit_model()
        names = {
            unit.id: unit.name
            for unit in OrgUnit.objects.filter(organization=organization, pk__in=list(group_counts)).only("id", "name")
        }
    groups = [
        {"id": str(gid), "name": names.get(gid, "—"), "students": total}
        for gid, total in sorted(group_counts.items(), key=lambda item: -item[1])
    ]

    # ── Status paylanması (qeydiyyatlı / akademik məzuniyyət / xaric …) ───────
    status_rows = records.order_by().values("status").annotate(total=Count("id"))
    status_display = dict(StudentAcademicRecord._meta.get_field("status").choices)
    statuses = sorted(
        (
            {
                "key": row["status"],
                "label": str(status_display.get(row["status"], row["status"])),
                "total": row["total"],
            }
            for row in status_rows
        ),
        key=lambda item: -item["total"],
    )

    # ── Tədris planı + cari semestr açılışları ───────────────────────────────
    plan_rows = CurriculumSubject.objects.filter(
        curriculum__organization=organization, curriculum__program=program
    ).count()
    period = _current_period(organization)
    offerings = 0
    if period is not None:
        offerings = CourseOffering.objects.filter(
            organization=organization, period=period, group_id__in=list(group_counts) or [None]
        ).count()

    preview = [
        {
            "id": str(record.id),
            "name": _person(record.student),
            "username": record.student.username,
            "group": names.get(record.group_id, ""),
            "year": record.admission_year,
            "status": record.status,
            "status_label": str(status_display.get(record.status, record.status)),
        }
        for record in records.select_related("student").order_by("student__first_name", "student__last_name")[
            :STUDENT_PREVIEW
        ]
    ]

    chair = program.specialty_unit.name if program.specialty_unit_id else ""
    return {
        "id": str(program.id),
        "name": program.name,
        "official_code": program.official_code or "",
        "legacy_official_code": program.legacy_official_code or "",
        "degree_label": program.get_degree_level_display(),
        "form_label": program.get_education_form_display(),
        "ects_total": program.ects_total,
        "absence_limit_percent": program.absence_limit_percent,
        "is_archived": program.is_archived,
        "unit": chair,
        "students_total": sum(group_counts.values()) + records.filter(group__isnull=True).count(),
        "students_grouped": sum(group_counts.values()),
        "students_ungrouped": records.filter(group__isnull=True).count(),
        "groups": groups,
        "statuses": statuses,
        "plan_rows": plan_rows,
        "offerings": offerings,
        "period": period.name if period is not None else "",
        "students": preview,
        "students_more": max(0, sum(group_counts.values()) - len(preview)),
    }


__all__ = ["build_program_detail", "STUDENT_PREVIEW"]
