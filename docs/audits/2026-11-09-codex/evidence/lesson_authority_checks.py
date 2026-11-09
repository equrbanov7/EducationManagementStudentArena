"""Offline regression checks for class scope and owner-present review IDs."""

import copy
import unittest

from prepare_lesson_authorities import ORG, PERIOD, generate


def fixture():
    def mapped(entity, label, source, target):
        return dict(
            id=entity + str(source),
            organization_id=ORG,
            source_system="myedu_mariadb",
            entity_type=entity,
            legacy_pk=str(source),
            target_model_label=label,
            target_pk=str(target),
            state="migrated",
        )

    course = dict(
        id="offering",
        organization_id=ORG,
        period_id=PERIOD,
        is_active=True,
        subject_id="subject",
        group_id="group",
        instructor_id=22,
    )
    tables = {
        "registrar.CourseOffering": [course],
        "organizations.AcademicPeriod": [dict(id=PERIOD, is_current=True, is_active=True, locked_at=None)],
        "registrar.Enrollment": [
            dict(id="e1", offering_id="offering", student_id=31, status="enrolled", lab_group=None, seminar_group=None),
            dict(id="e2", offering_id="offering", student_id=32, status="enrolled", lab_group=None, seminar_group=None),
        ],
        "registrar.Lesson": [],
        "registrar.LessonCorrection": [],
        "registrar.CorrectionReversal": [],
        "audit.AuditLog": [],
        "registrar.LabGroup": [],
        "registrar.SeminarGroup": [],
        "legacy_import.LegacyEntityMapVersion": [],
        "legacy_import.LegacyEntityMap": [
            mapped("worker", "auth.user", 2, 22),
            mapped("lesson_subject", "registrar.subject", 3, "subject"),
            mapped("group_unit", "organizations.orgunit", 4, "group"),
            mapped("student", "auth.user", 11, 31),
            mapped("student", "auth.user", 12, 32),
        ],
    }
    facts = {
        "journals": [
            dict(
                id=7,
                uniqid="U",
                teacher_id=2,
                lesson_id=3,
                groups_id="[4]",
                students_id="[11,12]",
                semestr=14,
                fake=0,
                sonra_sil=0,
            )
        ],
        "metadata": [dict(id=8, journal_id=7, fake=0, date="2026-10-01", times="08:30", saatliq_ders=1)],
        "all_slot_points": [dict(id=100, student_id=11, point="qb"), dict(id=101, student_id=12, point="0")],
    }
    probe = {
        "candidate_point_count": 247,
        "slots": [
            dict(
                offering_id="offering",
                legacy_journal_id=7,
                date="2026-10-01",
                start_time="08:30",
                kind="lecture",
                has_real_source_attendance_or_score=True,
                legacy_point_ids=[100, 101],
                exact_point_slot_and_student_match=True,
                metadata_kind_matches_points=True,
                metadata_ids=[8],
                explicit_pair_hours=2,
                source_fact_sha256="a" * 64,
            )
        ],
    }
    return {"tables": tables}, facts, probe


