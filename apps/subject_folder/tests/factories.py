"""Fənn qovluğu testləri üçün qurucular.

PG trigger-ləri (``registrar_guard_active_member``) açılış müəllimi və tələbə
qeydiyyatı üçün AKTİV üzvlük tələb edir — müəllim rolu ``grade.input`` daşıyır.
Sillabus birbaşa TƏSDİQLƏNMİŞ versiya kimi qurulur (iş axını testin mövzusu deyil).
"""

from __future__ import annotations

import itertools

from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit, Role
from apps.registrar.models import CourseOffering, Enrollment, Lesson, Subject
from apps.syllabus.models import Syllabus, SyllabusSection, SyllabusVersion
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType, RoleScopeType

User = get_user_model()
_SEQ = itertools.count(1)

WEEK_TITLES = ["Giriş və əsas anlayışlar", "Massivlər və siyahılar", "Rekursiya", "Sıralama alqoritmləri"]


def uniq(prefix: str) -> str:
    return f"{prefix}{next(_SEQ)}"


def activate_member(organization, user, role_name, *, permissions=(), level=50, scope_unit=None, scope_type=None):
    role, _ = Role.objects.get_or_create(
        organization=organization,
        name=role_name,
        defaults={
            "display_name": role_name.title(),
            "level": level,
            "permissions": list(permissions),
            "scope_type": scope_type or RoleScopeType.ORGANIZATION,
        },
    )
    Role.objects.filter(pk=role.pk).update(
        is_active=True, permissions=list(permissions), level=level, scope_type=scope_type or role.scope_type
    )
    membership, _ = Membership.objects.get_or_create(
        organization=organization, user=user, role=role, defaults={"is_active": True}
    )
    Membership.objects.filter(pk=membership.pk).update(is_active=True, scope_unit=scope_unit)
    return role


def make_user(prefix: str):
    name = uniq(prefix)
    return User.objects.create_user(name, f"{name}@sf.test", "pw", first_name=prefix.title(), last_name=name)


def make_org(slug: str | None = None):
    owner = make_user("owner")
    slug = slug or uniq("sforg")
    return Organization.objects.create(
        name=slug.upper(), slug=slug, org_type=OrganizationType.UNIVERSITY, owner=owner, status="active", is_active=True
    )


def make_teacher(organization, prefix="teacher"):
    user = make_user(prefix)
    activate_member(organization, user, "teacher", permissions=["grade.input"], level=60)
    return user


def make_student(organization, prefix="student"):
    user = make_user(prefix)
    activate_member(organization, user, "student", level=10)
    return user


def make_group(organization, name=None, parent=None):
    name = name or uniq("G")
    return OrgUnit.objects.create(
        organization=organization,
        name=name,
        slug=f"{organization.slug}-{name.lower()}",
        unit_type=OrgUnitType.GROUP,
        parent=parent,
    )


def make_period(organization, *, year="2026/2027", start="2026-09-01", end="2027-01-31", current=True):
    return AcademicPeriod.objects.create(
        organization=organization,
        name=uniq("Payız "),
        period_type=AcademicPeriodType.SEMESTER,
        academic_year=year,
        start_date=start,
        end_date=end,
        is_current=current,
    )


def make_subject(organization, code=None):
    code = code or uniq("SF")
    return Subject.objects.create(organization=organization, code=code, name=f"Fənn {code}")


def make_offering(organization, *, subject, period, instructor, group=None):
    return CourseOffering.objects.create(
        organization=organization,
        subject=subject,
        period=period,
        group=group or make_group(organization),
        instructor=instructor,
        lesson_hours=30,
    )


def enroll(offering, student, *, status="enrolled", source_group=None):
    return Enrollment.objects.create(
        organization=offering.organization,
        student=student,
        offering=offering,
        status=status,
        source_group=source_group,
    )


def add_lesson(offering, instructor, *, kind="seminar"):
    return Lesson.objects.create(
        organization=offering.organization,
        offering=offering,
        date=timezone.localdate(),
        kind=kind,
        instructor=instructor,
    )


def approve_syllabus(offering, author, *, option="2x5", week_titles=None, self_titles=None, status="approved"):
    """Açılış üçün sillabus dosyesi + (defolt) TƏSDİQLƏNMİŞ versiya; ``(syllabus, version)``."""
    organization = offering.organization
    syllabus, _ = Syllabus.objects.get_or_create(
        organization=organization,
        offering=offering,
        defaults={"subject": offering.subject, "period": offering.period, "author": author},
    )
    latest = syllabus.versions.order_by("-major").first()
    if latest is not None and latest.status == "approved" and status == "approved":
        SyllabusVersion.objects.filter(pk=latest.pk).update(status="archived")
    major = (latest.major + 1) if latest else 1
    now = timezone.now()
    version = SyllabusVersion.objects.create(
        organization=organization,
        syllabus=syllabus,
        major=major,
        status=status,
        locked_at=now if status == "approved" else None,
        approved_at=now if status == "approved" else None,
        approved_by=author if status == "approved" else None,
    )
    titles = WEEK_TITLES if week_titles is None else week_titles
    rows = [{"topic": title, "lecture": 2, "seminar": 0, "lab": 0, "outcome": "TN1"} for title in titles]
    count = {"1x10": 1, "2x5": 2, "10x1": 10}.get(option, 0)
    self_rows = [
        {"title": title} for title in (self_titles or [f"Sərbəst iş mövzusu {i}" for i in range(1, count + 1)])
    ]
    SyllabusSection.objects.create(organization=organization, version=version, section_id="week", data={"rows": rows})
    SyllabusSection.objects.create(
        organization=organization,
        version=version,
        section_id="self",
        data={"option": option, "topics": self_rows, "archived": []},
    )
    if status == "approved":
        syllabus.approved_version = version
    syllabus.current_version = version
    syllabus.save(update_fields=["approved_version", "current_version", "updated_at"])
    return syllabus, version


__all__ = [
    "WEEK_TITLES",
    "activate_member",
    "add_lesson",
    "approve_syllabus",
    "enroll",
    "make_group",
    "make_offering",
    "make_org",
    "make_period",
    "make_student",
    "make_subject",
    "make_teacher",
    "make_user",
    "uniq",
]
