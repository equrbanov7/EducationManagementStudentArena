"""«Tədris etdiyi fənlər» siyahısının təkrarsızlığı (profil məlumatı kartı).

2026-08 sahib bildirişi: «müəllimin tədris etdiyi fənlər yerində eyni fənlər
təkrarda düşüb». Səbəb — siyahı ``CourseOffering`` sətirlərindən qurulurdu və
dedup açarı ``(subject_id, group_id)`` idi, yəni fənn hər qrup/semestr üçün
yenidən çıxırdı.

Bu modul ``build_teacher_subject_rows``-un müqaviləsini kilidləyir: FƏNN üzrə
təkrarsız, amma qrup/semestr məlumatı itmədən.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.accounts.views.profile.context_builder._helpers import (
    TEACHER_SUBJECT_TOOLTIP_GROUPS,
    build_teacher_subject_rows,
)
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit, Role
from apps.registrar.models import CourseOffering, Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


def _activate_member(organization, user, role_name):
    """Aktiv üzvlük (PG ``registrar_guard_active_member`` tələbi)."""

    role, _created = Role.objects.get_or_create(
        organization=organization,
        name=role_name,
        defaults={"display_name": role_name.title(), "level": 50, "permissions": []},
    )
    Role.objects.filter(pk=role.pk).update(is_active=True)
    Membership.objects.get_or_create(organization=organization, user=user, role=role, defaults={"is_active": True})
    return role


class BuildTeacherSubjectRowsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("tsc_owner", "tsc_owner@qku.edu.az", "pw")
        cls.teacher = User.objects.create_user("tsc_teacher", "tsc_teacher@qku.edu.az", "pw")
        cls.other_teacher = User.objects.create_user("tsc_other", "tsc_other@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="Təkrar Universiteti",
                slug="tsc-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.other_org = Organization.objects.create(
                name="Digər Universitet",
                slug="tsc-univ-2",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.periods = [
                AcademicPeriod.objects.create(
                    organization=cls.org,
                    name=f"2024/2025 dövr {index}",
                    period_type=AcademicPeriodType.SEMESTER,
                    academic_year="2024/2025",
                    start_date="2024-09-01",
                    end_date="2025-01-31",
                )
                for index in range(3)
            ]
            cls.groups = [
                OrgUnit.objects.create(
                    organization=cls.org, name=f"QRUP-{index}", slug=f"tsc-g{index}", unit_type=OrgUnitType.GROUP
                )
                for index in range(4)
            ]
            cls.subject_a = Subject.objects.create(organization=cls.org, code="MM101", name="Mülki müdafiə")
            cls.subject_b = Subject.objects.create(organization=cls.org, code="HF101", name="Həyat təhlükəsizliyi")
            # PostgreSQL-də `registrar_guard_active_member` trigger-i instruktoru
            # AKTİV üzvlük olmadan `CourseOffering`-ə bağlamağa qoymur (SQLite-da
            # belə trigger yoxdur — ona görə uyğunsuzluq yalnız PG-də görünür).
            for organization, user in (
                (cls.org, cls.teacher),
                (cls.org, cls.other_teacher),
                (cls.other_org, cls.teacher),
                (cls.other_org, cls.other_teacher),
            ):
                _activate_member(organization, user, "teacher")

    def _offering(self, *, subject, group, period, instructor=None):
        with bypass_rls():
            return CourseOffering.objects.create(
                organization=self.org,
                subject=subject,
                period=period,
                group=group,
                instructor=instructor or self.teacher,
            )

    def test_same_subject_across_groups_and_semesters_is_one_row(self):
        """4 qrup × 3 semestr = 12 offering → 1 fənn sətri (əvvəl 4 çip idi)."""
        for period in self.periods:
            for group in self.groups:
                self._offering(subject=self.subject_a, group=group, period=period)

        with bypass_rls():
            rows = build_teacher_subject_rows(self.teacher, self.org)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["name"], "Mülki müdafiə")
        self.assertEqual(row["group_count"], 4)
        self.assertEqual(row["period_count"], 3)
        # Çox qrupda tək-qrup adı boşdur → şablon sayı göstərir.
        self.assertEqual(row["single_group_name"], "")

    def test_single_group_keeps_group_name(self):
        """Tək qrupda köhnə görünüş qorunur — məlumat itmir."""
        self._offering(subject=self.subject_a, group=self.groups[0], period=self.periods[0])

        with bypass_rls():
            rows = build_teacher_subject_rows(self.teacher, self.org)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["single_group_name"], "QRUP-0")
        self.assertEqual(rows[0]["group_count"], 1)
        self.assertEqual(rows[0]["period_count"], 1)

    def test_distinct_subjects_stay_separate_and_sorted_by_name(self):
        self._offering(subject=self.subject_a, group=self.groups[0], period=self.periods[0])
        self._offering(subject=self.subject_b, group=self.groups[1], period=self.periods[0])

        with bypass_rls():
            rows = build_teacher_subject_rows(self.teacher, self.org)

        self.assertEqual([row["name"] for row in rows], ["Həyat təhlükəsizliyi", "Mülki müdafiə"])

    def test_groupless_offering_does_not_inflate_group_count(self):
        """``group=None`` (bütün ixtisas üçün) sətri qrup saymır, fənni saxlayır."""
        self._offering(subject=self.subject_a, group=None, period=self.periods[0])
        self._offering(subject=self.subject_a, group=self.groups[0], period=self.periods[0])

        with bypass_rls():
            rows = build_teacher_subject_rows(self.teacher, self.org)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["group_count"], 1)
        self.assertEqual(rows[0]["single_group_name"], "QRUP-0")

    def test_tooltip_lists_group_names_and_is_capped(self):
        with bypass_rls():
            many_groups = [
                OrgUnit.objects.create(
                    organization=self.org,
                    name=f"BÖYÜK-{index:02d}",
                    slug=f"tsc-big{index}",
                    unit_type=OrgUnitType.GROUP,
                )
                for index in range(TEACHER_SUBJECT_TOOLTIP_GROUPS + 3)
            ]
        for group in many_groups:
            self._offering(subject=self.subject_a, group=group, period=self.periods[0])

        with bypass_rls():
            rows = build_teacher_subject_rows(self.teacher, self.org)

        row = rows[0]
        self.assertEqual(row["group_count"], TEACHER_SUBJECT_TOOLTIP_GROUPS + 3)
        self.assertEqual(row["groups_tooltip"].count(","), TEACHER_SUBJECT_TOOLTIP_GROUPS - 1)
        self.assertTrue(row["groups_tooltip"].endswith("…"))

    def test_other_teachers_and_orgs_are_excluded(self):
        self._offering(subject=self.subject_a, group=self.groups[0], period=self.periods[0])
        self._offering(
            subject=self.subject_b, group=self.groups[1], period=self.periods[0], instructor=self.other_teacher
        )

        with bypass_rls():
            rows = build_teacher_subject_rows(self.teacher, self.org)
            empty = build_teacher_subject_rows(self.teacher, self.other_org)

        self.assertEqual([row["name"] for row in rows], ["Mülki müdafiə"])
        self.assertEqual(empty, [])
