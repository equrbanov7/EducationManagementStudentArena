"""Final girişi — hər sonluq düz BİR tam PIN-hash (tutum testi 2026-10-06).

Yük testi: 60 s-də 500 tələbə `/exams/final/` → 56 % xəta, PIN göndərişi 40 s.
Səbəb: bir giriş 3–4 PBKDF2 yandırırdı (bilet yolunun dummy hash-i + tələbənin
HƏR aktiv final PIN-i + ``can_user_start`` təkrarı). Testlər tam hash-ləri iki
səviyyədə sayır: ``check_password`` çağırışları (pins modulu) və konfiqurasiya
olunmuş hasher-in ``encode`` çağırışları (make_password daxil — hər real hash).
"""

from contextlib import contextmanager
from datetime import timedelta
from unittest import mock

from django.contrib.auth.hashers import MD5PasswordHasher, make_password
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.exams.models import Exam, ExamQuestion, ExamQuestionOption, ExamStudentPin, FinalExamTicket
from apps.exams.services.final_center import pins
from apps.exams.services.student_pins import resolve_student_pin_login
from apps.exams.tests.test_final_center_flow import _FlowBase

_ORIGINAL_ENCODE = MD5PasswordHasher.encode


class _HashCounter:
    def __init__(self, check_spy, encode_spy):
        self._check = check_spy
        self._encode = encode_spy

    @property
    def check_password_calls(self):
        return self._check.call_count

    @property
    def full_hashes(self):
        return self._encode.call_count


