"""Dərs yükü testləri üçün minimal fixture qurucuları (sillabus naxışı)."""

from __future__ import annotations

from django.contrib.auth import get_user_model

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit, Role
from apps.registrar.models import Program, Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType, RoleScopeType

from ..constants import Season, TaskStatus
from ..models import TeachingTask, TeachingTaskRow

User = get_user_model()

YEAR = "2026/2027"

#: Real `teacher` rolunun dəsti (default_roles_university.py).
#:
#: ⚠️ `grade.input` MƏCBURİDİR: `registrar_guard_active_member` trigger-i
#: (`registrar/0041`) `CourseOffering.instructor` üçün məhz bu açarı tələb edir.
#: Onsuz offering sinxronu müəllimi yazmır (bax `distribution._write_offering`).
TEACHER_PERMS = ["workload.view", "grade.view", "grade.input", "course.view"]


def activate_member(
    organization,
    user,
    role_name,
    *,
    permissions=None,
    scope_unit=None,
    level=50,
    scope_type=None,
):
    """Aktiv rol + aktiv üzvlük yaradır və rolu qaytarır."""
    role, _created = Role.objects.get_or_create(
        organization=organization,
        name=role_name,
        defaults={
            "display_name": role_name.title(),
            "level": level,
            "permissions": list(permissions or []),
            "scope_type": scope_type or RoleScopeType.ORGANIZATION,
        },
    )
    Role.objects.filter(pk=role.pk).update(
        is_active=True,
        permissions=list(permissions or []),
        level=level,
        scope_type=scope_type or role.scope_type,
    )
    role.refresh_from_db()
    membership, _ = Membership.objects.get_or_create(
        organization=organization, user=user, role=role, defaults={"is_active": True}
    )
    Membership.objects.filter(pk=membership.pk).update(is_active=True, scope_unit=scope_unit)
    return role


def make_org(slug: str, *, owner=None):
    owner = owner or User.objects.create_user(f"{slug}_owner", f"{slug}_owner@x.test", "pw")
    return Organization.objects.create(
        name=slug.upper(),
        slug=slug,
        org_type=OrganizationType.UNIVERSITY,
        owner=owner,
        status="active",
        is_active=True,
    )


def make_structure(organization, *, code: str = "WL"):
    """Fakültə → kafedra → ixtisas → qrup + semestr + fənn + proqram."""
    faculty = OrgUnit.objects.create(
        organization=organization,
        name=f"{code}-fakultə",
        slug=f"{organization.slug}-{code.lower()}-faculty",
        unit_type=OrgUnitType.FACULTY,
    )
    chair = OrgUnit.objects.create(
        organization=organization,
        name=f"{code}-kafedra",
        slug=f"{organization.slug}-{code.lower()}-chair",
        unit_type=OrgUnitType.CHAIR,
        parent=faculty,
    )
    specialty = OrgUnit.objects.create(
        organization=organization,
        name=f"{code}-ixtisas",
        slug=f"{organization.slug}-{code.lower()}-specialty",
        unit_type=OrgUnitType.SPECIALTY,
        parent=chair,
    )
    group = OrgUnit.objects.create(
        organization=organization,
        name=f"{code}-236",
        slug=f"{organization.slug}-{code.lower()}-group",
        unit_type=OrgUnitType.GROUP,
        parent=specialty,
    )
    period = AcademicPeriod.objects.create(
        organization=organization,
        name=f"Payız {code}",
        period_type=AcademicPeriodType.SEMESTER,
        academic_year=YEAR,
        start_date="2026-09-01",
        end_date="2027-01-31",
        is_current=True,
    )
    program = Program.objects.create(
        organization=organization,
        code=f"P-{code}",
        name=f"{code} proqramı",
        specialty_unit=specialty,
    )
    subject = Subject.objects.create(organization=organization, code=f"{code}101", name="Alqoritmlər", ects=6)
    return {
        "faculty": faculty,
        "chair": chair,
        "specialty": specialty,
        "group": group,
        "period": period,
        "program": program,
        "subject": subject,
    }


def make_task(organization, chair, *, status=TaskStatus.DRAFT, created_by=None):
    return TeachingTask.objects.create(
        organization=organization,
        chair=chair,
        academic_year=YEAR,
        status=status,
        created_by=created_by,
    )


def make_row(
    task,
    stack,
    *,
    lecture_total: int = 30,
    seminar_total: int = 30,
    lab_total: int = 0,
    with_group: bool = True,
    with_period: bool = True,
    with_subject: bool = True,
):
    row = TeachingTaskRow.objects.create(
        organization=task.organization,
        task=task,
        season=Season.FALL,
        period=stack["period"] if with_period else None,
        subject=stack["subject"] if with_subject else None,
        subject_text="" if with_subject else "Təcrübə",
        specialty=stack["specialty"],
        faculty=stack["faculty"],
        student_count=25,
        union_count=1,
        subgroup_count=1,
        lecture_plan=lecture_total,
        lecture_total=lecture_total,
        seminar_plan=seminar_total,
        seminar_total=seminar_total,
        lab_total=lab_total,
        total_hours=lecture_total + seminar_total + lab_total,
        credits_value=6,
    )
    if with_group:
        row.groups.set([stack["group"]])
    return row
