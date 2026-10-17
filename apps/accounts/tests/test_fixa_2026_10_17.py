"""FIX-A (QA 2026-10-17) — oxu əhatəsi və şəxsi məlumat sızmaları.

* QA-2 F-04 — ümumi profil (`/accounts/users/<ad>/`) tələbənin e-poçtunu / telefonunu yalnız tələbəni öz
  kataloq əhatəsində görənə (reyestr/«İnsanlar» kartı ilə eyni qayda) göstərir.
* QA-2 F-03 — HR (`unit.view`, `user.search`, `user.edit`, tələbə açarı YOX): qrup çekmecəsi 403, fərdi plan
  DOCX 403, RİM mərkəzində tələbə hesabı görünmür / 404.
* QA-2 F-01 / F-02 — «Semestr açılışı» və «Tədris planı» oxusu açarın əhatəsi ilə; «Yeni plan» yalnız
  `plan.edit` əhatəsində ixtisas olanda.
* PERF-1 F-02 — RİM axtarışı: üzvlüklər bir sorğu ilə, `.distinct()` çıxarılıb və sətir dublikatı yoxdur.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from apps.accounts.services.rim import (
    RimAccessError,
    RimActor,
    assert_can_manage,
    manageable_users_queryset,
    prefetch_memberships,
    search_users,
    serialize_row,
)
from apps.organizations.models import Membership
from apps.registrar.public import build_curriculum_editor, build_semester_opening
from core.constants import OrgUnitType, RoleScopeType
from core.rls import bypass_rls

from .people_fixture import PeopleFixture, add_membership, make_role, make_user

HR_PERMS = ["unit.view", "member.view", "user.search", "user.edit", "people.view_teachers"]
OFFICE_PERMS = ["unit.view", "unit.group_manage", "student.records_view"]
SEM_UNIT_PERMS = ["semester.view", "plan.view", "plan.edit"]
RIM_PERMS = ["semester.view", "plan.view", "member.view", "user.search", "user.edit", "people.view_students"]


class FixAFixture(PeopleFixture):
    def __init__(self):
        super().__init__()
        with bypass_rls():
            self._build_fixa()

    def _build_fixa(self):
        Subject = django_apps.get_model("registrar", "Subject")
        CourseOffering = django_apps.get_model("registrar", "CourseOffering")
        org = self.org
        self.kafedra_a2 = self._unit("Kafedra A2", "kaf-a2", OrgUnitType.CHAIR, self.faculty_a)

        self.role_hr = make_role(org, "hr_fx", level=65, scope_type=RoleScopeType.ORGANIZATION, permissions=HR_PERMS)
        self.role_office = make_role(
            org, "office_fx", level=60, scope_type=RoleScopeType.ORGANIZATION, permissions=OFFICE_PERMS
        )
        self.role_sem = make_role(org, "sem_fx", level=75, scope_type=RoleScopeType.UNIT, permissions=SEM_UNIT_PERMS)
        self.role_rim = make_role(org, "rim_fx", level=90, scope_type=RoleScopeType.ORGANIZATION, permissions=RIM_PERMS)

        self.hr = make_user("fxa_hr", first="Həcər", last="Kadrova")
        add_membership(org, self.hr, self.role_hr)
        self.office = make_user("fxa_office", first="Ofelya", last="Ofisova")
        add_membership(org, self.office, self.role_office)
        self.rim = make_user("fxa_rim", first="Rimma", last="Rimova")
        add_membership(org, self.rim, self.role_rim)
        self.sem_dean_a = make_user("fxa_sem_dean", first="Səmə", last="Dekanova")
        add_membership(org, self.sem_dean_a, self.role_sem, unit=self.faculty_a)
        self.sem_chair_b = make_user("fxa_sem_chair_b", first="Bəxtiyar", last="Kafedrov")
        add_membership(org, self.sem_chair_b, self.role_sem, unit=self.kafedra_b1)
        # İxtisası OLMAYAN kafedra: oxu fakültəyə genişlənir, yazı (plan.edit) əhatəsi boşdur.
        self.sem_chair_a2 = make_user("fxa_sem_chair_a2", first="Arzu", last="Kafedrova")
        add_membership(org, self.sem_chair_a2, self.role_sem, unit=self.kafedra_a2)

        self.subject_a = Subject.objects.create(
            organization=org, code="FXA-A", name="Fənn A", chair_unit=self.kafedra_a1
        )
        self.subject_b = Subject.objects.create(
            organization=org, code="FXA-B", name="Fənn B", chair_unit=self.kafedra_b1
        )
        self.offering_chair_a = CourseOffering.objects.create(
            organization=org, subject=self.subject_a, period=self.period, group=self.group_a1
        )
        self.offering_chair_b = CourseOffering.objects.create(
            organization=org, subject=self.subject_b, period=self.period, group=self.group_b1
        )
        # Dekan A-nın qrupuna B kafedrasının fənni — dekan görür (qrup), kafedra B müdiri də görür (fənn).
        self.offering_b_to_group_a = CourseOffering.objects.create(
            organization=org, subject=self.subject_b, period=self.period, group=self.group_a1
        )


def _client(user, organization):
    client = Client()
    client.force_login(user)
    session = client.session
    session["active_organization"] = organization.slug
    session.save()
    return client


def _request(user, organization, role, **params):
    request = RequestFactory().get("/accounts/profile/", params)
    request.user = user
    request.organization = organization
    request.org_permissions = list(role.permissions)
    return request


class _Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.fx = FixAFixture()

    def get(self, user, url, **params):
        with bypass_rls():
            return _client(user, self.fx.org).get(url, params)


# ── QA-2 F-04 ─────────────────────────────────────────────────────────────────────────────────────────


class PublicProfileStudentPiiTest(_Base):
    PHONE = "+994500000000"

    def profile(self, viewer, target):
        response = self.get(viewer, reverse("accounts:public_profile", args=[target.username]))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_out_of_scope_dean_sees_minimal_card(self):
        html = self.profile(self.fx.dean_a, self.fx.student_b)
        self.assertNotIn(self.PHONE, html)
        self.assertNotIn(self.fx.student_b.email, html)

    def test_in_scope_dean_sees_contact(self):
        self.assertIn(self.PHONE, self.profile(self.fx.dean_b, self.fx.student_b))

    def test_hr_without_student_key_sees_no_student_email(self):
        html = self.profile(self.fx.hr, self.fx.student_b)
        self.assertNotIn(self.fx.student_b.email, html)
        self.assertNotIn(self.PHONE, html)

    def test_hr_still_sees_staff_email(self):
        self.assertIn(self.fx.teacher_b.email, self.profile(self.fx.hr, self.fx.teacher_b))

    def test_org_wide_student_key_sees_student_email(self):
        self.assertIn(self.fx.student_b.email, self.profile(self.fx.rim, self.fx.student_b))


# ── QA-2 F-03 ─────────────────────────────────────────────────────────────────────────────────────────


class GroupStudentsDrawerTest(_Base):
    def url(self):
        return reverse("organizations:group_students", args=[self.fx.org.slug, self.fx.group_a1.pk])

    def test_hr_gets_403_on_drawer(self):
        response = self.get(self.fx.hr, self.url())
        self.assertEqual(response.status_code, 403)
        self.assertNotIn(self.fx.student_a.username, response.content.decode())

    def test_teaching_office_still_gets_students(self):
        response = self.get(self.fx.office, self.url())
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.fx.student_a.username, [row["username"] for row in response.json()["rows"]])

    def test_hr_gets_403_on_individual_plan_docx(self):
        response = self.get(self.fx.hr, reverse("registrar:group_individual_plan", args=[self.fx.group_a1.pk]))
        self.assertEqual(response.status_code, 403)

    def test_registry_rows_hide_student_buttons_for_hr(self):
        from apps.organizations.public import build_groups_registry

        with bypass_rls():
            hr_rows = build_groups_registry(_request(self.fx.hr, self.fx.org, self.fx.role_hr), self.fx.org)["rows"]
            office_rows = build_groups_registry(
                _request(self.fx.office, self.fx.org, self.fx.role_office), self.fx.org
            )["rows"]
        self.assertTrue(hr_rows)
        self.assertFalse(any(row["can_view_students"] for row in hr_rows))
        self.assertTrue(all(row["can_view_students"] for row in office_rows))


def _rim_actor(user, organization, role):
    return RimActor(
        user=user, organization=organization, level=role.level, is_superadmin=False, permissions=set(role.permissions)
    )


class RimStudentAccountsTest(_Base):
    def usernames(self, actor, **kwargs):
        with bypass_rls():
            payload = search_users(actor, page_size=50, **kwargs)
        return {user.username for user in payload["results"]}

    def test_hr_does_not_see_students(self):
        names = self.usernames(_rim_actor(self.fx.hr, self.fx.org, self.fx.role_hr))
        self.assertIn(self.fx.teacher_a.username, names)
        self.assertNotIn(self.fx.student_a.username, names)
        self.assertNotIn(self.fx.student_b.username, names)

    def test_hr_cannot_manage_student(self):
        actor = _rim_actor(self.fx.hr, self.fx.org, self.fx.role_hr)
        with bypass_rls():
            self.assertFalse(manageable_users_queryset(actor).filter(pk=self.fx.student_a.pk).exists())
            with self.assertRaises(RimAccessError) as ctx:
                assert_can_manage(actor, self.fx.student_a)
        self.assertEqual(ctx.exception.status, 404)

    def test_hr_detail_endpoint_is_404_for_student(self):
        response = self.get(self.fx.hr, reverse("accounts:rim_user_detail", args=[self.fx.student_a.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertNotIn(self.fx.student_a.email, response.content.decode())

    def test_hr_detail_endpoint_still_works_for_staff(self):
        response = self.get(self.fx.hr, reverse("accounts:rim_user_detail", args=[self.fx.teacher_a.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["user"]["actions"]["edit"])

    def test_student_key_holder_sees_students(self):
        names = self.usernames(_rim_actor(self.fx.rim, self.fx.org, self.fx.role_rim))
        self.assertIn(self.fx.student_a.username, names)
        self.assertIn(self.fx.teacher_a.username, names)


# ── PERF-1 F-02 ───────────────────────────────────────────────────────────────────────────────────────


class RimSearchNoDuplicatesTest(_Base):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # İkili rol: müəllim + kafedra müdiri — üzvlük JOIN-u əvvəl `.distinct()` ilə «yığılırdı».
        with bypass_rls():
            add_membership(cls.fx.org, cls.fx.teacher_a, cls.fx.role_chair, unit=cls.fx.kafedra_a1)
            add_membership(cls.fx.org, cls.fx.student_a, cls.fx.role_hr)

    def test_search_rows_are_unique_without_distinct(self):
        actor = _rim_actor(self.fx.rim, self.fx.org, self.fx.role_rim)
        with bypass_rls():
            self.assertGreaterEqual(
                Membership.objects.filter(user=self.fx.teacher_a, organization=self.fx.org, is_active=True).count(), 2
            )
            for query in ("", "Əliyev", "ppl"):
                with self.subTest(query=query):
                    payload = search_users(actor, query=query, page_size=50, with_counts=True)
                    ids = [user.pk for user in payload["results"]]
                    self.assertEqual(len(ids), len(set(ids)))
                    self.assertEqual(payload["total"], len(ids))
                    self.assertEqual(payload["counts"]["all"], len(ids))
            self.assertIn(self.fx.teacher_a.pk, [user.pk for user in search_users(actor, page_size=50)["results"]])

    def test_rows_serialize_from_one_prefetch_query(self):
        actor = _rim_actor(self.fx.rim, self.fx.org, self.fx.role_rim)
        with bypass_rls():
            users = search_users(actor, page_size=50)["results"]
            with self.assertNumQueries(1):
                prefetch_memberships(users, self.fx.org)
            with self.assertNumQueries(0):
                rows = {row["username"]: row for row in (serialize_row(user, actor) for user in users)}
        self.assertEqual(
            sorted(role["role_name"] for role in rows[self.fx.teacher_a.username]["roles"]),
            sorted(["teacher", "chair_head"]),
        )


# ── QA-2 F-01 ─────────────────────────────────────────────────────────────────────────────────────────


class SemesterOpeningReadScopeTest(_Base):
    def build(self, user, role):
        with bypass_rls():
            return build_semester_opening(
                _request(user, self.fx.org, role, sm_period=str(self.fx.period.pk)), self.fx.org
            )

    @staticmethod
    def ids(payload):
        return {row["id"] for row in payload["rows"]}

    def test_dean_sees_only_own_faculty(self):
        payload = self.build(self.fx.sem_dean_a, self.fx.role_sem)
        self.assertEqual(
            self.ids(payload),
            {str(self.fx.offering_a.pk), str(self.fx.offering_chair_a.pk), str(self.fx.offering_b_to_group_a.pk)},
        )
        self.assertEqual({row["label"] for row in payload["chair_options"]}, {"Kafedra A1", "Kafedra A2"})
        self.assertEqual(payload["stats"]["total"], 3)
        # Kafedra bölgüsü də yalnız görünən 3 açılış üzrədir (B1 sətri dekanın qrupuna açılan fənn üçündür).
        self.assertEqual(sum(row["total"] for row in payload["chair_rows"]), 3)

    def test_chair_head_sees_only_own_kafedra(self):
        payload = self.build(self.fx.sem_chair_b, self.fx.role_sem)
        self.assertEqual(self.ids(payload), {str(self.fx.offering_chair_b.pk), str(self.fx.offering_b_to_group_a.pk)})
        self.assertEqual([row["label"] for row in payload["chair_options"]], ["Kafedra B1"])

    def test_chair_filter_cannot_widen_scope(self):
        with bypass_rls():
            payload = build_semester_opening(
                _request(
                    self.fx.sem_chair_b,
                    self.fx.org,
                    self.fx.role_sem,
                    sm_period=str(self.fx.period.pk),
                    sm_chair=str(self.fx.kafedra_a1.pk),
                ),
                self.fx.org,
            )
        self.assertEqual(payload["rows"], [])

    def test_org_wide_key_sees_everything(self):
        payload = self.build(self.fx.rim, self.fx.role_rim)
        self.assertEqual(
            self.ids(payload),
            {
                str(self.fx.offering_a.pk),
                str(self.fx.offering_chair_a.pk),
                str(self.fx.offering_chair_b.pk),
                str(self.fx.offering_b_to_group_a.pk),
            },
        )


# ── QA-2 F-02 ─────────────────────────────────────────────────────────────────────────────────────────


class CurriculumEditorReadScopeTest(_Base):
    def build(self, user, role, **params):
        with bypass_rls():
            return build_curriculum_editor(_request(user, self.fx.org, role, **params), self.fx.org)

    def test_dean_sees_only_own_faculty_plans(self):
        payload = self.build(self.fx.sem_dean_a, self.fx.role_sem)
        self.assertEqual({row["value"] for row in payload["plan_options"]}, {str(self.fx.curriculum_a.pk)})
        self.assertEqual({row["value"] for row in payload["program_options"]}, {str(self.fx.program_a.pk)})
        self.assertTrue(payload["can_create"])

    def test_out_of_scope_plan_id_is_not_opened(self):
        payload = self.build(self.fx.sem_dean_a, self.fx.role_sem, cu_plan=str(self.fx.curriculum_b.pk), cu_program="")
        self.assertNotEqual((payload["plan"] or {}).get("id"), str(self.fx.curriculum_b.pk))

    def test_chair_without_programs_reads_faculty_but_cannot_create(self):
        payload = self.build(self.fx.sem_chair_a2, self.fx.role_sem)
        self.assertEqual({row["value"] for row in payload["plan_options"]}, {str(self.fx.curriculum_a.pk)})
        self.assertFalse(payload["can_create"])
        self.assertFalse(payload["can_edit"])

    def test_org_wide_key_sees_all_plans(self):
        payload = self.build(self.fx.rim, self.fx.role_rim)
        self.assertEqual(
            {row["value"] for row in payload["plan_options"]},
            {str(self.fx.curriculum_a.pk), str(self.fx.curriculum_b.pk)},
        )
        # `plan.edit` açarı yoxdur → yaratma yoxdur.
        self.assertFalse(payload["can_create"])
