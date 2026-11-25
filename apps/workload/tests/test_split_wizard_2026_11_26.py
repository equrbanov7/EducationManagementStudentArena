"""«Bölgü sehrbazı» (sahib 2026-11-26): seminar 2 alt qrupa, lab hər alt qrupda yenə 2-yə — addım-addım.

Nəyi qoruyur
------------
* 2 seminar × 2 lab ssenarisi uçdan-uca (HTTP): jurnalda 2 seminar alt qrupu (reyestrin «234 K1 / K2» mənbəyi ilə)
  və 4 lab qrupu yaranır, tələbələr yerləşir, sətrin cəmi düzəldilir (seminar 60, lab 60, alt qrup 2, lab qrupu 4 —
  düzəliş tarixçəsi ilə), 6 seminar/lab bölgüsü düzgün qrup / alt qrup № / saatla yazılır, mühazirəçi təyin olunur;
* açılış datası: reyestr alt qrupları, tələbənin reyestr qrupu, jurnal bölmələri;
* təkrar yadda saxlama heç nə dəyişmir (idempotent);
* təsdiqlənmiş sənəd: səbəbsiz — 409 və HEÇ NƏ yazılmır (jurnal bölmələri də geri qayıdır); səbəblə — düzəliş açılır;
* icazə: müəllim və başqa kafedranın müdiri — 403;
* bağlı jurnal: bölmə dəyişikliyi 409, saat bölgüsü isə (bölmələr dəyişmirsə) yazılır;
* trigger sırası: azalan redaktə artandan əvvəl, sətir cəmi əlavələrdən əvvəl; cəmdən artıq saat — 400, heç nə yazılmır;
* müştəri ilə serverin vahidləri uyğun gəlmirsə — 400.
"""

from __future__ import annotations

import datetime
import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.organizations.models import AcademicPeriod, OrgUnit
from apps.registrar.models import (
    CourseOffering,
    Curriculum,
    Enrollment,
    LabGroup,
    Lesson,
    LessonKind,
    SeminarGroup,
    StudentAcademicRecord,
)
from apps.workload.constants import Season, TaskStatus
from apps.workload.models import TeacherAssignment, TeachingTask, TeachingTaskRow, WorkloadAmendment
from apps.workload.services.tasks import row_warnings
from core.constants import OrgUnitType, RoleScopeType

from .factories import TEACHER_PERMS, activate_member, make_org, make_structure, make_task

User = get_user_model()
CHAIR_PERMS = ["workload.view", "workload.manage", "workload.distribute", "workload.report"]
AMEND = {"amend_reason": "correction", "amend_note": "Bölgü sehrbazı"}


