"""Sillabus testləri üçün minimal fixture qurucuları.

``_activate_member`` ilə AKTİV üzvlük verilir — PG ``registrar_guard_active_member``
trigger-i ``CourseOffering``/``Enrollment`` üçün bunu tələb edir
(bax apps/registrar/tests/test_selfwork_archive.py).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit, Role
from apps.registrar.models import CourseOffering, Program, Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType, RoleScopeType

from ..constants import (
    LESSON_HOUR_KINDS,
    MIN_FILLED_WEEKS,
    WEEK_ROWS,
    SectionKey,
)

User = get_user_model()

#: Testlərdə istifadə olunan tədris planı saatları.
PLAN_HOURS = {"lecture": 30, "seminar": 16, "lab": 14}


def activate_member(organization, user, role_name, *, permissions=None, scope_unit=None, level=50, scope_type=None):
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


def make_academic_stack(organization, *, code: str = "SYL101"):
    """Kafedra + qrup + semestr + fənn + proqram + açılış."""
    chair = OrgUnit.objects.create(
        organization=organization,
        name=f"{code}-kafedra",
        slug=f"{organization.slug}-{code.lower()}-chair",
        unit_type=OrgUnitType.DEPARTMENT,
    )
    group = OrgUnit.objects.create(
        organization=organization,
        name=f"{code}-qrup",
        slug=f"{organization.slug}-{code.lower()}-group",
        unit_type=OrgUnitType.GROUP,
    )
    period = AcademicPeriod.objects.create(
        organization=organization,
        name=f"Payız {code}",
        period_type=AcademicPeriodType.SEMESTER,
        academic_year="2025/2026",
        start_date="2025-09-01",
        end_date="2026-01-31",
        is_current=True,
    )
    program = Program.objects.create(organization=organization, code=f"P-{code}", name="Proqram")
    subject = Subject.objects.create(organization=organization, code=code, name="Fənn")
    return {
        "chair": chair,
        "group": group,
        "period": period,
        "program": program,
        "subject": subject,
    }


def make_offering(organization, stack, instructor):
    return CourseOffering.objects.create(
        organization=organization,
        subject=stack["subject"],
        period=stack["period"],
        group=stack["group"],
        instructor=instructor,
        lesson_hours=sum(PLAN_HOURS.values()),
    )


def complete_section_data(plan_hours=None):
    """BÜTÜN biznes qaydalarını ödəyən bölmə məzmunu (100% tamamlanma)."""
    plan = dict(plan_hours or PLAN_HOURS)
    base = {kind: plan[kind] // MIN_FILLED_WEEKS for kind in LESSON_HOUR_KINDS}
    remainder = {kind: plan[kind] - base[kind] * MIN_FILLED_WEEKS for kind in LESSON_HOUR_KINDS}
    rows = []
    for index in range(WEEK_ROWS):
        if index >= MIN_FILLED_WEEKS:
            rows.append({"topic": "", **{kind: 0 for kind in LESSON_HOUR_KINDS}, "outcome": ""})
            continue
        row = {"topic": f"Mövzu {index + 1}", "outcome": f"TN{(index % 3) + 1}"}
        for kind in LESSON_HOUR_KINDS:
            row[kind] = base[kind] + (remainder[kind] if index == 0 else 0)
        rows.append(row)
    return {
        SectionKey.INFO.value: {
            "teacher": "b/m Nigar Həsənli",
            "office_hours": "Çərşənbə 14:00–16:00, otaq A-312",
            "prerequisites": "",
        },
        SectionKey.DESC.value: {"description": "T" * 130, "goal": "M" * 70},
        SectionKey.OUT.value: {"outcomes": ["Nəticə birinci mətn", "Nəticə ikinci mətn", "Nəticə üçüncü mətn"]},
        SectionKey.WEEK.value: {"rows": rows},
        SectionKey.METHOD.value: {"methods": ["Mühazirə", "Laboratoriya təcrübəsi"], "note": ""},
        SectionKey.ASSESS.value: {"midterm": 20, "project": 10, "note": ""},
        SectionKey.SELF.value: {
            "option": "2x5",
            "topics": [{"title": "Birinci sərbəst iş mövzusu"}, {"title": "İkinci sərbəst iş mövzusu"}],
            "archived": [],
        },
        SectionKey.LIT.value: {
            "primary": ["Cormen, Introduction to Algorithms, 2022", "Sedgewick, Algorithms, 2011"],
            "additional": ["Knuth, TAOCP, 1997"],
        },
        SectionKey.PREV.value: {},
        SectionKey.SEND.value: {},
    }
