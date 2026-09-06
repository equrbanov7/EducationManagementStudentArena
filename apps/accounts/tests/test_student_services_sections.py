"""Tələbə Xidmətləri Mərkəzi (ekran 08–09) — icazə, state maşını, audit, ixrac.

Nəyi qoruyur
------------
1. **Rol qapısı.** `student_services` və RİM hər iki bölməni GÖRÜR; müəllim və
   tələbə fraqment API-sindən 403 alır. Dekan reyestri GÖRÜR, amma ƏMR YAZA
   BİLMİR (`student.movement` onda QƏSDƏN yoxdur).
2. **Əhatə (§8/8).** Əhatəsi olmayan koordinator BOŞ dəst alır — bütün
   universitet DEYİL.
3. **State maşını.** Qanunsuz keçid 409, səbəb <20 simvol 400, əmr nömrəsi
   məcburi, dolu qrupa köçürmə 409.
4. **Tarixçə DƏYİŞMƏZDİR** (§8/5): `StudentMovement` UPDATE/DELETE qadağandır.
5. **Arxiv/məzun qaydası dəyişməyib**: `login_blocked_access_states` toxunulmaz.
6. **Bildiriş + audit** hər əmrdə yazılır.
7. **CSV ixracı** icazə-qapılıdır.
8. **ATİS idxalı**: ixtisas kodu ilə hədəf həlli, qəbul sahələri, qrupun
   AVTOMATİK təklifi, bloklayan xətalı sətrin qrupa təyin edilə bilməməsi.
9. **İcazə kataloqu** — `student.*` açarları kataloqda və etiket cədvəlindədir.
"""

import io
from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.organizations.models import Membership, Organization, OrgUnit, Role
from apps.registrar.models import (
    AcademicStatus,
    Curriculum,
    Program,
    StudentAcademicRecord,
    StudentMovement,
)
from core.constants import OrganizationType, OrgUnitType, RoleScopeType

User = get_user_model()

PASSWORD = "StrongPass123!"
REASON = "Tələbənin ərizəsi və dekanlığın rəyi əsasında köçürülür."

SECTIONS = ("student-admission", "student-registry")

#: Rol → (səviyyə, scope, icazələr). `default_roles_student_services` ilə eyni.
ROLE_SPECS = {
    "student_services": (
        60,
        RoleScopeType.ORGANIZATION,
        [
            "org.view",
            "unit.view",
            "catalog.view",
            "member.view",
            "user.import",
            "student.assign_group",
            "student.registry_view",
            "student.movement",
            "people.view_students",
            "people.view_contacts",
            "people.view_demographics",
            "people.manage_academic",
        ],
    ),
    "ikt_rehber": (
        88,
        RoleScopeType.ORGANIZATION,
        [
            "unit.*",
            "user.import",
            "student.registry_view",
            "student.movement",
            "student.assign_group",
            "people.view_students",
            "people.manage_academic",
        ],
    ),
    # Dekan: REYESTRƏ baxır, ƏMR YAZMIR (handoff §5/09).
    "dean": (
        75,
        RoleScopeType.ORGANIZATION,
        ["unit.view", "student.registry_view", "people.view_students", "people.manage_academic"],
    ),
    # Koordinator: açar var, amma `scope_unit` YOXDUR → fail-closed boş dəst.
    "program_coordinator": (45, RoleScopeType.UNIT, ["student.registry_view", "people.view_students"]),
    "teacher": (50, RoleScopeType.ORGANIZATION, ["course.view"]),
    "student": (10, RoleScopeType.ORGANIZATION, ["course.view"]),
}


class StudentServicesBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("ss_owner", "ss_owner@qku.edu.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="QA-DS3 Universiteti",
            slug="qa-ds3-univ",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        cls.faculty = OrgUnit.objects.create(
            organization=cls.org, unit_type=OrgUnitType.FACULTY, name="QA-DS3 Fakültə", slug="qa-ds3-fak"
        )
        cls.specialty = OrgUnit.objects.create(
            organization=cls.org,
            parent=cls.faculty,
            unit_type=OrgUnitType.SPECIALTY,
            name="QA-DS3 Kompüter elmləri",
            slug="qa-ds3-ixt",
            code="QA-DS3-IXT",
        )
        cls.group_a = OrgUnit.objects.create(
            organization=cls.org,
            parent=cls.specialty,
            unit_type=OrgUnitType.GROUP,
            name="QA-DS3 101",
            slug="qa-ds3-101",
            settings={"capacity": 2, "language_sector": "az"},
        )
        cls.group_b = OrgUnit.objects.create(
            organization=cls.org,
            parent=cls.specialty,
            unit_type=OrgUnitType.GROUP,
            name="QA-DS3 102",
            slug="qa-ds3-102",
            settings={"capacity": 5, "language_sector": "az"},
        )
        cls.group_full = OrgUnit.objects.create(
            organization=cls.org,
            parent=cls.specialty,
            unit_type=OrgUnitType.GROUP,
            name="QA-DS3 103 (dolu)",
            slug="qa-ds3-103",
            settings={"capacity": 1, "language_sector": "az"},
        )
        cls.program = Program.objects.create(
            organization=cls.org,
            code="QA-DS3-PRG",
            official_code="6050100",
            name="QA-DS3 Kompüter elmləri",
            specialty_unit=cls.specialty,
        )
        cls.curriculum = Curriculum.objects.create(
            organization=cls.org, program=cls.program, admission_year=2025, name="QA-DS3 plan"
        )

        cls.users = {}
        for name, (level, scope_type, permissions) in ROLE_SPECS.items():
            role, _ = Role.objects.update_or_create(
                organization=cls.org,
                name=name,
                defaults={
                    "display_name": name.replace("_", " ").title(),
                    "level": level,
                    "scope_type": scope_type,
                    "permissions": permissions,
                    "is_system": True,
                    "is_active": True,
                },
            )
            user = User.objects.create_user(f"ss_{name}", f"ss_{name}@qku.edu.az", PASSWORD)
            Membership.objects.create(user=user, organization=cls.org, role=role, is_primary=True, is_active=True)
            cls.users[name] = user

        # ⚠️ `registrar_guard_active_member` PG trigger-i akademik qeydin
        # tələbəsindən AKTİV `student` üzvlüyü tələb edir — fikstür onsuz
        # yazıla bilmir (bu, real axının da qaydasıdır).
        cls.student_role = Role.objects.get(organization=cls.org, name="student")
        cls.pupil = User.objects.create_user("ss_pupil", "ss_pupil@qku.edu.az", PASSWORD)
        Membership.objects.create(
            user=cls.pupil, organization=cls.org, role=cls.student_role, is_primary=True, is_active=True
        )
        cls.record = StudentAcademicRecord.objects.create(
            organization=cls.org,
            student=cls.pupil,
            program=cls.program,
            curriculum=cls.curriculum,
            group=cls.group_a,
            admission_year=2025,
            status=AcademicStatus.ENROLLED,
        )
        # `group_full` tutumunu doldurur (capacity=1).
        cls.blocker = User.objects.create_user("ss_blocker", "ss_blocker@qku.edu.az", PASSWORD)
        Membership.objects.create(
            user=cls.blocker, organization=cls.org, role=cls.student_role, is_primary=True, is_active=True
        )
        StudentAcademicRecord.objects.create(
            organization=cls.org,
            student=cls.blocker,
            program=cls.program,
            curriculum=cls.curriculum,
            group=cls.group_full,
            admission_year=2025,
            status=AcademicStatus.ENROLLED,
        )

    def _client(self, role_name):
        client = Client()
        client.force_login(self.users[role_name])
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _sections(self, role_name):
        response = self._client(role_name).get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200, role_name)
        return set(response.context["allowed_sections"])

    def _fragment(self, role_name, section, **params):
        url = reverse("accounts:profile_section_fragment", kwargs={"section": section})
        return self._client(role_name).get(url, params)

    def _movement_payload(self, **overrides):
        payload = {
            "record_id": str(self.record.pk),
            "kind": "group_transfer",
            "order_number": "R-140",
            "order_date": "2026-09-01",
            "reason": REASON,
            "target_group": str(self.group_b.pk),
        }
        payload.update(overrides)
        return payload

    def _post_movement(self, role_name="student_services", **overrides):
        return self._client(role_name).post(
            reverse("accounts:student_registry_action"), self._movement_payload(**overrides)
        )


