"""Request üzvlük snapshot-u + middleware RLS round-trip-ləri (perf 2026-10-07).

Ölçü (tələbə, warm keş — badge dəsti və org-switcher keşdə; ``CaptureQueriesContext``,
RLS ``set_config``/``current_setting`` ifadələri DAXİL):

    səhifə                              TestCase (atomic)   istehsal (autocommit)
    kabinet fraqmenti (dashboard)            20 → 16             19 → 15
    tam kabinet (?section=dashboard)         33 → 29             30 → 26
    tam kabinet, cold keş                    55 → 47             51 → 43
    imtahan sualları (take_exam)             24 → 22             22 → 20

Nə düşdü: middleware-in ``bypass_rls`` on/off cütü + ayrıca kontekst tətbiqi (BİR
``set_config`` ifadəsinə yığıldı, oxu artıq tenant RLS-i altındadır), unit-scope /
müraciət emalçısı / «Ana səhifə» rol adı üçün təkrar ``Membership`` SELECT-ləri,
müraciət badge-inin 3 × ``COUNT(DISTINCT <20 sütun>)`` + sətir oxusu (→ 1 aqreqat).
"""

from __future__ import annotations

import re

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

import pytest

from apps.accounts.tests.test_cabinet_shell_query_budget import _LOCMEM, _build_tenant, _client_for
from apps.applications.services.access import active_memberships
from apps.exams.models import Exam, ExamAnswer, ExamAttempt, ExamQuestion, ExamQuestionOption
from apps.exams.services.question_snapshot import build_question_snapshot
from apps.organizations.middleware import OrganizationMiddleware
from apps.organizations.models import Membership, Organization, OrgUnit, Role
from apps.organizations.request_memberships import request_active_memberships
from apps.organizations.scoping import _permission_scope_memberships, invalidate_permission_scope_cache
from core.constants import OrganizationType, OrgUnitType, RoleScopeType
from core.rls import bypass_rls

User = get_user_model()

_MEMBERSHIP_SQL = 'FROM "organizations_membership"'
_RLS_RE = re.compile(r"^SELECT (set_config|current_setting)\(")
_BYPASS_ON = "set_config('app.bypass_rls', 'on'"


def _add_exam_attempt(tenant):
    with bypass_rls():
        exam = Exam.objects.create(
            title="Snapshot imtahanı",
            author=tenant["teacher"],
            organization=tenant["org"],
            exam_type="test",
            is_active=True,
            is_public=True,
        )
        question = ExamQuestion.objects.create(
            exam=exam, order=1, text="S1", points=1, is_active=True, answer_mode="single"
        )
        options = [
            ExamQuestionOption.objects.create(question=question, text=f"v{i}", is_correct=i == 0) for i in range(3)
        ]
        attempt = ExamAttempt.objects.create(user=tenant["student"], exam=exam, status="in_progress", attempt_number=1)
        ExamAnswer.objects.create(
            attempt=attempt, question=question, question_snapshot=build_question_snapshot(question, options)
        )
    tenant["take_url"] = reverse("exams:take_exam", kwargs={"slug": exam.slug, "attempt_id": attempt.id})
    return tenant


def _pages(tenant):
    return {
        "fragment": (reverse("accounts:profile_section_fragment", args=["dashboard"]), True),
        "full": (reverse("accounts:profile") + "?section=dashboard", False),
        "take_exam": (tenant["take_url"], False),
    }


def _capture(client, url, ajax, *, cold=False):
    kwargs = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"} if ajax else {}
    client.get(url, **kwargs)  # isinmə: sessiya möhürü + badge/org-switcher keşi
    if cold:
        cache.clear()
    with CaptureQueriesContext(connection) as ctx:
        response = client.get(url, **kwargs)
    assert response.status_code == 200, (url, response.status_code)
    return [query["sql"] for query in ctx.captured_queries]


