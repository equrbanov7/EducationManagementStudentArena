"""Journal labels use academic home groups, never physical level cohorts."""

from django.template.loader import render_to_string

from apps.registrar import gradebook
from apps.registrar.journal_home_groups import home_group_map
from apps.registrar.models import Curriculum, Enrollment, Program, StudentAcademicRecord
from apps.registrar.tests.test_guest_roster import _GuestRosterBase
from core.rls import bypass_rls


class JournalHomeGroupTests(_GuestRosterBase):
    def test_mixed_level_journal_uses_home_record_without_guest_provenance(self):
        with bypass_rls():
            self.offering.subject.name = "Xarici dil (Elementary)"
            self.offering.subject.save(update_fields=["name"])
            enrollment = Enrollment.objects.create(organization=self.org, offering=self.offering, student=self.guest)
            journal = gradebook.get_offering_journal(offering=self.offering)
        row = next(row for row in journal["rows"] if row["enrollment"].pk == enrollment.pk)
        self.assertIsNone(row["source_group"])
        self.assertEqual(row["home_group"].pk, self.group2.pk)
        self.assertNotEqual(row["home_group"].pk, self.offering.group_id)
        html = render_to_string("registrar/partials/_jd_grid.html", {"journal": journal, "offering": self.offering})
        self.assertIn(self.group2.name, html)

    def test_missing_inactive_or_foreign_record_never_falls_back_to_offering(self):
        with bypass_rls():
            StudentAcademicRecord.objects.filter(organization=self.org, student=self.host).update(is_active=False)
            journal = gradebook.get_offering_journal(offering=self.offering)
            self.assertIsNone(next(row for row in journal["rows"] if row["student"].pk == self.host.pk)["home_group"])
            self.assertEqual(
                home_group_map(organization_id=self.org.pk, student_ids=[self.far_student.pk]),
                {self.far_student.pk: self.far_group},
            )
            self.assertEqual(
                home_group_map(organization_id="00000000-0000-0000-0000-000000000001", student_ids=[self.guest.pk]),
                {},
            )

    def test_ambiguous_home_group_is_unknown_and_single_batch_query(self):
        with bypass_rls():
            program = Program.objects.create(organization=self.org, code="SECOND", name="Second")
            curriculum = Curriculum.objects.create(organization=self.org, program=program, admission_year=2025)
            StudentAcademicRecord.objects.create(
                organization=self.org,
                student=self.host,
                program=program,
                curriculum=curriculum,
                group=self.group2,
                admission_year=2025,
            )
            with self.assertNumQueries(1):
                groups = home_group_map(organization_id=self.org.pk, student_ids=[self.host.pk, self.guest.pk])
            self.assertNotIn(self.host.pk, groups)
            self.assertEqual(groups[self.guest.pk], self.group2)

    def test_joint_template_keeps_home_group_not_physical_group(self):
        html = render_to_string(
            "registrar/joint_journal.html",
            {
                "rows": [{"group": self.group1, "home_group": self.group2, "student": self.guest, "cells": []}],
                "columns": [],
            },
        )
        self.assertInHTML(f'<span class="joint-student-group" title="Əsas qrup">{self.group2.name}</span>', html)
        self.assertNotInHTML(f'<span class="joint-student-group" title="Əsas qrup">{self.group1.name}</span>', html)
        self.assertInHTML(f'<span class="joint-home-group">Jurnal qrupu: {self.group1.name}</span>', html)

    def test_joint_template_unknown_home_never_claims_physical_cohort_as_home(self):
        html = render_to_string(
            "registrar/joint_journal.html",
            {"rows": [{"group": self.group1, "home_group": None, "student": self.guest, "cells": []}], "columns": []},
        )
        self.assertInHTML('<span class="joint-student-group" title="Əsas qrup">—</span>', html)
        self.assertNotInHTML(f'<span class="joint-student-group" title="Əsas qrup">{self.group1.name}</span>', html)
        self.assertInHTML(f'<span class="joint-home-group">Jurnal qrupu: {self.group1.name}</span>', html)
