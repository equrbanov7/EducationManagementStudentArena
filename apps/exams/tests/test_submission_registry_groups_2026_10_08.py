"""Sual göndərişi → reyestr qrupları (exams 0074) — fakültə/kafedra süzgəci və backfill.

Sahib qərarı (2026-10-08): dərs yükündən gələn REYESTR qrupu ilə göndərilən dəst
mərkəzin fakültə/kafedra süzgəcinə düşməlidir; mövcud göndərişlər ``group_label``-dən
YALNIZ birmənalı uyğunluqda bağlanır.
"""

import importlib

from django.apps import apps as django_apps
from django.urls import reverse

from apps.exams.models import QuestionSubmission, StudentGroup
from apps.exams.tests import test_submission_sources_2026_10_08 as s2
from apps.organizations.models import OrgUnit
from core.constants import OrgUnitType

MIGRATION = importlib.import_module("apps.exams.migrations.0074_questionsubmission_registry_groups")


class RegistryGroupReviewerFilterTests(s2._LoadFixture):
    def _section(self, **params):
        query = "&".join(f"{key}={value}" for key, value in params.items())
        response = self._client_for(self.exam_center).get(
            f"{reverse('accounts:profile')}?section=question-submissions&{query}"
        )
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_registry_group_submission_is_found_by_faculty_and_chair_filters(self):
        other_faculty = OrgUnit.objects.create(
            organization=self.org, name="Humanitar fakültə", unit_type=OrgUnitType.FACULTY
        )
        other_group = OrgUnit.objects.create(
            organization=self.org, name="Tarix-101", unit_type=OrgUnitType.GROUP, parent=other_faculty
        )
        inside = self._to_center(self._submission(title="Reyestr daxili", group_label="2233 İ", units=[self.group_a]))
        outside = self._to_center(
            self._submission(title="Reyestr xarici", group_label="Tarix-101", units=[other_group])
        )
        self.assertEqual(list(inside.registry_groups.all()), [self.group_a])
        self.assertEqual(list(outside.registry_groups.all()), [other_group])

        html = self._section(qsub_faculty=self.faculty.pk)
        self.assertIn("Reyestr daxili", html)
        self.assertNotIn("Reyestr xarici", html)
        html = self._section(qsub_faculty=self.faculty.pk, qsub_kafedra=self.chair.pk)
        self.assertIn("Reyestr daxili", html)
        self.assertNotIn("Reyestr xarici", html)

    def test_routing_reads_stored_registry_groups(self):
        submission = self._submission(title="Marşrut", group_label="2233 İ", units=[self.group_a])
        self.assertEqual(submission.chair_unit, self.chair)


class RegistryGroupBackfillTests(s2._LoadFixture):
    def _legacy(self, title, label, **extra):
        submission = self._submission(title=title, group_label=label, **extra)
        submission.registry_groups.clear()  # 0074-dən əvvəlki vəziyyət
        return submission

    def test_unambiguous_names_are_linked(self):
        submission = self._legacy("Köhnə 1", "2233 İ, 2232 İ")
        MIGRATION.backfill_registry_groups(django_apps, None)
        self.assertEqual(set(submission.registry_groups.all()), {self.group_a, self.group_b})
        # İdempotent.
        MIGRATION.backfill_registry_groups(django_apps, None)
        self.assertEqual(submission.registry_groups.count(), 2)

    def test_ambiguous_unknown_and_cohort_names_are_skipped(self):
        OrgUnit.objects.create(
            organization=self.org, name="2232 İ", slug="dup-2232-i", unit_type=OrgUnitType.GROUP, parent=self.faculty
        )
        cohort = StudentGroup.objects.create(teacher=self.teacher, organization=self.org, name="2233 İ")
        submission = self._legacy("Köhnə 2", "2233 İ, 2232 İ, Mövcud olmayan", student_group=cohort, groups=[cohort])
        MIGRATION.backfill_registry_groups(django_apps, None)
        # «2233 İ» — köhnə kohortun adıdır; «2232 İ» — iki reyestr qrupu (qeyri-müəyyən); üçüncü yoxdur.
        self.assertEqual(submission.registry_groups.count(), 0)

    def test_other_organization_group_is_never_linked(self):
        from apps.organizations.models import Organization
        from core.constants import OrganizationType

        other = Organization.objects.create(
            name="Başqa Uni", org_type=OrganizationType.UNIVERSITY, owner=self.owner, status="active", is_active=True
        )
        OrgUnit.objects.create(organization=other, name="Yalnız orada", unit_type=OrgUnitType.GROUP)
        submission = self._legacy("Köhnə 3", "Yalnız orada")
        MIGRATION.backfill_registry_groups(django_apps, None)
        self.assertEqual(submission.registry_groups.count(), 0)
        self.assertTrue(QuestionSubmission.objects.filter(pk=submission.pk).exists())

    def test_label_names_helper(self):
        self.assertEqual(MIGRATION.label_names(" 2233 İ ,2232 İ, 2233 İ,, "), ["2233 İ", "2232 İ"])


class RegistryGroupRlsTests(s2._LoadFixture):
    def test_join_table_has_forced_tenant_policy(self):
        from django.db import connection

        if connection.vendor != "postgresql":
            self.skipTest("RLS yalnız PostgreSQL-də")
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT c.relrowsecurity, c.relforcerowsecurity, "
                "(SELECT count(*) FROM pg_policy p WHERE p.polrelid = c.oid AND p.polname = 'rls_tenant_isolation') "
                "FROM pg_class c WHERE c.relname = %s",
                [MIGRATION._TABLE],
            )
            enabled, forced, policies = cursor.fetchone()
        self.assertTrue(enabled)
        self.assertTrue(forced)
        self.assertEqual(policies, 1)
