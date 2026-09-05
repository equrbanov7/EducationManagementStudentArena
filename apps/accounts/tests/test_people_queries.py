"""Kataloqun SORĞU BÜDCƏSİ və ƏMƏLLƏRİ.

Üç müqavilə kilidlənir:

1. **N+1 YOXDUR.** Sorğu sayı sətir sayı ilə ARTMAMALIDIR. 8 000+ hesablı real
   məlumat bazasında bir sətir üçün əlavə sorğu 25 sətirlik səhifəni 25 əlavə
   gediş-gəlişə çevirər. Test iki fərqli ölçüdə eyni sorğu sayını tələb edir.

2. **MÜTLƏQ BÜDCƏ = 4 sorğu.** Yalnız «artmır» demək azdır: sabit qalan, amma
   9-a sıçramış say da reqressiyadır. Tələbə idarəetmə səthi (``psm-*`` çekməcəsi)
   QƏSDƏN kataloqun ÜSTÜNDƏ, AYRI endpoint-lərdə oturur — siyahı yoluna bir
   sorğu belə əlavə etməməlidir. Dörd sorğu: COUNT · səhifə sətirləri ·
   struktur vahidləri · vahid adları (ata-baba həlli). Üzvlük/scope həlli
   (``get_permission_scope``) AYRICA sorğu DEYİL — QA 2026-09 keş auditindən
   sonra ``user`` obyektinə görə memoizasiya olunur (bax
   ``apps.organizations.scoping._permission_scope_memberships``), ona görə bu
   testin «isindirmə» çağırışı ilə eyni aktoru bölüşən ölçmə çağırışı onu
   TƏKRAR sorğulamır.

3. **Əməllər SCOPE-LUDUR.** Dekan öz fakültəsindən kənar hesabı dayandıra
   BİLMƏMƏLİDİR — RİM qatı bunu bilmir (o, yalnız rütbə/tenant yoxlayır), ona
   görə qapı kataloq qatındadır və məhz burada sınanır.
"""

from __future__ import annotations

from django.db import connection
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext

from apps.accounts.services import people
from apps.accounts.services.people.constants import DEFAULT_PAGE_SIZE, TEACHER_SORT_OPTIONS
from apps.accounts.services.rim.policy import RimAccessError
from core.rls import bypass_rls

from .people_fixture import PeopleFixture


def _request(user, organization):
    request = RequestFactory().get("/accounts/profile/")
    request.user = user
    request.organization = organization
    return request


def _filters(**params):
    return people.parse_filters(params, sort_options=TEACHER_SORT_OPTIONS, default_page_size=DEFAULT_PAGE_SIZE)


#: Bir kataloq səhifəsinin MÜTLƏQ sorğu büdcəsi. Rəqəmi qaldırmaq üçün əvvəlcə
#: yeni sorğunun niyə qaçılmaz olduğu izah edilməlidir — «testi düzəltmək» kifayət
#: deyil (bax modul başlığı, 2-ci müqavilə).
#: 5 → 4 (QA 2026-09 RBAC keş auditi): `get_permission_scope`-un membership
#: sorğusu artıq `user` obyektinə görə memoizasiya olunur, ona görə bu testin
#: isindirmə çağırışı ilə eyni aktoru bölüşən ölçmə çağırışı onu TƏKRAR
#: sorğulamır (bax `apps.organizations.scoping._permission_scope_memberships`).
LIST_QUERY_BUDGET = 4


class PeopleQueryBudgetTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.fx = PeopleFixture()

    def _actor(self, user):
        return people.resolve_actor(_request(user, self.fx.org))

    def test_teacher_list_query_count_does_not_grow_with_rows(self):
        actor = self._actor(self.fx.rector)
        filters = _filters(page_size=100)
        with bypass_rls():
            # Qərəzli müqayisə olmasın deyə hər iki ölçmə eyni kod yolundan keçir.
            people.build_teachers_page(actor=actor, filters=filters)
            with CaptureQueriesContext(connection) as small:
                small_payload = people.build_teachers_page(actor=actor, filters=filters)
            for index in range(12):
                self.fx.add_teacher(f"ppl_bulk_t{index}", last=f"Bulkov{index}")
            with CaptureQueriesContext(connection) as large:
                large_payload = people.build_teachers_page(actor=actor, filters=filters)

        self.assertGreater(len(large_payload["results"]), len(small_payload["results"]))
        self.assertEqual(
            len(large.captured_queries),
            len(small.captured_queries),
            "Müəllim siyahısında N+1: sətir sayı artdıqca sorğu sayı da artdı.\n"
            + "\n".join(query["sql"][:160] for query in large.captured_queries),
        )

    def test_student_list_query_count_does_not_grow_with_rows(self):
        actor = self._actor(self.fx.rector)
        filters = _filters(page_size=100)
        with bypass_rls():
            people.build_students_page(actor=actor, filters=filters)
            with CaptureQueriesContext(connection) as small:
                small_payload = people.build_students_page(actor=actor, filters=filters)
            for index in range(12):
                self.fx.add_student(f"ppl_bulk_s{index}", faculty="a", last=f"Bulkova{index}")
            with CaptureQueriesContext(connection) as large:
                large_payload = people.build_students_page(actor=actor, filters=filters)

        self.assertGreater(len(large_payload["results"]), len(small_payload["results"]))
        self.assertEqual(
            len(large.captured_queries),
            len(small.captured_queries),
            "Tələbə siyahısında N+1: sətir sayı artdıqca sorğu sayı da artdı.\n"
            + "\n".join(query["sql"][:160] for query in large.captured_queries),
        )

    def test_list_pages_stay_within_the_absolute_query_budget(self):
        """Hər iki kataloq TAM ``LIST_QUERY_BUDGET`` sorğu ilə qurulur.

        «Artmır» testi sabit, amma şişmiş sayı tutmur; bu test rəqəmin ÖZÜNÜ
        kilidləyir. Tələbə idarəetmə çekməcəsi kataloqun üstündə AYRI
        endpoint-lərdən (kart / qrup axtarışı / ön baxış) qidalanır, ona görə
        siyahı yolunun büdcəsi ona görə dəyişməməlidir.
        """
        actor = self._actor(self.fx.rector)
        filters = _filters(page_size=100)
        for label, builder in (
            ("Tələbə", people.build_students_page),
            ("Müəllim", people.build_teachers_page),
        ):
            with self.subTest(catalog=label):
                with bypass_rls():
                    # Isindirmə: icazə/etiket keşləri ilk çağırışda dolur, yoxsa
                    # ölçmə növbə sırasından asılı olardı.
                    builder(actor=actor, filters=filters)
                    with CaptureQueriesContext(connection) as captured:
                        builder(actor=actor, filters=filters)
                self.assertEqual(
                    len(captured.captured_queries),
                    LIST_QUERY_BUDGET,
                    f"{label} kataloqunun sorğu büdcəsi pozuldu "
                    f"({len(captured.captured_queries)} ≠ {LIST_QUERY_BUDGET}).\n"
                    + "\n".join(query["sql"][:160] for query in captured.captured_queries),
                )


class PeopleActionScopeTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.fx = PeopleFixture()

    def _actor(self, user):
        return people.resolve_actor(_request(user, self.fx.org))

    def test_dean_can_block_own_faculty_teacher(self):
        actor = self._actor(self.fx.dean_a)
        with bypass_rls():
            result = people.set_account_status(actor, self.fx.teacher_a, active=False, reason="Uzunmüddətli məzuniyyət")
            self.fx.teacher_a.refresh_from_db()
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(self.fx.teacher_a.is_active)

        with bypass_rls():
            people.set_account_status(actor, self.fx.teacher_a, active=True, reason="Qayıtdı")
            self.fx.teacher_a.refresh_from_db()
        self.assertTrue(self.fx.teacher_a.is_active)

    def test_dean_cannot_block_teacher_from_another_faculty(self):
        actor = self._actor(self.fx.dean_a)
        with self.assertRaises(RimAccessError) as ctx:
            with bypass_rls():
                people.set_account_status(actor, self.fx.teacher_b, active=False, reason="Səbəb")
        self.assertEqual(ctx.exception.reason_code, "target_outside_scope")
        self.assertEqual(ctx.exception.status, 404)
        self.fx.teacher_b.refresh_from_db()
        self.assertTrue(self.fx.teacher_b.is_active)

    def test_chair_without_manage_permission_cannot_block(self):
        actor = self._actor(self.fx.chair_a1)
        with self.assertRaises(RimAccessError) as ctx:
            with bypass_rls():
                people.set_account_status(actor, self.fx.teacher_a, active=False, reason="Səbəb")
        self.assertEqual(ctx.exception.reason_code, "permission_denied")

    def test_block_requires_a_reason(self):
        actor = self._actor(self.fx.dean_a)
        with self.assertRaises(RimAccessError) as ctx:
            with bypass_rls():
                people.set_account_status(actor, self.fx.teacher_a, active=False, reason="")
        self.assertEqual(ctx.exception.reason_code, "reason_required")

    def test_action_is_audited(self):
        from apps.audit.models import AuditLog

        actor = self._actor(self.fx.dean_a)
        with bypass_rls():
            people.set_account_status(actor, self.fx.teacher_a, active=False, reason="Audit sınağı")
            entries = list(AuditLog.objects.filter(resource_type="accounts.people"))
            people.set_account_status(actor, self.fx.teacher_a, active=True, reason="Geri")
        self.assertTrue(entries, "Kataloq əməli audit jurnalına düşmədi.")
        self.assertEqual(entries[-1].changes.get("action"), "people.account_blocked")

    def test_grant_and_revoke_teacher_role(self):
        actor = self._actor(self.fx.dean_a)
        with bypass_rls():
            target = self.fx.add_student("ppl_future_teacher", faculty="a", last="Yeniyev")
            people.set_teacher_role(
                actor, target, grant=True, reason="Kafedraya təyinat", unit_id=str(self.fx.kafedra_a1.pk)
            )
            _payload = people.build_teachers_page(actor=actor, filters=_filters(page_size=100))
        self.assertIn("ppl_future_teacher", {row["username"] for row in _payload["results"]})

        with bypass_rls():
            people.set_teacher_role(actor, target, grant=False, reason="Təyinat ləğv edildi")
            _payload = people.build_teachers_page(actor=actor, filters=_filters(page_size=100))
        self.assertNotIn("ppl_future_teacher", {row["username"] for row in _payload["results"]})

    def test_grant_rejects_unit_outside_scope(self):
        actor = self._actor(self.fx.dean_a)
        with bypass_rls():
            target = self.fx.add_student("ppl_future_teacher_b", faculty="a", last="Kənarov")
            with self.assertRaises(RimAccessError) as ctx:
                people.set_teacher_role(actor, target, grant=True, reason="Səbəb", unit_id=str(self.fx.kafedra_b1.pk))
        self.assertEqual(ctx.exception.reason_code, "unit_outside_scope")

    def test_unit_scoped_actor_must_pick_a_unit_when_granting(self):
        actor = self._actor(self.fx.dean_a)
        with bypass_rls():
            target = self.fx.add_student("ppl_future_teacher_c", faculty="a", last="Unitsiz")
            with self.assertRaises(RimAccessError) as ctx:
                people.set_teacher_role(actor, target, grant=True, reason="Səbəb", unit_id=None)
        self.assertEqual(ctx.exception.reason_code, "unit_required")


class PeopleEndpointTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.fx = PeopleFixture()

    def _login(self, user):
        self.client.force_login(user)

    def test_list_endpoint_requires_permission(self):
        self._login(self.fx.teacher_a)
        response = self.client.get("/accounts/people/teachers/list/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["has_access"])

    def test_unknown_catalog_is_rejected(self):
        self._login(self.fx.rector)
        response = self.client.get("/accounts/people/parents/list/")
        self.assertEqual(response.status_code, 404)

    def test_action_endpoint_rejects_unknown_action(self):
        self._login(self.fx.dean_a)
        response = self.client.post(
            "/accounts/people/action/",
            data={"action": "delete_everything", "user_id": self.fx.teacher_a.pk},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "unknown_action")

    def test_detail_endpoint_hides_out_of_scope_person(self):
        self._login(self.fx.dean_a)
        response = self.client.get(f"/accounts/people/person/{self.fx.teacher_b.pk}/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "target_outside_scope")

    def test_section_fragment_renders_for_permitted_actor(self):
        """Bölmə AJAX yolu ilə açılmalıdır (SECTION_PARTIALS ↔ AJAX_SAFE ↔ rbac)."""
        self._login(self.fx.dean_a)
        response = self.client.get("/accounts/profile/api/sections/people-teachers/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertIn('data-profile-section-panel="people-teachers"', payload["html"])
        self.assertIn("data-people-root", payload["html"])

    def test_section_fragment_is_denied_without_permission(self):
        self._login(self.fx.teacher_a)
        response = self.client.get("/accounts/profile/api/sections/people-students/")
        self.assertEqual(response.status_code, 403)
