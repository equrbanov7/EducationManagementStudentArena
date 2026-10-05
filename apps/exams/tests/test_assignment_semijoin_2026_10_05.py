"""Tələbə imtahan təyinatı semi-join ilə — nəticə eyni, DISTINCT/JOIN partlayışı yox (tutum testi 2026-10-05)."""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from apps.accounts.models import ProfileRole
from apps.accounts.queries.assignments import get_assigned_exams_for_user
from apps.exams.models import Exam, StudentGroup
from apps.exams.services import randomizer
from apps.exams.tests.test_exam_center_policy import _assign_user_to_org
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class AssignedExamsSemiJoinTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("sj_owner", email="sj-owner@example.com")
        self.org = Organization.objects.create(
            name="Semi-join", owner=self.owner, org_type=OrganizationType.SCHOOL, status="active", is_active=True
        )
        _assign_user_to_org(self.owner, self.org, ProfileRole.TEACHER, "teacher")
        self.student = User.objects.create_user("sj_student", email="sj-student@example.com")
        self.other = User.objects.create_user("sj_other", email="sj-other@example.com")
        self.group = StudentGroup.objects.create(organization=self.org, teacher=self.owner, name="SJ-1")
        self.group.students.add(self.student, self.other)

        def exam(title, **kw):
            return Exam.objects.create(title=title, author=self.owner, organization=self.org, is_active=True, **kw)

        self.direct = exam("direct")
        self.direct.allowed_users.add(self.student)
        self.by_group = exam("group")
        self.by_group.allowed_groups.add(self.group)
        self.both = exam("both")  # birbaşa VƏ qrupla — iki dəfə sayılmamalıdır
        self.both.allowed_users.add(self.student)
        self.both.allowed_groups.add(self.group)
        self.excluded = exam("excluded")
        self.excluded.allowed_groups.add(self.group)
        self.excluded.excluded_users.add(self.student)
        self.foreign = exam("foreign")
        self.foreign.allowed_users.add(self.other)

    def test_same_exams_once_each_without_distinct(self):
        with CaptureQueriesContext(connection) as ctx:
            ids = list(get_assigned_exams_for_user(self.student).values_list("id", flat=True))
        self.assertCountEqual(ids, [self.direct.id, self.by_group.id, self.both.id])
        self.assertEqual(len(ids), len(set(ids)))
        sql = " ".join(q["sql"] for q in ctx.captured_queries).upper()
        self.assertNotIn("DISTINCT", sql)


@override_settings(
    EXAM_RANDOMIZER_USAGE_CACHE_SECONDS=30,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class UsageCountSingleFlightTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_concurrent_miss_reuses_stale_value_instead_of_rebuilding(self):
        calls = []

        def builder():
            calls.append(1)
            return {1: len(calls)}

        self.assertEqual(randomizer._cached_usage_counts("k", builder), {1: 1})
        cache.delete("k")  # TTL bitdi; başqa sorğu yenidənqurmanı artıq götürüb
        cache.add("k:lock", 1, 30)
        self.assertEqual(randomizer._cached_usage_counts("k", builder), {1: 1})
        self.assertEqual(len(calls), 1)
        cache.delete("k:lock")
        self.assertEqual(randomizer._cached_usage_counts("k", builder), {1: 2})
