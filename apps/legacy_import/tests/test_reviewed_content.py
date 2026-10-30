"""Missing-only current-semester recovery: source proof, conflicts and atomicity."""

import copy
import datetime
import hashlib
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import SimpleTestCase, TestCase, override_settings

from apps.accounts.models import UserProfile
from apps.audit.models import AuditLog
from apps.legacy_import.models import LegacyEntityMap
from apps.legacy_import.services import reviewed_content as service
from apps.legacy_import.services.ledger import create_run, start_run
from apps.legacy_import.services.reviewed_content_contract import ContentError, load_payload, validate_payload
from apps.legacy_import.services.reviewed_content_spec import JOURNAL_GROUPS, ORG, RESOURCE, TARGETS
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonMark, Subject
from core.rls import apply_rls_request_context, reset_rls_context

PAIR = [pk for pk, spec in TARGETS.items() if spec["journal_id"] == 14565]
PAIR.sort()
A, B = PAIR
SPEC = TARGETS[A]


def payload():
    groups = [TARGETS[pk]["legacy_group_id"] for pk in PAIR]
    return {
        "format": "reviewed-journal-content/1",
        "organization_id": ORG,
        "academic_year": "2026/2027",
        "semester": {"id": 14, "name": "2026/2027 Payız", "type": "autumn"},
        "until": "2026-10-30",
        "targets": PAIR,
        "journals": [
            {
                "id": SPEC["journal_id"],
                "uniqid": SPEC["journal_uniqid"],
                "lesson_id": SPEC["legacy_subject_id"],
                "semestr": 14,
                "groups_id": list(JOURNAL_GROUPS[14565]),
                "teacher_id": SPEC["legacy_teacher_id"],
                "fake": 0,
                "sonra_sil": 0,
                "active": 1,
            }
        ],
        "dates": [{"id": 1, "journal_id": 14565, "month": 10, "day": 26, "time": "10:00"}],
        "workers": [
            {"id": SPEC["legacy_teacher_id"], "first_name": "Alim", "last_name": "Həsənli", "father_name": "Kərim"}
        ],
        "excuse_windows": [],
        "students": [{"id": 501, "group_id": groups[0]}, {"id": 502, "group_id": groups[1]}],
        "points": [
            {
                "id": sid,
                "journal_uniqid": SPEC["journal_uniqid"],
                "month_id": "10",
                "day_number": "26",
                "student_id": sid,
                "point": "9",
                "time": "10:00:00",
                "lab": 0,
                "sem_muh": 0,
                "excusable": 0,
                "update_counter": 1,
                "updated_at": "2026-10-26 15:00:00",
            }
            for sid in (501, 502)
        ],
    }


class SourceContractTests(SimpleTestCase):
    def test_exact_source_private_file_sha_and_scope(self):
        data = payload()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "source.json"
            path.write_text(json.dumps(data))
            path.chmod(0o600)
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(len(load_payload(path, sha, PAIR)["points"]), 2)
            with self.assertRaisesMessage(ContentError, "sha256_mismatch"):
                load_payload(path, "0" * 64, PAIR)
            path.chmod(0o644)
            with self.assertRaisesMessage(ContentError, "private_regular"):
                load_payload(path, sha, PAIR)
        data["journals"][0]["groups_id"] = [9999]
        with self.assertRaisesMessage(ContentError, "group_relationship"):
            validate_payload(data, target_ids=PAIR)

    def test_unreviewed_source_target_and_credentials_rejected(self):
        data = payload()
        with self.assertRaisesMessage(ContentError, "target_allowlist"):
            validate_payload(data, target_ids=["00000000-0000-0000-0000-000000000000"])
        data["password"] = "not_allowed"
        with self.assertRaisesMessage(ContentError, "payload_fields"):
            validate_payload(data, target_ids=PAIR)

    def test_noncalendar_component_tokens_never_enter_ordinary_score_conversion(self):
        from apps.legacy_import.services.reviewed_content_plan import build

        for token in ("1", "k1", "im", "ga"):
            data = payload()
            data["points"] = data["points"][:1]
            data["points"][0]["month_id"] = token
            data["until_date"] = datetime.date(2026, 10, 30)
            period = SimpleNamespace(start_date=datetime.date(2026, 9, 1), end_date=datetime.date(2027, 1, 31))
            state = SimpleNamespace(
                data=data, selected={A: TARGETS[A]}, selected_offerings={A: SimpleNamespace(period=period)}
            )
            with patch(
                "apps.legacy_import.services.reviewed_content_plan.mark_value",
                side_effect=AssertionError("componentconverted"),
            ):
                decision = build(state)
            self.assertEqual(decision.counts["noncalendar_cells_skipped"], 1)
            self.assertEqual(decision.marks, [])

    def test_exact_zero_seconds_time_is_same_slot_but_nonzero_or_timezone_is_not(self):
        from apps.legacy_import.services.reviewed_content_plan import _time

        self.assertEqual(_time("10:00:00"), _time("10:00"))
        for value in ("10:00:01", "10:00:00.1", "10:00:00.0000001", "10:00+04:00", "10:0", "10", "1000", None, "bad"):
            self.assertIsNone(_time(value))