class SectionGateTest(StudentServicesBase):
    def test_student_services_sees_both_sections(self):
        sections = self._sections("student_services")
        for key in SECTIONS:
            self.assertIn(key, sections, key)

    def test_rim_sees_both_sections(self):
        sections = self._sections("ikt_rehber")
        for key in SECTIONS:
            self.assertIn(key, sections, key)

    def test_fragments_return_200_for_student_services_and_rim(self):
        for role in ("student_services", "ikt_rehber"):
            for section in SECTIONS:
                with self.subTest(role=role, section=section):
                    self.assertEqual(self._fragment(role, section).status_code, 200)

    def test_fragments_return_403_for_teacher_and_student(self):
        for role in ("teacher", "student"):
            for section in SECTIONS:
                with self.subTest(role=role, section=section):
                    self.assertEqual(self._fragment(role, section).status_code, 403)

    def test_teacher_and_student_do_not_see_sections_in_menu(self):
        for role in ("teacher", "student"):
            leaked = self._sections(role) & set(SECTIONS)
            self.assertEqual(leaked, set(), f"{role}: {sorted(leaked)}")

    def test_dean_sees_registry_but_not_admission(self):
        sections = self._sections("dean")
        self.assertIn("student-registry", sections)
        self.assertNotIn("student-admission", sections)

    def test_dean_cannot_write_movement_order(self):
        response = self._post_movement("dean")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "permission_denied")

    def test_coordinator_without_scope_gets_empty_registry(self):
        """§8/8 — «əhatə yoxdur ≠ bütün universitet»."""
        response = self._fragment("program_coordinator", "student-registry")
        self.assertEqual(response.status_code, 200)
        section = response.context["student_registry_section"]
        self.assertTrue(section["has_access"])
        self.assertFalse(section["has_scope"])
        self.assertEqual(section["total"], 0)
        self.assertEqual(section["rows"], [])
        self.assertIn("əhatə", str(section["state_title"]).lower())

    def test_old_student_intake_key_still_works(self):
        """Köhnə bölmə açarı qırılmır (link/test uyğunluğu)."""
        self.assertIn("student-intake", self._sections("student_services"))
        self.assertEqual(self._fragment("student_services", "student-intake").status_code, 200)


