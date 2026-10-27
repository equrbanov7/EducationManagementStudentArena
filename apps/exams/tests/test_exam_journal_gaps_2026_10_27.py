"""İmtahan qrupunun «jurnalı yoxdur» boşluğu — əkiz fənn kartı, səbəb təsnifatı, yalnız-doldurma əmri (2026-10-27).

Sahib: «bəzilərini deyir ki jurnalı yoxdur — o qrupların o hissəsini həll et». Bax
``apps/registrar/exam_journal_scope.py``, ``apps/registrar/exam_journal_gaps.py`` və
``apps/exams/management/commands/fix_exam_journal_gaps.py``.
"""

from __future__ import annotations

from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.exams.services import exam_journal_link, exam_unit_coverage
from apps.exams.tests.test_exam_journal_link_2026_10_24 import _LinkSetup
from apps.organizations.models import Membership, OrgUnit
from apps.registrar import exam_journal_gaps
from apps.registrar import exam_journal_link as registrar_link
from apps.registrar.models import CourseOffering, Enrollment, StudentAcademicRecord, Subject
from core.constants import OrgUnitType
from core.rls import bypass_rls


class _GapSetup(_LinkSetup):
    def _new_student(self, username, group):
        student = get_user_model().objects.create_user(username, f"{username}@qku.edu.az", "pw")
        with bypass_rls():
            Membership.objects.create(
                user=student, organization=self.org, role=self.org.roles.get(name="student"), is_active=True
            )
            StudentAcademicRecord.objects.create(
                organization=self.org,
                student=student,
                program=self.program,
                curriculum=self.curriculum,
                group=group,
                admission_year=2024,
            )
        return student

    def _twin(self):
        """Eyni fənnin ikinci kataloq kartı — ad yalnız registr / boşluqla fərqlənir (normallaşdırılmış açar eyni)."""
        with bypass_rls():
            return Subject.objects.create(organization=self.org, code="CS101-B", name="proqram laşdırma")

    def _classify(self, subject=None, groups=None):
        with bypass_rls():
            return exam_journal_gaps.classify(
                self.org, (subject or self.subject).pk, [g.pk for g in (groups or [self.group])]
            )


class TwinSubjectTests(_GapSetup):
    """Qrupun jurnalı dublikat fənn kartının altındadır — yoxlama, bağlantı və körpü onu tanıyır."""

    def test_twin_offering_counts_as_the_groups_journal_in_the_wizard_check(self):
        twin = self._twin()
        with bypass_rls():
            rows = exam_unit_coverage.coverage(self.org, twin.pk, [self.group])
        self.assertEqual((rows[0].total, rows[0].uncovered, rows[0].has_journal), (1, 0, True))

    def test_twin_offering_is_linked_and_midterm_lands_there(self):
        twin = self._twin()
        exam, options = self._exam(title="Twin")
        with bypass_rls():
            exam.subject = twin
            exam.save(update_fields=["subject"])
            exam.allowed_units.add(self.group)
            exam_journal_link.refresh_links(exam)
            self.assertEqual(list(exam.journal_offerings.all()), [self.offering])
        self._finish(exam, options, correct=3)
        self.assertEqual(self._score_in(self.offering, self.enrollment).score, Decimal("30"))
        with bypass_rls():
            exam.refresh_from_db()
            counts = exam_journal_link.resync_exam_journal(exam, notify=False)
        self.assertEqual(counts.get("cleared", 0), 0)  # bağlı əkiz jurnaldakı bal «köhnə» sayılmır
        self.assertEqual(self._score_in(self.offering, self.enrollment).score, Decimal("30"))

    def test_exact_subject_offering_wins_over_twin(self):
        twin = self._twin()
        with bypass_rls():
            twin_offering = CourseOffering.objects.create(
                organization=self.org, subject=twin, period=self.period, group=self.group
            )
            ids = registrar_link.link_offering_ids(self.org, subject_id=self.subject.pk, group_ids=[self.group.pk])
        self.assertEqual(ids, [self.offering.pk])
        self.assertNotIn(twin_offering.pk, ids)

    def test_similar_but_different_name_is_not_a_twin(self):
        with bypass_rls():
            other = Subject.objects.create(organization=self.org, code="CS102", name="Proqramlaşdırma-2")
            rows = exam_unit_coverage.coverage(self.org, other.pk, [self.group])
        self.assertEqual((rows[0].uncovered, rows[0].has_journal), (1, False))

    def test_variant_name_rule(self):
        self.assertTrue(exam_journal_gaps.is_variant_name("Azərbaycan tarixi", "Azərbaycanın tarixi"))
        self.assertFalse(exam_journal_gaps.is_variant_name("Xarici dil-1", "Xarici dil-2"))
        self.assertFalse(exam_journal_gaps.is_variant_name("VoİP sistemləri", "Vo İP sistemləri"))  # əkiz
        self.assertFalse(exam_journal_gaps.is_variant_name("Mülki müdafiə", "Əmək mühafizəsi"))


