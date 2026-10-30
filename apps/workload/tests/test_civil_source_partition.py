"""Three official teachers keep five existing physical journals intact."""

from copy import deepcopy
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.organizations.models import Membership, OrgUnit
from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonMark
from apps.workload.models import TeacherAssignment, TeachingTaskRow
from apps.workload.services import civil_source_partition as civil
from apps.workload.services.sbio235_state import RepairError, records
from core.rls import apply_rls_request_context, reset_rls_context


@override_settings(RLS_TRANSACTION_SCOPED=True)
class CivilPartitionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from .test_cavid_source_batch import CavidSourceBatchTests

        CavidSourceBatchTests.setUpTestData.__func__(cls)

    def setUp(self):
        apply_rls_request_context(user_id=self.admin.pk, org_id=self.org.pk, bypass=False)
        # Keep the fixture's historic journals untouched and create a separate
        # five-journal partition case in its already-scoped finance chair.
        groups = [
            OrgUnit.objects.create(
                organization=self.org, parent=self.ga.parent, unit_type="group", name=f"Civil{i}", slug=f"civil{i}"
            )
            for i in range(5)
        ]
        teachers = [self.teacher, self.previous, get_user_model().objects.create_user(username="third_civil")]
        for teacher in teachers:
            profile = teacher.profile
            profile.organization, profile.role = self.org, "teacher"
            profile.save(update_fields=["organization", "role"])
            Membership.objects.get_or_create(
                organization=self.org,
                user=teacher,
                role=self.org.roles.get(name="teacher"),
                scope_unit=self.finance,
                defaults={"is_active": True},
            )
        rows = []
        for indices, sem in (([0, 2], 30), ([1, 3, 4], 45)):
            row = TeachingTaskRow.objects.create(
                organization=self.org,
                task=self.ta,
                subject=self.sa,
                period=self.period,
                season="fall",
                degree_level="bachelor",
                education_form="eyani",
                lecture_plan=15,
                lecture_total=15,
                seminar_plan=15,
                seminar_total=sem,
                total_hours=15 + sem,
                union_count=1,
                subgroup_count=len(indices),
            )
            row.groups.set([groups[i] for i in indices])
            for activity, hours in (("lecture", 15), ("seminar", sem)):
                TeacherAssignment.objects.create(organization=self.org, row=row, activity=activity, hours=hours)
            rows.append(row)
        targets = {
            74: {
                "teacher": teachers[0].pk,
                "groups": [str(groups[i].pk) for i in [0, 1]],
                "seminar": 30,
                "sections": 2,
                "row": str(rows[0].pk),
            },
            60: {
                "teacher": teachers[1].pk,
                "groups": [str(groups[i].pk) for i in [2, 3]],
                "seminar": 15,
                "sections": 1,
                "row": str(rows[1].pk),
            },
            36: {"teacher": teachers[2].pk, "groups": [str(groups[4].pk)], "seminar": 15, "sections": 1, "row": None},
        }
        journals = {}
        for target in targets.values():
            for gid in target["groups"]:
                offering = CourseOffering.objects.create(
                    organization=self.org,
                    group_id=gid,
                    subject=self.sa,
                    period=self.period,
                    instructor_id=target["teacher"],
                    lesson_hours=30,
                )
                enrollment = Enrollment.objects.create(
                    organization=self.org, offering=offering, student=self.a.enrollments.first().student
                )
                lesson = Lesson.objects.create(
                    organization=self.org,
                    offering=offering,
                    date="2026-10-20",
                    kind="seminar",
                    hours=2,
                    instructor_id=target["teacher"],
                    created_by=self.admin,
                )
                LessonMark.objects.create(
                    organization=self.org, lesson=lesson, enrollment=enrollment, score=9, status="present"
                )
                journals[str(offering.pk)] = (target["teacher"], gid)
        self.patcher = patch.multiple(
            civil,
            TASK=str(self.ta.pk),
            SUBJECT=str(self.sa.pk),
            PERIOD=str(self.period.pk),
            OLD_ROWS=tuple(str(r.pk) for r in rows),
            TARGETS=targets,
            JOURNALS=journals,
        )
        self.patcher.start()
        self.manifest = {
            "format": civil.FORMAT,
            "organization_id": civil.ORG,
            "old_row_groups": {str(r.pk): [str(g.pk) for g in r.groups.all()] for r in rows},
            "sources": [
                {
                    "line": line,
                    "sha256": civil.SOURCE_SHA,
                    "teacher_id": t["teacher"],
                    "hours": {"lecture": 15, "seminar": t["seminar"], "lab": 0},
                    "group_ids": t["groups"],
                }
                for line, t in targets.items()
            ],
        }

    def tearDown(self):
        self.patcher.stop()
        reset_rls_context()

    def execute(self, **kw):
        return civil.run(
            manifest=self.manifest,
            manifest_sha="c" * 64,
            lines=[36, 60, 74],
            organization=self.org,
            user=self.admin,
            **kw,
        )

    def test_atomic_dry_then_partition_preserves_journals_and_repeats(self):
        before = civil._state()
        academic = records(self.b.lessons.all())
        dry = self.execute()
        self.assertEqual(before, civil._state())
        result = self.execute(apply=True, expected_baseline=dry["baseline"])
        after = civil._state()
        self.assertEqual(len(after["rows"]), 3)
        self.assertEqual(before["journals"], after["journals"])
        self.assertEqual(academic, records(self.b.lessons.all()))
        self.assertEqual(self.execute()["already_done"], 1)
        self.assertEqual(result["created_journals"], 0)

    def test_source_change_rejected(self):
        self.manifest = deepcopy(self.manifest)
        self.manifest["sources"][0]["teacher_id"] = self.admin.pk
        with self.assertRaisesMessage(RepairError, "civil_partition_source_identity_changed"):
            self.execute()

    def test_undo_restores_two_rows_and_unassigned_ids(self):
        before = civil._state()
        dry = self.execute()
        result = self.execute(apply=True, expected_baseline=dry["baseline"])
        preview = self.execute(undo=result["batch"])
        self.execute(undo=result["batch"], apply=True, expected_baseline=preview["baseline"])
        after = civil._state()
        self.assertEqual(len(after["rows"]), 2)
        self.assertEqual(before["groups"], after["groups"])
        self.assertEqual(before["journals"], after["journals"])
        self.assertEqual({a["id"] for a in before["assignments"]}, {a["id"] for a in after["assignments"]})
        self.assertEqual({a["teacher_id"] for a in after["assignments"]}, {None})
