"""Təhlükəsizlik auditi 2026-10-07 SEC-05 — bağlanma xəbərdarlığının redaktəsi ORİJİNAL əhatəni yoxlayır.

``save_notice`` mövcud xəbərdarlığı redaktə edəndə yalnız formadan gələn YENİ
``org_unit``-in aktorun əhatəsində olduğunu yoxlayırdı. Unit-əhatəli aktor
(``journal.close`` öz fakültəsi ilə) başqa fakültənin və ya bütün təşkilatın
xəbərdarlığını ``notice_id`` ilə götürüb öz fakültəsinə «köçürürdü» — orijinal
xəbərdarlıq yox olurdu (toggle/delete isə orijinal bölməni düzgün yoxlayır).
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit, Role
from apps.registrar.models import JournalCloseNotice, JournalCloseScope
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType, RoleScopeType
from core.rls import bypass_rls

User = get_user_model()


@override_settings(UNIVERSITY_MODE=True)
class JournalCloseNoticeOriginalScopeTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("sec07jc_owner", "sec07jc_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="Sec07 JC Univ",
                slug="sec07-jc-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.faculty_own = OrgUnit.objects.create(
                organization=cls.org, name="Öz fakültə", slug="sec07jc-f1", unit_type=OrgUnitType.FACULTY
            )
            cls.faculty_other = OrgUnit.objects.create(
                organization=cls.org, name="Başqa fakültə", slug="sec07jc-f2", unit_type=OrgUnitType.FACULTY
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
            role = Role.objects.create(
                organization=cls.org,
                name="sec07_faculty_closer",
                display_name="Fakültə jurnal bağlayan",
                level=70,
                scope_type=RoleScopeType.UNIT,
                permissions=["journal.close"],
                is_active=True,
            )
            cls.closer = User.objects.create_user("sec07jc_closer", "sec07jc_closer@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.closer,
                organization=cls.org,
                role=role,
                scope_unit=cls.faculty_own,
                is_primary=True,
                is_active=True,
            )
            cls.other_notice = JournalCloseNotice.objects.create(
                organization=cls.org,
                period=cls.period,
                scope=JournalCloseScope.FACULTY,
                org_unit=cls.faculty_other,
                closes_on="2025-01-20",
                message="Başqa fakültənin xəbərdarlığı",
                is_active=True,
            )

    def _client(self):
        client = Client()
        client.force_login(self.closer)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _notice(self):
        with bypass_rls():
            return JournalCloseNotice.objects.get(pk=self.other_notice.pk)

    def test_unit_actor_cannot_take_over_another_faculty_notice(self):
        self._client().post(
            reverse("accounts:journal_close"),
            {
                "action": "save_notice",
                "notice_id": str(self.other_notice.id),
                "period": str(self.period.id),
                "scope": JournalCloseScope.FACULTY,
                "org_unit": str(self.faculty_own.id),
                "closes_on": "2025-01-25",
                "message": "Ələ keçirildi",
                "is_active": "1",
            },
        )
        notice = self._notice()
        self.assertEqual(notice.org_unit_id, self.faculty_other.id)
        self.assertEqual(notice.message, "Başqa fakültənin xəbərdarlığı")

    def test_unit_actor_still_edits_own_faculty_notice(self):
        with bypass_rls():
            own = JournalCloseNotice.objects.create(
                organization=self.org,
                period=self.period,
                scope=JournalCloseScope.FACULTY,
                org_unit=self.faculty_own,
                closes_on="2025-01-20",
                message="Öz xəbərdarlığım",
                is_active=True,
            )
        self._client().post(
            reverse("accounts:journal_close"),
            {
                "action": "save_notice",
                "notice_id": str(own.id),
                "period": str(self.period.id),
                "scope": JournalCloseScope.FACULTY,
                "org_unit": str(self.faculty_own.id),
                "closes_on": "2025-01-22",
                "message": "Yeniləndi",
                "is_active": "1",
            },
        )
        with bypass_rls():
            own.refresh_from_db()
        self.assertEqual(own.message, "Yeniləndi")
