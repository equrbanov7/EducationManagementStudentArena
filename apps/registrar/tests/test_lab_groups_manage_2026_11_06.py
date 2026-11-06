"""Sahib 2026-11-06: jurnalda «Lab qrupları» ekranı — qrupları yaratmaq, adlandırmaq, tələbə yerləşdirmək, silmək.

Nəyi qoruyur
------------
* səlahiyyət: jurnalın müəllimi (açılışın müəllimi / «lab» növlü pay), açılışın kafedrasının müdiri
  (``workload.distribute``), RİM rəhbəri, sahib — bəli; başqa kafedranın müdiri, başqa müəllim, ``journal.view``
  müşahidəçisi, tələbə, «seminar» payı — HTTP 403 və heç nə yazılmır; jurnal başlığındakı keçid yalnız idarəçiyə;
* yaratmaq: heç bölünməmiş jurnalda Lab-1, Lab-2 …; ən kiçik boş nömrə (dərsə bağlı nömrə «məşğul»); 9 tavanı;
  köhnə sətirsiz Lab-1 / Lab-2 qrup sayılır və «Lab-N» adlanır;
* ad: istəyə bağlı, dəyişdirilə bilir, boş = «Lab-N», təkrar ad rədd; qrid nişanı, sətir çipi, dərs modalı adı
  göstərir; adı dəyişən qrupun dərsləri bağlı qalır (nömrə dəyişmir);
* yerləşdirmək / köçürmək / qrupsuz etmək: yalnız bu jurnalın aktiv tələbələri; öz qrupunun dərsində qeydi olan
  tələbə köçürülmür; qrupsuz tələbələr ayrıca siyahıdadır;
* silmək: dərs bağlıdırsa yox; təsdiqsiz yox; üzvlər qrupsuz qalır;
* bağlı jurnal / keçmiş dövr — heç nə dəyişmir; hər dəyişiklik auditdədir.
"""

from __future__ import annotations

import datetime

from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from apps.audit.models import AuditLog
from apps.organizations.models import AcademicPeriod, Role
from apps.registrar import gradebook, lab_groups
from apps.registrar import lab_groups_manage as service
from apps.registrar.models import CourseOffering, Enrollment, JournalShare, LabGroup, Lesson, LessonKind, LessonMark
from apps.registrar.tests.subgroup_base import SubgroupFixture
from core.constants import RoleScopeType
from core.rls import bypass_rls


class LabManageBase(SubgroupFixture, TestCase):
    PREFIX = "labm"

    @classmethod
    def setUpTestData(cls):
        cls.build_world()
        with bypass_rls():
            cls.history.chair_unit = cls.chair
            cls.history.save(update_fields=["chair_unit"])
            cls.offering = cls.history_g1
            cls.offering.instructor = cls.teacher
            cls.offering.save(update_fields=["instructor"])
            student_role = cls.org.roles.get(name="student")
            teacher_role = cls.org.roles.get(name="teacher")
            cls.students = [cls._member(f"labm_s{index}", student_role) for index in range(3)]
            cls.e1, cls.e2, cls.e3 = (
                Enrollment.objects.create(organization=cls.org, student=student, offering=cls.offering)
                for student in cls.students
            )
            cls.e_host = Enrollment.objects.get(offering=cls.offering, student=cls.host)
            cls.chair_head = cls._member("labm_head", cls.org.roles.get(name="chair_head"), cls.chair)
            cls.far_head = cls._member("labm_farhead", cls.org.roles.get(name="chair_head"), cls.far_faculty)
            cls.rim = cls._member("labm_rim", cls.org.roles.get(name="ikt_rehber"))
            cls.other_teacher = cls._member("labm_other", teacher_role)
            observer_role = Role.objects.create(
                organization=cls.org,
                name="labm_observer",
                display_name="Müşahidəçi (test)",
                level=40,
                scope_type=RoleScopeType.ORGANIZATION,
                permissions=["journal.view"],
            )
            cls.observer = cls._member("labm_obs", observer_role)
            cls.lab_teacher = cls._member("labm_labt", teacher_role)
            cls.sem_teacher = cls._member("labm_semt", teacher_role)
            JournalShare.objects.create(
                organization=cls.org, offering=cls.offering, teacher=cls.lab_teacher, kinds=["lab"]
            )
            JournalShare.objects.create(
                organization=cls.org, offering=cls.offering, teacher=cls.sem_teacher, kinds=["seminar"]
            )

    # ── köməkçilər ──────────────────────────────────────────────────────────
    @property
    def url(self):
        return reverse("registrar:journal_lab_groups", args=[self.offering.pk])

    def post(self, user=None, **data):
        return self.client_for(user or self.teacher).post(self.url, data)

    def fresh(self):
        with bypass_rls():
            return CourseOffering.objects.select_related("organization", "period", "subject").get(pk=self.offering.pk)

    def groups_of(self):
        with bypass_rls():
            return dict(Enrollment.objects.filter(offering=self.offering).values_list("pk", "lab_group"))

    def set_groups(self, mapping):
        with bypass_rls():
            for enrollment, group in mapping.items():
                Enrollment.objects.filter(pk=enrollment.pk).update(lab_group=group)

    def lesson(self, lab_group=None, kind=LessonKind.LAB):
        with bypass_rls():
            return Lesson.objects.create(
                organization=self.org,
                offering=self.offering,
                date=datetime.date(2025, 10, 7),
                kind=kind,
                hours=2,
                lab_group=lab_group,
            )

    def numbers(self):
        return lab_groups.offering_groups(self.fresh())