def _rls_statements(sqls):
    return [sql for sql in sqls if _RLS_RE.match(sql)]


#: səhifə → (sorğu tavanı, Membership SELECT sayı, bypass ON ifadəsi sayı). Tavan = ölçü + 1.
#: Membership: middleware (1) + tam səhifədə gözləyən dəvətlər (``is_active=False`` — fərqli süzgəc).
#: bypass ON: middleware-də YOXDUR; qalanlar cross-org oxulardır (oxunmamış say, qoşulma müraciəti).
ATOMIC_BUDGET = {
    "fragment": (17, 1, 0),
    "full": (30, 2, 2),
    "take_exam": (23, 1, 1),
}


@override_settings(UNIVERSITY_MODE=True, CACHES=_LOCMEM)
class CabinetAndExamQueryBudgetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = _add_exam_attempt(_build_tenant(slug="rqm1", subject_count=3))

    def setUp(self):
        cache.clear()
        self.client = _client_for(self.tenant["org"], self.tenant["student"])

    def test_warm_budgets_single_membership_read_no_middleware_bypass(self):
        for page, (url, ajax) in _pages(self.tenant).items():
            budget, membership_reads, bypass_on = ATOMIC_BUDGET[page]
            with self.subTest(page=page):
                sqls = _capture(self.client, url, ajax)
                self.assertLessEqual(len(sqls), budget, f"{page}: {len(sqls)} sorğu > {budget}")
                self.assertEqual(sum(_MEMBERSHIP_SQL in sql for sql in sqls), membership_reads, page)
                self.assertEqual(sum(_BYPASS_ON in sql for sql in sqls), bypass_on, page)
                self.assertFalse(any("current_setting('app.bypass_rls'" in sql for sql in sqls[:6]), page)

    def test_cold_full_page_badge_has_no_distinct_application_counts(self):
        url, ajax = _pages(self.tenant)["full"]
        sqls = _capture(self.client, url, ajax, cold=True)
        self.assertLessEqual(len(sqls), 48)
        application_sqls = [sql for sql in sqls if '"applications_application"' in sql]
        self.assertFalse([sql for sql in application_sqls if "SELECT DISTINCT" in sql], application_sqls)
        # Badge (göndərən) + «Ana səhifə» kartı — hər biri TƏK aqreqat.
        self.assertEqual(len(application_sqls), 2, application_sqls)
        # Müraciət emalçısı yoxlaması üzvlüyü middleware snapshot-undan alır (+ org-switcher).
        self.assertEqual(sum(_MEMBERSHIP_SQL in sql for sql in sqls), 3)


@override_settings(UNIVERSITY_MODE=True, CACHES=_LOCMEM)
class AutocommitRlsRoundTripTests(TransactionTestCase):
    """İstehsal yolu (atomic blok YOX, sessiya-səviyyəli GUC memo-su işləyir)."""

    def test_fragment_rls_round_trips_and_budget(self):
        tenant = _build_tenant(slug="rqm2", subject_count=3)
        client = _client_for(tenant["org"], tenant["student"])
        cache.clear()
        sqls = _capture(client, reverse("accounts:profile_section_fragment", args=["dashboard"]), True)
        rls = _rls_statements(sqls)
        # Əvvəl 4: bypass on, bypass off, kontekst tətbiqi, sıfırlama. İndi: ön-təyin + sıfırlama.
        self.assertEqual(len(rls), 2, rls)
        self.assertIn("COALESCE((SELECT", rls[0])
        self.assertIn("set_config('app.current_org_id', ''", rls[-1])
        self.assertLessEqual(len(sqls), 15)
        self.assertEqual(sum(_MEMBERSHIP_SQL in sql for sql in sqls), 1)


def _org(slug, owner):
    with bypass_rls():
        return Organization.objects.create(
            name=f"{slug} Univ",
            slug=slug,
            org_type=OrganizationType.UNIVERSITY,
            owner=owner,
            status="active",
            is_active=True,
        )


