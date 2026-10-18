"""«Kurslarım» redizaynı + «Sillabusdan mövzuları götür» (2026-10-18).

* kabinet siyahısı: KPI, filtr (axtarış / status), sıralama, səhifələmə, kart sayğacları; sorğu sayı kart sayından
  asılı deyil; E2E qarmaqları (`[data-mc-card]` + içindəki ilk `/courses/<id>/dashboard/` keçidi) qalır;
* rəng / ikon deterministikdir; status kataloqunda `course` ailəsi;
* sillabus idxalı: icazə (sahib ✓, başqa müəllim 403, tələbə 403, başqa təşkilat 404, oxunmayan sillabus 404),
  ön baxış yazmır, idxal idempotentdir (ad / həftə), bağ saxlanılır, sorğu büdcəsi.
"""

import json
import re

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.courses.models import Course, CourseMembership, CourseTopic
from apps.courses.presentation import ACCENTS, accent_for, course_identity, icon_for
from apps.exams.models import Exam
from apps.organizations.models import Membership, Organization
from apps.syllabus.models import Syllabus, SyllabusSection, SyllabusVersion
from apps.syllabus.tests.factories import make_academic_stack
from core.constants import OrganizationType
from core.ui import status_catalog

User = get_user_model()

WEEK_ROWS = [
    {"topic": "Giriş və VBİS", "lecture": 2, "seminar": 2, "lab": 0, "outcome": "TN1"},
    {"topic": "  Relyasiya   modeli ", "lecture": 2, "seminar": 0, "lab": 0, "outcome": "TN1, TN2"},
    {"topic": "", "lecture": 2, "seminar": 0, "lab": 0, "outcome": ""},
    {"topic": "SQL sorğuları", "lecture": 2, "seminar": 2, "lab": 0, "outcome": "TN9"},
]


def _org(slug, owner):
    return Organization.objects.create(
        name=slug.upper(), slug=slug, org_type=OrganizationType.UNIVERSITY, owner=owner, status="active", is_active=True
    )


def _join(user, org, profile_role, role_name):
    profile = user.profile
    profile.organization = org
    profile.organization_type = org.org_type
    profile.role = profile_role
    profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])
    Membership.objects.update_or_create(
        user=user,
        organization=org,
        defaults={"role": org.roles.get(name=role_name), "is_primary": True, "is_active": True},
    )


def _login(client, user, org):
    client.force_login(user)
    session = client.session
    session["active_organization"] = org.slug
    session.save()


def _syllabus(org, stack, author, *, approved=True, rows=WEEK_ROWS):
    syllabus = Syllabus.objects.create(
        organization=org, subject=stack["subject"], period=stack["period"], chair_unit=stack["chair"], author=author
    )
    extra = {"locked_at": timezone.now(), "approved_at": timezone.now(), "approved_by": author} if approved else {}
    version = SyllabusVersion.objects.create(
        organization=org, syllabus=syllabus, status="approved" if approved else "draft", **extra
    )
    syllabus.current_version = version
    syllabus.approved_version = version if approved else None
    syllabus.save()
    SyllabusSection.objects.create(organization=org, version=version, section_id="week", data={"rows": rows})
    SyllabusSection.objects.create(
        organization=org, version=version, section_id="out", data={"outcomes": ["Modeli izah edir", "SQL yazır"]}
    )
    return syllabus


