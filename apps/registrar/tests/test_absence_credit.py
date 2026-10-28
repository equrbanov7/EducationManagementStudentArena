"""Ümumi üzrlü saatlar real qayıb/balları dəyişmədən bütün oxu yollarında işləyir."""

import uuid
from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import RequestFactory
from django.urls import reverse

from apps.registrar import absence_credit, gradebook, guest_merge
from apps.registrar.models import AbsenceCredit, CourseOffering, Enrollment, LessonMark
from apps.registrar.tests.test_corrections_bridge import _BaseJournalSetup
from core.rls import bypass_rls, journal_unlock


class AbsenceCreditTests(_BaseJournalSetup):
    def setUp(self):
        super().setUp()
        self.scope = bypass_rls()
        self.scope.__enter__()
        self.addCleanup(self.scope.__exit__, None, None, None)
        self.marks = [self._absent_lesson(day, hours=2)[1] for day in range(1, 7)]
        gradebook.recompute_absence_hours(enrollment=self.enrollment)

    def request(self, user=None):
        request = RequestFactory().post("/")
        request.user = user or self.admin
        request.organization = self.org
        return request

    def apply(self, hours=8, **kwargs):
        return absence_credit.adjust(
            request=kwargs.pop("request", self.request()),
            offering=self.offering,
            enrollment_id=self.enrollment.pk,
            hours=hours,
            reason=kwargs.pop("reason", "MR30 müəllimin təsdiq etdiyi ümumi üzrlü saat"),
            request_token=kwargs.pop("request_token", uuid.uuid4()),
            **kwargs,
        )

    def test_credit_preserves_six_absent_cells_and_all_canonical_read_paths(self):
        credit = self.apply()
        self.assertEqual((credit.old_absence_hours, credit.new_absence_hours), (12, 4))
        self.assertEqual(LessonMark.objects.filter(enrollment=self.enrollment, status="absent").count(), 6)
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.absence_hours, 4)
        self.assertEqual(gradebook.recompute_absence_hours(enrollment=self.enrollment), 4)
        row = gradebook.get_offering_journal(offering=self.offering)["rows"][0]
        self.assertEqual((row["absence_hours"], row["absence_count"], row["absence_credit_hours"]), (4, 6, 8))
        self.assertEqual(guest_merge.work_summary(self.enrollment)["absence_hours"], 4)

    def test_idempotent_retry_does_not_duplicate_and_reused_token_conflicts(self):
        token = uuid.uuid4()
        first = self.apply(request_token=token)
        self.assertEqual(self.apply(request_token=token).pk, first.pk)
        self.assertEqual(AbsenceCredit.objects.count(), 1)
        with self.assertRaises(absence_credit.CreditConflict):
            self.apply(hours=2, request_token=token)

    def test_bounds_validation_and_permission_denials_write_nothing(self):
        for value in (0, -1, 13, "1.5", "bad"):
            with self.assertRaises(ValidationError):
                self.apply(hours=value)
        with self.assertRaises(PermissionError):
            self.apply(request=self.request(self.teacher))
        foreign_request = self.request()
        foreign_request.organization = None
        with self.assertRaises(PermissionError):
            self.apply(request=foreign_request)
        self.assertEqual(AbsenceCredit.objects.count(), 0)

    def test_reverse_preserves_other_legitimate_credit_and_is_idempotent(self):
        first = self.apply()
        self.apply(hours=2, reason="İkinci müstəqil təsdiqli iki saat güzəşt")
        token = uuid.uuid4()
        reverse = self.apply(reverses_id=first.pk, request_token=token)
        self.assertEqual((reverse.old_absence_hours, reverse.new_absence_hours), (2, 10))
        self.assertEqual(self.apply(reverses_id=first.pk, request_token=token).pk, reverse.pk)
        with self.assertRaises(absence_credit.CreditConflict):
            self.apply(reverses_id=first.pk)
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.absence_hours, 10)

    def test_later_mark_changes_recompute_and_clamp_without_negative_hours(self):
        credit = self.apply()
        self._absent_lesson(8, hours=2)
        self.assertEqual(gradebook.recompute_absence_hours(enrollment=self.enrollment), 6)
        with journal_unlock():
            LessonMark.objects.filter(enrollment=self.enrollment).update(status="present")
        self.assertEqual(gradebook.recompute_absence_hours(enrollment=self.enrollment), 0)
        self.apply(reverses_id=credit.pk)
        self.assertEqual(gradebook.recompute_absence_hours(enrollment=self.enrollment), 0)

    def test_audit_failure_rolls_back_adjustment_and_cached_absence(self):
        with patch("apps.registrar.absence_credit.log_action", side_effect=RuntimeError("audit failed")):
            with self.assertRaises(RuntimeError):
                self.apply()
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.absence_hours, 12)
        self.assertEqual(AbsenceCredit.objects.count(), 0)

    def test_carried_credit_and_later_reversal_recompute_target_without_double_subtraction(self):
        from apps.organizations.models import OrgUnit

        group = OrgUnit.objects.create(organization=self.org, name="Other", slug="credit-other", unit_type="group")
        target_offering = CourseOffering.objects.create(
            organization=self.org, subject=self.subject, period=self.period, group=group, instructor=self.teacher
        )
        target = Enrollment.objects.create(
            organization=self.org, student=self.student, offering=target_offering, source_group=self.group
        )
        first = self.apply()
        self.enrollment.status = "dropped"
        self.enrollment.superseded_by = target
        self.enrollment.save(update_fields=["status", "superseded_by"])
        self.assertEqual(gradebook.recompute_absence_hours(enrollment=target), 4)
        credit = absence_credit.adjust(
            request=self.request(),
            offering=target_offering,
            enrollment_id=target.pk,
            hours=2,
            reason="Hədəf fəndə ayrıca iki saat güzəşt",
            request_token=uuid.uuid4(),
        )
        self.assertEqual(credit.new_absence_hours, 2)
        self.apply(reverses_id=first.pk)
        target.refresh_from_db()
        self.assertEqual(target.absence_hours, 10)
        self.assertEqual(gradebook.get_offering_journal(offering=target_offering)["rows"][0]["absence_hours"], 10)

    def test_legacy_reimport_keeps_credit_and_filters_other_tenants(self):
        from apps.legacy_import.services.rehearsal_journal_marks_targets import recompute_absence_hours

        self.apply()
        Enrollment.objects.filter(pk=self.enrollment.pk).update(absence_hours=99)
        count = recompute_absence_hours(SimpleNamespace(organization=self.org), [self.enrollment.pk])
        self.assertEqual(count, 1)
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.absence_hours, 4)
        self.assertEqual(recompute_absence_hours(SimpleNamespace(organization=None), [self.enrollment.pk]), 0)

    def test_source_cell_recompute_refreshes_merged_target_cache(self):
        from apps.organizations.models import OrgUnit

        group = OrgUnit.objects.create(organization=self.org, name="Other", slug="source-change", unit_type="group")
        offering = CourseOffering.objects.create(
            organization=self.org, subject=self.subject, period=self.period, group=group, instructor=self.teacher
        )
        target = Enrollment.objects.create(
            organization=self.org, student=self.student, offering=offering, source_group=self.group
        )
        self.apply()
        self.enrollment.status = "dropped"
        self.enrollment.superseded_by = target
        self.enrollment.save(update_fields=["status", "superseded_by"])
        gradebook.recompute_absence_hours(enrollment=self.enrollment)
        target.refresh_from_db()
        self.assertEqual(target.absence_hours, 4)
        self._absent_lesson(8, hours=2)
        gradebook.recompute_absence_hours(enrollment=self.enrollment)
        target.refresh_from_db()
        self.assertEqual(target.absence_hours, 6)
        with journal_unlock():
            LessonMark.objects.filter(enrollment=self.enrollment).update(status="present")
        gradebook.recompute_absence_hours(enrollment=self.enrollment)
        target.refresh_from_db()
        self.assertEqual(target.absence_hours, 0)

    def test_endpoint_and_actual_correction_form_use_existing_corrector_gate(self):
        self.client.force_login(self.admin)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()
        response = self.client.post(
            reverse("registrar:absence_credit_apply", args=[self.offering.pk]),
            {
                "enrollment": self.enrollment.pk,
                "hours": 8,
                "reason": "MR30 müəllimin ümumi saat təsdiqi",
                "request_token": uuid.uuid4(),
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["absence_hours"], 4)
        page = self.client.get(reverse("registrar:journal_detail", args=[self.offering.pk]) + "?correct=1")
        self.assertContains(page, 'name="request_token"')
        self.assertContains(page, 'name="hours"')
        self.client.force_login(self.student)
        denied = self.client.post(reverse("registrar:absence_credit_apply", args=[self.offering.pk]), {})
        self.assertEqual(denied.status_code, 404)
