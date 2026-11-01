"""One reviewed 17-person roster: six factual slots, no identity or history writes."""

import copy
from contextlib import ExitStack
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase, override_settings

from apps.audit.models import AuditLog
from apps.legacy_import.services import reviewed_content as service
from apps.legacy_import.services import reviewed_content_336_bridge as bridge
from apps.legacy_import.services import reviewed_content_336_spec as fixed
from apps.legacy_import.services.reviewed_content_contract import ContentError, validate_payload
from apps.legacy_import.services.reviewed_content_spec import RESOURCE
from apps.legacy_import.services.reviewed_content_state import digest
from apps.legacy_import.tests.test_reviewed_content import MissingOnlyContentTests, payload
from apps.organizations.models import Membership, OrgUnit
from apps.registrar.models import (
    CourseOffering,
    Curriculum,
    Enrollment,
    Lesson,
    LessonMark,
    Program,
    StudentAcademicRecord,
    Subject,
)
from apps.workload.models import TeacherAssignment, TeachingTask, TeachingTaskRow


def source_fixture():
    raw = payload()
    raw["targets"] = [fixed.TARGET]
    raw["journals"] = [
        {
            "id": 14917,
            "uniqid": "oRfdzNf4J4",
            "lesson_id": 5,
            "semestr": 14,
            "groups_id": [936, 937],
            "teacher_id": 23,
            "fake": 0,
            "sonra_sil": 0,
            "active": 1,
        }
    ]
    raw["workers"][0]["id"] = 23
    raw["students"] = [{"id": sid, "group_id": 937} for sid in fixed.PAIRS]
    raw["students"] += [{"id": sid, "group_id": 937} for sid in (11086, 11092)]
    raw["students"] += [{"id": sid, "group_id": 936} for sid in range(20000, 20022)]
    days = [
        (9, 21, "11:50", 0),
        (9, 28, "10:10", 1),
        (10, 5, "11:50", 0),
        (10, 12, "10:10", 1),
        (10, 16, "10:10", 1),
        (10, 19, "11:50", 0),
    ]
    raw["dates"], raw["points"] = [], []
    for index, (month, day, time, kind) in enumerate(days):
        raw["dates"].append({"id": index + 1, "journal_id": 14917, "month": month, "day": day, "time": time})
        for student_index, student in enumerate(raw["students"]):
            if student_index >= 33 and index == 5:
                continue
            point = copy.deepcopy(payload()["points"][0])
            point.update(
                id=len(raw["points"]) + 1,
                journal_uniqid="oRfdzNf4J4",
                month_id=f"{month:02}",
                day_number=str(day),
                time=time,
                sem_muh=kind,
                student_id=student["id"],
                point="ie",
            )
            if student_index == 0 and index in (0, 3, 4):
                point["point"] = "qb"
            if student_index == 1 and index == 2:
                point["point"] = "7"
            if student_index == 0 and index == 5:
                point["point"] = "9"
            raw["points"].append(point)
    return raw


