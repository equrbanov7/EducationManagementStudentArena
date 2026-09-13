"""Backend auditi 2026-09-13 — registrar tapıntıları.

* F-01: ``registrar:schedule`` slot əlavəsi ``offering_id="abc"`` ilə 500 verirdi
  (auditor probu ``MalformedInputProbesExtra::test_m21``) → indi 404.
* F-06: davamiyyət həddi iki mənbədən həll olunurdu — imtahan START QAPISI
  (``exam_bridge.exam_eligibility`` / ``exam_eligibility_batch``) açılış
  qrupunun İLK akademik qeydinin proqramını, kabinet isə tələbənin ÖZ
  proqramını götürürdü (auditor reprosu ``AttendanceLimitSourceProbe``:
  gate=25, cabinet=10). İndi hər ikisi ``registrar.absence_limit`` üzərindən
  tələbənin öz qeydini oxuyur.
"""

from __future__ import annotations

from django.test import RequestFactory
from django.urls import reverse

from apps.registrar import absence_limit, exam_bridge, guest_roster, services
from apps.registrar.models import Curriculum, Program, StudentAcademicRecord
from apps.registrar.tests.test_guest_roster import _GuestRosterBase
from core.rls import bypass_rls


class ScheduleAddSlotNonUuidTest(_GuestRosterBase):
    def test_add_slot_with_non_uuid_offering_is_404_not_500(self):
        client = self._client(self.owner)
        response = client.post(reverse("registrar:schedule"), {"offering_id": "abc", "weekday": "1", "start": "09:00"})
        self.assertEqual(response.status_code, 404)

    def test_add_slot_with_unknown_uuid_is_still_404(self):
        client = self._client(self.owner)
        response = client.post(
            reverse("registrar:schedule"),
            {"offering_id": "00000000-0000-0000-0000-000000000001", "weekday": "1", "start": "09:00"},
        )
        self.assertEqual(response.status_code, 404)


class AbsenceLimitSingleSourceTest(_GuestRosterBase):
    """Qonaq tələbənin proqramı (10 %) açılış qrupunun proqramından (25 %) fərqlidir."""

    def _guest_with_strict_program(self):
        with bypass_rls():
            strict_program = Program.objects.create(
                organization=self.org, code="STRICT", name="Strict", absence_limit_percent=10
            )
            strict_curriculum = Curriculum.objects.create(
                organization=self.org, program=strict_program, admission_year=2025
            )
            record = StudentAcademicRecord.objects.get(student=self.guest, organization=self.org)
            record.program = strict_program
            record.curriculum = strict_curriculum
            record.save(update_fields=["program", "curriculum"])
            self._drop_own_history(self.guest)
            enrollment = guest_roster.add_guest_student(
                offering=self.offering, student=self.guest, by_user=self.coordinator, reason="F-06"
            )
            # 30 saat dərs, 5 saat qayıb: 10 % həddə (3 saat) KƏSİLİR, 25 % həddə (7.5) buraxılır.
            offering = enrollment.offering
            offering.lesson_hours = 30
            offering.save(update_fields=["lesson_hours"])
            enrollment.absence_hours = 5
            enrollment.save(update_fields=["absence_hours"])
        return record, enrollment

    def test_helper_reads_the_students_own_program(self):
        record, enrollment = self._guest_with_strict_program()
        with bypass_rls():
            self.assertEqual(absence_limit.limit_percent_for_record(record), 10)
            self.assertEqual(absence_limit.limit_percent_for_enrollment(enrollment), 10)
            self.assertEqual(
                absence_limit.limit_percent_for_student(organization_id=self.org.pk, student_id=self.guest.pk), 10
            )
            # Ev sahibi tələbə öz (25 %) proqramında qalır.
            host_enrollment = self.host.enrollments.get(offering=self.offering)
            self.assertEqual(absence_limit.limit_percent_for_enrollment(host_enrollment), 25)
        self.assertEqual(absence_limit.limit_percent_for_record(None), 25)

    def test_exam_gate_equals_cabinet_for_guest_student(self):
        record, enrollment = self._guest_with_strict_program()
        with bypass_rls():
            gate = exam_bridge.exam_eligibility(student=self.guest, subject_id=self.history.pk, organization=self.org)
            batch = exam_bridge.exam_eligibility_batch(
                student=self.guest, subject_ids={self.history.pk}, organization=self.org
            )[self.history.pk]
            cabinet = services.get_exam_eligibility(
                enrollment=enrollment, limit_percent=record.program.absence_limit_percent
            )
        self.assertTrue(gate["linked"])
        self.assertEqual(gate["limit_percent"], 10)
        self.assertEqual(batch["limit_percent"], 10)
        self.assertEqual(cabinet["limit_percent"], 10)
        # Qərar da eynidir: 5 saat qayıb 10 %-lik həddi aşır → hər üç səth «kəsilib».
        self.assertTrue(cabinet["barred"])
        self.assertTrue(gate["barred"])
        self.assertTrue(batch["barred"])

    def test_student_journal_detail_uses_own_program_limit(self):
        """``public.build_student_journal_context`` detalı da tələbənin öz həddi ilə hesablanır."""
        from apps.registrar.public import build_student_journal_context

        record, enrollment = self._guest_with_strict_program()
        request = RequestFactory().get("/", {"subject": str(enrollment.pk), "period": str(self.period.pk)})
        request.user = self.guest
        request.organization = self.org
        with bypass_rls():
            context = build_student_journal_context(request, organization=self.org)
        detail = context["journal_student_section"]["detail"]
        self.assertIsNotNone(detail)
        # 10 % həddə 5 saat qayıb → kəsilib (25 % həddə buraxılardı — köhnə davranış).
        self.assertTrue(detail["dav_barred"])
