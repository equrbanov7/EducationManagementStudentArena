"""Existing empty children can receive a parent roster without duplicates."""

from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.organizations.models import OrgUnit
from apps.organizations.subgroup_targets import reusable_children, validated_parent
from apps.registrar.models import Enrollment, Lesson, LessonMark
from core.constants import OrgUnitType

from .test_groups_registry_split import _SplitBase


class ExistingSubgroupsTest(_SplitBase):
    def setUp(self):
        super().setUp()
        self.group.name = "135 TSPX"
        self.group.save(update_fields=["name"])

    def _child(self, name="135TSPX-1", *, linked=False, parent=None, settings=None, active=True):
        metadata = dict(self.group.settings or {})
        if linked:
            metadata["parent_group"] = str((parent or self.group).pk)
        metadata.update(settings or {})
        return OrgUnit.objects.create(
            organization=self.org,
            parent=self.specialty,
            unit_type=OrgUnitType.GROUP,
            name=name,
            slug="existing-" + str(OrgUnit.objects.count()),
            settings=metadata,
            is_active=active,
        )

    def _add(self, child, records):
        return self._client("teaching_office_head").post(
            reverse("organizations:group_action", kwargs={"slug": self.org.slug}),
            {"action": "add_students", "id": str(child.pk), "record_ids": ",".join(str(r.pk) for r in records)},
        )

    def _candidates(self, child):
        return self._client("teaching_office_head").get(
            reverse("organizations:group_student_candidates", kwargs={"slug": self.org.slug, "unit_id": child.pk})
        )

    def test_split_reuses_both_legacy_children_and_keeps_ids(self):
        first, second = self._child(), self._child("135 TSPX-2")
        before = OrgUnit.objects.count()
        response = self._split(
            "teaching_office_head", self._payload(self.students[:2], self.students[2:], ("135 TSPX-1", "135 TSPX-2"))
        )
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual({row["id"] for row in body["created"]}, {str(first.pk), str(second.pk)})
        self.assertTrue(all(row["reused"] for row in body["created"]))
        self.assertEqual(OrgUnit.objects.count(), before)
        self.assertEqual(body["moved"], 3)
        self.assertEqual(body["remaining"], 0)
        from apps.registrar.group_academic import group_subgroups

        family = group_subgroups(self.group)
        self.assertEqual({row["name"]: row["count"] for row in family["children"]}, {first.name: 2, second.name: 1})
        first.refresh_from_db()
        self.assertEqual(first.settings["parent_group"], str(self.group.pk))
        for student, target in zip(self.students, (first, first, second)):
            student.refresh_from_db()
            self.assertEqual(student.group_id, target.pk)

    def test_individual_add_lists_parent_students_and_binds_legacy_child(self):
        child = self._child()
        before = self._candidates(child)
        self.assertEqual(before.status_code, 200, before.content)
        self.assertEqual({row["id"] for row in before.json()["results"]}, {str(r.pk) for r in self.students})
        response = self._add(child, [self.students[0]])
        self.assertEqual(response.status_code, 200, response.content)
        self.students[0].refresh_from_db()
        self.assertEqual(self.students[0].group_id, child.pk)
        child.refresh_from_db()
        self.assertEqual(child.settings["parent_group"], str(self.group.pk))
        # Once nonempty, the persisted validated link keeps the remaining candidates available.
        self.assertEqual(len(self._candidates(child).json()["results"]), 2)
        self.assertEqual(self._add(child, [self.students[1]]).status_code, 200)

    def test_reused_child_keeps_parent_mark_and_transfer_history(self):
        child = self._child(linked=True)
        old = Enrollment.objects.create(organization=self.org, offering=self.offering, student=self.students[0].student)
        lesson = Lesson.objects.create(
            organization=self.org, offering=self.offering, date=self.period.start_date, kind="seminar"
        )
        mark = LessonMark.objects.create(organization=self.org, enrollment=old, lesson=lesson, score=9)
        response = self._add(child, [self.students[0]])
        self.assertEqual(response.status_code, 200, response.content)
        old.refresh_from_db()
        mark.refresh_from_db()
        self.assertEqual(old.status, Enrollment.Status.DROPPED)
        self.assertIsNotNone(old.superseded_by_id)
        self.assertEqual(old.superseded_by.offering.group_id, child.pk)
        self.assertEqual(mark.enrollment_id, old.pk)
        self.assertEqual(mark.score, 9)
        self.assertEqual(lesson.offering_id, self.offering.pk)
        # Existing canonical policy moves active writing to the child journal,
        # preserving the teacher while the original marks remain in history.
        from apps.registrar.gradebook import get_offering_journal

        successor = old.superseded_by
        self.assertEqual(successor.offering.instructor_id, self.offering.instructor_id)
        grid = get_offering_journal(offering=successor.offering)
        self.assertIn(self.students[0].student_id, [row["enrollment"].student_id for row in grid["rows"]])

    def test_rollback_of_second_transfer_keeps_children_and_roster_unchanged(self):
        first, second = self._child(), self._child("135 TSPX-2")
        from apps.organizations import student_transfer

        actual = student_transfer.transfer_student_group
        calls = []

        def fail_second(**kwargs):
            calls.append(kwargs)
            if len(calls) == 2:
                raise ValidationError("test failure")
            return actual(**kwargs)

        with patch.object(student_transfer, "transfer_student_group", side_effect=fail_second):
            response = self._split(
                "teaching_office_head", self._payload(self.students[:1], self.students[1:2], (first.name, second.name))
            )
        self.assertEqual(response.status_code, 409, response.content)
        for student in self.students:
            student.refresh_from_db()
            self.assertEqual(student.group_id, self.group.pk)
        for child in (first, second):
            child.refresh_from_db()
            self.assertNotIn("parent_group", child.settings)

    def test_individual_bulk_add_is_atomic_on_late_transfer_failure(self):
        child = self._child()
        from apps.organizations import student_transfer

        actual = student_transfer.transfer_student_group
        calls = []

        def fail_second(**kwargs):
            calls.append(kwargs)
            if len(calls) == 2:
                raise ValidationError("test failure")
            return actual(**kwargs)

        with patch.object(student_transfer, "transfer_student_group", side_effect=fail_second):
            response = self._add(child, self.students[:2])
        self.assertEqual(response.status_code, 409, response.content)
        child.refresh_from_db()
        self.assertNotIn("parent_group", child.settings)
        for student in self.students:
            student.refresh_from_db()
            self.assertEqual(student.group_id, self.group.pk)

    def test_rejects_other_parent_metadata_sector_or_archived_children(self):
        cases = (
            {"linked": True, "parent": self.group_b},
            {"settings": {"language_sector": "EN"}},
            {"settings": {"admission_year": 2099}},
            {"active": False},
        )
        for options in cases:
            with self.subTest(options=options):
                child = self._child(**options)
                self.assertNotEqual(validated_parent(child), self.group)
                response = self._split(
                    "teaching_office_head",
                    self._payload(self.students[:1], self.students[1:2], (child.name, "new-second")),
                )
                self.assertEqual(response.status_code, 400, response.content)
                self.assertEqual(response.json()["error"], "name_taken")
                child.delete()

    def test_no_inference_if_parent_family_is_ambiguous(self):
        child = self._child()
        alias = self._child("135TSPX")
        self.assertIsNone(validated_parent(child))
        self.assertEqual(self._candidates(child).json()["results"], [])
        self.assertEqual(self._add(child, self.students[:1]).status_code, 400)
        alias.delete()
        self.assertEqual(validated_parent(child), self.group)

    def test_parent_drawer_returns_existing_child_names_in_number_order(self):
        second, first = self._child("135 TSPX-2"), self._child()
        payload = self._client("teaching_office_head").get(self._students_url()).json()
        self.assertEqual(
            payload["subgroups"],
            [
                {"id": str(first.pk), "name": first.name, "number": 1},
                {"id": str(second.pk), "name": second.name, "number": 2},
            ],
        )
        self.assertEqual(reusable_children(self.group), [first, second])

    def test_numbered_parent_cannot_capture_another_parent_or_sector(self):
        self._child("135TSPX-1 ing")
        self._child("1351 TSPX-1")
        self._child("135TSPX-2", settings={"sector": "ing", "language_sector": "EN"})
        self.assertEqual(reusable_children(self.group), [])
