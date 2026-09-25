"""«Keçilmiş dərslər» — «Fakültə» və «Kafedra» filtrləri (sahib, 2026-09-25).

Fakültə = qrupun struktur əcdadı; Kafedra = müəllimin kafedra üzvlüyü VƏ YA fənnin aparıcı
kafedrası (``Subject.chair_unit``); fakültə seçimi kafedra siyahısını daraldır; siyahılar
aktorun əhatəsinə görədir; KPI, siyahı, CSV və «qeydə alınmayıb» sayğacı eyni filtrdən keçir."""

import datetime as dt
import uuid

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.organizations.models import OrgUnit
from apps.registrar import lessons_log as service
from apps.registrar.models import CourseOffering, Lesson, LessonKind, ScheduleSlot, Subject
from apps.syllabus.tests.factories import activate_member, make_academic_stack, make_org
from core.constants import OrgUnitType, RoleScopeType
from core.rls import bypass_rls

User = get_user_model()

PASSWORD = "StrongPass123!"
TEACHER_PERMS = ["course.view", "grade.input", "syllabus.edit"]
SUPERVISOR_PERMS = ["course.view", "journal.roster", "unit.view"]
SECTION = "lessons-log"
WINDOW = {"ll_range": "custom", "ll_from": "2025-09-01", "ll_to": "2026-01-31"}


