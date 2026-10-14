"""«Bölmə imtahanları» redizaynı (2026-10-14) — əhatə, bağlantı, KPI, filtr, çekmecə, sorğu sayı.

Kök səbəb (real dekanda boş siyahı): bağlantı demək olar ki, yalnız `subject.chair_unit`-ə
(prod nüsxəsində açılışı olan 1 664 fəndən 7-sində dolu) və müəllifin «ev» üzvlüyünə (yalnız
qrupsuz imtahanda) baxırdı; ORG-wide `exam.view` isə bölməni səssizcə boşaldırdı.
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit, Role
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType, RoleScopeType

User = get_user_model()
PASSWORD = "StrongPass123!"


def _context(user, org, params=None):
    from apps.accounts.views.profile._sections.unit_exams import build_unit_exams_context

    request = RequestFactory().get("/accounts/profile/", {"section": "unit-exams", **(params or {})})
    request.user = user
    request.organization = org
    return build_unit_exams_context(request, allowed_sections={"unit-exams"}, active_section="unit-exams")


def _titles(user, org, params=None):
    page = _context(user, org, params)["unit_exams_page_obj"]
    return None if page is None else {exam.title for exam in page.object_list}


class _World(TestCase):
    @classmethod
    def setUpTestData(cls):
        from apps.exams.models import Exam, ExamAttempt, ExamQuestion
        from apps.registrar.models import CourseOffering, Subject

        owner = User.objects.create_user("ue14_owner", "ue14o@x.test", PASSWORD)
        cls.org = Organization.objects.create(
            name="UE14", slug="ue14", org_type=OrganizationType.UNIVERSITY, owner=owner, status="active"
        )
        unit = lambda name, kind, parent=None: OrgUnit.objects.create(  # noqa: E731
            organization=cls.org, name=name, slug=f"ue14-{name}", unit_type=kind, parent=parent
        )
        cls.fac_a, cls.fac_b = unit("fa", OrgUnitType.FACULTY), unit("fb", OrgUnitType.FACULTY)
        cls.chair_a, cls.chair_b = unit("ca", OrgUnitType.CHAIR, cls.fac_a), unit("cb", OrgUnitType.CHAIR, cls.fac_b)
        cls.chair_a2 = unit("ca2", OrgUnitType.CHAIR, cls.fac_a)
        spec_a, spec_b = unit("sa", OrgUnitType.SPECIALTY, cls.fac_a), unit("sb", OrgUnitType.SPECIALTY, cls.fac_b)
        cls.group_a, cls.group_b = unit("ga", OrgUnitType.GROUP, spec_a), unit("gb", OrgUnitType.GROUP, spec_b)
        cls.period = AcademicPeriod.objects.create(
            organization=cls.org,
            name="Payız",
            period_type=AcademicPeriodType.SEMESTER,
            academic_year="2026/2027",
            start_date="2026-09-01",
            end_date="2027-01-31",
        )

        dean_role = cls.org.roles.get(name="dean")
        teacher_role = cls.org.roles.get(name="teacher")

        def person(username, role, scope_unit, primary=True):
            user = User.objects.create_user(username, f"{username}@x.test", PASSWORD)
            Membership.objects.create(
                organization=cls.org, user=user, role=role, scope_unit=scope_unit, is_active=True, is_primary=primary
            )
            return user

        cls.dean_a = person("ue14_dean_a", dean_role, cls.fac_a)
        cls.dean_b = person("ue14_dean_b", dean_role, cls.fac_b)
        cls.dean_none = person("ue14_dean_none", dean_role, None)
        cls.teacher_a = person("ue14_teacher_a", teacher_role, cls.chair_a)
        cls.teacher_b = person("ue14_teacher_b", teacher_role, cls.chair_b)

        free = Subject.objects.create(organization=cls.org, code="UE14-F", name="Sahibsiz fənn")
        owned_b = Subject.objects.create(organization=cls.org, code="UE14-B", name="B fənni", chair_unit=cls.chair_b)
        CourseOffering.objects.create(
            organization=cls.org, subject=free, period=cls.period, group=cls.group_a, instructor=cls.teacher_b
        )

        now = timezone.now()

        def exam(title, author, **kwargs):
            groups = kwargs.pop("groups", ())
            obj = Exam.objects.create(organization=cls.org, author=author, title=title, **kwargs)
            if groups:
                obj.allowed_units.set(groups)
            return obj

        cls.e_home = exam(
            "home-final",
            cls.teacher_a,
            exam_type_extended="final",
            is_active=True,
            start_datetime=now - timedelta(days=3),
            end_datetime=now - timedelta(days=2),
        )
        cls.e_group = exam(
            "b-group-in-a",
            cls.teacher_b,
            subject=free,
            groups=[cls.group_a],
            exam_type_extended="midterm",
            is_active=True,
            start_datetime=now - timedelta(hours=1),
            end_datetime=now + timedelta(hours=1),
        )
        cls.e_offering = exam(
            "b-offering-in-a", cls.teacher_b, subject=free, is_active=True, start_datetime=now + timedelta(days=5)
        )
        exam("b-unlinked", cls.teacher_b, is_active=True)
        exam("a-owned-by-b", cls.teacher_a, subject=owned_b, is_active=True)
        cls.e_mixed = exam("a-teacher-group-b", cls.teacher_a, subject=free, groups=[cls.group_b], exam_type="written")
        exam("deleted", cls.teacher_a, is_deleted=True)

        for order in (1, 2):
            ExamQuestion.objects.create(exam=cls.e_home, text=f"Q{order}", order=order, points=1)
        students = [User.objects.create_user(f"ue14_s{i}", f"ue14s{i}@x.test", PASSWORD) for i in range(4)]
        for index, student in enumerate(students[:3]):
            ExamAttempt.objects.create(
                user=student, exam=cls.e_home, status="submitted", correct_count=index + 1, wrong_count=3 - index
            )
        ExamAttempt.objects.create(user=students[3], exam=cls.e_group, status="submitted", correct_count=2)


class UnitExamsScopeAndLinkageTest(_World):
    def test_dean_sees_own_faculty_via_every_link(self):
        self.assertEqual(
            _titles(self.dean_a, self.org),
            {"home-final", "b-group-in-a", "b-offering-in-a", "a-teacher-group-b"},
        )

    def test_dean_of_a_never_sees_b_owned_exams(self):
        titles = _titles(self.dean_a, self.org)
        self.assertNotIn("b-unlinked", titles)
        self.assertNotIn("a-owned-by-b", titles)  # sahibi bilinir (B kafedrası)
        self.assertNotIn("deleted", titles)

    def test_dean_b_sees_b_owned_and_b_groups(self):
        titles = _titles(self.dean_b, self.org)
        self.assertTrue({"b-unlinked", "a-owned-by-b", "a-teacher-group-b"} <= titles)
        self.assertNotIn("home-final", titles)

    def test_chair_head_sees_own_teachers_exams_even_with_groups_elsewhere(self):
        # Qruplar kafedranın altında deyil (Fakültə → İxtisas → Qrup) — əvvəl qrup təyinli imtahan
        # müdirə heç vaxt görünmürdü. İndi sahibsiz imtahan müəllifin ev kafedrasına bağlanır.
        head = User.objects.create_user("ue14_head", "ue14h@x.test", PASSWORD)
        Membership.objects.create(
            organization=self.org,
            user=head,
            role=self.org.roles.get(name="chair_head"),
            scope_unit=self.chair_a,
            is_active=True,
            is_primary=True,
        )
        self.assertEqual(_titles(head, self.org), {"home-final", "a-teacher-group-b"})

    def test_no_scope_is_reported_separately(self):
        context = _context(self.dean_none, self.org)
        self.assertIsNone(context["unit_exams_page_obj"])
        self.assertFalse(context["unit_exams_section"]["has_scope"])

    def test_org_wide_exam_view_does_not_open_whole_org(self):
        wide = Role.objects.create(
            organization=self.org,
            name="ue14_wide",
            display_name="W",
            level=10,
            permissions=["exam.view"],
            scope_type=RoleScopeType.ORGANIZATION,
        )
        Membership.objects.create(organization=self.org, user=self.dean_a, role=wide, is_active=True)
        titles = _titles(self.dean_a, self.org)
        self.assertIn("home-final", titles)
        self.assertNotIn("b-unlinked", titles)

    def test_org_wide_only_without_unit_role_has_no_scope(self):
        wide = Role.objects.create(
            organization=self.org,
            name="ue14_wide2",
            display_name="W",
            level=10,
            permissions=["exam.view"],
            scope_type=RoleScopeType.ORGANIZATION,
        )
        user = User.objects.create_user("ue14_wide_only", "ue14w@x.test", PASSWORD)
        Membership.objects.create(organization=self.org, user=user, role=wide, is_active=True)
        self.assertFalse(_context(user, self.org)["unit_exams_section"]["has_scope"])


class UnitExamsKpiFilterDrawerTest(_World):
    def test_kpis_cover_whole_scope(self):
        tiles = {tile["label"]: tile for tile in _context(self.dean_a, self.org)["unit_exams_section"]["kpi_tiles"]}
        self.assertEqual(tiles["İMTAHAN"]["value"], 4)
        self.assertEqual(tiles["AKTİV"]["value"], 1)
        self.assertEqual(tiles["BİTMİŞ"]["value"], 1)
        self.assertEqual(tiles["FİNAL / MİDTERM"]["value"], "1 / 1")
        self.assertEqual(tiles["İŞTİRAKÇI"]["value"], 4)

    def test_filters(self):
        self.assertEqual(_titles(self.dean_a, self.org, {"ue_kind": "final"}), {"home-final"})
        self.assertEqual(_titles(self.dean_a, self.org, {"ue_status": "finished"}), {"home-final"})
        self.assertEqual(_titles(self.dean_a, self.org, {"ue_status": "scheduled"}), {"b-offering-in-a"})
        self.assertEqual(_titles(self.dean_a, self.org, {"ue_status": "draft"}), {"a-teacher-group-b"})
        self.assertEqual(_titles(self.dean_a, self.org, {"ue_form": "written"}), {"a-teacher-group-b"})
        self.assertEqual(
            _titles(self.dean_a, self.org, {"ue_chair": str(self.chair_a.pk)}), {"home-final", "a-teacher-group-b"}
        )
        self.assertEqual(_titles(self.dean_a, self.org, {"ue_q": "offering"}), {"b-offering-in-a"})
        today = timezone.localdate()
        self.assertEqual(
            _titles(self.dean_a, self.org, {"ue_from": str(today + timedelta(days=4))}), {"b-offering-in-a"}
        )

    def test_foreign_chair_or_period_id_cannot_widen_scope(self):
        titles = _titles(self.dean_a, self.org, {"ue_chair": str(self.chair_b.pk)})
        self.assertNotIn("b-unlinked", titles)
        self.assertEqual(titles, _titles(self.dean_a, self.org))

    def test_period_filter_by_dates(self):
        past = AcademicPeriod.objects.create(
            organization=self.org,
            name="Yaz",
            period_type=AcademicPeriodType.SEMESTER,
            academic_year="2020/2021",
            start_date="2021-02-01",
            end_date="2021-06-30",
        )
        self.assertEqual(_titles(self.dean_a, self.org, {"ue_period": str(past.pk)}), set())
        current = _titles(self.dean_a, self.org, {"ue_period": str(self.period.pk)})
        self.assertTrue(current <= _titles(self.dean_a, self.org))

    def test_drawer_rows_are_aggregates_only(self):
        section = _context(self.dean_a, self.org)["unit_exams_section"]
        rows = {row["title"]: row for row in section["drawer_rows"]}
        home = rows["home-final"]
        self.assertEqual(home["questions"], 2)
        self.assertEqual(home["finished"], 3)
        self.assertTrue(home["avg"].endswith("%"))
        self.assertEqual(home["detail_url"], "")  # dekan bu imtahanın müəllifi deyil
        group = rows["b-group-in-a"]
        self.assertEqual(group["groups"], ["ga"])
        self.assertEqual(group["avg"], "")  # 1 bitirən — məxfilik
        self.assertTrue(group["hidden_small"])
        self.assertNotIn("ue14_s3", str(section["drawer_rows"]))

    def test_own_exam_has_links(self):
        from apps.exams.models import Exam

        Exam.objects.create(organization=self.org, author=self.dean_a, title="dean-own")
        rows = {row["title"]: row for row in _context(self.dean_a, self.org)["unit_exams_section"]["drawer_rows"]}
        self.assertTrue(rows["dean-own"]["detail_url"])
        self.assertTrue(rows["dean-own"]["results_url"])

    def test_empty_state_texts_split(self):
        section = _context(self.dean_a, self.org, {"ue_q": "heçnə-yoxdur"})["unit_exams_section"]
        self.assertEqual(section["table_state"], "empty")
        self.assertTrue(section["is_filtered"])

    def test_no_n_plus_one(self):
        from apps.exams.models import Exam, ExamAttempt

        def count():
            dean = User.objects.get(pk=self.dean_a.pk)  # üzvlük memo-su istifadəçi obyektindədir
            with CaptureQueriesContext(connection) as ctx:
                _context(dean, self.org)
            return len(ctx.captured_queries)

        before = count()
        student = User.objects.create_user("ue14_extra", "ue14x@x.test", PASSWORD)
        for index in range(6):
            extra = Exam.objects.create(organization=self.org, author=self.teacher_a, title=f"extra-{index}")
            extra.allowed_units.set([self.group_a])
            ExamAttempt.objects.create(user=student, exam=extra, status="submitted", correct_count=1)
        self.assertEqual(count(), before)


class UnitExamsPageRenderTest(_World):
    def test_full_page_renders_redesign(self):
        client = Client()
        self.assertTrue(client.login(username="ue14_dean_a", password=PASSWORD))
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        response = client.get(reverse("accounts:profile"), {"section": "unit-exams"})
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        panel = html[html.index('data-profile-section-panel="unit-exams"') :]
        panel = panel[: panel.index("</section>")]
        self.assertIn("data-ue-root", panel)
        self.assertIn('data-ems-filters-auto="1"', panel)
        self.assertIn('id="ueRowsData"', panel)
        self.assertIn("data-ue-open", panel)
        self.assertNotIn("<h1", panel)
        self.assertNotIn("<style", panel)