class PermissionTest(LabManageBase):
    def test_who_can_manage(self):
        offering = self.fresh()
        for user in (self.teacher, self.owner, self.chair_head, self.lab_teacher):
            self.assertTrue(service.can_manage(user, offering), user.username)
        for user in (self.far_head, self.other_teacher, self.observer, self.host, self.sem_teacher, self.plain):
            self.assertFalse(service.can_manage(user, offering), user.username)

    def test_rim_and_chair_head_over_http(self):
        # 2026-11-07: köhnə ünvan kabinetin «Lab qrupları» bölməsinə yönləndirir (jurnal öncədən seçilmiş).
        for user in (self.rim, self.chair_head):
            response = self.client_for(user).get(self.url)
            self.assertEqual(response.status_code, 302, user.username)
            self.assertIn("section=lab-groups", response["Location"])
            self.assertIn(f"lg_offering={self.offering.pk}", response["Location"])
        self.post(self.rim, action="create")
        self.assertEqual(self.numbers(), [1])

    def test_others_get_403_and_change_nothing(self):
        self.set_groups({self.e1: 1})
        for user in (self.far_head, self.other_teacher, self.observer, self.host, self.sem_teacher):
            client = self.client_for(user)
            self.assertEqual(client.get(self.url).status_code, 403, user.username)
            for data in (
                {"action": "create", "name": "X"},
                {"action": "rename", "group": "1", "name": "X"},
                {"action": "assign", "target": "1", "enrollment": [str(self.e2.pk)]},
                {"action": "delete", "group": "1", "confirm": "1"},
            ):
                self.assertEqual(client.post(self.url, data).status_code, 403, (user.username, data))
        with bypass_rls():
            self.assertFalse(LabGroup.objects.filter(offering=self.offering).exists())
        self.assertEqual(self.groups_of()[self.e1.pk], 1)
        self.assertIsNone(self.groups_of()[self.e2.pk])

    def test_journal_header_link_only_for_managers(self):
        detail = reverse("registrar:journal_detail", args=[self.offering.pk])
        link = f"lg_offering={self.offering.pk}"
        self.assertContains(self.client_for(self.teacher).get(detail), link)
        observer_page = self.client_for(self.observer).get(detail)
        self.assertEqual(observer_page.status_code, 200)
        self.assertNotContains(observer_page, link)

    def test_inactive_offering_is_read_only(self):
        with bypass_rls():
            CourseOffering.objects.filter(pk=self.offering.pk).update(is_active=False)
        self.assertFalse(service.can_manage(self.teacher, self.fresh()))


