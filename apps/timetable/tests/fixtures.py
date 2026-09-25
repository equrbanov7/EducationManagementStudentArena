"""Avtomatik cədvəl testləri üçün kiçik, amma real struktur (Django bazası ilə).

Fakültə A → ixtisas A → qruplar «A-101», «A-102» (bakalavr), «M-601» (magistr),
«Q-701» (qiyabi); fakültə B → «B-101» (koordinatorun əhatəsindən KƏNAR).
Saatlar tələbələrin kurikulumundan gəlir; «Alqoritmlər» mühazirəsi tapşırıq
sətrində A-101 + A-102 birləşməsidir (axın).
"""

from __future__ import annotations

import datetime

from django.contrib.auth import get_user_model

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar.models import (
    CourseOffering,
    Curriculum,
    CurriculumSubject,
    Program,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


def _unit(org, name, unit_type, parent=None, **settings):
    return OrgUnit.objects.create(
        organization=org,
        name=name,
        slug=f"{org.slug}-{name}".lower().replace(" ", "-"),
        unit_type=unit_type,
        parent=parent,
        settings=settings,
    )


def _member(org, user, role_name, scope_unit=None):
    return Membership.objects.create(
        user=user,
        organization=org,
        role=org.roles.get(name=role_name),
        scope_unit=scope_unit,
        is_primary=True,
        is_active=True,
    )


def build_world(prefix="tt"):
    """Bütün obyektləri yaradır və sözlük qaytarır (``bypass_rls`` daxilində)."""
    with bypass_rls():
        owner = User.objects.create_user(f"{prefix}_owner", f"{prefix}_owner@x.test", "pw")
        org = Organization.objects.create(
            name=f"{prefix.upper()} Univ",
            slug=f"{prefix}-univ",
            org_type=OrganizationType.UNIVERSITY,
            owner=owner,
            status="active",
            is_active=True,
        )
        fac_a = _unit(org, f"{prefix} Fakültə A", OrgUnitType.FACULTY)
        spec_a = _unit(org, f"{prefix} İxtisas A", OrgUnitType.SPECIALTY, fac_a)
        chair = _unit(org, f"{prefix} Kafedra", OrgUnitType.CHAIR, fac_a)
        g101 = _unit(org, "A-101", OrgUnitType.GROUP, spec_a, degree_level="bachelor", education_form="full_time")
        g102 = _unit(org, "A-102", OrgUnitType.GROUP, spec_a, degree_level="bachelor", education_form="full_time")
        m601 = _unit(org, "M-601", OrgUnitType.GROUP, spec_a, degree_level="master", education_form="full_time")
        q701 = _unit(org, "Q-701", OrgUnitType.GROUP, spec_a, degree_level="bachelor", education_form="part_time")
        fac_b = _unit(org, f"{prefix} Fakültə B", OrgUnitType.FACULTY)
        spec_b = _unit(org, f"{prefix} İxtisas B", OrgUnitType.SPECIALTY, fac_b)
        b101 = _unit(org, "B-101", OrgUnitType.GROUP, spec_b, degree_level="bachelor", education_form="full_time")
        today = datetime.date.today()
        period = AcademicPeriod.objects.create(
            organization=org,
            name="Payız",
            period_type=AcademicPeriodType.SEMESTER,
            academic_year="2026/2027",
            start_date=today - datetime.timedelta(days=10),
            end_date=today + datetime.timedelta(days=120),
            is_current=True,
        )
        subjects = {
            code: Subject.objects.create(organization=org, code=code, name=name)
            for code, name in (
                ("ALQ", "Alqoritmlər"),
                ("FIZ", "Fizika"),
                ("TAR", "Tarix"),
                ("MAG", "Magistr seminarı"),
                ("QYB", "Qiyabi fənn"),
            )
        }
        teachers = [User.objects.create_user(f"{prefix}_t{k}", f"{prefix}_t{k}@x.test", "pw") for k in range(1, 4)]
        for teacher in teachers:
            _member(org, teacher, "teacher")
        coordinator = User.objects.create_user(f"{prefix}_coord", f"{prefix}_coord@x.test", "pw")
        _member(org, coordinator, "program_coordinator", scope_unit=fac_a)
        outsider = User.objects.create_user(f"{prefix}_coordb", f"{prefix}_coordb@x.test", "pw")
        _member(org, outsider, "program_coordinator", scope_unit=fac_b)
        rim = User.objects.create_user(f"{prefix}_rim", f"{prefix}_rim@x.test", "pw")
        _member(org, rim, "ikt_rehber")

        bachelor = Program.objects.create(organization=org, code="BA", name="Bakalavr", specialty_unit=spec_a)
        master = Program.objects.create(
            organization=org, code="MA", name="Magistr", specialty_unit=spec_a, degree_level="master"
        )
        cur_ba = Curriculum.objects.create(organization=org, program=bachelor, admission_year=2025)
        cur_ma = Curriculum.objects.create(organization=org, program=master, admission_year=2025)
        for curriculum, code, lecture, seminar in (
            (cur_ba, "ALQ", 30, 30),
            (cur_ba, "FIZ", 30, 15),
            (cur_ba, "TAR", 15, 0),
            (cur_ba, "QYB", 15, 15),
            (cur_ma, "MAG", 30, 30),
        ):
            CurriculumSubject.objects.create(
                organization=org,
                curriculum=curriculum,
                subject=subjects[code],
                semester_number=1,
                lecture_hours=lecture,
                seminar_hours=seminar,
            )
        students = []
        for index, (group, program, curriculum) in enumerate(
            (
                (g101, bachelor, cur_ba),
                (g101, bachelor, cur_ba),
                (g102, bachelor, cur_ba),
                (m601, master, cur_ma),
                (q701, bachelor, cur_ba),
                (b101, bachelor, cur_ba),
            )
        ):
            student = User.objects.create_user(f"{prefix}_s{index}", f"{prefix}_s{index}@x.test", "pw")
            _member(org, student, "student")
            StudentAcademicRecord.objects.create(
                organization=org,
                student=student,
                program=program,
                curriculum=curriculum,
                group=group,
                admission_year=2025,
            )
            students.append(student)
        t1, t2, t3 = teachers
        offerings = {}
        for group, code, instructor in (
            (g101, "ALQ", t1),
            (g101, "FIZ", t2),
            (g101, "TAR", t3),
            (g102, "ALQ", t1),
            (g102, "FIZ", t2),
            (m601, "MAG", t3),
            (q701, "QYB", t2),
            (b101, "ALQ", t1),
        ):
            offerings[(group.name, code)] = CourseOffering.objects.create(
                organization=org, subject=subjects[code], period=period, group=group, instructor=instructor
            )
        _stream_row(org, chair, period, subjects["ALQ"], [g101, g102], t1)
    return {
        "org": org,
        "owner": owner,
        "fac_a": fac_a,
        "fac_b": fac_b,
        "groups": {"A-101": g101, "A-102": g102, "M-601": m601, "Q-701": q701, "B-101": b101},
        "period": period,
        "subjects": subjects,
        "teachers": teachers,
        "coordinator": coordinator,
        "outsider": outsider,
        "rim": rim,
        "students": students,
        "offerings": offerings,
    }


def _stream_row(org, chair, period, subject, groups, lecturer):
    """Tapşırıq sətri: iki qrupun birgə mühazirəsi (union_count = 1)."""
    from apps.workload.models import TeacherAssignment, TeachingTask, TeachingTaskRow

    task = TeachingTask.objects.create(organization=org, academic_year=period.academic_year, chair=chair)
    row = TeachingTaskRow.objects.create(
        organization=org,
        task=task,
        period=period,
        subject=subject,
        union_count=1,
        subgroup_count=len(groups),
        lecture_plan=30,
        lecture_total=30,
        seminar_plan=30,
        seminar_total=30 * len(groups),
    )
    row.groups.set(groups)
    TeacherAssignment.objects.create(organization=org, row=row, teacher=lecturer, activity="lecture", hours=30)
    return row


def faculty_scope(world, key="fac_a"):
    return {"kind": "faculty", "unit_ids": [str(world[key].pk)], "group_ids": []}


__all__ = ["build_world", "faculty_scope"]
