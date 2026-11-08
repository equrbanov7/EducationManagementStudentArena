"""Sahib 2026-11-08: başqasının FİN-i ilə köçmüş xanalar düzgün adama; FİN sahibinin yalnız köçmüş, dəyişməmiş xanası
düzəlir; səhv alt qrup qeydiyyatı azad edilir (müəllimin işi varsa yox); hesabı olmayan adam üçün yalnız hesabat."""

import datetime
import io
import json
import re
import tempfile

from django.core.management import call_command
from django.test import TestCase

from apps.organizations.models import OrgUnit
from apps.registrar import services as registrar_services
from apps.registrar.models import Enrollment, Lesson, LessonKind, LessonMark, Subject
from apps.registrar.tests.test_lab_groups_2026_11_06 import WORKFLOW, _LabWorld
from core.constants import OrgUnitType
from core.rls import bypass_rls

OLD_DAY = datetime.date(2026, 10, 10)
LINE = re.compile(r"^legacy_identity: [a-z_]+=[0-9a-z_-]+( [a-z_]+=[0-9a-z_-]+)*$")
CHECK_PLAN = __import__("pathlib").Path(__file__).resolve().parents[1] / "legacy_identity_repair_2026_11_08.json"


def _v(status, score=None):
    return {"status": status, "score": score}


