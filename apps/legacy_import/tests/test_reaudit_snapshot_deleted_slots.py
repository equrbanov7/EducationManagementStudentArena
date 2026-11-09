"""Audit deleted timetable history without widening tenant or period scope."""

import datetime as dt
from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from django.utils import timezone

from apps.legacy_import.services.reaudit_snapshot import queries
from apps.organizations.models import AcademicPeriod, Organization, OrgUnit
from apps.registrar.models import CourseOffering, ScheduleSlot, Subject
from apps.registrar.tests.test_lab_groups_2026_11_06 import _LabWorld
from core.rls import bypass_rls


class DeletedSlotSnapshotTest(_LabWorld, TestCase):
    def setUp(self):
        self.scope = bypass_rls()
        self.scope.__enter__()
        self.addCleanup(self.scope.__exit__, None, None, None)
        self.assertEqual(connection.vendor, "postgresql")

    def slot(self, offering=None, **extra):
        offering = offering or self.offering
        return ScheduleSlot.all_objects.create(
            organization_id=offering.organization_id,
            offering=offering,
            weekday=1,
            start_time=dt.time(9),
            end_time=dt.time(10, 20),
            **extra,
        )

    def exported(self):
        label = "registrar.ScheduleSlot"
        with patch.object(queries, "ORG", str(self.org.pk)), patch.object(queries, "PERIOD", str(self.period.pk)):
            spec = queries.SCHEMAS[label]
            return list(queries.scoped_query(label, spec).values(*spec["fields"]))

    def test_deleted_and_parked_history_is_included_without_reactivating_slots(self):
        live = self.slot()
        parked = self.slot(is_parked=True, parked_at=timezone.now(), park_reason="Synthetic history")
        deleted = self.slot(is_deleted=True, deleted_at=timezone.now())
        self.assertFalse(ScheduleSlot.objects.filter(pk=deleted.pk).exists())
        rows = {row["id"]: row for row in self.exported()}
        self.assertEqual(set(rows), {live.pk, parked.pk, deleted.pk})
        self.assertTrue(rows[deleted.pk]["is_deleted"])
        self.assertEqual(rows[deleted.pk]["deleted_at"], deleted.deleted_at)
        self.assertTrue(rows[parked.pk]["is_parked"])
        self.assertFalse(ScheduleSlot.objects.filter(pk=deleted.pk).exists())
        parked.refresh_from_db()
        self.assertTrue(parked.is_parked)

    def test_deleted_foreign_tenant_and_other_period_are_excluded(self):
        kept = self.slot(is_deleted=True, deleted_at=timezone.now())
        other_period = AcademicPeriod.objects.create(
            organization=self.org,
            name="Synthetic previous",
            period_type=self.period.period_type,
            academic_year="2025/2026",
            start_date=dt.date(2025, 9, 15),
            end_date=dt.date(2026, 1, 15),
        )
        old_offering = CourseOffering.objects.create(
            organization=self.org,
            subject=self.offering.subject,
            group=self.group,
            period=other_period,
        )
        self.slot(old_offering, is_deleted=True, deleted_at=timezone.now())
        foreign = Organization.objects.create(name="Foreign", slug="deleted-slot-foreign", owner=self.owner)
        foreign_period = AcademicPeriod.objects.create(
            organization=foreign,
            name="Synthetic foreign",
            period_type=self.period.period_type,
            academic_year=self.period.academic_year,
            start_date=self.period.start_date,
            end_date=self.period.end_date,
        )
        foreign_offering = CourseOffering.objects.create(
            organization=foreign,
            subject=Subject.objects.create(organization=foreign, code="FOREIGN", name="Foreign"),
            group=OrgUnit.objects.create(organization=foreign, name="Foreign", slug="foreign", unit_type="group"),
            period=foreign_period,
        )
        self.slot(foreign_offering, is_deleted=True, deleted_at=timezone.now())
        self.assertEqual([row["id"] for row in self.exported()], [kept.pk])
