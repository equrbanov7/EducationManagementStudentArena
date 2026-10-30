"""A scalar45 source stays intact while an explicitly sealed three-group plan uses15."""

import copy
import json
from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.workload.services import reviewed_source_geometry as geometry
from apps.workload.services.reviewed_batch_manifest import ORG, YEAR, select_manifest
from apps.workload.services.sbio235_state import RepairError


def entry():
    values = {season + "_" + kind: None for season in ("fall", "spring") for kind in ("lecture", "seminar", "lab")}
    values.update(fall_lecture=30, fall_seminar=45, credits=4, subject="İqtisadiyyatın əsasları")
    return {
        "ready_class": "existing_owner_no_load",
        "source_reference": {
            "line": 55,
            "selection_id": 105,
            "season": "fall",
            "sha256": geometry.SOURCE_SHA,
            "values": values,
        },
        "desired_row": {
            "task_id": geometry.TASK,
            "subject_id": geometry.SUBJECT,
            "period_id": geometry.PERIOD,
            "season": "fall",
            "group_ids": sorted(geometry.GROUPS),
            "degree_level": "bachelor",
            "education_form": "full_time",
            "groups_text": "936 BM / 136 P / 136 F",
            "credits": 4,
        },
        "desired_contacts": {"lecture": 30, "seminar": 45, "lab": 0},
        "expected_assignments": [
            {"teacher_id": geometry.TEACHER, "activity": activity, "hours": hours, "is_hourly_paid": False}
            for activity, hours in (("lecture", 30), ("seminar", 45))
        ],
        "teacher_identity": [{"id": geometry.TEACHER}],
        "selected_subject_id": geometry.SUBJECT,
        "subject_candidates": [{"id": geometry.SUBJECT, "code": "QKU-SOURCE105", "name": "İqtisadiyyatın əsasları"}],
        "existing_rows": [],
        "existing_journals": [
            {
                "id": jid,
                "group_id": gid,
                "subject_id": geometry.SUBJECT,
                "period_id": geometry.PERIOD,
                "instructor_id": geometry.TEACHER,
                "is_active": True,
                "lesson_hours": 45,
            }
            for jid, gid in geometry.JOURNALS.items()
        ],
        "physical_source_groups": [{"id": gid} for gid in sorted(geometry.GROUPS)],
        "reviewed_policy": {geometry.KEY: copy.deepcopy(geometry.POLICY)},
    }


def plan(value):
    return select_manifest(
        {
            "format": "reviewed-workload-source/2",
            "organization_id": ORG,
            "academic_year": YEAR,
            "chair_id": "00000000-0000-4000-8000-000000000001",
            "source_entries": [value],
        },
        sha256="f" * 64,
        lines=[105],
    )


class ReviewedSourceGeometryTests(SimpleTestCase):
    def test_source_scalar_is_preserved_and_paid_totals_are_not_tripled(self):
        value = entry()
        before = json.dumps(value, sort_keys=True)
        item = plan(value).items[0]
        self.assertEqual(item["plan"], {"lecture": 30, "seminar": 15, "lab": 0})
        self.assertEqual(item["totals"], {"lecture": 30, "seminar": 45, "lab": 0})
        self.assertEqual((item["contacts"], item["union_count"], item["subgroup_count"]), (45, 1, 3))
        self.assertEqual(sum(a["hours"] for a in item["assignments"]), 75)
        self.assertEqual(json.dumps(value, sort_keys=True), before)
        self.assertEqual(value["source_reference"]["values"]["fall_seminar"], 45)

    def test_unreviewed_scalar_keeps_ordinary_parser_behavior(self):
        value = entry()
        value.pop("reviewed_policy")
        item = plan(value).items[0]
        self.assertEqual((item["plan"]["seminar"], item["contacts"], item["subgroup_count"]), (45, 75, 1))

    def test_source_proof_or_exact_course_mismatch_is_rejected(self):
        mutations = [
            lambda e: e["source_reference"].update(sha256="a" * 64),
            lambda e: e["source_reference"].update(line=54),
            lambda e: e["source_reference"].update(selection_id=104),
            lambda e: e["source_reference"].update(season="spring"),
            lambda e: e["source_reference"]["values"].update(fall_seminar="15*3"),
            lambda e: e["desired_row"].update(task_id="00000000-0000-4000-8000-000000000001"),
            lambda e: e["desired_row"]["group_ids"].pop(),
            lambda e: e["expected_assignments"][0].update(teacher_id=42),
            lambda e: e["teacher_identity"][0].update(id=42),
            lambda e: e["existing_journals"][0].update(lesson_hours=75),
            lambda e: e["existing_journals"][0].update(instructor_id=42),
            lambda e: e["existing_journals"][0].update(group_id=e["existing_journals"][1]["group_id"]),
            lambda e: e["existing_journals"].pop(),
            lambda e: e["reviewed_policy"][geometry.KEY].update(evidence_sha256="b" * 64),
            lambda e: e["reviewed_policy"][geometry.KEY].update(union_count=True),
            lambda e: e["reviewed_policy"].update(join_chair={}),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutations.index(mutate)):
                value = entry()
                mutate(value)
                with self.assertRaises((RepairError, KeyError)):
                    plan(value)

    def test_foreign_tenant_and_version_one_do_not_receive_exception(self):
        value = entry()
        raw = {
            "format": "reviewed-workload-source/1",
            "organization_id": ORG,
            "academic_year": YEAR,
            "chair_id": "00000000-0000-4000-8000-000000000001",
            "source_entries": [value],
        }
        with self.assertRaises(RepairError):
            select_manifest(raw, sha256="f" * 64, lines=[105])
        raw.update(format="reviewed-workload-source/2", organization_id="00000000-0000-4000-8000-000000000002")
        with self.assertRaises(RepairError):
            select_manifest(raw, sha256="f" * 64, lines=[105])

    def test_live_journal_capacity_owner_and_group_identity_are_guarded(self):
        item = plan(entry()).items[0]
        jid, gid = next(iter(geometry.JOURNALS.items()))
        value = dict(
            pk=jid,
            group_id=gid,
            subject_id=geometry.SUBJECT,
            period_id=geometry.PERIOD,
            instructor_id=geometry.TEACHER,
            lesson_hours=45,
            is_active=True,
        )
        geometry.validate_current(item, SimpleNamespace(**value))
        for field, replacement in (
            ("group_id", "wrong"),
            ("lesson_hours", 75),
            ("instructor_id", 42),
            ("is_active", False),
        ):
            with self.subTest(field=field), self.assertRaisesMessage(RepairError, "live_journal_context_changed"):
                geometry.validate_current(item, SimpleNamespace(**{**value, field: replacement}))
