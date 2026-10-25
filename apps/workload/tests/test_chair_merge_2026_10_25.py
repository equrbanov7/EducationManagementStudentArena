"""Sahib 2026-10-25: «Xarici dillər kafedrası olub, ora rəsmi olaraq elə dəyişib — ona birləşdir.»

``merge_chair_units``: mənbə kafedranın CARİ dərs yükü (sətirlər bölgüləri ilə; eyni sətir birləşir — saat
ikiqat olmur), aktiv üzvlüklər (əsas üzvlük əsas qalır), fənn kataloqu, cari sillabuslar hədəfə keçir; köhnə
il / köhnə semestr / qeyri-aktiv üzvlük mənbədə qalır; mənbə arxivlənir, köhnə adı hədəfin ``aliases``-ində
(kafedra reyestri axtarışı onu tapır). Dry-run defolt, idempotent, çıxış yalnız saylardır.
"""

from __future__ import annotations

import io

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.organizations.models import AcademicPeriod, Membership, OrgUnit
from apps.organizations.structure_views.registry_base import _apply_common_filters
from apps.registrar.models import Subject
from apps.syllabus.models import Syllabus
from apps.workload.constants import Activity, TaskStatus
from apps.workload.models import TeacherAssignment, TeachingTask, TeachingTaskRow
from core.constants import AcademicPeriodType, OrgUnitType, RoleScopeType

from .factories import TEACHER_PERMS, YEAR, activate_member, make_org, make_row, make_structure, make_task

User = get_user_model()


def _counts(output: str) -> dict:
    line = next(line for line in output.splitlines() if line.startswith("chair_merge: "))
    pairs = dict(item.split("=", 1) for item in line.split()[1:])
    return {key: (value if key == "mode" else int(value)) for key, value in pairs.items()}


