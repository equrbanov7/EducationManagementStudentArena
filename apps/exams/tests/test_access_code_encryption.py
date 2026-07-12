"""EXAM-P1-09 — imtahan giriş kodu bazada Fernet ilə şifrli saxlanır.

Product qaydası: access_code müəllim-görünən paylaşılan sirdir (birtərəfli hash
YOX) — Python səviyyəsində xam görünür (göstərmə/müqayisə dəyişmir), amma bazada
şifrli saxlanır. Köhnə xam mətn sətirləri (miqrasiyadan əvvəl) oxunmaqda davam
edir (geriyə-uyğunluq).
"""

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase

from apps.exams.models import Exam
from apps.exams.services.access_code_crypto import (
    AccessCodeDecryptionError,
    decrypt_access_code,
    encrypt_access_code,
)
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class TestAccessCodeEncryption(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("ac_teacher", "ac_teacher@example.com", "pw")
        self.org = Organization.objects.create(
            name="AC Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )

    def _exam(self, **kwargs):
        return Exam.objects.create(
            title="AC Exam",
            author=self.teacher,
            organization=self.org,
            exam_type="test",
            is_active=True,
            **kwargs,
        )

    def _raw_stored_code(self, exam_id):
        with connection.cursor() as cursor:
            cursor.execute("SELECT access_code FROM exams_exam WHERE id = %s", [exam_id])
            return cursor.fetchone()[0]

    def test_crypto_roundtrip(self):
        cipher = encrypt_access_code("123456")
        self.assertNotEqual(cipher, "123456")
        self.assertEqual(decrypt_access_code(cipher), "123456")

    def test_crypto_empty_stays_empty(self):
        self.assertEqual(encrypt_access_code(""), "")
        self.assertEqual(decrypt_access_code(""), "")

    def test_crypto_unopenable_value_passes_through(self):
        # Köhnə xam mətn (Fernet token deyil) olduğu kimi qaytarılır.
        self.assertEqual(decrypt_access_code("123456"), "123456")
        self.assertEqual(decrypt_access_code("ABC123"), "ABC123")

    def test_corrupted_ciphertext_is_not_treated_as_a_plaintext_access_code(self):
        cipher = encrypt_access_code("123456")
        corrupted = f"{cipher[:-1]}{'A' if cipher[-1] != 'A' else 'B'}"

        with self.assertRaises(AccessCodeDecryptionError):
            decrypt_access_code(corrupted)

    def test_access_code_stored_encrypted_at_rest(self):
        exam = self._exam(access_code="135790")
        raw = self._raw_stored_code(exam.id)
        # Bazadakı xam dəyər açıq mətn DEYİL, amma açıla bilir.
        self.assertNotEqual(raw, "135790")
        self.assertTrue(len(raw) > 6)
        self.assertEqual(decrypt_access_code(raw), "135790")

    def test_access_code_reads_back_as_plaintext(self):
        exam = self._exam(access_code="246800")
        exam.refresh_from_db()
        self.assertEqual(exam.access_code, "246800")
        # Təzədən yüklənən obyekt də xam qaytarır.
        self.assertEqual(Exam.objects.get(pk=exam.pk).access_code, "246800")

    def test_empty_access_code_stays_empty_and_presence_false(self):
        exam = self._exam(access_code="")
        exam.refresh_from_db()
        self.assertEqual(exam.access_code, "")
        self.assertFalse(bool(exam.access_code))
        self.assertEqual(self._raw_stored_code(exam.id), "")

    def test_compare_uses_plaintext(self):
        exam = self._exam(access_code="112233")
        reloaded = Exam.objects.get(pk=exam.pk)
        # Müqayisə yolu (access_policy: ``code != self.access_code``) xam üzərindir.
        self.assertTrue("112233" == reloaded.access_code)
        self.assertFalse("999999" == reloaded.access_code)

    def test_legacy_plaintext_row_still_readable(self):
        exam = self._exam(access_code="555444")
        # Bazaya BİRBAŞA xam mətn yaz (miqrasiyadan əvvəlki köhnə sətir kimi).
        with connection.cursor() as cursor:
            cursor.execute("UPDATE exams_exam SET access_code = %s WHERE id = %s", ["606060", exam.id])
        self.assertEqual(Exam.objects.get(pk=exam.pk).access_code, "606060")

    def test_resave_encrypts_legacy_plaintext(self):
        exam = self._exam(access_code="777888")
        with connection.cursor() as cursor:
            cursor.execute("UPDATE exams_exam SET access_code = %s WHERE id = %s", ["909090", exam.id])
        reloaded = Exam.objects.get(pk=exam.pk)
        reloaded.save(update_fields=["access_code"])
        raw = self._raw_stored_code(exam.id)
        self.assertNotEqual(raw, "909090")
        self.assertEqual(decrypt_access_code(raw), "909090")