class MovementStateMachineTest(StudentServicesBase):
    def test_group_transfer_writes_ledger_row_and_moves_student(self):
        response = self._post_movement()
        self.assertEqual(response.status_code, 200, response.content)
        self.record.refresh_from_db()
        self.assertEqual(self.record.group_id, self.group_b.pk)

        movement = StudentMovement.objects.get(record=self.record)
        self.assertEqual(movement.kind, "group_transfer")
        self.assertEqual(movement.order_number, "R-140")
        self.assertEqual(movement.order_date, date(2026, 9, 1))
        self.assertEqual(movement.from_label, "QA-DS3 101")
        self.assertEqual(movement.to_label, "QA-DS3 102")
        self.assertEqual(movement.actor, self.users["student_services"])

    def test_reason_shorter_than_twenty_chars_is_rejected(self):
        response = self._post_movement(reason="qısa")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "reason_too_short")
        self.assertFalse(StudentMovement.objects.exists())

    def test_order_number_is_required(self):
        response = self._post_movement(order_number="  ")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "order_number_required")

    def test_order_date_is_required(self):
        response = self._post_movement(order_date="")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "order_date_required")

    def test_group_transfer_requires_target_group(self):
        response = self._post_movement(target_group="")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "target_group_required")

    def test_full_group_is_rejected(self):
        response = self._post_movement(target_group=str(self.group_full.pk))
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "group_full")

    def test_academic_leave_requires_period_and_changes_status(self):
        missing = self._post_movement(kind="academic_leave", target_group="")
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(missing.json()["error"], "effective_until_required")

        response = self._post_movement(
            kind="academic_leave", target_group="", effective_until="2027-09-01", order_number="R-141"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, AcademicStatus.ACADEMIC_LEAVE)
        self.assertFalse(self.record.is_active)
        movement = StudentMovement.objects.get(kind="academic_leave")
        self.assertEqual(movement.effective_until, date(2027, 9, 1))

    def test_illegal_transition_is_rejected(self):
        """Xaric edilmiş tələbəyə «akademik məzuniyyət» əmri verilə bilməz."""
        self._post_movement(kind="expulsion", target_group="", order_number="R-142")
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, AcademicStatus.EXPELLED)

        response = self._post_movement(
            kind="academic_leave", target_group="", effective_until="2027-09-01", order_number="R-143"
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "illegal_transition")

    def test_reinstatement_returns_expelled_student_to_a_group(self):
        self._post_movement(kind="expulsion", target_group="", order_number="R-144")
        response = self._post_movement(kind="reinstatement", target_group=str(self.group_b.pk), order_number="R-145")
        self.assertEqual(response.status_code, 200, response.content)
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, AcademicStatus.ENROLLED)
        self.assertEqual(self.record.group_id, self.group_b.pk)
        # Akademik qeyd qayıdır, hesabın girişi isə ayrı (sübutlu) qapıdan açılır.
        self.assertTrue(response.json()["movement"]["access_notice"])

    def test_form_change_updates_education_form(self):
        response = self._post_movement(
            kind="form_change", target_group="", target_form="part_time", order_number="R-146"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.record.refresh_from_db()
        self.assertEqual(self.record.education_form, "part_time")

    def test_program_transfer_without_curriculum_is_rejected(self):
        other = Program.objects.create(
            organization=self.org,
            code="QA-DS3-PRG2",
            official_code="6050200",
            name="QA-DS3 İnformasiya təhlükəsizliyi",
            specialty_unit=self.specialty,
        )
        response = self._post_movement(
            kind="program_transfer", target_group="", target_program=str(other.pk), order_number="R-147"
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "curriculum_missing")

    def test_history_is_append_only(self):
        self._post_movement()
        movement = StudentMovement.objects.get()
        with self.assertRaises(ValidationError):
            movement.order_number = "R-999"
            movement.save()
        with self.assertRaises(ValidationError):
            movement.delete()


class MovementSideEffectsTest(StudentServicesBase):
    def test_audit_row_is_written(self):
        self._post_movement()
        entries = AuditLog.objects.filter(resource_type="accounts.people.movement")
        self.assertEqual(entries.count(), 1)
        entry = entries.first()
        self.assertEqual(entry.reason, REASON)
        self.assertEqual(entry.changes["kind"], "group_transfer")
        self.assertEqual(entry.changes["order_number"], "R-140")

    def test_student_is_notified(self):
        self._post_movement()
        from apps.notifications.models import InAppNotification

        self.assertTrue(InAppNotification.objects.filter(recipient=self.pupil).exists())

    def test_movement_history_endpoint_returns_row(self):
        self._post_movement()
        url = reverse("accounts:student_registry_card", kwargs={"record_id": self.record.pk})
        response = self._client("student_services").get(url)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["movements"]), 1)
        self.assertEqual(payload["movements"][0]["order_number"], "R-140")

    def test_document_upload_is_stored_and_gated(self):
        upload = SimpleUploadedFile("emr.pdf", b"%PDF-1.4 qa-ds3", content_type="application/pdf")
        response = self._client("student_services").post(
            reverse("accounts:student_registry_action"),
            self._movement_payload(document=upload),
        )
        self.assertEqual(response.status_code, 200, response.content)
        movement = StudentMovement.objects.get()
        self.assertTrue(movement.document)

        download = reverse("accounts:student_registry_document", kwargs={"movement_id": movement.pk})
        self.assertEqual(self._client("student_services").get(download).status_code, 200)
        self.assertEqual(self._client("teacher").get(download).status_code, 404)

    def test_raw_media_path_is_private_and_not_guessable(self):
        """P0 (audit 2026-09-03): `/media/student_movements/...` AÇIQ idi.

        İki qat: (1) prefiks `core.media_policies`-də private-dır — anonim
        sorğu login-ə yönləndirilir, icazəsiz aktor 404 alır; (2) fayl adı
        istifadəçidən GƏLMİR (UUID) — yol təxmin edilmir.
        """
        from core import media_policies, media_views

        upload = SimpleUploadedFile("emr.pdf", b"%PDF-1.4 qa-ds3-raw", content_type="application/pdf")
        response = self._client("student_services").post(
            reverse("accounts:student_registry_action"),
            self._movement_payload(document=upload),
        )
        self.assertEqual(response.status_code, 200, response.content)
        movement = StudentMovement.objects.get()
        path = movement.document.name

        self.assertTrue(path.startswith("student_movements/"))
        self.assertNotIn("emr.pdf", path)  # ad təsadüfiləşib
        self.assertIn("student_movements/", media_policies.PRIVATE_PREFIXES)
        self.assertTrue(media_views._is_private(path))

        # Anonim: login-ə yönləndirilir (fayl bayt-baytına verilmir).
        anonymous = Client()
        self.assertIn(anonymous.get(f"/media/{path}").status_code, (302, 401, 403, 404))

        # `student.registry_view` daşımayan aktor: 404 (mövcudluq da sızmır).
        self.assertFalse(media_policies.check_student_movement_access(self.users["teacher"], path))
        # Reyestr aktoru və əmrin aid olduğu tələbə: icazəli.
        self.assertTrue(media_policies.check_student_movement_access(self.users["student_services"], path))
        self.assertTrue(media_policies.check_student_movement_access(movement.record.student, path))