class LegacyIdentityRepairTest(_LabWorld, TestCase):
    def setUp(self):
        self.holder, self.person = self.e0.student, self.e1.student
        with bypass_rls():
            self.owner.is_superuser = True
            self.owner.save(update_fields=["is_superuser"])
            self.lessons = [
                Lesson.objects.create(
                    organization=self.org,
                    offering=self.offering,
                    date=OLD_DAY,
                    start_time=start,
                    kind=LessonKind.SEMINAR,
                    hours=2,
                )
                for start in (datetime.time(9, 0), datetime.time(10, 30), datetime.time(11, 50))
            ]
            l1, l2, l3 = self.lessons
            mark = LessonMark.objects.create
            mark(organization=self.org, lesson=l1, enrollment=self.e0, status="present", score=7)  # köçmüş, başqasının
            mark(organization=self.org, lesson=l2, enrollment=self.e0, status="present")  # köçmüş, sahibinki q/b idi
            mark(organization=self.org, lesson=l2, enrollment=self.e1, status="absent", entered_by=self.teacher)
            mark(organization=self.org, lesson=l3, enrollment=self.e0, status="present", entered_by=self.teacher)
            # Səhv alt qrup qeydiyyatları (başqa qrupun jurnalı): biri boş, birində müəllimin xanası var.
            other_group = OrgUnit.objects.create(
                organization=self.org, name="LAB-G2", slug="lab-g2", unit_type=OrgUnitType.GROUP
            )
            self.guests = []
            for code in ("LAB201", "LAB202"):
                offering = registrar_services.get_or_create_offering(
                    organization=self.org,
                    subject=Subject.objects.create(organization=self.org, code=code, name=code),
                    period=self.period,
                    group=other_group,
                )
                self.guests.append(
                    Enrollment.objects.create(
                        organization=self.org, student=self.holder, offering=offering, source_group=self.group
                    )
                )
            taught = Lesson.objects.create(
                organization=self.org, offering=self.guests[1].offering, date=OLD_DAY, kind=LessonKind.SEMINAR, hours=2
            )
            mark(
                organization=self.org,
                lesson=taught,
                enrollment=self.guests[1],
                status="absent",
                entered_by=self.teacher,
            )

        def item(lesson_index, value, *, holder_value=None, fix=False, own=None, date="2026-10-10"):
            starts = ("09:00", "10:30", "11:50")
            return {
                "offering": str(self.offering.pk),
                "date": date,
                "start_time": starts[lesson_index],
                "holder_enrollment": str(self.e0.pk),
                "value": value,
                "holder_value": holder_value,
                "holder_fix": fix,
                "holder_own": own,
            }

        items = [
            item(0, _v("present", 7), holder_value=_v("present", 7), fix=True),
            item(1, _v("present"), holder_value=_v("present"), fix=True, own=_v("absent")),
            item(2, _v("present"), holder_value=_v("present"), fix=True),
            item(0, _v("present"), date="2026-10-11"),
        ]
        plan = {
            "format": "legacy-identity/1",
            "cases": [
                {
                    "key": "a",
                    "holder": self.holder.pk,
                    "person": self.person.pk,
                    "items": items,
                    "releases": [{"enrollment": str(row.pk), "offering": str(row.offering_id)} for row in self.guests],
                },
                {"key": "b", "holder": self.holder.pk, "person": None, "items": items[:2], "releases": []},
            ],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(plan, handle)
        self.plan = handle.name

    def _call(self, *extra):
        out = io.StringIO()
        call_command(
            "repair_legacy_identity_20261108",
            "--org",
            self.org.slug,
            "--actor",
            self.owner.username,
            *extra,
            stdout=out,
        )
        counts = {}
        for line in out.getvalue().splitlines():
            self.assertRegex(line, LINE)
            if "mode=" not in line:
                counts.update(pair.split("=", 1) for pair in line[len("legacy_identity: ") :].split())
        return counts

    def _cell(self, lesson, enrollment):
        with bypass_rls():
            mark = LessonMark.objects.filter(lesson=lesson, enrollment=enrollment).first()
        return None if mark is None else (mark.status, None if mark.score is None else int(mark.score))

    def _status(self, enrollment):
        with bypass_rls():
            return Enrollment.objects.get(pk=enrollment.pk).status

    def test_dry_run_then_apply_idempotent_and_undo(self):
        l1, l2, l3 = self.lessons
        dry = self._call("--file", self.plan)
        self.assertEqual((dry["a_person_filled"], dry["a_holder_deleted"], dry["a_released"]), ("2", "1", "1"))
        self.assertEqual(self._cell(l1, self.e0), ("present", 7))
        self.assertEqual(self._status(self.guests[0]), "enrolled")

        counts = self._call("--file", self.plan, "--apply")
        self.assertEqual(counts["a_person_filled"], "2")  # L1 + L3 adamın boş xanası
        self.assertEqual(counts["a_person_cell_conflict"], "1")  # müəllimin «q/b»-si dəyişmir
        self.assertEqual(counts["a_holder_deleted"], "1")
        self.assertEqual(counts["a_holder_restored_own"], "1")
        self.assertEqual(counts["a_holder_teacher_or_edited_kept"], "1")
        self.assertEqual(counts["a_lesson_missing"], "1")
        self.assertEqual((counts["a_released"], counts["a_release_teacher_work_kept"]), ("1", "1"))
        self.assertEqual((counts["b_no_person_account"], counts["b_no_account_cells"]), ("1", "2"))
        self.assertEqual(self._cell(l1, self.e1), ("present", 7))
        self.assertIsNone(self._cell(l1, self.e0))
        self.assertEqual(self._cell(l2, self.e0), ("absent", None))
        self.assertEqual(self._cell(l2, self.e1), ("absent", None))
        self.assertEqual(self._cell(l3, self.e0), ("present", None))  # müəllimin yazdığı qalır
        self.assertEqual(self._status(self.guests[0]), "dropped")
        self.assertEqual(self._status(self.guests[1]), "enrolled")
        with bypass_rls():
            self.assertEqual(Enrollment.objects.get(pk=self.e0.pk).absence_hours, 2)

        again = self._call("--file", self.plan, "--apply")
        self.assertEqual((again["a_person_cell_same"], again["a_person_cell_conflict"]), ("2", "1"))
        self.assertEqual((again["a_holder_cell_empty"], again["a_holder_already_own"]), ("1", "1"))
        self.assertEqual(again["a_release_already_dropped"], "1")
        self.assertNotIn("a_person_filled", again)

        undo = self._call("--apply", "--undo")
        self.assertEqual((undo["undo_person_deleted"], undo["undo_holder_reverted"]), ("2", "1"))
        self.assertEqual((undo["undo_holder_recreated"], undo["undo_reenrolled"]), ("1", "1"))
        self.assertEqual(self._cell(l1, self.e0), ("present", 7))
        self.assertIsNone(self._cell(l1, self.e1))
        self.assertEqual(self._cell(l2, self.e0), ("present", None))
        self.assertEqual(self._status(self.guests[0]), "enrolled")
        self.assertEqual(self._call("--apply", "--undo"), {"undo_already_done": "1"})

    def test_repo_plan_is_ids_only(self):
        from apps.registrar.legacy_identity_repair_2026_11_08 import load_plan

        cases = load_plan(CHECK_PLAN)
        self.assertEqual([case["key"] for case in cases], ["a", "b", "c", "d"])
        self.assertIsNone(cases[1]["person"])
        text = CHECK_PLAN.read_text(encoding="utf-8")
        # Ad / FİN yoxdur: yalnız uuid, köhnə jurnal açarı, tarix, saat, status və rəqəmlər.
        for token in re.findall(r'"([^"]*)"', text):
            self.assertRegex(
                token,
                r"^([0-9a-f-]{36}|[A-Za-z0-9]{10}|\d{4}-\d\d-\d\d|\d\d:\d\d|[a-z_]+|legacy-identity/1|"
                r"prod copy 2026-11-02 \+ old system myedu_new \(semester 14\))$",
            )

    def test_workflow_wiring(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - repair_legacy_identity_20261108\n", text)
        self.assertIn('[ "$COMMAND" = "repair_legacy_identity_20261108" ]', text)
        self.assertIn("legacy_identity", text.split("grep -E '^(twin_relocate|")[1].split("):")[0])
