"""MR-000234: plan saatı yalnız dry-run baseline-ı ilə yazılır, bölmələr dəyişmir, undo dəqiq qaytarır."""

import datetime as dt
import io
from contextlib import ExitStack
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar.models import CourseOffering, JournalShare, Subject
from apps.syllabus.models import Syllabus, SyllabusVersion
from apps.syllabus.public import import_migrated_version, section_data_map
from apps.syllabus.services import mr234_plan_hours as service
from apps.syllabus.week_plan import expected_week_rows
from apps.workload.models import TeacherAssignment, TeachingTask, TeachingTaskRow
from core.rls import bypass_rls

WEEK = {"week": {"rows": [{"topic": f"Mövzu {i}", "practical": 2, "seminar": 2 if i < 13 else 0} for i in range(38)]}}


class MR234PlanHoursTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.actor = User.objects.create_superuser("mr234_admin", "admin@example.test", "test")
        with bypass_rls():
            cls.org = Organization.objects.create(
                id=service.ORG, name="QKU", slug="qku", org_type="university", owner=cls.actor, status="active"
            )
            teacher_role = cls.org.roles.get(name="teacher")
            cls.yegane = User.objects.create_user(id=service.AUTHOR, username="yegane.test")
            cls.aytac = User.objects.create_user(id=service.REFERENCE_AUTHOR, username="aytac.test")
            for user in (cls.yegane, cls.aytac):
                UserProfile.objects.filter(user=user).update(organization=cls.org)
                Membership.objects.create(user=user, organization=cls.org, role=teacher_role)
            period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Payız",
                academic_year="2026/2027",
                period_type="semester",
                start_date=dt.date(2026, 9, 1),
                end_date=dt.date(2027, 1, 31),
                is_current=True,
            )
            own_subject = Subject.objects.create(id=service.SUBJECT, organization=cls.org, code="QKU-539", name="Xd-2")
            group_subject = Subject.objects.create(organization=cls.org, code="QKU-105", name="İxd-2")
            group = OrgUnit.objects.create(organization=cls.org, name="935 BM ing", slug="bm935", unit_type="group")
            cls.offering = CourseOffering.objects.create(
                id=service.REFERENCE_OFFERING,
                organization=cls.org,
                subject=group_subject,
                period=period,
                group=group,
                instructor=cls.aytac,
                lesson_hours=75,
            )
            JournalShare.objects.create(
                organization=cls.org, offering=cls.offering, teacher=cls.yegane, source="legacy"
            )
            cls.reference, _ = import_migrated_version(
                organization=cls.org,
                subject=group_subject,
                period=period,
                offering=cls.offering,
                author=cls.aytac,
                approved_at=timezone.now(),
                plan_hours={"seminar": 75},
                section_data=WEEK,
            )
            cls.syllabus, cls.version = import_migrated_version(
                organization=cls.org,
                subject=own_subject,
                author=cls.yegane,
                approved_at=timezone.now(),
                section_data=WEEK,
            )
            chair = OrgUnit.objects.create(organization=cls.org, name="Dillər", slug="dil-chair", unit_type="chair")
            task = TeachingTask.objects.create(organization=cls.org, chair=chair, academic_year="2026/2027")
            cls.row = TeachingTaskRow.objects.create(
                id=service.WORKLOAD_ROW,
                organization=cls.org,
                task=task,
                subject=group_subject,
                period=period,
                seminar_plan=75,
                seminar_total=150,
            )
            cls.row.groups.add(group)
            TeacherAssignment.objects.create(
                organization=cls.org, row=cls.row, teacher=cls.yegane, activity="seminar", hours=75
            )

    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        for key, value in {
            "SYLLABUS": str(self.syllabus.pk),
            "APPROVED": str(self.version.pk),
            "REFERENCE_SYLLABUS": str(self.reference.pk),
        }.items():
            stack.enter_context(patch.object(service, key, value))

    def call(self, **kwargs):
        return service.repair_mr234_plan_hours(organization=self.org, user=self.actor, **kwargs)

    def test_dry_apply_repeat_and_exact_undo_keep_sections(self):
        before = section_data_map(self.version)
        dry = self.call()
        self.assertEqual(dry["versions_to_plan"], 1)
        self.assertEqual(SyllabusVersion.objects.get(pk=self.version.pk).plan_hours, {})
        with self.assertRaisesMessage(service.MR234Error, "fresh_live_baseline_required"):
            self.call(apply=True)
        with self.assertRaisesMessage(service.MR234Error, "live_baseline_changed"):
            self.call(apply=True, expected_baseline="0" * 64)
        self.assertEqual(self.call(apply=True, expected_baseline=dry["baseline"])["versions_planned"], 1)
        version = SyllabusVersion.objects.get(pk=self.version.pk)
        self.assertEqual(version.plan_hours, service.HOURS)
        self.assertEqual(version.status, "approved")
        self.assertEqual(expected_week_rows(version.plan_hours), 38)
        self.assertEqual(Syllabus.objects.get(pk=self.syllabus.pk).plan_hours_override, service.HOURS)
        self.assertEqual(section_data_map(version), before)
        self.assertEqual(self.call(), {"already_present": 1})

        undo = self.call(undo=True)
        self.assertEqual(undo["versions_to_restore"], 1)
        self.call(undo=True, apply=True, expected_baseline=undo["baseline"])
        self.assertEqual(SyllabusVersion.objects.get(pk=self.version.pk).plan_hours, {})
        self.assertEqual(Syllabus.objects.get(pk=self.syllabus.pk).plan_hours_override, {})
        self.assertEqual(self.call(undo=True), {"already_undone": 1})

    def test_reference_group_plan_change_refuses(self):
        SyllabusVersion.objects.filter(pk=self.reference.approved_version_id).update(plan_hours={"seminar": 60})
        with self.assertRaisesMessage(service.MR234Error, "reference_group_plan_changed"):
            self.call()

    def test_existing_plan_or_changed_topics_refuse(self):
        SyllabusVersion.objects.filter(pk=self.version.pk).update(plan_hours={"seminar": 60})
        with self.assertRaisesMessage(service.MR234Error, "plan_hours_changed"):
            self.call()
        SyllabusVersion.objects.filter(pk=self.version.pk).update(plan_hours={})
        self.version.sections.filter(section_id="week").update(data={"rows": [{"topic": "Bir"}]})
        with self.assertRaisesMessage(service.MR234Error, "week_topics_changed"):
            self.call()

    def test_undo_refuses_after_later_dossier_change(self):
        dry = self.call()
        self.call(apply=True, expected_baseline=dry["baseline"])
        self.version.sections.filter(section_id="lit").update(data={"primary": ["Yeni"]})
        with self.assertRaisesMessage(service.MR234Error, "undo_live_state_changed"):
            self.call(undo=True)

    def test_command_dry_run_prints_counts_and_baseline_only(self):
        out = io.StringIO()
        call_command("repair_mr234_plan_hours", actor=self.actor.username, stdout=out)
        line = out.getvalue().strip()
        self.assertRegex(line, r"^mr234_plan: baseline=[0-9a-f]{64} sharing_journals=0 versions_to_plan=1$")
        self.assertEqual(SyllabusVersion.objects.get(pk=self.version.pk).plan_hours, {})
        with self.assertRaisesMessage(CommandError, "fresh_live_baseline_required"):
            call_command("repair_mr234_plan_hours", actor=self.actor.username, apply=True, stdout=io.StringIO())
