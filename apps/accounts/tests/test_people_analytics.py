"""Kataloq ANALİTİKASININ müqavilələri.

Beş şey kilidlənir:

1. **Filtrdən SONRA.** Göstəricilər cari filtr dəstinə aiddir — dekan öz
   fakültəsini süzəndə rəqəmlər həmin fakültəyə aid olur, bütün təşkilata YOX.
2. **Sorğu büdcəsi sabitdir.** 2 və 40 sətirdə eyni sorğu sayı (kataloq özü 5
   sorğu ilə işləyir; analitika onu sətir sayına bağlı ETMƏMƏLİDİR).
3. **Fail-closed.** Əhatəsi olmayan istifadəçi BOŞ statistika görür.
4. **İcazə ayrılığı.** `people.view_demographics` yoxdursa cins/yaş aqreqatı da
   qaytarılmır (rəqəm şəklində belə demoqrafiya sızmır).
5. **PII AI-a getmir.** AI yükündə ad, soyad, istifadəçi adı, e-poçt, telefon,
   FİN və axtarış mətni OLMUR. Qoruma NAXIŞ deyil, AĞ SİYAHIDIR: sərbəst mətn
   mənbəli sahələrin (`Membership.title` və s.) ETİKETİ ümumiyyətlə göndərilmir,
   yalnız «neçə fərqli dəyər» sayı gedir.
"""

from __future__ import annotations

import json

from django.db import connection
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext

from apps.accounts.services import people
from apps.accounts.services.people.analytics_ai import build_ai_payload
from apps.accounts.services.people.constants import (
    DEFAULT_PAGE_SIZE,
    STUDENT_SORT_OPTIONS,
    TEACHER_SORT_OPTIONS,
)
from apps.registrar.models import Program
from core.rls import bypass_rls

from .people_fixture import PeopleFixture


def _request(user, organization):
    request = RequestFactory().get("/accounts/profile/")
    request.user = user
    request.organization = organization
    return request


def _teacher_filters(**params):
    return people.parse_filters(params, sort_options=TEACHER_SORT_OPTIONS, default_page_size=DEFAULT_PAGE_SIZE)


def _student_filters(**params):
    return people.parse_filters(params, sort_options=STUDENT_SORT_OPTIONS, default_page_size=DEFAULT_PAGE_SIZE)


def _bucket(payload, key):
    for item in payload["breakdowns"]:
        if item["key"] == key:
            return item
    raise AssertionError(f"«{key}» bölgüsü qaytarılmadı: {[b['key'] for b in payload['breakdowns']]}")


