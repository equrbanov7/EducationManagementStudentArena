"""Kabinet qabığının (profile shell) sorğu büdcəsi — Codex audit §14/§21 (2026-09-13).

Nə ölçülür
----------
Tam səhifə GET (``/accounts/profile/?section=…``) üç aktor üçün eyni fikstürdə:
tələbə (profile-info, my-subjects, my-journal, pending-answers, jurnal detalı),
müəllim (profile-info, my-exams), təşkilat rəhbəri/rektor (profile-info,
org-members). Sayğac ``CaptureQueriesContext`` — RLS ``set_config`` /
``current_setting`` ifadələri də daxildir (hər ``bypass_rls()`` bloku 3 ifadə).

İki rejim:

* **cold** — keş boş (badge dəsti ``get_or_set_cached_profile_badge_counts`` və
  navbar org-switcher hər dəfə hesablanır), sessiya artıq möhürlənib
  (``SessionTimeoutMiddleware`` ``last_activity`` yazısı yalnız ilk sorğuda /
  5 dəqiqədə bir olur — o, sabit vəziyyət deyil). Audit ölçüsü ilə müqayisə
  üçün.
* **warm** — badge dəsti (45s) və org-switcher (60s) keşdə: istehsalın sabit
  vəziyyəti, yəni ƏSL per-request qabıq yükü.

Qalan sorğuların təsnifatı (warm, tələbə ``pending-answers`` = 29 ifadə)
------------------------------------------------------------------------
Middleware (11):
  1 django_session · 2 auth_user · 3 accounts_userprofile access_state
  (``EmailOrUsernameBackend.get_user`` → ``user_can_authenticate``) ·
  4 eyni yoxlama ``SessionTimeoutMiddleware``-də (müdafiə qatı, toxunulmayıb) ·
  5-8 ``bypass_rls`` bloku + aktiv org üzvlükləri (``OrganizationMiddleware``) ·
  9 ``UserProfile`` (``user.is_superadmin`` → instans keşi; qabıq təzədən OXUMUR) ·
  10 RLS kontekstinin tətbiqi · 29 RLS sıfırlama.
RBAC (1):
  11 ``get_permission_scope`` üzvlük memosu (``role__organization``/``role__is_active``
  süzgəci middleware siyahısından fərqlidir, ``apps.organizations.scoping``).
Qabıq (11):
  12 gözləyən dəvətlər (``Membership is_active=False``) · 13-16 ``bypass_rls`` +
  gözləyən qoşulma müraciətləri (profil «ev» təşkilatı boş olanda) · 17-20
  ``bypass_rls`` + oxunmamış bildiriş sayı — BİR dəfə; navbar iki badge-i eyni
  ``in_app_unread_count``-u oxuyur · 21 ``courses_count`` (tələbə üçün
  ``assigned_courses_count`` ilə paylaşılır) · 22 ``posts_count`` · 23
  ``assigned_exams_count``.
Context processor (1):
  28 ``view_as_context`` → ``resolve_actor_access`` access_state yoxlaması
  (təhlükəsizlik funksiyası, toxunulmayıb).
Bölmə gövdəsi (4):
  24-27 ``_collect_pending_answer_items`` (imtahan/tapşırıq/lab/layihə).

Cold rejimdə bunlara badge dəsti (``cheap_counts`` 11 + ``applications`` 6 sorğu,
istehsalda 45s keş) və navbar org-switcher (``bypass_rls`` + 1, 60s keş) əlavə olunur.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.template import Context, Template
from django.test import Client, RequestFactory, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.accounts.views._helpers.rbac import _collect_actor_permissions, _invalidate_actor_permissions_cache
from apps.accounts.views._helpers.rbac_memberships import _bound_active_org_memberships
from apps.notifications.public import build_profile_notification_state
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import gradebook, services
from apps.registrar.models import (
    AttendanceStatus,
    Curriculum,
    CurriculumSubject,
    LessonKind,
    LessonMark,
    Program,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

_LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "cabinet-shell-budget"}}


def _build_tenant(*, slug: str, subject_count: int):
    """``test_student_sections_redesign`` fikstürü + rektor (təşkilat rəhbəri) aktoru."""
    owner = User.objects.create_user(f"{slug}_owner", f"{slug}_owner@qku.edu.az", "pw")
    with bypass_rls():
        org = Organization.objects.create(
            name=f"{slug} Univ",
            slug=slug,
            org_type=OrganizationType.UNIVERSITY,
            owner=owner,
            status="active",
            is_active=True,
        )
        group = OrgUnit.objects.create(organization=org, name="234 KE", slug=f"{slug}-g1", unit_type=OrgUnitType.GROUP)
        period = AcademicPeriod.objects.create(
            organization=org,
            name="2024/2025 Payız",
            period_type=AcademicPeriodType.SEMESTER,
            academic_year="2024/2025",
            start_date="2024-09-01",
            end_date="2025-01-31",
            is_current=True,
        )
        program = Program.objects.create(organization=org, code="KE", name="Kompüter elmləri", absence_limit_percent=25)
        curriculum = Curriculum.objects.create(organization=org, program=program, admission_year=2024)
        teacher = User.objects.create_user(f"{slug}_teacher", f"{slug}_teacher@qku.edu.az", "pw")
        Membership.objects.create(
            user=teacher, organization=org, role=org.roles.get(name="teacher"), is_primary=True, is_active=True
        )
        admin = User.objects.create_user(f"{slug}_admin", f"{slug}_admin@qku.edu.az", "pw")
        Membership.objects.create(
            user=admin, organization=org, role=org.roles.get(name="rector"), is_primary=True, is_active=True
        )
        student = User.objects.create_user(f"{slug}_student", f"{slug}_student@qku.edu.az", "pw")
        Membership.objects.create(
            user=student, organization=org, role=org.roles.get(name="student"), is_primary=True, is_active=True
        )
        record = StudentAcademicRecord.objects.create(
            organization=org, student=student, program=program, curriculum=curriculum, group=group, admission_year=2024
        )
        for i in range(subject_count):
            subject = Subject.objects.create(organization=org, code=f"KE10{i}", name=f"Fənn {i}", ects=5)
            CurriculumSubject.objects.create(
                organization=org, curriculum=curriculum, subject=subject, semester_number=1
            )
        services.enroll_mandatory_subjects(record=record, period=period, semester_number=1)
        enrollments = list(student.enrollments.select_related("offering").order_by("id"))
        for enrollment in enrollments:
            offering = enrollment.offering
            offering.lesson_hours = 60
            offering.instructor = teacher
            offering.save(update_fields=["lesson_hours", "instructor"])
            for day in (1, 2, 3):
                lesson = gradebook.create_lesson(
                    allow_past=True, offering=offering, date=datetime.date(2024, 10, day), kind=LessonKind.SEMINAR
                )
                LessonMark.objects.create(
                    organization=org,
                    lesson=lesson,
                    enrollment=enrollment,
                    status=AttendanceStatus.PRESENT if day != 3 else AttendanceStatus.ABSENT,
                    score=Decimal(7) if day != 3 else None,
                )
    return {
        "org": org,
        "student": student,
        "teacher": teacher,
        "admin": admin,
        "record": record,
        "period": period,
        "enrollments": enrollments,
    }


def _client_for(org, user):
    client = Client()
    client.force_login(user)
    session = client.session
    session["active_organization"] = org.slug
    session.save()
    return client


#: (aktor, bölmə, əlavə query) → (cold büdcə, warm büdcə). Ölçülmüş dəyər + 2
#: ehtiyat. Cold = audit metodu (keş boş, sessiya möhürlü); warm = sabit vəziyyət.
CASES = {
    ("student", "profile-info", ""): (63, 42),
    ("student", "my-subjects", ""): (89, 68),
    ("student", "my-journal", ""): (62, 41),
    ("student", "pending-answers", ""): (52, 31),
    ("student", "my-journal", "&subject={enrollment}"): (84, 63),
    ("teacher", "profile-info", ""): (57, 43),
    ("teacher", "my-exams", ""): (44, 30),
    ("admin", "profile-info", ""): (44, 32),
    ("admin", "org-members", ""): (52, 40),
}


@override_settings(UNIVERSITY_MODE=True, CACHES=_LOCMEM)
class CabinetShellQueryBudgetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.t1 = _build_tenant(slug="qb1", subject_count=1)
        cls.t5 = _build_tenant(slug="qb5", subject_count=5)

    def setUp(self):
        cache.clear()

    def _url(self, tenant, section, extra):
        return (
            reverse("accounts:profile") + f"?section={section}" + extra.format(enrollment=tenant["enrollments"][0].id)
        )

    def _measure(self, tenant, actor, section, extra, *, warm):
        client = _client_for(tenant["org"], tenant[actor])
        url = self._url(tenant, section, extra)
        # İsinmə: sessiya `last_activity` möhürü (3 yazı ifadəsi) yalnız ilk
        # sorğudadır; warm rejimdə badge/org-switcher keşi də dolur.
        client.get(url)
        if not warm:
            cache.clear()
        with CaptureQueriesContext(connection) as ctx:
            response = client.get(url)
        self.assertEqual(response.status_code, 200)
        return len(ctx.captured_queries), response

    def _label(self, actor, section, extra):
        return f"{actor}:{section}{' (detal)' if extra else ''}"

    def test_cold_budget_constant_in_row_count(self):
        """Sətir sayından asılı deyil (1 fənn = 5 fənn) və hər səhifə büdcə daxilindədir."""
        for (actor, section, extra), (cold_budget, _warm) in CASES.items():
            with self.subTest(page=self._label(actor, section, extra)):
                q1, _ = self._measure(self.t1, actor, section, extra, warm=False)
                q5, _ = self._measure(self.t5, actor, section, extra, warm=False)
                self.assertEqual(q1, q5, f"{section}: fənn sayı sorğu sayını dəyişdi ({q1} → {q5})")
                self.assertLessEqual(q5, cold_budget, f"{section}: cold büdcə aşıldı ({q5} > {cold_budget})")

    def test_warm_budget_steady_state(self):
        """İstehsal sabit vəziyyəti (badge dəsti + org-switcher keşdə)."""
        for (actor, section, extra), (_cold, warm_budget) in CASES.items():
            with self.subTest(page=self._label(actor, section, extra)):
                q5, _ = self._measure(self.t5, actor, section, extra, warm=True)
                self.assertLessEqual(q5, warm_budget, f"{section}: warm büdcə aşıldı ({q5} > {warm_budget})")

    def test_identity_panel_data_only_for_sections_that_render_it(self):
        """Təşkilat-giriş cədvəli / tələbə qrupları yalnız kimlik panelində qurulur;
        render olunan məzmun dəyişmir, digər bölmələrdə açarlar boş qalır."""
        t = self.t5
        admin_client = _client_for(t["org"], t["admin"])
        info = admin_client.get(self._url(t, "profile-info", ""))
        rows = info.context["organization_access_rows"]
        self.assertEqual([row["organization"].id for row in rows], [t["org"].id])
        self.assertContains(info, t["org"].name)
        self.assertEqual(rows[0]["member_count"], 3)  # müəllim + rektor + tələbə

        members = admin_client.get(self._url(t, "org-members", ""))
        self.assertEqual(list(members.context["organization_access_rows"]), [])
        self.assertEqual(members.context["student_member_groups_count"], 0)

        student_client = _client_for(t["org"], t["student"])
        subjects = student_client.get(self._url(t, "my-subjects", ""))
        self.assertEqual(list(subjects.context["organization_access_rows"]), [])
        # Tələbə üçün paylaşılan COUNT: hər iki açar eyni queryset-in sayıdır.
        self.assertEqual(subjects.context["courses_count"], subjects.context["assigned_courses_count"])

    def test_profile_home_org_equal_to_active_org_reuses_middleware_rows(self):
        """Profilin «ev» təşkilatı aktiv təşkilatdırsa (istehsal fikstürü) bildiriş
        vəziyyəti middleware üzvlüklərindən qurulur — nəticə canlı sorğu ilə eynidir."""
        t = self.t1
        profile = t["student"].profile
        profile.organization = t["org"]
        profile.save(update_fields=["organization", "updated_at"])
        try:
            client = _client_for(t["org"], t["student"])
            url = self._url(t, "profile-info", "")
            client.get(url)
            with CaptureQueriesContext(connection) as ctx:
                response = client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["student_can_leave_org"])
            self.assertLessEqual(len(ctx.captured_queries), CASES[("student", "profile-info", "")][0])
            fk_fetches = [
                q["sql"]
                for q in ctx.captured_queries
                if 'FROM "organizations_organization" WHERE "organizations_organization"."id" =' in q["sql"]
            ]
            self.assertEqual(fk_fetches, [], "profile.organization FK ayrıca SELECT etdi")
            # Canlı sorğu yolu ilə eyni cavab (memberships verilmədən).
            with bypass_rls():
                live = build_profile_notification_state(user=t["student"], profile=profile)
            self.assertTrue(live["student_can_leave_org"])
        finally:
            profile.organization = None
            profile.save(update_fields=["organization", "updated_at"])

    def test_actor_permissions_reuse_bound_rows_but_never_after_invalidation(self):
        """Middleware-in bağladığı üzvlük siyahısı yenidən istifadə olunur; eyni
        request-də mutasiya (`_invalidate_actor_permissions_cache`) → yalnız canlı sorğu."""
        t = self.t1
        org = t["org"]
        teacher_role = org.roles.get(name="teacher")
        rector_role = org.roles.get(name="rector")
        user = User.objects.get(pk=t["teacher"].pk)
        with bypass_rls():
            rows = list(Membership.objects.filter(user=user, organization=org, is_active=True).select_related("role"))
        user.set_active_organization_context(org, memberships=rows, permissions=[])

        with self.assertNumQueries(0):
            effective, _ = _collect_actor_permissions(user, org)
        self.assertEqual(
            effective,
            set(teacher_role.permissions or [])
            - {p for p in (teacher_role.permissions or []) if p.startswith("grant:")},
        )

        # Başqa təşkilat / boş siyahı → yenidən istifadə YOX.
        other_org = self.t5["org"]
        self.assertIsNone(_bound_active_org_memberships(user, other_org.pk))
        user.set_active_organization_context(org, memberships=[], permissions=[])
        self.assertIsNone(_bound_active_org_memberships(user, org.pk))

        # Mutasiya: rol dəyişir, keş etibarsızlaşdırılır → DB-dən yeni icazələr.
        user.set_active_organization_context(org, memberships=rows, permissions=[])
        with bypass_rls():
            Membership.objects.filter(user=user, organization=org).update(role=rector_role)
        _invalidate_actor_permissions_cache(user)
        self.assertIsNone(_bound_active_org_memberships(user, org.pk))
        with bypass_rls():
            effective_after, _ = _collect_actor_permissions(user, org)
        self.assertIn("*", effective_after)  # rektor rolu — tam icazə
        self.assertNotEqual(effective_after, effective)
        with bypass_rls():
            Membership.objects.filter(user=user, organization=org).update(role=teacher_role)

    def test_navbar_badge_reuses_precomputed_unread_count(self):
        """Navbar tag-ı kontekstdəki `in_app_unread_count`-u (eyni istifadəçi üçün)
        oxuyur — 0 sorğu; hazır say yoxdursa əvvəlki kimi canlı sayır."""
        user = self.t1["student"]
        request = RequestFactory().get("/")
        request.user = user
        template = Template("{% load notification_tags %}{% user_unread_notification_count request.user as n %}{{ n }}")

        with self.assertNumQueries(0):
            rendered = template.render(Context({"request": request, "in_app_unread_count": 7}))
        self.assertEqual(rendered, "7")

        # Başqa istifadəçi üçün çağırılırsa hazır say İŞLƏDİLMİR (canlı sorğu).
        other_template = Template("{% load notification_tags %}{% user_unread_notification_count target as n %}{{ n }}")
        with CaptureQueriesContext(connection) as ctx:
            rendered = other_template.render(
                Context({"request": request, "target": self.t5["student"], "in_app_unread_count": 7})
            )
        self.assertEqual(rendered, "0")
        self.assertTrue(any("notifications_inappnotification" in q["sql"] for q in ctx.captured_queries))

        with CaptureQueriesContext(connection) as ctx:
            rendered = template.render(Context({"request": request}))
        self.assertEqual(rendered, "0")
        self.assertTrue(any("notifications_inappnotification" in q["sql"] for q in ctx.captured_queries))
