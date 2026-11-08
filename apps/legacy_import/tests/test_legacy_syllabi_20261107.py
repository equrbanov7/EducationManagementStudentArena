"""recover_legacy_syllabi_20261107: real ORM dry-run / apply / idempotence / skips / undo with a synthetic repo plan."""

import copy
import datetime as dt
import hashlib
import io
import json
import tempfile
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.legacy_import.services import exact_syllabus_recovery as core
from apps.legacy_import.services import legacy_syllabi_20261107_plan as plan_module
from apps.legacy_import.services import legacy_syllabi_20261107_state as state
from apps.legacy_import.services.delta.syllabi import document_for
from apps.legacy_import.services.rehearsal_syllabus_targets import build_section_data
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar.models import CourseOffering, Lesson, Subject
from apps.syllabus.models import Syllabus, SyllabusSection, SyllabusVersion
from apps.syllabus.public import import_migrated_version, section_data_map, services
from core.rls import bypass_rls

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"
L30S15 = {"lecture": 30, "seminar": 15}
ENGLISH = {"week": {"rows": [{"topic": "Access to the CIS", "lecture": 2, "seminar": 2}]}}
UUIDS = {
    name: f"00000000-0000-4000-8000-{index:012d}"
    for index, name in enumerate(
        ("g_create", "g_replace", "g_plan", "g_missing", "s_create", "s_replace", "s_plan", "o_create", "o_replace"),
        start=1,
    )
}
UUIDS["o_plan"] = "00000000-0000-4000-8000-000000000099"


def sections_for(topic):
    week = [
        dict(
            id=900 + i,
            uniqid="U",
            movzu=f"{topic} {i}",
            muh_saat=m,
            sem_saat=s,
            praktiki_saat="0",
            lab_saat="0",
            qeyd="",
        )
        for i, (m, s) in enumerate([("2", "")] * 15 + [("", "2")] * 7 + [("", "1")])
    ]
    row = {
        "id": 1,
        "uniqid": "U",
        "lesson_id": 1,
        "teacher_id": 85,
        "ders_saati": 45,
        "language": "az",
        "active": 1,
        "week": week,
        "sections": {
            "sillabus_tesviri_ve_meqsedi": [[1, "Fənnin təsviri"]],
            "sillabus_qarsilama_mesaji": [[2, "Xoş gəlmisiniz, mən sizin müəllimiz"]],
            "sillabus_elmi_maraq": [[3, "Elmi maraqlarım"]],
            "sillabus_derslikler": [[4, "1. Dərslik. Bakı, 2010"]],
        },
    }
    sections, _ = build_section_data(document_for(row))
    sections["info"].update(plan_module.PERSONAL_INFO)
    sections["assess"]["exam_questions"] = []
    return sections


class LegacySyllabiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.actor = User.objects.create_superuser("lgsyl_admin", "admin@example.test", "test")
        with bypass_rls():
            cls.org = Organization.objects.create(
                id=ORG, name="QKU", slug="qku", org_type="university", owner=cls.actor, status="active"
            )
            cls.teacher = User.objects.create_user(username="lgsyl.teacher", first_name="Müəllim")
            UserProfile.objects.filter(user=cls.teacher).update(organization=cls.org)
            Membership.objects.create(user=cls.teacher, organization=cls.org, role=cls.org.roles.get(name="teacher"))
            cls.period = AcademicPeriod.objects.create(
                id=PERIOD,
                organization=cls.org,
                name="Payız",
                academic_year="2026/2027",
                period_type="semester",
                start_date=dt.date(2026, 9, 1),
                end_date=dt.date(2027, 1, 31),
                is_current=True,
            )
            cls.offerings = {}
            for key in ("create", "replace", "plan"):
                subject = Subject.objects.create(
                    id=UUIDS[f"s_{key}"], organization=cls.org, code=f"QKU-9{len(key)}{key[0]}", name=f"Fənn {key}"
                )
                group = OrgUnit.objects.create(
                    id=UUIDS[f"g_{key}"], organization=cls.org, name=key, slug=f"lgsyl-{key}", unit_type="group"
                )
                cls.offerings[key] = CourseOffering.objects.create(
                    id=UUIDS[f"o_{key}"],
                    organization=cls.org,
                    subject=subject,
                    period=cls.period,
                    group=group,
                    instructor=cls.teacher,
                    lesson_hours=45,
                )
            OrgUnit.objects.create(
                id=UUIDS["g_missing"], organization=cls.org, name="missing", slug="lgsyl-missing", unit_type="group"
            )
            create = cls.offerings["create"]
            cls.base, cls.english = import_migrated_version(
                organization=cls.org,
                subject=create.subject,
                author=cls.teacher,
                approved_at=timezone.now(),
                section_data=ENGLISH,
            )
            replace = cls.offerings["replace"]
            cls.own, cls.wrong = import_migrated_version(
                organization=cls.org,
                subject=replace.subject,
                period=cls.period,
                offering=replace,
                author=cls.teacher,
                approved_at=timezone.now(),
                plan_hours={"lecture": 15},
                section_data={"week": {"rows": [{"topic": "Yalnız mühazirə", "lecture": 2}]}},
            )
            plan_offering = cls.offerings["plan"]
            cls.planned, cls.planned_version = import_migrated_version(
                organization=cls.org,
                subject=plan_offering.subject,
                period=cls.period,
                offering=plan_offering,
                author=cls.teacher,
                approved_at=timezone.now(),
                plan_hours={"lecture": 45},
                section_data=sections_for("Plan"),
            )
            Lesson.objects.create(organization=cls.org, offering=create, date=dt.date(2026, 9, 15), kind="lecture")

    def target(self, key, offering, group, subject, action, **extra):
        row = {
            "key": key,
            "teacher": self.teacher.pk,
            "offering_id": offering and UUIDS[offering],
            "group_id": UUIDS[group],
            "subject_ids": [UUIDS[subject]],
            "lesson_hours": 45,
            "plan": dict(L30S15),
            "action": action,
        }
        row.update(extra)
        return row

    def setUp(self):
        sections = sections_for("Mövzu")
        self.plan = {
            "format": plan_module.FORMAT,
            "organization_id": ORG,
            "period_id": PERIOD,
            "sources": {
                "7584": {
                    "teacher": self.teacher.pk,
                    "legacy_teacher": 85,
                    "legacy_lesson": 1934,
                    "hours": dict(L30S15),
                    "excluded": ["welcome"],
                    "content_sha256": core.digest(sections),
                    "sections": sections,
                }
            },
            "targets": [
                self.target(
                    "t01",
                    "o_create",
                    "g_create",
                    "s_create",
                    "restore",
                    source="7584",
                    retire_base={
                        "syllabus_id": str(self.base.pk),
                        "version_id": str(self.english.pk),
                        "content_digest": core.digest(section_data_map(self.english)),
                    },
                ),
                self.target("t02", "o_replace", "g_replace", "s_replace", "restore", source="7584"),
                self.target("t03", "o_plan", "g_plan", "s_plan", "plan_sync"),
                self.target("t04", None, "g_missing", "s_create", "restore", source="7584"),
            ],
        }
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        self.plans = {UUIDS[f"o_{key}"]: dict(L30S15) for key in ("create", "replace", "plan")}
        self.patches.enter_context(
            patch.object(state, "plan_hours_for_offering", side_effect=lambda o: dict(self.plans[str(o.pk)]))
        )
        self.patches.enter_context(patch.object(state.timezone, "localdate", return_value=dt.date(2026, 11, 7)))

    def run_cmd(self, *, apply=False, undo="", plan=None):
        raw = json.dumps(plan or self.plan, ensure_ascii=False, sort_keys=True).encode()
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "plan.json"
            path.write_bytes(raw)
            with (
                patch.object(plan_module, "PLAN_PATH", path),
                patch.object(plan_module, "PLAN_SHA256", hashlib.sha256(raw).hexdigest()),
            ):
                kwargs = dict(org="qku", actor="lgsyl_admin", apply=apply, stdout=out)
                if undo:
                    kwargs["undo"] = undo
                call_command("recover_legacy_syllabi_20261107", **kwargs)
        return out.getvalue()

    def shown(self, key):
        return state.resolved_for(CourseOffering.objects.select_related("organization").get(pk=self.offerings[key].pk))

    def test_dry_apply_idempotent_and_exact_undo(self):
        lessons = list(Lesson.objects.values())
        dry = self.run_cmd()
        self.assertIn("legacy_syllabi: mode=dry_run", dry)
        self.assertIn("created=1", dry)
        self.assertIn("replaced=1", dry)
        self.assertIn("plan_synced=1", dry)
        self.assertIn("skipped_journal_missing=1", dry)
        self.assertIn("legacy_syllabi: entry=t04 result=skipped_journal_missing", dry)
        self.assertNotIn("batch=", dry)
        self.assertFalse(Syllabus.objects.filter(offering=self.offerings["create"]).exists())
        self.assertEqual(SyllabusVersion.objects.get(pk=self.english.pk).status, "approved")

        output = self.run_cmd(apply=True)
        batch = output.split("batch=")[1].strip()
        created = self.shown("create")
        self.assertEqual(str(created.offering_id), UUIDS["o_create"])
        self.assertEqual(
            (created.approved_version.status, created.approved_version.approval_source), ("approved", "migration")
        )
        self.assertEqual(created.approved_version.plan_hours, L30S15)
        data = section_data_map(created.approved_version)
        self.assertEqual(data["info"]["welcome"], "")
        self.assertEqual(data["info"]["research_interests"], [])
        self.assertEqual(data["week"]["rows"][0]["topic"], "Mövzu 0")
        self.assertEqual(SyllabusVersion.objects.get(pk=self.english.pk).status, "archived")
        replaced = self.shown("replace")
        self.assertEqual(replaced.pk, self.own.pk)
        self.assertEqual(replaced.approved_version.major, 2)
        self.assertEqual(SyllabusVersion.objects.get(pk=self.wrong.pk).status, "archived")
        self.assertEqual(SyllabusVersion.objects.get(pk=self.planned_version.pk).plan_hours, L30S15)
        self.assertEqual(list(Lesson.objects.values()), lessons)

        again = self.run_cmd(apply=True)
        self.assertIn("already_ok=3", again)
        self.assertNotIn("batch=", again)

        self.assertIn("versions_archived=2", self.run_cmd(undo=batch))
        self.assertEqual(self.shown("create").pk, created.pk)
        undone = self.run_cmd(apply=True, undo=batch)
        self.assertIn("plans_restored=1", undone)
        self.assertIn("base_versions_restored=1", undone)
        self.assertEqual(SyllabusVersion.objects.get(pk=self.english.pk).status, "approved")
        self.assertEqual(self.shown("create").pk, self.base.pk)
        self.assertFalse(Syllabus.objects.get(pk=created.pk).is_active)
        self.assertEqual(SyllabusVersion.objects.get(pk=self.wrong.pk).status, "approved")
        self.assertEqual(self.shown("replace").approved_version_id, self.wrong.pk)
        self.assertEqual(SyllabusVersion.objects.get(pk=self.planned_version.pk).plan_hours, {"lecture": 45})
        self.assertIn("already_undone=1", self.run_cmd(apply=True, undo=batch))

    def test_teacher_draft_and_changed_plan_skip_only_that_target(self):
        services.create_next_version(
            syllabus=self.own, actor=services.resolve_actor(self.actor, self.org), kind="minor"
        )
        draft = SyllabusVersion.objects.get(syllabus=self.own, status="draft")
        SyllabusSection.objects.filter(version=draft, section_id="week").update(
            data={"rows": [{"topic": "Müəllimin öz mövzusu", "lecture": 2}]}
        )
        self.plans[UUIDS["o_plan"]] = {"lecture": 45}
        output = self.run_cmd(apply=True)
        self.assertIn("entry=t02 result=skipped_teacher_content", output)
        self.assertIn("entry=t03 result=skipped_plan_changed", output)
        self.assertIn("entry=t01 result=created", output)
        self.assertEqual(SyllabusVersion.objects.get(pk=draft.pk).status, "draft")
        self.assertEqual(SyllabusVersion.objects.get(pk=self.wrong.pk).status, "approved")
        self.assertEqual(SyllabusVersion.objects.get(pk=self.planned_version.pk).plan_hours, {"lecture": 45})

    def test_personal_or_tampered_plan_refuses_without_writes(self):
        plan = copy.deepcopy(self.plan)
        plan["sources"]["7584"]["sections"]["info"]["welcome"] = "Xoş gəlmisiniz"
        with self.assertRaisesMessage(CommandError, "personal_content_present"):
            self.run_cmd(apply=True, plan=plan)
        plan = copy.deepcopy(self.plan)
        plan["sources"]["7584"]["sections"]["desc"]["description"] = "Əlaqə: muellim@example.az"
        with self.assertRaisesMessage(CommandError, "personal_content_present"):
            self.run_cmd(apply=True, plan=plan)
        plan = copy.deepcopy(self.plan)
        plan["sources"]["7584"]["sections"]["week"]["rows"][0]["topic"] = "Başqa"
        with self.assertRaisesMessage(CommandError, "source_content_changed"):
            self.run_cmd(apply=True, plan=plan)
        with (
            patch.object(plan_module, "PLAN_SHA256", "0" * 64),
            self.assertRaisesMessage(CommandError, "pinned_plan_changed"),
        ):
            call_command("recover_legacy_syllabi_20261107", org="qku", actor="lgsyl_admin", apply=True)
        self.assertFalse(Syllabus.objects.filter(offering=self.offerings["create"]).exists())

    def test_week_gap_restore_takes_official_plan_hours_and_source_topics(self):
        # Sahib 2026-11-09 (235 EM Tətbiqi riyaziyyat): köhnə sillabus L30+S15, rəsmi plan L30+S30 — yalnız
        # ``week_gap_ok`` ilə; mövzular artırılmır, plan saatı rəsmi yükdən.
        plan = copy.deepcopy(self.plan)
        target = next(t for t in plan["targets"] if t["key"] == "t01")
        target.update(plan={"lecture": 30, "seminar": 30}, lesson_hours=60)
        with self.assertRaisesMessage(CommandError, "target_source_mismatch"):
            self.run_cmd(apply=True, plan=plan)
        target["week_gap_ok"] = True
        CourseOffering.objects.filter(pk=self.offerings["create"].pk).update(lesson_hours=60)
        self.plans[UUIDS["o_create"]] = {"lecture": 30, "seminar": 30}
        output = self.run_cmd(apply=True, plan=plan)
        self.assertIn("entry=t01 result=created", output)
        shown = self.shown("create")
        self.assertEqual(shown.approved_version.plan_hours, {"lecture": 30, "seminar": 30})
        self.assertEqual(
            section_data_map(shown.approved_version)["week"], self.plan["sources"]["7584"]["sections"]["week"]
        )
        bad = copy.deepcopy(plan)
        bad["targets"][0]["plan"] = {"lecture": 30, "seminar": 30, "lab": 5}
        bad["targets"][0]["lesson_hours"] = 65
        with self.assertRaisesMessage(CommandError, "target_source_mismatch"):
            self.run_cmd(apply=True, plan=bad)

    def test_previous_receipt_and_changed_scope_skip(self):
        self.plan["targets"][0]["skip_if_receipt"] = "legacy_import.govher_own_syllabi"
        core.log_action(
            action=core.AuditAction.UPDATE,
            user=self.actor,
            organization=self.org,
            resource_type="legacy_import.govher_own_syllabi",
            resource_id="govsyl-20261106-120000-abcd",
            resource_repr="x",
            reason="MR-000250/251 own legacy syllabus restore",
            new_values={},
        )
        CourseOffering.objects.filter(pk=self.offerings["replace"].pk).update(lesson_hours=60)
        output = self.run_cmd(apply=True)
        self.assertIn("entry=t01 result=skipped_previously_restored", output)
        self.assertIn("entry=t02 result=skipped_hours_changed", output)
        self.assertFalse(Syllabus.objects.filter(offering=self.offerings["create"]).exists())

    def test_undo_refuses_after_later_change(self):
        batch = self.run_cmd(apply=True).split("batch=")[1].strip()
        version = self.shown("create").approved_version
        SyllabusSection.objects.filter(version=version, section_id="lit").update(data={"primary": ["Yeni"]})
        with self.assertRaisesMessage(CommandError, "undo_live_state_changed"):
            self.run_cmd(apply=True, undo=batch)
        self.assertEqual(SyllabusVersion.objects.get(pk=self.english.pk).status, "archived")