@override_settings(UNIVERSITY_MODE=True)
class LessonsLogUnitFiltersTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.org = make_org("llf-univ")
            stack = make_academic_stack(cls.org, code="LLF101")
            period = stack["period"]

            def unit(name, unit_type, parent=None):
                return OrgUnit.objects.create(
                    organization=cls.org,
                    name=name,
                    slug=f"llf-{name.lower().replace(' ', '-')}",
                    unit_type=unit_type,
                    parent=parent,
                )

            cls.f1 = unit("Mühəndislik fakültəsi", OrgUnitType.FACULTY)
            cls.f2 = unit("İqtisadiyyat fakültəsi", OrgUnitType.FACULTY)
            cls.c1 = unit("İnformatika kafedrası", OrgUnitType.CHAIR, cls.f1)
            cls.c2 = unit("Riyaziyyat kafedrası", OrgUnitType.CHAIR, cls.f1)
            cls.c3 = unit("Maliyyə kafedrası", OrgUnitType.CHAIR, cls.f2)
            specialty = unit("Proqram mühəndisliyi", OrgUnitType.SPECIALTY, cls.f1)
            cls.g1 = unit("PM-101", OrgUnitType.GROUP, specialty)  # qrup → ixtisas → fakültə (kafedrasız)
            cls.g2 = unit("MF-201", OrgUnitType.GROUP, cls.f2)

            cls.t1 = User.objects.create_user("llf_t1", "llf_t1@qku.edu.az", PASSWORD)
            cls.t2 = User.objects.create_user("llf_t2", "llf_t2@qku.edu.az", PASSWORD)
            cls.t3 = User.objects.create_user("llf_t3", "llf_t3@qku.edu.az", PASSWORD)
            cls.rim = User.objects.create_user("llf_rim", "llf_rim@qku.edu.az", PASSWORD)
            cls.dean = User.objects.create_user("llf_dean", "llf_dean@qku.edu.az", PASSWORD)
            activate_member(cls.org, cls.t1, "teacher", permissions=TEACHER_PERMS, scope_unit=cls.c1)
            activate_member(cls.org, cls.t2, "teacher", permissions=TEACHER_PERMS, scope_unit=cls.c3)
            activate_member(cls.org, cls.t3, "teacher", permissions=TEACHER_PERMS)
            activate_member(
                cls.org,
                cls.rim,
                "rim_head",
                permissions=SUPERVISOR_PERMS,
                level=90,
                scope_type=RoleScopeType.ORGANIZATION,
            )
            activate_member(
                cls.org,
                cls.dean,
                "dean",
                permissions=SUPERVISOR_PERMS,
                level=70,
                scope_type=RoleScopeType.UNIT,
                scope_unit=cls.f1,
            )
            for user, role in (
                (cls.t1, "teacher"),
                (cls.t2, "teacher"),
                (cls.t3, "teacher"),
                (cls.rim, "rim_head"),
                (cls.dean, "dean"),
            ):
                profile = user.profile
                profile.role = role
                profile.save(update_fields=["role"])

            def offering(code, group, teacher, chair=None):
                subject = Subject.objects.create(organization=cls.org, code=code, name=f"Fənn {code}", chair_unit=chair)
                return CourseOffering.objects.create(
                    organization=cls.org,
                    subject=subject,
                    period=period,
                    group=group,
                    instructor=teacher,
                    lesson_hours=60,
                )

            cls.o1 = offering("LLF-A", cls.g1, cls.t1, chair=cls.c2)
            cls.o2 = offering("LLF-B", cls.g2, cls.t2)
            cls.o3 = offering("LLF-C", cls.g1, cls.t3, chair=cls.c3)
            for index, item in enumerate((cls.o1, cls.o2, cls.o3)):
                Lesson.objects.create(
                    organization=cls.org,
                    offering=item,
                    date=dt.date(2025, 10, 6 + index),
                    kind=LessonKind.LECTURE,
                    hours=2,
                    topic=f"Mövzu {item.subject.code}",
                )

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _section(self, user, **params):
        url = reverse("accounts:profile_section_fragment", kwargs={"section": SECTION})
        response = self._client(user).get(url, dict(WINDOW, **params))
        self.assertEqual(response.status_code, 200)
        return response.context["lessons_log_section"]

    @staticmethod
    def _codes(section):
        return sorted(row["subject_code"] for row in section["rows"])

    @staticmethod
    def _field(section, name):
        return next(field for field in section["filters"]["fields"] if field["name"] == "ll_" + name)

    # ── Tərif ────────────────────────────────────────────────────────────────

    def test_faculty_is_the_groups_ancestor(self):
        self.assertEqual(self._codes(self._section(self.rim, ll_faculty=str(self.f1.pk))), ["LLF-A", "LLF-C"])
        self.assertEqual(self._codes(self._section(self.rim, ll_faculty=str(self.f2.pk))), ["LLF-B"])

    def test_kafedra_is_the_teachers_chair_or_the_subjects_chair(self):
        self.assertEqual(self._codes(self._section(self.rim, ll_kafedra=str(self.c1.pk))), ["LLF-A"])  # müəllim
        self.assertEqual(self._codes(self._section(self.rim, ll_kafedra=str(self.c2.pk))), ["LLF-A"])  # fənn
        self.assertEqual(self._codes(self._section(self.rim, ll_kafedra=str(self.c3.pk))), ["LLF-B", "LLF-C"])

    def test_totals_follow_the_filter(self):
        section = self._section(self.rim, ll_kafedra=str(self.c3.pk))
        self.assertEqual(section["totals"]["lessons"], 2)

    # ── Kaskad + seçim siyahıları ────────────────────────────────────────────

    def test_faculty_narrows_the_kafedra_options_and_drops_a_foreign_selection(self):
        everything = self._section(self.rim)
        faculties = [o["value"] for o in self._field(everything, "faculty")["options"]]
        kafedras = [o["value"] for o in self._field(everything, "kafedra")["options"]]
        self.assertEqual(set(faculties), {"", str(self.f1.pk), str(self.f2.pk)})
        self.assertEqual(set(kafedras), {"", str(self.c1.pk), str(self.c2.pk), str(self.c3.pk)})
        self.assertTrue(self._field(everything, "kafedra")["searchable"])

        narrowed = self._section(self.rim, ll_faculty=str(self.f1.pk), ll_kafedra=str(self.c3.pk))
        self.assertEqual(
            {o["value"] for o in self._field(narrowed, "kafedra")["options"]}, {"", str(self.c1.pk), str(self.c2.pk)}
        )
        # Fakültəyə aid olmayan kafedra atılır — nəticə boş qalmır, ixrac URL-i də təmizdir.
        self.assertEqual(self._field(narrowed, "kafedra")["value"], "")
        self.assertEqual(self._codes(narrowed), ["LLF-A", "LLF-C"])
        self.assertNotIn("ll_kafedra", narrowed["export_url"])
        # Fənn siyahısı da seçilmiş fakültəyə görə daralır.
        offerings = {o["value"] for o in self._field(narrowed, "offering")["options"]}
        self.assertNotIn(str(self.o2.pk), offerings)

    def test_options_respect_the_supervisors_scope(self):
        section = self._section(self.dean)
        self.assertEqual(self._codes(section), ["LLF-A", "LLF-C"])  # dekan yalnız öz fakültəsinin qruplarını görür
        self.assertEqual({o["value"] for o in self._field(section, "faculty")["options"]}, {"", str(self.f1.pk)})
        self.assertEqual(
            {o["value"] for o in self._field(section, "kafedra")["options"]}, {"", str(self.c1.pk), str(self.c2.pk)}
        )

    def test_unknown_unit_returns_nothing(self):
        section = self._section(self.rim, ll_kafedra=str(uuid.uuid4()))
        self.assertEqual(section["rows"], [])
        self.assertEqual(self._codes(self._section(self.rim, ll_faculty="not-a-uuid")), [])

    def test_applied_chip_names_the_unit(self):
        section = self._section(self.rim, ll_kafedra=str(self.c1.pk))
        chips = {chip["name"]: chip["value_label"] for chip in section["filters"]["applied"]}
        self.assertEqual(chips["ll_kafedra"], "İnformatika kafedrası")

    def test_rendered_bar_uses_the_project_select_with_search(self):
        url = reverse("accounts:profile_section_fragment", kwargs={"section": SECTION})
        response = self._client(self.rim).get(url, WINDOW)
        html = response.json()["html"] if "json" in response.get("Content-Type", "") else response.content.decode()
        for name in ("ll_faculty", "ll_kafedra"):
            self.assertIn(f'name="{name}"', html)
        self.assertIn('data-live-search="true"', html)

    # ── CSV + sayğac + sorğu büdcəsi ─────────────────────────────────────────

    def test_csv_export_applies_the_filters(self):
        response = self._client(self.rim).get(
            reverse("registrar:lessons_log_csv"), dict(WINDOW, ll_kafedra=str(self.c1.pk))
        )
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn("LLF-A", body)
        self.assertNotIn("LLF-B", body)
        self.assertNotIn("LLF-C", body)

    def test_unrecorded_counter_uses_the_same_units(self):
        window = {"start": dt.date(2025, 10, 6), "end": dt.date(2025, 10, 19)}

        def count(**filters):
            with bypass_rls():
                return service.unrecorded_slots(
                    self.rim, self.org, supervisor=True, window=window, today=dt.date(2025, 10, 20), filters=filters
                )["count"]

        with bypass_rls():
            slot = ScheduleSlot.objects.create(
                organization=self.org, offering=self.o2, weekday=5, start_time=dt.time(9, 0), end_time=dt.time(10, 20)
            )
            # Cədvəl semestrdən əvvəl daxil edilib — sayğac günü həmin gün qüvvədə olan cədvələ görə yoxlayır.
            ScheduleSlot.all_objects.filter(pk=slot.pk).update(created_at=timezone.make_aware(dt.datetime(2025, 8, 1)))
        self.assertEqual(count(), 2)  # 10.10 və 17.10 cümə — dərs yazılmayıb
        self.assertEqual(count(faculty_unit=self.f2), 2)
        self.assertEqual(count(faculty_unit=self.f1), 0)
        self.assertEqual(count(kafedra_unit=self.c3), 2)  # müəllim (t2) Maliyyə kafedrasındadır
        self.assertEqual(count(kafedra_unit=self.c1), 0)
        self.assertEqual(count(invalid_unit=True), 0)

    def test_option_queries_do_not_grow_with_rows(self):
        client = self._client(self.rim)
        url = reverse("accounts:profile_section_fragment", kwargs={"section": SECTION})
        client.get(url, WINDOW)  # isinmə
        with CaptureQueriesContext(connection) as before:
            client.get(url, WINDOW)
        with bypass_rls():
            for index in range(8):
                Lesson.objects.create(
                    organization=self.org,
                    offering=(self.o1, self.o2, self.o3)[index % 3],
                    date=dt.date(2025, 11, 3 + index),
                    kind=LessonKind.SEMINAR,
                    hours=2,
                )
        with CaptureQueriesContext(connection) as after:
            client.get(url, WINDOW)
        self.assertLessEqual(len(after.captured_queries), len(before.captured_queries))
