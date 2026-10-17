"""PERF-1 (FIX-F, 2026-10-17) — jurnal girişinin müəllim yoxlaması (F-15) və cədvəl redaktorunun müəllim siyahısı (F-16).

* F-15 — `can_edit_journal` / `is_direct_editor` müəllimin `grade.input` səlahiyyətini middleware-in request
  üzvlük snapshot-undan oxuyur (jurnal açılışında iki ayrıca `Membership` SELECT-i idi). Snapshot yararsızdırsa
  (bağlanmayıb / başqa org) canlı sorğu qalır; deaktiv rol hər iki yolda «yox» deməkdir.
* F-16 — `schedule_editor.teacher_choices` model nümunəsi yaratmır, təşkilat üzrə keşlənir; üzvlük yazısı keşi
  silir. Siyahı jurnal sahibi ola biləcək HƏR müəllimdir (aktiv `grade.input`, yazı yoxlaması ilə eyni dəst) —
  əvvəlki 400-lük səssiz kəsim yoxdur, soyad → ad sırası.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.organizations.models import Membership
from apps.organizations.request_memberships import bind_request_memberships, membership_epoch
from apps.registrar import journal_access, schedule_editor
from apps.registrar.integrity import eligible_instructor_user_ids
from apps.registrar.tests.test_student_sections_redesign import _build_tenant, _client_for
from core.rls import bypass_rls

#: `integrity._active_membership_roles` — `user__is_active` süzgəci yalnız bu sorğuda var (middleware-də yox).
_GRADE_INPUT_CHECK = 'INNER JOIN "auth_user" ON ("organizations_membership"."user_id" = "auth_user"."id")'


@override_settings(UNIVERSITY_MODE=True)
class JournalInstructorSnapshotTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = _build_tenant(slug="pf1f15", subject_count=1)
        cls.offering = cls.tenant["enrollments"][0].offering

    def _memberships(self):
        teacher = self.tenant["teacher"]
        with bypass_rls():
            rows = list(
                Membership.objects.filter(user=teacher, organization=self.tenant["org"], is_active=True)
                .select_related("organization", "role", "scope_unit")
                .order_by("-is_primary", "-role__level")
            )
        return teacher, rows

    def test_journal_open_reads_no_extra_instructor_membership(self):
        client = _client_for(self.tenant["org"], self.tenant["teacher"])
        url = reverse("registrar:journal_detail", args=[self.offering.pk])
        client.get(url)  # isinmə
        with CaptureQueriesContext(connection) as ctx:
            response = client.get(url)
        self.assertEqual(response.status_code, 200)
        checks = [q["sql"] for q in ctx.captured_queries if _GRADE_INPUT_CHECK in q["sql"]]
        self.assertEqual(checks, [], "müəllim yoxlaması request snapshot-undan gəlməlidir")

    def test_snapshot_answer_matches_live_query_without_queries(self):
        teacher, rows = self._memberships()
        bind_request_memberships(teacher, self.tenant["org"], rows, epoch=membership_epoch())
        offering = self.offering
        with CaptureQueriesContext(connection) as ctx:
            snapshot_verdict = journal_access._is_live_assigned_instructor(teacher, offering)
        self.assertTrue(snapshot_verdict)
        self.assertEqual(len(ctx.captured_queries), 0)

        teacher.__dict__.pop("_org_request_membership_snapshot", None)
        with bypass_rls(), CaptureQueriesContext(connection) as ctx:
            live_verdict = journal_access._is_live_assigned_instructor(teacher, offering)
        self.assertEqual(live_verdict, snapshot_verdict)
        self.assertEqual(len(ctx.captured_queries), 1)

    def test_inactive_role_is_rejected_on_both_paths(self):
        teacher, rows = self._memberships()
        for row in rows:
            row.role.is_active = False
        bind_request_memberships(teacher, self.tenant["org"], rows, epoch=membership_epoch())
        self.assertFalse(journal_access._is_live_assigned_instructor(teacher, self.offering))

    def test_stale_snapshot_falls_back_to_live_query(self):
        teacher, rows = self._memberships()
        bind_request_memberships(teacher, self.tenant["org"], rows, epoch=membership_epoch() - 1)
        with bypass_rls(), CaptureQueriesContext(connection) as ctx:
            self.assertTrue(journal_access._is_live_assigned_instructor(teacher, self.offering))
        self.assertEqual(len([q for q in ctx.captured_queries if _GRADE_INPUT_CHECK in q["sql"]]), 1)


LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "pf1-f16"}}


@override_settings(CACHES=LOCMEM)
class ScheduleTeacherChoicesTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = _build_tenant(slug="pf1f16", subject_count=1)
        cls.org = cls.tenant["org"]

    def setUp(self):
        cache.clear()

    def _add_teacher(self, username, first, last):
        user = get_user_model().objects.create_user(username, f"{username}@x.test", "pw")
        user.first_name, user.last_name = first, last
        user.save(update_fields=["first_name", "last_name"])
        with bypass_rls():
            Membership.objects.create(
                user=user, organization=self.org, role=self.org.roles.get(name="teacher"), is_active=True
            )
        return user

    def test_list_is_exactly_the_grade_input_set_sorted_by_surname(self):
        self._add_teacher("pf1f16_a", "Zərifə", "Ağayeva")
        self._add_teacher("pf1f16_b", "", "")  # adsız — istifadəçi adı göstərilir
        with bypass_rls():
            choices = schedule_editor.teacher_choices(self.org)
            eligible = eligible_instructor_user_ids(organization=self.org)
        self.assertEqual({row["id"] for row in choices}, {str(pk) for pk in eligible})
        self.assertNotIn(str(self.tenant["student"].pk), {row["id"] for row in choices})  # tələbə rolu
        self.assertIn({"id": str(get_user_model().objects.get(username="pf1f16_b").pk), "name": "pf1f16_b"}, choices)
        self.assertIn("Zərifə Ağayeva", [row["name"] for row in choices])

    def test_no_silent_cap_450_teachers_all_present(self):
        # 2026-10-17: əvvəl siyahı ad üzrə 400-də kəsilirdi — əlifbanın sonundakılar redaktorda yox idi.
        User = get_user_model()
        role = self.org.roles.get(name="teacher")
        users = User.objects.bulk_create(
            [
                User(username=f"pf1f16_bulk_{i:03d}", first_name=f"Ad{i:03d}", last_name=f"Soyad{i:03d}")
                for i in range(450)
            ]
        )
        with bypass_rls():
            Membership.objects.bulk_create(
                [Membership(user=user, organization=self.org, role=role, is_active=True) for user in users]
            )
            cache.clear()  # bulk_create siqnal göndərmir
            with CaptureQueriesContext(connection) as ctx:
                choices = schedule_editor.teacher_choices(self.org)
        ids = {row["id"] for row in choices}
        self.assertTrue({str(user.pk) for user in users} <= ids)
        self.assertGreaterEqual(len(choices), 451)
        self.assertEqual(len(ctx.captured_queries), 2)  # rollar + istifadəçilər (sətir sayından asılı deyil)
        bulk = [row["name"] for row in choices if row["name"].startswith("Ad")]
        self.assertEqual(bulk, [f"Ad{i:03d} Soyad{i:03d}" for i in range(450)])  # soyad → ad sırası

    def test_cached_per_org_and_constant_in_teacher_count(self):
        with bypass_rls(), CaptureQueriesContext(connection) as cold:
            first = schedule_editor.teacher_choices(self.org)
        with CaptureQueriesContext(connection) as warm:
            again = schedule_editor.teacher_choices(self.org)
        self.assertEqual(first, again)
        self.assertEqual(len(cold.captured_queries), 2)
        self.assertEqual(len(warm.captured_queries), 0)

        # Üzvlük yazısı keşi COMMIT-dən sonra silir (on_commit) — TestCase tranzaksiyasında callback-lar icra olunur.
        with self.captureOnCommitCallbacks(execute=True):
            for index in range(5):
                self._add_teacher(f"pf1f16_more_{index}", f"Ad{index}", "Soyad")
        with bypass_rls(), CaptureQueriesContext(connection) as grown:
            more = schedule_editor.teacher_choices(self.org)
        self.assertEqual(len(grown.captured_queries), 2)
        self.assertEqual(len(more), len(first) + 5)


class AllowedSubjectsNoCapTest(TestCase):
    """2026-10-17: `allowed_subjects` ehtiyat yolları əvvəl kodla sıralanıb 400-də səssizcə kəsilirdi."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = _build_tenant(slug="pf1subj", subject_count=1)
        cls.org = cls.tenant["org"]
        cls.period = cls.tenant["period"]

    def _bulk_subjects(self, prefix, count):
        from apps.registrar.models import Subject

        with bypass_rls():
            return Subject.objects.bulk_create(
                [
                    Subject(organization=self.org, code=f"{prefix}{i:03d}", name=f"{prefix} fənn {i}", ects=5)
                    for i in range(count)
                ]
            )

    def _choices(self, period):
        with bypass_rls(), CaptureQueriesContext(connection) as ctx:
            rows = schedule_editor.allowed_subjects(organization=self.org, group=None, period=period)
        return rows, len(ctx.captured_queries)

    def test_period_subjects_fallback_is_not_capped(self):
        from apps.registrar.models import CourseOffering

        subjects = self._bulk_subjects("ZPS", 450)
        with bypass_rls():
            CourseOffering.objects.bulk_create(
                [CourseOffering(organization=self.org, subject=subject, period=self.period) for subject in subjects]
            )
        rows, queries = self._choices(self.period)
        ids = {row["id"] for row in rows}
        self.assertTrue({str(subject.pk) for subject in subjects} <= ids)  # «Z…» kodları sıranın sonundadır
        self.assertEqual([row["code"] for row in rows], sorted(row["code"] for row in rows))
        self.assertEqual(queries, 2)

    def test_catalog_fallback_is_not_capped(self):
        from apps.organizations.models import AcademicPeriod
        from core.constants import AcademicPeriodType

        subjects = self._bulk_subjects("ZKT", 450)
        with bypass_rls():
            empty = AcademicPeriod.objects.create(
                organization=self.org,
                name="Boş dövr",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2030/2031",
                start_date="2030-09-01",
                end_date="2031-01-31",
            )
        rows, _queries = self._choices(empty)  # dövrdə açılış yoxdur → bütün kataloq
        self.assertTrue({str(subject.pk) for subject in subjects} <= {row["id"] for row in rows})
        self.assertGreaterEqual(len(rows), 451)