class ChairMergeCommandTests(TestCase):
    def setUp(self):
        self.org = make_org("wl-chair-merge")
        self.src = make_structure(self.org, code="SRC")
        self.tgt = make_structure(self.org, code="TGT")
        self.source, self.target = self.src["chair"], self.tgt["chair"]
        User.objects.create_superuser("merge_admin", "ma@x.test", "pw")

        self.only_src = User.objects.create_user("merge_a", "a@x.test", "pw")
        self.both = User.objects.create_user("merge_b", "b@x.test", "pw")
        self.left = User.objects.create_user("merge_c", "c@x.test", "pw")
        for user in (self.only_src, self.both, self.left):
            activate_member(
                self.org, user, "teacher", permissions=TEACHER_PERMS, scope_unit=self.source,
                scope_type=RoleScopeType.COURSE,
            )  # fmt: skip
        Membership.objects.filter(user=self.only_src).update(is_primary=True)
        Membership.objects.filter(user=self.left).update(is_active=False)
        role = Membership.objects.get(user=self.both).role
        Membership.objects.create(organization=self.org, user=self.both, role=role, scope_unit=self.target)
        Membership.objects.filter(user=self.both, scope_unit=self.source).update(is_primary=True)

        self.src_task = make_task(self.org, self.source, status=TaskStatus.DISTRIBUTED)
        self.tgt_task = make_task(self.org, self.target, status=TaskStatus.DISTRIBUTED)
        self.own_row = make_row(self.src_task, self.src, lecture_total=30, seminar_total=15)
        TeacherAssignment.objects.create(
            organization=self.org, row=self.own_row, teacher=self.only_src, activity=Activity.LECTURE, hours=30
        )
        # Eyni sətir (fənn + semestr + qrup) iki kafedrada: hədəfdə bölgüsüz, mənbədə bölgülü → birləşir.
        self.tgt_row = make_row(self.tgt_task, self.tgt, lecture_total=40, seminar_total=20)
        self.dup_row = make_row(self.src_task, self.tgt, lecture_total=40, seminar_total=20)
        TeacherAssignment.objects.create(
            organization=self.org, row=self.dup_row, teacher=self.both, activity=Activity.LECTURE, hours=40
        )
        self.old_task = TeachingTask.objects.create(
            organization=self.org, chair=self.source, academic_year="2025/2026", status=TaskStatus.DISTRIBUTED
        )
        old_period = AcademicPeriod.objects.create(
            organization=self.org, name="Yaz SRC", period_type=AcademicPeriodType.SEMESTER, academic_year="2025/2026",
            start_date="2026-02-01", end_date="2026-06-30",
        )  # fmt: skip
        subject = self.src["subject"]
        Subject.objects.filter(pk=subject.pk).update(chair_unit=self.source)
        self.current_syllabus = Syllabus.objects.create(
            organization=self.org, subject=subject, period=self.src["period"], chair_unit=self.source
        )
        self.base_syllabus = Syllabus.objects.create(organization=self.org, subject=subject, chair_unit=self.source)
        self.old_syllabus = Syllabus.objects.create(
            organization=self.org, subject=subject, period=old_period, chair_unit=self.source
        )

    def _run(self, *extra) -> dict:
        out = io.StringIO()
        call_command(
            "merge_chair_units", "--org", self.org.slug, "--year", YEAR, "--actor", "merge_admin",
            "--source", "SRC-kafedra", "--target", "TGT-kafedra", *extra, stdout=out,
        )  # fmt: skip
        return _counts(out.getvalue())

    def test_dry_run_counts_and_writes_nothing(self):
        counts = self._run()
        self.assertEqual(counts["mode"], "dry_run")
        self.assertEqual((counts["rows_moved"], counts["duplicate_rows_merged"], counts["tasks_closed"]), (1, 1, 1))
        self.assertEqual((counts["memberships_moved"], counts["memberships_deduplicated"]), (1, 1))
        self.assertEqual((counts["syllabi_moved"], counts["syllabi_history_kept"]), (2, 1))
        self.assertEqual(counts["source_archived"], 1)
        self.source.refresh_from_db()
        self.assertTrue(self.source.is_active)
        self.assertEqual(TeachingTaskRow.objects.filter(task=self.src_task).count(), 2)

    def test_apply_moves_current_work_keeps_history_and_is_idempotent(self):
        counts = self._run("--apply")
        self.assertEqual(counts["mode"], "apply")

        # Dərs yükü: öz sətri köçdü, dublikat birləşdi (saat bir dəfə), mənbə sənədi ləğv — silinmədi.
        self.assertEqual(TeachingTaskRow.objects.filter(task=self.tgt_task).count(), 2)
        self.assertEqual(TeachingTaskRow.objects.filter(pk=self.dup_row.pk).count(), 0)
        self.assertEqual(TeacherAssignment.objects.get(teacher=self.both).row_id, self.tgt_row.pk)
        self.assertEqual(TeacherAssignment.objects.get(teacher=self.only_src).row.task_id, self.tgt_task.pk)
        self.tgt_task.refresh_from_db()
        self.src_task.refresh_from_db()
        self.assertEqual(self.tgt_task.status, TaskStatus.DISTRIBUTED)
        self.assertEqual(self.src_task.status, TaskStatus.CANCELLED)
        self.assertEqual(TeachingTask.objects.get(pk=self.old_task.pk).chair_id, self.source.pk)

        # Üzvlüklər: əsas üzvlük əsas qalır; dublikatda hədəf əsas olur; qeyri-aktiv mənbədə qalır.
        moved = Membership.objects.get(user=self.only_src)
        self.assertEqual((moved.scope_unit_id, moved.is_primary, moved.is_active), (self.target.pk, True, True))
        kept = Membership.objects.get(user=self.both, scope_unit=self.target)
        self.assertTrue(kept.is_active and kept.is_primary)
        self.assertFalse(Membership.objects.get(user=self.both, scope_unit=self.source).is_active)
        self.assertEqual(Membership.objects.get(user=self.left).scope_unit_id, self.source.pk)

        # Kataloq + sillabus: cari və dövrsüz köçür, köhnə semestrinki qalır.
        self.assertEqual(Subject.objects.get(pk=self.src["subject"].pk).chair_unit_id, self.target.pk)
        self.assertEqual(Syllabus.objects.get(pk=self.current_syllabus.pk).chair_unit_id, self.target.pk)
        self.assertEqual(Syllabus.objects.get(pk=self.base_syllabus.pk).chair_unit_id, self.target.pk)
        self.assertEqual(Syllabus.objects.get(pk=self.old_syllabus.pk).chair_unit_id, self.source.pk)

        # Vahid: arxiv + tarixçə; alt vahid köçdü; köhnə ad hədəfdə — reyestr axtarışı tapır.
        self.source.refresh_from_db()
        self.target.refresh_from_db()
        self.assertFalse(self.source.is_active)
        self.assertEqual(self.source.settings["history"][-1]["merged_into"], str(self.target.pk))
        self.assertIn("SRC-kafedra", self.target.settings["aliases"])
        self.assertEqual(OrgUnit.objects.get(pk=self.src["specialty"].pk).parent_id, self.target.pk)
        chairs = OrgUnit.objects.filter(organization=self.org, is_active=True, unit_type=OrgUnitType.CHAIR)
        found = _apply_common_filters(chairs, search="src kafedra", head="")
        self.assertEqual(list(found.values_list("pk", flat=True)), [self.target.pk])

        again = self._run("--apply")
        self.assertEqual(again["already_merged"], 1)
        moved_keys = [k for k in again if k.endswith(("_moved", "rows_merged", "_closed", "_archived", "_reactivated"))]
        self.assertEqual({key: again[key] for key in moved_keys}, dict.fromkeys(moved_keys, 0))

    def test_duplicate_rows_with_both_distributions_block_apply(self):
        TeacherAssignment.objects.create(
            organization=self.org, row=self.tgt_row, teacher=self.only_src, activity=Activity.LECTURE, hours=40
        )
        with self.assertRaisesMessage(CommandError, "duplicate_rows_conflict"):
            self._run("--apply")
        self.source.refresh_from_db()
        self.assertTrue(self.source.is_active)
        self.assertEqual(TeachingTaskRow.objects.filter(task=self.src_task).count(), 2)

    def test_unknown_target_and_non_superuser_are_rejected(self):
        with self.assertRaisesMessage(CommandError, "target_not_found"):
            call_command(
                "merge_chair_units", "--org", self.org.slug, "--year", YEAR, "--actor", "merge_admin",
                "--source", "SRC-kafedra", "--target", "Yox kafedra", stdout=io.StringIO(),
            )  # fmt: skip
        with self.assertRaisesMessage(CommandError, "actor_must_be_active_superuser"):
            call_command(
                "merge_chair_units", "--org", self.org.slug, "--year", YEAR, "--actor", "merge_a",
                "--source", "SRC-kafedra", "--target", "TGT-kafedra", stdout=io.StringIO(),
            )  # fmt: skip
