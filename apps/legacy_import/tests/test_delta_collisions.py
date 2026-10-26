"""Fənn KODU toqquşması (magistr auditi, sahib 2026-10-26) — ``Catalog.subject_for`` + ``subject_collisions`` fazası.

Ssenari: legacy fənn 5 «Riyaziyyat», hədəfdə isə ``QKU-5`` kartı tapşırıq idxalının verdiyi BAŞQA fəndir
(«Başqa fənn»). Yoxlanılır: kod adı tutmursa jurnal yanlış karta yazılmır (ötürülür); faza delta-nın yaratdığı
yanlış açılışı (dərs + qeydiyyat sübutu ilə — DB qoruyucusu rəsmi icazə ilə keçilir) düzgün karta keçirir,
sillabus və dərs yükü sətri də keçir, xəritə yazılır, ikinci qaçış 0 yazı; əkiz rəsmi açılış varsa və ya açılış
delta-nın deyilsə — toxunulmur; dry-run heç nə yazmır; düzəlişdən sonra adi delta eyni açılışa yazır.
"""

import datetime as dt

from django.test import TestCase

from apps.audit.models import AuditLog
from apps.legacy_import.services.delta.apply import BATCH_RESOURCE, execute
from apps.legacy_import.services.delta.resolve import COLLISION_RESOURCE, Catalog
from apps.registrar.models import CourseOffering, Enrollment, Lesson, Subject
from apps.syllabus.models import Syllabus
from apps.workload.models import TeachingTask, TeachingTaskRow
from core.rls import bypass_rls

from . import test_delta_apply as base
from .test_delta_apply import UNTIL, _bundle

LEGACY = {"id": 5, "name": "Riyaziyyat", "lesson_code": "", "department_id": 3, "type": ""}


