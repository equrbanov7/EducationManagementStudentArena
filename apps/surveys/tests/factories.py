"""Sorğu testləri üçün kiçik «universitet» qurucusu.

Struktur: fakültə F → kafedra A, kafedra B; qrup G (A altında). İki açılış:
* ``off_math`` (müəllim A); dərsləri: biri ``instructor=None`` (→ A), biri C → {A, C};
* ``off_phys`` (müəllim B); dərsi YOXDUR → geri düşmə {B}.
PG trigger-ləri: tələbənin aktiv üzvlüyü, müəllimin `grade.input` icazəli üzvlüyü şərtdir.
"""

from __future__ import annotations

import datetime

from django.contrib.auth import get_user_model
from django.test import Client

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar.models import AssessmentScheme, CourseOffering, Enrollment, Lesson, Program, Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()
PW = "SurveyPass123!"


def member(org, username, role_name, *, unit=None):
    user = User.objects.create_user(username, f"{username}@qku.edu.az", PW)
    Membership.objects.create(
        user=user,
        organization=org,
        role=org.roles.get(name=role_name),
        scope_unit=unit,
        is_primary=True,
        is_active=True,
    )
    return user


def close_journal(org, offering):
    AssessmentScheme.objects.update_or_create(
        offering=offering, defaults={"organization": org, "is_published": True, "approval_status": "approved"}
    )


def build_world(slug: str, *, students: int = 4) -> dict:
    owner = User.objects.create_user(f"{slug}_owner", f"{slug}_owner@qku.edu.az", PW)
    with bypass_rls():
        org = Organization.objects.create(
            name=f"{slug} Univ",
            slug=slug,
            org_type=OrganizationType.UNIVERSITY,
            owner=owner,
            status="active",
            is_active=True,
        )
        faculty = OrgUnit.objects.create(
            organization=org, name="Fakültə F", slug=f"{slug}-f", unit_type=OrgUnitType.FACULTY
        )
        chair_a = OrgUnit.objects.create(
            organization=org, name="Kafedra A", slug=f"{slug}-ka", unit_type=OrgUnitType.CHAIR, parent=faculty
        )
        chair_b = OrgUnit.objects.create(
            organization=org, name="Kafedra B", slug=f"{slug}-kb", unit_type=OrgUnitType.CHAIR, parent=faculty
        )
        group = OrgUnit.objects.create(
            organization=org,
            name="G-101",
            slug=f"{slug}-g",
            unit_type=OrgUnitType.GROUP,
            parent=chair_a,
            settings={"course_year": 2},
        )
        period = AcademicPeriod.objects.create(
            organization=org,
            name=f"{slug} Payız",
            period_type=AcademicPeriodType.SEMESTER,
            academic_year="2026/2027",
            start_date=datetime.date(2026, 9, 1),
            end_date=datetime.date(2027, 1, 31),
            is_current=True,
        )
        Program.objects.create(organization=org, code=f"P-{slug}", name="Proqram")
        teacher_a = member(org, f"{slug}_ta", "teacher", unit=chair_a)
        teacher_b = member(org, f"{slug}_tb", "teacher", unit=chair_b)
        teacher_c = member(org, f"{slug}_tc", "teacher", unit=chair_a)
        math = Subject.objects.create(organization=org, code=f"{slug}-M", name="Riyaziyyat", chair_unit=chair_a)
        phys = Subject.objects.create(organization=org, code=f"{slug}-P", name="Fizika", chair_unit=chair_b)
        off_math = CourseOffering.objects.create(
            organization=org, subject=math, period=period, group=group, instructor=teacher_a
        )
        off_phys = CourseOffering.objects.create(
            organization=org, subject=phys, period=period, group=group, instructor=teacher_b
        )
        Lesson.objects.create(organization=org, offering=off_math, date=datetime.date(2026, 9, 10))
        Lesson.objects.create(
            organization=org, offering=off_math, date=datetime.date(2026, 9, 12), instructor=teacher_c
        )
        student_users = []
        for index in range(students):
            student = member(org, f"{slug}_s{index}", "student")
            for offering in (off_math, off_phys):
                Enrollment.objects.create(organization=org, student=student, offering=offering)
            student_users.append(student)
    return {
        "org": org,
        "owner": owner,
        "faculty": faculty,
        "chair_a": chair_a,
        "chair_b": chair_b,
        "group": group,
        "period": period,
        "teacher_a": teacher_a,
        "teacher_b": teacher_b,
        "teacher_c": teacher_c,
        "math": math,
        "phys": phys,
        "off_math": off_math,
        "off_phys": off_phys,
        "students": student_users,
    }


def close_all(world):
    with bypass_rls():
        close_journal(world["org"], world["off_math"])
        close_journal(world["org"], world["off_phys"])


def open_campaign(world, **fields):
    """Kampaniyanı birbaşa açır (siqnalsız) və istəyə görə sahələri dəyişir."""
    from apps.surveys.services.campaigns import ensure_campaign
    from apps.surveys.services.gate_snapshot import sync_gate_snapshot

    with bypass_rls():
        campaign, _created, _opened = ensure_campaign(world["org"], world["period"])
        if fields:
            for key, value in fields.items():
                setattr(campaign, key, value)
            campaign.save()
            sync_gate_snapshot(world["org"])
    return campaign


def client_for(org, user):
    client = Client()
    client.force_login(user)
    session = client.session
    session["active_organization"] = org.slug
    session.save()
    return client


def likert_payload(questions, *, score=4, overall=8, text=""):
    data = {}
    for question in questions:
        name = f"q_{question.code}"
        if question.kind == "likert5":
            data[name] = str(score)
        elif question.kind == "scale10":
            data[name] = str(overall)
        elif text:
            data[name] = text
    return data