class ClassAuthorityChecks(unittest.TestCase):
    def test_nullable_end_owner_present_and_zero_grade_preserved(self):
        snapshot, facts, probe = fixture()
        before = copy.deepcopy(facts)
        result = generate(snapshot, facts, probe, capture_sha256="b" * 64)
        self.assertEqual(len(result["class_authorities"]), 1)
        self.assertIsNone(result["class_authorities"][0]["slot"]["end_time"])
        self.assertEqual(result["reviewed_owner_present_source_ids"], ["100"])
        self.assertEqual(facts, before)

    def test_absent_only_class_is_not_excluded_by_old_import_policy(self):
        snapshot, facts, probe = fixture()
        facts["all_slot_points"][1]["point"] = "qb"
        probe["slots"][0]["has_real_source_attendance_or_score"] = False
        result = generate(snapshot, facts, probe, capture_sha256="b" * 64)
        self.assertEqual(len(result["class_authorities"]), 1)
        self.assertEqual(result["reviewed_owner_present_source_ids"], ["100", "101"])

    def test_student_roster_drift_holds_whole_lecture(self):
        snapshot, facts, probe = fixture()
        facts["journals"][0]["students_id"] = "[11]"
        result = generate(snapshot, facts, probe, capture_sha256="b" * 64)
        self.assertFalse(result["class_authorities"])
        self.assertEqual(result["held_classes"][0]["code"], "lecture_roster_scope_changed")

    def test_formal_subgroup_exact_roster_can_be_proven(self):
        snapshot, facts, probe = fixture()
        probe["slots"][0].update(kind="seminar", legacy_point_ids=[100])
        facts["journals"][0]["students_id"] = "[11]"
        snapshot["tables"]["registrar.Enrollment"][0]["seminar_group"] = 1
        snapshot["tables"]["registrar.Enrollment"][1]["seminar_group"] = 2
        snapshot["tables"]["registrar.SeminarGroup"] = [
            dict(offering_id="offering", number=1),
            dict(offering_id="offering", number=2),
        ]
        result = generate(snapshot, facts, probe, capture_sha256="b" * 64)
        self.assertEqual(result["class_authorities"][0]["slot"]["seminar_group"], 1)

    def test_full_roster_does_not_guess_subgroup(self):
        snapshot, facts, probe = fixture()
        probe["slots"][0]["kind"] = "lab"
        snapshot["tables"]["registrar.Enrollment"][0]["lab_group"] = 1
        snapshot["tables"]["registrar.Enrollment"][1]["lab_group"] = 2
        result = generate(snapshot, facts, probe, capture_sha256="b" * 64)
        self.assertFalse(result["class_authorities"])
        self.assertEqual(result["held_classes"][0]["code"], "source_roster_subgroup_not_unique")

    def test_same_day_other_time_is_never_merged_or_duplicated(self):
        snapshot, facts, probe = fixture()
        snapshot["tables"]["registrar.Lesson"] = [
            dict(offering_id="offering", date="2026-10-01", kind="lecture", start_time="10:10:00")
        ]
        result = generate(snapshot, facts, probe, capture_sha256="b" * 64)
        self.assertEqual(result["held_classes"][0]["code"], "same_day_retime_or_native_merge_review")
        self.assertFalse(result["reviewed_owner_present_source_ids"])

    def test_documented_retime_never_reappears_as_new_class(self):
        snapshot, facts, probe = fixture()
        snapshot["tables"]["registrar.LessonCorrection"] = [
            dict(
                id="correction",
                old_date="2026-10-01",
                old_kind="lecture",
                old_time="08:30",
                lesson_id=None,
                old_instructor_id=22,
            )
        ]
        result = generate(snapshot, facts, probe, capture_sha256="b" * 64)
        self.assertFalse(result["class_authorities"])
        self.assertEqual(result["held_classes"][0]["code"], "formal_lesson_correction_or_deletion_requires_review")

    def test_new_owner_policy_is_explicit_over_native_empty_cleanup(self):
        snapshot, facts, probe = fixture()
        snapshot["tables"]["audit.AuditLog"] = [
            dict(
                id="cleanup",
                organization_id=ORG,
                resource_id="offering",
                resource_type="legacy_import.empty_lesson",
                action="delete",
                old_values={
                    "lessons": [
                        dict(date="2026-10-01", start_time="08:30", kind="lecture", marks=[dict(status="absent")])
                    ]
                },
            )
        ]
        result = generate(snapshot, facts, probe, capture_sha256="b" * 64)
        self.assertEqual(result["class_authorities"][0]["reviewed_empty_cleanup_overrides"][0]["audit_id"], "cleanup")
        snapshot["tables"]["audit.AuditLog"][0]["old_values"]["lessons"][0]["marks"][0]["status"] = "present"
        self.assertFalse(generate(snapshot, facts, probe, capture_sha256="b" * 64)["class_authorities"])

    def test_changed_hours_or_foreign_teacher_hold(self):
        for mutate in ("hours", "teacher"):
            snapshot, facts, probe = fixture()
            if mutate == "hours":
                facts["metadata"][0]["saatliq_ders"] = 2
            else:
                snapshot["tables"]["registrar.CourseOffering"][0]["instructor_id"] = 99
            self.assertFalse(generate(snapshot, facts, probe, capture_sha256="b" * 64)["class_authorities"])


if __name__ == "__main__":
    unittest.main()