def _run_middleware(user, org_slug):
    request = RequestFactory().get("/")
    request.user = user
    request.session = {"active_organization": org_slug} if org_slug else {}
    OrganizationMiddleware(lambda r: HttpResponse("ok"))(request)
    return request


class RequestMembershipSnapshotTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("rqs_owner", "rqs_owner@example.test", "pw")
        cls.org = _org("rqs-a", cls.owner)
        cls.other = _org("rqs-b", cls.owner)
        cls.user = User.objects.create_user("rqs_user", "rqs_user@example.test", "pw")
        with bypass_rls():
            cls.chair = OrgUnit.objects.create(
                organization=cls.org, name="Kafedra", slug="rqs-chair", unit_type=OrgUnitType.DEPARTMENT
            )
            teacher = cls.org.roles.get(name="teacher")
            head = Role.objects.create(
                organization=cls.org,
                name="rqs_head",
                display_name="Müdir",
                level=70,
                scope_type=RoleScopeType.UNIT,
                permissions=["course.edit"],
            )
            Membership.objects.create(user=cls.user, organization=cls.org, role=teacher, is_active=True)
            Membership.objects.create(
                user=cls.user, organization=cls.org, role=head, scope_unit=cls.chair, is_primary=True, is_active=True
            )
            # İkinci təşkilatda da üzv — sessiyasız sorğu avto-seçim etmir (çox-org).
            Membership.objects.create(
                user=cls.user, organization=cls.other, role=cls.other.roles.get(name="teacher"), is_active=True
            )

    def _fresh_user(self):
        return User.objects.get(pk=self.user.pk)

    def _live(self, user):
        return list(
            Membership.objects.filter(
                user=user,
                organization=self.org,
                is_active=True,
                role__organization=self.org,
                role__is_active=True,
            ).select_related("role", "scope_unit")
        )

    def test_snapshot_matches_every_consumer_live_query(self):
        user = self._fresh_user()
        request = _run_middleware(user, self.org.slug)
        self.assertEqual(request.organization, self.org)
        live = self._live(self._fresh_user())
        with self.assertNumQueries(0):
            snapshot = request_active_memberships(user, self.org)
            scoped = _permission_scope_memberships(user, self.org)
            handler_rows = active_memberships(user, self.org)
        self.assertEqual({m.pk for m in snapshot}, {m.pk for m in live})
        self.assertEqual({m.pk for m in scoped}, {m.pk for m in live})
        # `handler_role_for` sıraya baxır — canlı sorğunun Meta sırası ilə eyni.
        self.assertEqual([m.pk for m in handler_rows], [m.pk for m in self._live(self._fresh_user())])
        self.assertEqual({m.scope_unit_id for m in handler_rows}, {None, self.chair.pk})

    def test_no_snapshot_for_other_org_after_write_or_invalidation(self):
        user = self._fresh_user()
        _run_middleware(user, self.org.slug)
        self.assertIsNone(request_active_memberships(user, self.other))
        self.assertIsNotNone(request_active_memberships(user, self.org))
        invalidate_permission_scope_cache(user)
        self.assertIsNone(request_active_memberships(user, self.org))

        _run_middleware(user, self.org.slug)
        self.assertIsNotNone(request_active_memberships(user, self.org))
        with bypass_rls():
            membership = Membership.objects.filter(user=user, organization=self.org).first()
            membership.save(update_fields=["updated_at"])  # siqnal → epoxa artır
        self.assertIsNone(request_active_memberships(user, self.org))

    def test_stale_snapshot_never_crosses_middleware_calls(self):
        user = self._fresh_user()
        _run_middleware(user, self.org.slug)
        self.assertIsNotNone(request_active_memberships(user, self.org))
        request = _run_middleware(user, None)  # sessiya org-u yoxdur, iki təşkilat → seçim yoxdur
        self.assertIsNone(request.organization)
        self.assertIsNone(request_active_memberships(user, self.org))

    def test_superuser_and_cross_org_rows_are_not_reused(self):
        admin = User.objects.create_superuser("rqs_admin", "rqs_admin@example.test", "pw")
        with bypass_rls():
            Membership.objects.create(
                user=admin, organization=self.org, role=self.org.roles.get(name="teacher"), is_active=True
            )
        _run_middleware(admin, self.org.slug)
        self.assertIsNone(request_active_memberships(admin, self.org))

        # Başqa təşkilatın struktur vahidi (pozuq məlumat) → snapshot bütövlükdə rədd.
        with bypass_rls():
            foreign_unit = OrgUnit.objects.create(
                organization=self.other, name="Yad", slug="rqs-foreign", unit_type=OrgUnitType.DEPARTMENT
            )
            Membership.objects.filter(user=self.user, organization=self.org, scope_unit=self.chair).update(
                scope_unit=foreign_unit
            )
        user = self._fresh_user()
        request = _run_middleware(user, self.org.slug)
        self.assertEqual(request.organization, self.org)
        self.assertIsNone(request_active_memberships(user, self.org))