class CreateRenameTest(LabManageBase):
    def test_split_a_journal_never_split_before(self):
        self.assertEqual(len(service.panel(self.fresh())["ungrouped"]), 4)
        self.post(action="create")
        self.post(action="create", name="  Axşam   qrupu ")
        self.assertEqual(self.numbers(), [1, 2])
        offering = self.fresh()
        with translation.override("az"):
            self.assertEqual(lab_groups.choices(offering), [(1, "Lab-1"), (2, "Axşam qrupu")])
        with bypass_rls():
            logs = AuditLog.objects.filter(resource_type=service.RESOURCE, action="create")
            self.assertEqual(logs.count(), 2)
        # Üzvsüz təzə qrup da jurnaldadır: «Yeni dərs»də lab dərsinin qrupu məcburidir.
        with self.assertRaises(lab_groups.LabGroupError):
            lab_groups.require_for_new(offering, kind=LessonKind.LAB, lab_group=None)

    def test_legacy_groups_without_rows_keep_working(self):
        self.set_groups({self.e1: 1, self.e2: 2})
        offering = self.fresh()
        with translation.override("az"):
            self.assertEqual(lab_groups.choices(offering), [(1, "Lab-1"), (2, "Lab-2")])
        self.post(action="create")
        self.assertEqual(self.numbers(), [1, 2, 3])

    def test_smallest_free_number_skips_lesson_bound_numbers_and_caps_at_nine(self):
        self.set_groups({self.e2: 2})
        self.lesson(lab_group=1)  # köhnə dərs Lab-1-ə bağlıdır, qrupun üzvü yoxdur
        self.post(action="create")
        self.assertEqual(self.numbers(), [2, 3])
        for _ in range(10):
            self.post(action="create")
        with bypass_rls():
            self.assertEqual(LabGroup.objects.filter(offering=self.offering).count(), 7)
        with self.assertRaises(service.LabGroupManageError):
            service.create_group(offering=self.fresh(), actor=self.teacher)

    def test_rename_default_and_duplicate(self):
        self.set_groups({self.e1: 1, self.e2: 2})
        self.post(action="rename", group="1", name="Səhər")
        with translation.override("az"):
            self.assertEqual(lab_groups.label(1, self.fresh()), "Səhər")
            self.post(action="rename", group="2", name="səhər")  # təkrar (registr fərqi sayılmır)
            self.assertEqual(lab_groups.label(2, self.fresh()), "Lab-2")
            self.post(action="rename", group="2", name="Lab-2")
            with bypass_rls():
                self.assertFalse(LabGroup.objects.filter(offering=self.offering, number=2).exists())
            self.post(action="rename", group="1", name="")
            self.assertEqual(lab_groups.label(1, self.fresh()), "Lab-1")
        self.post(action="rename", group="7", name="Yox")
        with bypass_rls():
            self.assertFalse(LabGroup.objects.filter(offering=self.offering, number=7).exists())
            renames = AuditLog.objects.filter(resource_type=service.RESOURCE, action="update")
            self.assertEqual(renames.count(), 2)


