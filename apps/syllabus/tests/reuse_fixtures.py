"""Təkrar istifadə testlərinin ortaq «dünyası» (2026-10-08).

Struktur::

    kafedra (DEPARTMENT)            başqa kafedra (CHAIR)
       │  (müəllimin üzvlüyü)          └── ixtisas C ── g4
    ixtisas A ── g1, g2, g5         ixtisas B ── g3

* A və C planı: 30/16/14 (``PLAN_HOURS``); B planı: 30/30/0 → g3-ün saatı FƏRQLİDİR;
* g1/g2/g3 qrupunun ağacında kafedra YOXDUR → sillabusun kafedrası müəllimin
  kafedra üzvlüyündən gəlir; g4-ün ağacında BAŞQA kafedra var → kafedra fərqlidir;
* müəllim: o1 (g1), o2 (g2), o3 (g3), o4 (g4); ikinci müəllim: o5 (g5);
* kafedra müdiri — kafedra səviyyəli təsdiq əhatəsi.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model

from apps.organizations.models import AcademicPeriod, OrgUnit
from apps.registrar.models import CourseOffering, Curriculum, CurriculumSubject, PlanStatus, Program, Subject
from apps.syllabus import services
from apps.syllabus.constants import SectionKey
from apps.syllabus.tests.factories import PLAN_HOURS, activate_member, complete_section_data, make_org
from core.constants import AcademicPeriodType, OrgUnitType, RoleScopeType

User = get_user_model()

TEACHER_PERMS = ["syllabus.view", "syllabus.edit", "syllabus.submit", "grade.input"]
CHAIR_PERMS = ["syllabus.view", "syllabus.review", "syllabus.approve", "syllabus.revise", "syllabus.reject"]
OTHER_HOURS = {"lecture": 30, "seminar": 30}


def _unit(org, name, unit_type, parent=None):
    return OrgUnit.objects.create(
        organization=org, name=name, slug=f"{org.slug}-{name.lower()}", unit_type=unit_type, parent=parent
    )


def _plan(org, program, subject, hours):
    curriculum = Curriculum.objects.create(
        organization=org, program=program, admission_year=2024, name=f"{program.code} plan", status=PlanStatus.APPROVED
    )
    CurriculumSubject.objects.create(
        organization=org,
        curriculum=curriculum,
        subject=subject,
        semester_number=1,
        lecture_hours=hours.get("lecture", 0),
        seminar_hours=hours.get("seminar", 0),
        lab_hours=hours.get("lab", 0),
    )
    return curriculum


def build_world(slug: str = "syl-reuse") -> dict:
    org = make_org(slug)
    chair = _unit(org, "Kafedra", OrgUnitType.DEPARTMENT)
    other_chair = _unit(org, "BaskaKafedra", OrgUnitType.CHAIR)
    spec_a = _unit(org, "IxtisasA", OrgUnitType.SPECIALTY)
    spec_b = _unit(org, "IxtisasB", OrgUnitType.SPECIALTY)
    spec_c = _unit(org, "IxtisasC", OrgUnitType.SPECIALTY, parent=other_chair)
    groups = {
        "g1": _unit(org, "101A", OrgUnitType.GROUP, parent=spec_a),
        "g2": _unit(org, "102A", OrgUnitType.GROUP, parent=spec_a),
        "g3": _unit(org, "103B", OrgUnitType.GROUP, parent=spec_b),
        "g4": _unit(org, "104C", OrgUnitType.GROUP, parent=spec_c),
        "g5": _unit(org, "105A", OrgUnitType.GROUP, parent=spec_a),
    }
    period = AcademicPeriod.objects.create(
        organization=org,
        name="Payız",
        period_type=AcademicPeriodType.SEMESTER,
        academic_year="2025/2026",
        start_date="2025-09-01",
        end_date="2026-01-31",
        is_current=True,
    )
    subject = Subject.objects.create(organization=org, code="RSE101", name="Alqoritmlər")
    programs = {
        "a": Program.objects.create(organization=org, code="PA", name="Proqram A", specialty_unit=spec_a),
        "b": Program.objects.create(organization=org, code="PB", name="Proqram B", specialty_unit=spec_b),
        "c": Program.objects.create(organization=org, code="PC", name="Proqram C", specialty_unit=spec_c),
    }
    curricula = {
        "a": _plan(org, programs["a"], subject, PLAN_HOURS),
        "b": _plan(org, programs["b"], subject, OTHER_HOURS),
        "c": _plan(org, programs["c"], subject, PLAN_HOURS),
    }

    teacher = User.objects.create_user(f"{slug}_t", f"{slug}_t@x.test", "pw", first_name="Nigar", last_name="Həsənli")
    teacher2 = User.objects.create_user(
        f"{slug}_t2", f"{slug}_t2@x.test", "pw", first_name="Elçin", last_name="Quliyev"
    )
    head = User.objects.create_user(f"{slug}_h", f"{slug}_h@x.test", "pw")
    for user, name in ((teacher, "teacher"), (teacher2, "teacher")):
        activate_member(org, user, name, permissions=TEACHER_PERMS, scope_unit=chair, scope_type=RoleScopeType.COURSE)
    activate_member(
        org, head, "chair_head", permissions=CHAIR_PERMS, scope_unit=chair, level=70, scope_type=RoleScopeType.UNIT
    )

    def offering(group, instructor):
        return CourseOffering.objects.create(
            organization=org, subject=subject, period=period, group=group, instructor=instructor, lesson_hours=60
        )

    offerings = {
        "o1": offering(groups["g1"], teacher),
        "o2": offering(groups["g2"], teacher),
        "o3": offering(groups["g3"], teacher),
        "o4": offering(groups["g4"], teacher),
        "o5": offering(groups["g5"], teacher2),
    }
    return {
        "org": org,
        "chair": chair,
        "other_chair": other_chair,
        "groups": groups,
        "period": period,
        "subject": subject,
        "programs": programs,
        "curricula": curricula,
        "teacher": teacher,
        "teacher2": teacher2,
        "head": head,
        "offerings": offerings,
    }


def actor(world, key="teacher"):
    return services.resolve_actor(world[key], world["org"])


def draft_for(world, key: str, *, user_key="teacher", hours=None):
    """``key`` açılışı üçün boş qaralama (``_create_draft`` glue-su ilə eyni çağırış)."""
    offering = world["offerings"][key]
    return services.create_draft(
        organization=world["org"],
        subject=world["subject"],
        period=world["period"],
        actor=actor(world, user_key),
        offering=offering,
        chair_unit=offering.group.parent,
        author=world[user_key],
        plan_hours=dict(hours or PLAN_HOURS),
    )


def fill(version, act, hours=None):
    for section_id, data in complete_section_data(hours or PLAN_HOURS).items():
        if section_id in {SectionKey.PREV.value, SectionKey.SEND.value}:
            continue
        services.save_section(version=version, section_id=section_id, data=data, actor=act)
    version.refresh_from_db()
    return version


def approve_version(world, version, act):
    version = services.submit(version=version, actor=act)
    head = actor(world, "head")
    version = services.start_review(version=version, actor=head)
    return services.approve(version=version, actor=head, comment="Uyğundur")


def approved_syllabus(world, key: str = "o1", *, user_key="teacher", hours=None):
    """Uçdan-uca (insan) təsdiqlənmiş sillabus."""
    syllabus, version = draft_for(world, key, user_key=user_key, hours=hours)
    act = actor(world, user_key)
    version = fill(version, act, hours)
    version = approve_version(world, version, act)
    syllabus.refresh_from_db()
    return syllabus, version


def target(world, key: str, *, syllabus=None, hours=None):
    """Hədəf açılış — saat rəsmi plandan (glue ilə eyni)."""
    from apps.registrar.public import plan_hours_for_offering

    offering = world["offerings"][key]
    return services.ReuseTarget(
        offering=offering,
        syllabus=syllabus,
        plan_hours=plan_hours_for_offering(offering) if hours is None else hours,
        unit_hint=offering.group.parent,
    )
