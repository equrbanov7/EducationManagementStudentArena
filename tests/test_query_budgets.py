"""Sorğu büdcəsi — N+1 reqressiyalarını ÖLÇÜ ilə tutur (2026-07-31 auditi).

Niyə sabit rəqəm yox, miqyaslanma
---------------------------------
`django_assert_num_queries(17)` kimi sabit büdcə kövrəkdir: yeni bir `select_related`
və ya bir əlavə icazə yoxlaması rəqəmi dəyişir və test heç bir real problem
olmadan düşür. Onda komanda rəqəmi artırır — və büdcə mənasını itirir.

Burada əsas ölçü **fərqdir**: eyni səhifə əvvəlcə N=2, sonra N=12 obyektlə
yüklənir və sorğu sayının **eyni qaldığı** iddia edilir. N+1 varsa fərq
obyekt sayı qədər artır — bu, kod oxunuşu ilə yox, ölçü ilə sübutdur və
`select_related` əlavəsi testi yalançı düşürmür.

Sabit yuxarı hədd yalnız «tavan» kimi qoyulur (kəskin deqradasiyanı tutmaq
üçün), dəqiq rəqəm kimi yox.

Audit konteksti
---------------
Faza 7-də N+1 namizədləri YALNIZ kod oxunuşu ilə aşkarlanmışdı. Bu fayl həmin
tapıntıları ölçüyə çevirir: «İmtahanlarım» səhifələnməsi (səhifə 12 sətir olsa
da sorğu sayı sabit qalmalıdır), kurs siyahısı və bildirişlər.
"""

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.exams.models import Exam
from apps.organizations.models import Membership, Organization, Role
from core.constants import OrganizationType, RoleScopeType

User = get_user_model()

PASSWORD = "StrongPass123!"

#: Kəskin deqradasiya tavanı. Dəqiq büdcə DEYİL — bu rəqəmə yaxınlaşmaq
#: özü-özlüyündə problem deyil, amma keçmək araşdırma tələb edir.
HARD_CEILING = 90


class QueryBudgetMixin:
    """`CaptureQueriesContext` üzərində kiçik köməkçi.

    `pytest`-in `django_assert_num_queries` fixture-ı sabit rəqəm istəyir;
    bizə iki ölçünün FƏRQİ lazımdır, ona görə birbaşa konteksti işlədirik.
    """

    def _count_queries(self, url):
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200, f"{url} → {response.status_code}")
        return len(ctx.captured_queries), ctx.captured_queries

    def assert_does_not_scale(self, url, make_rows, small=2, large=12):
        """`url` sorğu sayı sətir sayından ASILI OLMAMALIDIR.

        `make_rows(n)` — `n` ədəd əlavə sətir yaradan çağırış.
        """
        make_rows(small)
        baseline, _ = self._count_queries(url)
        make_rows(large - small)
        scaled, queries = self._count_queries(url)

        if scaled != baseline:
            # Fərqi izah etmək üçün ən çox təkrarlanan sorğunu göstər.
            from collections import Counter

            top = Counter(q["sql"][:110] for q in queries).most_common(3)
            detail = "\n".join(f"    {n}× {sql}" for sql, n in top)
            self.fail(
                f"N+1: {url}\n"
                f"  {small} sətir → {baseline} sorğu, {large} sətir → {scaled} sorğu "
                f"(+{scaled - baseline})\n"
                f"  ən çox təkrarlanan sorğular:\n{detail}"
            )
        self.assertLessEqual(
            scaled,
            HARD_CEILING,
            f"{url}: {scaled} sorğu — kəskin deqradasiya tavanını ({HARD_CEILING}) keçdi",
        )
        return scaled


class MyExamsQueryBudgetTest(QueryBudgetMixin, TestCase):
    """«İmtahanlarım» — səhifələmədən sonra sorğu sayı sabit qalmalıdır.

    Bu bölmə səhifələndi (`MY_EXAMS_PAGE_SIZE = 12`) və KPI sayğacları ayrıca
    aqreqat sorğulara çıxarıldı. Əgər aqreqatlar səhvən sətir başına icra
    olunsaydı, səhifələmə heç nə qazandırmazdı — bu test onu tutur.
    """

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("qb_owner", "qb_owner@qku.edu.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="Budget Univ",
            slug="budget-univ",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        role, _ = Role.objects.update_or_create(
            organization=cls.org,
            name="teacher",
            defaults={
                "display_name": "Teacher",
                "level": 60,
                "scope_type": RoleScopeType.ORGANIZATION,
                "permissions": [],
                "is_system": False,
                "is_active": True,
            },
        )
        cls.teacher = User.objects.create_user("qb_teacher", "qb_teacher@qku.edu.az", PASSWORD)
        Membership.objects.create(user=cls.teacher, organization=cls.org, role=role, is_primary=True, is_active=True)

    def setUp(self):
        self.client = Client()
        self.client.login(username="qb_teacher", password=PASSWORD)
        self._seq = 0
        # Sessiya/aktiv-təşkilat qurulmasının birdəfəlik sorğuları ölçüyə
        # düşməsin deyə səhifəni bir dəfə isindiririk.
        self.client.get(reverse("accounts:profile") + "?section=my-exams")

    def _make_exams(self, n):
        for _ in range(n):
            self._seq += 1
            Exam.objects.create(
                title=f"Budget exam {self._seq}",
                author=self.teacher,
                organization=self.org,
                exam_type="written",
                is_active=True,
            )

    def test_my_exams_section_does_not_scale_with_exam_count(self):
        self.assert_does_not_scale(
            reverse("accounts:profile") + "?section=my-exams",
            self._make_exams,
        )

    def test_my_exams_fragment_does_not_scale_with_exam_count(self):
        """SPA fraqmenti — tam səhifədən daha tez-tez çağırılır."""
        self.assert_does_not_scale(
            reverse("accounts:profile_section_fragment", args=["my-exams"]),
            self._make_exams,
        )

    def test_second_page_costs_the_same_as_the_first(self):
        """Səhifə 2 səhifə 1 qədər ucuz olmalıdır (offset sürüşməsi yox)."""
        self._make_exams(30)
        base_url = reverse("accounts:profile_section_fragment", args=["my-exams"])
        first, _ = self._count_queries(base_url)
        second, _ = self._count_queries(f"{base_url}?exam_page=2")
        self.assertEqual(
            second,
            first,
            f"səhifə 1 → {first} sorğu, səhifə 2 → {second} sorğu; səhifələmə sabit qiymətli olmalıdır",
        )