class WizardBase(TestCase):
    code = "SW"
    status = TaskStatus.AMENDED

    @classmethod
    def setUpTestData(cls):
        cls.org = make_org(f"wiz-{cls.code.lower()}")
        cls.stack = make_structure(cls.org, code=cls.code)
        cls.task = make_task(cls.org, cls.stack["chair"], status=cls.status)
        cls.head = User.objects.create_user(f"{cls.code.lower()}-head")
        activate_member(
            cls.org,
            cls.head,
            "chair_head",
            permissions=CHAIR_PERMS,
            scope_unit=cls.stack["chair"],
            level=70,
            scope_type=RoleScopeType.UNIT,
        )
        cls.teachers = [cls._teacher(f"t{index}") for index in range(1, 7)]
        cls.group = cls.stack["group"]
        cls.group.name = f"{cls.code} 234 K"
        cls.group.save(update_fields=["name"])
        cls.k1, cls.k2 = (cls._subgroup(f"{cls.code} 234 K{n}", n) for n in (1, 2))
        cls.row = TeachingTaskRow.objects.create(
            organization=cls.org,
            task=cls.task,
            season=Season.FALL,
            period=cls.stack["period"],
            subject=cls.stack["subject"],
            specialty=cls.stack["specialty"],
            faculty=cls.stack["faculty"],
            student_count=8,
            union_count=1,
            subgroup_count=1,
            lecture_plan=30,
            lecture_total=30,
            seminar_plan=30,
            seminar_total=30,
            lab_plan=15,
            lab_total=15,
            total_hours=75,
            credits_value=6,
        )
        cls.row.groups.set([cls.group])
        cls.offering = CourseOffering.objects.create(
            organization=cls.org,
            subject=cls.stack["subject"],
            group=cls.group,
            period=cls.stack["period"],
            lesson_hours=75,
        )
        curriculum = Curriculum.objects.create(organization=cls.org, program=cls.stack["program"], admission_year=2025)
        cls.enrollments = []
        for index in range(8):
            student = User.objects.create_user(
                f"{cls.code.lower()}-st{index}", first_name=f"Ad{index}", last_name=f"Soyad{index}"
            )
            activate_member(cls.org, student, "student", permissions=["course.view"], level=10)
            StudentAcademicRecord.objects.create(
                organization=cls.org,
                student=student,
                program=cls.stack["program"],
                curriculum=curriculum,
                group=cls.k1 if index < 4 else cls.k2,
                admission_year=2025,
            )
            cls.enrollments.append(
                Enrollment.objects.create(organization=cls.org, student=student, offering=cls.offering)
            )

    @classmethod
    def _teacher(cls, name):
        user = User.objects.create_user(f"{cls.code.lower()}-{name}", first_name=name.title(), last_name="Müəllim")
        activate_member(cls.org, user, "teacher", permissions=TEACHER_PERMS)
        return user

    @classmethod
    def _subgroup(cls, name, number):
        return OrgUnit.objects.create(
            organization=cls.org,
            name=name,
            slug=f"{cls.org.slug}-sub-{number}",
            unit_type=OrgUnitType.GROUP,
            parent=cls.stack["specialty"],
            settings={"parent_group": str(cls.group.pk)},
        )

    # ── köməkçilər ──────────────────────────────────────────────────────────
    def _payload(self, *, fix=True, lecture=True, teachers=None, seminar_hours=30, lab_hours=15, amend=True):
        e = [str(item.pk) for item in self.enrollments]
        teachers = teachers or self.teachers
        gid, rid = str(self.group.pk), str(self.row.pk)
        units = [
            {
                "row_id": rid,
                "activity": "seminar",
                "group_id": gid,
                "sub_number": n,
                "teacher_id": str(teachers[n - 1].pk),
                "hours": seminar_hours,
                "is_hourly_paid": False,
            }
            for n in (1, 2)
        ] + [
            {
                "row_id": rid,
                "activity": "lab",
                "group_id": gid,
                "sub_number": n,
                "teacher_id": str(teachers[n + 1].pk),
                "hours": lab_hours,
                "is_hourly_paid": False,
            }
            for n in (1, 2, 3, 4)
        ]
        payload = {
            "task_id": str(self.task.pk),
            "row_ids": [rid],
            "rows": [{"row_id": rid, "joint": False, "fix_totals": fix}],
            "groups": [
                {
                    "row_id": rid,
                    "group_id": gid,
                    "apply_journal": True,
                    "seminar": {
                        "count": 2,
                        "names": [self.k1.name, self.k2.name],
                        "units": [str(self.k1.pk), str(self.k2.pk)],
                        "placement": {pk: 1 if i < 4 else 2 for i, pk in enumerate(e)},
                    },
                    "lab": {
                        "count": 4,
                        "nested": True,
                        "names": [
                            f"{self.k1.name} · Lab-1",
                            f"{self.k1.name} · Lab-2",
                            f"{self.k2.name} · Lab-1",
                            f"{self.k2.name} · Lab-2",
                        ],
                        "placement": {pk: i // 2 + 1 for i, pk in enumerate(e)},
                    },
                }
            ],
            "units": units,
            "lecture": [{"row_id": rid, "teacher_id": str(teachers[0].pk)}] if lecture else [],
        }
        if amend:
            payload.update(AMEND)
        return payload

    def _save(self, payload, user=None):
        self.client.force_login(user or self.head)
        return self.client.post(
            reverse("workload:split_wizard_save"), data=json.dumps(payload), content_type="application/json"
        )

    def _state(self, user=None):
        self.client.force_login(user or self.head)
        return self.client.get(
            reverse("workload:split_wizard_state"), {"task": str(self.task.pk), "rows": str(self.row.pk)}
        )

    def _section_assignments(self):
        return list(
            TeacherAssignment.objects.filter(row=self.row, activity__in=["seminar", "lab"]).order_by(
                "activity", "sub_number"
            )
        )


class SplitWizardEndToEndTests(WizardBase):
    def test_state_lists_journal_students_and_registry_subgroups(self):
        response = self._state()
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertTrue(data["task"]["can_fix_totals"])
        row = data["rows"][0]
        self.assertEqual((row["plans"]["seminar"], row["plans"]["lab"], row["totals"]["lab"]), (30, 15, 15))
        group = data["groups"][0]
        self.assertEqual(group["id"], str(self.group.pk))
        self.assertEqual([u["name"] for u in group["registry_subgroups"]], [self.k1.name, self.k2.name])
        journal = group["journal"]
        self.assertEqual(journal["offering_id"], str(self.offering.pk))
        self.assertTrue(journal["can_manage"])
        self.assertEqual(journal["block_reason"], "")
        self.assertEqual(len(journal["students"]), 8)
        self.assertEqual({s["unit_id"] for s in journal["students"]}, {str(self.k1.pk), str(self.k2.pk)})
        self.assertEqual((journal["seminar"], journal["lab"]), ([], []))

    def test_two_seminars_times_two_labs_end_to_end(self):
        response = self._save(self._payload())
        self.assertEqual(response.status_code, 200, response.content)
        summary = response.json()["summary"]
        self.assertEqual((summary["added"], summary["rows_fixed"], summary["lecturers"]), (6, 1, 1))

        seminars = list(SeminarGroup.objects.filter(offering=self.offering).order_by("number"))
        self.assertEqual(
            [(s.number, s.name, s.unit_id) for s in seminars],
            [(1, self.k1.name, self.k1.pk), (2, self.k2.name, self.k2.pk)],
        )
        labs = list(LabGroup.objects.filter(offering=self.offering).order_by("number").values_list("number", "name"))
        self.assertEqual([n for n, _ in labs], [1, 2, 3, 4])
        self.assertEqual(labs[2][1], f"{self.k2.name} · Lab-1")
        placed = {
            row.pk: (row.seminar_group, row.lab_group) for row in Enrollment.objects.filter(offering=self.offering)
        }
        expected = {e.pk: (1 if i < 4 else 2, i // 2 + 1) for i, e in enumerate(self.enrollments)}
        self.assertEqual(placed, expected)

        self.row.refresh_from_db()
        self.assertEqual(
            (self.row.seminar_total, self.row.lab_total, self.row.subgroup_count, self.row.lab_group_count),
            (60, 60, 2, 4),
        )
        self.assertEqual(self.row.total_hours, 150)
        codes = {w["code"] for w in row_warnings(self.row)}
        self.assertFalse(codes & {"seminar_total_mismatch", "lab_total_mismatch", "total_hours_mismatch"}, codes)
        self.assertTrue(WorkloadAmendment.objects.filter(task=self.task, target_id=self.row.pk).exists())

        items = self._section_assignments()
        self.assertEqual(
            [(a.activity, a.group_id, a.sub_number, a.hours, a.teacher_id) for a in items],
            [("lab", self.group.pk, n, 15, self.teachers[n + 1].pk) for n in (1, 2, 3, 4)]
            + [("seminar", self.group.pk, n, 30, self.teachers[n - 1].pk) for n in (1, 2)],
        )
        lecture = TeacherAssignment.objects.get(row=self.row, activity="lecture")
        self.assertEqual((lecture.teacher_id, lecture.hours), (self.teachers[0].pk, 30))

        state = self._state().json()
        journal = state["groups"][0]["journal"]
        self.assertEqual([s["label"] for s in journal["seminar"]], [self.k1.name, self.k2.name])
        self.assertEqual(len(journal["lab"]), 4)

    def test_resave_is_idempotent(self):
        self.assertEqual(self._save(self._payload()).status_code, 200)
        before = {a.pk: (a.teacher_id, a.hours, a.sub_number) for a in TeacherAssignment.objects.filter(row=self.row)}
        sections = list(SeminarGroup.objects.filter(offering=self.offering).values_list("pk", "updated_at"))
        response = self._save(self._payload(lecture=False))
        self.assertEqual(response.status_code, 200, response.content)
        summary = response.json()["summary"]
        self.assertEqual(
            (summary["sections"], summary["removed"], summary["edited"], summary["added"], summary["rows_fixed"]),
            (0, 0, 0, 0, 0),
        )
        after = {a.pk: (a.teacher_id, a.hours, a.sub_number) for a in TeacherAssignment.objects.filter(row=self.row)}
        self.assertEqual(before, after)
        self.assertEqual(
            sections, list(SeminarGroup.objects.filter(offering=self.offering).values_list("pk", "updated_at"))
        )

    def test_over_total_without_fix_writes_nothing(self):
        response = self._save(self._payload(fix=False))
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["error"], "workload.wizard_over_total")
        self.assertFalse(SeminarGroup.objects.filter(offering=self.offering).exists())
        self.assertFalse(TeacherAssignment.objects.filter(row=self.row).exists())

    def test_units_must_match_the_configuration(self):
        payload = self._payload()
        payload["units"] = payload["units"][:-1]
        response = self._save(payload)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["error"], "workload.wizard_units")

    def test_unplaced_students_are_rejected(self):
        payload = self._payload()
        payload["groups"][0]["seminar"]["placement"].pop(str(self.enrollments[0].pk))
        response = self._save(payload)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["error"], "workload.wizard_sections")
        self.assertFalse(SeminarGroup.objects.filter(offering=self.offering).exists())


