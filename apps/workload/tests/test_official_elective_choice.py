"""Tapşırıqdakı RƏSMİ seçmə blok seçimi = qrupun seçimi (2026-10-15).

Yoxlanılır: blok mətni + seçilmiş fənn → qrupun ``GroupElectiveChoice`` qərarı yazılır,
açılış yaranır, qrup ``elective`` kimi yazılır; qrupun həmin blok üçün BAŞQA qərarı
əzilmir (``elective_choice_conflict``); planın blokunda olmayan fənn məcburi kimi açılır
(``elective_from_task``); blok mətni olmayan seçmə sətir gözləyir; ``resync_task_offerings``
əmri dry-run-da heç nə yazmır, apply-da idempotentdir.
"""

from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.utils import timezone

from apps.registrar.models import CurriculumSubject, Enrollment, GroupElectiveChoice, Subject
from apps.workload.constants import TaskStatus
from apps.workload.models import TeachingTaskRow
from apps.workload.services.offering_sync import sync_task_offerings

from .factories import make_row, make_task
from .test_plan_offerings import PlanOfferingBase, User

BLOCK_TEXT = "ATMF IX blok: 1.Fotosintez 2.Virusologiya 3.Parazitologiya"
BLOCK = "ATMF IX"


class _ElectiveBase(PlanOfferingBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.curriculum.status = "approved"
        cls.curriculum.save(update_fields=["status"])
        cls.virus = Subject.objects.create(organization=cls.org, code=f"{cls.code}-VIR", name="Virusologiya", ects=4)
        cls.photo = Subject.objects.create(organization=cls.org, code=f"{cls.code}-FOT", name="Fotosintez", ects=4)
        for subject in (cls.photo, cls.virus):
            CurriculumSubject.objects.create(
                organization=cls.org,
                curriculum=cls.curriculum,
                subject=subject,
                semester_number=3,
                is_elective=True,
                elective_group=BLOCK,
            )

    def block_row(self, task, subject, *, text=BLOCK_TEXT):
        row = make_row(task, {**self.stack, "subject": subject}, lecture_total=30, seminar_total=0)
        TeachingTaskRow.objects.filter(pk=row.pk).update(subject_text=text)
        return row

    def choice(self):
        return GroupElectiveChoice.objects.filter(
            organization=self.org, group=self.stack["group"], period=self.stack["period"], elective_group=BLOCK
        ).first()


class OfficialBlockChoiceTest(_ElectiveBase):
    code = "OEC"

    def test_block_row_records_group_choice_opens_offering_and_enrolls_group(self):
        task, _row = self.office_task()
        self.block_row(task, self.virus)
        result = self.approve(task)["offerings"]

        offering = self.offerings(subject=self.virus).get()
        self.assertEqual(offering.group_id, self.stack["group"].pk)
        choice = self.choice()
        self.assertIsNotNone(choice)
        self.assertEqual(choice.chosen_subject_id, self.virus.pk)
        enrollment = Enrollment.objects.get(offering=offering, student=self.student)
        self.assertEqual(enrollment.kind, "elective")
        # Aktiv üzvlüyü olmayan qrup üzvü ötürülür — qrupun qərarı bütövlükdə dayanmır.
        self.assertFalse(Enrollment.objects.filter(offering=offering, student=self.no_member).exists())
        self.assertFalse(self.offerings(subject=self.photo).exists())
        self.assertEqual(result.get("elective_from_task", 0), 1)
        self.assertEqual(result.get("elective_choice_recorded", 0), 1)
        self.assertEqual(result.get("elective_pending", 0), 0)

        again = sync_task_offerings(task, actor=self.actor(self.dean))
        self.assertEqual((again["created"], again["enrolled"], again["elective_choice_recorded"]), (0, 0, 0))
        self.assertEqual(GroupElectiveChoice.objects.filter(organization=self.org).count(), 1)

    def test_existing_different_group_choice_is_not_overridden(self):
        GroupElectiveChoice.objects.create(
            organization=self.org,
            group=self.stack["group"],
            period=self.stack["period"],
            elective_group=BLOCK,
            chosen_subject=self.photo,
        )
        task, _row = self.office_task()
        self.block_row(task, self.virus)
        result = self.approve(task)["offerings"]

        self.assertFalse(self.offerings(subject=self.virus).exists())
        self.assertEqual(self.choice().chosen_subject_id, self.photo.pk)
        self.assertEqual(result.get("elective_choice_conflict", 0), 1)
        self.assertEqual(result.get("elective_from_task", 0), 0)

    def test_free_elective_row_without_block_text_stays_pending(self):
        task, _row = self.office_task()
        self.block_row(task, self.virus, text="")
        result = self.approve(task)["offerings"]

        self.assertFalse(self.offerings(subject=self.virus).exists())
        self.assertIsNone(self.choice())
        self.assertEqual(result.get("elective_pending", 0), 1)

    def test_block_subject_outside_curriculum_block_opens_like_mandatory(self):
        other = Subject.objects.create(organization=self.org, code="OEC-PAR", name="Parazitologiya", ects=4)
        task, _row = self.office_task()
        self.block_row(task, other)
        result = self.approve(task)["offerings"]

        offering = self.offerings(subject=other).get()
        self.assertEqual(Enrollment.objects.get(offering=offering, student=self.student).kind, "mandatory")
        self.assertIsNone(self.choice())
        self.assertEqual(result.get("elective_from_task", 0), 1)
        self.assertEqual(result.get("elective_choice_recorded", 0), 0)


class ResyncCommandTest(_ElectiveBase):
    code = "OER"

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.superuser = User.objects.create_superuser("oer.root", "oer.root@x.test", "pw")

    def _run(self, *extra):
        out = StringIO()
        call_command(
            "resync_task_offerings",
            "--org",
            self.org.slug,
            "--year",
            "2026/2027",
            "--chair",
            self.stack["chair"].name,
            "--actor",
            self.superuser.username,
            *extra,
            stdout=out,
        )
        return out.getvalue()

    def _distributed_task(self):
        # Kafedraya çatmış, açılışları hələ yaranmamış sənəd (köhnə sinxronun «gözləyən» halı).
        task = make_task(self.org, self.stack["chair"], status=TaskStatus.DISTRIBUTED, created_by=self.office)
        task.submitted_at = timezone.now()
        task.save(update_fields=["submitted_at"])
        make_row(task, self.stack)
        self.block_row(task, self.virus)
        return task

    def test_dry_run_writes_nothing_and_apply_is_idempotent(self):
        self._distributed_task()
        dry = self._run()
        self.assertIn("DRY-RUN", dry)
        self.assertIn("created=2", dry)
        self.assertIn("elective_from_task=1", dry)
        self.assertFalse(self.offerings().exists())
        self.assertIsNone(self.choice())
        self.assertFalse(Enrollment.objects.filter(organization=self.org).exists())

        first = self._run("--apply")
        self.assertIn("APPLY", first)
        self.assertIn("created=2", first)
        self.assertIn("enrollments_created=2", first)
        self.assertEqual(self.offerings().count(), 2)
        self.assertEqual(self.choice().chosen_subject_id, self.virus.pk)

        second = self._run("--apply")
        self.assertIn("created=0", second)
        self.assertIn("elective_from_task=0", second)
        self.assertIn("enrollments_created=0", second)
        self.assertEqual(self.offerings().count(), 2)
        self.assertEqual(Enrollment.objects.filter(organization=self.org).count(), 2)

    def test_non_superuser_actor_is_rejected(self):
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            call_command(
                "resync_task_offerings",
                "--org",
                self.org.slug,
                "--year",
                "2026/2027",
                "--all-chairs",
                "--actor",
                self.office.username,
                stdout=StringIO(),
            )
