"""Sahib 2026-11-16 «indi et»: qalan midterm iştirakçıları — «eyni fənn» kart cütü və alt qrup qaydası.

* Kart cütü (``--alias A=B``): tələbə fənni BAŞQA kartda oxuyur → balı o jurnala yazılır, sonrakı yenidən
  sinxron «köhnə bağlantı» kimi silmir.
* ``--subgroup-exams``: qrupunda fənnin jurnalı YOXDUR → fənnin mövcud jurnalına alt qrup tələbəsi kimi + bal.
"""

from __future__ import annotations

from decimal import Decimal
from io import StringIO

from django.core.management import call_command

from apps.exams.services import exam_journal_link
from apps.exams.tests.test_exam_results_audit_2026_11_16 import _AuditSetup
from apps.organizations.models import Organization, OrgUnit
from apps.registrar import exam_journal_scope
from apps.registrar.models import ComponentScore, CourseOffering, Enrollment, Subject
from core.constants import OrgUnitType
from core.rls import bypass_rls


class OwnerRulesTests(_AuditSetup):
    def _place(self, *args):
        out = StringIO()
        call_command(
            "place_midterm_takers_20261116", "--org", self.org.slug, "--actor", self.owner.username, *args, stdout=out
        )
        return out.getvalue()

    def test_alias_pair_writes_into_the_card_the_student_studies_and_survives_resync(self):
        with bypass_rls():
            other = Subject.objects.create(
                organization=self.org, code="IT-845", name="İnformasiya texnologiyaları (ixt)"
            )
        exam, options = self._exam_for([self.group], title="Alias")
        with bypass_rls():
            exam.subject = other
            exam.save(update_fields=["subject"])
            exam_journal_link.refresh_links(exam)
        self._finish(exam, options, correct=2)
        out = self._place()
        self.assertIn("status_no_enrollment=1", out)

        out = self._place("--alias", f"IT-845={self.subject.code}")
        self.assertIn("alias_added=1", out)
        self.assertIn("status_written=1", out)
        with bypass_rls():
            self.assertEqual(exam_journal_scope.alias_pairs(Organization.objects.get(pk=self.org.pk)), [])
            self.assertFalse(ComponentScore.objects.filter(enrollment=self.enrollment).exists())

        out = self._place("--alias", f"IT-845={self.subject.code}", "--apply")
        self.assertIn("status_written=1", out)
        self.assertEqual(self._score_in(self.offering, self.enrollment).score, Decimal("20"))
        with bypass_rls():
            fresh = _reload_exam(exam)
            exam_journal_link.resync_exam_journal(fresh, notify=False)
        self.assertEqual(self._score_in(self.offering, self.enrollment).score, Decimal("20"))
        self.assertIn("status_unchanged=1", self._place())

    def test_bad_alias_code_is_rejected(self):
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            self._place("--alias", "NOPE-1=NOPE-2")

    def test_subgroup_exam_places_taker_into_the_subject_journal(self):
        with bypass_rls():
            lonely = OrgUnit.objects.create(
                organization=self.org, name="334T1", slug="own-334t1", unit_type=OrgUnitType.GROUP
            )
        exam, options = self._exam_for([lonely], title="Sub")
        taker = self._new_student("own_taker", lonely)
        self._attempt_by(taker, exam, options, correct=3)
        out = self._place()
        self.assertIn("skip_no_journal=1", out)

        out = self._place("--subgroup-exams", str(exam.pk), "--apply")
        self.assertIn("subgroup_host=1", out)
        self.assertIn(f"host exam={exam.pk} offering={self.offering.pk} n=1", out)
        with bypass_rls():
            row = Enrollment.objects.get(offering=self.offering, student=taker, status="enrolled")
            self.assertFalse(CourseOffering.objects.filter(group=lonely).exists())
        self.assertEqual(self._score_in(self.offering, row).score, Decimal("30"))


def _reload_exam(exam):
    from apps.exams.models import Exam

    return Exam.objects.select_related("organization").get(pk=exam.pk)
