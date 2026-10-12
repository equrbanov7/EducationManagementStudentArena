"""Rol auditi 2026-10-13 B10 — baş tələbənin «Qrupum» (`my-group`) bölməsi.

Köhnə vəziyyət: ``lead_student`` şablonu «məhdud qrup görünüşü» vəd edirdi (`member.view`), amma
kabinetdə bu açarı oxuyan səth yox idi — baş tələbə adi tələbə ilə eyni bölmələri görürdü, AI köməkçi
isə ona açılmayan `org-members` linkini təklif edirdi. Bu fayl yeni müqaviləni kilidləyir:

* bölmə YALNIZ `member.view` əhatəsi AKADEMİK QRUP olan aktorda görünür (rol adı ilə yox);
* panel yalnız ÖZ qrupunun qeydiyyatlı tələbələrini göstərir (başqa qrup yox, əlaqə məlumatı yox);
* fənn üzrə qayıb saatı + faiz (cari dövr), sorğu sayı tələbə sayından asılı deyil;
* adi tələbə / müəllim / dekan / `scope_unit`-siz baş tələbə — bölmə yoxdur, fraqment 403;
* AI köməkçi baş tələbəyə `my-group`, dekana `org-members` təklif edir.
"""

from __future__ import annotations

import datetime

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.accounts.views._helpers.rbac import _role_capabilities
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit, Role
from apps.registrar.group_overview import group_overview
from apps.registrar.models import (
    AcademicStatus,
    CourseOffering,
    Curriculum,
    Enrollment,
    Program,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType, RoleScopeType
from core.rls import bypass_rls

User = get_user_model()

LEAD_PERMISSIONS = ["course.view", "exam.view", "appeal.create", "member.view", "analytics.view_own"]
STUDENT_PERMISSIONS = ["course.view", "exam.view", "appeal.create"]


def _role(org, name, *, level, scope_type, permissions):
    # Təşkilat yaradılanda standart rollar siqnal ilə əkilir — testin dəqiq açar dəstini yaz.
    role, _created = Role.objects.update_or_create(
        organization=org,
        name=name,
        defaults={
            "display_name": name.replace("_", " ").title(),
            "level": level,
            "scope_type": scope_type,
            "permissions": list(permissions),
            "is_active": True,
        },
    )
    return role


@override_settings(UNIVERSITY_MODE=True)
class MyGroupSectionTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        today = timezone.localdate()
        cls.owner = User.objects.create_user("mg_owner", "mg_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="MG Univ",
                slug="mg-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.faculty = OrgUnit.objects.create(
                organization=cls.org, name="Fakültə", slug="mg-fac", unit_type=OrgUnitType.FACULTY
            )
            specialty = OrgUnit.objects.create(
                organization=cls.org,
                parent=cls.faculty,
                name="İxtisas",
                slug="mg-spec",
                unit_type=OrgUnitType.SPECIALTY,
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, parent=specialty, name="MG-101", slug="mg-101", unit_type=OrgUnitType.GROUP
            )
            cls.other_group = OrgUnit.objects.create(
                organization=cls.org, parent=specialty, name="MG-102", slug="mg-102", unit_type=OrgUnitType.GROUP
            )
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2026/2027",
                start_date=today - datetime.timedelta(days=30),
                end_date=today + datetime.timedelta(days=90),
            )
            program = Program.objects.create(organization=cls.org, specialty_unit=specialty, code="MG", name="Proqram")
            cls.curriculum = Curriculum.objects.create(organization=cls.org, program=program, admission_year=2026)
            cls.program = program

            cls.student_role = student_role = _role(
                cls.org, "student", level=10, scope_type=RoleScopeType.UNIT, permissions=STUDENT_PERMISSIONS
            )
            lead_role = _role(
                cls.org, "lead_student", level=30, scope_type=RoleScopeType.UNIT, permissions=LEAD_PERMISSIONS
            )
            teacher_role = _role(
                cls.org, "teacher", level=60, scope_type=RoleScopeType.UNIT, permissions=["member.view", "course.view"]
            )
            dean_role = _role(
                cls.org, "dean", level=80, scope_type=RoleScopeType.UNIT, permissions=["member.view", "unit.view"]
            )

            cls.lead = cls._user("mg_lead", "Leyla", "Aliyeva", "10001")
            cls._member(cls.lead, student_role, cls.group)
            cls._member(cls.lead, lead_role, cls.group)
            cls._record(cls.lead, cls.group)

            cls.mate = cls._user("mg_mate", "Murad", "Babayev", "10002")
            cls._member(cls.mate, student_role, cls.group)
            cls._record(cls.mate, cls.group)

            # Akademik məzuniyyətdə olan qrup yoldaşı — status açılmır, siyahıya düşmür.
            cls.on_leave = cls._user("mg_leave", "Nərmin", "Cəfərova", "10003")
            cls._member(cls.on_leave, student_role, cls.group)
            cls._record(cls.on_leave, cls.group, status=AcademicStatus.ACADEMIC_LEAVE)

            cls.stranger = cls._user("mg_stranger", "Orxan", "Dadaşov", "20001")
            cls._member(cls.stranger, student_role, cls.other_group)
            cls._record(cls.stranger, cls.other_group)

            cls.teacher = cls._user("mg_teacher", "Pərvin", "Eyvazova", "")
            cls._member(cls.teacher, teacher_role, cls.faculty)

            cls.dean = cls._user("mg_dean", "Rauf", "Fərzəliyev", "")
            cls._member(cls.dean, dean_role, cls.faculty)

            # `scope_unit`-siz baş tələbə: əhatə boşdur → bölmə yoxdur (fail-closed).
            cls.lead_unscoped = cls._user("mg_lead_noscope", "Sevda", "Qasımova", "10009")
            cls._member(cls.lead_unscoped, student_role, cls.group)
            cls._member(cls.lead_unscoped, lead_role, None)

            subject = Subject.objects.create(organization=cls.org, code="MG1", name="Riyaziyyat")
            offering = CourseOffering.objects.create(
                organization=cls.org, subject=subject, period=cls.period, group=cls.group, lesson_hours=30
            )
            cls.subject = subject
            Enrollment.objects.create(organization=cls.org, student=cls.lead, offering=offering, absence_hours=2)
            Enrollment.objects.create(organization=cls.org, student=cls.mate, offering=offering, absence_hours=9)
            other_subject = Subject.objects.create(organization=cls.org, code="MG2", name="Gizli fənn")
            other_offering = CourseOffering.objects.create(
                organization=cls.org,
                subject=other_subject,
                period=cls.period,
                group=cls.other_group,
                lesson_hours=30,
            )
            Enrollment.objects.create(
                organization=cls.org, student=cls.stranger, offering=other_offering, absence_hours=4
            )

    @classmethod
    def _user(cls, username, first, last, number):
        user = User.objects.create_user(username, f"{username}@qku.edu.az", "pw", first_name=first, last_name=last)
        UserProfile.objects.filter(user=user).update(organization=cls.org, institutional_identifier=number or None)
        return user

    @classmethod
    def _member(cls, user, role, unit):
        return Membership.objects.create(
            user=user, organization=cls.org, role=role, scope_unit=unit, is_active=True, is_primary=False
        )

    @classmethod
    def _record(cls, user, group, *, status=AcademicStatus.ENROLLED):
        return StudentAcademicRecord.objects.create(
            organization=cls.org,
            student=user,
            program=cls.program,
            curriculum=cls.curriculum,
            group=group,
            admission_year=2026,
            status=status,
        )

    # ── köməkçilər ────────────────────────────────────────────────────────
    def client_for(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def sections_of(self, user):
        response = self.client_for(user).get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        return set(response.context["allowed_sections"])

    def fragment(self, user):
        return self.client_for(user).get(reverse("accounts:profile_section_fragment", kwargs={"section": "my-group"}))

    # ── görünürlük ────────────────────────────────────────────────────────
    def test_lead_student_sees_my_group_section_and_sidebar_item(self):
        response = self.client_for(self.lead).get(reverse("accounts:profile"))
        self.assertIn("my-group", response.context["allowed_sections"])
        self.assertContains(response, 'data-section="my-group"')

    def test_plain_student_teacher_dean_do_not_get_the_section(self):
        for user in (self.mate, self.teacher, self.dean, self.owner):
            with self.subTest(user=user.username):
                self.assertNotIn("my-group", self.sections_of(user))

    def test_lead_student_without_scope_unit_does_not_get_the_section(self):
        self.assertNotIn("my-group", self.sections_of(self.lead_unscoped))
        self.assertEqual(self.fragment(self.lead_unscoped).status_code, 403)

    def test_fragment_endpoint_is_forbidden_for_others(self):
        for user in (self.mate, self.teacher, self.dean, self.stranger):
            with self.subTest(user=user.username):
                self.assertEqual(self.fragment(user).status_code, 403)

    # ── məzmun ────────────────────────────────────────────────────────────
    def test_panel_lists_only_own_group_classmates_without_contacts(self):
        response = self.fragment(self.lead)
        self.assertEqual(response.status_code, 200)
        html = response.json()["html"]
        self.assertIn("MG-101", html)
        self.assertIn("Murad Babayev", html)
        self.assertIn("Leyla Aliyeva", html)
        self.assertIn("10002", html)
        # Başqa qrup, məzuniyyətdəki yoldaş, e-poçt və başqa qrupun fənni — açılmır.
        self.assertNotIn("Orxan Dadaşov", html)
        self.assertNotIn("Nərmin Cəfərova", html)
        self.assertNotIn("@qku.edu.az", html)
        self.assertNotIn("Gizli fənn", html)
        self.assertIn("Riyaziyyat", html)
        # Sahib 2026-10-13 «ancaq şəxsi görünsün»: baş tələbə ÖZ qayıbını görür (2 / 30 → 7%), qrup
        # yoldaşınınkını YOX (Murad: 9 / 30 → 30%, həddi aşılıb — heç bir iz qalmamalıdır).
        self.assertIn("7%", html)
        self.assertNotIn("30%", html)
        self.assertNotIn("mg-cell--over", html)

    def test_full_page_section_renders_panel(self):
        response = self.client_for(self.lead).get(reverse("accounts:profile"), {"section": "my-group"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-profile-section-panel="my-group"')
        self.assertContains(response, "accounts/css/profile/sections/my_group.css")
        self.assertContains(response, "Murad Babayev")

    def test_overview_values_are_personal_only(self):
        data = group_overview(self.group, viewer_id=self.lead.pk, period=self.period)
        rows = {row["name"]: row for row in data["students"]}
        self.assertEqual(set(rows), {"Leyla Aliyeva", "Murad Babayev"})
        # Qrup yoldaşı sətrində YALNIZ ad + nömrə (+ «mən» bayrağı) — davamiyyət açarı yoxdur.
        self.assertEqual(set(rows["Murad Babayev"]), {"name", "student_number", "is_me"})
        self.assertEqual(rows["Murad Babayev"]["student_number"], "10002")
        self.assertTrue(rows["Leyla Aliyeva"]["is_me"])
        self.assertEqual([s["name"] for s in data["me"]["subjects"]], ["Riyaziyyat"])
        self.assertEqual(data["me"]["subjects"][0]["percent"], 7)
        self.assertEqual(data["me"]["subjects"][0]["level"], "ok")

    def test_overview_without_viewer_has_no_attendance(self):
        data = group_overview(self.group, period=self.period)
        self.assertIsNone(data["me"])
        self.assertFalse(data["has_attendance"])

    def test_overview_query_count_does_not_grow_with_students(self):
        def count():
            with CaptureQueriesContext(connection) as ctx:
                group_overview(self.group, viewer_id=self.lead.pk, period=self.period)
            return len(ctx.captured_queries)

        before = count()
        with bypass_rls():
            offering = CourseOffering.objects.get(subject=self.subject)
            extra_subject = Subject.objects.create(organization=self.org, code="MG3", name="Fizika")
            extra_offering = CourseOffering.objects.create(
                organization=self.org, subject=extra_subject, period=self.period, group=self.group, lesson_hours=0
            )
            for index in range(4):
                user = self._user(f"mg_extra{index}", "Ad", f"Soyad{index}", f"3000{index}")
                self._member(user, self.student_role, self.group)
                self._record(user, self.group)
                Enrollment.objects.create(organization=self.org, student=user, offering=offering, absence_hours=1)
                Enrollment.objects.create(organization=self.org, student=user, offering=extra_offering, absence_hours=1)
        # +1 yalnız `lesson_hours` boş açılışın məxrəc fallback-i (tək aqreqat sorğu) üçün.
        self.assertLessEqual(count(), before + 1)

    def test_capabilities_build_adds_no_query_for_actors_without_group_scope(self):
        """Dekan (`member.view` fakültə əhatəsi): qapı əlavə SELECT atmır (üzvlük sətirləri yaddaşda)."""
        user = User.objects.get(pk=self.dean.pk)
        user.set_active_organization_context(self.org)
        profile = user.profile
        _role_capabilities(user, profile)  # isinmə: üzvlük/əhatə keşləri dolur
        from apps.accounts.views._helpers.rbac_my_group import my_group_sections

        with self.assertNumQueries(0):
            self.assertEqual(my_group_sections(user, self.org), set())

    # ── AI köməkçi ────────────────────────────────────────────────────────
    def _navigation(self, user):
        from apps.accounts.views._helpers.rbac import _collect_actor_permissions
        from apps.ai_assistant.context_builder import _navigation_section

        memberships = list(
            Membership.objects.filter(user=user, organization=self.org, is_active=True).select_related(
                "role", "scope_unit"
            )
        )
        permissions, _ = _collect_actor_permissions(user, self.org)
        return _navigation_section(user, self.org, memberships, list(permissions))

    def test_ai_assistant_points_lead_student_to_my_group(self):
        text = self._navigation(self.lead)
        self.assertIn("?section=my-group", text)
        self.assertNotIn("?section=org-members", text)

    def test_ai_assistant_keeps_org_members_for_dean(self):
        text = self._navigation(self.dean)
        self.assertIn("?section=org-members", text)
        self.assertNotIn("?section=my-group", text)