@override_settings(RLS_TRANSACTION_SCOPED=True)
class Reviewed336Tests(TestCase):
    map_identity = MissingOnlyContentTests.__dict__["map_identity"]
    tearDown = MissingOnlyContentTests.tearDown
    apply = MissingOnlyContentTests.apply

    # Share the mature RLS-aware source-map fixture, without inheriting its tests.
    @classmethod
    def setUpTestData(cls):
        MissingOnlyContentTests.setUpTestData.__func__(cls)
        User = get_user_model()
        parent = OrgUnit.objects.create(
            pk=fixed.PARENT,
            organization=cls.org,
            name="Bounded specialty",
            slug="bounded-specialty",
            unit_type="specialty",
            parent=cls.specialty.parent,
        )
        group_settings = {"sector": "az", "degree_level": "bachelor", "education_form": "full_time"}
        cls.group = OrgUnit.objects.create(
            pk=fixed.GROUP,
            organization=cls.org,
            name="336F2",
            slug="myedu-grp-937",
            unit_type="group",
            parent=parent,
            settings=group_settings,
        )
        other = OrgUnit.objects.create(
            pk=fixed.OTHER_GROUP,
            organization=cls.org,
            name="336F1",
            slug="myedu-grp-936",
            unit_type="group",
            parent=parent,
            settings=group_settings,
        )
        chair = OrgUnit.objects.create(
            pk="6cb37f21-4d0f-4858-8c53-1f09d4d0efda",
            organization=cls.org,
            name="Chair",
            slug="bounded-chair",
            unit_type="chair",
            parent=cls.specialty.parent,
        )
        teacher = User.objects.create_user(
            pk=fixed.TEACHER, username="bounded_teacher", first_name="Alim", last_name="Həsənli"
        )
        teacher.profile.organization, teacher.profile.patronymic = cls.org, "Kərim"
        teacher.profile.save()
        Membership.objects.create(
            organization=cls.org, user=teacher, role=cls.org.roles.get(name="teacher"), scope_unit=parent
        )
        subject = Subject.objects.create(pk=fixed.SUBJECT, organization=cls.org, code="FIXED-336", name="Fixed subject")
        cls.target = CourseOffering.objects.create(
            pk=fixed.TARGET,
            organization=cls.org,
            subject=subject,
            period=cls.period,
            group=cls.group,
            instructor=teacher,
            lesson_hours=30,
        )
        cls.map_identity("worker", 23, "auth.user", teacher.pk)
        cls.map_identity("lesson_subject", 5, "registrar.subject", subject.pk)
        task = TeachingTask.objects.create(
            pk=fixed.TASK, organization=cls.org, academic_year="2026/2027", chair=chair, status="amended", revision=0
        )
        cls.row = TeachingTaskRow.objects.create(
            pk=fixed.ROW,
            organization=cls.org,
            task=task,
            subject=subject,
            period=cls.period,
            specialty=parent,
            lecture_plan=15,
            lecture_total=0,
            seminar_plan=15,
            seminar_total=15,
            total_hours=15,
            union_count=0,
            credits="3",
        )
        cls.row.groups.set([cls.group, other])
        TeacherAssignment.objects.create(
            pk=fixed.ASSIGNMENT, organization=cls.org, row=cls.row, teacher=teacher, activity="seminar", hours=15
        )
        program = Program.objects.create(
            organization=cls.org, code="FIXED336", name="Fixed program", degree_level="bachelor"
        )
        curriculum = Curriculum.objects.create(organization=cls.org, program=program, admission_year=2026)
        cls.pairs = {}
        by_user = {uid: sid for sid, (uid, _) in fixed.PAIRS.items()}
        for uid in sorted(fixed.ROSTER):
            user = User.objects.create_user(
                pk=uid, username=f"bounded_{uid}", first_name=f"Student{uid}", last_name="Family"
            )
            user.profile.organization, user.profile.patronymic, user.profile.access_state = (
                cls.org,
                "İlkin QIZI",
                "active",
            )
            user.profile.save()
            Membership.objects.create(
                organization=cls.org, user=user, role=cls.org.roles.get(name="student"), scope_unit=cls.group
            )
            StudentAcademicRecord.objects.create(
                organization=cls.org,
                student=user,
                group=cls.group,
                program=program,
                curriculum=curriculum,
                admission_year=2026,
            )
            Enrollment.objects.create(organization=cls.org, offering=cls.target, student=user)
            if uid in by_user:
                cls.pairs[by_user[uid]] = (
                    uid,
                    bridge.identity_hash(user.first_name, user.last_name, user.profile.patronymic),
                )

    def setUp(self):
        MissingOnlyContentTests.setUp(self)
        self.raw = source_fixture()
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(fixed, "PAIRS", self.pairs))
        self.stack.enter_context(patch.object(fixed, "PAYLOAD_DIGEST", digest(self.raw)))

    def execute(self, *, apply=False, expected_baseline="", targets=None):
        return service.execute(
            data=validate_payload(self.raw, target_ids=[fixed.TARGET]),
            source_sha256=fixed.SOURCE_SHA,
            user=self.admin,
            organization=self.org,
            apply=apply,
            expected_baseline=expected_baseline,
        )

    def test_full_bounded_recovery_and_idempotency(self):
        self.assertEqual((len(self.raw["points"]), len(self.raw["students"])), (238, 41))
        dry = self.execute()
        self.assertEqual((dry["missing_lessons"], dry["missing_marks"]), (6, 102))
        self.assertEqual(dry["student_identity_unresolved"], 136)
        result = self.execute(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual((result["created_lessons"], result["created_marks"]), (6, 102))
        lessons = Lesson.objects.filter(offering=self.target)
        self.assertEqual(lessons.filter(kind="lecture").count(), 3)
        self.assertEqual(lessons.filter(kind="seminar").count(), 3)
        self.assertFalse(lessons.exclude(instructor_id=None, created_by_id=None).exists())
        self.assertFalse(LessonMark.objects.filter(lesson__offering=self.target).exclude(entered_by_id=None).exists())
        self.assertEqual(LessonMark.objects.filter(lesson__offering=self.target, status="absent").count(), 3)
        self.assertEqual(self.execute()["missing_marks"], 0)
        self.assertEqual(self.execute(apply=True, expected_baseline=self.execute()["baseline"])["already_done"], 1)
        audit = AuditLog.objects.get(resource_type=RESOURCE)
        self.assertEqual(audit.new_values["reviewed_identity_evidence"]["identity_proof_sha256"], fixed.PROOF_SHA)
        self.assertEqual(audit.new_values["reviewed_identity_evidence"]["current_assignment"]["lecture_hours"], 0)

    def test_official_joint_partner_cells_prevent_second_copy(self):
        from apps.legacy_import.services.reviewed_content_plan import build
        from apps.legacy_import.services.reviewed_content_state import CurrentState

        OrgUnit.objects.filter(pk=fixed.OTHER_GROUP).update(slug="336-f1")
        OrgUnit.objects.create(
            organization=self.org,
            name="Different migrated group936",
            slug="myedu-grp-936",
            unit_type="group",
            parent=self.target.group.parent,
        )
        canonical = CourseOffering.objects.create(
            organization=self.org,
            subject=self.target.subject,
            period=self.target.period,
            group_id=fixed.OTHER_GROUP,
            instructor=self.target.instructor,
            lesson_hours=30,
        )
        data = validate_payload(self.raw, target_ids=[fixed.TARGET])
        decision = build(CurrentState(data, actor=self.admin))
        self.assertEqual(len(decision.marks), 102)
        enrollments = {
            uid: Enrollment.objects.create(organization=self.org, offering=canonical, student_id=uid)
            for uid, _ in self.pairs.values()
        }
        for lesson in decision.lessons.values():
            lesson.offering = canonical
            lesson.save(force_insert=True)
        for mark in decision.marks:
            mark.enrollment = enrollments[mark.enrollment.student_id]
        LessonMark.objects.bulk_create(decision.marks)
        existing_ids = set(LessonMark.objects.filter(lesson__offering=canonical).values_list("pk", flat=True))
        dry = self.execute()
        self.assertEqual(dry["existing_identical_cells"], 102)
        self.assertEqual((dry["missing_marks"], dry["missing_lessons"]), (0, 0))
        result = self.execute(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(result["already_done"], 1)
        self.assertFalse(Lesson.objects.filter(offering=self.target).exists())
        self.assertEqual(
            set(LessonMark.objects.filter(lesson__offering=canonical).values_list("pk", flat=True)), existing_ids
        )
        mark = LessonMark.objects.filter(lesson__offering=canonical, status="present").first()
        mark.score = 3 if mark.score != 3 else 4
        mark.save(update_fields=["score"])
        changed = self.execute()
        self.assertEqual(changed["existing_conflicting_cells_kept"], 1)
        self.assertEqual(changed["missing_marks"], 0)
        self.assertNotEqual(changed["baseline"], dry["baseline"])

    def test_az_case_and_suffix_are_bounded(self):
        self.assertEqual(
            bridge.identity_hash("AİŞƏ", "YUSİFOVA", "İLKİN QIZI"), bridge.identity_hash("Aişə", "Yusifova", "İlkin")
        )
        self.assertNotEqual(bridge.identity_hash("A", "Imanova", "E"), bridge.identity_hash("A", "İMANOVA", "E"))
        self.assertNotEqual(bridge.identity_hash("A", "B", "Elsəvər"), bridge.identity_hash("A", "B", "ELSEVƏR QIZI"))
        self.assertNotEqual(bridge.identity_hash("A", "B", "Qızı İlkin"), bridge.identity_hash("A", "B", "İlkin"))

    def test_existing_conflict_and_named_authors_are_preserved(self):
        uid = next(iter(self.pairs.values()))[0]
        lesson = Lesson.objects.create(
            organization=self.org,
            offering=self.target,
            date="2026-09-21",
            start_time="11:50",
            kind="seminar",
            hours=2,
            instructor=self.teacher,
            created_by=self.admin,
        )
        mark = LessonMark.objects.create(
            organization=self.org,
            lesson=lesson,
            enrollment=Enrollment.objects.get(offering=self.target, student_id=uid),
            status="present",
            score=2,
            entered_by=self.admin,
        )
        result = self.apply()
        self.assertEqual(result["created_marks"], 101)
        mark.refresh_from_db()
        lesson.refresh_from_db()
        self.assertEqual(
            (mark.score, mark.entered_by_id, lesson.instructor_id, lesson.created_by_id),
            (2, self.admin.pk, self.teacher.pk, self.admin.pk),
        )

    def test_late_identity_drift_is_detected(self):
        dry = self.execute()
        uid = next(iter(self.pairs.values()))[0]
        get_user_model().objects.filter(pk=uid).update(first_name="changed")
        with self.assertRaisesMessage(ContentError, "identity_hash_changed"):
            self.execute(apply=True, expected_baseline=dry["baseline"])
        self.assertFalse(Lesson.objects.filter(offering=self.target).exists())

    def test_late_unmatched_profile_drift_changes_baseline(self):
        dry = self.execute()
        get_user_model().objects.filter(pk=9068).update(last_name="still unique")
        with self.assertRaisesMessage(ContentError, "fresh_live_baseline_changed"):
            self.execute(apply=True, expected_baseline=dry["baseline"])

    def test_duplicate_canonical_roster_identity_rejected(self):
        uid = next(iter(self.pairs.values()))[0]
        user = get_user_model().objects.get(pk=uid)
        get_user_model().objects.filter(pk=9068).update(first_name=user.first_name, last_name=user.last_name)
        with self.assertRaisesMessage(ContentError, "identity_not_unique"):
            self.execute()

    def test_wrong_tenant_archive_inactive_and_missing_current_group_rejected(self):
        uid = next(iter(self.pairs.values()))[0]
        profile = get_user_model().objects.get(pk=uid).profile
        for field, value in (("organization_id", None), ("access_state", "archived")):
            with transaction.atomic():
                setattr(profile, field, value)
                profile.save()
                with self.assertRaisesMessage(ContentError, "reviewed_336_"):
                    self.execute()
                transaction.set_rollback(True)
            profile.refresh_from_db()
        get_user_model().objects.filter(pk=uid).update(is_active=False)
        with self.assertRaisesMessage(ContentError, "tenant_or_activity_changed"):
            self.execute()
        get_user_model().objects.filter(pk=uid).update(is_active=True)
        Membership.objects.filter(user_id=uid).update(is_active=False)
        with self.assertRaisesMessage(ContentError, "active_membership_missing"):
            self.execute()
        Membership.objects.filter(user_id=uid).update(is_active=True)
        StudentAcademicRecord.objects.filter(student_id=uid).update(is_active=False)
        with self.assertRaisesMessage(ContentError, "student_current_group_changed"):
            self.execute()

    def test_roster_and_teacher_ledger_conflicts_rejected(self):
        original = bridge._query

        def absent_teacher_ledger(label, **kwargs):
            query = original(label, **kwargs)
            return query.none() if label == "legacy_import.LegacyEntityMap" else query

        with patch.object(bridge, "_query", side_effect=absent_teacher_ledger):
            with self.assertRaisesMessage(ContentError, "teacher_ledger_required"):
                self.execute()
        uid = next(iter(self.pairs.values()))[0]
        Enrollment.objects.filter(offering=self.target, student_id=uid).update(status="withdrawn")
        with self.assertRaisesMessage(ContentError, "roster_changed"):
            self.execute()

    def test_student_ledger_and_source_tamper_rejected(self):
        sid = next(iter(self.pairs))
        self.map_identity("student", sid, "auth.user", self.admin.pk)
        with self.assertRaisesMessage(ContentError, "student_ledger_conflict"):
            self.execute()
        self.raw["points"][0]["point"] = "10"
        with self.assertRaisesMessage(ContentError, "exact_source"):
            self.execute()

    def test_hash_collision_and_workload_drift_rejected(self):
        pairs = dict(self.pairs)
        keys = list(pairs)
        pairs[keys[1]] = (pairs[keys[1]][0], pairs[keys[0]][1])
        with patch.object(fixed, "PAIRS", pairs):
            with self.assertRaisesMessage(ContentError, "hash_collision"):
                self.execute()
        self.row.seminar_total = 16
        self.row.save()
        with self.assertRaisesMessage(ContentError, "official_row_changed"):
            self.execute()

    def test_failure_rolls_back_all_cells_and_audit(self):
        dry = self.execute()
        with patch.object(service, "_verify_created", side_effect=ContentError("forced rollback")):
            with self.assertRaisesMessage(ContentError, "forced rollback"):
                self.execute(apply=True, expected_baseline=dry["baseline"])
        self.assertFalse(Lesson.objects.filter(offering=self.target).exists())
        self.assertFalse(AuditLog.objects.filter(resource_type=RESOURCE).exists())
        self.assertFalse(Enrollment.objects.filter(offering=self.target).exclude(absence_hours=0).exists())