class ClassifyTests(_GapSetup):
    def test_late_student_is_a_roster_gap_and_fill_is_idempotent(self):
        late = self._new_student("gap_late", self.group)
        gap = self._classify()[self.group.pk]
        self.assertEqual((gap.students, gap.uncovered, gap.reason), (2, 1, exam_journal_gaps.ROSTER_GAP))
        self.assertEqual(gap.fill_offering_ids, {self.offering.pk})
        with bypass_rls():
            first = exam_journal_gaps.fill_rosters(gap.fill_offering_ids, by_user=self.center)
            second = exam_journal_gaps.fill_rosters(gap.fill_offering_ids, by_user=self.center)
            self.assertTrue(Enrollment.objects.filter(offering=self.offering, student=late, status="enrolled").exists())
        self.assertEqual(first["enroll_created"], 1)
        self.assertEqual(second.get("enroll_created", 0), 0)
        self.assertEqual(self._classify()[self.group.pk].uncovered, 0)

    def test_dropped_student_is_not_refilled(self):
        late = self._new_student("gap_dropped", self.group)
        with bypass_rls():
            Enrollment.objects.create(organization=self.org, student=late, offering=self.offering, status="dropped")
        gap = self._classify()[self.group.pk]
        self.assertEqual(gap.reasons[exam_journal_gaps.DROPPED], 1)
        self.assertEqual(gap.fill_offering_ids, set())

    def test_group_without_any_trace_is_no_journal_and_variant_is_reported(self):
        with bypass_rls():
            history = Subject.objects.create(organization=self.org, code="AZT", name="Azərbaycan tarixi")
            variant = Subject.objects.create(organization=self.org, code="AZT-2", name="Azərbaycanın tarixi")
        gap = self._classify(subject=history)[self.group.pk]
        self.assertEqual(gap.reason, exam_journal_gaps.NO_JOURNAL)
        with bypass_rls():
            offering = CourseOffering.objects.create(
                organization=self.org, subject=variant, period=self.period, group=self.group
            )
            Enrollment.objects.create(organization=self.org, student=self.student, offering=offering)
        gap = self._classify(subject=history)[self.group.pk]
        self.assertEqual((gap.reason, gap.variant_codes), (exam_journal_gaps.VARIANT_SUBJECT, {"AZT-2"}))

    def test_parent_group_student_with_subgroup_journal_is_unplaced(self):
        with bypass_rls():
            faculty = OrgUnit.objects.create(organization=self.org, name="Fak", slug="gap-fak", unit_type="faculty")
            parent = OrgUnit.objects.create(
                organization=self.org, name="536 MU", slug="gap-mu", unit_type=OrgUnitType.GROUP, parent=faculty
            )
            sub = OrgUnit.objects.create(
                organization=self.org, name="536 MU1", slug="gap-mu1", unit_type=OrgUnitType.GROUP, parent=faculty
            )
            CourseOffering.objects.create(organization=self.org, subject=self.subject, period=self.period, group=sub)
        self._new_student("gap_parent", parent)
        self._new_student("gap_sub", sub)
        gap = self._classify(groups=[parent])[parent.pk]
        self.assertEqual(gap.reasons[exam_journal_gaps.SUBGROUP_UNPLACED], 1)
        self.assertEqual(gap.reasons[exam_journal_gaps.ROSTER_GAP], 1)  # alt qrupun öz tələbəsi — doldurulur


class FixCommandTests(_GapSetup):
    def setUp(self):
        super().setUp()
        with bypass_rls():
            get_user_model().objects.filter(pk=self.owner.pk).update(is_superuser=True)

    def _run(self, *args):
        out = StringIO()
        call_command("fix_exam_journal_gaps", "--org", self.org.slug, "--actor", self.owner.username, *args, stdout=out)
        return out.getvalue()

    def _late_attempt(self):
        """Tələbə imtahanı verib, amma jurnalın siyahısında YOX idi (qrupa sonra gəlib) → bal düşməyib."""
        with bypass_rls():
            Enrollment.objects.filter(pk=self.enrollment.pk).delete()
        exam, options = self._exam(title="Late")
        with bypass_rls():
            exam.allowed_units.add(self.group)
            exam_journal_link.refresh_links(exam)
        self._finish(exam, options, correct=2)
        return exam

    def test_dry_run_apply_and_second_dry_run(self):
        exam = self._late_attempt()
        out = self._run("--exam", str(exam.pk))
        self.assertIn("DRY-RUN", out)
        self.assertIn("roster_gap=1", out)
        self.assertIn("enroll_created=1", out)
        self.assertNotIn(self.student.username, out)
        with bypass_rls():
            self.assertFalse(Enrollment.objects.filter(offering=self.offering, student=self.student).exists())
        out = self._run("--exam", exam.slug, "--apply")
        self.assertIn("APPLY", out)
        with bypass_rls():
            enrollment = Enrollment.objects.get(offering=self.offering, student=self.student, status="enrolled")
        self.assertEqual(self._score_in(self.offering, enrollment).score, Decimal("20"))
        again = self._run("--exam", str(exam.pk))
        self.assertIn("roster_gap=0", again)
        self.assertNotIn("enroll_created", again)

    def test_actor_must_be_superuser_and_exam_must_exist(self):
        with self.assertRaises(CommandError):
            call_command("fix_exam_journal_gaps", "--org", self.org.slug, "--actor", self.teacher.username)
        with self.assertRaises(CommandError):
            self._run("--exam", "no-such-exam")
