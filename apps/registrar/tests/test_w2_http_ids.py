"""Dalğa 2 (2026-09-14) — audit 2026-09-13 backend F-01 (qalan yerlər): POST-dan
gələn qeyri-UUID pk `core.http_ids.parse_uuid` ilə çevrilir → 404 / validasiya
mesajı (əvvəl `ValidationError` → 500).

* `registrar:correction_apply` / `correction_delete` (`mark_id`, `lesson_id`, …);
* `registrar:journal_action` `delete_topic` (`topic_id`).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import services
from apps.registrar.models import CorrectionReason, Enrollment, Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class _Base(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("w2hid_owner", "w2hid_owner@qku.edu.az", "pw")
        with bypass_rls():
            self.org = Organization.objects.create(
                name="W2 Ids Univ",
                slug="w2-ids-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=self.owner,
                status="active",
                is_active=True,
            )
            group = OrgUnit.objects.create(
                organization=self.org, name="G1", slug="w2hid-g1", unit_type=OrgUnitType.GROUP
            )
            period = AcademicPeriod.objects.create(
                organization=self.org,
                name="2024/2025 Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date="2024-09-01",
                end_date="2025-01-31",
                is_current=True,
            )
            subject = Subject.objects.create(organization=self.org, code="W2ID", name="Dalğa 2")
            # RİM rəhbəri həm korrektor (`journal.correct`), həm də instruktor (`grade.*`).
            self.rim = User.objects.create_user("w2hid_rim", "w2hid_rim@qku.edu.az", "pw")
            Membership.objects.create(
                user=self.rim, organization=self.org, role=self.org.roles.get(name="ikt_rehber"), is_primary=True
            )
            self.offering = services.get_or_create_offering(
                organization=self.org, subject=subject, period=period, group=group
            )
            self.offering.instructor = self.rim
            self.offering.save(update_fields=["instructor"])
            student = User.objects.create_user("w2hid_student", "w2hid_student@qku.edu.az", "pw")
            Membership.objects.create(
                user=student, organization=self.org, role=self.org.roles.get(name="student"), is_primary=True
            )
            self.enrollment = Enrollment.objects.create(organization=self.org, student=student, offering=self.offering)
        self.client = Client()
        self.client.force_login(self.rim)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()


class CorrectionViewsBadPkTest(_Base):
    def test_apply_with_bad_mark_id_is_404_not_500(self):
        response = self.client.post(
            reverse("registrar:correction_apply", args=[self.offering.id]),
            {"target": "grade", "mark_id": "abc", "field": "attendance", "reason": CorrectionReason.MEDICAL},
        )
        self.assertEqual(response.status_code, 404)

    def test_apply_with_bad_lesson_id_is_404(self):
        response = self.client.post(
            reverse("registrar:correction_apply", args=[self.offering.id]),
            {"target": "grade", "lesson_id": "abc", "enrollment_id": str(self.enrollment.id), "field": "attendance"},
        )
        self.assertEqual(response.status_code, 404)

    def test_item_apply_with_bad_component_id_is_404(self):
        response = self.client.post(
            reverse("registrar:correction_apply", args=[self.offering.id]),
            {"target": "component", "component_id": "abc", "enrollment_id": str(self.enrollment.id)},
        )
        self.assertEqual(response.status_code, 404)

    def test_delete_with_bad_correction_id_is_a_validation_message(self):
        response = self.client.post(
            reverse("registrar:correction_delete", args=[self.offering.id]),
            {"type": "grade", "correction_id": "abc", "mark_id": "abc"},
        )
        self.assertIn(response.status_code, (302, 400))
        self.assertNotEqual(response.status_code, 500)

    def test_delete_lesson_with_bad_lesson_id_is_404(self):
        response = self.client.post(
            reverse("registrar:correction_delete", args=[self.offering.id]),
            {"type": "lesson", "correction_id": "11111111-1111-1111-1111-111111111111", "lesson_id": "abc"},
        )
        self.assertEqual(response.status_code, 404)


class JournalActionBadPkTest(_Base):
    def test_delete_topic_with_bad_topic_id_is_404(self):
        response = self.client.post(
            reverse("registrar:journal_selfwork_action", args=[self.offering.id]),
            {"action": "delete_topic", "topic_id": "abc"},
        )
        self.assertEqual(response.status_code, 404)
