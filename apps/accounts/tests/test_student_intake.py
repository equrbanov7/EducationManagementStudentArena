"""«Tələbə idxalı» (`user.import`) — icazə qapısı, quru icra, tətbiq, giriş.

Nəyi qoruyur
------------
2026-09 auditinin PHASE 1 §4 tapıntısı: «tələbə şöbəsi siyahı yükləyir → qeydlər
→ əlaqələr → hesablar → tələbə girə bilir» axınının işləyən YEGANƏ yolu legacy
köçürmə idi (`import_users_from_excel` prod-da bağlıdır, RİM mərkəzi isə yalnız
MÖVCUD hesabları idarə edir). Bu fayl yeni səthin müqaviləsini sabitləyir:

* qapı ROL ADINA baxmır — `user.import` açarı; tələbə/müəllim 403 alır;
* quru icra HEÇ NƏ yazmır və hər sətir üçün səbəb qaytarır;
* tətbiq `User` + `UserProfile` + `Membership` + `StudentAcademicRecord` yaradır;
* faylda təkrarlanan FİN xəta, bazada mövcud FİN ötürülür (üzərinə YAZILMIR);
* e-poçt toqquşması placeholder-ə düşür, hesab itmir;
* bir pis sətir faylı DAYANDIRMIR (sətir başına savepoint);
* hər hesab üçün audit sətri + bir yekun sətri yazılır;
* yaradılan hesab ilk-giriş axınındadır (`password_change_required`) və parolunu
  qoyandan sonra TƏLƏBƏ PORTALINDAN girə bilir, `my-subjects` fraqmenti açılır;
* prod kill-switch (`command_safety`) ZƏİFLƏDİLMİR və `alumni`/arxiv giriş
  qadağası dəyişmir.
"""

import io

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.identity import login_blocked_access_states
from apps.accounts.models import UserProfile
from apps.accounts.services import intake
from apps.audit.models import AuditLog
from apps.organizations.models import Membership, Organization, OrgUnit
from apps.registrar.models import Curriculum, Program, StudentAcademicRecord
from core.constants import OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

_HEADER = [
    "FİN",
    "Ad",
    "Soyad",
    "Ata adı",
    "Doğum tarixi",
    "Cins",
    "E-poçt",
    "Telefon",
    "Tələbə kodu",
    "Fakültə",
    "İxtisas",
    "Qrup",
    "Qəbul ili",
    "Kurs",
    "Dil bölməsi",
    "Təhsil səviyyəsi",
]


def csv_upload(rows, name="intake.csv"):
    """Sətir siyahısından yüklənə bilən CSV faylı qurur (başlıq avtomatik)."""

    buffer = io.StringIO()
    buffer.write(",".join(_HEADER) + "\n")
    for row in rows:
        buffer.write(",".join(str(value) for value in row) + "\n")
    return SimpleUploadedFile(name, buffer.getvalue().encode("utf-8"), content_type="text/csv")


def student_row(fin, first, last, group="SI-101", **overrides):
    values = {
        "fin": fin,
        "first": first,
        "last": last,
        "patronymic": "Ata",
        "birth_date": "14.05.2007",
        "gender": "kişi",
        "email": "",
        "phone": "0501112233",
        "code": "",
        "faculty": "",
        "speciality": "",
        "group": group,
        "year": "2025",
        "course": "1",
        "language": "az",
        "degree": "bakalavr",
    }
    values.update(overrides)
    return [
        values["fin"],
        values["first"],
        values["last"],
        values["patronymic"],
        values["birth_date"],
        values["gender"],
        values["email"],
        values["phone"],
        values["code"],
        values["faculty"],
        values["speciality"],
        values["group"],
        values["year"],
        values["course"],
        values["language"],
        values["degree"],
    ]