class SplitWizardOrderingTests(WizardBase):
    code = "SO"

    def test_whole_group_seminar_becomes_two_sections_and_lab_hours_swap(self):
        TeachingTaskRow.objects.filter(pk=self.row.pk).update(lab_total=30, subgroup_count=1, lab_group_count=2)
        TeachingTaskRow.objects.filter(pk=self.row.pk).update(total_hours=135)
        t = self.teachers
        TeacherAssignment.objects.create(
            organization=self.org, row=self.row, teacher=t[0], activity="seminar", hours=30
        )
        TeacherAssignment.objects.create(
            organization=self.org, row=self.row, teacher=t[2], activity="lab", hours=20, group=self.group, sub_number=1
        )
        TeacherAssignment.objects.create(
            organization=self.org, row=self.row, teacher=t[3], activity="lab", hours=10, group=self.group, sub_number=2
        )
        self.row.refresh_from_db()
        payload = self._payload(lecture=False)
        group = payload["groups"][0]
        group["lab"] = {
            "count": 2,
            "nested": False,
            "names": ["", ""],
            "placement": {str(e.pk): 1 if i % 2 == 0 else 2 for i, e in enumerate(self.enrollments)},
        }
        rid, gid = str(self.row.pk), str(self.group.pk)
        payload["units"] = [u for u in payload["units"] if u["activity"] == "seminar"] + [
            {
                "row_id": rid,
                "activity": "lab",
                "group_id": gid,
                "sub_number": 1,
                "teacher_id": str(t[2].pk),
                "hours": 10,
            },
            {
                "row_id": rid,
                "activity": "lab",
                "group_id": gid,
                "sub_number": 2,
                "teacher_id": str(t[3].pk),
                "hours": 20,
            },
        ]
        response = self._save(payload)
        self.assertEqual(response.status_code, 200, response.content)
        self.row.refresh_from_db()
        self.assertEqual((self.row.seminar_total, self.row.lab_total, self.row.lab_group_count), (60, 30, 0))
        items = [(a.activity, a.sub_number, a.teacher_id, a.hours) for a in self._section_assignments()]
        self.assertEqual(
            items,
            [
                ("lab", 1, t[2].pk, 10),
                ("lab", 2, t[3].pk, 20),
                ("seminar", 1, t[0].pk, 30),
                ("seminar", 2, t[1].pk, 30),
            ],
        )


