"""Müəllim idxalı (toplu Excel) + kataloqdan yaratma düymələri (2026-09-08).

* şablon: müəllim sütunları (FİN, kafedra məcburi); `user.import` olmayan 403;
* quru icra: kafedra tapılmayan sətir xəta, düzgün sətir «Yaradılacaq»;
* tətbiq: hesab + kafedraya bağlı müəllim üzvlüyü + vəzifə/tabel №; parol
  yalnız cavabda; audit sətri;
* kataloq: `people-teachers` / `people-students` fraqmentində «Yeni müəllim /
  Yeni tələbə» və «Toplu idxal» düymələri (icazə olanda), RİM forması daxil.
"""

from __future__ import annotations

import csv
import io
import re

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.accounts.models import UserProfile
from apps.audit.models import AuditLog
from apps.organizations.models import Membership

from .test_teaching_office_stage2 import Stage2BaseTest


def _csv(rows):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "FİN",
            "Ad",
            "Soyad",
            "Ata adı",
            "Doğum tarixi",
            "Cins",
            "E-poçt",
            "Telefon",
            "İşçi kodu",
            "Fakültə",
            "Kafedra",
            "Vəzifə",
            "Elmi dərəcə",
            "Elmi ad",
            "Ünvan",
        ]
    )
    for row in rows:
        writer.writerow(row)
    return SimpleUploadedFile("muellimler.csv", ("﻿" + buffer.getvalue()).encode("utf-8"), content_type="text/csv")


class _IntakeBase(Stage2BaseTest):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        head = cls.roles["teaching_office_head"]
        head.permissions = list(head.permissions) + ["user.import", "people.view_teachers", "people.view_students"]
        head.save(update_fields=["permissions"])

    def _post(self, role, name, file):
        return self._client(role).post(reverse(name), {"file": file})


class TeacherIntakeEndpointTest(_IntakeBase):
    def test_template_lists_teacher_columns_and_is_gated(self):
        response = self._client("teaching_office_head").get(reverse("accounts:teacher_intake_template"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertEqual(self._client("teacher").get(reverse("accounts:teacher_intake_template")).status_code, 403)

    def test_preview_flags_unknown_kafedra_and_accepts_valid_row(self):
        upload = _csv(
            [
                [
                    "ABC1234",
                    "Aynur",
                    "Əliyeva",
                    "Rauf",
                    "12.03.1985",
                    "qadın",
                    "aynur@example.com",
                    "+994501112233",
                    "T-101",
                    self.faculty.name,
                    self.chair.name,
                    "baş müəllim",
                    "fəlsəfə doktoru",
                    "dosent",
                    "Bakı",
                ],
                [
                    "ABC1235",
                    "Elnur",
                    "Hüseynov",
                    "",
                    "1990-07-01",
                    "kişi",
                    "",
                    "",
                    "T-102",
                    "",
                    "Olmayan kafedra",
                    "",
                    "",
                    "",
                    "",
                ],
            ]
        )
        response = self._post("teaching_office_head", "accounts:teacher_intake_preview", upload)
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload["summary"]["create"], 1)
        self.assertEqual(payload["summary"]["error"], 1)
        ok_row, bad_row = payload["rows"]
        self.assertEqual(ok_row["group"], self.chair.name)
        self.assertTrue(ok_row["username"].startswith("mu.t-101"))
        self.assertEqual(bad_row["code"], "kafedra_unknown")
        # Quru icra HEÇ NƏ yazmır.
        self.assertFalse(UserProfile.objects.filter(fin="ABC1234").exists())

    def test_apply_creates_teacher_with_membership_and_title(self):
        row = [
            "ABC1234",
            "Aynur",
            "Əliyeva",
            "Rauf",
            "12.03.1985",
            "qadın",
            "aynur@example.com",
            "+994501112233",
            "T-101",
            "",
            self.chair.name,
            "baş müəllim",
            "fəlsəfə doktoru",
            "dosent",
            "Bakı",
        ]
        response = self._post("teaching_office_head", "accounts:teacher_intake_apply", _csv([row]))
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload["summary"]["created"], 1)
        self.assertEqual(len(payload["credentials"]), 1)
        self.assertTrue(payload["credentials"][0]["password"])
        profile = UserProfile.objects.get(fin="ABC1234")
        self.assertEqual(profile.staff_position, "baş müəllim")
        self.assertEqual(profile.academic_degree, "fəlsəfə doktoru")
        self.assertEqual(profile.location, "Bakı")
        self.assertTrue(profile.password_change_required)
        membership = Membership.objects.get(user=profile.user, organization=self.org)
        self.assertEqual(membership.scope_unit_id, self.chair.id)
        self.assertEqual(membership.role.name, "teacher")
        self.assertEqual(membership.title, "baş müəllim")
        self.assertEqual(membership.employee_id, "T-101")
        self.assertTrue(AuditLog.objects.filter(organization=self.org, resource_type="teacher_intake").exists())
        # Eyni FİN ikinci dəfə ötürülür.
        again = self._post("teaching_office_head", "accounts:teacher_intake_preview", _csv([row])).json()
        self.assertEqual(again["rows"][0]["status"], "skip")

    def test_apply_is_gated(self):
        upload = _csv([["ABC1234", "A", "B", "", "", "", "", "", "", "", self.chair.name, "", "", "", ""]])
        self.assertEqual(self._post("teacher", "accounts:teacher_intake_apply", upload).status_code, 403)


