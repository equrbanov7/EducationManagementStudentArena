"""«Təhsil aldığı yer haqqında arayış» — möhürlü PDF, publik faktlar, aktiv tələbə qaydası (sahib 2026-10-19)."""

from __future__ import annotations

import hashlib

from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import UserProfile
from apps.registrar import enrollment_certificate
from apps.registrar.models import AcademicStatus, StudentAcademicRecord
from apps.verification.models import DocType, DocumentSeal
from core.rate_limit import _rate_limit_cache
from core.rls import bypass_rls

from .world import client_for, latest_seal
from .world_documents import arayis_url, build_documents_world, pdf_text, post_arayis

PLACE = "Səbail rayon hərbi komissarlığına"


def _count(**filters) -> int:
    with bypass_rls():
        return DocumentSeal.objects.filter(doc_type=DocType.ENROLLMENT_CERTIFICATE, **filters).count()


class CertificatePdfTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_documents_world("qkuar")

    def test_pdf_is_sealed_and_prints_the_official_text(self):
        response = post_arayis(self.w, self.w["txm"], place=PLACE)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("Arayis_", response["Content-Disposition"])
        seal = latest_seal(subject_user=self.w["student"], doc_type=DocType.ENROLLMENT_CERTIFICATE)
        self.assertIsNotNone(seal)
        self.assertEqual(seal.issued_by_id, self.w["txm"].pk)
        self.assertEqual(seal.scope_path, self.w["g1"].path)
        self.assertEqual(seal.language, "az")
        self.assertEqual(seal.file_sha256, hashlib.sha256(response.content).hexdigest())
        text = " ".join(pdf_text(response.content).split())
        course = enrollment_certificate._ROMANS[enrollment_certificate.course_number(self.w["record"])]
        for expected in (
            "QƏRBİ KASPİ UNİVERSİTETİ",
            "ARAYIŞ",
            "Arayış № AR-",
            "Qurbanov Elvin Rauf oğlu",
            "Qərbi Kaspi Universitetinin «Fakültə F1» fakültəsinin «Kompüter elmləri» ixtisası",
            f"bakalavriat təhsil pilləsinin {course} kurs, KE-101 qrup tələbəsidir",
            "Təhsil forması: əyani.",
            "Qəbul ili: 2024.",
            f"Arayış {PLACE} təqdim edilmək üçün verilir.",
            "Fakültə dekanı",
            "Tədris şöbəsinin müdiri / Tələbə Xidmətləri",
            "M.Y.",
            seal.code,
        ):
            self.assertIn(expected, text)
        self.assertNotIn("EMS Arena", text)

    def test_without_place_prints_the_default_sentence(self):
        text = " ".join(pdf_text(post_arayis(self.w, self.w["owner"]).content).split())
        self.assertIn("Arayış tələb olunan yerə təqdim edilmək üçün verilir.", text)

    def test_same_day_same_content_reuses_the_seal_and_bytes(self):
        first = post_arayis(self.w, self.w["txm"], place=PLACE).content
        second = post_arayis(self.w, self.w["txm"], place=PLACE).content
        self.assertEqual(first, second)
        self.assertEqual(_count(subject_user=self.w["student"]), 1)
        post_arayis(self.w, self.w["txm"], place="Kapital Bank ASC-yə")
        self.assertEqual(_count(subject_user=self.w["student"]), 2)  # başqa mətn → başqa fayl → yeni möhür

    def test_get_is_not_allowed(self):
        response = client_for(self.w["org"], self.w["txm"]).get(arayis_url(self.w["record"]))
        self.assertEqual(response.status_code, 405)
        self.assertEqual(_count(), 0)

    def test_issuance_is_audited_with_the_cleaned_place(self):
        from apps.audit.models import AuditLog

        post_arayis(self.w, self.w["txm"], place="  Kapital\u202e Bank\x00 ASC-yə\n ")
        with bypass_rls():
            row = AuditLog.objects.filter(
                resource_type="registrar.enrollment_certificate_pdf", resource_id=str(self.w["record"].pk)
            ).first()
            seal = latest_seal(subject_user=self.w["student"], doc_type=DocType.ENROLLMENT_CERTIFICATE)
        self.assertIsNotNone(row)
        self.assertEqual(row.new_values["place"], "Kapital Bank ASC-yə")
        self.assertEqual(row.new_values["code"], seal.code)
        self.assertEqual(seal.payload["place"], "Kapital Bank ASC-yə")


class CertificatePublicFactsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_documents_world("qkuaf")

    def setUp(self):
        cache.clear()
        _rate_limit_cache().clear()

    def test_payload_carries_no_pii_beyond_the_minimum(self):
        post_arayis(self.w, self.w["txm"], place=PLACE)
        seal = latest_seal(subject_user=self.w["student"], doc_type=DocType.ENROLLMENT_CERTIFICATE)
        self.assertEqual(seal.payload["holder"], "Elvin Q.")
        keys = [key for key, _value in seal.payload["facts"]]
        self.assertEqual(keys, ["program", "degree", "course", "education_form", "student_status"])
        blob = str(seal.payload)
        # Təqdim yeri PDF-də çap olunur → möhür sətrində qalır (hara verildiyi bilinsin), amma faktlarda YOX.
        self.assertEqual(seal.payload["place"], PLACE)
        self.assertNotIn("komissarlığ", str(seal.payload["facts"]))
        for leak in ("Qurbanov", "Rauf", self.w["student"].username, "KE-101", "2024", "@", "Fakültə"):
            self.assertNotIn(leak, blob)

    def test_public_page_shows_the_status_facts(self):
        post_arayis(self.w, self.w["txm"])
        seal = latest_seal(subject_user=self.w["student"], doc_type=DocType.ENROLLMENT_CERTIFICATE)
        response = Client().get(reverse("verification:detail", args=[seal.code]), REMOTE_ADDR="85.132.1.9")
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        for expected in ("Təhsil aldığı yer haqqında arayış", "Elvin Q.", "Kompüter elmləri", "Aktiv tələbə", "Əyani"):
            self.assertIn(expected, body)
        for leak in ("Qurbanov", "KE-101", "Rauf"):
            self.assertNotIn(leak, body)

    def test_public_page_does_not_show_the_place(self):
        post_arayis(self.w, self.w["txm"], place=PLACE)
        seal = latest_seal(subject_user=self.w["student"], doc_type=DocType.ENROLLMENT_CERTIFICATE)
        body = Client().get(reverse("verification:detail", args=[seal.code]), REMOTE_ADDR="85.132.1.10").content
        self.assertNotIn("komissarlığ", body.decode())


class CertificateScopeAndRefusalTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_documents_world("qkuas")

    def test_permission_matrix(self):
        for name in ("owner", "to_head", "txm", "rim", "vrector", "dean", "vdean"):
            with self.subTest(role=name):
                self.assertEqual(post_arayis(self.w, self.w[name]).status_code, 200)
        for name in ("office", "teacher", "student", "s2", "unit_staff"):
            with self.subTest(role=name):
                self.assertEqual(post_arayis(self.w, self.w[name]).status_code, 404)
        for name in ("dean", "vdean"):
            with self.subTest(role=f"{name}-out-of-scope"):
                self.assertEqual(post_arayis(self.w, self.w[name], record=self.w["record2"]).status_code, 404)
        self.assertEqual(post_arayis(self.w, self.w["txm"], record=self.w["record2"]).status_code, 200)

    def _refused(self, **changes):
        with bypass_rls():
            StudentAcademicRecord.objects.filter(pk=self.w["record"].pk).update(**changes)
        response = post_arayis(self.w, self.w["txm"])
        self.assertEqual(response.status_code, 409)
        self.assertTrue(response.json()["message"])
        self.assertEqual(_count(subject_user=self.w["student"]), 0)
        return response.json()

    def test_expelled_student_is_refused(self):
        self.assertEqual(self._refused(status=AcademicStatus.EXPELLED)["code"], "not_active")

    def test_graduated_and_leave_are_refused(self):
        self.assertEqual(self._refused(status=AcademicStatus.GRADUATED)["code"], "not_active")
        self.assertEqual(self._refused(status=AcademicStatus.ACADEMIC_LEAVE)["code"], "not_active")

    def test_archived_account_is_refused(self):
        with bypass_rls():
            UserProfile.objects.filter(user=self.w["student"]).update(access_state="archived")
        response = post_arayis(self.w, self.w["txm"])
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "archived")

    def test_unknown_year_and_ended_period_are_refused(self):
        self.assertEqual(self._refused(admission_year=1950)["code"], "year_unknown")
        self.assertEqual(self._refused(admission_year=2015)["code"], "period_ended")


class CertificateTextHelpersTest(TestCase):
    """Ata adı şəkilçisi və «təqdim ediləcəyi yer» təmizlənməsi (rəy 2026-10-19, LOW)."""

    def test_typed_suffixes_are_replaced_by_the_gendered_one(self):
        phrase = enrollment_certificate.patronymic_phrase
        for typed in (
            "Rauf",
            "Rauf oğlu",
            "Rauf oglu",
            "Rauf OĞLU",
            "Rauf Oglu",
            "Rauf ogl.",
            "Rauf o.",
            "Rauf  oğlu ",
        ):
            with self.subTest(typed=typed):
                self.assertEqual(phrase(typed, "male"), "Rauf oğlu")
        for typed in ("Aygün", "Aygün qızı", "Aygün qizi", "Aygün QIZI", "Aygün q.", "Aygün Qızı"):
            with self.subTest(typed=typed):
                self.assertEqual(phrase(typed, "female"), "Aygün qızı")
        self.assertEqual(phrase("Rauf qızı", "male"), "Rauf oğlu")  # səhv yazılmış şəkilçi də düzəlir

    def test_unknown_gender_keeps_the_typed_patronymic(self):
        phrase = enrollment_certificate.patronymic_phrase
        self.assertEqual(phrase("  Rauf   oğlu ", "unspecified"), "Rauf oğlu")
        self.assertEqual(phrase("Rauf", ""), "Rauf")
        self.assertEqual(phrase("", "male"), "")

    def test_place_drops_control_and_bidi_characters(self):
        clean = enrollment_certificate.clean_place
        self.assertEqual(clean("Bank\u202eı\u200b\x07 ASC-yə"), "Bankı ASC-yə")
        self.assertEqual(clean("\tSəbail\n rayon\r\n"), "Səbail rayon")
        self.assertEqual(len(clean("ə" * 500)), enrollment_certificate.MAX_PLACE_LENGTH)
