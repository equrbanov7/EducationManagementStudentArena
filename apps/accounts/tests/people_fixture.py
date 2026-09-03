"""«Müəllimlər»/«Tələbələr» kataloqu testləri üçün ORTAQ universitet fixture-u.

İki fakültəli kiçik universitet qurur (A və B) ki, scope sızması ölçülə bilsin:
dekan A yalnız A-nı, kafedra müdiri A1 yalnız A1-i görməlidir.

⚠️ ``registrar_guard_active_member`` PG trigger-i ``Enrollment``/
``StudentAcademicRecord`` üçün AKTİV üzvlük tələb edir — ona görə hər tələbəyə
və müəllimə üzvlük verilir (bax `apps/registrar/tests/test_selfwork_archive.py`).
"""

from __future__ import annotations

from datetime import date

from django.contrib.auth import get_user_model

from apps.accounts.models import UserProfile
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit, Role
from apps.registrar.models import (
    CourseOffering,
    Curriculum,
    Enrollment,
    Program,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType, RoleScopeType
from core.rls import bypass_rls

User = get_user_model()

PEOPLE_READ = [
    "people.view_teachers",
    "people.view_students",
    "people.view_contacts",
    "people.view_demographics",
]


def make_user(username, *, first, last, patronymic="", gender="unspecified", birth_date=None, is_active=True):
    user = User.objects.create_user(username, f"{username}@qku.edu.az", "pw")
    user.first_name = first
    user.last_name = last
    user.is_active = is_active
    user.save(update_fields=["first_name", "last_name", "is_active"])
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.patronymic = patronymic
    profile.gender = gender
    profile.birth_date = birth_date
    profile.phone = "+994500000000"
    profile.save(update_fields=["patronymic", "gender", "birth_date", "phone"])
    return user


def make_role(organization, name, *, level, scope_type, permissions):
    role, _ = Role.objects.get_or_create(
        organization=organization,
        name=name,
        defaults={
            "display_name": name.replace("_", " ").title(),
            "level": level,
            "scope_type": scope_type,
            "permissions": permissions,
        },
    )
    Role.objects.filter(pk=role.pk).update(is_active=True, level=level, scope_type=scope_type, permissions=permissions)
    role.refresh_from_db()
    return role


def add_membership(organization, user, role, *, unit=None):
    membership, _ = Membership.objects.get_or_create(
        organization=organization,
        user=user,
        role=role,
        scope_unit=unit,
        defaults={"is_active": True},
    )
    if not membership.is_active:
        Membership.objects.filter(pk=membership.pk).update(is_active=True)
    return membership


class PeopleFixture:
    """`setUpTestData` içindən çağırılan qurucu — testlər onun sahələrini oxuyur."""

    def __init__(self):
        self.owner = User.objects.create_user("ppl_owner", "ppl_owner@qku.edu.az", "pw")
        with bypass_rls():
            self._build()

    def _build(self):
        self.org = Organization.objects.create(
            name="People Univ",
            slug="people-univ",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.owner,
            status="active",
            is_active=True,
        )
        self.period = AcademicPeriod.objects.create(
            organization=self.org,
            name="Payız",
            period_type=AcademicPeriodType.SEMESTER,
            academic_year="2025/2026",
            start_date="2025-09-01",
            end_date="2026-01-31",
            is_current=True,
        )

        self.faculty_a = self._unit("Fakültə A", "fak-a", OrgUnitType.FACULTY, None)
        self.kafedra_a1 = self._unit("Kafedra A1", "kaf-a1", OrgUnitType.CHAIR, self.faculty_a)
        self.specialty_a1 = self._unit("İxtisas A1", "ixt-a1", OrgUnitType.SPECIALTY, self.kafedra_a1)
        self.group_a1 = self._unit("Qrup A1-1", "qrup-a1-1", OrgUnitType.GROUP, self.specialty_a1)

        self.faculty_b = self._unit("Fakültə B", "fak-b", OrgUnitType.FACULTY, None)
        self.kafedra_b1 = self._unit("Kafedra B1", "kaf-b1", OrgUnitType.CHAIR, self.faculty_b)
        self.specialty_b1 = self._unit("İxtisas B1", "ixt-b1", OrgUnitType.SPECIALTY, self.kafedra_b1)
        self.group_b1 = self._unit("Qrup B1-1", "qrup-b1-1", OrgUnitType.GROUP, self.specialty_b1)

        self.role_rector = make_role(
            self.org, "rector", level=100, scope_type=RoleScopeType.ORGANIZATION, permissions=["*"]
        )
        self.role_dean = make_role(
            self.org,
            "dean",
            level=80,
            scope_type=RoleScopeType.UNIT,
            permissions=[*PEOPLE_READ, "people.manage_status", "people.manage_teacher_role"],
        )
        self.role_chair = make_role(
            self.org,
            "chair_head",
            level=70,
            scope_type=RoleScopeType.UNIT,
            permissions=["people.view_teachers", "people.view_students"],
        )
        # `grade.input` MƏCBURİDİR: `registrar_guard_active_member` PG trigger-i
        # `CourseOffering.instructor` üçün məhz bu icazəni tələb edir.
        self.role_teacher = make_role(
            self.org,
            "teacher",
            level=50,
            scope_type=RoleScopeType.COURSE,
            permissions=["course.view", "grade.input"],
        )
        self.role_student = make_role(
            self.org, "student", level=10, scope_type=RoleScopeType.UNIT, permissions=["course.view"]
        )

        self.rector = make_user("ppl_rector", first="Rəşad", last="Rektorov")
        add_membership(self.org, self.rector, self.role_rector)

        self.dean_a = make_user("ppl_dean_a", first="Dilarə", last="Dekanova")
        add_membership(self.org, self.dean_a, self.role_dean, unit=self.faculty_a)

        self.dean_b = make_user("ppl_dean_b", first="Bəhram", last="Bəyov")
        add_membership(self.org, self.dean_b, self.role_dean, unit=self.faculty_b)

        # Scope-suz dekan — `scope_unit` təyin EDİLMƏYİB (fail-closed sınağı).
        self.dean_unscoped = make_user("ppl_dean_x", first="Xəyal", last="Xəyalov")
        add_membership(self.org, self.dean_unscoped, self.role_dean, unit=None)

        self.chair_a1 = make_user("ppl_chair_a1", first="Kamran", last="Kafedrov")
        add_membership(self.org, self.chair_a1, self.role_chair, unit=self.kafedra_a1)

        self.teacher_a = make_user(
            "ppl_teacher_a",
            first="Elvin",
            last="Əliyev",
            patronymic="Səməd oğlu",
            gender=UserProfile.Gender.MALE,
            birth_date=date(1985, 5, 10),
        )
        add_membership(self.org, self.teacher_a, self.role_teacher, unit=self.kafedra_a1)

        self.teacher_b = make_user("ppl_teacher_b", first="Nərmin", last="Bəkirova")
        add_membership(self.org, self.teacher_b, self.role_teacher, unit=self.kafedra_b1)

        self.program_a = Program.objects.create(
            organization=self.org, code="PA", name="Proqram A", specialty_unit=self.specialty_a1
        )
        self.program_b = Program.objects.create(
            organization=self.org, code="PB", name="Proqram B", specialty_unit=self.specialty_b1
        )
        self.curriculum_a = Curriculum.objects.create(
            organization=self.org, program=self.program_a, admission_year=2024
        )
        self.curriculum_b = Curriculum.objects.create(
            organization=self.org, program=self.program_b, admission_year=2024
        )
        self.subject = Subject.objects.create(organization=self.org, code="MAT101", name="Riyaziyyat")

        self.student_a = self.add_student("ppl_student_a", faculty="a", first="Aysel", last="Ağayeva")
        self.student_b = self.add_student("ppl_student_b", faculty="b", first="Bəxtiyar", last="Babayev")

        self.offering_a = CourseOffering.objects.create(
            organization=self.org,
            subject=self.subject,
            period=self.period,
            group=self.group_a1,
            instructor=self.teacher_a,
        )
        Enrollment.objects.create(organization=self.org, student=self.student_a, offering=self.offering_a)

    def _unit(self, name, slug, unit_type, parent):
        return OrgUnit.objects.create(organization=self.org, name=name, slug=slug, unit_type=unit_type, parent=parent)

    def add_student(self, username, *, faculty, first="Tələbə", last="Tələbəyev", **kwargs):
        """Yeni tələbə + akademik qeyd. Sorğu-sayı testi bunu döngü ilə çağırır."""
        user = make_user(username, first=first, last=last, **kwargs)
        add_membership(self.org, user, self.role_student)
        StudentAcademicRecord.objects.create(
            organization=self.org,
            student=user,
            program=self.program_a if faculty == "a" else self.program_b,
            curriculum=self.curriculum_a if faculty == "a" else self.curriculum_b,
            group=self.group_a1 if faculty == "a" else self.group_b1,
            admission_year=2024,
        )
        return user

    def add_teacher(self, username, *, faculty="a", first="Müəllim", last="Müəllimov", **kwargs):
        user = make_user(username, first=first, last=last, **kwargs)
        add_membership(
            self.org,
            user,
            self.role_teacher,
            unit=self.kafedra_a1 if faculty == "a" else self.kafedra_b1,
        )
        return user


__all__ = ["PEOPLE_READ", "PeopleFixture", "add_membership", "make_role", "make_user"]
