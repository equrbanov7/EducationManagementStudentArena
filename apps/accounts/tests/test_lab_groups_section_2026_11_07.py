"""«Lab qrupları» kabinet bölməsi (sahib 2026-11-07: «sidebarda qruplar olan yerdə yerləşsin … belə yox»).

Nəyi qoruyur
------------
* menyu qapısı: jurnalın müəllimi (lab saatlı öz jurnalı), «lab» payı, kafedra müdiri (``workload.distribute``), RİM —
  bəli; tələbə, ``journal.view`` müşahidəçisi, jurnalsız müəllim, «seminar» payı — yox;
* bölmə: jurnal siyahısı yalnız lab saatlı (və ya artıq bölünmüş) və aktorun idarə edə bildiyi jurnallar; kənar
  kafedranın müdiri bizim jurnalı görmür və URL ilə seçəndə iş sahəsi açılmır;
* iş sahəsi: «Qrupsuz» + qrup sütunları, kilidli tələbə (öz qrupunun dərsində qeydi var), yaratmaq formu, JS/CSS
  xarici fayllardır; bağlı semestrdə yalnız oxu;
* köhnə ünvan (/jurnal/<id>/lab-qruplari/) bölməyə yönləndirir, jurnal öncədən seçilir;
* yazılar bölmənin JSON endpoint-i ilə: yaratmaq / ad / köçürmək / silmək; başqasına 403, GET 405, naməlum əməl 400.
"""

from __future__ import annotations

import datetime

from django.test import override_settings
from django.urls import reverse

from apps.accounts.views._helpers.rbac_sections import apply_permission_section_gates
from apps.organizations.models import AcademicPeriod
from apps.registrar import lab_groups
from apps.registrar import lab_groups_section as journals
from apps.registrar.models import Enrollment, LabGroup, Lesson, LessonKind, LessonMark, ScheduleSlot
from apps.registrar.tests.test_lab_groups_manage_2026_11_06 import LabManageBase
from core.rls import bypass_rls

SECTION = "lab-groups"