class AssignDeleteTest(LabManageBase):
    def assign(self, target, *enrollments, user=None):
        return self.post(user, action="assign", target=target, enrollment=[str(row.pk) for row in enrollments])

    def test_assign_move_unassign(self):
        self.post(action="create")
        self.post(action="create")
        self.assign("1", self.e1, self.e2)
        self.assertEqual((self.groups_of()[self.e1.pk], self.groups_of()[self.e2.pk]), (1, 1))
        self.assign("2", self.e2)
        self.assertEqual(self.groups_of()[self.e2.pk], 2)
        self.assign("none", self.e1)
        self.assertIsNone(self.groups_of()[self.e1.pk])
        panel = service.panel(self.fresh())
        self.assertEqual({row["enrollment"].pk for row in panel["ungrouped"]}, {self.e1.pk, self.e3.pk, self.e_host.pk})
        self.assertEqual([len(group["members"]) for group in panel["groups"]], [0, 1])
        with bypass_rls():
            moves = AuditLog.objects.filter(resource_type=service.RESOURCE, resource_id=str(self.e2.pk))
            self.assertEqual(moves.count(), 2)

    def test_assign_rejects_foreign_or_missing_targets(self):
        self.set_groups({self.e1: 1})
        with bypass_rls():
            foreign = Enrollment.objects.filter(student=self.host).exclude(offering=self.offering).first()
        self.assign("1", self.e2, foreign)
        self.assign("5", self.e2)
        self.assign("", self.e2)
        self.post(action="assign", target="1")
        self.assertIsNone(self.groups_of()[self.e2.pk])

    def test_student_with_marks_in_own_group_lessons_is_not_moved(self):
        self.set_groups({self.e1: 1, self.e2: 1})
        bound = self.lesson(lab_group=1)
        whole = self.lesson()
        with bypass_rls():
            LessonMark.objects.create(organization=self.org, lesson=bound, enrollment=self.e1, status="present")
            LessonMark.objects.create(organization=self.org, lesson=whole, enrollment=self.e2, status="present")
        self.post(action="create")
        action = reverse("registrar:journal_lab_groups_action", args=[self.offering.pk])
        response = self.client_for(self.teacher).post(
            action, {"action": "assign", "target": "2", "enrollment": [str(self.e1.pk), str(self.e2.pk)]}
        )
        self.assertEqual((self.groups_of()[self.e1.pk], self.groups_of()[self.e2.pk]), (1, 2))
        levels = [item["level"] for item in response.json()["messages"]]
        self.assertEqual(levels, ["success", "warning"])

    def test_delete_rules(self):
        self.set_groups({self.e1: 1, self.e2: 2, self.e3: 2})
        self.post(action="rename", group="2", name="Axşam")
        bound = self.lesson(lab_group=1)
        self.post(action="delete", group="1", confirm="1")
        self.assertEqual(self.numbers(), [1, 2])
        self.post(action="delete", group="2")  # təsdiqsiz
        self.assertEqual(self.numbers(), [1, 2])
        self.post(action="delete", group="2", confirm="1")
        self.assertEqual(self.numbers(), [1])
        self.assertEqual((self.groups_of()[self.e2.pk], self.groups_of()[self.e3.pk]), (None, None))
        with bypass_rls():
            self.assertFalse(LabGroup.objects.filter(offering=self.offering, number=2).exists())
            log = AuditLog.objects.get(resource_type=service.RESOURCE, action="delete")
            self.assertEqual(log.changes["unassigned"], 2)
            Lesson.objects.filter(pk=bound.pk).update(lab_group=None)
        self.post(action="delete", group="1", confirm="1")
        self.assertEqual(self.numbers(), [])

    def test_closed_period_changes_nothing(self):
        with bypass_rls():
            AcademicPeriod.objects.filter(pk=self.period.pk).update(is_current=False)
        self.assertTrue(service.block_reason(self.fresh()))
        action = reverse("registrar:journal_lab_groups_action", args=[self.offering.pk])
        response = self.client_for(self.teacher).post(action, {"action": "create"})
        self.assertEqual((response.status_code, response.json()["error"]), (409, "blocked"))
        self.post(action="create")
        self.assertEqual(self.numbers(), [])


class GridAndModalNamesTest(LabManageBase):
    def test_names_in_grid_chips_header_and_lesson_modal(self):
        self.set_groups({self.e1: 1, self.e2: 2})
        lesson = self.lesson(lab_group=1)
        self.post(action="rename", group="1", name="Səhər qrupu")
        detail = reverse("registrar:journal_detail", args=[self.offering.pk])
        response = self.client_for(self.teacher).get(detail, HTTP_ACCEPT_LANGUAGE="az")
        self.assertContains(response, '<option value="1">Səhər qrupu</option>', html=False)
        self.assertContains(response, '<option value="2">Lab-2</option>', html=False)
        self.assertContains(response, ">Səhər qrupu</div>")  # dərs sütununun nişanı
        self.assertContains(response, ">Səhər qrupu</small>")  # tələbə sətrinin çipi
        # Adı dəyişən qrupun dərsi bağlı qalır: nömrə eyni, Lab-2 tələbəsinin xanası yenə bağlıdır.
        with bypass_rls():
            self.assertEqual(Lesson.objects.get(pk=lesson.pk).lab_group, 1)
            journal = gradebook.get_offering_journal(offering=self.fresh())
            result = gradebook.save_marks(
                offering=self.fresh(),
                entries=[
                    {"lesson_id": str(lesson.pk), "enrollment_id": str(self.e1.pk), "status": "present"},
                    {"lesson_id": str(lesson.pk), "enrollment_id": str(self.e2.pk), "status": "present"},
                ],
                enforce_day=False,
                report=True,
            )
        self.assertEqual(journal["lesson_meta"][0]["lab_group_label"], "Səhər qrupu")
        self.assertEqual((result["written"], result["rejected"]), (1, 1))
