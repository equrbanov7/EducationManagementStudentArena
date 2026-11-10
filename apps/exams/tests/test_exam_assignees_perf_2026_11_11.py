"""«Tapşırıq təyin olunmuşlar» — sürət (sahib 2026-11-10: «çox yavaş açılır; qrup / tələbə əlavə edəndə qrup
artdıqca gecikmə artır; search edərkən səhifə zəif hərəkət edir»).

Kök səbəblər və düzəlişlər:

* ``subgroup_rollup.subgroup_pattern`` hər (qrup × qardaş qrup) cütü üçün regex-i YENİDƏN kompilyasiya edirdi
  (``re`` keşi 512 şablondan sonra daşır) — indi ``lru_cache``;
* siyahı səhifəsi reyestr qrupu üzvlərini iki dəfə hesablayırdı, mətn süzgəci şablonu hər sətirdə qururdu;
* hər süzgəc / çip / səhifə / əlavə əməli TAM səhifəni yenidən yükləyirdi — indi ``X-EAS-Partial`` fraqmenti.

Bu fayl sorğu büdcələrini (tələbə / qrup sayından asılı olmayan) və fraqment rejiminin düzgünlüyünü qoruyur.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.db import connection
from django.test import SimpleTestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.exams.models import ExamAttempt, ExamStudentPin
from apps.exams.services import exam_assignees
from apps.exams.services.student_pins import _assigned_student_ids
from apps.exams.tests.test_exam_assignees_2026_10_27 import _Fixture
from apps.exams.tests.test_w4_wizard_units import _login
from apps.exams.views.teacher.exams.assignee_edit import AUDIT_REASON
from apps.organizations.models import Membership, OrgUnit
from apps.registrar import subgroup_rollup
from apps.registrar.models import StudentAcademicRecord
from core.constants import OrgUnitType
from core.rls import bypass_rls
from core.search_text import tolerant_match, tolerant_matcher

User = get_user_model()
REPO = Path(__file__).resolve().parents[3]
PARTIAL = {"HTTP_X_EAS_PARTIAL": "1"}
AJAX = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}


class _ScaleFixture(_Fixture):
    """N reyestr qrupu × M tələbə (toplu yaradılır) — büdcə müqayisələri üçün."""

    _serial = 0

    def _units(self, count, students_each, *, parent=None):
        type(self)._serial += 1
        tag = f"p{type(self)._serial}"
        role = self.org.roles.get(name="student")
        with bypass_rls():
            units = OrgUnit.objects.bulk_create(
                [
                    OrgUnit(
                        organization=self.org,
                        parent=parent or self.faculty,
                        name=f"{700 + index} {tag} az",
                        slug=f"eas-{tag}-{index}",
                        unit_type=OrgUnitType.GROUP,
                    )
                    for index in range(count)
                ]
            )
            users = User.objects.bulk_create(
                [
                    User(username=f"{tag}_{g}_{s}", email=f"{tag}_{g}_{s}@test.az", first_name="Ad", last_name=f"S{s}")
                    for g in range(count)
                    for s in range(students_each)
                ]
            )
            Membership.objects.bulk_create(
                [Membership(user=user, organization=self.org, role=role, is_active=True) for user in users]
            )
            StudentAcademicRecord.objects.bulk_create(
                [
                    StudentAcademicRecord(
                        organization=self.org,
                        student=user,
                        program=self.program,
                        curriculum=self.curriculum,
                        group=units[index // students_each],
                        admission_year=2024,
                    )
                    for index, user in enumerate(users)
                ]
            )
        return units, users

    def _client(self):
        return _login(self.teacher, self.org)

    def _page_url(self, exam):
        return reverse("exams:teacher_exam_assignees", kwargs={"slug": exam.slug})

    def _update_url(self, exam):
        return reverse("exams:teacher_exam_assignees_update", kwargs={"slug": exam.slug})

    def _measure(self, call):
        with CaptureQueriesContext(connection) as ctx:
            response = call()
        return len(ctx), response


class PageBudgetTests(_ScaleFixture):
    def _exam_with(self, groups, students_each, title):
        units, users = self._units(groups, students_each)
        exam = self._exam(title=title, exam_type_extended="midterm")
        exam.allowed_units.add(*units)
        with bypass_rls():
            ExamAttempt.objects.bulk_create(
                [
                    ExamAttempt(exam=exam, user=user, status="submitted", finished_at=timezone.now(), correct_count=1)
                    for user in users[::2]
                ]
            )
        return exam, users

    def _count(self, exam, **extra):
        client = self._client()
        client.get(self._page_url(exam), **extra)  # isinmə (sessiya, icazə keşi)
        count, response = self._measure(lambda: client.get(self._page_url(exam), **extra))
        self.assertEqual(response.status_code, 200)
        return count, response

    def test_page_queries_do_not_grow_with_groups_or_students(self):
        small, _ = self._exam_with(2, 3, "Small")
        big, big_users = self._exam_with(17, 12, "Big")
        small_count, _ = self._count(small)
        big_count, response = self._count(big)
        self.assertEqual(response.context["stats"]["eligible"], len(big_users))
        self.assertEqual(len(response.context["assigned_units"]), 17)
        self.assertLessEqual(big_count, small_count + 2, (small_count, big_count))
        self.assertLessEqual(big_count, 42)

    def test_partial_response_is_only_the_live_regions_and_is_cheaper(self):
        exam, users = self._exam_with(4, 5, "Partial")
        full_count, full = self._count(exam)
        part_count, part = self._count(exam, **PARTIAL)
        html = part.content.decode()
        self.assertNotIn("<html", html)
        self.assertNotIn("js-eas-unit-picker", html)  # «əlavə et» kartı yenidən qurulmur (seçicilər yerində qalır)
        for region in ("summary", "filters", "table"):
            self.assertEqual(html.count(f'data-eas-live="{region}"'), 1, region)
        self.assertEqual(part["Cache-Control"], "no-store")
        self.assertIn("X-EAS-Partial", part["Vary"])
        self.assertLess(len(part.content), len(full.content) / 2)
        self.assertLessEqual(part_count, full_count)
        # Eyni süzgəc → tam səhifədəki cədvəllə EYNİ sətirlər.
        self.assertEqual([row.user_id for row in part.context["rows"]], [row.user_id for row in full.context["rows"]])
        self.assertContains(full, 'data-eas-live="table"')
        self.assertContains(full, "js-eas-filter-form")

    def test_partial_respects_filters_and_pagination(self):
        exam, users = self._exam_with(3, 4, "Filters")
        client = self._client()
        group_name = exam.allowed_units.order_by("name").first().name
        response = client.get(self._page_url(exam), {"group": group_name, "status": "finished"}, **PARTIAL)
        rows = response.context["rows"]
        self.assertTrue(rows)
        self.assertTrue(all(row.group_name == group_name and row.status == "finished" for row in rows))
        self.assertContains(response, 'aria-pressed="true"', count=1)
        response = client.get(self._page_url(exam), {"q": "zzzz-yoxdur"}, **PARTIAL)
        self.assertEqual(response.context["filtered_count"], 0)

    def test_read_only_viewer_gets_partial_without_edit_controls(self):
        exam, _ = self._exam_with(1, 2, "ReadOnly")
        with bypass_rls():
            role = self.org.roles.get(name="teacher")
            role.permissions = [perm for perm in role.permissions if perm not in ("exam.edit", "exam.*", "*")]
            role.save(update_fields=["permissions"])
        response = self._client().get(self._page_url(exam), **PARTIAL)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "js-eas-remove-unit")
        self.assertNotContains(response, "js-eas-user-action")

    def test_student_is_denied_partial_too(self):
        exam, _ = self._exam_with(1, 1, "Denied")
        response = _login(self.student, self.org).get(self._page_url(exam), **PARTIAL)
        self.assertEqual(response.status_code, 403)

    def test_detail_page_counter_is_constant(self):
        small, _ = self._exam_with(1, 2, "DSmall")
        big, big_users = self._exam_with(12, 10, "DBig")
        client = self._client()

        def count(exam):
            url = reverse("exams:teacher_exam_detail", kwargs={"slug": exam.slug})
            client.get(url)
            total, response = self._measure(lambda: client.get(url))
            self.assertEqual(response.status_code, 200)
            return total

        self.assertEqual(exam_assignees.assignee_count(big), len(big_users))
        self.assertLessEqual(count(big), count(small) + 2)


class EditBudgetTests(_ScaleFixture):
    """Əlavə / çıxarma sorğuları artıq təyin olunmuş qrupların (və tələbələrin) sayından asılı deyil."""

    def _prepared(self, assigned, students_each, title):
        units, users = self._units(assigned + 2, students_each)
        exam = self._exam(title=title, exam_type_extended="midterm")
        exam.allowed_units.add(*units[:assigned])
        from apps.exams.services.student_pins import provision_exam_student_pins

        provision_exam_student_pins(exam)
        return exam, units, users

    def _post(self, client, exam, **data):
        return client.post(self._update_url(exam), data, **AJAX, **PARTIAL)

    def _add_unit_count(self, exam, units, assigned):
        client = self._client()
        # İsinmə: birinci əlavə proses keşlərini (icazə, bildiriş kataloqu, regex) doldurur.
        self.assertEqual(
            self._post(client, exam, action="add_units", allowed_units=str(units[assigned].pk)).status_code, 200
        )
        count, response = self._measure(
            lambda: self._post(client, exam, action="add_units", allowed_units=str(units[assigned + 1].pk))
        )
        self.assertEqual(response.status_code, 200, response.content[:300])
        return count

    def test_add_group_queries_are_not_proportional_to_assigned_groups(self):
        small, small_units, _ = self._prepared(1, 3, "AddSmall")
        big, big_units, _ = self._prepared(16, 8, "AddBig")
        small_count = self._add_unit_count(small, small_units, 1)
        big_count = self._add_unit_count(big, big_units, 16)
        self.assertEqual(big.allowed_units.count(), 18)
        self.assertLessEqual(big_count, small_count + 2, (small_count, big_count))
        self.assertLessEqual(big_count, 70)

    def test_add_student_queries_are_not_proportional_to_assigned_groups(self):
        small, _, _ = self._prepared(1, 3, "UserSmall")
        big, _, _ = self._prepared(16, 8, "UserBig")
        _, extra = self._units(1, 4)

        def count(exam, first, second):
            client = self._client()
            self.assertEqual(self._post(client, exam, action="add_users", users=[first.pk]).status_code, 200)
            total, response = self._measure(lambda: self._post(client, exam, action="add_users", users=[second.pk]))
            self.assertEqual(response.status_code, 200, response.content[:300])
            return total

        small_count = count(small, extra[0], extra[1])
        big_count = count(big, extra[2], extra[3])
        self.assertLessEqual(big_count, small_count + 2, (small_count, big_count))
        self.assertLessEqual(big_count, 70)

    def test_add_many_students_in_one_request_is_one_bulk_write(self):
        exam, _, _ = self._prepared(2, 2, "Bulk")
        _, extra = self._units(1, 12)
        client = self._client()
        self.assertEqual(self._post(client, exam, action="add_users", users=[extra[0].pk]).status_code, 200)
        one, _ = self._measure(lambda: self._post(client, exam, action="add_users", users=[extra[1].pk]))
        many, response = self._measure(
            lambda: self._post(client, exam, action="add_users", users=[user.pk for user in extra[2:]])
        )
        self.assertEqual(response.status_code, 200, response.content[:300])
        self.assertLessEqual(many, one + 2, (one, many))
        self.assertTrue({user.pk for user in extra} <= _assigned_student_ids(exam))


class PartialEditFlowTests(_ScaleFixture):
    """Fraqment rejimində (JS) əməl: eyni qapılar / audit / PIN, amma flash mesaj YOX — mesaj cavabdadır."""

    def _audit_actions(self, exam):
        with bypass_rls():
            logs = AuditLog.objects.filter(reason=AUDIT_REASON, object_id=str(exam.pk)).order_by("created_at")
            return [log.changes["action"] for log in logs]

    def test_add_group_then_student_then_remove(self):
        units, users = self._units(2, 3)
        exam = self._exam(title="Flow", exam_type_extended="midterm")
        client = self._client()
        url = self._update_url(exam)

        response = client.post(url, {"action": "add_units", "allowed_units": str(units[0].pk)}, **AJAX, **PARTIAL)
        self.assertEqual(response.status_code, 200, response.content[:300])
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertTrue(payload["message"])
        self.assertEqual(payload["warnings"], [])
        self.assertEqual(list(get_messages(response.wsgi_request)), [])  # flash yığılmır
        group_students = {user.pk for user in users[:3]}
        self.assertEqual(_assigned_student_ids(exam), group_students)
        with bypass_rls():
            self.assertEqual(
                set(ExamStudentPin.objects.filter(exam=exam).values_list("student_id", flat=True)), group_students
            )

        outsider = users[4]
        response = client.post(url, {"action": "add_users", "users": [outsider.pk]}, **AJAX, **PARTIAL)
        self.assertEqual(response.status_code, 200, response.content[:300])
        self.assertEqual(_assigned_student_ids(exam), group_students | {outsider.pk})

        # Canlı hissə dərhal yeni vəziyyəti göstərir (JS bunu çağırır).
        part = client.get(self._page_url(exam), **PARTIAL)
        self.assertEqual(part.context["stats"]["eligible"], 4)
        self.assertEqual(part.context["stats"]["individual"], 1)
        self.assertEqual([unit["id"] for unit in part.context["assigned_units"]], [str(units[0].pk)])

        response = client.post(url, {"action": "remove_user", "user": outsider.pk}, **AJAX, **PARTIAL)
        self.assertEqual(response.status_code, 200)
        response = client.post(url, {"action": "remove_unit", "unit": str(units[0].pk)}, **AJAX, **PARTIAL)
        self.assertEqual(response.status_code, 200, response.content[:300])
        self.assertEqual(_assigned_student_ids(exam), set())
        with bypass_rls():
            self.assertFalse(ExamStudentPin.objects.filter(exam=exam).exists())
        self.assertEqual(self._audit_actions(exam), ["add_units", "add_users", "remove_user", "remove_unit"])
        self.assertEqual(client.get(self._page_url(exam), **PARTIAL).context["stats"]["eligible"], 0)

    def test_without_partial_header_flash_message_is_kept(self):
        units, _ = self._units(1, 1)
        exam = self._exam(title="Legacy")
        response = self._client().post(
            self._update_url(exam), {"action": "add_units", "allowed_units": str(units[0].pk)}, **AJAX
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("warnings", response.json())
        self.assertEqual(len(list(get_messages(response.wsgi_request))), 1)

    def test_rejections_are_unchanged_in_partial_mode(self):
        exam = self._exam(title="Reject")
        client = self._client()
        url = self._update_url(exam)
        self.assertEqual(client.post(url, {"action": "add_units"}, **AJAX, **PARTIAL).status_code, 400)
        response = client.post(url, {"action": "add_units", "allowed_units": str(self.group_b.pk)}, **AJAX, **PARTIAL)
        self.assertEqual(response.status_code, 400)  # başqa tenantın qrupu
        response = client.post(url, {"action": "add_users", "users": [self.student_b.pk]}, **AJAX, **PARTIAL)
        self.assertEqual(response.status_code, 400)
        student = _login(self.student, self.org)
        self.assertEqual(
            student.post(url, {"action": "add_users", "users": [self.student.pk]}, **AJAX, **PARTIAL).status_code, 403
        )
        self.assertFalse(exam.allowed_units.exists())
        self.assertFalse(exam.allowed_users.exists())


class SubgroupPatternCacheTests(SimpleTestCase):
    """Kök səbəb: ad şablonu hər cüt üçün yenidən kompilyasiya olunurdu — keş nəticəni DƏYİŞMİR."""

    CASES = [
        ("234 K az", "234 K-1", True),
        ("534 TB az", "534 TB 1", True),
        ("233KE", "233 KE-1", True),
        ("234 K ing", "234 K-1", False),
        ("234 K ing", "234 K ing-1", True),
        ("235 İT az", "235 İT-1 az", True),
        ("036", "0361", False),
        ("234 K az", "234 K az", False),
        ("234 K az", "634 ing", False),
    ]

    def test_results_match_documented_rules(self):
        for combined, candidate, expected in self.CASES * 2:  # ikinci keçid keşdən gəlir
            with self.subTest(combined=combined, candidate=candidate):
                self.assertIs(subgroup_rollup.is_subgroup_of(combined, candidate), expected)

    def test_pattern_is_compiled_once_per_base(self):
        subgroup_rollup.subgroup_pattern.cache_clear()
        first = subgroup_rollup.subgroup_pattern("234 k")
        self.assertIs(subgroup_rollup.subgroup_pattern("234 k"), first)
        info = subgroup_rollup.subgroup_pattern.cache_info()
        self.assertEqual((info.misses, info.hits), (1, 1))

    def test_group_family_over_many_siblings_does_not_recompile(self):
        class _Unit:
            def __init__(self, pk, name):
                self.pk, self.name, self.parent_id, self.settings = pk, name, 1, {}

        siblings = [_Unit(index, f"{100 + index} Q az") for index in range(700)]
        groups = siblings[:17]
        original = subgroup_rollup._sibling_groups
        subgroup_rollup._sibling_groups = lambda organization, parent_ids: siblings
        try:
            subgroup_rollup.group_family(None, groups)  # keşi doldurur
            real_compile = re.compile
            calls = []
            re.compile = lambda *args, **kwargs: calls.append(args) or real_compile(*args, **kwargs)
            try:
                family = subgroup_rollup.group_family(None, groups)
            finally:
                re.compile = real_compile
        finally:
            subgroup_rollup._sibling_groups = original
        self.assertEqual(calls, [])
        self.assertEqual(set(family), {group.pk for group in groups})
        self.assertTrue(all(value == ([], []) for value in family.values()))


def _reference_tolerant_match(query, *texts, compact=False) -> bool:
    """2026-11-11-dən ƏVVƏLKİ ``tolerant_match`` (şablon hər çağırışda qurulurdu) — paritet etalonu."""
    from core.search_text import _glued, code_regex, fold_regex, tokens_of

    tokens = tokens_of(query)
    if not tokens:
        return True
    haystack = [str(text).replace("\u0307", "") for text in texts if text not in (None, "")]

    def _hit(pattern):
        rx = re.compile(pattern, re.IGNORECASE)
        return any(rx.search(text) for text in haystack)

    if all(_hit(code_regex(token) if compact else fold_regex(token)) for token in tokens):
        return True
    glued = _glued(tokens) if compact else None
    return bool(glued) and _hit(glued)


class TolerantMatcherTests(SimpleTestCase):
    def test_matcher_equals_previous_tolerant_match(self):
        texts = [
            ("Əliyev Əli Elçin", "ali.aliyev", "N-1024", "ali@test.az"),
            ("İsmayılova Şəbnəm", "shebnem.i", "", None),
            ("Xəlilov Çingiz", "cingiz", "234 K ing", ""),
            ("", "", "", ""),
        ]
        queries = ["", "ali", "aliyev eli", "ismayil", "shebnem", "khalilov", "234king", "234 k", "yox", "a b c d e"]
        hits = 0
        for compact in (False, True):
            for query in queries:
                matcher = tolerant_matcher(query, compact=compact)
                for row in texts:
                    with self.subTest(query=query, compact=compact, row=row[0]):
                        expected = _reference_tolerant_match(query, *row, compact=compact)
                        self.assertEqual(matcher(*row), expected)
                        self.assertEqual(tolerant_match(query, *row, compact=compact), expected)
                        hits += expected
        self.assertGreater(hits, 20)  # etalon həm uyğun, həm uyğunsuz halları əhatə edir
        self.assertTrue(tolerant_matcher("aliyev")("Əliyev"))
        self.assertFalse(tolerant_matcher("zzz")("Əliyev"))


class ClientContractTests(SimpleTestCase):
    """JS / şablon müqaviləsi: tam yenidən yükləmə yoxdur, köhnə sorğular ləğv olunur."""

    def _read(self, relative):
        return (REPO / relative).read_text(encoding="utf-8")

    def test_assignees_js_refreshes_regions_instead_of_reloading(self):
        js = self._read("apps/exams/static/exams/js/teacher_exam_assignees.js")
        self.assertNotIn("location.reload", js)
        self.assertIn('"X-EAS-Partial"', js)
        self.assertIn("AbortController", js)
        self.assertIn("liveController.abort()", js)
        self.assertIn('EMSDelegate.on("submit", ".js-eas-filter-form"', js)
        self.assertIn('"[data-eas-live] a[href]"', js)

    def test_shared_picker_aborts_stale_search_requests(self):
        js = self._read("static/js/searchable_select.js")
        self.assertIn("controller.abort()", js)
        self.assertIn("controller ? controller.signal : undefined", js)

    def test_page_template_wraps_live_regions(self):
        page = self._read("apps/exams/templates/exams/teacher/teacher_exam_assignees.html")
        live = self._read("apps/exams/templates/exams/teacher/partials/assignees/_live.html")
        for region in ("summary", "filters", "table"):
            self.assertIn(f'data-eas-live="{region}"', page)
            self.assertIn(f'data-eas-live="{region}"', live)
        self.assertNotIn("_add.html", live)