def _setting(name):
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting(%s, true)", [name])
        return cursor.fetchone()[0] or ""


@pytest.mark.postgres
class TenantScopedSessionReadUnderEnforcedRlsTests(TestCase):
    """Middleware-in sessiya org-u oxusu ``rls_app_role`` (RLS TƏTBİQ OLUNUR) altında.

    ``emsarena_agent`` superuser-dir — mənfi assert-lər yalnız məhdud rolda etibarlıdır.
    """

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("rqe_owner", "rqe_owner@example.test", "pw")
        cls.org_a = _org("rqe-a", cls.owner)
        cls.org_b = _org("rqe-b", cls.owner)
        cls.user = User.objects.create_user("rqe_user", "rqe_user@example.test", "pw")
        with bypass_rls():
            Membership.objects.create(
                user=cls.user, organization=cls.org_a, role=cls.org_a.roles.get(name="student"), is_active=True
            )

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("RLS yalnız PostgreSQL-dədir")
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL ROLE rls_app_role")

    def test_session_org_rows_read_under_that_tenant_without_bypass(self):
        rows = OrganizationMiddleware._tenant_scoped_session_memberships(self.user, self.org_a.slug)
        self.assertEqual([m.organization_id for m in rows], [self.org_a.pk])
        self.assertEqual(_setting("app.current_org_id"), str(self.org_a.pk))
        self.assertEqual(_setting("app.current_user_id"), str(self.user.pk))
        self.assertEqual(_setting("app.bypass_rls"), "off")

    def test_failed_verification_restores_secure_default(self):
        for slug in (self.org_b.slug, "rqe-yoxdur"):
            with self.subTest(slug=slug):
                self.assertIsNone(OrganizationMiddleware._tenant_scoped_session_memberships(self.user, slug))
                self.assertEqual(_setting("app.current_org_id"), "")
                self.assertEqual(_setting("app.current_user_id"), "")
                self.assertEqual(_setting("app.bypass_rls"), "off")

    def test_full_middleware_resolves_and_resets_under_enforced_rls(self):
        request = _run_middleware(self.user, self.org_a.slug)
        self.assertEqual(request.organization, self.org_a)
        self.assertEqual(len(request.org_memberships), 1)
        self.assertIsNotNone(request_active_memberships(self.user, self.org_a))
        self.assertEqual(_setting("app.current_org_id"), "")  # middleware `finally` sıfırlaması

        # Üzv olmadığı org-un slug-ı: köhnə yol → yeganə üzvlük olan A avto-seçilir.
        request = _run_middleware(self.user, self.org_b.slug)
        self.assertEqual(request.organization, self.org_a)
        self.assertEqual(request.session["active_organization"], self.org_a.slug)
        self.assertEqual(_setting("app.bypass_rls"), "off")
