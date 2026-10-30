"""Exact MR83 diagnostics exclude other journals and foreign tenants."""

from unittest.mock import patch

from django.test import TransactionTestCase

from apps.registrar.models import CourseOffering
from apps.syllabus.models import Syllabus, SyllabusShare
from apps.workload.services.scoped_snapshot.request_syllabus import collect_request_syllabus
from apps.workload.tests import test_scoped_snapshot as fixtures


class RequestSyllabusTests(TransactionTestCase):
    setUp = fixtures.ScopedSnapshotTests.setUp

    def test_links_are_included_without_unrelated_syllabi(self):
        target = CourseOffering.objects.create(
            organization=self.org, subject=self.stack["subject"], period=self.stack["period"], instructor=self.teacher
        )
        source = Syllabus.objects.create(organization=self.org, subject=self.stack["subject"], author=self.teacher)
        share = SyllabusShare.objects.create(organization=self.org, offering=target, syllabus=source)
        unrelated = Syllabus.objects.create(organization=self.org, subject=self.stack["subject"], author=self.actor)
        with (
            patch("apps.workload.services.scoped_snapshot.request_syllabus.OFFERINGS", (str(target.pk),)),
            patch("apps.workload.services.scoped_snapshot.request_syllabus.SYLLABI", ()),
        ):
            result = collect_request_syllabus()
        self.assertEqual([row["id"] for row in result["request_syllabi"]], [source.pk])
        self.assertEqual([row["id"] for row in result["request_syllabus_shares"]], [share.pk])
        self.assertTrue(Syllabus.objects.filter(pk=unrelated.pk).exists())
        with (
            patch("apps.workload.services.scoped_snapshot.request_syllabus.ORG", self.foreign.pk),
            patch("apps.workload.services.scoped_snapshot.request_syllabus.OFFERINGS", (str(target.pk),)),
            patch("apps.workload.services.scoped_snapshot.request_syllabus.SYLLABI", (str(source.pk),)),
        ):
            self.assertTrue(all(not rows for rows in collect_request_syllabus().values()))