class CatalogCreateButtonsTest(_IntakeBase):
    def test_teachers_catalog_offers_create_and_bulk_import(self):
        response = self._fragment("teaching_office_head", "people-teachers")
        self.assertEqual(response.status_code, 200)
        section = response.context["people_section"]
        self.assertTrue(section["can_create"])
        self.assertEqual(section["intake_section"], "teacher-intake")
        html = response.json()["html"]
        self.assertIn('data-rimc-open="teacher"', html)
        self.assertIn("section=teacher-intake", html)
        self.assertIn('id="rimc-form"', html)
        self.assertIn('name="title"', html)

    def test_students_catalog_offers_student_create(self):
        response = self._fragment("teaching_office_head", "people-students")
        self.assertEqual(response.status_code, 200)
        html = response.json()["html"]
        self.assertIn('data-rimc-open="student"', html)
        self.assertIn("section=student-intake", html)
        self.assertIn('name="education_form"', html)

    def test_teacher_intake_section_renders_for_importer(self):
        self.assertIn("teacher-intake", self._sections("teaching_office_head"))
        response = self._fragment("teaching_office_head", "teacher-intake")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["teacher_intake_section"]["has_access"])
        html = response.json()["html"]
        # Başlıq QABIQDAN gəlir (panel `<h1>/<h2>` yazmır) — panel öz
        # çəngəlləri və 3 addımlı lenti ilə tanınır.
        self.assertIn("data-six-root", html)
        self.assertIn("Toplu əlavənin mərhələləri", html)
        self.assertNotIn("teacher-intake", self._sections("teacher"))

    def test_bulk_sections_never_say_idxal(self):
        """Sahib qərarı (2026-09): «idxal» səhv anlayışdır — «əlavə» işlədilir.

        Yalnız GÖRÜNƏN mətnə baxılır; daxili adlar (`student-intake`,
        `data-six-*`, `user.import`) qəsdən olduğu kimi qalır.
        """
        for section in ("teacher-intake", "student-intake"):
            with self.subTest(section=section):
                html = self._fragment("teaching_office_head", section).json()["html"]
                # Panel həqiqətən açılıb (icazə rəddi səhifəsi deyil).
                self.assertIn("data-six-root", html)
                self.assertNotIn("idxal", html.lower())
                self.assertIn("əlavə", html.lower())

    def test_bulk_section_renders_the_three_step_ems_ui_surface(self):
        """Redizayn müqaviləsi: qabıq başlığı + lent + dropzone + KPI yuvası."""
        html = self._fragment("teaching_office_head", "student-intake").json()["html"]
        # Başlıq YALNIZ qabıqdan gəlir — panelin ÖZ gövdəsində sərbəst h1/h2
        # olmamalıdır. Dialoqların (`ems-overlay`) öz `<h2>` başlığı a11y üçün
        # məcburidir (`aria-labelledby`), ona görə overlay blokları çıxarılır:
        # 2026-09-09-dan panelə «Tək müəllim/tələbə əlavə et» dialoqu da daxildir.
        body = re.sub(r'<div class="ems-overlay.*', "", html, flags=re.S)
        self.assertNotIn("<h1", body)
        self.assertNotIn("<h2", body)
        self.assertIn('class="ems-header__subtitle"', html)
        self.assertIn("six-scope__text", html)  # əhatə nişanı (başlıq əməli)
        self.assertEqual(html.count('class="ems-step ems-step--'), 3)
        self.assertIn("data-six-drop", html)
        self.assertIn('data-six-counts="kpi"', html)
        self.assertIn("ems-table--zebra", html)
        # CSP: inline üslub/skript yoxdur.
        self.assertNotIn("<style", html)
        self.assertNotIn('style="', html)

    def test_sidebar_and_catalog_use_the_new_wording(self):
        html = self._fragment("teaching_office_head", "people-teachers").json()["html"]
        self.assertIn("Toplu əlavə (Excel)", html)
        self.assertNotIn("Toplu idxal", html)
