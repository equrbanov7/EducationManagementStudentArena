"""RİM «Yeni hesab» — tək-tək tələbə/müəllim yaratma + toplu idxal səthi.

Nəyi qoruyur
------------
RİM mərkəzi 2026-09-06-ya qədər yalnız MÖVCUD hesabları idarə edirdi; yaratmaq
üçün operator ya 1 sətirlik Excel düzəldirdi, ya da server aləti tələb edirdi.
Bu fayl yeni səthin müqaviləsini sabitləyir:

* qapı ROL ADINA baxmır — toplu idxalla EYNİ `user.import` açarıdır; RİM-in
  axtarış/parol açarları TƏK BAŞINA yaratmağa icazə VERMİR (`rim_staff` yolu);
* tələbə yaradılışı `User` + `UserProfile` + `Membership` + `StudentAcademicRecord`
  verir; müəllim yaradılışı akademik qeyd YARATMIR;
* mövcud FİN sahə xətasıdır (fayl axınında `skip`, formda «yaratdım?» aldanışı
  olmasın), e-poçt toqquşması isə hər iki axında placeholder + xəbərdarlıqdır;
* istifadəçi adı toqquşması `st.<kod>.2` şəkilçisi ilə həll olunur;
* hər yaradılış audit sətri yazır və parol audit-ə DÜŞMÜR;
* toplu axın RİM-dən mövcud `student_intake_*` endpoint-lərinə gedir və EYNİ
  faylın ikinci tətbiqi yeni hesab YARATMIR (FİN artıq var → ötürülür).
"""

from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, override_settings
from django.urls import reverse

from apps.accounts.models import UserProfile
from apps.accounts.services.rim import RimAccessError
from apps.accounts.services.rim import create as rim_create
from apps.accounts.services.rim import resolve_actor
from apps.audit.models import AuditLog
from apps.organizations.models import Membership, OrgUnit
from apps.registrar.models import StudentAcademicRecord
from core.constants import OrgUnitType
from core.rls import bypass_rls

from .test_student_intake import StudentIntakeBase, student_row

User = get_user_model()


def base_payload(**overrides):
    data = {
        "fin": "1AAAAA1",
        "first_name": "Nigar",
        "last_name": "Əliyeva",
        "patronymic": "Səməd",
        "birth_date": "2007-05-14",
        "gender": "qadın",
        "email": "",
        "phone": "0501112233",
        "code": "",
        "group": "",
        "admission_year": "2025",
        "unit": "",
    }
    data.update(overrides)
    return data


