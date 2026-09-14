"""Dalğa 2 (2026-09-14) — audit 2026-09-13 backend F-06 qalıqları: davamiyyət
həddinin QALAN dörd çağıranı da ``registrar.absence_limit`` üzərindən tələbənin
ÖZ proqramını oxuyur:

* ``finals.compute_final_result`` — tək yol (``batch=None``) və toplu yol;
* ``finals_batch.FinalsBatch.limit_percent_for_enrollment``;
* ``journal_extras.get_final_breakdown`` («Yekun» tabı) sətirləri;
* ``gradebook.get_offering_journal`` (müəllim qridi) sətirləri.

Parity: proqram həddi açılışın İLK tələbəsindən (25 %) fərqli olan qonaq tələbə
(10 %) üçün dörd səth + imtahan qapısı + kabinet EYNİ həddi və EYNİ qərarı verir.
Sorğu büdcəsi sətir sayından asılı deyil (1 və 3 qonaq → eyni sorğu sayı).
"""

from __future__ import annotations

from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.registrar import absence_limit, exam_bridge, finals, finals_batch, gradebook, guest_roster, journal_extras
from apps.registrar.models import Curriculum, Program, StudentAcademicRecord
from apps.registrar.tests.test_guest_roster import _GuestRosterBase
from core.rls import bypass_rls


class AbsenceLimitParityTest(_GuestRosterBase):
    def _strict_program(self):
        program = Program.objects.create(organization=self.org, code="STRICT", name="Strict", absence_limit_percent=10)
        curriculum = Curriculum.objects.create(organization=self.org, program=program, admission_year=2025)
        return program, curriculum

    def _guest_with_strict_program(self, student=None, *, program=None, curriculum=None, absence_hours=5):
        student = student or self.guest
        with bypass_rls():
            if program is None:
                program, curriculum = self._strict_program()
            record = StudentAcademicRecord.objects.get(student=student, organization=self.org)
            record.program = program
            record.curriculum = curriculum
            record.save(update_fields=["program", "curriculum"])
            self._drop_own_history(student)
            enrollment = guest_roster.add_guest_student(
                offering=self.offering, student=student, by_user=self.coordinator, reason="F-06 w2"
            )
            offering = enrollment.offering
            offering.lesson_hours = 30  # 30 saat: 10 % → 3 saat, 25 % → 7.5 saat
            offering.save(update_fields=["lesson_hours"])
            enrollment.absence_hours = absence_hours
            enrollment.save(update_fields=["absence_hours"])
        return record, enrollment

    def test_all_surfaces_agree_for_guest_student(self):
        record, enrollment = self._guest_with_strict_program()
        with bypass_rls():
            # Açılış-səviyyəli (qrupun ilk tələbəsi) hədd hələ də 25-dir — fərq məhz budur.
            self.assertEqual(absence_limit.limit_percent_for_offering(self.offering), 25)

            single = finals.compute_final_result(enrollment=enrollment)
            batch = finals_batch.build([enrollment])
            self.assertEqual(batch.limit_percent_for_enrollment(enrollment), 10)
            batched = finals.compute_final_result(enrollment=enrollment, batch=batch)
            results_row = next(
                row
                for row in finals.get_offering_results(offering=self.offering)["rows"]
                if row["enrollment"].id == enrollment.id
            )
            breakdown_row = next(
                row
                for row in journal_extras.get_final_breakdown(self.offering)["rows"]
                if row["enrollment"].id == enrollment.id
            )
            grid_row = next(
                row
                for row in gradebook.get_offering_journal(offering=self.offering)["rows"]
                if row["enrollment"].id == enrollment.id
            )
            gate = exam_bridge.exam_eligibility(student=self.guest, subject_id=self.history.pk, organization=self.org)

        for label, eligibility in (
            ("single", single["eligibility"]),
            ("batched", batched["eligibility"]),
            ("results", results_row["result"]["eligibility"]),
            ("breakdown", breakdown_row["eligibility"]),
            ("gate", gate),
        ):
            self.assertEqual(eligibility["limit_percent"], 10, label)
            self.assertTrue(eligibility["barred"], label)
        self.assertTrue(single["barred"] and batched["barred"])
        self.assertTrue(results_row["result"]["barred"] and breakdown_row["barred"])
        # Müəllim qridi qayıbı `Enrollment.absence_hours`-dan yox, işarələrdən sayır (bu testdə
        # işarə yoxdur) — burada hədd və sətrin ÖZ icazəli saatı yoxlanır: 3 (10 % × 30),
        # başlıq isə açılış-səviyyəli 7.5 qalır.
        self.assertEqual(grid_row["eligibility"]["limit_percent"], 10)
        self.assertEqual(grid_row["allowed_absence"], 3)
        self.assertEqual(breakdown_row["allowed_absence"], 3)

    def test_host_student_keeps_the_offering_limit(self):
        """Ev sahibi (25 %) 5 saat qayıbla BURAXILIR — qonağın sərt həddi ona sirayət etmir."""
        self._guest_with_strict_program()
        with bypass_rls():
            host_enrollment = self.host.enrollments.get(offering=self.offering)
            host_enrollment.absence_hours = 5
            host_enrollment.save(update_fields=["absence_hours"])
            result = finals.compute_final_result(enrollment=host_enrollment)
            grid_row = next(
                row
                for row in gradebook.get_offering_journal(offering=self.offering)["rows"]
                if row["enrollment"].id == host_enrollment.id
            )
        self.assertEqual(result["eligibility"]["limit_percent"], 25)
        self.assertFalse(result["barred"])
        self.assertFalse(grid_row["barred"])

    def test_query_budget_is_independent_of_row_count(self):
        program, curriculum = None, None
        with bypass_rls():
            program, curriculum = self._strict_program()
        self._guest_with_strict_program(program=program, curriculum=curriculum)

        def _count():
            with bypass_rls(), CaptureQueriesContext(connection) as captured:
                gradebook.get_offering_journal(offering=self.offering)
                journal_extras.get_final_breakdown(self.offering)
                finals.get_offering_results(offering=self.offering)
            return len(captured)

        _count()  # isinmə: ilk çağırış sxem/keş kimi birdəfəlik sətirləri yaradır
        one_guest = _count()
        with bypass_rls():
            for name in ("gr_w2_g2", "gr_w2_g3"):
                extra = self._make_student(name, self.group2)
                self._guest_with_strict_program(extra, program=program, curriculum=curriculum)
        three_guests = _count()
        self.assertEqual(one_guest, three_guests)