class StudentIntakeBase(TestCase):
    """Fakültə → ixtisas → qrup zənciri + proqram/kurikulum + aktorlar."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("six_owner", "six_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="SIX Univ",
                slug="six-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.faculty = OrgUnit.objects.create(
                organization=cls.org, name="Mühəndislik", slug="six-fac", unit_type=OrgUnitType.FACULTY
            )
            cls.speciality = OrgUnit.objects.create(
                organization=cls.org,
                parent=cls.faculty,
                name="Kompüter mühəndisliyi",
                slug="six-spec",
                unit_type=OrgUnitType.SPECIALTY,
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org,
                parent=cls.speciality,
                name="SI-101",
                slug="six-g101",
                unit_type=OrgUnitType.GROUP,
            )
            # Proqramsız ikinci ixtisas — «program_missing» yolunu qorumaq üçün.
            cls.bare_speciality = OrgUnit.objects.create(
                organization=cls.org,
                parent=cls.faculty,
                name="Proqramsız ixtisas",
                slug="six-spec-bare",
                unit_type=OrgUnitType.SPECIALTY,
            )
            cls.bare_group = OrgUnit.objects.create(
                organization=cls.org,
                parent=cls.bare_speciality,
                name="SI-999",
                slug="six-g999",
                unit_type=OrgUnitType.GROUP,
            )
            cls.program = Program.objects.create(
                organization=cls.org,
                specialty_unit=cls.speciality,
                code="KM",
                name="Kompüter mühəndisliyi",
            )
            cls.curriculum = Curriculum.objects.create(organization=cls.org, program=cls.program, admission_year=2025)

            cls.rim = User.objects.create_user("six_rim", "six_rim@qku.edu.az", "pw")
            cls.hr = User.objects.create_user("six_hr", "six_hr@qku.edu.az", "pw")
            cls.teacher = User.objects.create_user("six_teacher", "six_teacher@qku.edu.az", "pw")
            cls.student = User.objects.create_user("six_student", "six_student@qku.edu.az", "pw")
            for user, role_name in (
                (cls.rim, "ikt_rehber"),
                (cls.hr, "hr"),
                (cls.teacher, "teacher"),
                (cls.student, "student"),
            ):
                Membership.objects.create(
                    user=user,
                    organization=cls.org,
                    role=cls.org.roles.get(name=role_name),
                    is_primary=True,
                    is_active=True,
                )
                user.profile.organization = cls.org
                user.profile.save(update_fields=["organization"])

    def client_for(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def preview(self, user, rows):
        return self.client_for(user).post(reverse("accounts:student_intake_preview"), {"file": csv_upload(rows)})

    def apply(self, user, rows):
        return self.client_for(user).post(reverse("accounts:student_intake_apply"), {"file": csv_upload(rows)})


class IntakePermissionGateTest(StudentIntakeBase):
    """Kim idxal edə bilir — rol adı yox, `user.import`."""

    def test_default_roles_carry_the_permission(self):
        for role_name in ("ikt_rehber", "hr"):
            self.assertIn("user.import", self.org.roles.get(name=role_name).permissions, role_name)
        for role_name in ("teacher", "student", "exam_center"):
            self.assertNotIn("user.import", self.org.roles.get(name=role_name).permissions, role_name)

    def test_student_and_teacher_are_denied(self):
        for user in (self.student, self.teacher):
            for name in ("student_intake_preview", "student_intake_apply"):
                response = self.client_for(user).post(reverse("accounts:%s" % name), {})
                self.assertEqual(response.status_code, 403, "%s / %s" % (user.username, name))
            self.assertEqual(self.client_for(user).get(reverse("accounts:student_intake_template")).status_code, 403)

    def test_rim_reaches_the_surface(self):
        response = self.client_for(self.rim).get(reverse("accounts:student_intake_template"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])

    def test_section_is_listed_only_for_importers(self):
        response = self.client_for(self.rim).get(reverse("accounts:profile"), {"section": "student-intake"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("student-intake", response.context["allowed_sections"])
        self.assertTrue(response.context["student_intake_section"]["has_access"])

        response = self.client_for(self.teacher).get(reverse("accounts:profile"), {"section": "student-intake"})
        self.assertNotIn("student-intake", response.context["allowed_sections"])

    def test_ajax_fragment_is_gated(self):
        url = reverse("accounts:profile_section_fragment", kwargs={"section": "student-intake"})
        self.assertEqual(self.client_for(self.rim).get(url).status_code, 200)
        self.assertEqual(self.client_for(self.student).get(url).status_code, 403)

    def test_inactive_membership_closes_the_gate(self):
        with bypass_rls():
            Membership.objects.filter(user=self.rim, organization=self.org).update(is_active=False)
        self.assertFalse(intake.can_import(self.rim, self.org))


class IntakeDryRunTest(StudentIntakeBase):
    """Quru icra HEÇ NƏ yazmır və hər sətrin səbəbini göstərir."""

    def _rows_by_status(self, payload):
        return {row["row"]: row for row in payload["rows"]}

    def test_valid_rows_are_planned_without_writing(self):
        response = self.preview(self.rim, [student_row("1AAAAA1", "Aysel", "Məmmədova")])
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["summary"], {"total": 1, "create": 1, "skip": 0, "error": 0})
        self.assertEqual(payload["rows"][0]["status"], "create")
        with bypass_rls():
            self.assertFalse(UserProfile.objects.filter(fin="1AAAAA1").exists())

    def test_missing_fin_and_name_are_errors(self):
        response = self.preview(
            self.rim,
            [
                student_row("", "Aysel", "Məmmədova"),
                student_row("2BBBBB2", "", "Məmmədova"),
                student_row("SHORT", "Aysel", "Məmmədova"),
            ],
        )
        rows = self._rows_by_status(response.json())
        self.assertEqual(rows[2]["code"], "fin_required")
        self.assertEqual(rows[3]["code"], "name_required")
        self.assertEqual(rows[4]["code"], "fin_invalid")

    def test_duplicate_fin_in_file_is_an_error(self):
        response = self.preview(
            self.rim,
            [student_row("3CCCCC3", "A", "B"), student_row("3CCCCC3", "C", "D")],
        )
        rows = self._rows_by_status(response.json())
        self.assertEqual(rows[2]["status"], "create")
        self.assertEqual(rows[3]["code"], "fin_duplicate_in_file")

    def test_existing_fin_is_skipped_not_overwritten(self):
        with bypass_rls():
            profile = self.student.profile
            profile.fin = "4DDDDD4"
            profile.save(update_fields=["fin"])
        response = self.preview(self.rim, [student_row("4DDDDD4", "Yeni", "Ad")])
        row = response.json()["rows"][0]
        self.assertEqual(row["status"], "skip")
        self.assertEqual(row["code"], "fin_exists")
        with bypass_rls():
            self.student.refresh_from_db()
            self.assertEqual(self.student.first_name, "")

    def test_unknown_group_and_speciality_are_errors(self):
        response = self.preview(
            self.rim,
            [
                student_row("5EEEEE5", "A", "B", group="YOXDUR"),
                student_row("6FFFFF6", "C", "D", speciality="Yalançı ixtisas"),
                student_row("7GGGGG7", "E", "F", group="SI-999"),
            ],
        )
        rows = self._rows_by_status(response.json())
        self.assertEqual(rows[2]["code"], "group_unknown")
        self.assertEqual(rows[3]["code"], "speciality_unknown")
        self.assertEqual(rows[4]["code"], "program_missing")

    def test_bad_date_and_year_are_errors(self):
        response = self.preview(
            self.rim,
            [
                student_row("8HHHHH8", "A", "B", birth_date="32.13.2007"),
                student_row("9IIIII9", "C", "D", year="iki min"),
                student_row("1JJJJJ1", "E", "F", year="1800"),
            ],
        )
        rows = self._rows_by_status(response.json())
        self.assertEqual(rows[2]["code"], "birth_date_invalid")
        self.assertEqual(rows[3]["code"], "admission_year_invalid")
        self.assertEqual(rows[4]["code"], "admission_year_out_of_range")

    def test_email_collision_falls_back_to_placeholder(self):
        response = self.preview(
            self.rim,
            [
                student_row("2KKKKK2", "A", "B", email="six_student@qku.edu.az"),
                student_row("3LLLLL3", "C", "D", email=""),
                student_row("4MMMMM4", "E", "F", email="taze@qku.edu.az"),
            ],
        )
        rows = self._rows_by_status(response.json())
        self.assertEqual(rows[2]["email"], "intake.2kkkkk2@%s" % intake.PLACEHOLDER_DOMAIN)
        self.assertEqual(rows[3]["email"], "intake.3lllll3@%s" % intake.PLACEHOLDER_DOMAIN)
        self.assertEqual(rows[4]["email"], "taze@qku.edu.az")
        self.assertTrue(rows[2]["warnings"])

    def test_unreadable_file_is_rejected_as_a_whole(self):
        response = self.client_for(self.rim).post(
            reverse("accounts:student_intake_preview"),
            {"file": SimpleUploadedFile("x.txt", b"a,b\n1,2\n", content_type="text/plain")},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "intake_file_type_unsupported")


class IntakeApplyTest(StudentIntakeBase):
    """Tətbiq — hesab + üzvlük + akademik qeyd, sətir izolyasiyası, audit."""

    def test_apply_creates_the_full_chain(self):
        response = self.apply(
            self.rim,
            [student_row("5NNNNN5", "Aysel", "Məmmədova", code="20250001")],
        )
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["summary"]["created"], 1)

        credential = payload["credentials"][0]
        self.assertEqual(credential["username"], "st.20250001")
        self.assertTrue(credential["password"])

        with bypass_rls():
            user = User.objects.get(username="st.20250001")
            self.assertEqual(user.first_name, "Aysel")
            self.assertTrue(user.is_active)

            profile = user.profile
            self.assertEqual(profile.fin, "5NNNNN5")
            self.assertEqual(profile.access_state, UserProfile.AccessState.ACTIVE)
            self.assertTrue(profile.password_change_required)
            self.assertFalse(profile.email_verified)
            self.assertEqual(profile.institutional_identifier, "20250001")
            self.assertEqual(profile.gender, "male")
            self.assertIsNotNone(profile.birth_date)

            membership = Membership.objects.get(user=user, organization=self.org)
            self.assertEqual(membership.role.name, "student")
            self.assertTrue(membership.is_active)

            record = StudentAcademicRecord.objects.get(student=user, organization=self.org)
            self.assertEqual(record.group_id, self.group.id)
            self.assertEqual(record.program_id, self.program.id)
            self.assertEqual(record.curriculum_id, self.curriculum.id)
            self.assertEqual(record.admission_year, 2025)

    def test_username_falls_back_to_fin_when_no_code(self):
        self.apply(self.rim, [student_row("6OOOOO6", "A", "B")])
        with bypass_rls():
            self.assertTrue(User.objects.filter(username="st.fin.6ooooo6").exists())

    def test_username_collision_gets_a_suffix(self):
        # Eyni istifadəçi adını «tutmuş» kənar hesab — idxal onu ƏZMƏMƏLİDİR.
        with bypass_rls():
            User.objects.create_user("st.20250042", "squatter@qku.edu.az", "pw")
        self.apply(self.rim, [student_row("7PPPPP7", "C", "D", code="20250042")])
        with bypass_rls():
            profile = UserProfile.objects.get(fin="7PPPPP7")
            self.assertEqual(profile.user.username, "st.20250042.2")

    def test_duplicate_student_code_is_skipped(self):
        self.apply(self.rim, [student_row("8QQQQQ8", "E", "F", code="20250055")])
        response = self.apply(self.rim, [student_row("9ZZZZZ9", "G", "H", code="20250055")])
        row = response.json()["rows"][0]
        self.assertEqual(row["status"], "skip")
        self.assertEqual(row["code"], "student_code_exists")
        with bypass_rls():
            self.assertFalse(UserProfile.objects.filter(fin="9ZZZZZ9").exists())

    def test_partial_failure_keeps_the_good_rows(self):
        response = self.apply(
            self.rim,
            [
                student_row("9RRRRR9", "Yaxşı", "Sətir"),
                student_row("", "Pis", "Sətir"),
                student_row("1SSSSS1", "Digər", "Yaxşı"),
            ],
        )
        payload = response.json()
        self.assertEqual(payload["summary"]["created"], 2)
        self.assertEqual(payload["summary"]["error"], 1)
        with bypass_rls():
            self.assertEqual(UserProfile.objects.filter(fin__in=["9RRRRR9", "1SSSSS1"]).count(), 2)

    def test_email_collision_is_applied_as_placeholder(self):
        self.apply(self.rim, [student_row("2TTTTT2", "A", "B", email="six_teacher@qku.edu.az")])
        with bypass_rls():
            profile = UserProfile.objects.get(fin="2TTTTT2")
            self.assertTrue(profile.user.email.endswith(intake.PLACEHOLDER_DOMAIN))
            self.assertFalse(profile.email_verified)

    def test_audit_rows_are_written(self):
        self.apply(self.rim, [student_row("3UUUUU3", "A", "B"), student_row("4VVVVV4", "C", "D")])
        with bypass_rls():
            created = AuditLog.objects.filter(organization=self.org, reason="student_intake_created")
            batch = AuditLog.objects.filter(organization=self.org, reason="student_intake_batch")
            self.assertEqual(created.count(), 2)
            self.assertEqual(batch.count(), 1)
            self.assertEqual(batch.first().changes["created"], 2)
            # Parol audit jurnalına HEÇ VAXT düşməməlidir.
            for row in created:
                self.assertNotIn("password", (row.changes or {}))

    def test_missing_curriculum_is_created_on_apply(self):
        response = self.apply(self.rim, [student_row("5WWWWW5", "A", "B", year="2026")])
        self.assertEqual(response.json()["summary"]["created"], 1)
        with bypass_rls():
            self.assertTrue(
                Curriculum.objects.filter(organization=self.org, program=self.program, admission_year=2026).exists()
            )


class IntakeLoginFlowTest(StudentIntakeBase):
    """Yaradılan hesab ilk-giriş axınındadır və portal girişi işləyir."""

    def _create_student(self):
        response = self.apply(self.rim, [student_row("6XXXXX6", "Nigar", "Əliyeva", code="20250777")])
        credential = response.json()["credentials"][0]
        with bypass_rls():
            return User.objects.get(username=credential["username"]), credential["password"]

    def test_first_login_is_required(self):
        user, _password = self._create_student()
        with bypass_rls():
            self.assertTrue(user.profile.password_change_required)
            self.assertFalse(user.profile.email_verified)
            # Arxiv/staged qaydaları TOXUNULMAZ qalır — yeni hesab bloklu deyil.
            self.assertNotIn(user.profile.access_state, login_blocked_access_states())

    @override_settings(UNIVERSITY_MODE=True)
    def test_student_can_authenticate_after_setting_a_password(self):
        user, _password = self._create_student()
        with bypass_rls():
            # Mövcud «setup tamamlandı» axını: parol qoyulur, e-poçt təsdiqlənir.
            user.set_password("QaAudit2026!")
            user.save(update_fields=["password"])
            profile = user.profile
            profile.password_change_required = False
            profile.email_verified = True
            profile.save(update_fields=["password_change_required", "email_verified"])

        client = Client()
        self.assertTrue(client.login(username=user.username, password="QaAudit2026!"))
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()

        response = client.get(reverse("accounts:profile_section_fragment", kwargs={"section": "my-subjects"}))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])


class IntakeSafetyContractTest(StudentIntakeBase):
    """Prod kill-switch və giriş qadağası ZƏİFLƏDİLMİR."""

    def test_management_command_stays_disabled_in_production(self):
        from django.core.management.base import CommandError

        from core.management.command_safety import require_safe_management_command

        with self.settings(MANAGEMENT_COMMAND_ENVIRONMENT="production"):
            with self.assertRaises(CommandError):
                require_safe_management_command("import_users_from_excel")

    def test_login_blocked_states_are_unchanged(self):
        self.assertEqual(
            set(login_blocked_access_states()),
            {UserProfile.AccessState.STAGED, UserProfile.AccessState.ARCHIVED},
        )
