"""«Dərs yüküm» — cədvəlin «CƏMİ» xanası görünən sətirlərin cəmidir (müəllim rəyi W1, 2026-10-08).

Bug: semestr tabı («Payız») sətirləri süzürdü, «CƏMİ» isə semestrdən asılı olmayaraq
İLLİK cəmi göstərirdi — ekranda 300 saatlıq sətirlərin altında «630» yazılırdı.
Birləşmiş qruplar («2233 İ 2232 İ») ikiqat sayılmır: bir sətir = bir təyinat.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.organizations.models import OrgUnit
from apps.workload.constants import Activity, Season, TaskStatus
from apps.workload.services import assign_teacher, confirm_distribution, resolve_actor, teacher_workload_summary
from core.constants import OrgUnitType, RoleScopeType

from .factories import TEACHER_PERMS, YEAR, activate_member, make_org, make_row, make_structure, make_task

User = get_user_model()

CHAIR_PERMS = ["workload.view", "workload.manage", "workload.distribute", "workload.report"]


class MyWorkloadVisibleTotalTest(TestCase):
    def setUp(self):
        self.org = make_org("wl-w1")
        self.stack = make_structure(self.org, code="WLW")
        self.head = User.objects.create_user("wlw_head", "wlw_head@x.test", "pw")
        activate_member(
            self.org,
            self.head,
            "chair_head",
            permissions=CHAIR_PERMS,
            scope_unit=self.stack["chair"],
            level=70,
            scope_type=RoleScopeType.UNIT,
        )
        self.teacher = User.objects.create_user("wlw_teacher", "wlw_teacher@x.test", "pw")
        activate_member(
            self.org,
            self.teacher,
            "teacher",
            permissions=TEACHER_PERMS,
            scope_unit=self.stack["chair"],
            level=50,
            scope_type=RoleScopeType.COURSE,
        )
        actor = resolve_actor(self.head, self.org)
        task = make_task(self.org, self.stack["chair"], status=TaskStatus.APPROVED, created_by=self.head)
        # Payız: birləşmiş iki qrup («2233 İ 2232 İ») — 30 mühazirə + 30 seminar = 60 saat.
        fall = make_row(task, self.stack, lecture_total=30, seminar_total=30)
        second_group = OrgUnit.objects.create(
            organization=self.org,
            parent=self.stack["group"].parent,
            name="2232 İ",
            slug="wl-w1-2232",
            unit_type=OrgUnitType.GROUP,
        )
        fall.groups.add(second_group)
        fall.groups_text = "2233 İ 2232 İ"
        fall.save(update_fields=["groups_text"])
        # Yaz: 45 + 25 = 70 saat.
        spring = make_row(task, self.stack, lecture_total=45, seminar_total=25)
        spring.season = Season.SPRING
        spring.save(update_fields=["season"])
        for row, lecture, seminar in ((fall, 30, 30), (spring, 45, 25)):
            assign_teacher(row=row, actor=actor, activity=Activity.LECTURE, teacher_id=self.teacher.pk, hours=lecture)
            assign_teacher(row=row, actor=actor, activity=Activity.SEMINAR, teacher_id=self.teacher.pk, hours=seminar)
        confirm_distribution(task=task, actor=actor)
        self.client.force_login(self.teacher)

    def _rows(self, season=""):
        response = self.client.get(reverse("workload:my_rows"), {"year": YEAR, "season": season})
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_fall_tab_total_equals_visible_rows(self):
        payload = self._rows("fall")
        visible = sum(row["hours"] for row in payload["rows"])
        self.assertEqual(visible, 60)
        self.assertEqual(payload["summary"]["rows_total_hours"], visible)
        # «İllik cəmi» KPI-ı illik olaraq qalır.
        self.assertEqual(payload["summary"]["total_hours"], 130)
        self.assertEqual(payload["summary"]["fall_hours"], 60)
        self.assertEqual(payload["summary"]["spring_hours"], 70)

    def test_spring_and_all_tabs(self):
        spring = self._rows("spring")
        self.assertEqual(spring["summary"]["rows_total_hours"], sum(r["hours"] for r in spring["rows"]))
        self.assertEqual(spring["summary"]["rows_total_hours"], 70)
        summer = self._rows("summer")
        self.assertEqual(summer["rows"], [])
        self.assertEqual(summer["summary"]["rows_total_hours"], 0)
        everything = self._rows("")
        self.assertEqual(everything["summary"]["rows_total_hours"], 130)
        self.assertEqual(sum(r["hours"] for r in everything["rows"]), 130)

    def test_combined_groups_are_not_double_counted(self):
        payload = self._rows("fall")
        combined = [row for row in payload["rows"] if row["groups"] == "2233 İ 2232 İ"]
        self.assertEqual(len(combined), 2)  # mühazirə + seminar, qrup başına YOX
        self.assertEqual(
            teacher_workload_summary(organization=self.org, teacher=self.teacher, academic_year=YEAR)["total_hours"],
            130,
        )

    def test_section_footer_is_labelled_and_matches_rows(self):
        response = self.client.get(reverse("accounts:profile_section_fragment", kwargs={"section": "my-workload"}))
        self.assertEqual(response.status_code, 200)
        html = response.json()["html"]
        self.assertIn("data-wlm-total-label", html)
        self.assertIn('data-label-season="CƏMİ — {season} semestri"', html)
        self.assertRegex(html, r"data-wlm-total>\s*130\s*<")