@override_settings(RLS_TRANSACTION_SCOPED=True)
class MissingOnlyContentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.admin = User.objects.create_superuser(username="reviewed_source_operator")
        cls.org = Organization.objects.create(pk=ORG, name="QKU", slug="qku", org_type="university", owner=cls.admin)
        faculty = OrgUnit.objects.create(organization=cls.org, name="Məktəb", slug="rc-faculty", unit_type="faculty")
        cls.specialty = OrgUnit.objects.create(
            organization=cls.org, name="Maliyyə", slug="rc-spec", unit_type="specialty", parent=faculty
        )
        cls.groups = {}
        for index, pk in enumerate(PAIR):
            cls.groups[pk] = OrgUnit.objects.create(
                pk=TARGETS[pk]["group_id"],
                organization=cls.org,
                name=f"536MU{index+1}",
                slug=f"myedu-grp-{TARGETS[pk]['legacy_group_id']}" if pk == A else f"rc-group-{index}",
                unit_type="group",
                parent=cls.specialty,
            )
        cls.period = AcademicPeriod.objects.create(
            pk=SPEC["period_id"],
            organization=cls.org,
            name="Payız",
            academic_year="2026/2027",
            period_type="semester",
            start_date="2026-09-01",
            end_date="2027-01-31",
            is_current=True,
        )
        cls.teacher = User.objects.create_user(
            pk=SPEC["teacher_id"], username="rc_teacher", first_name="Alim", last_name="Həsənli"
        )
        cls.teacher.profile.organization, cls.teacher.profile.patronymic = cls.org, "Kərim"
        cls.teacher.profile.save(update_fields=["organization", "patronymic"])
        Membership.objects.create(
            organization=cls.org,
            user=cls.teacher,
            role=cls.org.roles.get(name="teacher"),
            scope_unit=cls.specialty,
            is_primary=True,
        )
        cls.subject = Subject.objects.create(
            pk=SPEC["subject_id"], organization=cls.org, code="RC-SOURCE", name="Mühasibatlığın əsasları"
        )
        cls.offerings = {
            pk: CourseOffering.objects.create(
                pk=pk,
                organization=cls.org,
                subject=cls.subject,
                period=cls.period,
                group=cls.groups[pk],
                instructor=cls.teacher,
                lesson_hours=60,
            )
            for pk in PAIR
        }
        cls.source_run = create_run(
            organization=cls.org,
            actor=cls.admin,
            authorize=lambda **kwargs: True,
            source_system="myedu_mariadb",
            snapshot_sha256="a" * 64,
            snapshot_size_bytes=1,
            source_row_count=100,
            schema_version="test-v1",
            transform_version="test-v1",
            mode="rehearsal",
        )
        cls.source_run = start_run(run_id=cls.source_run.pk, actor=cls.admin, authorize=lambda **kwargs: True)
        cls.source_students, cls.enrollments = {}, {}
        for sid, pk in zip((501, 502), PAIR):
            user = User.objects.create_user(username=f"rc_student_{sid}")
            user.profile.organization = cls.org
            user.profile.save(update_fields=["organization"])
            Membership.objects.create(
                organization=cls.org,
                user=user,
                role=cls.org.roles.get(name="student"),
                scope_unit=cls.groups[pk],
                is_primary=True,
            )
            cls.source_students[sid] = user
            cls.enrollments[sid] = Enrollment.objects.create(
                organization=cls.org, offering=cls.offerings[pk], student=user
            )
            cls.map_identity("student", sid, "auth.user", user.pk)
        cls.map_identity("group_unit", TARGETS[B]["legacy_group_id"], "organizations.orgunit", cls.groups[B].pk)
        cls.map_identity("lesson_subject", SPEC["legacy_subject_id"], "registrar.subject", cls.subject.pk)
        cls.map_identity("worker", SPEC["legacy_teacher_id"], "auth.user", cls.teacher.pk)

    @classmethod
    def map_identity(cls, entity, source, label, target):
        return LegacyEntityMap.objects.create(
            organization=cls.org,
            source_system="myedu_mariadb",
            entity_type=entity,
            legacy_pk=str(source),
            target_model_label=label,
            target_pk=str(target),
            state="migrated",
            source_row_hash="b" * 64,
            transform_version="test-v1",
            created_run=cls.source_run,
        )

    def setUp(self):
        apply_rls_request_context(user_id=self.admin.pk, org_id=ORG, bypass=False)
        self.raw = payload()
        self.clock = patch(
            "apps.legacy_import.services.reviewed_content.timezone.localdate", return_value=datetime.date(2026, 10, 30)
        )
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def tearDown(self):
        reset_rls_context()

    def execute(self, *, apply=False, expected_baseline="", targets=PAIR):
        data = validate_payload(self.raw, target_ids=targets)
        return service.execute(
            data=data,
            source_sha256="c" * 64,
            user=self.admin,
            organization=self.org,
            apply=apply,
            expected_baseline=expected_baseline,
        )

    def apply(self, **kwargs):
        dry = self.execute(**kwargs)
        return self.execute(apply=True, expected_baseline=dry["baseline"], **kwargs)

    def existing(self, *, sid=501, offering=A, score=5, instructor=None, entered_by=None, kind="seminar"):
        lesson = Lesson.objects.create(
            organization=self.org,
            offering=self.offerings[offering],
            date="2026-10-26",
            start_time="10:00",
            kind=kind,
            hours=2,
            instructor=instructor,
        )
        enrollment = self.enrollments[sid]
        if str(enrollment.offering_id) != offering:
            enrollment = Enrollment.objects.create(
                organization=self.org, offering=self.offerings[offering], student=self.source_students[sid]
            )
        return LessonMark.objects.create(
            organization=self.org,
            lesson=lesson,
            enrollment=enrollment,
            status="present",
            score=score,
            entered_by=entered_by,
        )

    def test_default_audit_reads_actual_cells_without_any_write(self):
        def readonly(execute, sql, params, many, context):
            self.assertFalse(sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")))
            return execute(sql, params, many, context)

        with connection.execute_wrapper(readonly):
            result = self.execute()
        self.assertEqual((result["missing_lessons"], result["missing_marks"]), (2, 2))
        self.assertFalse(Lesson.objects.exists())
        self.assertFalse(AuditLog.objects.filter(resource_type=RESOURCE).exists())

    def test_apply_adds_only_missing_cells_and_repeat_is_idempotent(self):
        roster = list(Enrollment.objects.order_by("pk").values())
        result = self.apply()
        self.assertEqual((result["created_lessons"], result["created_marks"]), (2, 2))
        self.assertEqual(list(Enrollment.objects.order_by("pk").values()), roster)
        self.assertFalse(Lesson.objects.exclude(instructor__isnull=True, created_by__isnull=True).exists())
        self.assertFalse(LessonMark.objects.exclude(entered_by__isnull=True).exists())
        again = self.apply()
        self.assertEqual(again["already_done"], 1)
        self.assertEqual((Lesson.objects.count(), LessonMark.objects.count()), (2, 2))

    def test_current_nonempty_conflict_and_known_authors_are_preserved(self):
        mark = self.existing(instructor=self.teacher, entered_by=self.teacher)
        before = (mark.score, mark.lesson.instructor_id, mark.entered_by_id)
        result = self.apply()
        mark.refresh_from_db()
        self.assertEqual((mark.score, mark.lesson.instructor_id, mark.entered_by_id), before)
        self.assertEqual(result["existing_conflicting_cells_kept"], 1)
        self.assertEqual(result["created_marks"], 1)

    def test_existing_identical_cell_keeps_null_authors_and_is_not_duplicated(self):
        mark = self.existing(score=9)
        result = self.apply()
        mark.refresh_from_db()
        self.assertIsNone(mark.entered_by_id)
        self.assertIsNone(mark.lesson.instructor_id)
        self.assertEqual(result["existing_identical_cells"], 1)
        self.assertEqual(LessonMark.objects.count(), 2)

    def test_stale_baseline_refuses_current_teacher_change(self):
        preview = self.execute()
        self.offerings[A].lesson_hours = 65
        self.offerings[A].save(update_fields=["lesson_hours"])
        with self.assertRaisesMessage(ContentError, "baseline_changed"):
            self.execute(apply=True, expected_baseline=preview["baseline"])
        self.assertFalse(LessonMark.objects.exists())

    def test_late_guard_failure_rolls_back_all_inserts_and_audit(self):
        with patch("apps.legacy_import.services.reviewed_content._verify_created", side_effect=ContentError("late")):
            with self.assertRaisesMessage(ContentError, "late"):
                self.apply()
        self.assertEqual((Lesson.objects.count(), LessonMark.objects.count()), (0, 0))
        self.assertFalse(AuditLog.objects.filter(resource_type=RESOURCE).exists())

    def test_shared_source_existing_mark_in_other_child_is_not_copied(self):
        self.existing(offering=B, score=9)
        result = self.apply()
        self.assertEqual(result["existing_identical_cells"], 1)
        self.assertFalse(
            LessonMark.objects.filter(lesson__offering_id=A, enrollment__student=self.source_students[501]).exists()
        )
        self.assertEqual(result["created_marks"], 1)

    def test_unselected_child_never_receives_new_cells(self):
        result = self.apply(targets=[A])
        self.assertEqual(result["created_marks"], 1)
        self.assertEqual(result["source_cell_belongs_to_unselected_family_slice"], 1)
        self.assertFalse(LessonMark.objects.filter(lesson__offering_id=B).exists())

    def test_unknown_student_is_counted_and_no_account_or_enrollment_created(self):
        self.raw["points"][0]["student_id"] = 9999
        self.raw["students"][0]["id"] = 9999
        before = (get_user_model().objects.count(), Enrollment.objects.count())
        result = self.apply()
        self.assertEqual(result["student_identity_unresolved"], 1)
        self.assertEqual((get_user_model().objects.count(), Enrollment.objects.count()), before)

    def test_foreign_student_profile_is_rejected_even_if_mapping_points_there(self):
        other = Organization.objects.create(name="Foreign", slug="rc-foreign", org_type="university", owner=self.admin)
        user = get_user_model().objects.create_user(username="rc_foreign_student")
        UserProfile.objects.filter(user=user).update(organization=other)
        self.map_identity("student", 9999, "auth.user", user.pk)
        self.raw["points"][0]["student_id"] = 9999
        self.raw["students"][0]["id"] = 9999
        result = self.apply()
        self.assertEqual(result["student_foreign_profile_rejected"], 1)
        self.assertFalse(Enrollment.objects.filter(student=user, organization=self.org).exists())

    def test_missing_roster_is_not_silently_populated(self):
        self.enrollments[501].delete()
        result = self.apply()
        self.assertEqual(result["no_existing_target_enrollment"], 1)
        self.assertFalse(Enrollment.objects.filter(student=self.source_students[501]).exists())

    def test_ambiguous_child_membership_skips_without_first_slice_fallback(self):
        Enrollment.objects.create(organization=self.org, offering=self.offerings[B], student=self.source_students[501])
        self.raw["students"][0]["group_id"] = 9999
        result = self.apply()
        self.assertEqual(result["ambiguous_enrollment_slice"], 1)
        self.assertFalse(LessonMark.objects.filter(enrollment__student=self.source_students[501]).exists())

    def test_special_sem_muh3_never_uses_ordinary_grade_conversion(self):
        self.raw["points"][0]["sem_muh"] = 3
        result = self.apply()
        self.assertEqual(result["special_deferred_targets"], 2)
        self.assertEqual(result["missing_marks"], 0)
        self.assertFalse(Lesson.objects.exists())

    def test_invalid_nonzero_seconds_are_not_guessed(self):
        self.raw["points"][0]["time"] = "10:00:30"
        result = self.apply()
        self.assertEqual(result["invalid_time_cells"], 1)
        self.assertEqual(result["created_marks"], 1)

    def test_existing_lesson_kind_is_preserved_when_source_disagrees(self):
        Lesson.objects.create(
            organization=self.org,
            offering=self.offerings[A],
            date="2026-10-26",
            start_time="10:00",
            kind="lecture",
            hours=2,
        )
        result = self.apply()
        self.assertEqual(result["existing_lesson_kind_conflicts_kept"], 1)
        self.assertEqual(Lesson.objects.filter(offering_id=A).get().kind, "lecture")

    def test_absence_only_source_does_not_create_phantom_lesson(self):
        for point in self.raw["points"]:
            point["point"] = "qb"
        result = self.apply()
        self.assertEqual(result["new_absence_only_cells_skipped"], 2)
        self.assertFalse(Lesson.objects.exists())

    def test_excused_source_window_does_not_turn_into_unexcused_absence(self):
        self.raw["points"][0]["point"] = "qb"
        self.raw["excuse_windows"] = [
            {"id": 1, "student_id": 501, "allowed_date_start": "2026-10-25", "allowed_date_end": "2026-10-27"}
        ]
        self.apply()
        mark = LessonMark.objects.get(enrollment=self.enrollments[501])
        self.assertEqual(mark.status, "excused")
        self.enrollments[501].refresh_from_db()
        self.assertEqual(self.enrollments[501].absence_hours, 0)

    def test_absence_without_attested_window_source_is_deferred(self):
        self.raw.pop("excuse_windows")
        self.raw["points"][0]["point"] = "qb"
        result = self.apply()
        self.assertEqual(result["absence_source_policy_unattested"], 1)
        self.assertFalse(LessonMark.objects.filter(enrollment=self.enrollments[501]).exists())

    def test_absence_cache_recomputed_only_for_existing_target_enrollment(self):
        Lesson.objects.create(
            organization=self.org,
            offering=self.offerings[A],
            date="2026-10-26",
            start_time="10:00",
            kind="seminar",
            hours=2,
        )
        self.raw["points"][0]["point"] = "qb"
        result = self.apply()
        self.assertEqual(result["created_marks"], 2)
        self.enrollments[501].refresh_from_db()
        self.assertEqual(self.enrollments[501].absence_hours, 2)
        self.assertEqual(self.enrollments[501].status, "enrolled")

    def test_wrong_teacher_patronymic_refuses_before_any_content_write(self):
        self.raw["workers"][0]["father_name"] = "Başqa ata"
        with self.assertRaisesMessage(ContentError, "teacher_full_identity"):
            self.apply()
        self.assertFalse(Lesson.objects.exists())

    def test_wrong_subject_or_group_current_fk_refuses(self):
        self.offerings[A].is_active = False
        self.offerings[A].save(update_fields=["is_active"])
        with self.assertRaisesMessage(ContentError, "activity_changed"):
            self.apply()
        self.assertFalse(Lesson.objects.exists())

    def test_grade_zero_is_preserved_as_numeric_source_value(self):
        self.raw["points"][0]["point"] = "0"
        self.apply()
        self.assertEqual(LessonMark.objects.get(enrollment=self.enrollments[501]).score, 0)

    def test_source_update_winner_is_not_first_cell_or_average(self):
        newer = copy.deepcopy(self.raw["points"][0])
        newer.update(id=700, point="10", update_counter=2)
        self.raw["points"].append(newer)
        self.apply()
        self.assertEqual(LessonMark.objects.get(enrollment=self.enrollments[501]).score, 10)