class SplitWizardDistributedTests(WizardBase):
    code = "SD"
    status = TaskStatus.DISTRIBUTED

    def test_amendment_required_rolls_everything_back_then_succeeds_with_reason(self):
        response = self._save(self._payload(amend=False))
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()["error"], "workload.amendment_required")
        self.assertFalse(SeminarGroup.objects.filter(offering=self.offering).exists())
        self.assertFalse(Enrollment.objects.filter(offering=self.offering, seminar_group__isnull=False).exists())
        self.assertEqual(TeachingTask.objects.get(pk=self.task.pk).status, TaskStatus.DISTRIBUTED)

        response = self._save(self._payload())
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["task"]["status"], TaskStatus.AMENDED)
        amendment = WorkloadAmendment.objects.get(task=self.task, target_id=self.row.pk)
        self.assertEqual((amendment.reason, amendment.note), ("correction", "Bölgü sehrbazı"))
        self.assertEqual(amendment.old_values["seminar_total"], 30)
        self.assertEqual(SeminarGroup.objects.filter(offering=self.offering).count(), 2)


class SplitWizardGappedNumbersTests(WizardBase):
    """Review 2026-11-26: «Lab-1» silinib {2,3} (və ya {1,3}) qalıb, Lab-2-də dərs var — heç nə dəyişmədən «Təsdiqlə»
    jurnalı yenidən nömrələməməlidir (əvvəl Lab-2-nin dərsləri Lab-3-ün tələbələrinə keçirdi)."""

    code = "SG"

    def _gapped(self, numbers):
        LabGroup.objects.filter(offering=self.offering).delete()
        Lesson.objects.filter(offering=self.offering).delete()
        for number in numbers:
            LabGroup.objects.create(organization=self.org, offering=self.offering, number=number)
        for index, item in enumerate(self.enrollments):
            Enrollment.objects.filter(pk=item.pk).update(lab_group=numbers[index % 2], seminar_group=None)
        Lesson.objects.create(
            organization=self.org,
            offering=self.offering,
            date=datetime.date(2026, 10, 7),
            kind=LessonKind.LAB,
            hours=2,
            lab_group=numbers[0],
        )
        TeachingTaskRow.objects.filter(pk=self.row.pk).update(lab_total=30, lab_group_count=2, total_hours=90)
        self.row.refresh_from_db()

    def test_no_op_save_keeps_real_numbers(self):
        rid, gid = str(self.row.pk), str(self.group.pk)
        for numbers in ([2, 3], [1, 3]):
            with self.subTest(numbers=numbers):
                TeacherAssignment.objects.filter(row=self.row).delete()
                self._gapped(numbers)
                state = self._state().json()
                self.assertEqual([s["number"] for s in state["groups"][0]["journal"]["lab"]], numbers)
                before = dict(Enrollment.objects.filter(offering=self.offering).values_list("pk", "lab_group"))
                payload = {
                    "task_id": str(self.task.pk),
                    "row_ids": [rid],
                    "rows": [{"row_id": rid, "joint": False, "fix_totals": False}],
                    "groups": [
                        {
                            "row_id": rid,
                            "group_id": gid,
                            "apply_journal": True,
                            "seminar": {"count": 0, "numbers": [], "names": [], "units": [], "placement": {}},
                            "lab": {
                                "count": 2,
                                "numbers": numbers,
                                "nested": False,
                                "names": ["", ""],
                                "placement": {str(pk): number for pk, number in before.items()},
                            },
                        }
                    ],
                    "units": [
                        {"row_id": rid, "activity": "seminar", "group_id": gid, "sub_number": None, "teacher_id": ""},
                    ]
                    + [
                        {
                            "row_id": rid,
                            "activity": "lab",
                            "group_id": gid,
                            "sub_number": number,
                            "teacher_id": str(self.teachers[i].pk),
                            "hours": 15,
                        }
                        for i, number in enumerate(numbers)
                    ],
                    **AMEND,
                }
                response = self._save(payload)
                self.assertEqual(response.status_code, 200, response.content)
                self.assertEqual(response.json()["summary"]["sections"], 0)
                self.assertEqual(
                    dict(Enrollment.objects.filter(offering=self.offering).values_list("pk", "lab_group")), before
                )
                self.assertEqual(
                    sorted(LabGroup.objects.filter(offering=self.offering).values_list("number", flat=True)), numbers
                )
                self.assertEqual(
                    sorted(
                        TeacherAssignment.objects.filter(row=self.row, activity="lab").values_list(
                            "sub_number", flat=True
                        )
                    ),
                    numbers,
                )