class _Base(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("crs_t1", "crs_t1@example.com", "pw", first_name="Nigar")
        self.org = _org("crs-org", self.teacher)
        _join(self.teacher, self.org, ProfileRole.TEACHER, "teacher")
        self.other = User.objects.create_user("crs_t2", "crs_t2@example.com", "pw")
        _join(self.other, self.org, ProfileRole.TEACHER, "teacher")
        self.student = User.objects.create_user("crs_s1", "crs_s1@example.com", "pw")
        _join(self.student, self.org, ProfileRole.STUDENT, "student")
        self.course = Course.objects.create(owner=self.teacher, title="Verilənlər bazası", organization=self.org)
        _login(self.client, self.teacher, self.org)


class MyCoursesListTests(_Base):
    def _section(self, **params):
        url = reverse("accounts:profile_section_fragment", kwargs={"section": "my-courses"})
        return self.client.get(url, params)

    def _make(self, n, prefix="Kurs"):
        for i in range(n):
            course = Course.objects.create(
                owner=self.teacher, title=f"{prefix} {i}", organization=self.org, status="published"
            )
            CourseTopic.objects.create(course=course, title="T1", order=1)
            CourseMembership.objects.create(course=course, user=self.student, role="student", group_name=f"G-{i}")
            Exam.objects.create(author=self.teacher, course=course, title=f"E{i}", organization=self.org)

    def test_renders_header_kpis_filters_and_cards_with_e2e_hooks(self):
        self._make(2)
        response = self._section()
        self.assertEqual(response.status_code, 200)
        html = response.json()["html"]
        self.assertIn("ems-kpis", html)
        self.assertIn("data-ems-filters", html)
        self.assertIn('name="mc_q"', html)
        self.assertIn("js-open-create-course", html)
        cards = re.findall(r'<article class="mcl-card[^"]*" data-mc-card', html)
        self.assertEqual(len(cards), 3)
        # E2E: kartın içindəki İLK panel keçidi başlıqdakı əsas keçiddir (redaktə keçidi ondan sonra gəlir).
        first_card = html[html.index("data-mc-card") :]
        first_link = re.search(r'href="(/courses/\d+/dashboard/[^"]*)"', first_card).group(1)
        self.assertIn("from_section=my-courses", first_link)
        self.assertNotIn("edit=1", first_link)
        self.assertIn("crs-accent--", html)

    def test_card_counters_are_annotated(self):
        self._make(1, prefix="Say")
        response = self._section(mc_q="Say")
        card = response.context["my_courses_section"]["courses"][0]
        self.assertEqual(
            (card.card_topic_count, card.card_student_count, card.card_exam_count, card.card_group_count),
            (1, 1, 1, 1),
        )
        self.assertEqual(card.card_group_names, ["G-0"])
        self.assertEqual(card.card_task_count, 0)

    def test_search_status_and_sort(self):
        self._make(2)
        section = self._section(mc_q="verilen").context["my_courses_section"]
        self.assertEqual([c.title for c in section["courses"]], ["Verilənlər bazası"])
        self.assertTrue(section["is_filtered"])
        drafts = self._section(mc_status="draft").context["my_courses_section"]
        self.assertEqual([c.status for c in drafts["courses"]], ["draft"])
        ordered = self._section(mc_sort="title").context["my_courses_section"]
        titles = [c.title for c in ordered["courses"]]
        self.assertEqual(titles, sorted(titles))
        invalid = self._section(mc_status="hacked", mc_sort="nope").context["my_courses_section"]
        self.assertEqual(invalid["state"]["status"], "")
        self.assertEqual(invalid["state"]["sort"], "newest")

    def test_filtered_empty_state_and_kpis(self):
        response = self._section(mc_q="yoxdur-bele-kurs")
        section = response.context["my_courses_section"]
        self.assertEqual(section["courses"], [])
        self.assertEqual(section["total"], 1)
        self.assertContains(response, "fa-filter-circle-xmark")
        values = {tile["label"]: tile["value"] for tile in section["kpi_tiles"]}
        self.assertIn(1, values.values())

    def test_pagination(self):
        self._make(13)
        first = self._section().context["my_courses_section"]
        self.assertEqual(len(first["courses"]), 12)
        self.assertTrue(first["page_obj"].has_next())
        second = self._section(mc_page=2).context["my_courses_section"]
        self.assertEqual(len(second["courses"]), 2)
        self.assertIn("mc_page=2", second["return_to"])

    def test_query_count_does_not_grow_with_course_count(self):
        self._make(2)
        self._section()
        with CaptureQueriesContext(connection) as small:
            self._section()
        self._make(7, prefix="Daha")
        with CaptureQueriesContext(connection) as large:
            self._section()
        self.assertEqual(len(small.captured_queries), len(large.captured_queries))
        course_queries = [q for q in large.captured_queries if "courses_course" in q["sql"]]
        # KPI aqreqatı + filtr seçimləri + kart səhifəsi (+ qrup çipləri); filtrsiz COUNT yoxdur.
        self.assertLessEqual(len(course_queries), 4, [q["sql"][:90] for q in course_queries])

    def test_member_teacher_sees_course_without_owner_actions(self):
        CourseMembership.objects.create(course=self.course, user=self.other, role="teacher")
        _login(self.client, self.other, self.org)
        html = self._section().json()["html"]
        self.assertIn("Verilənlər bazası", html)
        self.assertNotIn(reverse("courses:update_course_status", args=[self.course.pk]), html)

    def test_first_time_empty_state(self):
        self.course.delete()
        html = self._section().json()["html"]
        self.assertIn("mcl-empty", html)
        self.assertNotIn("ems-kpis", html)


class PresentationTests(TestCase):
    def test_accent_is_deterministic_and_curated(self):
        self.assertEqual(accent_for("qku-101"), accent_for("qku-101"))
        self.assertIn(accent_for("python"), ACCENTS)
        self.assertEqual(icon_for("Verilənlər bazası"), "fa-database")
        self.assertEqual(icon_for("Python ilə proqramlaşdırma"), "fa-code")
        self.assertEqual(icon_for("Naməlum"), "fa-graduation-cap")

    def test_identity_prefers_linked_subject(self):
        course = Course(title="Hər hansı ad")
        self.assertEqual(course_identity(course)["accent"], accent_for("hər hansı ad"))

    def test_status_catalog_course_family(self):
        self.assertEqual(status_catalog.keys("course"), ("published", "draft", "archived"))
        self.assertIn("ems-badge--success", status_catalog.get("course", "published").css_class)


class SyllabusImportTests(_Base):
    def setUp(self):
        super().setUp()
        self.stack = make_academic_stack(self.org, code="CRS101")
        self.syllabus = _syllabus(self.org, self.stack, self.teacher)
        self.preview_url = reverse("courses:syllabus_preview", args=[self.course.pk])
        self.import_url = reverse("courses:syllabus_import", args=[self.course.pk])
        self.options_url = reverse("courses:syllabus_options", args=[self.course.pk])

    def _import(self, link=True, syllabus=None):
        return self.client.post(
            self.import_url,
            data=json.dumps({"syllabus": str((syllabus or self.syllabus).pk), "link": link}),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    def test_options_list_readable_syllabi(self):
        response = self.client.get(self.options_url)
        self.assertEqual(response.status_code, 200)
        items = response.json()["items"]
        self.assertEqual([item["id"] for item in items], [str(self.syllabus.pk)])
        self.assertTrue(items[0]["is_own"])
        self.assertTrue(items[0]["is_approved"])

    def test_preview_lists_weeks_and_writes_nothing(self):
        response = self.client.get(self.preview_url, {"syllabus": self.syllabus.pk})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual([row["week"] for row in payload["rows"]], [1, 2, 4])
        self.assertEqual(payload["rows"][1]["title"], "Relyasiya modeli")
        self.assertEqual(payload["counts"], {"total": 3, "new": 3, "existing": 0})
        self.assertFalse(CourseTopic.objects.filter(course=self.course).exists())
        self.course.refresh_from_db()
        self.assertIsNone(self.course.syllabus_id)

    def test_import_creates_topics_links_and_is_idempotent(self):
        CourseTopic.objects.create(course=self.course, title="Əl ilə mövzu", order=1)
        response = self._import()
        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.json()["created"], response.json()["skipped"]), (3, 0))
        self.assertTrue(response.json()["linked"])
        topics = list(CourseTopic.objects.filter(course=self.course).order_by("order"))
        self.assertEqual([t.order for t in topics], [1, 2, 3, 4])
        self.assertEqual([t.syllabus_week for t in topics], [None, 1, 2, 4])
        self.assertIn("TN2 — SQL yazır", topics[2].description)
        self.assertNotIn("TN9", topics[3].description)  # mövcud olmayan nəticə kodu yazılmır
        self.course.refresh_from_db()
        self.assertEqual(self.course.syllabus_id, self.syllabus.pk)

        again = self._import()
        self.assertEqual((again.json()["created"], again.json()["skipped"]), (0, 3))
        self.assertEqual(CourseTopic.objects.filter(course=self.course).count(), 4)

    def test_import_skips_same_title_and_renamed_week(self):
        CourseTopic.objects.create(course=self.course, title="giriş   və vbis", order=1)
        self._import()
        renamed = CourseTopic.objects.get(course=self.course, syllabus_week=2)
        renamed.title = "Yeni ad"
        renamed.save()
        preview = self.client.get(self.preview_url, {"syllabus": self.syllabus.pk}).json()
        self.assertEqual(preview["counts"]["new"], 0)
        self.assertEqual(self._import().json()["created"], 0)
        self.assertEqual(CourseTopic.objects.filter(course=self.course).count(), 3)

    def test_second_syllabus_weeks_are_new_and_imported(self):
        """Review MEDIUM: həftə açarı `(sillabus, həftə)`-dür — B-nin eyni nömrəli həftələri A ilə toqquşmur."""
        self._import()
        other = _syllabus(
            self.org,
            make_academic_stack(self.org, code="CRS104"),
            self.teacher,
            rows=[{"topic": "Şəbəkə modeli"}, {"topic": "TCP/IP"}, {"topic": "Giriş və VBİS"}],
        )
        preview = self.client.get(self.preview_url, {"syllabus": other.pk}).json()
        self.assertEqual([row["exists"] for row in preview["rows"]], [False, False, True])  # 3-cü: eyni ad
        result = self._import(syllabus=other).json()
        self.assertEqual((result["created"], result["skipped"]), (2, 1))
        created = CourseTopic.objects.filter(course=self.course, syllabus_source=other).order_by("order")
        self.assertEqual([(t.syllabus_week, t.title) for t in created], [(1, "Şəbəkə modeli"), (2, "TCP/IP")])
        self.assertEqual(CourseTopic.objects.filter(course=self.course, syllabus_source=self.syllabus).count(), 3)
        self.assertEqual(self._import(syllabus=other).json()["created"], 0)

    def test_title_key_folds_dotted_and_dotless_i(self):
        from apps.courses.syllabus_import import title_key

        self.assertEqual(title_key("SINAQ  İşi"), title_key("sınaq işi"))
        self.assertEqual(title_key("VBİS"), title_key("vbis"))

    def test_card_exam_count_skips_disabled_practical_exams(self):
        from unittest import mock

        Exam.objects.create(author=self.teacher, course=self.course, title="Test", organization=self.org)
        Exam.objects.create(
            author=self.teacher, course=self.course, title="Praktiki", organization=self.org, exam_type="coding"
        )
        url = reverse("accounts:profile_section_fragment", kwargs={"section": "my-courses"})
        with mock.patch("apps.exams.features.practical_exams_enabled", return_value=False):
            card = self.client.get(url).context["my_courses_section"]["courses"][0]
        self.assertEqual(card.card_exam_count, 1)

    def test_stale_link_is_not_rendered_into_dialog(self):
        self.course.syllabus = self.syllabus
        self.course.save()
        Syllabus.objects.filter(pk=self.syllabus.pk).update(is_active=False)
        response = self.client.get(reverse("courses:course_dashboard", args=[self.course.pk]))
        self.assertContains(response, 'data-linked-id=""')
        self.assertNotContains(response, "cd-syl-chip")

    def test_import_without_link_keeps_course_unlinked(self):
        self.assertEqual(self._import(link=False).json()["created"], 3)
        self.course.refresh_from_db()
        self.assertIsNone(self.course.syllabus_id)

    def test_draft_syllabus_uses_current_version(self):
        stack = make_academic_stack(self.org, code="CRS102")
        draft = _syllabus(self.org, stack, self.teacher, approved=False, rows=[{"topic": "Qaralama mövzu"}])
        response = self.client.get(self.preview_url, {"syllabus": draft.pk})
        self.assertEqual(response.json()["syllabus"]["status"], "draft")
        self.assertEqual(response.json()["counts"]["new"], 1)

    def test_other_teacher_is_denied(self):
        _login(self.client, self.other, self.org)
        self.assertEqual(self.client.get(self.preview_url, {"syllabus": self.syllabus.pk}).status_code, 403)
        self.assertEqual(self._import().status_code, 403)
        self.assertEqual(self.client.get(self.options_url).status_code, 403)
        self.assertFalse(CourseTopic.objects.filter(course=self.course).exists())

    def test_student_member_is_denied(self):
        CourseMembership.objects.create(course=self.course, user=self.student, role="student")
        _login(self.client, self.student, self.org)
        self.assertEqual(self._import().status_code, 403)
        self.assertFalse(CourseTopic.objects.filter(course=self.course).exists())

    def test_course_of_another_org_is_not_found(self):
        stranger = User.objects.create_user("crs_x", "crs_x@example.com", "pw")
        other_org = _org("crs-other", stranger)
        _join(stranger, other_org, ProfileRole.TEACHER, "teacher")
        _login(self.client, stranger, other_org)
        self.assertEqual(self._import().status_code, 404)

    def test_unreadable_syllabus_is_not_found(self):
        # Başqa təşkilatın sillabusu heç vaxt oxunmur.
        stranger = User.objects.create_user("crs_y", "crs_y@example.com", "pw")
        other_org = _org("crs-foreign", stranger)
        foreign = _syllabus(other_org, make_academic_stack(other_org, code="CRS109"), stranger)
        self.assertEqual(self.client.get(self.preview_url, {"syllabus": foreign.pk}).status_code, 404)
        self.assertEqual(self._import(syllabus=foreign).status_code, 404)
        self.assertEqual(self.client.get(self.preview_url, {"syllabus": "not-a-uuid"}).status_code, 404)
        self.assertFalse(CourseTopic.objects.filter(course=self.course).exists())

    def test_colleague_syllabus_needs_syllabus_view_scope(self):
        """Həmkarın sillabusu yalnız sillabus modulunun oxu qaydası ilə (``syllabus.view`` + əhatə) açılır."""
        colleague = _syllabus(self.org, make_academic_stack(self.org, code="CRS103"), self.other)
        role = self.org.roles.get(name="teacher")
        role.permissions = [p for p in role.permissions if p != "syllabus.view"]
        role.save(update_fields=["permissions"])
        _login(self.client, self.teacher, self.org)
        self.assertEqual(self.client.get(self.preview_url, {"syllabus": colleague.pk}).status_code, 404)
        self.assertEqual(self._import(syllabus=colleague).status_code, 404)
        # Öz sillabusu (müəllif) icazə açarından asılı olmayaraq oxunur.
        self.assertEqual(self.client.get(self.preview_url, {"syllabus": self.syllabus.pk}).status_code, 200)
        ids = [item["id"] for item in self.client.get(self.options_url, {"q": "Fənn"}).json()["items"]]
        self.assertNotIn(str(colleague.pk), ids)

    def test_query_budget(self):
        self.client.get(self.preview_url, {"syllabus": self.syllabus.pk})
        with CaptureQueriesContext(connection) as preview:
            self.client.get(self.preview_url, {"syllabus": self.syllabus.pk})
        with CaptureQueriesContext(connection) as applied:
            self._import()
        own = lambda ctx: [q for q in ctx.captured_queries if re.search(r"courses_|syllabus_", q["sql"])]  # noqa: E731
        # Ön baxış: kurs + sillabus (versiyalarla bir SELECT) + bölmələr + mövcud mövzular.
        self.assertLessEqual(len(own(preview)), 5, [q["sql"][:100] for q in own(preview)])
        # İdxal: kurs + sillabus + bölmələr + kilid + mövcud + max(order) + bulk insert + bağ yeniləməsi.
        self.assertLessEqual(len(own(applied)), 9, [q["sql"][:100] for q in own(applied)])

    def test_dashboard_shows_link_chip_and_import_entry_points(self):
        url = reverse("courses:course_dashboard", args=[self.course.pk])
        response = self.client.get(url)
        self.assertContains(response, 'data-bs-target="#syllabusImportModal"', count=2)  # başlıq + boş vəziyyət
        self.assertContains(response, 'id="syllabusImportModal"')
        self.assertNotContains(response, "cd-syl-chip")
        with CaptureQueriesContext(connection) as before:
            self.client.get(url)
        self._import()
        with CaptureQueriesContext(connection) as after:
            response = self.client.get(url)
        self.assertContains(response, "cd-syl-chip")
        self.assertContains(response, self.stack["subject"].name)
        # Bağlı sillabus `select_related` ilə gəlir; artım yalnız mövzu siyahısının resurs prefetch-idir.
        self.assertLessEqual(len(after.captured_queries), len(before.captured_queries) + 1)

    def test_student_dashboard_hides_import(self):
        CourseMembership.objects.create(course=self.course, user=self.student, role="student")
        _login(self.client, self.student, self.org)
        response = self.client.get(reverse("courses:course_dashboard", args=[self.course.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "syllabusImportModal")
