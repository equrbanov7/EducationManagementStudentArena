"""Səviyyə qrupları keçidi sidebar-dadır (2026-11-01) və səhifə jurnal sayı ilə ləngimir.

Sahib: «Xarici dil səviyyə qrupları keçidini jurnalın üstündən götür, sidebara qrupların
yanına qoy; açılmasında gecikmə var». Burada: (1) keçid roster əhatəli heyətdə
«Tədris şöbəsi → Qruplar»-dan sonra, səviyyə jurnalı olan müəllimdə «Elektron jurnal»-ın
yanındadır, tələbədə/adi müəllimdə yoxdur; (2) jurnal siyahısında üzən düymə qalmayıb;
(3) reyestr səhifəsinin sorğu sayı səviyyəsiz jurnalların sayından asılı deyil.
"""

from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.organizations.models import Membership
from apps.registrar.models import CourseOffering, Subject
from apps.registrar.tests.test_guest_roster import _GuestRosterBase
from core.rls import bypass_rls


@override_settings(UNIVERSITY_MODE=True)
class LanguageCohortNavTests(_GuestRosterBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.history.name = "Xarici dil-1 (Elementary)"
            cls.history.save(update_fields=["name"])
            cls.plain_teacher = cls._make_user("gr_plain_teacher")
            Membership.objects.create(
                user=cls.plain_teacher,
                organization=cls.org,
                role=cls.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
            cls.math_offering = cls.host.enrollments.get(offering__subject=cls.math).offering
            cls.math_offering.instructor = cls.plain_teacher
            cls.math_offering.save(update_fields=["instructor"])
            cls.student = cls.host
            for user in (cls.coordinator, cls.teacher, cls.plain_teacher, cls.student):
                user.profile.organization = cls.org
                user.profile.save(update_fields=["organization"])

    @classmethod
    def _make_user(cls, username):
        from django.contrib.auth import get_user_model

        return get_user_model().objects.create_user(username, f"{username}@qku.edu.az", "pw")

    def _sidebar(self, user):
        response = self._client(user).get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_roster_staff_sees_the_link_right_after_groups_in_the_teaching_office_group(self):
        html = self._sidebar(self.coordinator)
        link = f'href="{reverse("registrar:language_cohorts")}"'
        self.assertIn(link, html)
        group_start = html.index('data-sidebar-group="teaching-office"')
        groups_item = html.index('data-section="groups-registry"', group_start)
        self.assertLess(groups_item, html.index(link, group_start))
        # Qruplar ilə səviyyə qrupları arasında başqa bənd yoxdur (eyni hissə, yanaşı).
        between = html[groups_item : html.index(link, group_start)]
        self.assertEqual(between.count("sidebar-menu-item"), 1)

    def test_level_journal_teacher_gets_the_link_beside_the_journal_entry(self):
        html = self._sidebar(self.teacher)
        link = f'href="{reverse("registrar:language_cohorts")}"'
        self.assertIn(link, html)
        journal = html.index('href="/jurnal/" target="_blank"')
        self.assertLess(journal, html.index(link))
        self.assertNotIn('data-sidebar-group="teaching-office"', html)

    def test_student_and_teacher_without_level_journal_do_not_get_the_link(self):
        link = f'href="{reverse("registrar:language_cohorts")}"'
        self.assertNotIn(link, self._sidebar(self.plain_teacher))
        self.assertNotIn(link, self._sidebar(self.student))

    def _render_journal_item(self, user, layout):
        from django.template.loader import render_to_string
        from django.test import RequestFactory

        request = RequestFactory().get("/")
        request.user = user
        request.organization = self.org
        return render_to_string(
            "accounts/profile/sidebar/items/_my_journal.html",
            {
                "allowed_sections": {"my-journal"},
                "role_capabilities": {"is_student": False},
                "sidebar_layout": layout,
                "profile_base_url": "/profile/",
            },
            request=request,
        )

    def test_roster_staff_on_the_compact_teacher_layout_still_gets_the_link_beside_the_journal(self):
        """Tam akkordeonda bənd «Tədris şöbəsi»ndədir; kompakt müəllim düzümündə o qrup yoxdur —
        roster əhatəli heyət keçidi itirməməlidir (review tapıntısı, 2026-11-01)."""
        link = f'href="{reverse("registrar:language_cohorts")}"'
        self.assertIn(link, self._render_journal_item(self.coordinator, "teacher"))
        self.assertNotIn(link, self._render_journal_item(self.coordinator, "full"))
        self.assertIn(link, self._render_journal_item(self.teacher, "full"))
        self.assertNotIn(link, self._render_journal_item(self.plain_teacher, "teacher"))

    def test_nav_tag_is_computed_once_per_request(self):
        from django.template import Context, Template
        from django.test import RequestFactory

        request = RequestFactory().get("/")
        request.user = self.coordinator
        request.organization = self.org
        template = Template(
            "{% load language_cohort_links %}{% language_cohort_nav as a %}{% language_cohort_nav as b %}"
            "{{ a.staff }}|{{ b.staff }}|{{ a.url }}"
        )
        with CaptureQueriesContext(connection) as first:
            rendered = template.render(Context({"request": request}))
        self.assertEqual(rendered, f"True|True|{reverse('registrar:language_cohorts')}")
        with CaptureQueriesContext(connection) as second:
            template.render(Context({"request": request}))
        self.assertGreater(len(first), 0)
        self.assertEqual(len(second), 0)

    def test_journal_list_no_longer_renders_the_floating_entry_button(self):
        response = self._client(self.coordinator).get(reverse("registrar:journal_list"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, f'href="{reverse("registrar:language_cohorts")}"')

    def _add_plain_journals(self, count):
        with bypass_rls():
            for index in range(count):
                subject = Subject.objects.create(
                    organization=self.org, code=f"PLN{index:03d}", name=f"Adi fənn {index}"
                )
                CourseOffering.objects.create(
                    organization=self.org,
                    subject=subject,
                    group=self.group1,
                    period=self.period,
                    instructor=self.teacher,
                )

    def test_registry_page_query_count_does_not_grow_with_non_level_journals(self):
        client = self._client(self.coordinator)
        url = reverse("registrar:language_cohorts")
        self._add_plain_journals(3)
        with CaptureQueriesContext(connection) as small:
            self.assertEqual(client.get(url).status_code, 200)
        self._add_plain_journals(20)
        with CaptureQueriesContext(connection) as large:
            response = client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(large), len(small))
        self.assertContains(response, "lc-grid")
        self.assertContains(response, 'class="lc-form"')

    def test_authorized_cohorts_uses_one_scope_query_for_many_cohorts(self):
        from apps.registrar import language_cohorts

        cohorts = [
            language_cohorts.create_cohort(
                organization=self.org,
                actor=self.coordinator,
                department=self.chair,
                period=self.period,
                subject=self.history,
                instructor=self.teacher,
                name=f"Level {index}",
                hours=30,
                lecture_hours=0,
                seminar_hours=30,
                lab_hours=0,
                entry_score_max=50,
                pass_threshold=51,
                min_final_exam_score=17,
                confirm_separate=True,
            )
            for index in range(3)
        ]
        expected = [row for row in cohorts if language_cohorts.can_manage(self.coordinator, row)]
        self.assertEqual(len(expected), 3)
        with CaptureQueriesContext(connection) as batched:
            rows = language_cohorts.authorized_cohorts(self.coordinator, self.org)
        self.assertEqual({row.pk for row in rows}, {row.pk for row in cohorts})
        self.assertLessEqual(len(batched), 6)
        self.assertEqual(language_cohorts.authorized_cohorts(self.outsider, self.org), [])
        self.assertEqual(
            {row.pk for row in language_cohorts.authorized_cohorts(self.teacher, self.org)}, {row.pk for row in cohorts}
        )
