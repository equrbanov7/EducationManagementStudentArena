"""MR-000250/251: real ORM dry-run / apply / idempotence / refusal / undo with a bounded synthetic packet."""

import copy
import datetime as dt
import hashlib
import io
import json
import tempfile
from contextlib import ExitStack
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.legacy_import.services import exact_syllabus_recovery as core
from apps.legacy_import.services import govher_syllabi_spec as spec
from apps.legacy_import.services import govher_syllabi_state as state
from apps.legacy_import.services.delta.syllabi import document_for
from apps.legacy_import.services.rehearsal_syllabus_targets import build_section_data
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar.models import CourseOffering, Lesson, Subject
from apps.syllabus.models import Syllabus, SyllabusSection, SyllabusVersion
from apps.syllabus.public import import_migrated_version, section_data_map, services
from apps.workload.models import TeacherAssignment, TeachingTask, TeachingTaskRow
from core.rls import bypass_rls

A, B = spec.CASES
ENGLISH = {"week": {"rows": [{"topic": "Access to the CIS. Definition of GIS", "lecture": 2, "seminar": 2}]}}


def source_for(case):
    pins = case["source"]
    if case["key"] == "mr250":
        hours = [("2", "2")] * 15
    else:
        hours = [("2", "")] * 15 + [("", "2")] * 7 + [("", "1")]
    week = [
        dict(
            id=900000 + i,
            uniqid=pins["uniqid"],
            movzu=f"M&ouml;vzu {case['key']} {i}",
            muh_saat=lecture,
            sem_saat=seminar,
            praktiki_saat="0",
            lab_saat="0",
            qeyd="",
        )
        for i, (lecture, seminar) in enumerate(hours)
    ]
    sections = {table: [[10, f"Mətn {table}"]] for table in spec.COMMON_TABLES}
    sections["sillabus_serbest_is"] = [[20 + i, f"Sərbəst iş {i}"] for i in range(case["selfwork_rows"])]
    source = {
        "id": pins["id"],
        "uniqid": pins["uniqid"],
        "lesson_id": pins["lesson_id"],
        "teacher_id": spec.SOURCE_AUTHOR,
        "ders_saati": pins["ders_saati"],
        "language": pins["language"],
        "active": 1,
        "week": week,
        "sections": sections,
    }
    journal = dict(
        case["journal"],
        name="Fixture - (2026/2027 Payız)",
        teacher_id=spec.SOURCE_AUTHOR,
        sillabus_id=pins["id"],
        active=1,
        fake=0,
        sonra_sil=0,
        kredit=4,
    )
    return {"source": source, "source_journal": journal}


class GovherSyllabiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.actor = User.objects.create_superuser("govher_admin", "admin@example.test", "test")
        with bypass_rls():
            cls.org = Organization.objects.create(
                id=spec.ORG, name="QKU", slug="qku", org_type="university", owner=cls.actor, status="active"
            )
            cls.teacher = User.objects.create_user(id=spec.AUTHOR, username="govher.test", first_name="Gövhər")
            UserProfile.objects.filter(user=cls.teacher).update(organization=cls.org)
            Membership.objects.create(user=cls.teacher, organization=cls.org, role=cls.org.roles.get(name="teacher"))
            cls.period = AcademicPeriod.objects.create(
                id=spec.PERIOD,
                organization=cls.org,
                name="Payız",
                academic_year="2026/2027",
                period_type="semester",
                start_date=dt.date(2026, 9, 1),
                end_date=dt.date(2027, 1, 31),
                is_current=True,
            )
            chair = OrgUnit.objects.create(
                organization=cls.org, name="Ekologiya", slug="govher-chair", unit_type="chair"
            )
            task = TeachingTask.objects.create(organization=cls.org, chair=chair, academic_year="2026/2027")
            cls.offerings = {}
            for case, code in ((A, "QKU-2436"), (B, "QKU-2669")):
                subject = Subject.objects.create(
                    id=case["subject_ids"][0], organization=cls.org, code=code, name=f"Fənn {code}"
                )
                group = OrgUnit.objects.create(
                    id=case["group_id"], organization=cls.org, name=case["key"], slug=case["key"], unit_type="group"
                )
                cls.offerings[case["key"]] = CourseOffering.objects.create(
                    id=case["offering_id"],
                    organization=cls.org,
                    subject=subject,
                    period=cls.period,
                    group=group,
                    instructor=cls.teacher,
                    lesson_hours=case["hours"],
                )
                row = TeachingTaskRow.objects.create(
                    id=case["workload_row"],
                    organization=cls.org,
                    task=task,
                    subject=subject,
                    period=cls.period,
                    lecture_plan=case["plan"]["lecture"],
                    seminar_plan=case["plan"]["seminar"],
                    lecture_total=case["plan"]["lecture"],
                    seminar_total=case["plan"]["seminar"],
                )
                row.groups.add(group)
                for activity, hours in case["plan"].items():
                    TeacherAssignment.objects.create(
                        organization=cls.org, row=row, teacher=cls.teacher, activity=activity, hours=hours
                    )
            cls.base, cls.english = import_migrated_version(
                organization=cls.org,
                subject=cls.offerings["mr250"].subject,
                author=cls.teacher,
                approved_at=timezone.now(),
                section_data=ENGLISH,
            )
            Lesson.objects.create(
                organization=cls.org, offering=cls.offerings["mr250"], date=dt.date(2026, 9, 15), kind="lecture"
            )

    def setUp(self):
        self.entries = {case["offering_id"]: source_for(case) for case in spec.CASES}
        cases = []
        for case in spec.CASES:
            entry = self.entries[case["offering_id"]]
            sections, _ = build_section_data(document_for(entry["source"]))
            pinned = copy.deepcopy(case)
            pinned.update(
                source_digest=core.digest(entry["source"]),
                journal_digest=core.digest(entry["source_journal"]),
                converted_digest=core.digest(sections),
                selfwork_topics=len(sections["self"]["topics"]),
            )
            if pinned["replace"]:
                pinned["replace"] = {
                    "syllabus_id": str(self.base.pk),
                    "version_id": str(self.english.pk),
                    "content_digest": core.digest(section_data_map(self.english)),
                }
            cases.append(pinned)
        self.cases = tuple(cases)
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        self.patches.enter_context(patch.object(spec, "CASES", self.cases))
        plans = {case["offering_id"]: case["plan"] for case in self.cases}
        self.patches.enter_context(
            patch.object(state, "plan_hours_for_offering", side_effect=lambda o: dict(plans[str(o.pk)]))
        )
        self.patches.enter_context(patch.object(state.timezone, "localdate", return_value=dt.date(2026, 11, 6)))

    def run_cmd(self, *, apply=False, undo="", entries=None):
        raw = json.dumps(
            {"format": spec.FORMAT, "organization_id": spec.ORG, "entries": entries or self.entries}, ensure_ascii=False
        ).encode()
        out = io.StringIO()
        with (
            tempfile.NamedTemporaryFile(suffix=".json") as file,
            patch.object(spec, "PACKET_SHA256", hashlib.sha256(raw).hexdigest()),
        ):
            file.write(raw)
            file.flush()
            kwargs = dict(org="qku", actor="govher_admin", apply=apply, stdout=out)
            if undo:
                kwargs["undo"] = undo
            else:
                kwargs.update(file=file.name, sha256=hashlib.sha256(raw).hexdigest())
            call_command("recover_govher_syllabi", **kwargs)
        return out.getvalue()

    def shown(self, key):
        return state.resolved_for(CourseOffering.objects.select_related("organization").get(pk=self.offerings[key].pk))

    def test_dry_apply_idempotent_and_exact_undo(self):
        lessons = list(Lesson.objects.values())
        dry = self.run_cmd()
        self.assertIn("mode=dry_run", dry)
        self.assertIn("versions_created=2", dry)
        self.assertIn("wrong_versions_archived=1", dry)
        self.assertEqual(SyllabusVersion.objects.get(pk=self.english.pk).status, "approved")
        self.assertFalse(Syllabus.objects.filter(offering=self.offerings["mr251"]).exists())

        output = self.run_cmd(apply=True)
        batch = output.split("batch=")[1].strip()
        base = self.shown("mr250")
        self.assertEqual(base.pk, self.base.pk)
        self.assertEqual(SyllabusVersion.objects.get(pk=self.english.pk).status, "archived")
        restored = base.approved_version
        self.assertEqual((restored.major, restored.status, restored.approval_source), (2, "approved", "migration"))
        self.assertEqual(restored.plan_hours, A["plan"])
        self.assertEqual(section_data_map(restored)["week"]["rows"][0]["topic"], "Mövzu mr250 0")
        created = self.shown("mr251")
        self.assertEqual(str(created.offering_id), str(self.offerings["mr251"].pk))
        self.assertEqual(created.author_id, spec.AUTHOR)
        self.assertEqual(created.approved_version.status, "approved")
        self.assertEqual(len(section_data_map(created.approved_version)["week"]["rows"]), 23)
        self.assertEqual(list(Lesson.objects.values()), lessons)

        self.assertIn("already_present=2", self.run_cmd(apply=True))
        self.assertIn("versions_archived=2", self.run_cmd(undo=batch))
        self.assertEqual(self.shown("mr250").approved_version_id, restored.pk)
        self.assertIn("versions_restored=1", self.run_cmd(apply=True, undo=batch))
        self.assertEqual(SyllabusVersion.objects.get(pk=self.english.pk).status, "approved")
        self.assertEqual(self.shown("mr250").approved_version_id, self.english.pk)
        self.assertEqual(SyllabusVersion.objects.get(pk=restored.pk).status, "archived")
        self.assertFalse(Syllabus.objects.get(pk=created.pk).is_active)
        self.assertIn("already_undone=1", self.run_cmd(apply=True, undo=batch))
        with self.assertRaisesMessage(CommandError, "previous_undo_requires_review"):
            self.run_cmd(apply=True)

    def blank_draft(self):
        offering = self.offerings["mr251"]
        syllabus, draft = services.create_draft(
            organization=self.org,
            subject=offering.subject,
            period=offering.period,
            offering=offering,
            author=self.teacher,
            actor=services.resolve_actor(self.actor, self.org),
        )
        return syllabus, draft

    def test_blank_draft_kept_in_archive_and_restored_on_undo(self):
        dossier, draft = self.blank_draft()
        batch = self.run_cmd(apply=True).split("batch=")[1].strip()
        dossier.refresh_from_db()
        self.assertEqual(SyllabusVersion.objects.get(pk=draft.pk).status, "archived")
        self.assertEqual(self.shown("mr251").pk, dossier.pk)
        self.assertEqual(dossier.current_version_id, dossier.approved_version_id)
        self.assertEqual(dossier.approved_version.major, 2)
        self.run_cmd(apply=True, undo=batch)
        dossier.refresh_from_db()
        self.assertEqual(SyllabusVersion.objects.get(pk=draft.pk).status, "draft")
        self.assertEqual(dossier.current_version_id, draft.pk)
        self.assertIsNone(dossier.approved_version_id)
        self.assertTrue(dossier.is_active)

    def test_teacher_written_draft_is_never_archived(self):
        _, draft = self.blank_draft()
        SyllabusSection.objects.filter(version=draft, section_id="week").update(
            data={"rows": [{"topic": "Müəllimin öz mövzusu", "lecture": 2}]}
        )
        with self.assertRaisesMessage(CommandError, "journal_draft_not_blank"):
            self.run_cmd(apply=True)
        self.assertEqual(SyllabusVersion.objects.get(pk=draft.pk).status, "draft")
        self.assertEqual(SyllabusVersion.objects.get(pk=self.english.pk).status, "approved")

    def test_tampered_source_and_changed_live_scope_refuse_without_writes(self):
        entries = copy.deepcopy(self.entries)
        entries[A["offering_id"]]["source"]["week"][0]["movzu"] = "Başqa mətn"
        with self.assertRaisesMessage(CommandError, "pinned_source_changed"):
            self.run_cmd(apply=True, entries=entries)
        with (
            patch.object(spec, "PACKET_SHA256", "0" * 64),
            self.assertRaisesMessage(CommandError, "pinned_source_packet_changed"),
        ):
            call_command(
                "recover_govher_syllabi", org="qku", actor="govher_admin", file=__file__, sha256="1" * 64, apply=True
            )
        CourseOffering.objects.filter(pk=self.offerings["mr251"].pk).update(lesson_hours=60)
        with self.assertRaisesMessage(CommandError, "live_journal_scope_changed"):
            self.run_cmd(apply=True)
        CourseOffering.objects.filter(pk=self.offerings["mr251"].pk).update(lesson_hours=45)
        SyllabusSection.objects.filter(version=self.english, section_id="week").update(data={"rows": []})
        with self.assertRaisesMessage(CommandError, "wrong_language_content_changed"):
            self.run_cmd(apply=True)
        self.assertEqual(SyllabusVersion.objects.filter(syllabus=self.base).count(), 1)
        self.assertFalse(Syllabus.objects.filter(offering=self.offerings["mr251"]).exists())

    def test_changed_official_workload_refuses(self):
        TeacherAssignment.objects.filter(row_id=B["workload_row"], activity="seminar").update(hours=10)
        with self.assertRaisesMessage(CommandError, "official_assignment_changed"):
            self.run_cmd(apply=True)

    def test_undo_refuses_after_later_change(self):
        batch = self.run_cmd(apply=True).split("batch=")[1].strip()
        version = self.shown("mr251").approved_version
        SyllabusSection.objects.filter(version=version, section_id="lit").update(data={"primary": ["Yeni"]})
        with self.assertRaisesMessage(CommandError, "undo_live_state_changed"):
            self.run_cmd(apply=True, undo=batch)
