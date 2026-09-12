"""P1-11 (2026-09-12 audit) — TƏK sərt scope həlledicisi.

Tapıntı: ``apps/organizations/scoping.py``-də iki paralel resolver var idi.
Köhnə ``get_unit_scope`` rolun ``scope_type``-ına və icazəsinə BAXMADAN hər
aktiv üzvlüyün ``scope_unit``-ini toplayırdı — yəni dekanın başqa fakültənin
kafedrasına MÜƏLLİM kimi təyinatı həmin kafedranı dekan səlahiyyətinə (üzv
siyahısı, akademik qeydlər, statistika, imtahanlar, qruplar, «view-as»…)
«borc verirdi». Sərt ``get_permission_scope`` isə YALNIZ tələb olunan açarı
daşıyan üzvlükdən əhatə çıxarır. Köhnəsi silindi; bu modul hər köçürülmüş
çağıran üçün üç şeyi kilidləyir:

  (a) imtiyazlı rol + ƏLAQƏSİZ unit üzvlüyü → əlaqəsiz unit borc VERİLMİR;
  (b) qanuni unit-əhatəli aktor öz alt-ağacını görməyə DAVAM edir;
  (c) ``get_unit_scope`` artıq mövcud deyil (qoruyucu test).

Fikstur: Fakültə A (dekanın əhatəsi) → kafedra A1; Fakültə B → kafedra B1.
``dean_lent`` — dekan (scope_unit=A) + müəllim üzvlüyü (scope_unit=B1);
``dean_unscoped_lent`` — scope_unit-siz dekan + müəllim üzvlüyü (B1).
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse

from apps.exams.forms import StudentGroupForm
from apps.exams.models import Exam, StudentGroup
from apps.exams.views.teacher.groups import _group_queryset_for_actor
from apps.organizations import public as org_public
from apps.organizations import scoping
from apps.organizations.models import Membership, Organization, OrgUnit
from apps.organizations.scoping import get_permission_scope, scope_org_units
from apps.organizations.structure_views.members import build_members_section, resolve_members_access
from apps.organizations.views.org_admin.context import (
    build_organization_members_context,
    build_organization_structure_context,
)
from apps.organizations.views.shared._helpers import _get_structure_scope
from core.constants import OrganizationType, OrgUnitType

User = get_user_model()

PASSWORD = "StrongPass123!"


# ─── Fikstur köməkçiləri ────────────────────────────────────────────────────


def _user(username):
    return User.objects.create_user(username, f"{username}@p111.test", PASSWORD)


def _member(org, user, role_name, scope_unit=None, *, is_primary=True):
    return Membership.objects.create(
        user=user,
        organization=org,
        role=org.roles.get(name=role_name),
        scope_unit=scope_unit,
        is_primary=is_primary,
        is_active=True,
    )


def _request(user, org, path="/", data=None):
    """Middleware-in qurduğu request kontekstinin minimal surəti."""
    request = RequestFactory().get(path, data or {})
    request.user = user
    request.organization = org
    memberships = list(
        Membership.objects.filter(user=user, organization=org, is_active=True).select_related("role", "scope_unit")
    )
    permissions = set()
    for membership in memberships:
        permissions.update(membership.role.permissions or [])
    request.org_memberships = memberships
    request.org_permissions = list(permissions)
    user.set_active_organization_context(org, memberships=memberships, permissions=list(permissions))
    return request


def _client(user, org):
    client = Client()
    client.force_login(user)
    session = client.session
    session["active_organization"] = org.slug
    session.save()
    return client


class _WorldMixin:
    """İki fakültəli təşkilat + «borc verən» üzvlük kombinasiyaları."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = _user("p111_owner")
        cls.org = Organization.objects.create(
            name="P1-11 University",
            slug="p1-11-university",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        cls.faculty_a = OrgUnit.objects.create(organization=cls.org, unit_type=OrgUnitType.FACULTY, name="Fakültə A")
        cls.chair_a1 = OrgUnit.objects.create(
            organization=cls.org, unit_type=OrgUnitType.CHAIR, name="Kafedra A1", parent=cls.faculty_a
        )
        cls.faculty_b = OrgUnit.objects.create(organization=cls.org, unit_type=OrgUnitType.FACULTY, name="Fakültə B")
        cls.chair_b1 = OrgUnit.objects.create(
            organization=cls.org, unit_type=OrgUnitType.CHAIR, name="Kafedra B1", parent=cls.faculty_b
        )

        # (a) imtiyazlı rol + ƏLAQƏSİZ unit üzvlüyü.
        cls.dean_lent = _user("p111_dean_lent")
        _member(cls.org, cls.dean_lent, "dean", cls.faculty_a)
        _member(cls.org, cls.dean_lent, "teacher", cls.chair_b1, is_primary=False)
        # scope_unit-siz UNIT rolu + əlaqəsiz üzvlük — heç nə görməməlidir.
        cls.dean_unscoped_lent = _user("p111_dean_unscoped")
        _member(cls.org, cls.dean_unscoped_lent, "dean", None)
        _member(cls.org, cls.dean_unscoped_lent, "teacher", cls.chair_b1, is_primary=False)
        # (b) qanuni unit-əhatəli aktorlar.
        cls.dean_plain = _user("p111_dean_plain")
        _member(cls.org, cls.dean_plain, "dean", cls.faculty_a)
        cls.vice_dean = _user("p111_vice_dean")
        _member(cls.org, cls.vice_dean, "vice_dean", cls.faculty_a)
        cls.tutor = _user("p111_tutor")
        _member(cls.org, cls.tutor, "tutor", cls.faculty_a)
        # ORGANIZATION əhatəli rollar.
        cls.hr = _user("p111_hr")
        _member(cls.org, cls.hr, "hr")
        cls.vice_rector = _user("p111_vice_rector")
        _member(cls.org, cls.vice_rector, "vice_rector")
        # Hədəf üzvlər.
        cls.student_a = _user("p111_student_a")
        _member(cls.org, cls.student_a, "student", cls.chair_a1)
        cls.student_b = _user("p111_student_b")
        _member(cls.org, cls.student_b, "student", cls.chair_b1)
        cls.teacher_a = _user("p111_teacher_a")
        _member(cls.org, cls.teacher_a, "teacher", cls.chair_a1)
        cls.teacher_b = _user("p111_teacher_b")
        _member(cls.org, cls.teacher_b, "teacher", cls.chair_b1)

    def _subtree_a_ids(self):
        return {self.faculty_a.pk, self.chair_a1.pk}


# ─── (c) Qoruyucu — köhnə resolver yoxdur ───────────────────────────────────


class LegacyResolverRemovedTest(SimpleTestCase):
    def test_get_unit_scope_no_longer_exists(self):
        self.assertFalse(hasattr(scoping, "get_unit_scope"))
        self.assertFalse(hasattr(scoping, "_resolve_unit_scope"))
        self.assertNotIn("get_unit_scope", scoping.__all__)
        self.assertFalse(hasattr(org_public, "get_unit_scope"))
        self.assertNotIn("get_unit_scope", org_public.__all__)

    def test_empty_permission_is_rejected_not_org_wide(self):
        """Boş açar səssiz ORG_WIDE ola bilməz — fail-closed, proqramçı xətası."""
        with self.assertRaises(ValueError):
            get_permission_scope(None, None, "")
        with self.assertRaises(ValueError):
            get_permission_scope(None, None, None)

    def test_scope_helpers_require_a_permission(self):
        """Açarsız qollar resolverlə birlikdə silindi — `permission` məcburidir."""
        with self.assertRaises(TypeError):
            scoping.user_scope_covers_unit(None, None, None)
        with self.assertRaises(TypeError):
            scoping.user_scope_subtree_q(None, None, path_field="path", id_field="id")


# ─── Sərt resolver semantikası ──────────────────────────────────────────────


class StrictResolverSemanticsTest(_WorldMixin, TestCase):
    def test_unrelated_teacher_membership_does_not_lend_its_unit(self):
        for permission in ("unit.view", "member.view", "grade.view", "exam.view", "group.manage"):
            with self.subTest(permission=permission):
                scope = get_permission_scope(self.dean_lent, self.org, permission)
                self.assertTrue(scope.is_unit_scoped)
                self.assertEqual(set(scope.unit_ids), {self.faculty_a.pk})
                self.assertNotIn(self.chair_b1.pk, scope.unit_ids)

    def test_unit_role_without_scope_unit_stays_empty_despite_unrelated_membership(self):
        for permission in ("unit.view", "member.view", "grade.view", "exam.view", "group.manage"):
            with self.subTest(permission=permission):
                scope = get_permission_scope(self.dean_unscoped_lent, self.org, permission)
                self.assertFalse(scope.has_structure_access)

    def test_organization_role_is_org_wide_regardless_of_level(self):
        """Köhnə resolver ORGANIZATION rolunu yalnız level ≥ 90-da org-wide sayırdı (HR 65 boş qalırdı)."""
        self.assertTrue(get_permission_scope(self.hr, self.org, "member.view").is_org_wide)
        self.assertTrue(get_permission_scope(self.vice_rector, self.org, "analytics.view_all").is_org_wide)
        # Açar yoxdursa ORGANIZATION rolu da əhatə vermir.
        self.assertFalse(get_permission_scope(self.vice_rector, self.org, "analytics.view_unit").has_structure_access)

    def test_query_budget_does_not_grow_with_the_number_of_keys(self):
        """Soyuq: üzvlük SELECT + OrgUnit path SELECT = 2 sorğu; eyni istifadəçi
        üçün ikinci açar (eyni unit dəsti) = 0 — üzvlük və path-lər `user`
        obyektində memoizasiya olunur. Köhnə resolver hər çağırışda 2 sorğu
        atırdı, indi çağıranlar iki açarla (statistika, qruplar) da bahalaşmır."""
        dean = User.objects.select_related("profile").get(pk=self.dean_lent.pk)
        with self.assertNumQueries(2):
            get_permission_scope(dean, self.org, "unit.view")
        with self.assertNumQueries(0):
            get_permission_scope(dean, self.org, "member.view")
        hr = User.objects.select_related("profile").get(pk=self.hr.pk)
        with self.assertNumQueries(1):  # ORGANIZATION rolu — path sorğusu lazım deyil
            get_permission_scope(hr, self.org, "member.view")

    def test_request_cache_is_keyed_by_permission(self):
        request = _request(self.dean_plain, self.org)
        first = get_permission_scope(self.dean_plain, self.org, "unit.view", request=request)
        with self.assertNumQueries(0):
            again = get_permission_scope(self.dean_plain, self.org, "unit.view", request=request)
        self.assertIs(first, again)
        self.assertIn(("permission", self.dean_plain.pk, self.org.pk, "unit.view"), request._unit_scope_cache)


# ─── Struktur səthləri: `_get_structure_scope` (unit.view) ──────────────────


class StructureScopeCallersTest(_WorldMixin, TestCase):
    def _detail_url(self, unit):
        return reverse("organizations:structure_unit_detail", kwargs={"slug": self.org.slug, "unit_id": unit.id})

    def test_helper_uses_unit_view_scope_without_lent_unit(self):
        scope = _get_structure_scope(_request(self.dean_lent, self.org), self.org)
        self.assertEqual(set(scope.unit_ids), {self.faculty_a.pk})

    def test_unit_detail_modal_does_not_open_lent_kafedra(self):
        client = _client(self.dean_lent, self.org)
        own = client.get(self._detail_url(self.chair_a1), HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(own.status_code, 200)
        lent = client.get(self._detail_url(self.chair_b1), HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(lent.status_code, 404)

    def test_unscoped_dean_gets_nothing_on_legacy_structure_context(self):
        """Əvvəl əhatəsiz qol BÜTÜN kök vahidləri siyahılayırdı (fail-open)."""
        context = build_organization_structure_context(_request(self.dean_unscoped_lent, self.org), self.org)
        self.assertEqual(context["units"], [])
        self.assertEqual(context["unit_total_count"], 0)
        self.assertFalse(context["can_create_faculty"])
        client = _client(self.dean_unscoped_lent, self.org)
        self.assertEqual(
            client.get(self._detail_url(self.chair_b1), HTTP_X_REQUESTED_WITH="XMLHttpRequest").status_code, 404
        )

    def test_plain_dean_still_sees_own_faculty(self):
        context = build_organization_structure_context(_request(self.dean_plain, self.org), self.org)
        self.assertEqual([unit.pk for unit in context["units"]], [self.faculty_a.pk])
        self.assertEqual({f.pk for f in context["faculties"]}, {self.faculty_a.pk})
        self.assertEqual({k.pk for k in context["kafedras"]}, {self.chair_a1.pk})

    def test_hr_with_unit_view_is_org_wide_on_structure(self):
        """HR `unit.view` daşıyan ORGANIZATION roludur — köhnə resolver ona (65 < 90) boş əhatə verirdi."""
        scope = _get_structure_scope(_request(self.hr, self.org), self.org)
        self.assertTrue(scope.is_org_wide)
        client = _client(self.hr, self.org)
        self.assertEqual(
            client.get(self._detail_url(self.chair_b1), HTTP_X_REQUESTED_WITH="XMLHttpRequest").status_code, 200
        )


# ─── Üzv siyahıları: `member.view` ──────────────────────────────────────────


class MembersContextCallersTest(_WorldMixin, TestCase):
    def _legacy_member_ids(self, user):
        context = build_organization_members_context(_request(user, self.org), self.org)
        return {membership.user_id for membership in context["members"]}

    def _registry_member_ids(self, user):
        section = build_members_section(_request(user, self.org), self.org)
        self.assertTrue(section["has_access"])
        return {row["user_id"] for row in section["rows"]}

    def test_lent_kafedra_members_are_not_listed(self):
        for ids in (self._legacy_member_ids(self.dean_lent), self._registry_member_ids(self.dean_lent)):
            self.assertIn(self.student_a.id, ids)
            self.assertIn(self.teacher_a.id, ids)
            self.assertNotIn(self.student_b.id, ids)
            self.assertNotIn(self.teacher_b.id, ids)

    def test_unscoped_dean_sees_nobody(self):
        self.assertEqual(self._legacy_member_ids(self.dean_unscoped_lent), set())
        access = resolve_members_access(_request(self.dean_unscoped_lent, self.org), self.org)
        self.assertTrue(access.scope_unset)
        self.assertEqual(access.memberships.count(), 0)

    def test_plain_dean_and_hr_regressions(self):
        dean_ids = self._registry_member_ids(self.dean_plain)
        self.assertIn(self.student_a.id, dean_ids)
        self.assertNotIn(self.student_b.id, dean_ids)
        hr_ids = self._registry_member_ids(self.hr)
        self.assertIn(self.student_a.id, hr_ids)
        self.assertIn(self.student_b.id, hr_ids)
        self.assertTrue(resolve_members_access(_request(self.hr, self.org), self.org).is_org_wide)

    def test_members_page_for_lent_dean(self):
        response = _client(self.dean_lent, self.org).get(
            reverse("organizations:members", kwargs={"slug": self.org.slug})
        )
        self.assertEqual(response.status_code, 200)
        ids = {membership.user_id for membership in response.context["members"]}
        self.assertIn(self.student_a.id, ids)
        self.assertNotIn(self.student_b.id, ids)

    def test_actions_column_has_a_screen_reader_label(self):
        """P2-8: əməllər sütununun `<th>`-i boş qalmır — etiket ekran oxuyucu üçün gizlidir."""
        section = build_members_section(_request(self.owner, self.org), self.org)
        actions = section["columns"][-1]
        self.assertEqual(actions["key"], "actions")
        self.assertTrue(actions["sr_only"])
        self.assertTrue(str(actions["label"]).strip())


# ─── «Heyət idarəetməsi» reyestri (accounts) ────────────────────────────────


class StaffManagementRegistryScopeTest(_WorldMixin, TestCase):
    def _section(self, user, level):
        from apps.accounts.views._helpers.org_sections import _build_student_org_management_section

        request = _request(user, self.org, "/profile/", {"section": "student-organization-management"})
        return _build_student_org_management_section(
            request=request, organization=self.org, is_superadmin=False, user_level=level
        )

    def test_lent_kafedra_is_excluded(self):
        section = self._section(self.dean_lent, 80)
        self.assertTrue(section["unit_scope_active"])
        ids = {row["user_id"] for row in section["rows"]}
        self.assertIn(self.student_a.id, ids)
        self.assertNotIn(self.student_b.id, ids)

    def test_unscoped_dean_sees_nobody_instead_of_the_whole_org(self):
        section = self._section(self.dean_unscoped_lent, 80)
        self.assertTrue(section["unit_scope_active"])
        self.assertEqual(section["rows"], [])
        self.assertEqual(section["member_total_count"], 0)

    def test_hr_is_org_wide(self):
        section = self._section(self.hr, 65)
        self.assertFalse(section["unit_scope_active"])
        ids = {row["user_id"] for row in section["rows"]}
        self.assertIn(self.student_a.id, ids)
        self.assertIn(self.student_b.id, ids)

    def test_actions_column_has_a_screen_reader_label(self):
        """P2-8: staff-management cədvəlinin əməllər sütunu."""
        from apps.accounts.views._helpers.org_sections._members_ui import columns

        actions = columns()[-1]
        self.assertEqual(actions["key"], "actions")
        self.assertTrue(actions["sr_only"])
        self.assertTrue(str(actions["label"]).strip())


# ─── Akademik qeydlər (grade.view) ──────────────────────────────────────────


class AcademicRecordsScopeTest(_WorldMixin, TestCase):
    def _scope(self, user):
        from apps.accounts.views.academic_records import _scope

        return _scope(_request(user, self.org))

    def test_lent_kafedra_is_outside_the_records_scope(self):
        organization, scope = self._scope(self.dean_lent)
        self.assertIs(organization, self.org)
        self.assertEqual(set(scope.unit_ids), {self.faculty_a.pk})
        visible = set(scope_org_units(OrgUnit.objects.filter(organization=self.org), scope))
        self.assertEqual(visible, {self.faculty_a, self.chair_a1})

    def test_unscoped_dean_has_no_records_scope(self):
        organization, scope = self._scope(self.dean_unscoped_lent)
        self.assertIs(organization, self.org)
        self.assertFalse(scope.has_structure_access)

    def test_role_gate_still_runs_before_scope(self):
        self.assertEqual(self._scope(self.teacher_a), (None, None))
        self.assertEqual(self._scope(self.hr), (None, None))

    def test_central_and_plain_dean_regressions(self):
        exam_center = _user("p111_exam_center")
        _member(self.org, exam_center, "exam_center_head")
        _organization, scope = self._scope(exam_center)
        self.assertTrue(scope.is_org_wide)
        _organization, dean_scope = self._scope(self.dean_plain)
        self.assertEqual(set(dean_scope.unit_ids), {self.faculty_a.pk})


# ─── Statistika (analytics.view_all → analytics.view_unit) ──────────────────


class StatisticsScopeTest(_WorldMixin, TestCase):
    def _statistics_scope(self, user):
        from apps.accounts.views.profile._sections.statistics import statistics_scope

        return statistics_scope(_request(user, self.org), self.org)

    def test_two_step_resolution(self):
        self.assertEqual(set(self._statistics_scope(self.dean_lent).unit_ids), {self.faculty_a.pk})
        self.assertTrue(self._statistics_scope(self.vice_rector).is_org_wide)  # yalnız analytics.view_all
        self.assertTrue(self._statistics_scope(self.hr).is_org_wide)  # analytics.view_unit, ORGANIZATION
        self.assertFalse(self._statistics_scope(self.dean_unscoped_lent).has_structure_access)
        self.assertFalse(self._statistics_scope(self.teacher_a).has_structure_access)

    def _captured_scoped_ids(self, run):
        calls = []

        def fake_org_admin_statistics(*, organization, filters=None, scoped_unit_ids=None):
            calls.append(scoped_unit_ids)
            return {"summary": {}}

        with (
            mock.patch("core.cache.get_or_set_cached_statistics", side_effect=lambda **kw: kw["compute"]()),
            mock.patch(
                "apps.accounts.services.statistics_selectors.get_org_admin_statistics",
                side_effect=fake_org_admin_statistics,
            ),
        ):
            run()
        self.assertEqual(len(calls), 1)
        return calls[0]

    def _section_run(self, user):
        from apps.accounts.views.profile._sections.statistics import build_statistics_section

        capabilities = {"is_superadmin": False, "is_org_admin": True, "is_teacher": False, "is_tutor": False}
        request = _request(user, self.org, "/profile/", {"section": "statistics"})
        return lambda: build_statistics_section(request, capabilities=capabilities)

    def test_dashboard_scoped_ids_exclude_lent_kafedra(self):
        scoped = self._captured_scoped_ids(self._section_run(self.dean_lent))
        self.assertEqual(set(scoped), self._subtree_a_ids())

    def test_dashboard_unscoped_dean_is_fail_closed_not_org_wide(self):
        self.assertEqual(self._captured_scoped_ids(self._section_run(self.dean_unscoped_lent)), [])

    def test_dashboard_vice_rector_stays_org_wide(self):
        self.assertIsNone(self._captured_scoped_ids(self._section_run(self.vice_rector)))

    def test_csv_export_mirrors_the_dashboard_scope(self):
        url = reverse("accounts:statistics_export_csv")
        lent = self._captured_scoped_ids(lambda: _client(self.dean_lent, self.org).get(url))
        self.assertEqual(set(lent), self._subtree_a_ids())
        unscoped = self._captured_scoped_ids(lambda: _client(self.dean_unscoped_lent, self.org).get(url))
        self.assertEqual(unscoped, [])


# ─── «unit-exams» bölməsi (exam.view) ───────────────────────────────────────


class UnitExamsScopeTest(_WorldMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.exam_a = Exam.objects.create(title="A imtahanı", author=cls.teacher_a, organization=cls.org)
        cls.exam_b = Exam.objects.create(title="B imtahanı", author=cls.teacher_b, organization=cls.org)

    def _exam_ids(self, user):
        from apps.accounts.views.profile._sections.unit_exams import build_unit_exams_context

        context = build_unit_exams_context(
            _request(user, self.org, "/profile/", {"section": "unit-exams"}),
            allowed_sections={"unit-exams"},
            active_section="unit-exams",
        )
        page = context["unit_exams_page_obj"]
        return None if page is None else {exam.id for exam in page.object_list}

    def test_lent_kafedra_exams_are_not_shown(self):
        ids = self._exam_ids(self.dean_lent)
        self.assertIn(self.exam_a.id, ids)
        self.assertNotIn(self.exam_b.id, ids)

    def test_unscoped_dean_gets_defaults(self):
        self.assertIsNone(self._exam_ids(self.dean_unscoped_lent))

    def test_plain_dean_regression(self):
        self.assertEqual(self._exam_ids(self.dean_plain), {self.exam_a.id})


# ─── «View as» hədəfləri (member.view) ──────────────────────────────────────


class ViewAsScopeTest(_WorldMixin, TestCase):
    def _target(self, actor, target):
        from apps.accounts.services.view_as import validate_target

        return validate_target(actor, self.org, target.pk)[0]

    def test_lent_kafedra_student_is_not_a_target(self):
        self.assertIsNotNone(self._target(self.dean_lent, self.student_a))
        self.assertIsNone(self._target(self.dean_lent, self.student_b))

    def test_unscoped_dean_has_no_targets(self):
        self.assertIsNone(self._target(self.dean_unscoped_lent, self.student_a))
        self.assertIsNone(self._target(self.dean_unscoped_lent, self.student_b))

    def test_plain_dean_regression(self):
        self.assertIsNotNone(self._target(self.dean_plain, self.student_a))
        self.assertIsNone(self._target(self.dean_plain, self.student_b))


# ─── Qruplar: forma (group.manage) + siyahı (group.manage → group.view) ─────


class GroupScopeTest(_WorldMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.group_a1 = StudentGroup.objects.create(
            teacher=cls.teacher_a, organization=cls.org, name="A1 qrup", org_unit=cls.chair_a1
        )
        cls.group_b1 = StudentGroup.objects.create(
            teacher=cls.teacher_b, organization=cls.org, name="B1 qrup", org_unit=cls.chair_b1
        )

    def _form_unit_ids(self, user):
        form = StudentGroupForm(actor=user, organization=self.org)
        return set(form.fields["org_unit"].queryset.values_list("pk", flat=True))

    def _visible_groups(self, user):
        request = _request(user, self.org)
        return set(_group_queryset_for_actor(request, self.org).values_list("name", flat=True))

    def test_form_unit_choices_exclude_lent_kafedra(self):
        self.assertEqual(self._form_unit_ids(self.dean_lent), self._subtree_a_ids())
        self.assertEqual(self._form_unit_ids(self.dean_unscoped_lent), set())
        self.assertEqual(self._form_unit_ids(self.dean_plain), self._subtree_a_ids())
        self.assertEqual(self._form_unit_ids(self.vice_rector), set(self.org.units.values_list("pk", flat=True)))

    def test_group_list_excludes_lent_kafedra(self):
        self.assertEqual(self._visible_groups(self.dean_lent), {"A1 qrup"})
        self.assertEqual(self._visible_groups(self.dean_unscoped_lent), set())

    def test_read_only_and_curator_roles_keep_their_subtree(self):
        # Dekan müavini yalnız `group.view` daşıyır → fallback açar işləyir.
        self.assertEqual(self._visible_groups(self.vice_dean), {"A1 qrup"})
        # Tyutor `group.manage` daşıyır (sahib qərarı 2026-09-07).
        self.assertEqual(self._visible_groups(self.tutor), {"A1 qrup"})
        self.assertEqual(self._visible_groups(self.vice_rector), {"A1 qrup", "B1 qrup"})


# ─── İdarəetmə qapısı: muaf rollar (imtahan mərkəzi, Tədris şöbəsi) ─────────


class ManageGateExemptRolesTest(_WorldMixin, TestCase):
    """`_can_manage_organization` `ADMIN_ALIAS_EXEMPT_ROLE_NAMES`-ə tabedir.

    Sərt resolver `unit.view`-lu ORGANIZATION rolunu org-wide edir; xam
    `level >= 80` qapısı ilə birlikdə bu, imtahan mərkəzi rəhbərinə (85) legacy
    fakültə/kafedra əməllərini AÇARDI — köhnə boş resolverdə (level < 90 → boş
    əhatə) həmin yol təsadüfən bağlı idi. Qapı alias qaydasına bağlandı.
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.exam_center_head = _user("p111_exam_center_head")
        _member(cls.org, cls.exam_center_head, "exam_center_head")
        cls.teaching_office_head = _user("p111_teaching_office_head")
        _member(cls.org, cls.teaching_office_head, "teaching_office_head")

    def test_exempt_roles_are_not_org_managers_but_admin_equivalents_still_are(self):
        from apps.organizations.views.shared._helpers import _can_manage_organization

        self.assertFalse(_can_manage_organization(self.exam_center_head, self.org))
        self.assertFalse(_can_manage_organization(self.teaching_office_head, self.org))
        self.assertFalse(_can_manage_organization(self.hr, self.org))
        self.assertTrue(_can_manage_organization(self.dean_plain, self.org))
        self.assertTrue(_can_manage_organization(self.vice_rector, self.org))
        self.assertTrue(_can_manage_organization(self.owner, self.org))

    def test_exam_center_head_cannot_create_a_faculty_through_the_legacy_handler(self):
        url = reverse("organizations:structure_faculties", kwargs={"slug": self.org.slug})
        client = _client(self.exam_center_head, self.org)
        before = OrgUnit.objects.filter(organization=self.org, unit_type=OrgUnitType.FACULTY).count()
        response = client.post(
            url, {"action": "create", "name": "Yad fakültə", "code": "YF"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])
        self.assertEqual(OrgUnit.objects.filter(organization=self.org, unit_type=OrgUnitType.FACULTY).count(), before)
        # Oxu (`unit.view`) isə rol kataloquna görə açıqdır — detal modalı 200.
        detail = client.get(
            reverse("organizations:structure_unit_detail", kwargs={"slug": self.org.slug, "unit_id": self.chair_b1.id}),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(detail.status_code, 200)

    def test_dean_keeps_creating_kafedras_under_own_faculty(self):
        """Reqressiya: dekanın (admin-ekvivalent) legacy kafedra yaratması dəyişmir."""
        url = reverse("organizations:structure_kafedras", kwargs={"slug": self.org.slug})
        client = _client(self.dean_plain, self.org)
        response = client.post(
            url,
            {"action": "create", "name": "Yeni kafedra", "code": "YK", "parent": str(self.faculty_a.id)},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200, response.content[:300])
        self.assertTrue(
            OrgUnit.objects.filter(organization=self.org, name="Yeni kafedra", parent=self.faculty_a).exists()
        )
        # Başqa fakültənin altında YOX (əhatə).
        response = client.post(
            url,
            {"action": "create", "name": "Yad kafedra", "code": "YDK", "parent": str(self.faculty_b.id)},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(OrgUnit.objects.filter(organization=self.org, name="Yad kafedra").exists())
