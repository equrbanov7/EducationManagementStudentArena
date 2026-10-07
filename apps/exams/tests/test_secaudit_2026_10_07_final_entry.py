"""Təhlükəsizlik auditi 2026-10-07, AUTH-03 — `/exams/final/` PIN girişi girişi bağlanmış hesabı buraxmır.

Final mərkəzi ``login(request, user, backend=...)`` ilə sessiya açır, yəni backend-in
``user_can_authenticate`` yoxlaması (``access_state`` staged/archived) bu yolda işləmir. PIN həlledicisi
yalnız ``is_active`` baxırdı, arxiv (məzun/xaric) hesabda isə ``is_active`` QƏSDƏN True qalır — belə hesab
həmin sorğu daxilində autentifikasiya olunub imtahan cəhdi aça bilirdi.
"""

from django.test import TestCase

from apps.accounts.models import UserProfile
from apps.exams.services.final_center import pins
from apps.exams.services.student_pins import provision_exam_student_pins, resolve_student_pin_login, student_visible_pin
from apps.exams.tests.test_final_center_flow import _FlowBase
from apps.exams.tests.test_student_pin_async_hashing_2026_10_06 import _OrgFixture


def _archive(user):
    UserProfile.objects.filter(user=user).update(access_state=UserProfile.AccessState.ARCHIVED)


class ArchivedStudentPinEntryTests(_OrgFixture, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org, cls.teacher, cls.students = cls.make_org("a3pin")
        cls.exam = cls.make_final(cls.org, cls.teacher)
        cls.exam.allowed_users.add(*cls.students[:2])
        provision_exam_student_pins(cls.exam)

    def setUp(self):
        pins._verified_pins.clear()
        self.active, self.archived = self.students[0], self.students[1]
        _archive(self.archived)

    def test_control_active_student_resolves(self):
        pin = student_visible_pin(self.exam, self.active)
        exam, student = resolve_student_pin_login(self.active.username, pin)
        self.assertEqual((exam, student), (self.exam, self.active))

    def test_archived_student_with_valid_pin_is_rejected(self):
        pin = student_visible_pin(self.exam, self.archived)
        self.assertTrue(pin)
        self.assertEqual(resolve_student_pin_login(self.archived.username, pin), (None, None))


class ArchivedStudentTicketEntryTests(_FlowBase):
    def test_control_active_ticket_holder_is_logged_in(self):
        client, response = self._entry_client()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(int(client.session["_auth_user_id"]), self.student.pk)

    def test_archived_ticket_holder_gets_no_session(self):
        _archive(self.student)
        client, response = self._entry_client()
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", client.session)
        self.assertNotIn("final_exam_ticket_id", client.session)