@contextmanager
def count_pin_hashes():
    """``check_password`` (pins) + hasher ``encode`` (hər real hash) sayğacı."""
    with (
        mock.patch.object(pins, "check_password", wraps=pins.check_password) as check_spy,
        mock.patch.object(MD5PasswordHasher, "encode", autospec=True, side_effect=_ORIGINAL_ENCODE) as encode_spy,
    ):
        yield _HashCounter(check_spy, encode_spy)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class FinalEntryHashBudgetTests(_FlowBase):
    PIN_A = "24681357"
    PIN_B = "97531864"

    def setUp(self):
        super().setUp()
        pins._verified_pins.clear()
        # Fərdi PIN yolu: bilet yoxdur, imtahan başlayıb.
        FinalExamTicket.objects.all().delete()
        Exam.objects.filter(pk=self.exam.pk).update(start_datetime=timezone.now() - timedelta(minutes=1))
        self.exam.refresh_from_db()
        self.pin_row = self._student_pin(self.exam, self.student, self.PIN_A)

    @staticmethod
    def _student_pin(exam, student, raw):
        return ExamStudentPin.objects.create(
            exam=exam,
            student=student,
            pin_hash=make_password(raw),
            pin_cipher=pins._fernet().encrypt(raw.encode()).decode(),
        )

    def _second_final(self):
        now = timezone.now()
        exam2 = Exam.objects.create(
            title="FCF Final 2",
            author=self.center,
            organization=self.org,
            exam_type="test",
            exam_type_extended="final",
            is_active=True,
            total_duration_minutes=60,
            random_question_count=1,
            start_datetime=now - timedelta(minutes=1),
            end_datetime=now + timedelta(hours=2),
        )
        question = ExamQuestion.objects.create(exam=exam2, order=1, text="İkinci final sualı")
        ExamQuestionOption.objects.create(question=question, label="A", text="Cavab", is_correct=True)
        return exam2

    def _post(self, username, pin):
        return Client().post(reverse("exams:final_exam_entry"), {"username": username, "pin": pin})

    def _assert_generic_failure(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", response.wsgi_request.session)

    # --- Fərdi PIN yolu -------------------------------------------------

    def test_success_costs_exactly_one_hash(self):
        with count_pin_hashes() as counter:
            response = self._post(self.student.username, self.PIN_A)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(int(response.wsgi_request.session["_auth_user_id"]), self.student.pk)
        self.assertEqual(counter.full_hashes, 1)
        self.assertEqual(counter.check_password_calls, 1)

    def test_success_with_padded_pin_still_one_hash(self):
        with count_pin_hashes() as counter:
            response = self._post(self.student.username, f"  {self.PIN_A} ")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(counter.full_hashes, 1)

    def test_wrong_pin_costs_exactly_one_hash(self):
        with count_pin_hashes() as counter:
            response = self._post(self.student.username, "00000000")
        self._assert_generic_failure(response)
        self.assertEqual(counter.full_hashes, 1)
        self.assertEqual(counter.check_password_calls, 1)

    def test_unknown_user_costs_exactly_one_hash(self):
        with count_pin_hashes() as counter:
            response = self._post("no_such_student_xyz", self.PIN_A)
        self._assert_generic_failure(response)
        self.assertEqual(counter.full_hashes, 1)
        self.assertEqual(counter.check_password_calls, 1)

    def test_user_without_pins_costs_exactly_one_hash(self):
        with count_pin_hashes() as counter:
            response = self._post(self.student2.username, self.PIN_A)
        self._assert_generic_failure(response)
        self.assertEqual(counter.full_hashes, 1)
        self.assertEqual(counter.check_password_calls, 1)

    def test_empty_pin_costs_exactly_one_hash(self):
        with count_pin_hashes() as counter:
            response = self._post(self.student.username, "")
        self._assert_generic_failure(response)
        self.assertEqual(counter.full_hashes, 1)

    def test_two_active_finals_second_pin_one_hash_and_correct_exam(self):
        exam2 = self._second_final()
        self._student_pin(exam2, self.student, self.PIN_B)
        with count_pin_hashes() as counter:
            response = self._post(self.student.username, self.PIN_B)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(counter.full_hashes, 1)
        self.assertEqual(counter.check_password_calls, 1)
        # Giriş məhz PIN-i yazılan imtahana bağlanıb.
        self.assertTrue(FinalExamTicket.objects.filter(exam=exam2, student=self.student).exists())
        self.assertFalse(FinalExamTicket.objects.filter(exam=self.exam, student=self.student).exists())

    def test_two_active_finals_wrong_pin_one_hash(self):
        exam2 = self._second_final()
        self._student_pin(exam2, self.student, self.PIN_B)
        with count_pin_hashes() as counter:
            response = self._post(self.student.username, "11223344")
        self._assert_generic_failure(response)
        self.assertEqual(counter.full_hashes, 1)

    def test_revoked_pin_is_rejected_with_one_hash(self):
        ExamStudentPin.objects.filter(pk=self.pin_row.pk).update(revoked_at=timezone.now())
        with count_pin_hashes() as counter:
            response = self._post(self.student.username, self.PIN_A)
        self._assert_generic_failure(response)
        self.assertEqual(counter.full_hashes, 1)

    def test_unreadable_cipher_falls_back_to_hash_authority(self):
        # Şifrə oxunmur (məs. açar dəyişib) — hash yeganə hakimdir, giriş işləyir.
        ExamStudentPin.objects.filter(pk=self.pin_row.pk).update(pin_cipher="not-a-fernet-token")
        with count_pin_hashes() as counter:
            response = self._post(self.student.username, self.PIN_A)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(counter.full_hashes, 1)

    # --- Bilet (otaq-oturum) PIN yolu ------------------------------------

    def _ticket_with_pin(self):
        ExamStudentPin.objects.filter(pk=self.pin_row.pk).delete()
        ticket = FinalExamTicket.objects.create(
            organization=self.org, session=self.session, exam=self.exam, student=self.student
        )
        return ticket, pins.set_ticket_pin(ticket, self.center)

    def test_ticket_pin_success_one_hash(self):
        ticket, raw = self._ticket_with_pin()
        with count_pin_hashes() as counter:
            response = self._post(self.student.username, raw)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.wsgi_request.session["final_exam_ticket_id"], ticket.pk)
        self.assertEqual(counter.full_hashes, 1)

    def test_ticket_wrong_pin_one_hash_and_failure_still_counted(self):
        ticket, _raw = self._ticket_with_pin()
        with count_pin_hashes() as counter:
            response = self._post(self.student.username, "55554444")
        self._assert_generic_failure(response)
        self.assertEqual(counter.full_hashes, 1)
        ticket.refresh_from_db()
        # Lockout semantikası dəyişmir: uyğunsuz cəhd sayılır.
        self.assertEqual(ticket.pin_failed_attempts, 1)

    def test_ticket_lockout_still_arms_without_extra_hashes(self):
        ticket, raw = self._ticket_with_pin()
        with override_settings(FINAL_EXAM_PIN_MAX_FAILURES=2), count_pin_hashes() as counter:
            for _ in range(3):
                self._post(self.student.username, "55554444")
            response = self._post(self.student.username, raw)
        ticket.refresh_from_db()
        self.assertTrue(ticket.is_pin_locked)
        # Kilidli bilet doğru PIN-i də qəbul etmir; hər sorğu yenə bir hash.
        self._assert_generic_failure(response)
        self.assertEqual(counter.full_hashes, 4)

    # --- Servis səviyyəsi (büdcəsiz çağırış öz-özünü bərabərləşdirir) ----

    def test_resolver_alone_costs_one_hash_per_outcome(self):
        exam2 = self._second_final()
        self._student_pin(exam2, self.student, self.PIN_B)
        cases = [
            (self.student.username, self.PIN_B, exam2.pk),
            (self.student.username, "00000000", None),
            ("ghost_user_123", self.PIN_A, None),
            (self.student2.username, self.PIN_A, None),
        ]
        for username, raw, expected_exam in cases:
            pins._verified_pins.clear()
            with self.subTest(username=username, raw=raw), count_pin_hashes() as counter:
                exam, _user = resolve_student_pin_login(username, raw)
                self.assertEqual(exam.pk if exam else None, expected_exam)
                self.assertEqual(counter.full_hashes, 1)