@override_settings(UNIVERSITY_MODE=True)
class _SectionBase(LabManageBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            # Tarix (G1) — cədvəldə laboratoriya slotu var → lab saatlı jurnal; Fizika (G1) — lab yoxdur.
            ScheduleSlot.objects.create(
                organization=cls.org,
                offering=cls.offering,
                weekday=2,
                start_time=datetime.time(9, 0),
                end_time=datetime.time(10, 20),
                week_type="all",
                kind=LessonKind.LAB,
            )

    def fragment(self, user, **params):
        response = self.client_for(user).get(reverse("accounts:profile_section_fragment", args=[SECTION]), params)
        self.assertEqual(response.status_code, 200, user.username)
        return response.json()["html"]

    def action_url(self, offering=None):
        return reverse("registrar:journal_lab_groups_action", args=[(offering or self.offering).pk])

    def act(self, user=None, **data):
        return self.client_for(user or self.teacher).post(self.action_url(), data)

    def rows(self, user, **params):
        with bypass_rls():
            scope = journals.resolve_scope(user, self.org)
            return {
                row["id"]
                for row in journals.page(user, self.org, scope, journals.parse_filters(params, self.org))["rows"]
            }


class MenuGateTest(_SectionBase):
    def test_menu_gate(self):
        expected = {
            self.teacher: True,
            self.lab_teacher: True,
            self.chair_head: True,
            self.rim: True,
            self.sem_teacher: False,
            self.other_teacher: False,
            self.observer: False,
            self.host: False,
        }
        for user, visible in expected.items():
            sections: set = set()
            apply_permission_section_gates(user, self.org, sections, is_superadmin=False, is_owner=False)
            self.assertEqual(SECTION in sections, visible, user.username)

    def test_sidebar_item_sits_next_to_groups_for_staff_and_under_journal_for_teacher(self):
        page = self.client_for(self.teacher).get(reverse("accounts:profile"), {"section": SECTION})
        self.assertContains(page, f'data-profile-section-panel="{SECTION}"')
        self.assertContains(page, f'data-section="{SECTION}"')
        self.assertContains(page, "#flask-conical")
        student = self.client_for(self.host).get(reverse("accounts:profile"), {"section": SECTION})
        self.assertEqual(student.status_code, 200)
        self.assertNotContains(student, f'data-section="{SECTION}"')
        self.assertEqual(
            self.client_for(self.host).get(reverse("accounts:profile_section_fragment", args=[SECTION])).status_code,
            403,
        )


class ListTest(_SectionBase):
    def test_teacher_sees_only_lab_journals_without_structure_filters(self):
        html = self.fragment(self.teacher)
        self.assertIn("data-lgx-root", html)
        self.assertIn("accounts/css/profile/sections/lab_groups.css", html)
        self.assertIn("accounts/js/profile/lab_groups.js", html)
        self.assertIn(f"lg_offering={self.offering.pk}", html)
        self.assertNotIn(f"lg_offering={self.physics_g1.pk}", html)  # Fizikada laboratoriya yoxdur
        self.assertNotIn('name="lg_faculty"', html)  # şəxsi əhatə — fakültə / kafedra süzgəci lazım deyil
        self.assertIn('name="lg_group"', html)
        self.assertIn("data-bootstrap-select", html)
        self.assertIn("Jurnal seçin", html)

    def test_split_journal_appears_and_status_filter(self):
        with bypass_rls():
            LabGroup.objects.create(organization=self.org, offering=self.physics_g1, number=1)
        self.assertEqual(self.rows(self.teacher), {str(self.offering.pk), str(self.physics_g1.pk)})
        self.assertEqual(self.rows(self.teacher, lg_status="split"), {str(self.physics_g1.pk)})
        self.assertEqual(self.rows(self.teacher, lg_status="unsplit"), {str(self.offering.pk)})
        # Fizikanın yeganə tələbəsi qrupsuzdur → «qrupsuz tələbəsi var»; Tarix bölünəndə o da düşür.
        self.assertEqual(self.rows(self.teacher, lg_status="pending"), {str(self.physics_g1.pk)})
        self.set_groups({self.e1: 1})
        self.assertEqual(self.rows(self.teacher, lg_status="pending"), {str(self.offering.pk), str(self.physics_g1.pk)})

    def test_scope_follows_manage_rules(self):
        own = str(self.offering.pk)
        self.assertIn(own, self.rows(self.rim))
        self.assertIn(own, self.rows(self.chair_head))
        self.assertIn(own, self.rows(self.lab_teacher))
        self.assertNotIn(own, self.rows(self.far_head))
        html = self.fragment(self.far_head, lg_offering=own)
        self.assertNotIn("data-lgx-ws", html)
        self.assertIn("səlahiyyətiniz yoxdur", html)

    def test_rim_gets_structure_filters_and_kpis(self):
        html = self.fragment(self.rim)
        for name in ("lg_q", "lg_period", "lg_faculty", "lg_chair", "lg_teacher", "lg_group", "lg_status"):
            self.assertIn(f'name="{name}"', html, name)
        self.assertIn("ems-kpis", html)
        self.assertIn("Lab saatlı jurnal", html)


class WorkspaceTest(_SectionBase):
    def test_workspace_columns_lock_and_tools(self):
        self.set_groups({self.e1: 1, self.e2: 1})
        self.act(action="rename", group="1", name="Səhər")
        bound = self.lesson(lab_group=1)
        with bypass_rls():
            LessonMark.objects.create(organization=self.org, lesson=bound, enrollment=self.e1, status="present")
        html = self.fragment(self.teacher, lg_offering=str(self.offering.pk))
        self.assertIn("data-lgx-ws", html)
        self.assertIn(self.action_url(), html)
        self.assertIn('data-lgx-col="none"', html)
        self.assertIn('data-lgx-col="1"', html)
        self.assertIn("Səhər", html)
        self.assertIn("lgx-stu is-locked", html)  # e1 — öz qrupunun dərsində qeydi var
        self.assertIn('draggable="true"', html)
        self.assertIn("data-lgx-create-form", html)
        self.assertIn("data-lgx-move", html)
        self.assertIn('data-readonly="0"', html)
        self.assertNotIn("data-lgx-delete", html)  # qrupa dərs bağlıdır — silmək düyməsi yoxdur
        self.assertIn(reverse("registrar:journal_detail", args=[self.offering.pk]), html)

    def test_closed_period_is_read_only(self):
        with bypass_rls():
            AcademicPeriod.objects.filter(pk=self.period.pk).update(is_current=False)
        html = self.fragment(self.teacher, lg_offering=str(self.offering.pk))
        self.assertIn('data-readonly="1"', html)
        self.assertIn("ems-banner--warning", html)
        self.assertNotIn("data-lgx-create-form", html)
        self.assertNotIn("data-lgx-pick", html)

    def test_old_url_redirects_to_section_with_journal_preselected(self):
        client = self.client_for(self.teacher)
        response = client.get(reverse("registrar:journal_lab_groups", args=[self.offering.pk]))
        self.assertEqual(response.status_code, 302)
        page = client.get(response["Location"])
        self.assertContains(page, "data-lgx-ws")
        self.assertContains(page, self.action_url())
        detail = client.get(reverse("registrar:journal_detail", args=[self.offering.pk]))
        self.assertContains(detail, "jd2-labgroups-link")
        self.assertContains(detail, f"lg_offering={self.offering.pk}")


class ActionEndpointTest(_SectionBase):
    def groups(self):
        with bypass_rls():
            return dict(Enrollment.objects.filter(offering=self.offering).values_list("pk", "lab_group"))

    def test_create_rename_assign_delete(self):
        response = self.act(action="create", name="Səhər")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["messages"][0]["level"], "success")
        self.act(action="create")
        self.assertEqual(self.numbers(), [1, 2])
        self.assertEqual(lab_groups.label(1, self.fresh()), "Səhər")
        self.assertEqual(self.act(action="rename", group="2", name="Axşam").status_code, 200)
        self.assertEqual(lab_groups.label(2, self.fresh()), "Axşam")
        moved = self.act(action="assign", target="2", enrollment=[str(self.e1.pk), str(self.e2.pk)])
        self.assertEqual(moved.json()["messages"][0]["text"].split()[0], "2")
        self.assertEqual((self.groups()[self.e1.pk], self.groups()[self.e2.pk]), (2, 2))
        self.act(action="assign", target="none", enrollment=[str(self.e1.pk)])
        self.assertIsNone(self.groups()[self.e1.pk])
        self.assertEqual(self.act(action="delete", group="2").status_code, 400)  # təsdiqsiz
        self.assertEqual(self.act(action="delete", group="2", confirm="1").status_code, 200)
        self.assertIsNone(self.groups()[self.e2.pk])
        self.assertEqual(self.numbers(), [1])

    def test_errors_and_permissions(self):
        self.assertEqual(self.act(action="nope").status_code, 400)
        duplicate = self.act(action="assign", target="7", enrollment=[str(self.e1.pk)])
        self.assertEqual((duplicate.status_code, duplicate.json()["error"]), (400, "not_found"))
        self.assertEqual(self.client_for(self.teacher).get(self.action_url()).status_code, 405)
        for user in (self.far_head, self.other_teacher, self.observer, self.host, self.sem_teacher):
            self.assertEqual(self.act(user, action="create").status_code, 403, user.username)
        self.assertEqual(self.numbers(), [])
        with bypass_rls():
            self.assertFalse(Lesson.objects.filter(offering=self.offering).exists())