class DeltaSubjectCollisionTests(TestCase):
    setUpTestData = classmethod(base.DeltaApplyTests.setUpTestData.__func__)

    def setUp(self):
        with bypass_rls():
            self.wrong = Subject.objects.get(organization=self.org, code="QKU-5")
            self.wrong.name = "Başqa fənn"
            self.wrong.save(update_fields=["name"])

    def _run(self, *, apply, phases=("subject_collisions",), bundle=None):
        with bypass_rls():
            return execute(
                organization=self.org,
                actor=self.actor,
                bundle=bundle or _bundle(),
                apply=apply,
                until=UNTIL,
                tag="delta-collision-test",
                phases=phases,
            )

    def _wrong_offering(self, *, from_delta=True):
        """Delta-nın əvvəlki (səhv) tətbiqi: legacy jurnal «Başqa fənn» kartında — qeydiyyat, dərs, sillabus, yük."""

        with bypass_rls():
            offering = CourseOffering.objects.create(
                organization=self.org, subject=self.wrong, period=self.period, group=self.group, lesson_hours=45
            )
            Enrollment.objects.create(organization=self.org, student=self.existing, offering=offering)
            Lesson.objects.create(organization=self.org, offering=offering, date=dt.date(2026, 10, 6), hours=2)
            Syllabus.objects.create(
                organization=self.org, subject=self.wrong, offering=offering, period=self.period, chair_unit=self.chair
            )
            task = TeachingTask.objects.create(organization=self.org, chair=self.chair, academic_year="2026/2027")
            row = TeachingTaskRow.objects.create(
                organization=self.org,
                task=task,
                season="fall",
                period=self.period,
                subject=self.wrong,
                subject_text=self.wrong.name,
                specialty=self.specialty,
                total_hours=45,
            )
            row.groups.set([self.group])
            if from_delta:
                AuditLog.objects.create(
                    organization=self.org,
                    action="create",
                    resource_type=BATCH_RESOURCE,
                    resource_id="delta-old",
                    new_values={"created": {"offerings": [str(offering.pk)]}},
                )
        return offering, row

    def test_code_with_other_name_is_not_accepted(self):
        with bypass_rls():
            self.assertEqual(Catalog(self.org).subject_for(LEGACY), (None, "code_collision"))
            Subject.objects.filter(pk=self.wrong.pk).update(name="Riyaziyyat")
            self.assertEqual(Catalog(self.org).subject_for(LEGACY)[1], "code")
        run = self._run(apply=False, phases=("offerings",))
        self.assertEqual(run.counters["journal.subject_unresolved"], 0)

    def test_collision_journal_is_skipped_by_regular_phases(self):
        run = self._run(apply=True, phases=("offerings",))
        self.assertEqual(run.counters["subject.code_collision"], 1)
        self.assertEqual(run.counters["journal.subject_unresolved"], 1)
        with bypass_rls():
            self.assertFalse(CourseOffering.objects.filter(organization=self.org).exists())

    def test_dry_run_writes_nothing(self):
        offering, _row = self._wrong_offering()
        run = self._run(apply=False)
        self.assertEqual(run.counters["written.collision_offerings"], 1)
        with bypass_rls():
            offering.refresh_from_db()
            self.assertEqual(offering.subject_id, self.wrong.pk)
            self.assertFalse(Subject.objects.filter(organization=self.org, code="QKU-L5").exists())
            self.assertFalse(AuditLog.objects.filter(resource_type=COLLISION_RESOURCE).exists())

    def test_wrong_offering_moves_to_new_subject_and_rerun_is_noop(self):
        offering, row = self._wrong_offering()
        run = self._run(apply=True)
        for key in ("offerings", "syllabi", "load_rows", "mappings", "subjects"):
            self.assertEqual(run.counters[f"written.collision_{key}"], 1, key)
        with bypass_rls():
            target = Subject.objects.get(organization=self.org, code="QKU-L5")
            self.assertEqual((target.name, target.ects, target.chair_unit_id), ("Riyaziyyat", 5, None))
            offering.refresh_from_db()
            self.assertEqual(offering.subject_id, target.pk)
            self.assertEqual(Lesson.objects.filter(offering=offering).count(), 1, "dərslər açılışla qalır")
            self.assertEqual(Syllabus.objects.get(offering=offering).subject_id, target.pk)
            row.refresh_from_db()
            self.assertEqual((row.subject_id, row.subject_text), (target.pk, "Riyaziyyat"))
            self.assertTrue(AuditLog.objects.filter(object_id=str(offering.pk), reason__contains="toqquşması").exists())
            self.assertEqual(Catalog(self.org).subject_for(LEGACY), (target, "collision_fixed"))

        again = self._run(apply=True)
        self.assertFalse([key for key in again.counters if key.startswith("written.")])
        self.assertEqual(again.counters["collision.no_wrong_offering"], 1)

        regular = self._run(apply=True, phases=base_phases())
        self.assertEqual(regular.counters["offering.existing"], 1, "düzəlişdən sonra delta eyni açılışa yazır")
        with bypass_rls():
            self.assertEqual(CourseOffering.objects.filter(organization=self.org, group=self.group).count(), 1)

    def test_existing_same_name_subject_is_reused(self):
        offering, _row = self._wrong_offering()
        with bypass_rls():
            target = Subject.objects.create(organization=self.org, code="TAP-1", name="Riyaziyyat")
        run = self._run(apply=True)
        self.assertNotIn("written.collision_subjects", run.counters)
        with bypass_rls():
            offering.refresh_from_db()
            self.assertEqual(offering.subject_id, target.pk)

    def test_twin_official_offering_is_left_for_owner_decision(self):
        offering, row = self._wrong_offering()
        with bypass_rls():
            target = Subject.objects.create(organization=self.org, code="TAP-1", name="Riyaziyyat")
            CourseOffering.objects.create(organization=self.org, subject=target, period=self.period, group=self.group)
        run = self._run(apply=True)
        self.assertEqual(run.counters["collision.twin_exists"], 1)
        self.assertEqual(run.counters["collision.twin_wrong_load_row"], 1)
        self.assertFalse([key for key in run.counters if key.startswith("written.")])
        with bypass_rls():
            offering.refresh_from_db()
            self.assertEqual(offering.subject_id, self.wrong.pk)
            self.assertEqual(Catalog(self.org).subject_for(LEGACY), (None, "code_collision"))

    def test_offering_not_created_by_delta_is_untouched(self):
        offering, _row = self._wrong_offering(from_delta=False)
        run = self._run(apply=True)
        self.assertEqual(run.counters["collision.offering_not_from_delta"], 1)
        self.assertFalse([key for key in run.counters if key.startswith("written.")])
        with bypass_rls():
            offering.refresh_from_db()
            self.assertEqual(offering.subject_id, self.wrong.pk)


def base_phases():
    from apps.legacy_import.services.delta.apply import DEFAULT_PHASES

    return tuple(phase for phase in DEFAULT_PHASES if phase != "workload")