class RegistryReadTest(StudentServicesBase):
    def test_registry_rows_carry_admission_columns(self):
        response = self._fragment("student_services", "student-registry")
        section = response.context["student_registry_section"]
        self.assertTrue(section["has_access"])
        rows = {row["record_id"]: row for row in section["rows"]}
        row = rows[str(self.record.pk)]
        self.assertEqual(row["group_name"], "QA-DS3 101")
        self.assertEqual(row["form_label"], "Əyani")
        self.assertEqual(row["funding_label"], "Ödənişli")
        self.assertEqual(row["status"], AcademicStatus.ENROLLED)

    def test_filters_and_sorting_are_applied_server_side(self):
        response = self._fragment("student_services", "student-registry", sr_group=str(self.group_full.pk))
        section = response.context["student_registry_section"]
        self.assertEqual(section["total"], 1)
        self.assertEqual(section["rows"][0]["group_name"], "QA-DS3 103 (dolu)")

        sorted_response = self._fragment("student_services", "student-registry", sr_sort="-year")
        self.assertEqual(sorted_response.status_code, 200)
        columns = sorted_response.context["student_registry_section"]["columns"]
        year_column = [column for column in columns if column["key"] == "year"][0]
        self.assertEqual(year_column["sort_dir"], "descending")

    def test_status_filter_narrows_the_set(self):
        response = self._fragment("student_services", "student-registry", sr_status="expelled")
        self.assertEqual(response.context["student_registry_section"]["total"], 0)

    def test_kpis_are_computed_not_stored(self):
        section = self._fragment("student_services", "student-registry").context["student_registry_section"]
        self.assertEqual(section["kpis"]["total"], 2)
        self.assertEqual(section["kpis"]["full_time"], 2)
        self.assertEqual(section["kpis"]["special"], 0)


class ExportGateTest(StudentServicesBase):
    def test_export_is_permission_gated(self):
        url = reverse("accounts:student_registry_export")
        self.assertEqual(self._client("teacher").get(url).status_code, 403)
        self.assertEqual(self._client("student").get(url).status_code, 403)

        response = self._client("student_services").get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        body = response.content.decode("utf-8-sig")
        self.assertIn("QA-DS3 101", body)

    def test_export_respects_filters(self):
        response = self._client("student_services").get(
            reverse("accounts:student_registry_export"), {"sr_group": str(self.group_full.pk)}
        )
        body = response.content.decode("utf-8-sig")
        self.assertIn("QA-DS3 103", body)
        self.assertNotIn("QA-DS3 101", body)