class PeopleAnalyticsFilterTest(TestCase):
    """Göstəricilər CARİ FİLTRƏ görə hesablanır (sahibin əsas tələbi)."""

    @classmethod
    def setUpTestData(cls):
        cls.fx = PeopleFixture()

    def _actor(self, user):
        return people.resolve_actor(_request(user, self.fx.org))

    def test_org_wide_actor_sees_both_faculties(self):
        with bypass_rls():
            payload = people.build_teacher_analytics(actor=self._actor(self.fx.rector), filters=_teacher_filters())
        self.assertTrue(payload["has_access"])
        self.assertEqual(payload["total"], 2)  # teacher_a + teacher_b
        faculties = {row["label"] for row in _bucket(payload, "faculty")["rows"]}
        self.assertEqual(faculties, {"Fakültə A", "Fakültə B"})

    def test_dean_sees_only_own_faculty(self):
        """Scope daralması analitikaya da tətbiq olunur (siyahı ilə eyni dəst)."""
        with bypass_rls():
            payload = people.build_teacher_analytics(actor=self._actor(self.fx.dean_a), filters=_teacher_filters())
        self.assertEqual(payload["total"], 1)
        self.assertEqual([row["label"] for row in _bucket(payload, "faculty")["rows"]], ["Fakültə A"])

    def test_faculty_filter_narrows_the_numbers(self):
        actor = self._actor(self.fx.rector)
        with bypass_rls():
            unfiltered = people.build_teacher_analytics(actor=actor, filters=_teacher_filters())
            filtered = people.build_teacher_analytics(
                actor=actor, filters=_teacher_filters(faculty=str(self.fx.faculty_b.pk))
            )
        self.assertEqual(unfiltered["total"], 2)
        self.assertEqual(filtered["total"], 1)
        self.assertEqual([row["label"] for row in _bucket(filtered, "faculty")["rows"]], ["Fakültə B"])

    def test_search_filter_applies_to_analytics(self):
        with bypass_rls():
            payload = people.build_teacher_analytics(
                actor=self._actor(self.fx.rector), filters=_teacher_filters(q="Əliyev")
            )
        self.assertEqual(payload["total"], 1)

    def test_bucket_sums_match_the_headline_total(self):
        """Şəxs başına DƏQİQ BİR mənbə sətri seçilir — səbətlər cəmi ≠ ikiqat say."""
        with bypass_rls():
            payload = people.build_teacher_analytics(actor=self._actor(self.fx.rector), filters=_teacher_filters())
        for key in ("faculty", "kafedra", "role"):
            self.assertEqual(
                sum(row["count"] for row in _bucket(payload, key)["rows"]),
                payload["total"],
                f"«{key}» bölgüsünün cəmi ümumi sayla üst-üstə düşmür.",
            )

    def test_student_analytics_reports_program_and_course(self):
        """İxtisas səbətinin etiketi: ``Ad · <RƏSMİ şifr>``.

        ⚠️ REQRESSİYA QORUYUCUSU: etiket əvvəllər DAXİLİ ``Program.code``
        («PA», «PB» — köçürmənin ``MYEDU-*`` açarı) ilə qurulurdu və uydurma
        açar birbaşa istifadəçinin filtr siyahısına sızırdı. İndi yalnız rəsmi
        dövlət şifri işlədilir (cari NK 503 şifri, yoxsa əvvəlki nəsil şifr).
        """
        with bypass_rls():
            Program.objects.filter(pk=self.fx.program_a.pk).update(official_code="6004002")
            # İkinci proqram yeni təsnifatda LƏĞV olunub — yalnız köhnə şifri var,
            # etiket ona geri çəkilməlidir (şifrsiz qalmamalıdır).
            Program.objects.filter(pk=self.fx.program_b.pk).update(legacy_official_code="050401")
            payload = people.build_student_analytics(actor=self._actor(self.fx.rector), filters=_student_filters())
        self.assertEqual(payload["total"], 2)
        programs = {row["label"] for row in _bucket(payload, "program")["rows"]}
        self.assertEqual(programs, {"Proqram A · 6004002", "Proqram B · 050401"})
        for label in programs:
            self.assertNotIn("PA", label)
            self.assertNotIn("PB", label)
        self.assertEqual(sum(row["count"] for row in _bucket(payload, "course")["rows"]), 2)

    def test_student_group_filter_narrows_the_numbers(self):
        actor = self._actor(self.fx.rector)
        with bypass_rls():
            payload = people.build_student_analytics(
                actor=actor, filters=_student_filters(group=str(self.fx.group_a1.pk))
            )
        self.assertEqual(payload["total"], 1)
        self.assertEqual([row["label"] for row in _bucket(payload, "group")["rows"]], ["Qrup A1-1"])


class PeopleAnalyticsPermissionTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.fx = PeopleFixture()

    def _actor(self, user):
        return people.resolve_actor(_request(user, self.fx.org))

    def test_unscoped_dean_gets_empty_analytics(self):
        """`scope_unit` təyin edilməmiş UNIT rolu → BOŞ statistika, org-wide YOX."""
        with bypass_rls():
            payload = people.build_teacher_analytics(
                actor=self._actor(self.fx.dean_unscoped), filters=_teacher_filters()
            )
        self.assertFalse(payload["has_access"])
        self.assertEqual(payload["total"], 0)
        self.assertEqual(payload["breakdowns"], [])
        self.assertEqual(payload["status"], [])

    def test_actor_without_view_permission_gets_empty_analytics(self):
        with bypass_rls():
            payload = people.build_students_page(actor=self._actor(self.fx.teacher_a), filters=_student_filters())
            analytics = people.build_student_analytics(actor=self._actor(self.fx.teacher_a), filters=_student_filters())
        self.assertFalse(payload["has_access"])
        self.assertFalse(analytics["has_access"])
        self.assertEqual(analytics["total"], 0)

    def test_demographics_are_withheld_without_the_permission(self):
        """Kafedra müdirində `view_demographics` yoxdur → cins/yaş aqreqatı boşdur."""
        with bypass_rls():
            chair = people.build_teacher_analytics(actor=self._actor(self.fx.chair_a1), filters=_teacher_filters())
            rector = people.build_teacher_analytics(actor=self._actor(self.fx.rector), filters=_teacher_filters())
        self.assertFalse(chair["can_view_demographics"])
        self.assertEqual(chair["gender"], [])
        self.assertEqual(chair["age"]["buckets"], [])
        self.assertGreater(chair["total"], 0)  # say görünür, demoqrafiya yox

        self.assertTrue(rector["can_view_demographics"])
        self.assertEqual(len(rector["gender"]), 3)
        self.assertEqual(len(rector["age"]["buckets"]), 6)


class PeopleAnalyticsQueryBudgetTest(TestCase):
    """Sorğu sayı sətir sayı ilə ARTMAMALIDIR (2 vs 40 sətir)."""

    @classmethod
    def setUpTestData(cls):
        cls.fx = PeopleFixture()

    def _actor(self, user):
        return people.resolve_actor(_request(user, self.fx.org))

    def test_teacher_analytics_query_count_is_constant(self):
        actor = self._actor(self.fx.rector)
        filters = _teacher_filters()
        with bypass_rls():
            people.build_teacher_analytics(actor=actor, filters=filters)  # isindirmə
            with CaptureQueriesContext(connection) as small:
                small_payload = people.build_teacher_analytics(actor=actor, filters=filters)
            for index in range(38):
                self.fx.add_teacher(f"pan_bulk_t{index}", last=f"Bulkov{index}")
            with CaptureQueriesContext(connection) as large:
                large_payload = people.build_teacher_analytics(actor=actor, filters=filters)

        self.assertEqual(small_payload["total"], 2)
        self.assertEqual(large_payload["total"], 40)
        self.assertEqual(
            len(large.captured_queries),
            len(small.captured_queries),
            "Müəllim analitikasında N+1: sətir sayı artdıqca sorğu sayı da artdı.\n"
            + "\n".join(query["sql"][:160] for query in large.captured_queries),
        )

    def test_student_analytics_query_count_is_constant(self):
        actor = self._actor(self.fx.rector)
        filters = _student_filters()
        with bypass_rls():
            people.build_student_analytics(actor=actor, filters=filters)
            with CaptureQueriesContext(connection) as small:
                small_payload = people.build_student_analytics(actor=actor, filters=filters)
            for index in range(38):
                self.fx.add_student(f"pan_bulk_s{index}", faculty="a", last=f"Bulkova{index}")
            with CaptureQueriesContext(connection) as large:
                large_payload = people.build_student_analytics(actor=actor, filters=filters)

        self.assertEqual(small_payload["total"], 2)
        self.assertEqual(large_payload["total"], 40)
        self.assertEqual(
            len(large.captured_queries),
            len(small.captured_queries),
            "Tələbə analitikasında N+1: sətir sayı artdıqca sorğu sayı da artdı.\n"
            + "\n".join(query["sql"][:160] for query in large.captured_queries),
        )