@override_settings(RATELIMIT_ENABLE=False)
class RimCreateBase(StudentIntakeBase):
    """`test_student_intake` strukturunu (fakültə→ixtisas→qrup+proqram) təkrar işlədir."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.chair = OrgUnit.objects.create(
                organization=cls.org,
                parent=cls.faculty,
                name="Kompüter kafedrası",
                slug="six-chair",
                unit_type=OrgUnitType.CHAIR,
            )
            # RİM ƏMƏKDAŞI: hesab əməliyyatları var, `user.import` YOXDUR.
            cls.rim_staff = User.objects.create_user("six_rim_staff", "six_staff@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.rim_staff,
                organization=cls.org,
                role=cls.org.roles.get(name="rim_staff"),
                is_primary=True,
                is_active=True,
            )
            cls.rim_staff.profile.organization = cls.org
            cls.rim_staff.profile.save(update_fields=["organization"])

    def actor_for(self, user):
        """RİM aktoru — `resolve_actor` ilə (aktiv üzvlük + təşkilat konteksti).

        ``request.organization`` normalda `OrganizationMiddleware` tərəfindən
        qoyulur; servis testində onu ƏL İLƏ veririk. İcazələr yenə də AKTİV
        üzvlükdən həll olunur — qapı test üçün zəiflədilmir.
        """
        request = RequestFactory().post("/accounts/rim/create/")
        request.user = user
        request.organization = self.org
        return resolve_actor(request)

    def create(self, user, kind, **overrides):
        return rim_create.create_account(self.actor_for(user), kind=kind, data=base_payload(**overrides))


class RimCreatePermissionTest(RimCreateBase):
    """Qapı: `user.import` — RİM-in öz açarları tək başına kifayət etmir."""

    def test_gate_key_is_the_intake_key(self):
        self.assertEqual(rim_create.PERM_CREATE, "user.import")

    def test_rim_staff_carries_account_keys_but_not_import(self):
        permissions = self.org.roles.get(name="rim_staff").permissions
        self.assertNotIn("user.import", permissions)
        self.assertNotIn("user.credentials", permissions)

    def test_rim_staff_cannot_create(self):
        actor = self.actor_for(self.rim_staff)
        self.assertFalse(rim_create.can_create(actor))
        with self.assertRaises(RimAccessError) as caught:
            rim_create.create_account(actor, kind="student", data=base_payload(group=str(self.group.pk)))
        self.assertEqual(caught.exception.reason_code, "permission_denied")
        self.assertEqual(caught.exception.status, 403)
        self.assertFalse(User.objects.filter(profile__fin="1AAAAA1").exists())

    def test_teacher_and_student_cannot_create(self):
        for user in (self.teacher, self.student):
            with self.assertRaises(RimAccessError, msg=user.username):
                self.create(user, "teacher")

    def test_importers_can_create(self):
        for user in (self.rim, self.hr):
            self.assertTrue(rim_create.can_create(self.actor_for(user)), user.username)


class RimCreateStudentTest(RimCreateBase):
    """Tələbə yolu — hesab + üzvlük + AKADEMİK QEYD."""

    def setUp(self):
        self.result = self.create(self.rim, "student", group=str(self.group.pk))
        self.created = User.objects.get(pk=self.result["user_id"])

    def test_account_membership_and_academic_record(self):
        self.assertEqual(self.created.first_name, "Nigar")
        membership = Membership.objects.get(user=self.created, organization=self.org)
        self.assertEqual(membership.role.name, "student")
        self.assertTrue(membership.is_active)
        self.assertIsNone(membership.scope_unit)

        record = StudentAcademicRecord.objects.get(student=self.created, organization=self.org)
        self.assertEqual(record.group_id, self.group.pk)
        self.assertEqual(record.program_id, self.program.pk)
        self.assertEqual(record.admission_year, 2025)

    def test_first_login_contract(self):
        profile = UserProfile.objects.get(user=self.created)
        self.assertTrue(profile.password_change_required)
        self.assertFalse(profile.email_verified)
        self.assertEqual(profile.access_state, UserProfile.AccessState.ACTIVE)
        self.assertEqual(profile.student_group_number, self.group.name)

    def test_password_is_returned_once_and_works(self):
        password = self.result["password"]
        self.assertTrue(password)
        self.created.refresh_from_db()
        self.assertTrue(self.created.check_password(password))

    def test_username_follows_the_intake_convention(self):
        self.assertTrue(self.result["username"].startswith("st."), self.result["username"])

    def test_audit_row_written_without_the_password(self):
        rows = AuditLog.objects.filter(organization=self.org, resource_id=str(self.created.pk))
        self.assertEqual(rows.count(), 1)
        row = rows.get()
        self.assertIn("yeni hesab yaradıldı", row.reason)
        self.assertEqual(row.resource_type, "User")
        self.assertNotIn(self.result["password"], str(row.changes))
        self.assertNotIn(self.result["password"], row.reason)

    def test_group_is_required(self):
        with self.assertRaises(rim_create.RimCreateError) as caught:
            self.create(self.rim, "student", fin="2BBBBB2", group="")
        self.assertIn("group", caught.exception.fields)

    def test_non_uuid_group_is_a_field_error_not_a_crash(self):
        with self.assertRaises(rim_create.RimCreateError) as caught:
            self.create(self.rim, "student", fin="2BBBBB2", group="not-a-uuid")
        self.assertIn("group", caught.exception.fields)


class RimCreateTeacherTest(RimCreateBase):
    """Müəllim yolu — hesab + üzvlük, AKADEMİK QEYD YOX."""

    def setUp(self):
        self.result = self.create(self.rim, "teacher", fin="3CCCCC3", code="EMP-77", unit=str(self.chair.pk))
        self.created = User.objects.get(pk=self.result["user_id"])

    def test_membership_uses_the_teacher_role_and_chair_scope(self):
        membership = Membership.objects.get(user=self.created, organization=self.org)
        self.assertEqual(membership.role.name, "teacher")
        self.assertEqual(membership.scope_unit_id, self.chair.pk)

    def test_no_student_academic_record(self):
        self.assertFalse(StudentAcademicRecord.objects.filter(student=self.created).exists())
        profile = UserProfile.objects.get(user=self.created)
        self.assertEqual(profile.student_group_number, "")
        self.assertEqual(profile.student_specialization, "")

    def test_username_uses_the_teacher_prefix(self):
        self.assertEqual(self.result["username"], "mu.emp-77")

    def test_chair_is_optional(self):
        result = self.create(self.rim, "teacher", fin="4DDDDD4")
        membership = Membership.objects.get(user_id=result["user_id"], organization=self.org)
        self.assertIsNone(membership.scope_unit)

    def test_unknown_chair_is_a_field_error(self):
        with self.assertRaises(rim_create.RimCreateError) as caught:
            self.create(self.rim, "teacher", fin="5EEEEE5", unit=str(self.group.pk))
        self.assertIn("unit", caught.exception.fields)


class RimCreateCollisionTest(RimCreateBase):
    """Sənədləşdirilmiş toqquşma davranışı — FİN / kod / e-poçt / istifadəçi adı."""

    def test_existing_fin_is_a_field_error(self):
        self.create(self.rim, "teacher", fin="6FFFFF6")
        with self.assertRaises(rim_create.RimCreateError) as caught:
            self.create(self.rim, "teacher", fin="6FFFFF6", first_name="Başqa")
        self.assertIn("fin", caught.exception.fields)
        self.assertEqual(caught.exception.status, 400)
        self.assertEqual(User.objects.filter(profile__fin="6FFFFF6").count(), 1)

    def test_invalid_fin_is_a_field_error(self):
        with self.assertRaises(rim_create.RimCreateError) as caught:
            self.create(self.rim, "teacher", fin="short")
        self.assertIn("fin", caught.exception.fields)

    def test_missing_names_collect_all_field_errors_at_once(self):
        with self.assertRaises(rim_create.RimCreateError) as caught:
            self.create(self.rim, "teacher", fin="", first_name="", last_name="")
        self.assertEqual(set(caught.exception.fields), {"fin", "first_name", "last_name"})

    def test_email_collision_falls_back_to_placeholder(self):
        result = self.create(self.rim, "teacher", fin="7GGGGG7", email=self.teacher.email)
        created = User.objects.get(pk=result["user_id"])
        self.assertTrue(created.email.endswith(".invalid"), created.email)
        self.assertTrue(any("placeholder" in text for text in result["warnings"]))

    def test_duplicate_code_is_a_field_error(self):
        self.create(self.rim, "student", fin="8HHHHH8", code="ST-1", group=str(self.group.pk))
        with self.assertRaises(rim_create.RimCreateError) as caught:
            self.create(self.rim, "student", fin="9IIIII9", code="ST-1", group=str(self.group.pk))
        self.assertIn("code", caught.exception.fields)

    def test_username_collision_gets_a_suffix(self):
        User.objects.create_user("mu.emp-9", "taken@qku.edu.az", "pw")
        result = self.create(self.rim, "teacher", fin="1JJJJJ1", code="EMP-9")
        self.assertEqual(result["username"], "mu.emp-9.2")


@override_settings(RATELIMIT_ENABLE=False)
class RimCreateViewTest(RimCreateBase):
    """View qatı — bölmə, yaratma endpoint-i, seçici kataloqu."""

    def test_section_shows_the_entry_point_only_for_importers(self):
        response = self.client_for(self.rim).get(reverse("accounts:profile"), {"section": "rim-center"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["rim_center_section"]["can_create"])
        self.assertContains(response, 'data-ems-overlay-open="rimc-chooser"')
        self.assertContains(response, "data-rimc-root")

    def test_section_hides_the_entry_point_without_the_import_key(self):
        response = self.client_for(self.rim_staff).get(reverse("accounts:profile"), {"section": "rim-center"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["rim_center_section"]["can_create"])
        self.assertNotContains(response, "data-rimc-root")

    def test_create_endpoint_denies_unauthorised_actor(self):
        response = self.client_for(self.rim_staff).post(
            reverse("accounts:rim_create_account"),
            data={"kind": "teacher", **base_payload(fin="2KKKKK2")},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "permission_denied")

    def test_create_endpoint_creates_and_returns_the_password_once(self):
        response = self.client_for(self.rim).post(
            reverse("accounts:rim_create_account"),
            data={"kind": "teacher", **base_payload(fin="3LLLLL3")},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["password"])
        created = User.objects.get(pk=payload["user_id"])
        self.assertTrue(created.check_password(payload["password"]))

    def test_create_endpoint_returns_field_errors(self):
        response = self.client_for(self.rim).post(
            reverse("accounts:rim_create_account"),
            data={"kind": "student", **base_payload(fin="bad", group="")},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.json()["fields"]), {"fin", "group"})

    def test_unknown_kind_is_rejected(self):
        response = self.client_for(self.rim).post(
            reverse("accounts:rim_create_account"),
            data={"kind": "superadmin", **base_payload(fin="4MMMMM4")},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "account_kind_unknown")

    def test_catalog_endpoint_shape_and_gate(self):
        url = reverse("accounts:rim_create_catalog")
        response = self.client_for(self.rim).get(url, {"catalog": "group", "q": "SI-1"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("results", payload)
        self.assertIn("has_more", payload)
        self.assertEqual([row["text"] for row in payload["results"]], ["SI-101"])

        self.assertEqual(self.client_for(self.rim_staff).get(url, {"catalog": "group"}).status_code, 403)

    def test_catalog_rejects_unknown_collection(self):
        response = self.client_for(self.rim).get(reverse("accounts:rim_create_catalog"), {"catalog": "users"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"], [])

    def test_catalog_is_tenant_scoped_to_chairs(self):
        response = self.client_for(self.rim).get(reverse("accounts:rim_create_catalog"), {"catalog": "unit"})
        self.assertEqual([row["text"] for row in response.json()["results"]], ["Kompüter kafedrası"])


@override_settings(RATELIMIT_ENABLE=False)
class RimBulkSurfaceTest(RimCreateBase):
    """Toplu axın — RİM konsolu MÖVCUD idxal endpoint-lərini çağırır."""

    def test_section_carries_the_intake_endpoints(self):
        response = self.client_for(self.rim).get(reverse("accounts:profile"), {"section": "rim-center"})
        section = response.context["rim_center_section"]
        self.assertEqual(section["intake_preview_url"], reverse("accounts:student_intake_preview"))
        self.assertEqual(section["intake_apply_url"], reverse("accounts:student_intake_apply"))
        self.assertEqual(section["intake_template_url"], reverse("accounts:student_intake_template"))
        self.assertContains(response, "data-rimb-drop")

    def test_preview_shape(self):
        response = self.preview(self.rim, [student_row("5NNNNN5", "Aysel", "Quliyeva")])
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["summary"]["create"], 1)
        row = payload["rows"][0]
        for key in ("row", "status", "fin", "full_name", "group", "username", "warnings"):
            self.assertIn(key, row)
        self.assertFalse(User.objects.filter(profile__fin="5NNNNN5").exists())

    def test_apply_twice_creates_only_once(self):
        rows = [student_row("6OOOOO6", "Rəna", "Məmmədova")]
        first = self.apply(self.rim, rows).json()
        self.assertEqual(first["summary"]["created"], 1)

        second = self.apply(self.rim, rows).json()
        self.assertEqual(second["summary"]["created"], 0)
        self.assertEqual(second["summary"]["skip"], 1)
        self.assertEqual(User.objects.filter(profile__fin="6OOOOO6").count(), 1)

    def test_bulk_and_single_share_the_same_gate(self):
        client = Client()
        client.force_login(self.rim_staff)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        self.assertEqual(client.post(reverse("accounts:student_intake_preview"), {}).status_code, 403)
        self.assertEqual(
            client.post(
                reverse("accounts:rim_create_account"),
                data={"kind": "teacher"},
                content_type="application/json",
            ).status_code,
            403,
        )


@override_settings(RATELIMIT_ENABLE=True)
class RimCreateRateLimitTest(RimCreateBase):
    """Kütləvi yaratmanın qarşısı — aktor başına saatlıq hədd."""

    @override_settings(RIM_ACCOUNT_CREATE_RATE_LIMIT="1/h")
    def test_second_create_is_rate_limited(self):
        self.create(self.rim, "teacher", fin="7PPPPP7")
        with self.assertRaises(rim_create.RimCreateError) as caught:
            self.create(self.rim, "teacher", fin="8QQQQQ8")
        self.assertEqual(caught.exception.status, 429)
        self.assertFalse(User.objects.filter(profile__fin="8QQQQQ8").exists())


class IntakeCoreSharingTest(RimCreateBase):
    """Toplu və tək-tək axının EYNİ nüvədən keçdiyini sabitləyir."""

    def test_bulk_apply_uses_the_shared_core(self):
        from apps.accounts.services.intake import apply as intake_apply
        from apps.accounts.services.intake import create as intake_core

        self.assertIs(intake_apply.student_role, intake_core.student_role)
        self.assertIs(intake_apply.generate_initial_password, intake_core.generate_initial_password)

    def test_username_base_is_kind_aware(self):
        from apps.accounts.services.intake import create as intake_core

        self.assertEqual(intake_core.username_base("student", code="ST-5", fin="1AAAAA1"), "st.st-5")
        self.assertEqual(intake_core.username_base("teacher", code="", fin="1AAAAA1"), "mu.fin.1aaaaa1")
