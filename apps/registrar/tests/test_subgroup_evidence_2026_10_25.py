"""«Alt qrup» nişanı yalnız SƏNƏDLİ yerləşdirməyə (sahib 2026-10-25: «Bilməsən yazma»).

Köçürmənin (legacy delta, rollup) ``source_group`` yazdığı, sənədsiz sətirlər — ana qrup / bölgü jurnalı — kabinetdə,
jurnal çipində və kredit bölgüsündə «alt qrup» SAYILMIR. Sənədli yerləşdirmə (modal sənədi və ya «Alt qrupa
yerləşdir» aləti) nişanı saxlayır. Eyni fənn dövrdə iki jurnalda olsa kredit bir dəfə sayılır.
"""

from __future__ import annotations

from django.test import TestCase

from apps.registrar import credit_load, gradebook
from apps.registrar.models import Enrollment
from apps.registrar.public import record_imported_placement
from apps.registrar.subgroup_evidence import documented_subgroup_ids
from apps.registrar.tests.subgroup_base import SubgroupFixture
from apps.registrar.tests.subgroup_evidence_fixture import attach_guest_document
from core.rls import bypass_rls


class SubgroupEvidenceTest(SubgroupFixture, TestCase):
    PREFIX = "sge"

    @classmethod
    def setUpTestData(cls):
        cls.build_world()

    def _import_guest(self):
        """Köçürmənin yazdığı kimi: ``source_group`` dolu, sənəd yoxdur, tarixçə ``via=import``."""
        with bypass_rls():
            enrollment = Enrollment.objects.create(
                organization=self.org, student=self.student, offering=self.physics_g1, source_group=self.group2
            )
            record_imported_placement(enrollment=enrollment, actor=self.dean, reason="Köhnə sistemdən köçürmə")
        return enrollment

    def _journal_row(self):
        with bypass_rls():
            journal = gradebook.get_offering_journal(offering=self.physics_g1)
        return {row["student"].id: row for row in journal["rows"]}[self.student.id]

    def test_imported_row_without_document_is_not_a_subgroup(self):
        enrollment = self._import_guest()
        with bypass_rls():
            self.assertEqual(documented_subgroup_ids([enrollment.pk]), set())
            load = credit_load.credit_load(self.student, self.period)
        self.assertNotIn(str(enrollment.pk), load["subgroup_enrollment_ids"])
        self.assertEqual(load["subgroup"], 0)
        self.assertFalse(self._journal_row()["is_guest"])

    def test_document_turns_the_badge_on(self):
        enrollment = self._import_guest()
        attach_guest_document(enrollment, self.dean)
        with bypass_rls():
            self.assertEqual(documented_subgroup_ids([enrollment.pk]), {enrollment.pk})
            load = credit_load.credit_load(self.student, self.period)
        self.assertIn(str(enrollment.pk), load["subgroup_enrollment_ids"])
        self.assertTrue(self._journal_row()["is_guest"])

    def test_same_subject_in_two_journals_counts_credit_once(self):
        with bypass_rls():
            before = credit_load.credit_load(self.student, self.period)["total"]
            # Tələbənin öz «Tarix» jurnalı var; eyni fənnin ana qrup jurnalına da yazılıb (mühazirə/seminar bölgüsü).
            Enrollment.objects.create(
                organization=self.org, student=self.student, offering=self.history_g1, source_group=self.group2
            )
            after = credit_load.credit_load(self.student, self.period)["total"]
        self.assertEqual(before, after)