def _atis_csv(rows) -> SimpleUploadedFile:
    """ATİS ixracını təqlid edən CSV (başlıq adına görə xəritələnir)."""
    import csv as _csv

    buffer = io.StringIO()
    writer = _csv.writer(buffer)
    writer.writerow(
        [
            "FİN",
            "Ad",
            "Soyad",
            "Doğum tarixi",
            "Qəbul ili",
            "İxtisas kodu",
            "Qəbul balı",
            "İmtahan növü",
            "Təhsil forması",
            "Təhsil haqqı",
            "Dil bölməsi",
            "ATİS nömrəsi",
        ]
    )
    for row in rows:
        writer.writerow(row)
    return SimpleUploadedFile("atis.csv", buffer.getvalue().encode("utf-8-sig"), content_type="text/csv")


class AtisAdmissionTest(StudentServicesBase):
    def _preview(self, upload, **extra):
        data = {"file": upload}
        data.update(extra)
        return self._client("student_services").post(reverse("accounts:student_intake_preview"), data)

    def test_program_code_resolves_target_and_proposes_group(self):
        upload = _atis_csv(
            [
                [
                    "1AB1234",
                    "Aysel",
                    "Əliyeva",
                    "12.03.2007",
                    "2025",
                    "6050100",
                    "543,5",
                    "I qrup",
                    "əyani",
                    "dövlət sifarişi",
                    "az",
                    "A-1",
                ]
            ]
        )
        response = self._preview(upload)
        self.assertEqual(response.status_code, 200, response.content)
        row = response.json()["rows"][0]
        self.assertEqual(row["status"], "create", row)
        self.assertEqual(row["program_label"].split(" · ")[0], "QA-DS3 Kompüter elmləri")
        self.assertEqual(row["admission_score"], "543.5")
        self.assertEqual(row["education_form"], "full_time")
        self.assertEqual(row["funding_type"], "state")
        self.assertEqual(row["atis_id"], "A-1")
        # Qrup AVTOMATİK təklif olunub və seçicidə variantlar var.
        self.assertTrue(row["group_id"])
        self.assertTrue(row["group_options"])

    def test_unknown_program_code_blocks_the_row(self):
        upload = _atis_csv(
            [["1AB1235", "Tural", "Məmmədov", "12.03.2007", "2025", "9999999", "", "", "", "", "az", "A-2"]]
        )
        row = self._preview(upload).json()["rows"][0]
        self.assertEqual(row["status"], "error")
        self.assertEqual(row["code"], "unknown_program")
        self.assertEqual(row["message"], "İxtisas kodu universitetdə tapılmadı")
        # Bloklayan xətalı sətir qrupa təyin edilə bilməz.
        self.assertEqual(row["group_id"], "")

    def test_duplicate_fin_inside_file_is_blocking(self):
        upload = _atis_csv(
            [
                ["1AB1236", "Nigar", "Quliyeva", "12.03.2007", "2025", "6050100", "500", "", "", "", "az", "A-3"],
                ["1AB1236", "Nigar", "Quliyeva", "12.03.2007", "2025", "6050100", "500", "", "", "", "az", "A-4"],
            ]
        )
        rows = self._preview(upload).json()["rows"]
        self.assertEqual(rows[0]["status"], "create")
        self.assertEqual(rows[1]["status"], "error")
        self.assertEqual(rows[1]["code"], "fin_duplicate_in_file")

    def test_group_override_wins_over_auto_proposal(self):
        upload = _atis_csv(
            [["1AB1237", "Leyla", "Həsənova", "12.03.2007", "2025", "6050100", "480", "", "", "", "az", "A-5"]]
        )
        response = self._preview(upload, group_2=str(self.group_b.pk))
        row = response.json()["rows"][0]
        self.assertEqual(row["group_id"], str(self.group_b.pk))
        self.assertEqual(row["group"], "QA-DS3 102")

    def test_apply_writes_admission_fields_to_the_record(self):
        upload = _atis_csv(
            [
                [
                    "1AB1238",
                    "Kamran",
                    "Rzayev",
                    "12.03.2007",
                    "2025",
                    "6050100",
                    "612,25",
                    "Blok",
                    "qiyabi",
                    "ödənişli",
                    "az",
                    "A-6",
                ]
            ]
        )
        response = self._client("student_services").post(
            reverse("accounts:student_intake_apply"), {"file": upload, "group_2": str(self.group_b.pk)}
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["summary"]["created"], 1)

        record = StudentAcademicRecord.objects.get(student__profile__fin="1AB1238")
        self.assertEqual(str(record.admission_score), "612.25")
        self.assertEqual(record.admission_exam_type, "Blok")
        self.assertEqual(record.education_form, "part_time")
        self.assertEqual(record.funding_type, "paid")
        self.assertEqual(record.atis_id, "A-6")
        self.assertEqual(record.group_id, self.group_b.pk)

    def test_group_creation_requires_assign_permission(self):
        url = reverse("accounts:student_admission_create_group")
        payload = {"specialty": str(self.specialty.pk), "name": "QA-DS3 104", "capacity": "25", "sector": "az"}
        self.assertEqual(self._client("teacher").post(url, payload).status_code, 403)

        response = self._client("student_services").post(url, payload)
        self.assertEqual(response.status_code, 200, response.content)
        created = OrgUnit.objects.get(organization=self.org, name="QA-DS3 104")
        self.assertEqual(created.parent_id, self.specialty.pk)
        self.assertEqual(created.settings["capacity"], 25)

    def test_non_uuid_specialty_is_a_404_not_a_500(self):
        """QA 2026-09-05 STUDENT-MGMT-01: `specialty=x` `filter(pk=...)`-də ValidationError → 500 verirdi."""
        response = self._client("student_services").post(
            reverse("accounts:student_admission_create_group"),
            {"specialty": "x", "name": "QA-x", "capacity": "25"},
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "specialty_not_found")

    def test_duplicate_group_name_is_rejected(self):
        response = self._client("student_services").post(
            reverse("accounts:student_admission_create_group"),
            {"specialty": str(self.specialty.pk), "name": "QA-DS3 101", "capacity": "25"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "group_name_taken")


class ContractTest(StudentServicesBase):
    def test_permission_catalog_contains_student_keys(self):
        from apps.organizations.permissions import (
            PERMISSION_CATEGORIES,
            PERMISSION_CATEGORY_LABELS,
            PERMISSION_LABELS,
            get_all_permissions,
            validate_permissions,
        )

        keys = ("student.registry_view", "student.movement", "student.assign_group")
        self.assertIn("student", PERMISSION_CATEGORIES)
        self.assertIn("student", PERMISSION_CATEGORY_LABELS)
        for key in keys:
            self.assertIn(key, get_all_permissions(), key)
            self.assertIn(key, PERMISSION_LABELS, key)
            self.assertTrue(str(PERMISSION_LABELS[key]).strip(), key)
        self.assertTrue(validate_permissions(list(keys)))

    def test_default_role_template_carries_the_new_keys(self):
        from apps.organizations.default_roles_student_services import STUDENT_SERVICES_ROLES

        spec = STUDENT_SERVICES_ROLES[0]
        self.assertEqual(spec["name"], "student_services")
        self.assertEqual(spec["level"], 60)
        for key in ("user.import", "student.registry_view", "student.movement", "student.assign_group"):
            self.assertIn(key, spec["permissions"], key)
        # RİM operatorunun açarları QƏSDƏN verilmir (səlahiyyət ayrılığı).
        for key in ("user.credentials", "user.block", "user.soft_delete"):
            self.assertNotIn(key, spec["permissions"], key)

    def test_student_services_role_is_not_admin_alias_exempt_by_accident(self):
        """Səviyyə 60 < 80 → implicit `org_admin` aliası ONSUZ DA yoxdur."""
        from core.roles import ProfileRole

        aliases = ProfileRole.aliases_for_membership_role("student_services", level=60)
        self.assertNotIn(ProfileRole.ORG_ADMIN, aliases)

    def test_org_admin_surfaces_are_not_granted(self):
        sections = self._sections("student_services")
        for key in ("permission-editor", "manage-roles", "role-assignment", "org-roles"):
            self.assertNotIn(key, sections, key)

    def test_login_blocked_access_states_unchanged(self):
        """Arxiv/məzun qaydası TOXUNULMAYIB (`PHASE1_MIGRATION_REPAIRS`)."""
        from apps.accounts.identity import login_blocked_access_states
        from apps.accounts.models import UserProfile

        self.assertEqual(
            set(login_blocked_access_states()),
            {UserProfile.AccessState.STAGED, UserProfile.AccessState.ARCHIVED},
        )

    def test_applications_telebe_unit_prefers_student_services_role(self):
        from apps.applications.constants import DEFAULT_UNIT_SEED

        unit = [row for row in DEFAULT_UNIT_SEED if row["code"] == "telebe"][0]
        self.assertEqual(unit["handler_role_names"][0], "student_services")
        self.assertIn("hr", unit["handler_role_names"])

    def test_section_registry_is_consistent(self):
        from apps.accounts.views.profile._sections.labels import (
            DIRECT_PROFILE_SECTION_TEMPLATES,
            build_section_titles,
        )
        from apps.accounts.views.profile.sections_api import AJAX_SAFE_SECTIONS, SECTION_PARTIALS

        titles = build_section_titles()
        for key in SECTIONS:
            self.assertIn(key, SECTION_PARTIALS, key)
            self.assertIn(key, AJAX_SAFE_SECTIONS, key)
            self.assertIn(key, DIRECT_PROFILE_SECTION_TEMPLATES, key)
            self.assertIn(key, titles, key)

    def test_movement_kinds_match_the_status_catalog(self):
        from apps.registrar.movements import RULES
        from core.ui import status_catalog

        catalog_keys = set(status_catalog.keys("student_movement"))
        self.assertEqual(catalog_keys, set(RULES))
        self.assertEqual(len(catalog_keys), 6)


class MovementGuardsTest(StudentServicesBase):
    """QA 2026-09-05 STUDENT-MGMT-04/05/06/07/08 — hərəkət əmrinin giriş qapıları və giriş vəziyyəti."""

    def test_unknown_kind_is_a_json_400_not_a_500(self):
        response = self._post_movement(kind="nope")
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())

    def test_non_uuid_record_or_group_is_a_404(self):
        self.assertEqual(self._post_movement(record_id="x").status_code, 404)
        self.assertEqual(self._post_movement(target_group="x").status_code, 404)

    def test_transfer_to_the_current_group_is_refused(self):
        response = self._post_movement(target_group=str(self.group_a.pk))
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "same_group")

    def test_academic_leave_with_a_past_end_date_is_refused(self):
        response = self._post_movement(kind="academic_leave", target_group="", effective_until="01.01.2020")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "effective_until_past")

    def test_expulsion_archives_access_and_reinstatement_only_warns(self):
        """Xaric → giriş bağlanır; bərpa → qeyd qayıdır, GİRİŞ isə bildirişlə qalır.

        `archived → active` keçidi Postgres trigger-i ilə qorunur (sübut sətri
        olmadan `42501`), ona görə bərpa əmri girişi avtomatik açmır — cavabda
        `access_notice` gəlir və operator kimlik səthinin bərpa axınına yönəlir.
        """
        from apps.accounts.models import UserProfile

        profile, _ = UserProfile.objects.get_or_create(user=self.record.student)
        self.assertEqual(profile.access_state, UserProfile.AccessState.ACTIVE)
        response = self._post_movement(kind="expulsion", target_group="")
        self.assertEqual(response.status_code, 200, response.content)
        profile.refresh_from_db()
        self.assertEqual(profile.access_state, UserProfile.AccessState.ARCHIVED)

        response = self._post_movement(kind="reinstatement", order_number="R-141")
        self.assertEqual(response.status_code, 200, response.content)
        profile.refresh_from_db()
        self.assertEqual(profile.access_state, UserProfile.AccessState.ARCHIVED)
        self.assertIn("giriş", response.json()["movement"]["access_notice"])
