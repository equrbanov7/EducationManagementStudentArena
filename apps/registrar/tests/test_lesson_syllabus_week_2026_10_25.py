"""Sahib 2026-10-25: jurnalda keçilmiş dərsin MÖVZUSU sillabusun həftəlik plan SƏTRİNƏ bağlanır.

Nəyi qoruyur
------------
* ``Lesson.syllabus_week`` — təsdiqlənmiş planın ``week.rows`` sırası ilə 1-dən sətir nömrəsi (boş mövzulu
  sətirlər də sayılır); plandan seçilmiş / başlığı DƏQİQ (boşluq, registr normallaşdırılmış) eyni yazılmış
  mövzu yaradılanda və mövzu dəyişəndə bağlanır, sərbəst mətn bağlanmır;
* mövzu dəyişməyən redaktə köçürülmüş (mövzusuz) dərsin bağını SİLMİR;
* ``display_topic``: yazılmış mövzu, yoxdursa bağlı sətrin mövzusu, heç biri yoxdursa boş (uydurma yox) —
  jurnal sütunu, «Keçilmiş dərslər», modal «keçirilib» işarəsi;
* hər plan sətri üçün «keçilib» (tarixlərlə) / «planlaşdırılıb» / «keçilməyib» — «Sillabusa bax» panelinin
  JSON-u (müəllim, tələbə, yalnız-oxu ``journal.view``);
* modal: plan seçimi + sərbəst mətn (``lesson_topic_custom`` üstündür);
* ``link_lesson_syllabus_weeks`` əmri: defolt dry-run, ``--apply``, idempotent, stdout-da yalnız saylar.
"""

from __future__ import annotations

import datetime
import io

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit, Role
from apps.registrar import gradebook, journal_topics
from apps.registrar import lessons_log as lessons_log_service
from apps.registrar import services as registrar_services
from apps.registrar.models import Enrollment, Lesson, LessonKind, Subject
from apps.syllabus.models import Syllabus, SyllabusSection, SyllabusVersion
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType, RoleScopeType
from core.rls import bypass_rls

User = get_user_model()

#: 5 sətir: 3-cü boşdur (saat var, mövzu yox) — nömrələmədə SAYILIR; 2-ci və 5-ci eyni başlıqdır.
PLAN = [
    {"topic": "Giriş və məqsədlər", "lecture": 2, "seminar": 0, "lab": 0},
    {"topic": "Massivlər", "lecture": 2, "seminar": 2, "lab": 0},
    {"topic": "", "lecture": 2, "seminar": 0, "lab": 0},
    {"topic": "Ağaclar  və   qraflar", "lecture": 2, "seminar": 0, "lab": 0},
    {"topic": "Massivlər", "lecture": 0, "seminar": 2, "lab": 0},
]


class LessonSyllabusWeekTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.today = timezone.localdate()
        with bypass_rls():
            cls.owner = User.objects.create_user("lsw_owner", "lsw_owner@x.test", "pw")
            cls.org = Organization.objects.create(
                name="LSW Univ",
                slug="lsw-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, name="LSW-G1", slug="lsw-g1", unit_type=OrgUnitType.GROUP
            )
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Cari",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2026/2027",
                start_date=cls.today - datetime.timedelta(days=60),
                end_date=cls.today + datetime.timedelta(days=60),
                is_current=True,
            )
            cls.teacher = User.objects.create_user("lsw_teacher", "lsw_teacher@x.test", "pw")
            cls.student = User.objects.create_user("lsw_student", "lsw_student@x.test", "pw")
            cls.viewer = User.objects.create_user("lsw_viewer", "lsw_viewer@x.test", "pw")
            cls.stranger = User.objects.create_user("lsw_stranger", "lsw_stranger@x.test", "pw")
            cls._member(cls.teacher, "teacher", ["grade.input"])
            cls._member(cls.student, "student", [])
            cls._member(cls.viewer, "dean_viewer", ["journal.view"], level=70)
            cls._member(cls.stranger, "student", [], suffix="-2")
            cls.offering = cls._offering("LSW101", "Alqoritmlər")
            cls.other = cls._offering("LSW102", "Şəbəkələr")
            Enrollment.objects.create(organization=cls.org, student=cls.student, offering=cls.offering)
            cls.version = cls._approved_plan(cls.offering, PLAN)
            cls._approved_plan(cls.other, [{"topic": "TCP/IP", "lecture": 2, "seminar": 0, "lab": 0}])

    # ── qurucular ────────────────────────────────────────────────────────────
    @classmethod
    def _member(cls, user, role_name, permissions, *, level=50, suffix=""):
        role, _created = Role.objects.get_or_create(
            organization=cls.org,
            name=f"{role_name}{suffix}",
            defaults={"display_name": role_name.title(), "level": level, "permissions": list(permissions)},
        )
        Role.objects.filter(pk=role.pk).update(
            is_active=True, permissions=list(permissions), level=level, scope_type=RoleScopeType.ORGANIZATION
        )
        membership, _ = Membership.objects.get_or_create(
            organization=cls.org, user=user, role=role, defaults={"is_active": True}
        )
        Membership.objects.filter(pk=membership.pk).update(is_active=True)

    @classmethod
    def _offering(cls, code, name):
        subject = Subject.objects.create(organization=cls.org, code=code, name=name)
        item = registrar_services.get_or_create_offering(
            organization=cls.org, subject=subject, period=cls.period, group=cls.group
        )
        item.instructor = cls.teacher
        item.lesson_hours = 60
        item.save(update_fields=["instructor", "lesson_hours"])
        return item

    @classmethod
    def _approved_plan(cls, offering, rows):
        syllabus = Syllabus.objects.create(
            organization=cls.org,
            subject=offering.subject,
            period=offering.period,
            offering=offering,
            author=cls.teacher,
        )
        now = timezone.now()
        version = SyllabusVersion.objects.create(
            organization=cls.org,
            syllabus=syllabus,
            major=1,
            status="approved",
            locked_at=now,
            approved_at=now,
            approved_by=cls.teacher,
        )
        SyllabusSection.objects.create(
            organization=cls.org, version=version, section_id="week", data={"rows": [dict(row) for row in rows]}
        )
        syllabus.approved_version = version
        syllabus.current_version = version
        syllabus.save(update_fields=["approved_version", "current_version", "updated_at"])
        return version

    def _fresh(self, offering=None):
        from apps.registrar.models import CourseOffering

        return CourseOffering.objects.select_related("organization", "period").get(pk=(offering or self.offering).pk)

    def _lesson(self, *, days_ago=7, topic="", week=None, offering=None, kind=LessonKind.LECTURE, created_by=None):
        return Lesson.objects.create(
            organization=self.org,
            offering=offering or self.offering,
            date=self.today - datetime.timedelta(days=days_ago),
            kind=kind,
            topic=topic,
            syllabus_week=week,
            created_by=created_by,
        )

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    # ── plan sətirləri və bağ ────────────────────────────────────────────────
    def test_week_rows_are_numbered_in_plan_order_including_blank_rows(self):
        rows = journal_topics.syllabus_week_rows(self._fresh())
        self.assertEqual([row["week"] for row in rows], [1, 2, 3, 4, 5])
        self.assertEqual(rows[2]["title"], "")
        self.assertEqual(rows[1]["kinds"], ("lecture", "seminar"))
        topics = journal_topics.syllabus_topic_rows(self._fresh())
        self.assertEqual(
            [(row["title"], row["week"]) for row in topics][:3],
            [
                ("Giriş və məqsədlər", 1),
                ("Massivlər", 2),
                ("Ağaclar  və   qraflar", 4),
            ],
        )

    def test_resolution_is_exact_after_whitespace_and_case_normalisation(self):
        offering = self._fresh()
        self.assertEqual(journal_topics.resolve_syllabus_week(offering, "  giriş   VƏ məqsədlər "), 1)
        self.assertEqual(journal_topics.resolve_syllabus_week(offering, "ağaclar və qraflar"), 4)
        self.assertIsNone(journal_topics.resolve_syllabus_week(offering, "Giriş"))  # qismən uyğunluq YOX
        self.assertIsNone(journal_topics.resolve_syllabus_week(offering, ""))
        # Təkrar başlıq: cari sətir uyğundursa saxlanılır, yoxdursa İLK sətir.
        self.assertEqual(journal_topics.resolve_syllabus_week(offering, "Massivlər", current=5), 5)
        self.assertEqual(journal_topics.resolve_syllabus_week(offering, "Massivlər", current=1), 2)

    def test_create_lesson_links_a_plan_topic_but_not_free_text(self):
        with bypass_rls():
            planned = gradebook.create_lesson(
                offering=self._fresh(), date=self.today, kind=LessonKind.LECTURE, topic="Massivlər", allow_past=True
            )
            free = gradebook.create_lesson(
                offering=self._fresh(),
                date=self.today - datetime.timedelta(days=1),
                kind=LessonKind.LECTURE,
                topic="Əlavə məşğələ",
                allow_past=True,
            )
        self.assertEqual(planned.syllabus_week, 2)
        self.assertIsNone(free.syllabus_week)

    def test_update_relinks_on_topic_change_and_keeps_a_legacy_link_otherwise(self):
        legacy = self._lesson(topic="", week=4)
        with bypass_rls():
            gradebook.update_lesson(lesson=legacy, topic="", hours=2, allow_locked=True, allow_past=True)
        legacy.refresh_from_db()
        self.assertEqual(legacy.syllabus_week, 4, "mövzu dəyişməyib — köçürülmüş bağ qalır")

        with bypass_rls():
            gradebook.update_lesson(lesson=legacy, topic="Ağaclar və qraflar", allow_locked=True, allow_past=True)
        legacy.refresh_from_db()
        self.assertEqual((legacy.topic, legacy.syllabus_week), ("Ağaclar və qraflar", 4))

        with bypass_rls():
            gradebook.update_lesson(lesson=legacy, topic="Sərbəst mövzu", allow_locked=True, allow_past=True)
        legacy.refresh_from_db()
        self.assertIsNone(legacy.syllabus_week)

    # ── göstəriş ─────────────────────────────────────────────────────────────
    def test_display_topic_falls_back_to_the_linked_row_and_never_invents(self):
        typed = self._lesson(topic="Öz mövzum", week=1, days_ago=9)
        linked = self._lesson(topic="", week=4, days_ago=8)
        bare = self._lesson(topic="", days_ago=7)
        stale = self._lesson(topic="", week=99, days_ago=6)  # plan qısalıb — sətir yoxdur
        lessons = list(Lesson.objects.filter(pk__in=[typed.pk, linked.pk, bare.pk, stale.pk]).order_by("date"))
        journal_topics.attach_syllabus_topics(lessons, offering=self._fresh())
        self.assertEqual([lesson.display_topic for lesson in lessons], ["Öz mövzum", "Ağaclar  və   qraflar", "", ""])

    def test_bulk_attach_across_offerings_uses_a_fixed_number_of_queries(self):
        self._lesson(topic="", week=2)
        self._lesson(topic="", week=1, offering=self.other)
        lessons = list(Lesson.objects.select_related("offering").filter(organization=self.org))
        with CaptureQueriesContext(connection) as ctx:
            journal_topics.attach_syllabus_topics(lessons)
        self.assertLessEqual(len(ctx.captured_queries), 3)
        self.assertEqual(sorted(lesson.display_topic for lesson in lessons), ["Massivlər", "TCP/IP"])

    def test_attach_without_linked_lessons_runs_no_query(self):
        lessons = [self._lesson(topic="Massivlər"), self._lesson(topic="")]
        with CaptureQueriesContext(connection) as ctx:
            journal_topics.attach_syllabus_topics(lessons)
        self.assertEqual(len(ctx.captured_queries), 0)

    def test_lessons_log_rows_show_the_syllabus_topic(self):
        self._lesson(topic="", week=1)
        self._lesson(topic="", days_ago=3)
        rows = lessons_log_service.build_rows(Lesson.objects.filter(offering=self.offering))
        by_topic = {row["topic"]: row["has_topic"] for row in rows}
        self.assertEqual(by_topic, {"Giriş və məqsədlər": True, "": False})

    def test_topic_meta_marks_a_linked_untitled_lesson_as_covered(self):
        offering = self._fresh()
        lesson = self._lesson(topic="", week=2)
        journal_topics.attach_syllabus_topics([lesson], offering=offering)
        meta = {row["title"]: row for row in journal_topics.lesson_topic_meta(offering, [lesson])}
        self.assertTrue(meta["Massivlər"]["covered"])
        self.assertEqual(meta["Massivlər"]["week"], 2)
        self.assertFalse(meta["Giriş və məqsədlər"]["covered"])

    # ── plan sətrinin statusu ────────────────────────────────────────────────
    def test_week_progress_marks_each_row_with_its_dates(self):
        first = self._lesson(topic="", week=1, days_ago=10)
        second = self._lesson(topic="giriş və MƏQSƏDLƏR", days_ago=9, kind=LessonKind.SEMINAR)  # bağsız, başlıqla
        self._lesson(topic="", week=5, days_ago=-3)  # gələcək
        self._lesson(topic="Sərbəst", days_ago=2)  # heç bir sətrə aid deyil
        progress = journal_topics.week_progress(
            self._fresh(), list(Lesson.objects.filter(offering=self.offering)), today=self.today
        )
        by_week = {row["week"]: row for row in progress}
        self.assertNotIn(3, by_week, "mövzusuz, bağsız sətir göstərilmir")
        self.assertTrue(by_week[1]["covered"])
        self.assertEqual(by_week[1]["dates"], [first.date, second.date])
        self.assertFalse(by_week[2]["covered"] or by_week[2]["planned"])
        self.assertTrue(by_week[5]["planned"] and not by_week[5]["covered"])

    def test_syllabus_panel_json_reports_progress_to_teacher_student_and_viewer(self):
        self._lesson(topic="", week=4, days_ago=5)
        url = reverse("registrar:offering_syllabus_json", args=[self.offering.id])
        for user in (self.teacher, self.student, self.viewer):
            response = self._client(user).get(url)
            self.assertEqual(response.status_code, 200, user.username)
            progress = response.json()["week_progress"]
            self.assertEqual((progress["covered"], progress["total"]), (1, 4), user.username)
            row = next(item for item in progress["rows"] if item["week"] == 4)
            self.assertTrue(row["covered"])
            self.assertEqual(row["dates"], [(self.today - datetime.timedelta(days=5)).strftime("%d.%m.%Y")])
        self.assertEqual(self._client(self.stranger).get(url).status_code, 404)

    # ── modal: plan seçimi + sərbəst mətn ────────────────────────────────────
    def _post_lesson(self, **fields):
        data = {
            "action": "add_lesson",
            "lesson_date": self.today.isoformat(),
            "lesson_kind": LessonKind.LECTURE,
            "lesson_hours": "2",
            "lesson_time": "08:30|10:00",
        }
        data.update(fields)
        return self._client(self.teacher).post(reverse("registrar:journal_detail", args=[self.offering.id]), data)

    def test_modal_plan_choice_links_the_row(self):
        self._post_lesson(lesson_topic="Ağaclar  və   qraflar", lesson_topic_custom="")
        lesson = Lesson.objects.get(offering=self.offering)
        self.assertEqual((lesson.topic, lesson.syllabus_week), ("Ağaclar  və   qraflar", 4))

    def test_modal_free_text_wins_over_the_plan_choice(self):
        self._post_lesson(lesson_topic="Massivlər", lesson_topic_custom="Laboratoriya təhlükəsizliyi")
        lesson = Lesson.objects.get(offering=self.offering)
        self.assertEqual((lesson.topic, lesson.syllabus_week), ("Laboratoriya təhlükəsizliyi", None))

    def test_journal_modal_renders_the_free_text_field_and_row_numbers(self):
        response = self._client(self.teacher).get(reverse("registrar:journal_detail", args=[self.offering.id]))
        self.assertContains(response, 'name="lesson_topic_custom"')
        self.assertContains(response, 'data-week="4"')
        self.assertContains(response, "registrar/js/journal_lesson_topic.js")

    # ── backfill əmri ────────────────────────────────────────────────────────
    def _run(self, *args):
        out = io.StringIO()
        with bypass_rls():
            call_command("link_lesson_syllabus_weeks", "--org", self.org.slug, *args, stdout=out)
        return out.getvalue()

    def test_backfill_is_dry_run_by_default_then_applies_idempotently(self):
        exact = self._lesson(topic=" massivlər ")
        free = self._lesson(topic="Massivlər və siyahılar")
        kept = self._lesson(topic="Giriş və məqsədlər", week=3)  # artıq bağlı — toxunulmur
        Lesson.objects.filter(pk=exact.pk).update(syllabus_week=None)

        dry = self._run()
        self.assertIn("syllabus_week_link: mode=dry_run", dry)
        self.assertIn("lessons_matched=1", dry)
        self.assertIn("lessons_unmatched=1", dry)
        self.assertIn("written=0", dry)
        exact.refresh_from_db()
        self.assertIsNone(exact.syllabus_week)

        applied = self._run("--apply")
        self.assertIn("written=1", applied)
        for line in applied.strip().splitlines():
            self.assertRegex(line, r"^syllabus_week_link: [a-z_]+=[0-9a-z_]+( [a-z_]+=[0-9a-z_]+)*$")
        exact.refresh_from_db()
        free.refresh_from_db()
        kept.refresh_from_db()
        self.assertEqual(exact.syllabus_week, 2)
        self.assertIsNone(free.syllabus_week)
        self.assertEqual(kept.syllabus_week, 3)

        again = self._run("--apply")
        self.assertIn("written=0", again)
        self.assertIn("lessons_candidate=1", again)  # yalnız sərbəst mətnli dərs qalıb
