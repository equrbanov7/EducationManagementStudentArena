"""Four blank cells: existing writer, source pins, contrary evidence and exact undo."""

import copy
import datetime
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase, override_settings

from apps.audit.models import AuditLog
from apps.legacy_import.models import LegacyEntityMap
from apps.legacy_import.services import reviewed_content as service
from apps.legacy_import.services import reviewed_content_four as four
from apps.legacy_import.services import reviewed_content_four_spec as fixed
from apps.legacy_import.services.ledger import create_run, start_run
from apps.legacy_import.services.reviewed_content_contract import ContentError, validate_payload
from apps.legacy_import.services.reviewed_content_four_undo import undo
from apps.legacy_import.services.reviewed_content_spec import ORG
from apps.legacy_import.services.reviewed_content_state import digest
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonMark, Subject
from core.rls import apply_rls_request_context, reset_rls_context


class FourCellsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.actor = User.objects.create_superuser("four_operator")
        cls.org = Organization.objects.create(id=ORG, slug="qku", name="QKU", org_type="university", owner=cls.actor)
        cls.actor.profile.organization = cls.org
        cls.actor.profile.save(update_fields=["organization"])
        cls.period = AcademicPeriod.objects.create(
            id=fixed.PERIOD,
            organization=cls.org,
            name="Payız",
            academic_year="2026/2027",
            period_type="semester",
            start_date="2026-09-01",
            end_date="2027-01-31",
            is_current=True,
        )
        cls.source_run = create_run(
            organization=cls.org,
            actor=cls.actor,
            authorize=lambda **kw: True,
            source_system="myedu_mariadb",
            snapshot_sha256="a" * 64,
            snapshot_size_bytes=1,
            source_row_count=10,
            schema_version="test",
            transform_version="test",
            mode="rehearsal",
        )
        cls.source_run = start_run(run_id=cls.source_run.pk, actor=cls.actor, authorize=lambda **kw: True)
        cls.offerings = {}
        cls.raw = {
            "format": "reviewed-journal-content/1",
            "organization_id": ORG,
            "academic_year": "2026/2027",
            "semester": {"id": 14, "name": "2026/2027 Payız", "type": "autumn"},
            "until": "2026-11-01",
            "targets": sorted(fixed.TARGETS),
            "journals": [],
            "points": [],
            "dates": [],
            "workers": [],
            "students": [],
            "excuse_windows": [],
        }
        for index, (oid, spec) in enumerate(fixed.TARGETS.items()):
            teacher = User.objects.create_user(
                id=spec["teacher_id"],
                username="four_teacher" + str(index),
                first_name="Ad",
                last_name="Soyad" + str(index),
            )
            teacher.profile.organization, teacher.profile.patronymic = cls.org, "Ata"
            teacher.profile.save(update_fields=["organization", "patronymic"])
            group = OrgUnit.objects.create(
                id=spec["group_id"],
                organization=cls.org,
                name="G" + str(index),
                slug="four-group" + str(index),
                unit_type="group",
            )
            Membership.objects.create(
                organization=cls.org,
                user=teacher,
                role=cls.org.roles.get(name="teacher"),
                scope_unit=group,
                is_primary=True,
            )
            subject = Subject.objects.create(
                id=spec["subject_id"], organization=cls.org, code="F" + str(index), name="Fənn" + str(index)
            )
            cls.offerings[oid] = CourseOffering.objects.create(
                id=oid,
                organization=cls.org,
                period=cls.period,
                group=group,
                subject=subject,
                instructor=teacher,
                lesson_hours=30,
            )
            for entity, source, label, target in [
                ("worker", spec["legacy_teacher_id"], "auth.user", teacher.pk),
                ("group_unit", spec["legacy_group_id"], "organizations.orgunit", group.pk),
                ("lesson_subject", spec["legacy_subject_id"], "registrar.subject", subject.pk),
            ]:
                cls.mapping(entity, source, label, target)
            cls.raw["workers"].append(
                {
                    "id": spec["legacy_teacher_id"],
                    "first_name": teacher.first_name,
                    "last_name": teacher.last_name,
                    "father_name": "Ata",
                }
            )
            cls.raw["journals"].append(
                {
                    "id": spec["journal_id"],
                    "uniqid": spec["journal_uniqid"],
                    "lesson_id": spec["legacy_subject_id"],
                    "semestr": 14,
                    "teacher_id": spec["legacy_teacher_id"],
                    "groups_id": [spec["legacy_group_id"]],
                    "fake": 0,
                    "sonra_sil": 0,
                    "active": 1,
                }
            )
            c = next(c for c in fixed.CASES.values() if c[0] == oid)
            cls.raw["dates"].append(
                {"id": index + 1, "journal_id": spec["journal_id"], "month": "10", "day": c[5][-2:], "time": c[6][:5]}
            )
            Lesson.objects.create(
                id=c[1],
                organization=cls.org,
                offering=cls.offerings[oid],
                date=c[5],
                start_time=c[6],
                kind="seminar",
                hours=2,
                created_by=teacher if index else None,
            )
        for point, c in fixed.CASES.items():
            user = User.objects.create_user(id=c[4], username="four_student" + str(point))
            user.profile.organization = cls.org
            user.profile.save(update_fields=["organization"])
            Membership.objects.create(
                organization=cls.org,
                user=user,
                role=cls.org.roles.get(name="student"),
                scope_unit=cls.offerings[c[0]].group,
                is_primary=True,
            )
            cls.mapping("student", c[3], "auth.user", user.pk)
            Enrollment.objects.create(id=c[2], organization=cls.org, offering=cls.offerings[c[0]], student=user)
            spec = fixed.TARGETS[c[0]]
            cls.raw["students"].append({"id": c[3], "group_id": spec["legacy_group_id"]})
            cls.raw["points"].append(
                {
                    "id": point,
                    "journal_uniqid": spec["journal_uniqid"],
                    "month_id": "10",
                    "day_number": c[5][-2:],
                    "student_id": c[3],
                    "point": "qb",
                    "time": c[6],
                    "lab": 0,
                    "sem_muh": 0,
                    "excusable": 0,
                    "update_counter": 0,
                    "updated_at": "",
                }
            )

    @classmethod
    def mapping(cls, entity, source, label, target):
        return LegacyEntityMap.objects.create(
            organization=cls.org,
            source_system="myedu_mariadb",
            entity_type=entity,
            legacy_pk=str(source),
            target_model_label=label,
            target_pk=str(target),
            state="migrated",
            source_row_hash="b" * 64,
            transform_version="test",
            created_run=cls.source_run,
        )

    def setUp(self):
        apply_rls_request_context(user_id=self.actor.pk, org_id=ORG, bypass=False)
        self.raw = copy.deepcopy(self.raw)
        self.pin = patch.object(fixed, "PAYLOAD_DIGEST", digest(self.raw))
        self.pin.start()
        self.addCleanup(self.pin.stop)
        self.addCleanup(reset_rls_context)
        self.clock = patch.object(service.timezone, "localdate", return_value=datetime.date(2026, 11, 1))
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def execute(self, **kwargs):
        return service.execute(
            data=validate_payload(self.raw, target_ids=sorted(fixed.TARGETS)),
            source_sha256=fixed.SOURCE_SHA,
            user=self.actor,
            organization=self.org,
            **kwargs,
        )

    def apply(self):
        return self.execute(apply=True, expected_baseline=self.execute()["baseline"])

    def undo(self, batch, **kwargs):
        return undo(
            data=validate_payload(self.raw, target_ids=sorted(fixed.TARGETS)),
            source_sha256=fixed.SOURCE_SHA,
            user=self.actor,
            organization=self.org,
            batch=batch,
            **kwargs,
        )

    def test_four_existing_cells_only_both_rls_repeat_null_authors_and_exact_undo(self):
        for mode in [False, True]:
            with self.subTest(mode=mode), override_settings(RLS_TRANSACTION_SCOPED=mode), transaction.atomic():
                with self.captureOnCommitCallbacks(execute=True):
                    result = self.apply()
                self.assertEqual((result["created_lessons"], result["created_marks"]), (0, 4))
                self.assertEqual(Lesson.objects.count(), 2)
                self.assertEqual(LessonMark.objects.filter(status="absent", score=None, entered_by=None).count(), 4)
                self.assertEqual(set(Enrollment.objects.values_list("absence_hours", flat=True)), {2})
                self.assertEqual(self.apply()["already_done"], 1)
                dry = self.undo(result["batch"])
                done = self.undo(result["batch"], apply=True, expected_baseline=dry["baseline"])
                self.assertEqual(done["deleted_marks"], 4)
                self.assertEqual(LessonMark.objects.count(), 0)
                self.assertEqual(set(Enrollment.objects.values_list("absence_hours", flat=True)), {0})
                self.assertEqual(self.undo(result["batch"])["already_undone"], 1)
                with self.assertRaisesMessage(ContentError, "contrary_clear_delete"):
                    self.apply()
                transaction.set_rollback(True)

    def test_source_tampering_partial_targets_and_typed_ledger_missing_or_contradicting_hold(self):
        self.raw["points"][0]["point"] = "0"
        with self.assertRaisesMessage(ContentError, "exact_source"):
            self.execute()
        self.raw["points"][0]["point"] = "qb"
        original = four.fixed_four_recovery_history

        def missing_row(**kwargs):
            history = original(**kwargs)
            history["four_cell_history_ledger"] = [
                r
                for r in history["four_cell_history_ledger"]
                if not (r["entity_type"] == "worker" and r["legacy_pk"] == "23")
            ]
            return history

        with patch.object(four, "fixed_four_recovery_history", side_effect=missing_row):
            with self.assertRaisesMessage(ContentError, "ten_typed_identity"):
                self.execute()

        def contradictory_row(**kwargs):
            history = original(**kwargs)
            for row in history["four_cell_history_ledger"]:
                if row["entity_type"] == "worker" and row["legacy_pk"] == "23":
                    row["target_pk"] = "8163"
            return history

        with patch.object(four, "fixed_four_recovery_history", side_effect=contradictory_row):
            with self.assertRaisesMessage(ContentError, "typed_source_ledger_conflict"):
                self.execute()

    def test_contrary_clear_delete_and_malformed_audit_hold_without_new_marks(self):
        c = fixed.CASES[5558632]
        for action, changes in [
            ("update", [{"lesson_id": c[1], "enrollment_id": c[2], "old": "q/b", "new": "—"}]),
            ("delete", []),
            ("update", {"broken": "PRIVATE"}),
        ]:
            with transaction.atomic():
                AuditLog.objects.create(
                    organization=self.org,
                    user=self.actor,
                    action=action,
                    resource_type="registrar.grade.mark",
                    resource_id=c[1],
                    changes=changes,
                )
                with self.assertRaisesMessage(ContentError, "contrary_clear_delete"):
                    self.execute()
                transaction.set_rollback(True)
        self.assertEqual(LessonMark.objects.count(), 0)

    def test_current_nonempty_zero_and_ie_never_overwritten(self):
        c = fixed.CASES[5458056]
        for status, score in [("present", 0), ("excused", None)]:
            mark = LessonMark.objects.create(
                organization=self.org,
                lesson_id=c[1],
                enrollment_id=c[2],
                status=status,
                score=score,
                entered_by=self.actor,
            )
            with self.assertRaisesMessage(ContentError, "nonempty_value"):
                self.execute()
            mark.refresh_from_db()
            self.assertEqual((mark.status, mark.score, mark.entered_by_id), (status, score, self.actor.pk))
            mark.delete()

    def test_canonical_inactive_dropped_other_group_copy_holds(self):
        c = fixed.CASES[5458056]
        src = self.offerings[c[0]]
        other_group = OrgUnit.objects.create(
            organization=self.org, name="Other", slug="four-other-group", unit_type="group"
        )
        other = CourseOffering.objects.create(
            organization=self.org,
            subject=src.subject,
            period=self.period,
            group=other_group,
            instructor=src.instructor,
            is_active=False,
            lesson_hours=2,
        )
        enr = Enrollment.objects.create(organization=self.org, offering=other, student_id=c[4], status="dropped")
        lesson = Lesson.objects.create(
            organization=self.org, offering=other, date=c[5], start_time=c[6], kind="seminar", hours=2
        )
        LessonMark.objects.create(organization=self.org, enrollment=enr, lesson=lesson, status="absent")
        with self.assertRaisesMessage(ContentError, "canonical_copy_already_elsewhere"):
            self.execute()

    def test_changed_exact_lesson_enrollment_profile_and_foreign_actor_hold(self):
        c = fixed.CASES[5458056]
        enr = Enrollment.objects.get(pk=c[2])
        enr.status = "dropped"
        enr.save(update_fields=["status"])
        with self.assertRaisesMessage(ContentError, "active_enrollment_changed"):
            self.execute()
        enr.status = "enrolled"
        enr.save(update_fields=["status"])
        Lesson.objects.filter(pk=c[1]).update(hours=1)
        with self.assertRaisesMessage(ContentError, "existing_lesson_changed"):
            self.execute()
        Lesson.objects.filter(pk=c[1]).update(hours=2)
        foreign = get_user_model().objects.create_superuser("four_foreign")
        foreign.profile.organization = None
        foreign.profile.save(update_fields=["organization"])
        with self.assertRaisesMessage(ContentError, "history_unavailable"):
            service.execute(
                data=validate_payload(self.raw, target_ids=sorted(fixed.TARGETS)),
                source_sha256=fixed.SOURCE_SHA,
                user=foreign,
                organization=self.org,
            )

    def test_late_evidence_and_write_failure_roll_back_all(self):
        dry = self.execute()
        c = fixed.CASES[5458056]
        with transaction.atomic():
            AuditLog.objects.create(
                organization=self.org,
                user=self.actor,
                action="delete",
                resource_type="registrar.LessonMark",
                resource_id=c[2],
            )
            with self.assertRaises(ContentError):
                self.execute(apply=True, expected_baseline=dry["baseline"])
            transaction.set_rollback(True)
        with patch.object(service, "_verify_created", side_effect=ContentError("late_failure")):
            with self.assertRaisesMessage(ContentError, "late_failure"):
                self.apply()
        self.assertEqual(LessonMark.objects.count(), 0)
        self.assertEqual(set(Enrollment.objects.values_list("absence_hours", flat=True)), {0})

    def test_undo_refuses_teacher_edit_and_stale_baseline(self):
        result = self.apply()
        dry = self.undo(result["batch"])
        mark = LessonMark.objects.first()
        mark.status = "excused"
        mark.entered_by = self.actor
        mark.save()
        with self.assertRaisesMessage(ContentError, "undo_baseline_changed"):
            self.undo(result["batch"], apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(LessonMark.objects.count(), 4)

    def test_formal_correction_and_grade_fact_hold_even_when_current_cell_is_blank(self):
        from apps.registrar.models import JournalCorrection, LegacyGradeFact

        c = fixed.CASES[5458056]
        with transaction.atomic():
            JournalCorrection.objects.create(
                organization=self.org,
                lesson_ref=c[1],
                enrollment_ref=c[2],
                lesson_mark_ref="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                field="attendance",
                old_status="absent",
                new_status="",
                created_mark=False,
                reason="technical",
                note="PRIVATE_DOCUMENT_REASON",
                document="private.pdf",
                corrected_by=self.actor,
            )
            with self.assertRaisesMessage(ContentError, "formal_correction_hygiene_or_gradefact"):
                self.execute()
            transaction.set_rollback(True)
        with transaction.atomic():
            LegacyGradeFact.objects.create(
                organization=self.org,
                source_system="myedu_mariadb",
                source_table="journals_dates_points",
                source_pk=5458056,
                source_snapshot_sha256="a" * 64,
                source_row_hash="b" * 64,
                materialization_digest="c" * 64,
                transform_version="test",
                evidence_kind="other",
                mapping_status="unresolved",
                mapping_issue_code="legacy_grade_fact_unresolved",
                raw_score_text="PRIVATE_SOURCE_TEXT",
            )
            with self.assertRaisesMessage(ContentError, "formal_correction_hygiene_or_gradefact"):
                self.execute()
            transaction.set_rollback(True)
        self.assertEqual(LessonMark.objects.count(), 0)

    def test_late_available_audit_changes_dry_baseline_and_no_writer_runs(self):
        dry = self.execute()
        c = fixed.CASES[5458056]
        AuditLog.objects.create(
            organization=self.org,
            user=self.actor,
            action="view",
            resource_type="registrar.Lesson",
            resource_id=c[1],
            changes=[],
            reason="PRIVATE_NEW_AUDIT",
        )
        with self.assertRaisesMessage(ContentError, "fresh_live_baseline_changed"):
            self.execute(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(LessonMark.objects.count(), 0)

    def test_only_remaining_three_blank_cells_are_created_and_existing_named_absence_kept(self):
        c = fixed.CASES[5458056]
        old = LessonMark.objects.create(
            organization=self.org, lesson_id=c[1], enrollment_id=c[2], status="absent", entered_by=self.actor
        )
        before = (old.pk, old.created_at, old.updated_at, old.entered_by_id)
        result = self.apply()
        self.assertEqual(result["created_marks"], 3)
        old.refresh_from_db()
        self.assertEqual((old.pk, old.created_at, old.updated_at, old.entered_by_id), before)
        self.assertEqual(self.apply()["already_done"], 1)

    def test_actual_undo_command_dry_apply_and_safe_numeric_summary(self):
        import re
        from io import StringIO

        from django.core.management import call_command

        result = self.apply()
        data = validate_payload(self.raw, target_ids=sorted(fixed.TARGETS))
        output = StringIO()
        with patch("apps.legacy_import.management.commands.undo_reviewed_four_cells.load_payload", return_value=data):
            call_command(
                "undo_reviewed_four_cells",
                actor=self.actor.username,
                manifest="PRIVATE_SOURCE_PATH",
                batch=result["batch"],
                stdout=output,
            )
            baseline = re.search(r"baseline=([a-f0-9]{64})", output.getvalue())[1]
            self.assertIn("mode=dry_run", output.getvalue())
            self.assertEqual(LessonMark.objects.count(), 4)
            output = StringIO()
            call_command(
                "undo_reviewed_four_cells",
                actor=self.actor.username,
                manifest="PRIVATE_SOURCE_PATH",
                batch=result["batch"],
                apply=True,
                expected_baseline=baseline,
                stdout=output,
            )
        self.assertEqual(LessonMark.objects.count(), 0)
        self.assertIn("mode=undo", output.getvalue())
        self.assertIn("deleted_marks=4", output.getvalue())
        self.assertNotIn("PRIVATE", output.getvalue())

    def test_active_access_state_cannot_override_deleted_or_blocked_profile(self):
        from django.utils import timezone

        user = get_user_model().objects.get(pk=next(iter(fixed.CASES.values()))[4])
        profile = user.profile
        for field, value in [("is_deleted", True), ("deleted_at", timezone.now()), ("blocked_at", timezone.now())]:
            original = getattr(profile, field)
            setattr(profile, field, value)
            profile.save(update_fields=[field])
            with self.subTest(field=field), self.assertRaisesMessage(ContentError, "active_tenant_student_required"):
                self.execute()
            setattr(profile, field, original)
            profile.save(update_fields=[field])