class SplitWizardJournalCreationTests(WizardBase):
    code = "SJ"

    def test_missing_journal_is_reported_and_created_through_the_sync_path(self):
        group = OrgUnit.objects.create(
            organization=self.org,
            name="SJ 236 K",
            slug=f"{self.org.slug}-g236",
            unit_type=OrgUnitType.GROUP,
            parent=self.stack["specialty"],
        )
        self.row.groups.add(group)
        state = self._state().json()
        self.assertIsNone({g["id"]: g for g in state["groups"]}[str(group.pk)]["journal"])
        self.assertTrue(state["task"]["plan_reached"])
        self.client.force_login(self.head)
        response = self.client.post(
            reverse("workload:split_wizard_journals"),
            data=json.dumps({"task_id": str(self.task.pk), "row_ids": [str(self.row.pk)]}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(
            CourseOffering.objects.filter(
                organization=self.org, subject=self.stack["subject"], period=self.stack["period"], group=group
            ).exists()
        )
        state = self._state().json()
        self.assertIsNotNone({g["id"]: g for g in state["groups"]}[str(group.pk)]["journal"])


class SplitWizardPermissionTests(WizardBase):
    code = "SP"

    def test_teacher_and_foreign_chair_head_are_denied(self):
        teacher = self.teachers[0]
        self.assertEqual(self._state(teacher).status_code, 403)
        self.assertEqual(self._save(self._payload(), teacher).status_code, 403)
        other_chair = OrgUnit.objects.create(
            organization=self.org,
            name="SP-başqa",
            slug=f"{self.org.slug}-other-chair",
            unit_type=OrgUnitType.CHAIR,
            parent=self.stack["faculty"],
        )
        stranger = User.objects.create_user("sp-stranger")
        activate_member(
            self.org,
            stranger,
            "chair_head",
            permissions=CHAIR_PERMS,
            scope_unit=other_chair,
            level=70,
            scope_type=RoleScopeType.UNIT,
        )
        self.assertEqual(self._save(self._payload(), stranger).status_code, 403)
        self.assertFalse(SeminarGroup.objects.filter(offering=self.offering).exists())
        self.assertFalse(TeacherAssignment.objects.filter(row=self.row).exists())


class SplitWizardClosedJournalTests(WizardBase):
    code = "SC"

    def _lock(self):
        """Keçmiş dövr — siyahı qapısı bağlıdır (``roster_block_reason``; «Lab qrupları» ekranı ilə eyni qapı)."""
        AcademicPeriod.objects.filter(pk=self.stack["period"].pk).update(is_current=False)

    def test_closed_journal_blocks_section_changes_but_not_unchanged_load(self):
        self._lock()
        state = self._state().json()
        self.assertTrue(state["groups"][0]["journal"]["block_reason"])
        response = self._save(self._payload())
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()["error"], "workload.wizard_blocked")
        self.assertFalse(SeminarGroup.objects.filter(offering=self.offering).exists())

        payload = self._payload()
        payload["groups"][0]["apply_journal"] = False  # sehrbaz bağlı jurnalda bölmələri göndərmir
        response = self._save(payload)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(SeminarGroup.objects.filter(offering=self.offering).exists())
        self.assertEqual(TeacherAssignment.objects.filter(row=self.row, activity="lab").count(), 4)
