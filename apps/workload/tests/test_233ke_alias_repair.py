"""Exact233KE bərpası: dolu jurnallar/versiyalar qalır, sürüşmə və kənar scope rədd edilir."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar.journal_group_identity import choices_for_scope, filter_group
from apps.registrar.models import (
    AssessmentScheme,
    CourseOffering,
    Curriculum,
    Enrollment,
    Lesson,
    StudentAcademicRecord,
    Subject,
)
from apps.registrar.page_contexts import journal_list_context
from apps.registrar.public import journal_access_diagnostics, workload_hours_for_offering
from apps.syllabus.models import Syllabus, SyllabusSection, SyllabusShare, SyllabusVersion
from apps.workload.models import TeacherAssignment, TeachingTask, TeachingTaskRow
from apps.workload.services import ke233_alias_repair as repair
from apps.workload.services import ke233_alias_spec as spec
from apps.workload.services import ke233_alias_state as state
from apps.workload.services.group_aliases import verified_aliases
from apps.workload.services.queries import serialize_rows
from apps.workload.services.row_edit import save_row_amended
from apps.workload.services.scoped_snapshot.data import collect
from apps.workload.services.scoping import resolve_actor
from apps.workload.services.task_row_matching import RowMatcher
from core.constants import OrgUnitType
from core.rls import apply_rls_request_context, reset_rls_context

from .factories import TEACHER_PERMS, activate_member, make_structure

User = get_user_model()


@override_settings(RLS_TRANSACTION_SCOPED=True)
class Ke233AliasRepairTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("ke233_admin", "admin@x.test", "pw")
        self.org = Organization.objects.create(
            pk=spec.ORG,
            name="QKU",
            slug="qku",
            owner=self.admin,
            org_type="university",
            status="active",
            is_active=True,
        )
        self.stack = make_structure(self.org, code="KE")
        settings = {"degree_level": "bachelor", "education_form": "full_time", "sector": "az"}
        self.source = OrgUnit.objects.create(
            pk=spec.SOURCE,
            organization=self.org,
            name="233KE",
            slug="alias",
            unit_type="group",
            parent=self.stack["specialty"],
            settings=settings,
        )
        self.target = OrgUnit.objects.create(
            pk=spec.TARGET,
            organization=self.org,
            name="233 KE az",
            slug="canonical",
            unit_type="group",
            parent=self.stack["specialty"],
            settings=settings,
        )
        self.source.refresh_from_db()
        self.target.refresh_from_db()
        periods = sorted({r["period_id"] for r in spec.ROWS})
        self.periods = {}
        for pid in periods:
            fall = pid == "a4f88744-8d49-4772-84ef-c28a96c3b372"
            self.periods[pid] = AcademicPeriod.objects.create(
                pk=pid,
                organization=self.org,
                academic_year=spec.YEAR,
                name="Payız" if fall else "Yaz",
                period_type="semester",
                start_date="2026-09-01" if fall else "2027-02-01",
                end_date="2027-01-31" if fall else "2027-06-30",
                is_current=fall,
            )
        self.subjects, self.teachers = {}, {}
        all_items = [*spec.MOVES, *state.retained_items(), *spec.COLLISIONS]
        for i, item in enumerate(all_items):
            sid, tid = item["subject_id"], item["teacher_id"]
            self.subjects[sid] = Subject.objects.create(pk=sid, organization=self.org, code=f"KE-{i}", name=f"Fənn{i}")
            if tid and tid not in self.teachers:
                user = User.objects.create_user(pk=tid, username=f"teacher{tid}", password="pw")
                activate_member(self.org, user, "teacher", permissions=TEACHER_PERMS, scope_unit=self.stack["chair"])
                self.teachers[tid] = user
        self.tasks = {}
        for i, tid in enumerate(sorted({r["task_id"] for r in spec.ROWS})):
            chair = OrgUnit.objects.create(
                organization=self.org,
                name=f"Kafedra{i}",
                slug=f"chair{i}",
                unit_type=OrgUnitType.CHAIR,
                parent=self.stack["faculty"],
            )
            self.tasks[tid] = TeachingTask.objects.create(
                pk=tid, organization=self.org, chair=chair, academic_year=spec.YEAR, status="distributed"
            )
        self.rows = {}
        for item in spec.ROWS:
            for gid in item["before_groups"]:
                if not OrgUnit.objects.filter(pk=gid).exists():
                    OrgUnit.objects.create(
                        pk=gid,
                        organization=self.org,
                        name=gid[:8],
                        slug=gid[:8],
                        unit_type="group",
                        parent=self.stack["specialty"],
                    )
            info = next(v for v in all_items if v["subject_id"] == item["subject_id"])
            row = TeachingTaskRow.objects.create(
                pk=item["id"],
                organization=self.org,
                task=self.tasks[item["task_id"]],
                subject=self.subjects[item["subject_id"]],
                period=self.periods[item["period_id"]],
                lecture_plan=30 if info["teacher_id"] else 0,
                lecture_total=30 if info["teacher_id"] else 0,
                total_hours=30,
                groups_text="old233KE",
            )
            row.groups.set(item["before_groups"])
            if info["teacher_id"]:
                TeacherAssignment.objects.create(
                    organization=self.org, row=row, teacher_id=info["teacher_id"], activity="lecture", hours=30
                )
            if item["id"] == spec.RETAINED["row_id"]:
                row.lecture_plan, row.seminar_plan, row.seminar_total, row.total_hours = 0, 0, 15, 45
                row.save(update_fields=["lecture_plan", "seminar_plan", "seminar_total", "total_hours"])
                TeacherAssignment.objects.create(
                    organization=self.org, row=row, teacher_id=8304, activity="seminar", hours=15
                )
            self.rows[item["id"]] = row
        self.offerings = {}
        for item in all_items:
            ids = [item["id"]] if "id" in item else [item["source"], item["target"]]
            for oid in ids:
                target = "target" in item and oid == item["target"]
                offering = CourseOffering.objects.create(
                    pk=oid,
                    organization=self.org,
                    subject=self.subjects[item["subject_id"]],
                    period=self.periods[item["period_id"]],
                    instructor_id=item["teacher_id"],
                    group=self.target if target else self.source,
                    lesson_hours=45 if item["teacher_id"] else 0,
                )
                self.offerings[oid] = offering
        self.student = User.objects.create_user("student_ke233", password="pw")
        activate_member(self.org, self.student, "student", permissions=["grade.view"], scope_unit=self.target)
        curriculum = Curriculum.objects.create(
            organization=self.org, program=self.stack["program"], admission_year=2023, version=1, status="approved"
        )
        self.sar = StudentAcademicRecord.objects.create(
            organization=self.org,
            student=self.student,
            group=self.target,
            program=self.stack["program"],
            curriculum=curriculum,
            admission_year=2023,
        )
        # Dolu target jurnalları; köhnə collisions isə0enrollment/0lesson qalır.
        for item in spec.COLLISIONS:
            Enrollment.objects.create(
                organization=self.org, student=self.student, offering=self.offerings[item["target"]]
            )
        self.lesson = Lesson.objects.create(
            organization=self.org,
            offering=self.offerings["5ce57ac5-73cd-4917-b160-229b2f1a87f5"],
            kind="lecture",
            hours=2,
            date="2026-10-20",
            instructor_id=8304,
            created_by=self.admin,
            topic="Jalənin qorunan dərsi",
        )
        share_source = self.offerings["5c1f6e6d-44f1-4321-a28f-9fc87ed6070c"]
        self.sy = self.make_syllabus(share_source, pk=spec.SHARE_SYLLABUS)
        self.aida_sy = self.make_syllabus(self.offerings[spec.COLLISIONS[0]["source"]])
        self.make_syllabus(self.offerings[spec.COLLISIONS[0]["target"]])
        self.retained_syllabus = Syllabus.objects.create(
            organization=self.org,
            offering=self.offerings[spec.RETAINED["id"]],
            subject_id=spec.RETAINED["subject_id"],
            period_id=spec.RETAINED["period_id"],
            author_id=8304,
        )
        self.retained_version = SyllabusVersion.objects.create(
            organization=self.org, syllabus=self.retained_syllabus, status="draft", plan_hours={"lecture": 30}
        )
        SyllabusSection.objects.create(
            organization=self.org,
            version=self.retained_version,
            section_id="week",
            data={"rows": [{"topic": "qaralama eyni qalsın"}]},
        )
        self.retained_syllabus.current_version = self.retained_version
        self.retained_syllabus.save(update_fields=["current_version"])
        AssessmentScheme.objects.get_or_create(organization=self.org, offering=self.offerings[spec.RETAINED["id"]])
        for item in spec.PRESERVED:
            AssessmentScheme.objects.get_or_create(organization=self.org, offering=self.offerings[item["id"]])
        apply_rls_request_context(user_id=self.admin.pk, org_id=self.org.pk, bypass=False)

    def make_syllabus(self, offering, pk=None):
        kwargs = {"pk": pk} if pk else {}
        sy = Syllabus.objects.create(
            **kwargs,
            organization=self.org,
            offering=offering,
            subject=offering.subject,
            period=offering.period,
            author_id=offering.instructor_id,
        )
        version = SyllabusVersion.objects.create(
            organization=self.org,
            syllabus=sy,
            status="approved",
            locked_at=timezone.now(),
            approved_by=self.admin,
            plan_hours={"lecture": 30, "seminar": 15},
        )
        SyllabusSection.objects.create(
            organization=self.org, version=version, section_id="week", data={"rows": [{"topic": "qorunsun"}]}
        )
        sy.current_version = sy.approved_version = version
        sy.save(update_fields=["current_version", "approved_version"])
        return sy

    def tearDown(self):
        reset_rls_context()

    def run_repair(self, **kw):
        return repair.run(organization=self.org, user=self.admin, source_sha256=spec.SOURCE_SHA, **kw)

    def apply(self):
        return self.run_repair(apply=True, expected_baseline=state.digest(state.state()))

    def test_dry_run_rolls_back_every_write_and_preserves_manual_practice_total(self):
        before = state.state()
        result = self.run_repair()
        self.assertEqual(result["changed_rows"], 7)
        self.assertEqual(result["moved_offerings"], 2)
        self.assertEqual(result["retired_empty_offerings"], 4)
        self.assertEqual(result["enroll_created"], 2)
        self.assertEqual(result["enroll_guest_added"], 2)
        self.assertEqual(result["created_shares"], 1)
        self.assertEqual(state.state(), before)

    def test_apply_repeat_undo_preserves_lesson_and_approved_syllabi(self):
        academic = state.academic()
        aida_fields = state.records(Syllabus.objects.filter(pk=self.aida_sy.pk))
        before_enrollments = state.enrollment_rows()
        before_shares = state.share_rows()
        result = self.apply()
        self.lesson.refresh_from_db()
        self.assertEqual(str(self.lesson.offering.group_id), spec.SOURCE)
        retained = CourseOffering.objects.select_related("organization", "period").get(pk=spec.RETAINED["id"])
        diagnostic = journal_access_diagnostics(offering=retained, teacher_ids=[8304])[0]
        self.assertTrue(diagnostic["direct_editor"])
        self.assertTrue(diagnostic["structural_write_candidate"])
        self.assertFalse(diagnostic["syllabus_locked"])
        self.assertEqual(workload_hours_for_offering(retained)["lecture"], 30)
        self.assertEqual(workload_hours_for_offering(retained)["seminar"], 15)
        self.assertTrue(
            Enrollment.objects.filter(offering=retained, student=self.student, source_group=self.target).exists()
        )
        self.assertEqual(state.academic(), academic)
        self.assertEqual(state.records(Syllabus.objects.filter(pk=self.aida_sy.pk)), aida_fields)
        self.assertTrue(SyllabusShare.objects.filter(syllabus=self.sy, offering_id=spec.SHARE_TARGET).exists())
        self.source.refresh_from_db()
        self.assertFalse(self.source.is_active)
        self.assertEqual(self.source.settings["canonical_group"], spec.TARGET)
        self.assertEqual(self.run_repair()["already_applied"], 1)
        undo_baseline = state.digest(state.state())
        preview = self.run_repair(undo=result["batch"])
        self.assertEqual(preview["restored_rows"], 7)
        self.assertEqual(state.digest(state.state()), undo_baseline)
        self.run_repair(undo=result["batch"], apply=True, expected_baseline=undo_baseline)
        self.assertEqual(state.academic(), academic)
        self.assertEqual(state.enrollment_rows(), before_enrollments)
        self.assertEqual(state.share_rows(), before_shares)
        self.source.refresh_from_db()
        self.assertTrue(self.source.is_active)

    def test_concurrent_snapshot_change_rejects_whole_batch(self):
        baseline = state.digest(state.state())
        self.lesson.topic = "yeni real mövzu"
        self.lesson.save(update_fields=["topic", "updated_at"])
        with self.assertRaisesRegex(state.RepairError, "baseline_conflict"):
            self.run_repair(apply=True, expected_baseline=baseline)
        self.assertTrue(OrgUnit.objects.get(pk=spec.SOURCE).is_active)

    def test_collision_lesson_is_never_retired_or_deleted(self):
        Lesson.objects.create(
            organization=self.org,
            offering=self.offerings[spec.COLLISIONS[0]["source"]],
            kind="lecture",
            hours=2,
            date="2026-10-21",
            instructor_id=8349,
            topic="Yeni yazılmış dərs",
        )
        with self.assertRaisesRegex(state.RepairError, "collision_source_has_content"):
            self.run_repair()

    def test_unknown_alias_row_or_real_membership_blocks_group_retirement(self):
        Membership.objects.filter(user=self.student).update(scope_unit=self.source)
        with self.assertRaisesRegex(state.RepairError, "outside_group_reference_in_use"):
            self.run_repair()

    def test_parent_subgroup_or_english_sector_never_merges(self):
        self.source.settings = {**self.source.settings, "sector": "en"}
        self.source.save(update_fields=["settings"])
        with self.assertRaisesRegex(state.RepairError, "group_sector_or_program_mismatch"):
            self.run_repair()

    def test_undo_after_teacher_writes_is_rejected(self):
        result = self.apply()
        self.lesson.topic = "bərpadan sonra müəllimin düzəlişi"
        self.lesson.save(update_fields=["topic", "updated_at"])
        with self.assertRaisesRegex(state.RepairError, "undo_state_changed"):
            self.run_repair(undo=result["batch"])
        self.lesson.refresh_from_db()
        self.assertEqual(self.lesson.topic, "bərpadan sonra müəllimin düzəlişi")

    def test_failure_after_row_changes_rolls_back_all_writes(self):
        before = state.state()
        with patch.object(repair, "link_legacy_share", return_value="other_teacher"):
            with self.assertRaisesRegex(state.RepairError, "syllabus_link_other_teacher"):
                self.apply()
        self.assertEqual(state.state(), before)

    def test_foreign_tenant_and_non_admin_cannot_run(self):
        with self.assertRaisesRegex(state.RepairError, "source_or_tenant_mismatch"):
            repair.run(organization=self.org, user=self.admin, source_sha256="0" * 64)
        with self.assertRaisesRegex(state.RepairError, "active_superadmin_required"):
            repair.run(organization=self.org, user=self.student, source_sha256=spec.SOURCE_SHA)

    def test_apply_requires_current_baseline(self):
        with self.assertRaisesRegex(state.RepairError, "expected_baseline_required"):
            self.run_repair(apply=True)

    def test_ui_and_future_import_select_canonical_but_preserve_historical_fk(self):
        self.apply()
        row = TeachingTaskRow.objects.select_related("task", "subject").get(pk=spec.RETAINED["row_id"])
        payload = next(r for r in serialize_rows(row.task) if r["id"] == str(row.pk))
        self.assertEqual(payload["groups"], [{"id": spec.TARGET, "name": "233 KE az"}])
        chosen, how = RowMatcher([row]).match(
            season=row.season,
            subject_text=row.subject_label,
            groups_text="233 KE az",
            subject=row.subject,
            group_ids=[self.target.pk],
        )
        self.assertEqual(chosen.pk, row.pk)
        self.assertEqual(how, "units")
        before = CourseOffering.objects.count()
        saved = save_row_amended(
            task=row.task,
            row=row,
            actor=resolve_actor(self.admin, self.org),
            data={"group_ids": [spec.TARGET], "total_hours": row.total_hours},
        )
        self.assertEqual(list(saved.groups.values_list("pk", flat=True)), [self.source.pk])
        self.assertEqual(CourseOffering.objects.count(), before)
        self.lesson.refresh_from_db()
        self.assertEqual(str(self.lesson.offering.group_id), spec.SOURCE)

    def test_explicit_alias_mapper_rejects_subgroups_english_and_foreign_pointers(self):
        self.apply()
        self.source.refresh_from_db()
        self.assertEqual(verified_aliases([self.source])[self.source.pk].pk, self.target.pk)
        for changed in (
            {"parent_group": spec.TARGET},
            {"sector": "en"},
            {"canonical_group": str(self.stack["group"].pk)},
        ):
            self.source.settings = {
                "degree_level": "bachelor",
                "education_form": "full_time",
                "sector": "az",
                "canonical_group": spec.TARGET,
                **changed,
            }
            self.assertEqual(verified_aliases([self.source]), {})
        self.source.settings = {
            "degree_level": "bachelor",
            "education_form": "full_time",
            "sector": "az",
            "canonical_group": spec.TARGET,
        }
        self.source.name = "233 KE-1"
        self.assertEqual(verified_aliases([self.source]), {})

    def test_scoped_export_preserves_only_valid_same_tenant_canonical_uuid(self):
        self.apply()
        self.source.refresh_from_db()
        self.source.settings = {**self.source.settings, "private_secret": "must not export"}
        self.source.save(update_fields=["settings"])
        data = collect(student_secret=b"stable-test-only-secret" * 2)
        source = next(g for g in data["groups"] if str(g["id"]) == spec.SOURCE)
        self.assertEqual(source["settings"]["canonical_group"], spec.TARGET)
        self.assertNotIn("private_secret", source["settings"])
        self.source.settings = {**self.source.settings, "canonical_group": "https://untrusted.invalid/"}
        self.source.save(update_fields=["settings"])
        again = collect(student_secret=b"stable-test-only-secret" * 2)
        self.assertNotIn("canonical_group", next(g for g in again["groups"] if str(g["id"]) == spec.SOURCE)["settings"])

    def test_journal_canonical_group_filter_keeps_retained_journals_visible(self):
        self.apply()
        request = RequestFactory().get("/jurnal/", {"year": spec.YEAR, "group": spec.TARGET})
        request.user, request.organization = self.admin, self.org
        context = journal_list_context(self.admin, request)
        ids = {str(o.pk) for o in context["offerings"]}
        self.assertTrue({item["id"] for item in state.retained_items()} <= ids)
        choices = context["journal_groups"]
        self.assertEqual(
            [r for r in choices if r["value"] in (spec.SOURCE, spec.TARGET)],
            [{"value": spec.TARGET, "label": "233 KE az"}],
        )
        self.assertTrue(all(o.journal_group_name == "233 KE az" for o in context["offerings"]))
        retained = next(o for o in context["offerings"] if str(o.pk) == spec.RETAINED["id"])
        self.assertEqual(str(retained.group_id), spec.SOURCE)

    def test_alias_journal_filter_never_broadens_teacher_queryset(self):
        self.apply()
        scoped = CourseOffering.objects.filter(organization=self.org, instructor_id=8304, is_active=True)
        self.assertEqual(choices_for_scope(scoped), [{"value": spec.TARGET, "label": "233 KE az"}])
        found, selected = filter_group(scoped, self.target.pk, within=scoped)
        self.assertEqual(selected, spec.TARGET)
        self.assertEqual([str(pk) for pk in found.values_list("id", flat=True)], [str(self.lesson.offering_id)])
        self.assertFalse(found.filter(instructor_id=8349).exists())
