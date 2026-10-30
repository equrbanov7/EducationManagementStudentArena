"""Strict sealed identity comparisons with privacy-safe operator diagnostics."""

from copy import deepcopy
from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.workload.services.tspx_roster_state import _identity_error, _identity_record_mismatches


class RosterIdentityDiagnosticsTests(SimpleTestCase):
    def setUp(self):
        self.record = SimpleNamespace(
            student=SimpleNamespace(is_active=True, first_name="Exact first", last_name="Exact last"),
            status="enrolled",
            group_id="parent-fk",
            admission_year=2025,
            program_id="program-fk",
            curriculum_id="curriculum-fk",
        )
        self.profile = SimpleNamespace(patronymic="Exact father")
        self.item = {
            "target_group_id": "child-fk",
            "keep_admission_year": 2025,
            "keep_program_id": "program-fk",
            "keep_curriculum_id": "curriculum-fk",
            "source_identity": {
                "first_name": "Exact first",
                "last_name": "Exact last",
                "patronymic": "Exact father",
            },
        }

    def mismatch(self, record=None, profile=None, item=None):
        return _identity_record_mismatches(
            record or self.record, profile or self.profile, item or self.item, "parent-fk"
        )

    def test_same_person_parent_and_exact_child_are_accepted(self):
        self.assertEqual(self.mismatch(), ())
        self.record.group_id = "child-fk"
        self.record.student.first_name = " EXACT  FIRST "
        self.assertEqual(self.mismatch(), ())

    def test_every_identity_and_record_predicate_remains_strict(self):
        cases = (
            ("user_active", "student.is_active", False),
            ("record_status", "status", "expelled"),
            ("record_group", "group_id", "other-fk"),
            ("admission_year", "admission_year", 2026),
            ("program", "program_id", "other-program"),
            ("curriculum", "curriculum_id", "other-curriculum"),
            ("first_name", "student.first_name", "Changed first"),
            ("last_name", "student.last_name", "Changed last"),
        )
        for code, path, value in cases:
            with self.subTest(code=code):
                record = deepcopy(self.record)
                target, field = (record.student, path.split(".")[1]) if "." in path else (record, path)
                setattr(target, field, value)
                self.assertEqual(self.mismatch(record=record), (code,))
        self.profile.patronymic = "Changed father"
        self.assertEqual(self.mismatch(), ("patronymic",))

    def test_error_contains_only_manifest_slot_and_static_field_codes(self):
        self.record.student.first_name = "Private changed first"
        self.profile.patronymic = "Private changed father"
        error = _identity_error(17, self.mismatch())
        self.assertEqual(
            error,
            "tspx_live_student_identity_or_record_changed:source_slot=17:fields=first_name,patronymic",
        )
        for private in ("Private", "parent-fk", "program-fk", "curriculum-fk", "Exact"):
            self.assertNotIn(private, error)

    def test_diagnostics_do_not_normalize_father_suffix_or_html(self):
        for value in ("Exact father oğlu", "Exact &amp; father"):
            with self.subTest(value=value):
                self.profile.patronymic = value
                self.assertEqual(self.mismatch(), ("patronymic",))