class PeopleAnalyticsAiPayloadTest(TestCase):
    """AI-a YALNIZ aqreqat gedir — şəxsi məlumat və axtarış mətni GETMİR."""

    @classmethod
    def setUpTestData(cls):
        cls.fx = PeopleFixture()

    def _actor(self, user):
        return people.resolve_actor(_request(user, self.fx.org))

    def _payload_text(self, kind="teachers", **params):
        actor = self._actor(self.fx.rector)
        filters = _teacher_filters(**params) if kind == "teachers" else _student_filters(**params)
        with bypass_rls():
            analytics = (
                people.build_teacher_analytics(actor=actor, filters=filters)
                if kind == "teachers"
                else people.build_student_analytics(actor=actor, filters=filters)
            )
        payload = build_ai_payload(analytics, filters=filters)
        return payload, json.dumps(payload, ensure_ascii=False, default=str)

    def test_ai_payload_contains_no_person_identifiers(self):
        for kind in ("teachers", "students"):
            _payload, text = self._payload_text(kind)
            for secret in (
                self.fx.teacher_a.first_name,
                self.fx.teacher_a.last_name,
                self.fx.teacher_a.username,
                self.fx.teacher_a.email,
                self.fx.student_a.last_name,
                self.fx.student_a.username,
                "+994500000000",
                "Səməd oğlu",
            ):
                self.assertNotIn(secret, text, f"«{kind}» AI yükünə şəxsi məlumat düşdü: {secret}")

    def test_ai_payload_never_carries_the_search_text(self):
        """Operator axtarış xanasına şəxsin adını yaza bilər — o sətir AI-a getmir."""
        payload, text = self._payload_text("teachers", q="Əliyev Elvin")
        self.assertNotIn("Əliyev", text)
        self.assertTrue(payload["scope"]["search_applied"])

    def test_ai_payload_keys_are_allowlisted(self):
        payload, _text = self._payload_text("teachers")
        self.assertEqual(
            set(payload),
            {"kind", "total", "status", "gender", "age", "breakdowns", "workload", "scope"},
        )

    def test_ai_payload_carries_the_aggregate_numbers(self):
        payload, _text = self._payload_text("teachers")
        self.assertEqual(payload["total"], 2)
        self.assertTrue(payload["breakdowns"])
        self.assertTrue(payload["workload"])

    # ── Sərbəst mətn AI-a GETMİR (ağ siyahı, naxış deyil) ──────────────────

    def _set_title(self, user, title):
        """`Membership.title` — SƏRBƏST mətn sahəsi (operator nə yazsa, o qalır)."""
        from apps.organizations.models import Membership

        with bypass_rls():
            Membership.objects.filter(organization=self.fx.org, user=user).update(title=title)

    def test_free_text_title_never_reaches_the_ai_payload(self):
        """Real prob: vəzifə sahəsinə ad + FİN yazılıb — yükdə GÖRÜNMƏMƏLİDİR.

        Köhnə qat yalnız e-poçt/telefon naxışını silirdi, ona görə bu sətir
        `{"key": "title", "rows": [{"label": "Dos. ..."}]}` kimi AI-a düşürdü.
        """
        probe = "Dos. Elvin Qurbanov (FIN 5AB7C9D)"
        self._set_title(self.fx.teacher_a, probe)

        payload, text = self._payload_text("teachers")

        self.assertNotIn(probe, text)
        self.assertNotIn("Qurbanov", text)
        self.assertNotIn("5AB7C9D", text)
        block = _bucket(payload, "title")
        self.assertTrue(block["labels_withheld"])
        self.assertNotIn("rows", block)
        self.assertEqual(block["people"], 2)
        self.assertEqual(block["distinct_values"], 2)

    def test_structure_labels_are_still_sent(self):
        """Ağ siyahı hər şeyi kəsmir: struktur adları AI üçün lazımdır və qalır."""
        payload, _text = self._payload_text("teachers")

        labels = [row["label"] for row in _bucket(payload, "kafedra")["rows"]]
        self.assertIn(self.fx.kafedra_a1.name, labels)

    def test_unlisted_keys_lose_their_labels(self):
        """Sabah əlavə olunan bölgü/göstərici SƏSSİZCƏ PII gətirə bilməz."""
        payload = build_ai_payload(
            {
                "kind": "teachers",
                "total": 1,
                "breakdowns": [
                    {
                        "key": "bio",
                        "title": "Tərcümeyi-hal",
                        "rows": [{"label": "Elvin Qurbanov, FIN 5AB7C9D", "count": 1, "percent": 100.0}],
                    },
                    {"key": "Sərbəst açar", "title": "x", "rows": [{"label": "gizli-etiket", "count": 1}]},
                ],
                "workload": [
                    {"key": "offerings", "label": "Dərs açılışı", "value": 3},
                    {"key": "staff_position", "label": "Dos. Elvin Qurbanov", "value": 1},
                ],
            }
        )
        text = json.dumps(payload, ensure_ascii=False, default=str)

        self.assertNotIn("Qurbanov", text)
        self.assertNotIn("gizli-etiket", text)
        # Açarı formata uymayan bölgü ÜMUMİYYƏTLƏ düşmür.
        self.assertEqual([item["key"] for item in payload["breakdowns"]], ["bio"])
        # Dərs yükündə sərbəst mətn yoxdur: yalnız tanınan açar + rəqəm.
        self.assertEqual(payload["workload"], [{"key": "offerings", "value": 3}])

    def test_enum_labels_come_from_code_not_from_data(self):
        """Status/cins etiketi KODDAKI xəritədəndir — dataya güvənilmir."""
        payload = build_ai_payload(
            {
                "kind": "teachers",
                "status": [
                    {"key": "active", "label": "Elvin Qurbanov", "count": 2},
                    {"key": "smuggled", "label": "FIN 5AB7C9D", "count": 1},
                ],
                "gender": [{"key": "male", "label": "Elvin Qurbanov", "count": 1}],
            }
        )
        text = json.dumps(payload, ensure_ascii=False, default=str)

        self.assertNotIn("Qurbanov", text)
        self.assertNotIn("5AB7C9D", text)
        self.assertEqual([row["key"] for row in payload["status"]], ["active"])

    def test_scope_never_carries_free_text_filter_values(self):
        """`?year=` sorğu parametri də sərbəst mətndir — ciddi formatdan keçir."""
        payload, text = self._payload_text("teachers", year="Elvin Qurbanov FIN 5AB", season="Payız")

        self.assertNotIn("Qurbanov", text)
        self.assertEqual(payload["scope"]["academic_year"], "")
        self.assertTrue(payload["scope"]["season_filter"])


class PeopleAnalyticsEndpointTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.fx = PeopleFixture()

    def test_analytics_endpoint_returns_payload(self):
        self.client.force_login(self.fx.dean_a)
        response = self.client.get("/accounts/people/teachers/analytics/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["has_access"])
        self.assertEqual(payload["kind"], "teachers")
        self.assertEqual(payload["total"], 1)

    def test_analytics_endpoint_is_fail_closed(self):
        self.client.force_login(self.fx.teacher_a)
        response = self.client.get("/accounts/people/students/analytics/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["has_access"])
        self.assertEqual(payload["total"], 0)
        self.assertEqual(payload["breakdowns"], [])

    def test_unknown_catalog_is_rejected(self):
        self.client.force_login(self.fx.rector)
        response = self.client.get("/accounts/people/parents/analytics/")
        self.assertEqual(response.status_code, 404)

    def test_ai_endpoint_never_500s_without_access(self):
        self.client.force_login(self.fx.teacher_a)
        response = self.client.get("/accounts/people/teachers/analytics/ai/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["ok"])

    def test_section_fragment_carries_the_analytics_hooks(self):
        self.client.force_login(self.fx.dean_a)
        response = self.client.get("/accounts/profile/api/sections/people-teachers/")
        self.assertEqual(response.status_code, 200)
        html = response.json()["html"]
        self.assertIn("data-people-analytics", html)
        self.assertIn("/analytics/", html)
        self.assertIn("data-pan-charts", html)
