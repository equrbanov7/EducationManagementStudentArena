"""Jurnal siyahısının (org-wide korrektor görünüşü) sorğu büdcəsi (QA 2026-09-05
P2-18 — bax :mod:`apps.registrar.journal_list_query`).

Əvvəllər `journal_list_context` BÜTÜN offering-ləri model instansiyası kimi
yükləyib (3 səviyyəli `select_related` + `Count` annotasiyası) Python-da
süzürdü — İKT rəhbəri (org-wide) görünüşündə açılış sayı artdıqca sorğu SAYI
sabit qalsa da hər sorğunun ölçüsü (və CPU) xətti artırdı, dropdown-lar isə
TAM dəst üzərində əl ilə təkrarsızlaşdırılırdı. Bu test açılış sayını 4-dən
40-a çoxaldıb sorğu SAYININ DƏYİŞMƏDİYİNİ (data həcmindən asılı olmadığını)
qıfıllayır — registrasiya, N+1 və ya yenidən tam-dəst yükləməsi geri
qayıtsaydı bu test qırılardı."""

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import services
from apps.registrar.models import Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

#: Real sorğu sayı bundan kiçik/bərabərdirsə keçər — bir neçə sabit sorğu
#: (org resolve, permission, dövr/il/fəsil, 3 dropdown, count + səhifə + kind
#: etiketləri) üçün rahat pay, amma "N açılış = N-ə mütənasib sorğu" halını
#: dərhal tutacaq qədər sıxdır.
MAX_QUERIES = 40


class JournalListQueryBudgetTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("jlq_owner", "jlq_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="JLQ Univ",
                slug="jlq-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.faculty = OrgUnit.objects.create(
                organization=cls.org, name="JLQ Fakültə", slug="jlq-fac", unit_type=OrgUnitType.FACULTY
            )
            cls.group_a = OrgUnit.objects.create(
                organization=cls.org, name="JLQ-A", slug="jlq-g-a", unit_type=OrgUnitType.GROUP, parent=cls.faculty
            )
            cls.group_b = OrgUnit.objects.create(
                organization=cls.org, name="JLQ-B", slug="jlq-g-b", unit_type=OrgUnitType.GROUP, parent=cls.faculty
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
            cls.admin = User.objects.create_user("jlq_admin", "jlq_admin@qku.edu.az", "pw", is_superuser=True)

    def _client(self):
        client = Client()
        client.force_login(self.admin)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _seed_offerings(self, count: int, prefix: str) -> None:
        with bypass_rls():
            for i in range(count):
                teacher = User.objects.create_user(f"jlq_t_{prefix}_{i}", f"jlq_t_{prefix}_{i}@qku.edu.az", "pw")
                Membership.objects.create(
                    user=teacher,
                    organization=self.org,
                    role=self.org.roles.get(name="teacher"),
                    is_primary=True,
                    is_active=True,
                )
                subject = Subject.objects.create(
                    organization=self.org, code=f"JLQ{prefix.upper()}{i:03d}", name=f"JLQ fənni {prefix} {i}"
                )
                group = self.group_a if i % 2 == 0 else self.group_b
                offering = services.get_or_create_offering(
                    organization=self.org, subject=subject, period=self.period, group=group
                )
                offering.instructor = teacher
                offering.save(update_fields=["instructor"])

    def test_broad_journal_list_query_count_does_not_scale_with_offering_volume(self):
        client = self._client()
        # İsti-tut sorğusu (say-a DAXİL DEYİL): ContentType/permission keşi kimi
        # PROSES-səviyyəli, YALNIZ BİRİNCİ çağırışda görünən sorğuları udur —
        # əks halda "kiçik dəst" ölçüsü süni şəkildə şişər (soyuq keş).
        client.get(reverse("registrar:journal_list"), {"year": "2024/2025"})

        self._seed_offerings(4, "a")
        with CaptureQueriesContext(connection) as small:
            resp_small = client.get(reverse("registrar:journal_list"), {"year": "2024/2025"})
        self.assertEqual(resp_small.status_code, 200)
        small_count = len(small.captured_queries)

        # Ordu-lu qatı da yoxlayaq: fakültə/qrup/müəllim dropdown-larının həqiqətən
        # dolduğunu (boş qalıb sükutla keçmədiyini) təsdiqləyir.
        self.assertContains(resp_small, 'name="teacher"')
        self.assertContains(resp_small, 'name="faculty"')

        self._seed_offerings(36, "b")  # cəmi 40 açılış
        with CaptureQueriesContext(connection) as large:
            resp_large = client.get(reverse("registrar:journal_list"), {"year": "2024/2025"})
        self.assertEqual(resp_large.status_code, 200)
        large_count = len(large.captured_queries)

        self.assertEqual(
            small_count,
            large_count,
            "sorğu sayı açılış sayına görə dəyişir — dropdown/süzgəc yenidən "
            "TAM dəst üzərində Python-da hesablanır (P2-18 reqressiyası)",
        )
        self.assertLessEqual(
            large_count,
            MAX_QUERIES,
            f"jurnal siyahısı sorğu büdcəsini keçdi ({large_count} > {MAX_QUERIES})",
        )

    def test_own_journal_view_stays_cheap_and_unaffected(self):
        # Adi müəllim (broad DEYİL) görünüşü bu refaktordan toxunulmaz qalmalıdır.
        self._seed_offerings(10, "c")
        teacher = User.objects.filter(username="jlq_t_c_0").get()
        client = Client()
        client.force_login(teacher)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        with CaptureQueriesContext(connection) as ctx:
            resp = client.get(reverse("registrar:journal_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertLessEqual(len(ctx.captured_queries), MAX_QUERIES)
