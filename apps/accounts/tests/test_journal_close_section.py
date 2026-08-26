"""RİM «Jurnal bağlama» kabinet bölməsi — icazə qapısı, toplu əməliyyat, xəbərdarlıq."""

import datetime

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar.models import ApprovalStatus, JournalCloseNotice, JournalCloseScope
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


@override_settings(UNIVERSITY_MODE=True)
class JournalCloseSectionTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("jcs_owner", "jcs_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="JCS Univ",
                slug="jcs-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.faculty = OrgUnit.objects.create(
                organization=cls.org, name="Fakültə", slug="jcs-f", unit_type=OrgUnitType.FACULTY
            )
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="2024/2025 Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date="2024-09-01",
                end_date="2025-01-31",
                is_current=True,
            )
            cls.rim = User.objects.create_user("jcs_rim", "jcs_rim@qku.edu.az", "pw")
            cls.teacher = User.objects.create_user("jcs_teacher", "jcs_teacher@qku.edu.az", "pw")
            for user, role in ((cls.rim, "ikt_rehber"), (cls.teacher, "teacher")):
                Membership.objects.create(
                    user=user,
                    organization=cls.org,
                    role=cls.org.roles.get(name=role),
                    is_primary=True,
                    is_active=True,
                )

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    # ── Görünürlük / icazə qapısı ────────────────────────────────────────
    def test_section_renders_for_rim(self):
        resp = self._client(self.rim).get(reverse("accounts:profile"), {"section": "journal-close"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'data-profile-section-panel="journal-close"')
        self.assertContains(resp, "jc-toolbar")

    def test_teacher_gets_403_on_post(self):
        resp = self._client(self.teacher).post(reverse("accounts:journal_close"), {"action": "close"})
        self.assertEqual(resp.status_code, 403)

    def test_teacher_gets_403_on_get(self):
        resp = self._client(self.teacher).get(reverse("accounts:journal_close"))
        self.assertEqual(resp.status_code, 403)

    # ── Toplu bağlama / açma (HTTP) ──────────────────────────────────────
    def test_close_and_reopen_via_view(self):
        from apps.registrar.models import AssessmentScheme

        client = self._client(self.rim)
        resp = client.post(
            reverse("accounts:journal_close"),
            {"action": "close", "period": str(self.period.id), "scope": "organization", "org_unit": ""},
        )
        self.assertEqual(resp.status_code, 302)

        resp = client.post(
            reverse("accounts:journal_close"),
            {
                "action": "reopen",
                "period": str(self.period.id),
                "scope": "organization",
                "org_unit": "",
                "reason": "Səhv əhatə",
            },
        )
        self.assertEqual(resp.status_code, 302)
        with bypass_rls():
            self.assertFalse(
                AssessmentScheme.objects.filter(organization=self.org, approval_status=ApprovalStatus.APPROVED).exists()
            )

    def test_reopen_without_reason_is_rejected(self):
        resp = self._client(self.rim).post(
            reverse("accounts:journal_close"),
            {"action": "reopen", "period": str(self.period.id), "scope": "organization", "org_unit": ""},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        messages = [str(m) for m in resp.context["messages"]]
        self.assertTrue(any("səbəb" in m.lower() for m in messages), messages)

    # ── Bağlanma xəbərdarlığı (CRUD) ─────────────────────────────────────
    def test_notice_create_toggle_and_delete(self):
        client = self._client(self.rim)
        client.post(
            reverse("accounts:journal_close"),
            {
                "action": "save_notice",
                "period": str(self.period.id),
                "scope": JournalCloseScope.FACULTY,
                "org_unit": str(self.faculty.id),
                "closes_on": "2025-01-20",
                "message": "",
                "is_active": "1",
            },
        )
        with bypass_rls():
            notice = JournalCloseNotice.objects.get(organization=self.org)
        self.assertEqual(notice.closes_on, datetime.date(2025, 1, 20))
        self.assertTrue(notice.is_active)

        client.post(
            reverse("accounts:journal_close"),
            {"action": "toggle_notice", "notice_id": str(notice.id)},
        )
        with bypass_rls():
            notice.refresh_from_db()
        self.assertFalse(notice.is_active)

        client.post(
            reverse("accounts:journal_close"),
            {"action": "delete_notice", "notice_id": str(notice.id)},
        )
        with bypass_rls():
            self.assertFalse(JournalCloseNotice.objects.filter(pk=notice.pk).exists())

    def test_notice_requires_unit_for_faculty_scope(self):
        resp = self._client(self.rim).post(
            reverse("accounts:journal_close"),
            {
                "action": "save_notice",
                "period": str(self.period.id),
                "scope": JournalCloseScope.FACULTY,
                "org_unit": "",
                "closes_on": "2025-01-20",
            },
            follow=True,
        )
        messages = [str(m) for m in resp.context["messages"]]
        self.assertTrue(any("bölmə" in m.lower() for m in messages), messages)
        with bypass_rls():
            self.assertFalse(JournalCloseNotice.objects.exists())

    def test_notice_actions_are_audited(self):
        from apps.audit.models import AuditLog

        self._client(self.rim).post(
            reverse("accounts:journal_close"),
            {
                "action": "save_notice",
                "period": str(self.period.id),
                "scope": JournalCloseScope.ORGANIZATION,
                "org_unit": "",
                "closes_on": "2025-01-20",
            },
        )
        with bypass_rls():
            self.assertTrue(AuditLog.objects.filter(resource_type="registrar.journal_close_notice").exists())
