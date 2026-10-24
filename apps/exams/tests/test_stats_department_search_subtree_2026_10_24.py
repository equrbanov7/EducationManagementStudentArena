"""İmtahan statistikası — kafedra seçicisi (``exams:stats_department_search``) fakültənin ALT-AĞACINI göstərir.

2026-10-24: əvvəl ``parent_id=fakültə`` (yalnız birbaşa uşaq) idi — fakültə ilə kafedra arasında ara
səviyyə olanda kafedra siyahıda çıxmırdı; pozuq ``?faculty=`` isə süzgəci səssizcə atıb BÜTÜN
kafedraları qaytarırdı. ``accounts:records_department_search`` (commit 24b720c) ilə eyni qayda.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org
from apps.organizations.models import Organization, OrgUnit
from core.constants import OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class StatsDepartmentSearchSubtreeTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        owner = User.objects.create_user("sdss_owner", "sdss_owner@test.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="SDSS Uni", org_type=OrganizationType.UNIVERSITY, owner=owner, status="active", is_active=True
        )
        cls.center = User.objects.create_user("sdss_center", "sdss_center@test.az", PASSWORD)
        _assign_user_to_org(cls.center, cls.org, ProfileRole.MEMBER, "exam_center_head")
        with bypass_rls():

            def unit(slug, name, unit_type, parent=None):
                return OrgUnit.objects.create(
                    organization=cls.org, slug=slug, name=name, unit_type=unit_type, parent=parent
                )

            cls.school = unit("sdss-s", "Rəqəmsal texnologiyalar məktəbi", OrgUnitType.FACULTY)
            middle = unit("sdss-m", "Tədris departamenti", OrgUnitType.UNIT, cls.school)
            cls.deep = unit("sdss-k", "Proqramlaşdırma kafedrası", OrgUnitType.CHAIR, middle)
            cls.direct = unit("sdss-c", "Kompüter elmləri kafedrası", OrgUnitType.CHAIR, cls.school)
            cls.econ = unit("sdss-e", "İqtisadiyyat məktəbi", OrgUnitType.FACULTY)
            cls.finance = unit("sdss-f", "Maliyyə kafedrası", OrgUnitType.CHAIR, cls.econ)

    def _ids(self, **params) -> set[str]:
        client = Client()
        client.force_login(self.center)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        response = client.get(reverse("exams:stats_department_search"), params)
        self.assertEqual(response.status_code, 200)
        return {row["id"] for row in response.json()["results"]}

    def test_faculty_param_lists_kafedras_of_whole_subtree(self):
        self.assertEqual(self._ids(faculty=str(self.school.pk)), {str(self.deep.pk), str(self.direct.pk)})

    def test_several_faculties_union_their_subtrees(self):
        self.assertEqual(
            self._ids(faculty=f"{self.school.pk},{self.econ.pk}"),
            {str(self.deep.pk), str(self.direct.pk), str(self.finance.pk)},
        )

    def test_without_faculty_lists_all_kafedras(self):
        self.assertEqual(self._ids(), {str(self.deep.pk), str(self.direct.pk), str(self.finance.pk)})

    def test_malformed_or_unknown_faculty_returns_empty(self):
        self.assertEqual(self._ids(faculty="not-a-uuid"), set())
        self.assertEqual(self._ids(faculty="00000000-0000-0000-0000-000000000000"), set())
