"""Sahib 2026-10-23: final / midterm girişində istifadəçi adından əlavə E-POÇT da yazıla bilər.

* Fərdi (kabinet) PIN yolu: e-poçt (registr / boşluq / Unicode fərqi ilə) eyni tələbəni tapır.
* Bilet (zal oturumu) yolu: e-poçtla giriş tələbəni login edir.
* Bir dəyərin iki hesaba uyğun gəlməsini DB özü qadağan edir (``accounts_username_email_cross_collision``);
  ``find_login_user`` yenə də ikisini görsə heç kimi seçməz.
* Forma «İstifadəçi adı və ya e-poçt» yazır.
"""

from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from apps.exams.services.final_center import pins
from apps.exams.services.login_identity import canonical_login, find_login_user
from apps.exams.services.student_pins import provision_exam_student_pins, resolve_student_pin_login, student_visible_pin
from apps.exams.tests.test_final_center_flow import _FlowBase
from apps.exams.tests.test_student_pin_async_hashing_2026_10_06 import _OrgFixture

User = get_user_model()


class CanonicalLoginTests(SimpleTestCase):
    def test_trim_case_and_unicode(self):
        self.assertEqual(canonical_login("  Aysel.Q@Gmail.COM "), "aysel.q@gmail.com")
        self.assertEqual(canonical_login("ａｙｓｅｌ"), "aysel")  # tam enli Unicode (NFKC)


class PersonalPinEmailTests(_OrgFixture, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org, cls.teacher, cls.students = cls.make_org("emailpin")
        cls.exam = cls.make_final(cls.org, cls.teacher)
        cls.exam.allowed_users.add(cls.students[0])
        provision_exam_student_pins(cls.exam)
        User.objects.filter(pk=cls.students[0].pk).update(email="Aysel.Quliyeva@Gmail.com")

    def setUp(self):
        pins._verified_pins.clear()
        self.student = User.objects.get(pk=self.students[0].pk)

    def test_email_resolves_the_same_student(self):
        pin = student_visible_pin(self.exam, self.student)
        for typed in ("aysel.quliyeva@gmail.com", "  AYSEL.QULIYEVA@GMAIL.COM ", self.student.username):
            pins._verified_pins.clear()
            self.assertEqual(resolve_student_pin_login(typed, pin), (self.exam, self.student), typed)

    def test_wrong_pin_with_email_is_rejected(self):
        self.assertEqual(resolve_student_pin_login("aysel.quliyeva@gmail.com", "000000"), (None, None))

    def test_unknown_email_finds_nobody(self):
        self.assertIsNone(find_login_user("yoxdur@example.com"))


class TicketEntryEmailTests(_FlowBase):
    def test_ticket_holder_logs_in_with_email(self):
        User.objects.filter(pk=self.student.pk).update(email="ticket.student@example.com")
        client = Client()
        response = client.post(
            reverse("exams:final_exam_entry"), {"username": "Ticket.Student@Example.com", "pin": self.raw_pin}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(int(client.session["_auth_user_id"]), self.student.pk)

    def test_form_label_mentions_email(self):
        html = Client().get(reverse("exams:final_exam_entry")).content.decode()
        self.assertIn("İstifadəçi adı və ya e-poçt", html)
