"""Two-target real PostgreSQL: exact full names, complete content, fill-only and atomic undo."""

import copy
import hashlib
import io
import json
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.legacy_import.services import named_syllabus_recovery as recovery
from apps.legacy_import.tests.test_workload_syllabi import plan
from apps.organizations.models import OrgUnit
from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonMark, Subject
from apps.syllabus.models import Syllabus
from apps.syllabus.public import import_migrated_version, link_legacy_share, section_data_map
from apps.workload.models import TeacherAssignment
from apps.workload.tests import test_scoped_snapshot as fixtures
from apps.workload.tests.factories import TEACHER_PERMS, activate_member, make_row


class NamedSyllabusRecoveryTests(TestCase):
    def setUp(self):
        fixtures.ScopedSnapshotTests.setUp(self)
        self.org.refresh_from_db()
        self.stack["period"].refresh_from_db()
        self.task.status = "distributed"
        self.task.save(update_fields=["status"])
        self.rows, self.targets, self.authors = [], [], []
        self.payload = {"format": recovery.FORMAT, "entries": {}}
        for index, original in enumerate(recovery.ROWS):
            pinned = copy.deepcopy(original)
            author = self.teacher if index == 0 else get_user_model().objects.create_user("named-second-author")
            activate_member(self.org, author, "snapshot_teacher", permissions=TEACHER_PERMS)
            UserProfile.objects.filter(user=author).update(organization=self.org, access_state="active")
            title = f"Named course {'I' if index == 0 else 'II'}"
            subject = Subject.objects.create(organization=self.org, code=pinned["subject_code"], name=title)
            groups = [
                OrgUnit.objects.create(
                    organization=self.org,
                    name=f"Named {index}-{n}",
                    slug=f"named-{index}-{n}",
                    unit_type="group",
                    parent=self.stack["specialty"],
                )
                for n in range(3)
            ]
            stack = {**self.stack, "subject": subject, "group": groups[0]}
            workload = make_row(
                self.task,
                stack,
                lecture_total=pinned["row_totals"]["lecture"],
                seminar_total=pinned["row_totals"]["seminar"],
            )
            for key, value in {
                **{k + "_plan": v for k, v in pinned["source_plan_units"].items()},
                "credits": pinned["credits"],
                "degree_level": pinned["degree_level"],
                "education_form": pinned["education_form"],
                "total_hours": pinned["row_total_hours"],
                "union_count": pinned["union_count"],
                "subgroup_count": pinned["subgroup_count"],
            }.items():
                setattr(workload, key, value)
            workload.save()
            workload.groups.set(groups)
            for allocation in pinned["assignments"]:
                TeacherAssignment.objects.create(
                    organization=self.org,
                    row=workload,
                    teacher=author,
                    activity=allocation["activity"],
                    hours=allocation["hours"],
                    is_hourly_paid=allocation["is_hourly_paid"],
                )
            offering = CourseOffering.objects.create(
                organization=self.org,
                subject=subject,
                period=self.stack["period"],
                group=groups[0],
                instructor=author,
                lesson_hours=pinned["hours"],
            )
            source = plan()["source"]
            source.update(
                id=pinned["source_syllabus_id"],
                teacher_id=pinned["source_author"],
                lesson_id=pinned["source_lesson"],
                uniqid=f"named-source-{index}",
                ders_saati=pinned["hours"],
            )
            source["week"] = [
                dict(
                    id=100 + n,
                    uniqid=source["uniqid"],
                    movzu=f"Full topic {n}",
                    muh_saat="2" if index == 0 or n < 7 else "1",
                    sem_saat="1" if index == 0 or n == 7 else "2",
                    praktiki_saat="0",
                    lab_saat="0",
                    qeyd="Source note",
                )
                for n in range(pinned["topics"])
            ]
            source["sections"]["sillabus_serbest_is"] = [
                [200 + n, f"Full selfwork topic {n}"] for n in range(index + 3)
            ]
            journal = dict(
                id=pinned["journal_id"],
                teacher_id=pinned["source_author"],
                lesson_id=pinned["journal_lesson"],
                sillabus_id=source["id"],
                name=title + " - (2026/2027 Payız)",
                semestr=14,
                active=1,
                fake=0,
                sonra_sil=0,
                fenn_saati=pinned["hours"],
                kredit=pinned["credits"],
                groups_id=json.dumps(pinned["source_group_ids"]),
            )
            lesson = {"id": source["lesson_id"], "name": title}
            sections, _codes = recovery.build_section_data(recovery.document_for(source))
            pinned.update(
                offering_id=str(offering.pk),
                row_id=str(workload.pk),
                task_id=str(self.task.pk),
                author_id=author.pk,
                subject_id=str(subject.pk),
                group_id=str(groups[0].pk),
                row_group_ids=sorted(str(g.pk) for g in groups),
                period_id=str(offering.period_id),
                uniqid=source["uniqid"],
                source_course_title=title,
                source_journal_name=journal["name"],
                source_digest=recovery.core.digest(source),
                journal_digest=recovery.core.digest(journal),
                source_lesson_digest=recovery.core.digest(lesson),
                selfwork_rows=index + 3,
                selfwork_topics=index + 3,
                converted_content_digest=recovery.core.digest(sections),
                assignments=[{**a, "teacher_id": author.pk} for a in pinned["assignments"]],
            )
            self.payload["entries"][str(offering.pk)] = {
                "source": source,
                "source_journal": journal,
                "source_lesson": lesson,
            }
            self.rows.append(pinned)
            self.targets.append(offering)
            self.authors.append(author)
        self.addCleanup(patch.stopall)
        patch.object(recovery, "ROWS", tuple(self.rows)).start()
        patch.object(recovery.timezone, "localdate", return_value=self.stack["period"].start_date).start()

    def command(self, *, apply=False, undo="", data=None, org=None):
        raw = json.dumps(data or self.payload, ensure_ascii=False, sort_keys=True).encode()
        output = io.StringIO()
        with tempfile.NamedTemporaryFile() as file:
            file.write(raw)
            file.flush()
            kwargs = dict(org=(org or self.org).slug, actor=self.actor.username, apply=apply, stdout=output)
            if undo:
                kwargs["undo"] = undo
            else:
                kwargs.update(file=file.name, sha256=hashlib.sha256(raw).hexdigest())
            call_command("recover_named_workload_syllabi", **kwargs)
        return output.getvalue()

    def own(self):
        return Syllabus.objects.filter(offering_id__in=[o.pk for o in self.targets])

    def test_two_target_dry_apply_full_selfwork_repeat_and_exact_id_archive_undo(self):
        before = [recovery.core.metadata_digest(o) for o in self.targets]
        self.assertIn("syllabi_created=2", self.command())
        self.assertFalse(self.own().exists())
        output = self.command(apply=True)
        batch = output.split("batch=")[1].strip()
        self.assertIn("selfwork_restored=7", output)
        ids = set(self.own().values_list("pk", flat=True))
        for row, offering in zip(self.rows, self.targets):
            syllabus = self.own().get(offering=offering)
            version = syllabus.approved_version
            self.assertEqual(version.approval_source, "migration")
            self.assertEqual(syllabus.author_id, row["author_id"])
            sections = section_data_map(version)
            self.assertEqual(len(sections["self"]["topics"]), row["selfwork_topics"])
            self.assertEqual(recovery.core.digest(sections), row["converted_content_digest"])
            offering.refresh_from_db()
        self.assertEqual(before, [recovery.core.metadata_digest(o) for o in self.targets])
        self.assertIn("already_present=2", self.command(apply=True))
        self.assertEqual(ids, set(self.own().values_list("pk", flat=True)))
        self.assertIn("syllabi_retired=2", self.command(apply=True, undo=batch))
        self.assertEqual(ids, set(self.own().values_list("pk", flat=True)))
        self.assertFalse(self.own().filter(is_active=True).exists())
        self.assertIn("already_undone=1", self.command(apply=True, undo=batch))

    def test_full_custom_title_keeps_ordinal_and_qualification_and_exact_target_set(self):
        for title in (
            "Named course II - (2026/2027 Payız)",
            "Named course I533MRK - (2026/2027 Payız)",
            "Named course I (ixtisas üzrə) - (2026/2027 Payız)",
            "Named course I - (2025/2026 Payız)",
        ):
            data = copy.deepcopy(self.payload)
            data["entries"][self.rows[0]["offering_id"]]["source_journal"]["name"] = title
            with self.assertRaisesMessage(CommandError, "source_full_custom_course_name_scope"):
                self.command(apply=True, data=data)
            self.assertFalse(self.own().exists())
        data = copy.deepcopy(self.payload)
        data["entries"].pop(self.rows[1]["offering_id"])
        with self.assertRaisesMessage(CommandError, "fixed_source_target_set_required"):
            self.command(apply=True, data=data)

    def test_changed_raw_journal_pointer_or_source_text_never_imports(self):
        for key in ("sillabus_id", "lesson_id"):
            data = copy.deepcopy(self.payload)
            data["entries"][self.rows[0]["offering_id"]]["source_journal"][key] += 1
            with self.assertRaisesMessage(CommandError, "journal_source_scope"):
                self.command(apply=True, data=data)
        data = copy.deepcopy(self.payload)
        data["entries"][self.rows[0]["offering_id"]]["source"]["sections"]["sillabus_derslikler"][0][
            1
        ] = "Changed content"
        with self.assertRaisesMessage(CommandError, "pinned_source_digest_changed"):
            self.command(apply=True, data=data)
        self.assertFalse(self.own().exists())

    def test_existing_draft_on_second_target_rolls_back_first_import(self):
        existing = Syllabus.objects.create(
            organization=self.org,
            offering=self.targets[1],
            subject=self.targets[1].subject,
            period=self.targets[1].period,
            author=self.authors[1],
        )
        with self.assertRaisesMessage(CommandError, "existing_syllabus_no_overwrite"):
            self.command(apply=True)
        self.assertEqual(set(self.own().values_list("pk", flat=True)), {existing.pk})

    def test_effective_shared_approved_source_is_preserved(self):
        target = self.targets[0]
        group = OrgUnit.objects.create(
            organization=self.org, name="Shared source group", slug="named-share-group", unit_type="group"
        )
        original = CourseOffering.objects.create(
            organization=self.org, subject=target.subject, period=target.period, group=group, instructor=self.authors[0]
        )
        syllabus, version = import_migrated_version(
            organization=self.org,
            subject=target.subject,
            period=target.period,
            offering=original,
            author=self.authors[0],
            approved_at=timezone.now(),
            section_data={"desc": {"description": "Existing source"}},
        )
        link_legacy_share(syllabus=syllabus, offering=target, user=self.actor)
        with self.assertRaisesMessage(CommandError, "existing_syllabus_no_overwrite"):
            self.command(apply=True)
        self.assertFalse(self.own().exists())
        self.assertEqual(section_data_map(version)["desc"]["description"], "Existing source")

    def test_workload_credit_groups_assignments_and_tenant_changes_fail_closed(self):
        row = recovery.core.model("workload.TeachingTaskRow").objects.get(pk=self.rows[1]["row_id"])
        row.credits = "99"
        row.save(update_fields=["credits"])
        with self.assertRaisesMessage(CommandError, "live_official_workload_scope_changed"):
            self.command(apply=True)
        self.assertFalse(self.own().exists())
        row.credits = self.rows[1]["credits"]
        row.save(update_fields=["credits"])
        original_group_ids = list(row.groups.values_list("pk", flat=True))
        row.groups.remove(original_group_ids[-1])
        with self.assertRaisesMessage(CommandError, "live_official_workload_scope_changed"):
            self.command(apply=True)
        row.groups.add(original_group_ids[-1])
        TeacherAssignment.objects.filter(row=row, activity="seminar").update(hours=14)
        with self.assertRaisesMessage(CommandError, "live_workload_assignment_changed"):
            self.command(apply=True)
        with self.assertRaisesMessage(CommandError, "actor_or_tenant_scope"):
            self.command(apply=True, org=self.foreign)

    def test_existing_lesson_mark_preserved_and_author_revocation_rejected(self):
        activate_member(self.org, self.actor, "student")
        enrollment = Enrollment.objects.create(organization=self.org, offering=self.targets[0], student=self.actor)
        lesson = Lesson.objects.create(
            organization=self.org, offering=self.targets[0], date=self.stack["period"].start_date, kind="seminar"
        )
        mark = LessonMark.objects.create(organization=self.org, lesson=lesson, enrollment=enrollment, score=8)
        mark.refresh_from_db()
        before = recovery.core.metadata_digest(mark)
        self.command(apply=True)
        mark.refresh_from_db()
        self.assertEqual(recovery.core.metadata_digest(mark), before)
        UserProfile.objects.filter(user=self.authors[0]).update(access_state="archived")
        with self.assertRaisesRegex(CommandError, "author_(identity_scope|permission_missing)"):
            self.command(apply=True)

    def test_second_source_new_share_blocks_entire_undo(self):
        batch = self.command(apply=True).split("batch=")[1].strip()
        target = self.targets[1]
        syllabus = self.own().get(offering=target)
        group = OrgUnit.objects.create(
            organization=self.org, name="New consumer", slug="named-new-consumer", unit_type="group"
        )
        consumer = CourseOffering.objects.create(
            organization=self.org, subject=target.subject, period=target.period, group=group, instructor=self.authors[1]
        )
        link_legacy_share(syllabus=syllabus, offering=consumer, user=self.actor)
        with self.assertRaisesMessage(CommandError, "undo_content_or_usage_changed"):
            self.command(apply=True, undo=batch)
        self.assertEqual(self.own().filter(is_active=True, approved_version__status="approved").count(), 2)
