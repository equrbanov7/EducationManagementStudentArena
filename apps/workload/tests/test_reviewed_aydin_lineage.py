"""Real PostgreSQL preservation, audit provenance, fail-closed apply and explicit undo."""

import datetime as dt
from contextlib import ExitStack
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.syllabus.public import content_fingerprints
from apps.workload.services import reviewed_aydin_lineage_repair as repair
from apps.workload.services import reviewed_aydin_lineage_spec as spec
from apps.workload.services import reviewed_aydin_lineage_state as state
from apps.workload.services import reviewed_ilahe_subject_state as actor_state
from apps.workload.services.reviewed_leyla_catalog_graph import RepairError
from apps.workload.tests.factories import TEACHER_PERMS, activate_member, make_org, make_structure


class ReviewedAydinLineageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("aydin-lineage")
        cls.actor = cls.org.owner
        cls.actor.is_superuser = True
        cls.actor.save(update_fields=["is_superuser"])
        apps.get_model("accounts.UserProfile").objects.filter(user=cls.actor).update(organization=cls.org)
        cls.teacher = get_user_model().objects.create_user("aydin-author")
        activate_member(cls.org, cls.teacher, "teacher", permissions=TEACHER_PERMS)
        cls.structure = make_structure(cls.org, code="AL")
        cls.versions, cls.owners, cls.courses = {}, {}, {}
        cls.bodies = {}
        for i, key in enumerate((spec.OLDER, spec.NEWER)):
            group = apps.get_model("organizations.OrgUnit").objects.create(
                organization=cls.org,
                parent=cls.structure["specialty"],
                unit_type="group",
                name=f"Group{i}",
                slug=f"aydin-{i}",
            )
            course = apps.get_model("registrar.CourseOffering").objects.create(
                organization=cls.org,
                subject=cls.structure["subject"],
                period=cls.structure["period"],
                group=group,
                instructor=cls.teacher,
                lesson_hours=135,
            )
            owner = apps.get_model("syllabus.Syllabus").objects.create(
                organization=cls.org,
                subject=cls.structure["subject"],
                period=cls.structure["period"],
                offering=course,
                author=cls.teacher,
                chair_unit=cls.structure["chair"],
            )
            version = apps.get_model("syllabus.SyllabusVersion").objects.create(
                id=key,
                organization=cls.org,
                syllabus=owner,
                change_kind="copied",
                applies_to_period=cls.structure["period"],
                created_by=cls.teacher,
                plan_hours={"lecture": 45, "seminar": 45},
            )
            apps.get_model("syllabus.SyllabusVersion").objects.filter(pk=key).update(
                created_at=dt.datetime.fromisoformat(spec.CREATED[key])
            )
            apps.get_model("syllabus.Syllabus").objects.filter(pk=owner.pk).update(current_version=version)
            data = {k: {} for k in ("info", "desc", "out", "week", "method", "assess", "self", "lit", "prev", "send")}
            data["info"] = {"teacher": "Own human author"}
            data["week"] = {"rows": [{"topic": "", "lecture": 45, "seminar": 45 + i}]}
            for section, value in data.items():
                apps.get_model("syllabus.SyllabusSection").objects.create(
                    organization=cls.org, version=version, section_id=section, data=value
                )
            cls.bodies[key] = content_fingerprints(data)["canonical_body_sha256"]
            cls.versions[key], cls.owners[key], cls.courses[key] = version, owner, course
            student = get_user_model().objects.create_user(f"aydin-student-{i}")
            activate_member(cls.org, student, "student", permissions=["course.view", "grade.view"])
            enr = apps.get_model("registrar.Enrollment").objects.create(
                organization=cls.org, offering=course, student=student
            )
            lesson = apps.get_model("registrar.Lesson").objects.create(
                organization=cls.org,
                offering=course,
                date=dt.date(2026, 10, 1),
                kind="seminar",
                hours=2,
                topic="Historical body preserved",
            )
            cls.mark = apps.get_model("registrar.LessonMark").objects.create(
                organization=cls.org, lesson=lesson, enrollment=enr, status="present", score=Decimal("0")
            )
        Version = apps.get_model("syllabus.SyllabusVersion")
        Version.objects.filter(pk=spec.OLDER).update(source_version_id=spec.NEWER)
        Version.objects.filter(pk=spec.NEWER).update(source_version_id=spec.OLDER)
        Audit = apps.get_model("audit.AuditLog")

        def audit_create(**values):
            stamp = dt.datetime.fromisoformat(spec.AUDIT_CREATED[values["id"]])
            with patch("django.utils.timezone.now", return_value=stamp):
                return Audit.objects.create(**values)

        for key, audit in spec.CREATE_AUDITS.items():
            audit_create(
                id=audit,
                organization=cls.org,
                user=cls.teacher,
                resource_type="syllabus.version",
                resource_id=key,
                action="create",
                new_values={"status": "draft", "version": "v1.0"},
            )
        audit_create(
            id=spec.COPY_AUDIT,
            organization=cls.org,
            user=cls.teacher,
            resource_type="syllabus.version",
            resource_id=spec.NEWER,
            action="update",
            new_values={"kind": "copied", "status": "draft", "version": "v1.0"},
            changes={
                "reuse": "copy",
                "week_adjusted": True,
                "source_version": "v1.0",
                "source_syllabus": str(cls.owners[spec.OLDER].pk),
            },
        )

    def setUp(self):
        self.context = ExitStack()
        self.addCleanup(self.context.close)
        for obj, key, value in (
            (spec, "ORG", str(self.org.pk)),
            (actor_state.spec, "ORG", str(self.org.pk)),
            (spec, "AUTHOR", self.teacher.pk),
            (spec, "SUBJECT", str(self.structure["subject"].pk)),
            (spec, "PERIOD", str(self.structure["period"].pk)),
            (spec, "OWNERS", {k: str(v.pk) for k, v in self.owners.items()}),
            (spec, "OFFERINGS", {k: str(v.pk) for k, v in self.courses.items()}),
            (spec, "BODY", self.bodies),
        ):
            self.context.enter_context(patch.object(obj, key, value))

    def run_repair(self, **kwargs):
        return repair.run(organization=self.org, actor=self.actor, **kwargs)

    def test_dry_apply_repeat_and_explicit_undo_preserve_graph_and_zero_scores(self):
        before = state.snapshot(self.org)
        dry = self.run_repair()
        self.assertEqual(dry["status"], "dry_run")
        self.assertEqual(state.snapshot(self.org), before)
        result = self.run_repair(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(result["status"], "applied")
        after = state.snapshot(self.org)
        self.assertTrue(after["corrected"])
        self.assertEqual(repair.protected(before), repair.protected(after))
        self.assertEqual(self.run_repair()["status"], "already_applied")
        Version = apps.get_model("syllabus.SyllabusVersion")
        self.assertIsNone(Version.objects.get(pk=spec.OLDER).source_version_id)
        self.assertEqual(str(Version.objects.get(pk=spec.NEWER).source_version_id), spec.OLDER)
        undo_dry = self.run_repair(undo=result["receipt"])
        self.assertEqual(undo_dry["status"], "dry_run")
        self.assertTrue(state.snapshot(self.org)["corrected"])
        undone = self.run_repair(apply=True, undo=result["receipt"], expected_baseline=undo_dry["baseline"])
        self.assertEqual(undone["status"], "undone")
        self.assertEqual(state.snapshot(self.org), before)
        self.assertEqual(self.run_repair(undo=result["receipt"])["status"], "already_undone")
        self.mark.refresh_from_db()
        self.assertEqual(self.mark.score, Decimal("0"))

    def test_missing_explicit_copy_audit_holds(self):
        with patch.object(spec, "COPY_AUDIT", spec.CREATE_AUDITS[spec.OLDER]):
            with self.assertRaisesMessage(RepairError, "aydin_copy_anchor_changed"):
                self.run_repair()

    def test_body_change_holds_even_when_empty_topics(self):
        apps.get_model("syllabus.SyllabusSection").objects.filter(version_id=spec.OLDER, section_id="info").update(
            data={"teacher": "Changed human body"}
        )
        with self.assertRaisesMessage(RepairError, "aydin_body_changed"):
            self.run_repair()

    def test_wrong_or_stale_baseline_holds(self):
        with self.assertRaisesMessage(RepairError, "aydin_fresh_baseline_required"):
            self.run_repair(apply=True, expected_baseline="0" * 64)
        dry = self.run_repair()
        self.mark.score = Decimal("1")
        self.mark.save(update_fields=["score"])
        with self.assertRaisesMessage(RepairError, "aydin_fresh_baseline_required"):
            self.run_repair(apply=True, expected_baseline=dry["baseline"])

    def test_unreceipted_null_cannot_be_adopted(self):
        apps.get_model("syllabus.SyllabusVersion").objects.filter(pk=spec.OLDER).update(source_version=None)
        with self.assertRaisesMessage(RepairError, "aydin_corrected_without_receipt"):
            self.run_repair()

    def test_unauthorized_actor_and_foreign_tenant_hold(self):
        with self.assertRaisesMessage(RepairError, "aydin_actor_scope_refused"):
            repair.run(organization=self.org, actor=self.teacher)
        other = make_org("aydin-foreign")
        with self.assertRaisesMessage(RepairError, "aydin_actor_scope_refused"):
            repair.run(organization=other, actor=self.actor)

    def test_preservation_failure_rolls_back_fk_and_side_effect(self):
        dry = self.run_repair()
        original = state.snapshot
        calls = 0

        def changed(org):
            nonlocal calls
            calls += 1
            if calls == 2:
                apps.get_model("registrar.LessonMark").objects.filter(pk=self.mark.pk).update(score=Decimal("1"))
            return original(org)

        with patch.object(state, "snapshot", changed):
            with self.assertRaisesMessage(RepairError, "aydin_preservation_failed"):
                self.run_repair(apply=True, expected_baseline=dry["baseline"])
        self.assertFalse(state.snapshot(self.org)["corrected"])
        self.mark.refresh_from_db()
        self.assertEqual(self.mark.score, Decimal("0"))

    def test_undo_requires_exact_receipt_and_unchanged_after_graph(self):
        dry = self.run_repair()
        result = self.run_repair(apply=True, expected_baseline=dry["baseline"])
        with self.assertRaisesMessage(RepairError, "aydin_exact_receipt_required"):
            self.run_repair(undo="00000000-0000-0000-0000-000000000001")
        self.mark.score = Decimal("1")
        self.mark.save(update_fields=["score"])
        with self.assertRaisesMessage(RepairError, "aydin_undo_state_changed"):
            self.run_repair(undo=result["receipt"])

    def test_normal_export_closure_rejects_cycle_then_accepts_preserved_versions(self):
        from apps.workload.services.scoped_snapshot import SnapshotError
        from apps.workload.services.syllabus_content_export.collect import closure

        Syllabus = apps.get_model("syllabus.Syllabus")
        Version = apps.get_model("syllabus.SyllabusVersion")
        with self.assertRaisesMessage(SnapshotError, "syllabus_lineage_cycle"):
            closure(
                list(Syllabus.objects.filter(pk__in=spec.OWNERS.values())),
                list(Version.objects.filter(pk__in=spec.OWNERS)),
            )
        dry = self.run_repair()
        self.run_repair(apply=True, expected_baseline=dry["baseline"])
        syllabi, versions = closure(
            list(Syllabus.objects.filter(pk__in=spec.OWNERS.values())), list(Version.objects.filter(pk__in=spec.OWNERS))
        )
        self.assertEqual(set(syllabi), set(spec.OWNERS.values()))
        self.assertEqual(set(versions), set(spec.OWNERS))

    def test_command_defaults_to_readonly_and_returns_only_safe_receipt_fields(self):
        output = StringIO()
        call_command("repair_reviewed_aydin_lineage", actor=self.actor.username, stdout=output)
        self.assertRegex(
            output.getvalue(),
            r"^reviewed_aydin_lineage: status=dry_run applied=0 baseline=[a-f0-9]{64} receipt=none\n$",
        )
        self.assertFalse(state.snapshot(self.org)["corrected"])

    def test_command_sanitizes_unknown_error_without_body_or_contact_output(self):
        with patch.object(repair, "run", side_effect=RepairError("PRIVATE_BODY_AND_CONTACT")):
            with self.assertRaisesMessage(CommandError, "aydin_reviewed_guard_failed"):
                call_command("repair_reviewed_aydin_lineage", actor=self.actor.username, stdout=StringIO())
