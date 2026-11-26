"""Bir plan sətrində seminar və laboratoriyanın fərqli qrup bölgüsü."""

from apps.organizations.models import OrgUnit
from apps.registrar.models import Enrollment, LabGroup, SeminarGroup
from apps.workload.models import TeachingTaskRow
from apps.workload.services.subject_cards import cards_page
from core.constants import OrgUnitType

from .test_split_wizard_2026_11_26 import WizardBase


class SplitWizardActivityModesTests(WizardBase):
    code = "WM"

    def add_second_group(self):
        second = OrgUnit.objects.create(
            organization=self.org,
            name="WM 236 K",
            slug="wm-g236",
            unit_type=OrgUnitType.GROUP,
            parent=self.stack["specialty"],
        )
        self.row.groups.add(second)
        return second

    def journal_snapshot(self, kind):
        model = {"seminar": SeminarGroup, "lab": LabGroup}[kind]
        groups = list(
            model.objects.filter(offering=self.offering)
            .order_by("number")
            .values_list("pk", "number", "name", "updated_at")
        )
        roster = dict(Enrollment.objects.filter(offering=self.offering).values_list("pk", kind + "_group"))
        return groups, roster

    def check_mixed_save(self, joint, separate):
        seed = self._save(self._payload(lecture=False))
        self.assertEqual(seed.status_code, 200, seed.content)
        preserved = self.journal_snapshot(joint)
        second = self.add_second_group()
        payload = self._payload(lecture=False)
        row = payload["rows"][0]
        row["joint_by_activity"] = {joint: True, separate: False}
        group = payload["groups"][0]
        # The hidden panel can contain stale/empty values. Editing its sibling must preserve the actual journal.
        group[joint] = {"count": 0, "names": [], "placement": {}}
        group[separate]["names"][0] = "Yenilənmiş bölmə"
        originals = [u for u in payload["units"] if u["activity"] == separate]
        template = originals[0]
        payload["units"] = originals + [
            {**template, "group_id": str(second.pk), "sub_number": None},
            {
                **template,
                "activity": joint,
                "group_id": "",
                "sub_number": None,
                "hours": 30 if joint == "seminar" else 15,
            },
        ]
        response = self._save(payload)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.journal_snapshot(joint), preserved)
        self.assertEqual(self.journal_snapshot(separate)[0][0][2], "Yenilənmiş bölmə")
        for kind, count in [(joint, 1), (separate, len(originals) + 1)]:
            assignments = [a for a in self._section_assignments() if a.activity == kind]
            self.assertEqual(len(assignments), count)
            if kind == joint:
                self.assertIsNone(assignments[0].group_id)
            else:
                self.assertEqual({a.group_id for a in assignments}, {self.group.pk, second.pk})
        self.row.refresh_from_db()
        self.assertEqual(
            (self.row.subgroup_count, self.row.lab_group_count, self.row.seminar_total, self.row.lab_total),
            (1, 5, 30, 75) if joint == "seminar" else (3, 1, 90, 15),
        )
        state_row = self._state().json()["rows"][0]
        self.assertEqual(state_row["joint_by_activity"], row["joint_by_activity"])
        self.assertEqual(state_row["joint"], joint == "seminar")
        card = cards_page(self.task, limit=1)["cards"][0]
        self.assertEqual([line["joint"] for line in card[joint]["lines"]], [True])
        self.assertEqual({line["group_id"] for line in card[separate]["lines"]}, {str(self.group.pk), str(second.pk)})
        response = self._save(payload)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(any(response.json()["summary"].values()), response.content)
        self.assertEqual(self.journal_snapshot(joint), preserved)

    def test_seminars_together_lab_groups_separate(self):
        self.check_mixed_save("seminar", "lab")

    def test_seminar_groups_separate_labs_together(self):
        self.check_mixed_save("lab", "seminar")

    def test_lab_follows_seminar_count_when_zero_and_old_joint_post_still_applies_to_both(self):
        self.add_second_group()
        TeachingTaskRow.objects.filter(pk=self.row.pk).update(subgroup_count=3, lab_group_count=0)
        self.assertEqual(self._state().json()["rows"][0]["joint_by_activity"], {"seminar": False, "lab": False})
        payload = self._payload(lecture=False)
        payload["rows"][0]["joint"] = True
        payload["units"] = [
            {
                "row_id": str(self.row.pk),
                "activity": kind,
                "group_id": "",
                "teacher_id": str(self.teachers[0].pk),
                "hours": hours,
            }
            for kind, hours in [("seminar", 30), ("lab", 15)]
        ]
        response = self._save(payload)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self._state().json()["rows"][0]["joint_by_activity"], {"seminar": True, "lab": True})

    def test_lab_only_fix_preserves_inactive_seminar_count(self):
        second = self.add_second_group()
        TeachingTaskRow.objects.filter(pk=self.row.pk).update(
            seminar_plan=0, seminar_total=0, subgroup_count=7, lab_group_count=0
        )
        payload = self._payload(lecture=False)
        payload["rows"][0]["joint_by_activity"] = {"lab": False}
        payload["groups"][0].update(apply_journal=False, lab={"count": 0})
        payload["units"] = [
            {"row_id": str(self.row.pk), "activity": "lab", "group_id": str(group.pk), "teacher_id": ""}
            for group in (self.group, second)
        ]
        response = self._save(payload)
        self.assertEqual(response.status_code, 200, response.content)
        self.row.refresh_from_db()
        self.assertEqual((self.row.subgroup_count, self.row.lab_group_count, self.row.lab_total), (7, 2, 30))
